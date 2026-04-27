from __future__ import annotations

from datetime import datetime, timezone
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.models import InitialMeasurement, PipelineRun, VeeException, VeeExecutionLog
from app.services.seeds import seed_demo_environment


def _get_initial_measurement(session) -> InitialMeasurement:
    seed_demo_environment(session)
    session.commit()

    row = session.scalar(select(InitialMeasurement).limit(1))
    assert row is not None
    return row


def test_initial_measurement_links_to_canonical_and_master_context(session):
    row = _get_initial_measurement(session)
    session.commit()

    assert row.canonical_measurement is not None
    assert row.canonical_measurement.id == row.canonical_measurement_id
    assert row.measuring_component is not None
    assert row.device is not None
    assert row.service_point is not None
    assert row.value == row.canonical_measurement.value


def test_initial_measurement_allows_only_one_row_per_canonical(session):
    first = _get_initial_measurement(session)

    duplicate = InitialMeasurement(
        canonical_measurement_id=first.canonical_measurement_id,
        measuring_component_id=first.measuring_component_id,
        device_id=first.device_id,
        service_point_id=first.service_point_id,
        measured_at=first.measured_at,
        value=first.value,
        quality_code=first.quality_code,
        status_code=first.status_code,
        unit_of_measure=first.unit_of_measure,
        initial_status="ready",
        ready_for_vee_at=datetime.now(timezone.utc),
        details={"source": "duplicate"},
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_vee_execution_log_and_exception_link_to_initial_measurement(session):
    initial = _get_initial_measurement(session)
    existing_log_count = len(initial.vee_execution_logs)
    existing_exception_count = len(initial.vee_exceptions)
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

    exception = VeeException(
        initial_measurement_id=initial.id,
        vee_execution_log_id=execution.id,
        exception_code="vee_required_field_missing",
        severity="error",
        exception_status="open",
        blocking_finalization=True,
        detected_at=datetime.now(timezone.utc),
        details={"field": "unit_of_measure"},
    )
    session.add(exception)
    session.commit()

    execution_count = session.scalar(
        select(func.count(VeeExecutionLog.id)).where(
            VeeExecutionLog.initial_measurement_id == initial.id
        )
    )
    exception_count = session.scalar(
        select(func.count(VeeException.id)).where(
            VeeException.initial_measurement_id == initial.id
        )
    )
    assert execution_count == existing_log_count + 1
    assert exception_count == existing_exception_count + 1
    assert session.get(VeeExecutionLog, execution.id) is not None
    assert session.get(VeeException, exception.id) is not None
    assert execution.pipeline_run is not None
    assert execution.pipeline_run.pipeline_name == "vee"
    assert exception.vee_execution_log is not None
    assert exception.vee_execution_log.id == execution.id
