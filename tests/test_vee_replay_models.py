from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    InitialMeasurement,
    PipelineRun,
    VeeException,
    VeeExecutionLog,
    VeeReplayRequest,
    VeeReplayRequestItem,
)
from app.services.seeds import seed_demo_environment


def _seed_replay_context(session) -> tuple[InitialMeasurement, VeeException]:
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert initial is not None

    pipeline_run = PipelineRun(
        pipeline_name="vee",
        trigger_type="manual",
        status="processing",
        started_at=datetime.now(timezone.utc),
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
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        summary_code="vee_failed_required_field",
        details={"rule_hits": 1},
    )
    session.add(execution)
    session.flush()

    vee_exception = VeeException(
        initial_measurement_id=initial.id,
        vee_execution_log_id=execution.id,
        exception_code="vee_required_field_missing",
        severity="error",
        exception_status="open",
        blocking_finalization=True,
        detected_at=datetime.now(timezone.utc),
        details={"field": "unit_of_measure"},
    )
    session.add(vee_exception)
    session.commit()

    return initial, vee_exception


def test_vee_replay_request_links_scope_entities_and_pipeline_runs(session):
    initial, vee_exception = _seed_replay_context(session)

    request = VeeReplayRequest(
        request_scope="hes_system",
        status="queued",
        requested_by="operator_ui",
        hes_system_id=initial.canonical_measurement.hes_read_raw.hes_system_id,
        details={"source": "test"},
    )
    session.add(request)
    session.flush()

    item = VeeReplayRequestItem(
        vee_replay_request_id=request.id,
        initial_measurement_id=initial.id,
        representative_vee_exception_id=vee_exception.id,
        status="pending",
        details={"source": "test"},
    )
    session.add(item)
    session.flush()

    pipeline_run = PipelineRun(
        pipeline_name="vee_replay",
        trigger_type="manual",
        status="processing",
        vee_replay_request_id=request.id,
        started_at=datetime.now(timezone.utc),
        details={"scope": "hes_system"},
    )
    session.add(pipeline_run)
    session.commit()

    refreshed = session.get(VeeReplayRequest, request.id)
    assert refreshed is not None
    assert refreshed.hes_system is not None
    assert len(refreshed.request_items) == 1
    assert len(refreshed.pipeline_runs) == 1
    assert refreshed.request_items[0].initial_measurement_id == initial.id
    assert refreshed.request_items[0].representative_vee_exception_id == vee_exception.id
    assert refreshed.pipeline_runs[0].pipeline_name == "vee_replay"


def test_vee_replay_request_item_allows_only_one_initial_per_request(session):
    initial, vee_exception = _seed_replay_context(session)

    request = VeeReplayRequest(
        request_scope="hes_system",
        status="queued",
        requested_by="operator_ui",
        hes_system_id=initial.canonical_measurement.hes_read_raw.hes_system_id,
        details={"source": "test"},
    )
    session.add(request)
    session.flush()

    first = VeeReplayRequestItem(
        vee_replay_request_id=request.id,
        initial_measurement_id=initial.id,
        representative_vee_exception_id=vee_exception.id,
        status="pending",
        details={"source": "first"},
    )
    duplicate = VeeReplayRequestItem(
        vee_replay_request_id=request.id,
        initial_measurement_id=initial.id,
        representative_vee_exception_id=vee_exception.id,
        status="pending",
        details={"source": "duplicate"},
    )
    session.add(first)
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
