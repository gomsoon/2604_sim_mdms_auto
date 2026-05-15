from __future__ import annotations

from sqlalchemy import func, select

from app.models import InitialMeasurement, OperationalEvent, VeeException, VeeExecutionLog
from app.services.auth import create_user_account
from app.services.finalization import is_initial_measurement_finalizable
from app.services.seeds import seed_demo_environment
from app.services.vee import (
    acknowledge_vee_exception,
    evaluate_or_get_vee_baseline,
    reevaluate_vee_exception,
    resolve_vee_exception,
)


def _prepare_required_field_exception(session) -> tuple[InitialMeasurement, VeeException]:
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None

    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
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
