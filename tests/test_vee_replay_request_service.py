from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import IngestBatch, InitialMeasurement, PipelineRun, VeeException, VeeExecutionLog
from app.services.hes_systems import ensure_hes_system
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_master_data
from app.services.vee_replay_requests import (
    VeeReplayRequestError,
    create_vee_replay_request,
)


def _prepare_replay_environment(session) -> int:
    seed_master_data(session)
    hes_system = ensure_hes_system(
        session,
        hes_code="HES",
        display_name="Demo HES",
        source_family="hes",
        default_delivery_mode="poll",
        timezone_name="Asia/Seoul",
    )
    session.commit()
    return hes_system.id


def _ingest_initial_measurement(
    session,
    *,
    hes_system_id: int,
    batch_id: str,
    measured_at: str,
) -> tuple[InitialMeasurement, int]:
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": batch_id,
            "received_at": "2026-05-01T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": measured_at,
                    "value": 1.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                    "interval_size_minutes": 60,
                }
            ],
        },
        hes_system_id=hes_system_id,
    )
    session.commit()

    initial = session.scalar(
        select(InitialMeasurement)
        .where(InitialMeasurement.measured_at == datetime.fromisoformat(measured_at))
        .order_by(InitialMeasurement.id.desc())
        .limit(1)
    )
    batch = session.scalar(select(IngestBatch).where(IngestBatch.batch_id == batch_id).limit(1))
    assert initial is not None
    assert batch is not None
    return initial, batch.id


def _attach_vee_exception(
    session,
    initial: InitialMeasurement,
    *,
    exception_status: str = "open",
    blocking_finalization: bool = True,
    exception_code: str = "vee_required_field_missing",
    severity: str = "error",
    detected_at: datetime | None = None,
) -> VeeException:
    detected = detected_at or datetime.now(timezone.utc)
    pipeline_run = PipelineRun(
        pipeline_name="vee",
        trigger_type="manual",
        status="processing",
        started_at=detected,
        details={"scope": "measurement"},
    )
    session.add(pipeline_run)
    session.flush()

    execution = VeeExecutionLog(
        initial_measurement_id=initial.id,
        pipeline_run_id=pipeline_run.id,
        execution_scope="measurement",
        trigger_type="manual",
        rule_set_code="vee_baseline_v1",
        execution_status="completed_with_exception",
        started_at=detected,
        completed_at=detected,
        summary_code=exception_code,
        details={"rule_hits": 1},
    )
    session.add(execution)
    session.flush()

    vee_exception = VeeException(
        initial_measurement_id=initial.id,
        vee_execution_log_id=execution.id,
        exception_code=exception_code,
        severity=severity,
        exception_status=exception_status,
        blocking_finalization=blocking_finalization,
        detected_at=detected,
        resolved_at=detected if exception_status == "resolved" else None,
        resolution_type="operator_resolved" if exception_status == "resolved" else None,
        details={"source": "test"},
    )
    session.add(vee_exception)
    session.commit()
    return vee_exception


def test_create_vee_replay_request_for_hes_system_scope(session):
    hes_system_id = _prepare_replay_environment(session)
    initial, _batch_id = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-hes-batch",
        measured_at="2026-05-01T00:00:00+09:00",
    )
    vee_exception = _attach_vee_exception(session, initial)

    result = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
        operator_memo="scope test",
    )
    session.commit()

    request = result.request
    assert result.created_item_count == 1
    assert request.request_scope == "hes_system"
    assert request.status == "queued"
    assert request.target_initial_count == 1
    assert request.hes_system_id == hes_system_id
    assert len(request.request_items) == 1
    item = request.request_items[0]
    assert item.initial_measurement_id == initial.id
    assert item.representative_vee_exception_id == vee_exception.id
    assert item.details["exception_code"] == vee_exception.exception_code
    assert item.details["service_point_id"] == initial.service_point_id


def test_create_vee_replay_request_filters_by_ingest_batch_scope(session):
    hes_system_id = _prepare_replay_environment(session)
    initial_one, batch_one_id = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-batch-one",
        measured_at="2026-05-01T01:00:00+09:00",
    )
    initial_two, _batch_two_id = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-batch-two",
        measured_at="2026-05-02T01:00:00+09:00",
    )
    _attach_vee_exception(session, initial_one)
    _attach_vee_exception(session, initial_two)

    result = create_vee_replay_request(
        session,
        request_scope="ingest_batch",
        requested_by="operator_ui",
        ingest_batch_id=batch_one_id,
    )

    assert result.created_item_count == 1
    assert result.request.target_initial_count == 1
    assert result.request.request_items[0].initial_measurement_id == initial_one.id


def test_create_vee_replay_request_filters_by_date_range_scope(session):
    hes_system_id = _prepare_replay_environment(session)
    initial_in_range, _ = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-range-in",
        measured_at="2026-05-03T12:00:00+09:00",
    )
    initial_out_of_range, _ = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-range-out",
        measured_at="2026-05-10T12:00:00+09:00",
    )
    _attach_vee_exception(session, initial_in_range)
    _attach_vee_exception(session, initial_out_of_range)

    result = create_vee_replay_request(
        session,
        request_scope="date_range",
        requested_by="operator_ui",
        measured_at_from=datetime.fromisoformat("2026-05-03T00:00:00+09:00"),
        measured_at_to=datetime.fromisoformat("2026-05-04T00:00:00+09:00"),
        window_timezone_name="Asia/Seoul",
    )

    assert result.created_item_count == 1
    assert result.request.target_initial_count == 1
    assert result.request.request_items[0].initial_measurement_id == initial_in_range.id


def test_create_vee_replay_request_dedupes_by_initial_and_prefers_blocking_exception(session):
    hes_system_id = _prepare_replay_environment(session)
    initial, _batch_id = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-dedupe-batch",
        measured_at="2026-05-05T00:00:00+09:00",
    )
    warning_exception = _attach_vee_exception(
        session,
        initial,
        exception_code="vee_zero_value_detected",
        severity="warning",
        blocking_finalization=False,
        detected_at=datetime(2026, 5, 5, 3, 0, tzinfo=timezone.utc),
    )
    blocking_exception = _attach_vee_exception(
        session,
        initial,
        exception_code="vee_required_field_missing",
        severity="error",
        blocking_finalization=True,
        detected_at=datetime(2026, 5, 5, 2, 0, tzinfo=timezone.utc),
    )

    result = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )

    assert result.created_item_count == 1
    item = result.request.request_items[0]
    assert item.initial_measurement_id == initial.id
    assert item.representative_vee_exception_id == blocking_exception.id
    assert item.representative_vee_exception_id != warning_exception.id


def test_create_vee_replay_request_rejects_scope_without_active_targets(session):
    hes_system_id = _prepare_replay_environment(session)
    initial, _batch_id = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-empty-batch",
        measured_at="2026-05-06T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial, exception_status="resolved")

    with pytest.raises(VeeReplayRequestError) as exc_info:
        create_vee_replay_request(
            session,
            request_scope="hes_system",
            requested_by="operator_ui",
            hes_system_id=hes_system_id,
        )

    assert exc_info.value.error_code == "no_targets_found"


def test_create_vee_replay_request_rejects_duplicate_active_scope(session):
    hes_system_id = _prepare_replay_environment(session)
    initial, _batch_id = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-duplicate-batch",
        measured_at="2026-05-07T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial)

    first = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )
    assert first.created_item_count == 1

    with pytest.raises(VeeReplayRequestError) as exc_info:
        create_vee_replay_request(
            session,
            request_scope="hes_system",
            requested_by="operator_ui",
            hes_system_id=hes_system_id,
        )

    assert exc_info.value.error_code == "request_already_active"
