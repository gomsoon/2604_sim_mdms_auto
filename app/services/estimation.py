from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BillCharge,
    EstimationAudit,
    FinalMeasurement,
    InitialMeasurement,
    VeeException,
)
from app.services.bill_charges import (
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
    BillChargeCalculationSummary,
    calculate_bill_charges,
)
from app.services.bill_determinants import (
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
    BillDeterminantCalculationSummary,
    calculate_bill_determinants,
)
from app.services.finalization import create_or_get_final_measurement, is_initial_measurement_finalizable
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from app.services.processing_replay import (
    UsageRecalculationResult,
    recalculate_impacted_usage_windows,
)
from app.services.vee import (
    evaluate_or_get_vee_baseline,
    resolve_vee_exception,
)


ESTIMATION_STRATEGY_LINEAR_INTERPOLATION = "linear_interpolation"
ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED = "previous_value_based"
SUPPORTED_ESTIMATION_STRATEGIES = {
    ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
    ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
}

ESTIMATION_ALLOWED_EXCEPTION_CODES = {
    "vee_negative_value_detected",
    "vee_high_value_detected",
}

ESTIMATION_QUALITY_CODE = "ESTIMATED"
ESTIMATION_REVISION_REASON_CODE = "estimation_applied"
_VALUE_SCALE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class EstimationActionError(Exception):
    error_code: str
    fallback_message: str


@dataclass(frozen=True, slots=True)
class EstimationComputationResult:
    estimation_status: str
    result_code: str
    estimated_value: Decimal | None
    source_previous_final: FinalMeasurement | None
    source_next_final: FinalMeasurement | None
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class EstimationSummary:
    estimation_audit_id: int
    pipeline_run_id: int
    target_vee_exception_id: int
    initial_measurement_id: int
    strategy_code: str
    estimation_status: str
    result_code: str
    estimated_value: Decimal | None
    vee_execution_log_id: int | None
    active_exception_count: int
    blocking_exception_count: int
    previous_final_id: int | None
    current_final_id: int | None
    final_created: bool
    final_superseded: bool
    daily_usage_groups_updated: int
    daily_usage_rows_deleted: int
    monthly_usage_groups_updated: int
    monthly_usage_rows_deleted: int
    usage_recalculation_results: list[UsageRecalculationResult]
    bill_determinant_groups: int
    bill_determinant_created: int
    bill_determinant_superseded: int
    bill_determinant_reused: int
    bill_charge_groups: int
    bill_charge_created: int
    bill_charge_superseded: int
    bill_charge_reused: int


def _get_active_vee_exception(session: Session, vee_exception_id: int) -> VeeException:
    vee_exception = session.get(VeeException, vee_exception_id)
    if vee_exception is None:
        raise EstimationActionError("not_found", "The selected VEE exception does not exist.")
    if vee_exception.exception_status not in {"open", "acknowledged"}:
        raise EstimationActionError(
            "exception_not_active",
            "The selected VEE exception is not active.",
        )
    return vee_exception


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


def _find_supporting_previous_final(
    session: Session,
    *,
    initial_row: InitialMeasurement,
) -> FinalMeasurement | None:
    return session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.service_point_id == initial_row.service_point_id,
            FinalMeasurement.measuring_component_id == initial_row.measuring_component_id,
            FinalMeasurement.device_id == initial_row.device_id,
            FinalMeasurement.measured_at < initial_row.measured_at,
        )
        .order_by(FinalMeasurement.measured_at.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )


def _find_supporting_next_final(
    session: Session,
    *,
    initial_row: InitialMeasurement,
) -> FinalMeasurement | None:
    return session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.service_point_id == initial_row.service_point_id,
            FinalMeasurement.measuring_component_id == initial_row.measuring_component_id,
            FinalMeasurement.device_id == initial_row.device_id,
            FinalMeasurement.measured_at > initial_row.measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(1)
    )


def _snapshot_initial_measurement(initial_row: InitialMeasurement) -> dict[str, object]:
    return {
        "initial_measurement_id": initial_row.id,
        "measured_at": initial_row.measured_at.isoformat(),
        "value": str(initial_row.value),
        "quality_code": initial_row.quality_code,
        "status_code": initial_row.status_code,
        "unit_of_measure": initial_row.unit_of_measure,
        "initial_status": initial_row.initial_status,
    }


def _snapshot_final_measurement(final_row: FinalMeasurement | None) -> dict[str, object] | None:
    if final_row is None:
        return None
    return {
        "final_measurement_id": final_row.id,
        "measured_at": final_row.measured_at.isoformat(),
        "value": str(final_row.value),
        "quality_code": final_row.quality_code,
        "status_code": final_row.status_code,
        "unit_of_measure": final_row.unit_of_measure,
        "revision_number": final_row.revision_number,
        "is_current": final_row.is_current,
    }


def _quantize_value(value: Decimal) -> Decimal:
    return value.quantize(_VALUE_SCALE, rounding=ROUND_HALF_UP)


def _build_estimation_result(
    session: Session,
    *,
    initial_row: InitialMeasurement,
    target_exception: VeeException,
    strategy_code: str,
) -> EstimationComputationResult:
    previous_final = _find_supporting_previous_final(session, initial_row=initial_row)
    next_final = _find_supporting_next_final(session, initial_row=initial_row)

    if target_exception.exception_code not in ESTIMATION_ALLOWED_EXCEPTION_CODES:
        return EstimationComputationResult(
            estimation_status="blocked",
            result_code="blocked_unsupported_exception_code",
            estimated_value=None,
            source_previous_final=previous_final,
            source_next_final=next_final,
            details={
                "blocked_reason": "unsupported_exception_code",
                "exception_code": target_exception.exception_code,
            },
        )

    unit_of_measure = (initial_row.unit_of_measure or "").strip()
    if not unit_of_measure:
        return EstimationComputationResult(
            estimation_status="blocked",
            result_code="blocked_invalid_target_state",
            estimated_value=None,
            source_previous_final=previous_final,
            source_next_final=next_final,
            details={"blocked_reason": "missing_unit_of_measure"},
        )

    if strategy_code == ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED:
        if previous_final is None:
            return EstimationComputationResult(
                estimation_status="blocked",
                result_code="blocked_missing_previous_final",
                estimated_value=None,
                source_previous_final=None,
                source_next_final=next_final,
                details={"blocked_reason": "missing_previous_final"},
            )
        if previous_final.unit_of_measure != unit_of_measure:
            return EstimationComputationResult(
                estimation_status="blocked",
                result_code="blocked_uom_mismatch",
                estimated_value=None,
                source_previous_final=previous_final,
                source_next_final=next_final,
                details={
                    "blocked_reason": "uom_mismatch",
                    "target_unit_of_measure": unit_of_measure,
                    "previous_unit_of_measure": previous_final.unit_of_measure,
                },
            )
        return EstimationComputationResult(
            estimation_status="applied",
            result_code="applied_previous_value_based",
            estimated_value=_quantize_value(previous_final.value),
            source_previous_final=previous_final,
            source_next_final=next_final,
            details={},
        )

    if strategy_code == ESTIMATION_STRATEGY_LINEAR_INTERPOLATION:
        if previous_final is None:
            return EstimationComputationResult(
                estimation_status="blocked",
                result_code="blocked_missing_previous_final",
                estimated_value=None,
                source_previous_final=None,
                source_next_final=next_final,
                details={"blocked_reason": "missing_previous_final"},
            )
        if next_final is None:
            return EstimationComputationResult(
                estimation_status="blocked",
                result_code="blocked_missing_next_final",
                estimated_value=None,
                source_previous_final=previous_final,
                source_next_final=None,
                details={"blocked_reason": "missing_next_final"},
            )
        if previous_final.unit_of_measure != unit_of_measure or next_final.unit_of_measure != unit_of_measure:
            return EstimationComputationResult(
                estimation_status="blocked",
                result_code="blocked_uom_mismatch",
                estimated_value=None,
                source_previous_final=previous_final,
                source_next_final=next_final,
                details={
                    "blocked_reason": "uom_mismatch",
                    "target_unit_of_measure": unit_of_measure,
                    "previous_unit_of_measure": previous_final.unit_of_measure,
                    "next_unit_of_measure": next_final.unit_of_measure,
                },
            )
        total_seconds = (next_final.measured_at - previous_final.measured_at).total_seconds()
        if total_seconds <= 0:
            return EstimationComputationResult(
                estimation_status="blocked",
                result_code="blocked_context_mismatch",
                estimated_value=None,
                source_previous_final=previous_final,
                source_next_final=next_final,
                details={"blocked_reason": "invalid_neighbor_order"},
            )
        offset_seconds = (initial_row.measured_at - previous_final.measured_at).total_seconds()
        ratio = Decimal(str(offset_seconds / total_seconds))
        estimated_value = previous_final.value + (next_final.value - previous_final.value) * ratio
        return EstimationComputationResult(
            estimation_status="applied",
            result_code="applied_linear_interpolation",
            estimated_value=_quantize_value(estimated_value),
            source_previous_final=previous_final,
            source_next_final=next_final,
            details={
                "interpolation_ratio": str(ratio),
            },
        )

    raise EstimationActionError(
        "unsupported_strategy",
        "The selected estimation strategy is not supported.",
    )


def _find_current_flat_charge_rate(
    session: Session,
    *,
    service_point_id: int,
    measuring_component_id: int,
    billing_period_start_at: datetime,
    billing_period_end_at: datetime,
) -> Decimal | None:
    current_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.charge_type == BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE)
        .where(BillCharge.billing_period_start_at == billing_period_start_at)
        .where(BillCharge.billing_period_end_at == billing_period_end_at)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    return None if current_charge is None else current_charge.unit_rate_value


def _recalculate_downstream_artifacts(
    session: Session,
    *,
    previous_final: FinalMeasurement | None,
    current_final: FinalMeasurement,
    estimation_audit_id: int,
    initial_measurement_id: int,
    vee_exception_id: int,
) -> tuple[
    int,
    int,
    int,
    int,
    list[UsageRecalculationResult],
    BillDeterminantCalculationSummary | None,
    BillChargeCalculationSummary | None,
]:
    (
        daily_usage_groups_updated,
        daily_usage_rows_deleted,
        monthly_usage_groups_updated,
        monthly_usage_rows_deleted,
        usage_recalculation_results,
    ) = recalculate_impacted_usage_windows(
        session,
        previous_final=previous_final,
        current_final=current_final,
        trigger_type="estimation_apply",
        details_context={
            "trigger_source": "estimation",
            "estimation_audit_id": estimation_audit_id,
            "initial_measurement_id": initial_measurement_id,
            "vee_exception_id": vee_exception_id,
            "previous_final_measurement_id": previous_final.id if previous_final is not None else None,
            "current_final_measurement_id": current_final.id,
        },
    )

    monthly_windows: set[tuple[int, int, datetime, datetime]] = set()
    for row in usage_recalculation_results:
        if row.usage_type != "monthly_consumption":
            continue
        if row.current_usage_transaction_id is None and row.previous_usage_transaction_id is None:
            continue
        monthly_windows.add(
            (
                row.service_point_id,
                row.measuring_component_id,
                datetime.fromisoformat(row.period_start_at),
                datetime.fromisoformat(row.period_end_at),
            )
        )

    determinant_summary: BillDeterminantCalculationSummary | None = None
    charge_summary: BillChargeCalculationSummary | None = None
    for service_point_id, measuring_component_id, period_start_at, period_end_at in sorted(
        monthly_windows,
        key=lambda row: (row[0], row[1], row[2], row[3]),
    ):
        existing_rate = _find_current_flat_charge_rate(
            session,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            billing_period_start_at=period_start_at,
            billing_period_end_at=period_end_at,
        )
        determinant_result = calculate_bill_determinants(
            session,
            determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            date_from=period_start_at,
            date_to=period_end_at,
            trigger_type="estimation_apply",
            revision_reason_code=ESTIMATION_REVISION_REASON_CODE,
            details_context={
                "trigger_source": "estimation",
                "estimation_audit_id": estimation_audit_id,
                "initial_measurement_id": initial_measurement_id,
                "vee_exception_id": vee_exception_id,
                "current_final_measurement_id": current_final.id,
            },
        )
        charge_result = calculate_bill_charges(
            session,
            charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
            unit_rate_value=existing_rate,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            date_from=period_start_at,
            date_to=period_end_at,
            trigger_type="estimation_apply",
            revision_reason_code=ESTIMATION_REVISION_REASON_CODE,
            details_context={
                "trigger_source": "estimation",
                "estimation_audit_id": estimation_audit_id,
                "initial_measurement_id": initial_measurement_id,
                "vee_exception_id": vee_exception_id,
                "current_final_measurement_id": current_final.id,
                "bill_determinant_groups": determinant_result.groups,
            },
        )
        if determinant_summary is None:
            determinant_summary = determinant_result
        else:
            determinant_summary = BillDeterminantCalculationSummary(
                determinant_type=determinant_summary.determinant_type,
                groups=determinant_summary.groups + determinant_result.groups,
                created=determinant_summary.created + determinant_result.created,
                superseded=determinant_summary.superseded + determinant_result.superseded,
                reused=determinant_summary.reused + determinant_result.reused,
                complete=determinant_summary.complete + determinant_result.complete,
                partial=determinant_summary.partial + determinant_result.partial,
                blocked=determinant_summary.blocked + determinant_result.blocked,
            )
        if charge_summary is None:
            charge_summary = charge_result
        else:
            charge_summary = BillChargeCalculationSummary(
                charge_type=charge_summary.charge_type,
                groups=charge_summary.groups + charge_result.groups,
                created=charge_summary.created + charge_result.created,
                superseded=charge_summary.superseded + charge_result.superseded,
                reused=charge_summary.reused + charge_result.reused,
                complete=charge_summary.complete + charge_result.complete,
                partial=charge_summary.partial + charge_result.partial,
                blocked=charge_summary.blocked + charge_result.blocked,
            )

    return (
        daily_usage_groups_updated,
        daily_usage_rows_deleted,
        monthly_usage_groups_updated,
        monthly_usage_rows_deleted,
        usage_recalculation_results,
        determinant_summary,
        charge_summary,
    )


def apply_estimation_from_vee_exception(
    session: Session,
    vee_exception_id: int,
    *,
    strategy_code: str,
    estimated_by: str,
    operator_memo: str | None = None,
) -> EstimationSummary:
    if strategy_code not in SUPPORTED_ESTIMATION_STRATEGIES:
        raise EstimationActionError(
            "unsupported_strategy",
            "The selected estimation strategy is not supported.",
        )

    target_exception = _get_active_vee_exception(session, vee_exception_id)
    initial_row = target_exception.initial_measurement
    previous_current_final = _get_current_final_measurement_for_initial(
        session,
        initial_measurement_id=initial_row.id,
    )
    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="estimation",
        trigger_type="manual",
        details={
            "vee_exception_id": vee_exception_id,
            "initial_measurement_id": initial_row.id,
            "strategy_code": strategy_code,
            "estimated_by": estimated_by,
            "operator_memo": operator_memo,
        },
    )

    try:
        computation_result = _build_estimation_result(
            session,
            initial_row=initial_row,
            target_exception=target_exception,
            strategy_code=strategy_code,
        )
        audit_row = EstimationAudit(
            pipeline_run_id=pipeline_run.id,
            service_point_id=initial_row.service_point_id,
            measuring_component_id=initial_row.measuring_component_id,
            device_id=initial_row.device_id,
            target_initial_measurement_id=initial_row.id,
            target_measured_at=initial_row.measured_at,
            strategy_code=strategy_code,
            estimation_status=computation_result.estimation_status,
            estimated_value=computation_result.estimated_value,
            unit_of_measure=initial_row.unit_of_measure or None,
            source_previous_final_measurement_id=(
                computation_result.source_previous_final.id
                if computation_result.source_previous_final is not None
                else None
            ),
            source_next_final_measurement_id=(
                computation_result.source_next_final.id
                if computation_result.source_next_final is not None
                else None
            ),
            superseded_final_measurement_id=None,
            result_final_measurement_id=None,
            operator_memo=operator_memo,
            details={
                "target_vee_exception_snapshot": {
                    "vee_exception_id": target_exception.id,
                    "exception_code": target_exception.exception_code,
                    "severity": target_exception.severity,
                    "blocking_finalization": target_exception.blocking_finalization,
                },
                "original_initial_measurement_snapshot": _snapshot_initial_measurement(initial_row),
                "source_previous_final_snapshot": _snapshot_final_measurement(
                    computation_result.source_previous_final
                ),
                "source_next_final_snapshot": _snapshot_final_measurement(
                    computation_result.source_next_final
                ),
                "estimation_result": computation_result.details,
            },
        )
        session.add(audit_row)
        session.flush()

        if computation_result.estimation_status == "blocked":
            details = {
                **pipeline_run.details,
                "estimation_audit_id": audit_row.id,
                "result_code": computation_result.result_code,
            }
            complete_pipeline_run(
                pipeline_run,
                result_code="estimation_blocked",
                details=details,
            )
            return EstimationSummary(
                estimation_audit_id=audit_row.id,
                pipeline_run_id=pipeline_run.id,
                target_vee_exception_id=target_exception.id,
                initial_measurement_id=initial_row.id,
                strategy_code=strategy_code,
                estimation_status="blocked",
                result_code=computation_result.result_code,
                estimated_value=None,
                vee_execution_log_id=None,
                active_exception_count=1,
                blocking_exception_count=1 if target_exception.blocking_finalization else 0,
                previous_final_id=previous_current_final.id if previous_current_final is not None else None,
                current_final_id=previous_current_final.id if previous_current_final is not None else None,
                final_created=False,
                final_superseded=False,
                daily_usage_groups_updated=0,
                daily_usage_rows_deleted=0,
                monthly_usage_groups_updated=0,
                monthly_usage_rows_deleted=0,
                usage_recalculation_results=[],
                bill_determinant_groups=0,
                bill_determinant_created=0,
                bill_determinant_superseded=0,
                bill_determinant_reused=0,
                bill_charge_groups=0,
                bill_charge_created=0,
                bill_charge_superseded=0,
                bill_charge_reused=0,
            )

        assert computation_result.estimated_value is not None
        initial_row.value = computation_result.estimated_value
        initial_row.quality_code = ESTIMATION_QUALITY_CODE
        updated_details = dict(initial_row.details or {})
        updated_details["estimation"] = {
            "estimation_audit_id": audit_row.id,
            "strategy_code": strategy_code,
            "estimated_at": datetime.now(timezone.utc).isoformat(),
            "estimated_by": estimated_by,
        }
        initial_row.details = updated_details

        resolve_vee_exception(
            session,
            target_exception.id,
            resolution_type="estimated",
            operator_memo=operator_memo,
        )
        execution, _ = evaluate_or_get_vee_baseline(
            session,
            initial_row,
            pipeline_run=pipeline_run,
            trigger_type="estimation_apply",
            force=True,
        )
        active_exceptions = _load_active_vee_exceptions(
            session,
            initial_measurement_id=initial_row.id,
        )
        blocking_exception_count = sum(1 for row in active_exceptions if row.blocking_finalization)

        current_final = previous_current_final
        final_created = False
        final_superseded = False
        daily_usage_groups_updated = 0
        daily_usage_rows_deleted = 0
        monthly_usage_groups_updated = 0
        monthly_usage_rows_deleted = 0
        usage_recalculation_results: list[UsageRecalculationResult] = []
        determinant_summary: BillDeterminantCalculationSummary | None = None
        charge_summary: BillChargeCalculationSummary | None = None

        if blocking_exception_count == 0 and is_initial_measurement_finalizable(initial_row):
            current_final, final_created = create_or_get_final_measurement(
                session,
                initial_row,
                revision_reason_code=ESTIMATION_REVISION_REASON_CODE,
            )
            final_superseded = (
                final_created
                and previous_current_final is not None
                and current_final.id != previous_current_final.id
            )
            if final_created:
                (
                    daily_usage_groups_updated,
                    daily_usage_rows_deleted,
                    monthly_usage_groups_updated,
                    monthly_usage_rows_deleted,
                    usage_recalculation_results,
                    determinant_summary,
                    charge_summary,
                ) = _recalculate_downstream_artifacts(
                    session,
                    previous_final=previous_current_final,
                    current_final=current_final,
                    estimation_audit_id=audit_row.id,
                    initial_measurement_id=initial_row.id,
                    vee_exception_id=target_exception.id,
                )

        audit_row.superseded_final_measurement_id = (
            previous_current_final.id if final_superseded and previous_current_final is not None else None
        )
        audit_row.result_final_measurement_id = current_final.id if final_created and current_final is not None else None
        audit_row.details = {
            **audit_row.details,
            "applied_initial_measurement_snapshot": _snapshot_initial_measurement(initial_row),
            "result_final_measurement_snapshot": _snapshot_final_measurement(
                current_final if final_created else None
            ),
            "vee_execution_log_id": execution.id,
            "active_exception_count": len(active_exceptions),
            "blocking_exception_count": blocking_exception_count,
            "downstream_recalculation_summary": {
                "daily_usage_groups_updated": daily_usage_groups_updated,
                "daily_usage_rows_deleted": daily_usage_rows_deleted,
                "monthly_usage_groups_updated": monthly_usage_groups_updated,
                "monthly_usage_rows_deleted": monthly_usage_rows_deleted,
                "usage_recalculation_results": [
                    asdict(row) for row in usage_recalculation_results
                ],
                "bill_determinant": (
                    asdict(determinant_summary) if determinant_summary is not None else None
                ),
                "bill_charge": asdict(charge_summary) if charge_summary is not None else None,
            },
        }
        session.flush()

        result_code = "estimation_applied"
        if blocking_exception_count > 0:
            result_code = "estimation_applied_with_open_exceptions"
        elif not final_created:
            result_code = "estimation_applied_without_final_change"

        complete_pipeline_run(
            pipeline_run,
            result_code=result_code,
            details={
                **pipeline_run.details,
                "estimation_audit_id": audit_row.id,
                "vee_execution_log_id": execution.id,
                "active_exception_count": len(active_exceptions),
                "blocking_exception_count": blocking_exception_count,
                "final_created": final_created,
                "final_superseded": final_superseded,
            },
        )
        return EstimationSummary(
            estimation_audit_id=audit_row.id,
            pipeline_run_id=pipeline_run.id,
            target_vee_exception_id=target_exception.id,
            initial_measurement_id=initial_row.id,
            strategy_code=strategy_code,
            estimation_status="applied",
            result_code=result_code,
            estimated_value=computation_result.estimated_value,
            vee_execution_log_id=execution.id,
            active_exception_count=len(active_exceptions),
            blocking_exception_count=blocking_exception_count,
            previous_final_id=previous_current_final.id if previous_current_final is not None else None,
            current_final_id=current_final.id if current_final is not None else None,
            final_created=final_created and previous_current_final is None,
            final_superseded=final_superseded,
            daily_usage_groups_updated=daily_usage_groups_updated,
            daily_usage_rows_deleted=daily_usage_rows_deleted,
            monthly_usage_groups_updated=monthly_usage_groups_updated,
            monthly_usage_rows_deleted=monthly_usage_rows_deleted,
            usage_recalculation_results=usage_recalculation_results,
            bill_determinant_groups=0 if determinant_summary is None else determinant_summary.groups,
            bill_determinant_created=0 if determinant_summary is None else determinant_summary.created,
            bill_determinant_superseded=0
            if determinant_summary is None
            else determinant_summary.superseded,
            bill_determinant_reused=0 if determinant_summary is None else determinant_summary.reused,
            bill_charge_groups=0 if charge_summary is None else charge_summary.groups,
            bill_charge_created=0 if charge_summary is None else charge_summary.created,
            bill_charge_superseded=0 if charge_summary is None else charge_summary.superseded,
            bill_charge_reused=0 if charge_summary is None else charge_summary.reused,
        )
    except Exception:
        fail_pipeline_run(
            pipeline_run,
            result_code="estimation_failed_exception",
            details=pipeline_run.details,
        )
        raise
