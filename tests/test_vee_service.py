from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    InitialMeasurement,
    OperationalEvent,
    RawIntervalWindowState,
    VeeException,
    VeeExecutionLog,
)
from app.services.auth import create_user_account
from app.services.finalization import is_initial_measurement_finalizable
from app.services.seeds import seed_demo_environment
from app.services.vee import (
    acknowledge_vee_exception,
    evaluate_or_get_vee_baseline,
    reevaluate_vee_exception,
    resolve_vee_exception,
)


def _reset_vee_baseline(session, initial: InitialMeasurement) -> None:
    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    session.flush()


def _prepare_clean_initial(session) -> InitialMeasurement:
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None
    assert initial.measuring_component is not None
    assert initial.canonical_measurement.hes_read_raw is not None

    _reset_vee_baseline(session, initial)
    initial.value = Decimal("10.0000")
    initial.unit_of_measure = "kWh"
    initial.measuring_component.unit_of_measure = "kWh"
    initial.measuring_component.multiplier = 1.0

    raw_row = initial.canonical_measurement.hes_read_raw
    raw_row.interval_size_minutes = 60
    raw_row.is_duplicate = False
    raw_row.canonical_status = "mapped"
    raw_row.source_business_ts = raw_row.measured_at

    for row in session.scalars(select(RawIntervalWindowState)).all():
        session.delete(row)
    session.flush()
    return initial


def _prepare_required_field_exception(session) -> tuple[InitialMeasurement, VeeException]:
    initial = _prepare_clean_initial(session)
    initial.unit_of_measure = ""
    session.flush()

    evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert vee_exception is not None
    return initial, vee_exception


def test_acknowledge_vee_exception_keeps_initial_measurement_blocked_for_finalization(session):
    initial, vee_exception = _prepare_required_field_exception(session)
    actor = create_user_account(
        session,
        login_id="vee-ack",
        display_name="VEE Ack",
        role_code="operator",
        password="secret-password",
    )
    session.commit()

    opened_alert = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.event_code == "vee_exception_opened",
            OperationalEvent.entity_type == "vee_exception",
            OperationalEvent.entity_id == vee_exception.id,
        )
        .limit(1)
    )
    assert opened_alert is not None

    acknowledge_vee_exception(
        session,
        vee_exception.id,
        acknowledged_by=actor.login_id,
        acknowledged_by_user_account_id=actor.id,
    )
    session.commit()
    session.refresh(initial)
    session.refresh(vee_exception)
    session.refresh(opened_alert)

    assert vee_exception.exception_status == "acknowledged"
    assert vee_exception.acknowledged_by == "vee-ack"
    assert vee_exception.acknowledged_by_user_account_id == actor.id
    assert initial.initial_status == "exception"
    assert is_initial_measurement_finalizable(initial) is False
    assert opened_alert.alert_status == "acknowledged"
    assert opened_alert.acknowledged_by == "vee-ack"


def test_resolve_vee_exception_restores_finalizable_initial_measurement_when_last_blocker_clears(
    session,
):
    initial, vee_exception = _prepare_required_field_exception(session)
    actor = create_user_account(
        session,
        login_id="vee-resolve",
        display_name="VEE Resolve",
        role_code="operator",
        password="secret-password",
    )
    session.commit()

    resolve_vee_exception(
        session,
        vee_exception.id,
        resolution_type="operator_resolution",
        resolved_by=actor.login_id,
        resolved_by_user_account_id=actor.id,
        operator_memo="Reviewed by operator.",
    )
    session.commit()
    session.refresh(initial)
    session.refresh(vee_exception)

    assert vee_exception.exception_status == "resolved"
    assert vee_exception.resolved_by == "vee-resolve"
    assert vee_exception.resolved_by_user_account_id == actor.id
    assert vee_exception.resolution_type == "operator_resolution"
    assert vee_exception.operator_memo == "Reviewed by operator."
    assert initial.initial_status == "accepted"
    assert is_initial_measurement_finalizable(initial) is True


def test_vee_exception_open_and_resolve_are_connected_to_operational_events(session):
    initial, vee_exception = _prepare_required_field_exception(session)

    opened_alert = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.event_code == "vee_exception_opened",
            OperationalEvent.entity_type == "vee_exception",
            OperationalEvent.entity_id == vee_exception.id,
        )
        .limit(1)
    )

    assert opened_alert is not None
    assert opened_alert.is_alert is True
    assert opened_alert.alert_status == "open"
    assert opened_alert.meter_identifier == "MTR-1001"

    resolve_vee_exception(
        session,
        vee_exception.id,
        resolution_type="operator_resolution",
        operator_memo="Reviewed by operator.",
    )
    session.commit()

    closed_alert = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.id == opened_alert.id,
        )
        .limit(1)
    )
    resolved_event = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.event_code == "vee_exception_resolved",
            OperationalEvent.entity_type == "vee_exception",
            OperationalEvent.entity_id == vee_exception.id,
        )
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )

    assert closed_alert is not None
    assert closed_alert.alert_status == "closed"
    assert resolved_event is not None
    assert resolved_event.is_alert is False


def test_reevaluate_vee_exception_clears_old_blocker_and_creates_new_execution(session):
    initial, vee_exception = _prepare_required_field_exception(session)
    actor = create_user_account(
        session,
        login_id="vee-reevaluate",
        display_name="VEE Reevaluate",
        role_code="operator",
        password="secret-password",
    )
    session.commit()
    initial.unit_of_measure = "kWh"
    session.flush()

    execution = reevaluate_vee_exception(
        session,
        vee_exception.id,
        reevaluated_by=actor.login_id,
        reevaluated_by_user_account_id=actor.id,
    )
    session.commit()
    session.refresh(initial)
    session.refresh(vee_exception)

    assert execution.execution_status == "passed"
    assert execution.trigger_type == "manual_re_evaluate"
    assert vee_exception.exception_status == "resolved"
    assert vee_exception.resolved_by == "vee-reevaluate"
    assert vee_exception.resolved_by_user_account_id == actor.id
    assert vee_exception.resolution_type == "re_evaluated_superseded"
    assert initial.initial_status == "accepted"
    assert is_initial_measurement_finalizable(initial) is True
    assert session.scalar(
        select(func.count())
        .select_from(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
    ) == 2
    assert session.scalar(
        select(func.count())
        .select_from(VeeException)
        .where(
            VeeException.initial_measurement_id == initial.id,
            VeeException.exception_status.in_(("open", "acknowledged")),
        )
    ) == 0
    reevaluated_event = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.event_code == "vee_re_evaluated",
            OperationalEvent.entity_type == "initial_measurement",
            OperationalEvent.entity_id == initial.id,
        )
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert reevaluated_event is not None


def test_reevaluate_vee_exception_can_reopen_same_exception_code_in_new_snapshot(session):
    initial, vee_exception = _prepare_required_field_exception(session)

    execution = reevaluate_vee_exception(
        session,
        vee_exception.id,
        reevaluated_by="operator_ui",
    )
    session.commit()
    session.refresh(initial)
    session.refresh(vee_exception)

    reopened = session.scalars(
        select(VeeException)
        .where(
            VeeException.initial_measurement_id == initial.id,
            VeeException.exception_code == "vee_required_field_missing",
        )
        .order_by(VeeException.id.asc())
    ).all()

    assert execution.execution_status == "completed_with_exception"
    assert vee_exception.exception_status == "resolved"
    assert vee_exception.resolution_type == "re_evaluated_superseded"
    assert initial.initial_status == "exception"
    assert len(reopened) == 2
    assert reopened[-1].exception_status == "open"


def test_evaluate_or_get_vee_baseline_reuses_cached_warning_execution_and_restores_acceptance(
    session,
):
    initial = _prepare_clean_initial(session)
    initial.value = Decimal("0.0000")

    first_execution, created = evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    assert created is True
    assert first_execution.execution_status == "completed_with_exception"
    assert first_execution.summary_code == "vee_completed_with_zero_value"
    assert initial.initial_status == "accepted"

    initial.initial_status = "ready"
    session.flush()

    cached_execution, created = evaluate_or_get_vee_baseline(session, initial, force=False)
    session.commit()
    session.refresh(initial)

    assert created is False
    assert cached_execution.id == first_execution.id
    assert initial.initial_status == "accepted"
    assert session.scalar(
        select(func.count())
        .select_from(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
    ) == 1


def test_evaluate_or_get_vee_baseline_reuses_cached_execution_and_restores_exception_when_blocker_active(
    session,
):
    initial, vee_exception = _prepare_required_field_exception(session)
    first_execution = session.scalar(
        select(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
        .order_by(VeeExecutionLog.id.asc())
        .limit(1)
    )
    assert first_execution is not None
    assert vee_exception.blocking_finalization is True

    initial.initial_status = "ready"
    session.flush()

    cached_execution, created = evaluate_or_get_vee_baseline(session, initial, force=False)
    session.commit()
    session.refresh(initial)

    assert created is False
    assert cached_execution.id == first_execution.id
    assert initial.initial_status == "exception"
    assert session.scalar(
        select(func.count())
        .select_from(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
    ) == 1


def test_evaluate_or_get_vee_baseline_prioritizes_required_field_summary_over_later_negative_hit(
    session,
):
    initial = _prepare_clean_initial(session)
    initial.unit_of_measure = ""
    initial.value = Decimal("-1.0000")

    execution, created = evaluate_or_get_vee_baseline(session, initial, force=True)
    session.commit()

    open_codes = session.scalars(
        select(VeeException.exception_code)
        .where(
            VeeException.initial_measurement_id == initial.id,
            VeeException.exception_status.in_(("open", "acknowledged")),
        )
        .order_by(VeeException.id.asc())
    ).all()

    assert created is True
    assert execution.summary_code == "vee_failed_required_field"
    assert execution.details["rule_hits"][:2] == [
        "vee_required_field_missing",
        "vee_negative_value_detected",
    ]
    assert initial.initial_status == "exception"
    assert open_codes == [
        "vee_required_field_missing",
        "vee_negative_value_detected",
    ]


def test_evaluate_or_get_vee_baseline_prioritizes_missing_interval_summary_over_later_high_value_hit(
    session,
):
    initial = _prepare_clean_initial(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    assert raw_row.source_system is not None
    assert raw_row.meter_identifier is not None
    assert raw_row.channel_identifier is not None
    assert raw_row.source_business_ts is not None

    initial.value = Decimal("1500.0000")
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

    execution, created = evaluate_or_get_vee_baseline(session, initial, force=True)
    session.commit()

    open_codes = session.scalars(
        select(VeeException.exception_code)
        .where(
            VeeException.initial_measurement_id == initial.id,
            VeeException.exception_status.in_(("open", "acknowledged")),
        )
        .order_by(VeeException.id.asc())
    ).all()

    assert created is True
    assert execution.summary_code == "vee_failed_missing_interval"
    assert execution.details["rule_hits"][-2:] == [
        "vee_missing_interval_detected",
        "vee_high_value_detected",
    ]
    assert initial.initial_status == "exception"
    assert open_codes == [
        "vee_missing_interval_detected",
        "vee_high_value_detected",
    ]


def test_evaluate_or_get_vee_baseline_force_reuses_existing_open_exception_for_same_code(
    session,
):
    initial, vee_exception = _prepare_required_field_exception(session)
    first_execution = session.scalar(
        select(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
        .order_by(VeeExecutionLog.id.asc())
        .limit(1)
    )
    assert first_execution is not None

    execution, created = evaluate_or_get_vee_baseline(session, initial, force=True)
    session.commit()
    session.refresh(vee_exception)

    active_required_field = session.scalars(
        select(VeeException)
        .where(
            VeeException.initial_measurement_id == initial.id,
            VeeException.exception_code == "vee_required_field_missing",
            VeeException.exception_status.in_(("open", "acknowledged")),
        )
        .order_by(VeeException.id.asc())
    ).all()

    assert created is True
    assert execution.id != first_execution.id
    assert len(active_required_field) == 1
    assert active_required_field[0].id == vee_exception.id
    assert active_required_field[0].vee_execution_log_id == execution.id
    assert session.scalar(
        select(func.count())
        .select_from(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
    ) == 2
