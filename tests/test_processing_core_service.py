from __future__ import annotations

from sqlalchemy import func, select

from app.models import (
    CanonicalMeasurement,
    InitialMeasurement,
    RawIntervalWindowState,
    VeeException,
    VeeExecutionLog,
)
from app.services.processing_core import ensure_processing_core_lineage
from app.services.vee import evaluate_or_get_vee_baseline
from app.services.seeds import seed_demo_environment


def _reset_vee_baseline(session, initial: InitialMeasurement) -> None:
    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    session.flush()


def test_ensure_processing_core_lineage_creates_initial_measurement_and_pass_through_log(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    assert canonical is not None

    initial = ensure_processing_core_lineage(session, canonical)
    session.commit()

    log = session.scalar(
        select(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
        .order_by(VeeExecutionLog.id.asc())
        .limit(1)
    )

    assert initial.canonical_measurement_id == canonical.id
    assert initial.initial_status == "accepted"
    assert log is not None
    assert log.execution_status == "passed"
    assert log.summary_code == "vee_passed"


def test_ensure_processing_core_lineage_is_idempotent(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    assert canonical is not None

    ensure_processing_core_lineage(session, canonical)
    ensure_processing_core_lineage(session, canonical)
    session.commit()

    assert session.scalar(select(func.count()).select_from(InitialMeasurement)) == 1
    assert session.scalar(select(func.count()).select_from(VeeExecutionLog)) == 1


def test_evaluate_or_get_vee_baseline_marks_missing_unit_as_exception(session):
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert initial is not None
    _reset_vee_baseline(session, initial)
    initial.unit_of_measure = ""

    execution, created = evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .limit(1)
    )

    assert created is True
    assert initial.initial_status == "exception"
    assert execution.execution_status == "completed_with_exception"
    assert execution.summary_code == "vee_failed_required_field"
    assert exception is not None
    assert exception.exception_code == "vee_required_field_missing"


def test_evaluate_or_get_vee_baseline_marks_duplicate_source_as_exception(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert canonical is not None
    assert initial is not None
    _reset_vee_baseline(session, initial)
    canonical.hes_read_raw.is_duplicate = True
    canonical.hes_read_raw.canonical_status = "duplicate"

    execution, created = evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .limit(1)
    )

    assert created is True
    assert initial.initial_status == "exception"
    assert execution.execution_status == "completed_with_exception"
    assert execution.summary_code == "vee_completed_with_duplicate"
    assert exception is not None
    assert exception.exception_code == "vee_duplicate_detected"


def test_evaluate_or_get_vee_baseline_marks_zero_value_as_non_blocking_warning(session):
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert initial is not None
    _reset_vee_baseline(session, initial)
    initial.value = 0

    execution, created = evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .limit(1)
    )

    assert created is True
    assert initial.initial_status == "accepted"
    assert execution.execution_status == "completed_with_exception"
    assert execution.summary_code == "vee_completed_with_zero_value"
    assert exception is not None
    assert exception.exception_code == "vee_zero_value_detected"
    assert exception.blocking_finalization is False


def test_evaluate_or_get_vee_baseline_marks_invalid_interval_size_as_blocking(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert canonical is not None
    assert initial is not None
    _reset_vee_baseline(session, initial)
    canonical.hes_read_raw.interval_size_minutes = 17

    execution, created = evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .limit(1)
    )

    assert created is True
    assert initial.initial_status == "exception"
    assert execution.execution_status == "completed_with_exception"
    assert execution.summary_code == "vee_failed_interval_size"
    assert exception is not None
    assert exception.exception_code == "vee_interval_size_invalid"
    assert exception.blocking_finalization is True


def test_evaluate_or_get_vee_baseline_marks_partial_window_as_missing_interval(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert canonical is not None
    assert initial is not None
    assert canonical.hes_read_raw is not None
    raw_row = canonical.hes_read_raw
    assert raw_row.source_system is not None
    assert raw_row.meter_identifier is not None
    assert raw_row.channel_identifier is not None
    raw_row.source_business_ts = raw_row.measured_at
    assert raw_row.source_business_ts is not None

    _reset_vee_baseline(session, initial)
    session.add(
        RawIntervalWindowState(
            source_system=raw_row.source_system,
            meter_identifier=raw_row.meter_identifier,
            channel_identifier=raw_row.channel_identifier,
            window_start_at=raw_row.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=raw_row.interval_size_minutes,
            expected_slot_count=4,
            received_slot_count=2,
            received_slot_bitmap="00,15",
            completion_status="partial",
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.flush()

    execution, created = evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .limit(1)
    )

    assert created is True
    assert initial.initial_status == "exception"
    assert execution.execution_status == "completed_with_exception"
    assert execution.summary_code == "vee_failed_missing_interval"
    assert exception is not None
    assert exception.exception_code == "vee_missing_interval_detected"
    assert exception.blocking_finalization is True
