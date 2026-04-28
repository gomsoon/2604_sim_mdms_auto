from __future__ import annotations

from sqlalchemy import select

from app.models import InitialMeasurement, VeeException
from app.services.finalization import is_initial_measurement_finalizable
from app.services.seeds import seed_demo_environment
from app.services.vee import (
    acknowledge_vee_exception,
    evaluate_or_get_vee_baseline,
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

    acknowledge_vee_exception(session, vee_exception.id, acknowledged_by="operator_ui")
    session.commit()
    session.refresh(initial)
    session.refresh(vee_exception)

    assert vee_exception.exception_status == "acknowledged"
    assert vee_exception.acknowledged_by == "operator_ui"
    assert initial.initial_status == "exception"
    assert is_initial_measurement_finalizable(initial) is False


def test_resolve_vee_exception_restores_finalizable_initial_measurement_when_last_blocker_clears(
    session,
):
    initial, vee_exception = _prepare_required_field_exception(session)

    resolve_vee_exception(
        session,
        vee_exception.id,
        resolution_type="operator_resolution",
        operator_memo="Reviewed by operator.",
    )
    session.commit()
    session.refresh(initial)
    session.refresh(vee_exception)

    assert vee_exception.exception_status == "resolved"
    assert vee_exception.resolution_type == "operator_resolution"
    assert vee_exception.operator_memo == "Reviewed by operator."
    assert initial.initial_status == "accepted"
    assert is_initial_measurement_finalizable(initial) is True
