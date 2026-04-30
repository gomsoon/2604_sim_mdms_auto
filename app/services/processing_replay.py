from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FinalMeasurement, InitialMeasurement, UsageTransaction, VeeException
from app.services.finalization import create_or_get_final_measurement, is_initial_measurement_finalizable
from app.services.operational_events import record_operational_event
from app.services.usage import (
    USAGE_TYPE_DAILY,
    USAGE_TYPE_MONTHLY,
    UsageWindowScope,
    build_usage_window_scope,
    calculate_usage_transactions,
)
from app.services.vee import VeeExceptionActionError, reevaluate_vee_exception


@dataclass(frozen=True, slots=True)
class ReVeeReplaySummary:
    target_vee_exception_id: int
    initial_measurement_id: int
    vee_execution_log_id: int
    active_exception_count: int
    blocking_exception_count: int
    exception_cleared: bool
    exception_reopened: bool
    previous_final_id: int | None
    current_final_id: int | None
    final_created: bool
    final_superseded: bool
    final_unchanged: bool
    daily_usage_groups_updated: int
    daily_usage_rows_deleted: int
    monthly_usage_groups_updated: int
    monthly_usage_rows_deleted: int
    usage_recalculation_results: list["UsageRecalculationResult"]


@dataclass(frozen=True, slots=True)
class UsageRecalculationResult:
    usage_type: str
    service_point_id: int
    measuring_component_id: int
    period_start_at: str
    period_end_at: str
    action: str
    previous_usage_transaction_id: int | None
    current_usage_transaction_id: int | None
    previous_calculation_status: str | None
    current_calculation_status: str | None
    previous_usage_value: str | None
    current_usage_value: str | None
    previous_missing_interval_count: int | None
    current_missing_interval_count: int | None


def _get_current_final_measurement_for_initial(
    session: Session,
    *,
    initial_measurement_id: int,
) -> FinalMeasurement | None:
    return session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.initial_measurement_id == initial_measurement_id,
            FinalMeasurement.is_current.is_(True),
        )
        .order_by(FinalMeasurement.revision_number.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )


def _load_active_vee_exceptions(
    session: Session,
    *,
    initial_measurement_id: int,
) -> list[VeeException]:
    return session.scalars(
        select(VeeException)
        .where(
            VeeException.initial_measurement_id == initial_measurement_id,
            VeeException.exception_status.in_(("open", "acknowledged")),
        )
        .order_by(VeeException.id.asc())
    ).all()


def _count_current_finals_in_window(
    session: Session,
    *,
    window: UsageWindowScope,
) -> int:
    return session.scalar(
        select(func.count())
        .select_from(FinalMeasurement)
        .where(
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.service_point_id == window.service_point_id,
            FinalMeasurement.measuring_component_id == window.measuring_component_id,
            FinalMeasurement.measured_at >= window.period_start_at,
            FinalMeasurement.measured_at < window.period_end_at,
        )
    ) or 0


def _delete_usage_transaction_for_window(
    session: Session,
    *,
    window: UsageWindowScope,
) -> int:
    row = session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.service_point_id == window.service_point_id)
        .where(UsageTransaction.measuring_component_id == window.measuring_component_id)
        .where(UsageTransaction.usage_type == window.usage_type)
        .where(UsageTransaction.period_start_at == window.period_start_at)
        .where(UsageTransaction.period_end_at == window.period_end_at)
        .limit(1)
    )
    if row is None:
        return 0
    session.delete(row)
    session.flush()
    return 1


def _get_usage_transaction_for_window(
    session: Session,
    *,
    window: UsageWindowScope,
) -> UsageTransaction | None:
    return session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.service_point_id == window.service_point_id)
        .where(UsageTransaction.measuring_component_id == window.measuring_component_id)
        .where(UsageTransaction.usage_type == window.usage_type)
        .where(UsageTransaction.period_start_at == window.period_start_at)
        .where(UsageTransaction.period_end_at == window.period_end_at)
        .limit(1)
    )


def _build_usage_recalculation_result(
    *,
    window: UsageWindowScope,
    previous_snapshot: dict[str, object] | None,
    current_snapshot: dict[str, object] | None,
    action: str,
) -> UsageRecalculationResult:
    return UsageRecalculationResult(
        usage_type=window.usage_type,
        service_point_id=window.service_point_id,
        measuring_component_id=window.measuring_component_id,
        period_start_at=window.period_start_at.isoformat(),
        period_end_at=window.period_end_at.isoformat(),
        action=action,
        previous_usage_transaction_id=(
            int(previous_snapshot["id"]) if previous_snapshot is not None else None
        ),
        current_usage_transaction_id=(
            int(current_snapshot["id"]) if current_snapshot is not None else None
        ),
        previous_calculation_status=(
            str(previous_snapshot["calculation_status"])
            if previous_snapshot is not None
            else None
        ),
        current_calculation_status=(
            str(current_snapshot["calculation_status"])
            if current_snapshot is not None
            else None
        ),
        previous_usage_value=(
            str(previous_snapshot["usage_value"]) if previous_snapshot is not None else None
        ),
        current_usage_value=(
            str(current_snapshot["usage_value"]) if current_snapshot is not None else None
        ),
        previous_missing_interval_count=(
            int(previous_snapshot["missing_interval_count"])
            if previous_snapshot is not None
            else None
        ),
        current_missing_interval_count=(
            int(current_snapshot["missing_interval_count"])
            if current_snapshot is not None
            else None
        ),
    )


def _snapshot_usage_transaction(row: UsageTransaction | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "calculation_status": row.calculation_status,
        "usage_value": str(row.usage_value),
        "missing_interval_count": row.missing_interval_count,
        "quality_summary": row.quality_summary,
    }


def _recalculate_impacted_usage_windows(
    session: Session,
    *,
    previous_final: FinalMeasurement | None,
    current_final: FinalMeasurement | None,
    trigger_type: str,
    details_context: dict[str, object] | None = None,
) -> tuple[int, int, int, int, list[UsageRecalculationResult]]:
    impacted_daily: set[UsageWindowScope] = set()
    impacted_monthly: set[UsageWindowScope] = set()

    for final_row in (previous_final, current_final):
        if final_row is None:
            continue
        impacted_daily.add(
            build_usage_window_scope(
                final_row,
                usage_type=USAGE_TYPE_DAILY,
            )
        )
        impacted_monthly.add(
            build_usage_window_scope(
                final_row,
                usage_type=USAGE_TYPE_MONTHLY,
            )
        )

    all_results: list[UsageRecalculationResult] = []

    def _apply(windows: set[UsageWindowScope]) -> tuple[int, int]:
        groups_updated = 0
        rows_deleted = 0
        for window in sorted(
            windows,
            key=lambda row: (
                row.service_point_id,
                row.measuring_component_id,
                row.period_start_at,
                row.period_end_at,
                row.usage_type,
            ),
        ):
            previous_row = _get_usage_transaction_for_window(session, window=window)
            previous_snapshot = _snapshot_usage_transaction(previous_row)
            current_final_count = _count_current_finals_in_window(session, window=window)
            if current_final_count == 0:
                deleted = _delete_usage_transaction_for_window(session, window=window)
                rows_deleted += deleted
                all_results.append(
                    _build_usage_recalculation_result(
                        window=window,
                        previous_snapshot=previous_snapshot,
                        current_snapshot=None,
                        action="deleted" if deleted else "unchanged",
                    )
                )
                continue

            calculate_usage_transactions(
                session,
                usage_type=window.usage_type,
                service_point_id=window.service_point_id,
                measuring_component_id=window.measuring_component_id,
                date_from=window.period_start_at,
                date_to=window.period_end_at - timedelta(microseconds=1),
                trigger_type=trigger_type,
                details_context=details_context,
            )
            current_row = _get_usage_transaction_for_window(session, window=window)
            current_snapshot = _snapshot_usage_transaction(current_row)
            action = "unchanged"
            if previous_snapshot is None and current_snapshot is not None:
                action = "updated"
            elif previous_snapshot is not None and current_snapshot is not None and (
                previous_snapshot["calculation_status"] != current_snapshot["calculation_status"]
                or previous_snapshot["usage_value"] != current_snapshot["usage_value"]
                or previous_snapshot["missing_interval_count"]
                != current_snapshot["missing_interval_count"]
                or previous_snapshot["quality_summary"] != current_snapshot["quality_summary"]
            ):
                action = "updated"
            if action == "updated":
                groups_updated += 1
            all_results.append(
                _build_usage_recalculation_result(
                    window=window,
                    previous_snapshot=previous_snapshot,
                    current_snapshot=current_snapshot,
                    action=action,
                )
            )
        return groups_updated, rows_deleted

    daily_groups_updated, daily_rows_deleted = _apply(impacted_daily)
    monthly_groups_updated, monthly_rows_deleted = _apply(impacted_monthly)
    return (
        daily_groups_updated,
        daily_rows_deleted,
        monthly_groups_updated,
        monthly_rows_deleted,
        all_results,
    )


def reevaluate_vee_exception_and_replay(
    session: Session,
    vee_exception_id: int,
    *,
    reevaluated_by: str,
    operator_memo: str | None = None,
) -> ReVeeReplaySummary:
    target_exception = session.get(VeeException, vee_exception_id)
    if target_exception is None:
        raise VeeExceptionActionError(
            "not_found",
            "The selected VEE exception does not exist.",
        )

    initial_measurement_id = target_exception.initial_measurement_id
    previous_final = _get_current_final_measurement_for_initial(
        session,
        initial_measurement_id=initial_measurement_id,
    )
    previous_final_id = previous_final.id if previous_final is not None else None

    execution = reevaluate_vee_exception(
        session,
        vee_exception_id,
        reevaluated_by=reevaluated_by,
        operator_memo=operator_memo,
    )
    initial_row = session.get(InitialMeasurement, initial_measurement_id)
    if initial_row is None:
        raise VeeExceptionActionError(
            "not_found",
            "The selected VEE exception does not exist.",
        )

    active_exceptions = _load_active_vee_exceptions(
        session,
        initial_measurement_id=initial_measurement_id,
    )
    blocking_exception_count = sum(1 for row in active_exceptions if row.blocking_finalization)
    current_final: FinalMeasurement | None = previous_final
    final_created = False
    final_superseded = False
    final_unchanged = previous_final is not None
    daily_usage_groups_updated = 0
    daily_usage_rows_deleted = 0
    monthly_usage_groups_updated = 0
    monthly_usage_rows_deleted = 0
    usage_recalculation_results: list[UsageRecalculationResult] = []

    if not active_exceptions and is_initial_measurement_finalizable(initial_row):
        current_final, final_created = create_or_get_final_measurement(
            session,
            initial_row,
            revision_reason_code="vee_re_evaluated",
        )
        final_superseded = final_created and previous_final_id is not None
        final_unchanged = not final_created

        if final_superseded:
            record_operational_event(
                session,
                "final_measurement_superseded",
                entity_type="final_measurement",
                entity_id=current_final.id,
                details={
                    "initial_measurement_id": initial_measurement_id,
                    "previous_final_measurement_id": previous_final_id,
                    "current_final_measurement_id": current_final.id,
                    "vee_execution_log_id": execution.id,
                },
                initial_measurement_id=initial_measurement_id,
                previous_final_measurement_id=previous_final_id,
                current_final_measurement_id=current_final.id,
            )

        if final_created:
            (
                daily_usage_groups_updated,
                daily_usage_rows_deleted,
                monthly_usage_groups_updated,
                monthly_usage_rows_deleted,
                usage_recalculation_results,
            ) = _recalculate_impacted_usage_windows(
                session,
                previous_final=previous_final,
                current_final=current_final,
                trigger_type="vee_re_evaluate",
                details_context={
                    "trigger_source": "re_vee",
                    "initial_measurement_id": initial_measurement_id,
                    "vee_execution_log_id": execution.id,
                    "previous_final_measurement_id": previous_final_id,
                    "current_final_measurement_id": current_final.id,
                },
            )
            record_operational_event(
                session,
                "usage_recalculated_after_vee",
                entity_type="initial_measurement",
                entity_id=initial_measurement_id,
                details={
                    "initial_measurement_id": initial_measurement_id,
                    "vee_execution_log_id": execution.id,
                    "daily_usage_groups_updated": daily_usage_groups_updated,
                    "daily_usage_rows_deleted": daily_usage_rows_deleted,
                    "monthly_usage_groups_updated": monthly_usage_groups_updated,
                    "monthly_usage_rows_deleted": monthly_usage_rows_deleted,
                    "usage_recalculation_results": [
                        asdict(row) for row in usage_recalculation_results
                    ],
                },
                initial_measurement_id=initial_measurement_id,
                daily_usage_groups_updated=daily_usage_groups_updated,
                daily_usage_rows_deleted=daily_usage_rows_deleted,
                monthly_usage_groups_updated=monthly_usage_groups_updated,
                monthly_usage_rows_deleted=monthly_usage_rows_deleted,
            )

    session.flush()
    return ReVeeReplaySummary(
        target_vee_exception_id=vee_exception_id,
        initial_measurement_id=initial_measurement_id,
        vee_execution_log_id=execution.id,
        active_exception_count=len(active_exceptions),
        blocking_exception_count=blocking_exception_count,
        exception_cleared=len(active_exceptions) == 0,
        exception_reopened=len(active_exceptions) > 0,
        previous_final_id=previous_final_id,
        current_final_id=current_final.id if current_final is not None else None,
        final_created=final_created and previous_final_id is None,
        final_superseded=final_superseded,
        final_unchanged=final_unchanged,
        daily_usage_groups_updated=daily_usage_groups_updated,
        daily_usage_rows_deleted=daily_usage_rows_deleted,
        monthly_usage_groups_updated=monthly_usage_groups_updated,
        monthly_usage_rows_deleted=monthly_usage_rows_deleted,
        usage_recalculation_results=usage_recalculation_results,
    )
