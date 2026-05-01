from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import (
    InitialMeasurement,
    OperationalEvent,
    PipelineRun,
    VeeException,
    VeeExecutionLog,
    VeeReplayRequest,
    VeeReplayRequestItem,
)
from app.services.hes_systems import ensure_hes_system
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_master_data
from app.services.vee_replay_processor import process_queued_vee_replay_requests
from app.services.vee_replay_requests import create_vee_replay_request


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
) -> InitialMeasurement:
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
    assert initial is not None
    return initial


def _attach_vee_exception(
    session,
    initial: InitialMeasurement,
    *,
    exception_code: str = "vee_required_field_missing",
) -> VeeException:
    detected = datetime.now(timezone.utc)
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
        severity="error",
        exception_status="open",
        blocking_finalization=True,
        detected_at=detected,
        details={"source": "test"},
    )
    session.add(vee_exception)
    session.commit()
    return vee_exception


def test_process_queued_vee_replay_requests_completes_single_request(session):
    hes_system_id = _prepare_replay_environment(session)
    initial = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-process-one",
        measured_at="2026-05-10T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial)
    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )
    session.commit()

    summary = process_queued_vee_replay_requests(session, limit=1, processed_by="worker_a")

    request = session.get(VeeReplayRequest, created.request.id)
    item = session.scalar(
        select(VeeReplayRequestItem)
        .where(VeeReplayRequestItem.vee_replay_request_id == created.request.id)
        .limit(1)
    )
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.vee_replay_request_id == created.request.id)
        .limit(1)
    )

    assert summary.claimed_requests == 1
    assert summary.completed_requests == 1
    assert summary.failed_requests == 0
    assert summary.processed_items == 1
    assert summary.succeeded_items == 1
    assert summary.failed_items == 0
    assert request is not None
    assert request.status == "completed"
    assert request.started_at is not None
    assert request.completed_at is not None
    assert request.processed_count == 1
    assert request.succeeded_count == 1
    assert request.failed_count == 0
    assert request.details["progress_percent"] == 100.0
    assert request.details["remaining_count"] == 0
    assert item is not None
    assert item.status == "completed"
    assert item.vee_execution_log_id is not None
    assert item.current_final_measurement_id is not None
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    started_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "vee_replay_started")
        .where(OperationalEvent.entity_id == request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    completed_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "vee_replay_completed")
        .where(OperationalEvent.entity_id == request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert started_event is not None
    assert completed_event is not None


def test_process_queued_vee_replay_requests_marks_request_failed_when_one_item_errors(
    session,
    monkeypatch,
):
    hes_system_id = _prepare_replay_environment(session)
    initial_one = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-process-two-a",
        measured_at="2026-05-11T00:00:00+09:00",
    )
    initial_two = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-process-two-b",
        measured_at="2026-05-12T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial_one)
    _attach_vee_exception(session, initial_two)
    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )
    session.commit()

    items = session.scalars(
        select(VeeReplayRequestItem)
        .where(VeeReplayRequestItem.vee_replay_request_id == created.request.id)
        .order_by(VeeReplayRequestItem.id.asc())
    ).all()
    failing_exception_id = items[0].representative_vee_exception_id

    from app.services import vee_replay_processor as replay_processor_module

    original_replay = replay_processor_module.reevaluate_vee_exception_and_replay

    def _flaky_replay(db_session, vee_exception_id, *, reevaluated_by, operator_memo=None):
        if vee_exception_id == failing_exception_id:
            raise RuntimeError("forced replay failure")
        return original_replay(
            db_session,
            vee_exception_id,
            reevaluated_by=reevaluated_by,
            operator_memo=operator_memo,
        )

    monkeypatch.setattr(
        replay_processor_module,
        "reevaluate_vee_exception_and_replay",
        _flaky_replay,
    )

    summary = process_queued_vee_replay_requests(session, limit=1, processed_by="worker_b")

    request = session.get(VeeReplayRequest, created.request.id)
    refreshed_items = session.scalars(
        select(VeeReplayRequestItem)
        .where(VeeReplayRequestItem.vee_replay_request_id == created.request.id)
        .order_by(VeeReplayRequestItem.id.asc())
    ).all()
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.vee_replay_request_id == created.request.id)
        .limit(1)
    )

    assert summary.claimed_requests == 1
    assert summary.completed_requests == 0
    assert summary.failed_requests == 1
    assert summary.processed_items == 2
    assert summary.succeeded_items == 1
    assert summary.failed_items == 1
    assert request is not None
    assert request.status == "failed"
    assert request.processed_count == 2
    assert request.succeeded_count == 1
    assert request.failed_count == 1
    assert request.last_error == "forced replay failure"
    assert request.details["progress_percent"] == 100.0
    assert {row.status for row in refreshed_items} == {"completed", "failed"}
    failed_item = next(row for row in refreshed_items if row.status == "failed")
    completed_item = next(row for row in refreshed_items if row.status == "completed")
    assert failed_item.result_code == "processing_error"
    assert failed_item.details["error_summary"] == "forced replay failure"
    assert completed_item.current_final_measurement_id is not None
    assert pipeline_run is not None
    assert pipeline_run.status == "failed"
    failed_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "vee_replay_failed")
        .where(OperationalEvent.entity_id == request.id)
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert failed_event is not None


def test_process_vee_replay_requests_cli_processes_queued_request(app, session):
    hes_system_id = _prepare_replay_environment(session)
    initial = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-cli-batch",
        measured_at="2026-05-13T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial)
    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )
    session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["process-vee-replay-requests", "--limit", "1"])

    refreshed = session.get(VeeReplayRequest, created.request.id)

    assert result.exit_code == 0
    assert "claimed_requests=1" in result.output
    assert "completed_requests=1" in result.output
    assert refreshed is not None
    assert refreshed.status == "completed"
