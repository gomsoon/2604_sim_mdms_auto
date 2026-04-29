from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import (
    FinalMeasurement,
    InitialMeasurement,
    OperationalEvent,
    UsageTransaction,
    VeeException,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.processing_replay import reevaluate_vee_exception_and_replay
from app.services.seeds import seed_demo_environment
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def _create_required_field_exception(session) -> tuple[InitialMeasurement, VeeException]:
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


def test_reevaluate_replay_creates_final_and_usage_when_issue_clears(session):
    initial, vee_exception = _create_required_field_exception(session)
    initial.unit_of_measure = "kWh"
    session.commit()

    summary = reevaluate_vee_exception_and_replay(
        session,
        vee_exception.id,
        reevaluated_by="operator_ui",
    )
    session.commit()

    final_row = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == initial.id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    usage_rows = session.scalars(
        select(UsageTransaction).order_by(UsageTransaction.usage_type.asc())
    ).all()

    assert summary.exception_cleared is True
    assert summary.exception_reopened is False
    assert summary.final_created is True
    assert summary.final_superseded is False
    assert summary.final_unchanged is False
    assert summary.daily_usage_groups_updated == 1
    assert summary.monthly_usage_groups_updated == 1
    assert final_row is not None
    assert final_row.revision_number == 1
    assert len(usage_rows) == 2
    assert {row.usage_type for row in usage_rows} == {
        "daily_consumption",
        "monthly_consumption",
    }
    assert session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "usage_recalculated_after_vee")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    ) is not None


def test_reevaluate_replay_supersedes_final_and_updates_usage(session):
    seed_demo_environment(session)
    session.commit()

    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None
    initial.value = Decimal("-1.0000")
    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
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

    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == initial.id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None

    initial.value = Decimal("42.0000")
    session.commit()

    summary = reevaluate_vee_exception_and_replay(
        session,
        vee_exception.id,
        reevaluated_by="operator_ui",
    )
    session.commit()

    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == initial.id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    daily_usage = session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.usage_type == "daily_consumption")
        .limit(1)
    )
    monthly_usage = session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.usage_type == "monthly_consumption")
        .limit(1)
    )

    assert summary.exception_cleared is True
    assert summary.final_created is False
    assert summary.final_superseded is True
    assert summary.final_unchanged is False
    assert summary.previous_final_id == old_final.id
    assert current_final is not None
    assert current_final.id != old_final.id
    assert current_final.revision_number == 2
    assert current_final.revision_reason_code == "vee_re_evaluated"
    assert summary.current_final_id == current_final.id
    assert summary.daily_usage_groups_updated == 1
    assert summary.monthly_usage_groups_updated == 1
    assert daily_usage is not None
    assert monthly_usage is not None
    assert daily_usage.usage_value == Decimal("42.0000")
    assert monthly_usage.usage_value == Decimal("42.0000")
    assert session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "final_measurement_superseded")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    ) is not None
