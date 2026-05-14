from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalMeasurement,
    EstimationAudit,
    FinalMeasurement,
    HesReadRaw,
    IngestBatch,
    InitialMeasurement,
    RawIntervalWindowState,
    VeeException,
)
from app.services.correction_policy import (
    CORRECTION_POLICY_BLOCKED,
    CorrectionPolicyDecision,
    build_correction_policy_decision,
)
from app.services.bill_charges import BillChargeCalculationSummary
from app.services.bill_determinants import (
    BillDeterminantCalculationSummary,
)
from app.services.downstream_recalculation import recalculate_downstream_artifacts
from app.services.finalization import create_or_get_final_measurement, is_initial_measurement_finalizable
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from app.services.processing_replay import UsageRecalculationResult
from app.services.vee import (
    evaluate_or_get_vee_baseline,
    reevaluate_initial_measurement,
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
ESTIMATION_MODE_SUBSTITUTION = "substitution"
ESTIMATION_MODE_SYNTHETIC_MISSING_INTERVAL = "synthetic_missing_interval"
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
    return _find_supporting_previous_final_for_context(
        session,
        service_point_id=initial_row.service_point_id,
        measuring_component_id=initial_row.measuring_component_id,
        device_id=initial_row.device_id,
        measured_at=initial_row.measured_at,
    )


def _find_supporting_next_final(
    session: Session,
    *,
    initial_row: InitialMeasurement,
) -> FinalMeasurement | None:
    return _find_supporting_next_final_for_context(
        session,
        service_point_id=initial_row.service_point_id,
        measuring_component_id=initial_row.measuring_component_id,
        device_id=initial_row.device_id,
        measured_at=initial_row.measured_at,
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


def _snapshot_raw_interval_window_state(
    window_state: RawIntervalWindowState | None,
) -> dict[str, object] | None:
    if window_state is None:
        return None
    return {
        "raw_interval_window_state_id": window_state.id,
        "window_start_at": window_state.window_start_at.isoformat(),
        "window_size_minutes": window_state.window_size_minutes,
        "interval_size_minutes": window_state.interval_size_minutes,
        "expected_slot_count": window_state.expected_slot_count,
        "received_slot_count": window_state.received_slot_count,
        "received_slot_bitmap": window_state.received_slot_bitmap,
        "completion_status": window_state.completion_status,
        "details": dict(window_state.details or {}),
    }


def _snapshot_hes_read_raw(raw_row: HesReadRaw | None) -> dict[str, object] | None:
    if raw_row is None:
        return None
    return {
        "hes_read_raw_id": raw_row.id,
        "measured_at": raw_row.measured_at.isoformat(),
        "reading_value": str(raw_row.reading_value),
        "quality_code": raw_row.quality_code,
        "status_code": raw_row.status_code,
        "unit_of_measure": raw_row.unit_of_measure,
        "interval_size_minutes": raw_row.interval_size_minutes,
        "source_business_ts": (
            raw_row.source_business_ts.isoformat() if raw_row.source_business_ts is not None else None
        ),
        "source_slot_code": raw_row.source_slot_code,
        "canonical_status": raw_row.canonical_status,
    }


def _snapshot_canonical_measurement(
    canonical_row: CanonicalMeasurement | None,
) -> dict[str, object] | None:
    if canonical_row is None:
        return None
    return {
        "canonical_measurement_id": canonical_row.id,
        "hes_read_raw_id": canonical_row.hes_read_raw_id,
        "measured_at": canonical_row.measured_at.isoformat(),
        "value": str(canonical_row.value),
        "quality_code": canonical_row.quality_code,
        "status_code": canonical_row.status_code,
        "unit_of_measure": canonical_row.unit_of_measure,
    }


def _quantize_value(value: Decimal) -> Decimal:
    return value.quantize(_VALUE_SCALE, rounding=ROUND_HALF_UP)


def _expected_slot_codes(interval_size_minutes: int) -> list[str]:
    if interval_size_minutes <= 0 or 60 % interval_size_minutes != 0:
        raise EstimationActionError(
            "invalid_interval_size",
            "The selected interval window is not supported for synthetic estimation.",
        )
    return [f"{minute:02d}" for minute in range(0, 60, interval_size_minutes)]


def _decode_slot_bitmap(value: str | None) -> set[str]:
    if not value:
        return set()
    return {slot for slot in value.split(",") if slot}


def _encode_slot_bitmap(values: set[str]) -> str | None:
    if not values:
        return None
    return ",".join(sorted(values))


def _find_supporting_previous_final_for_context(
    session: Session,
    *,
    service_point_id: int,
    measuring_component_id: int,
    device_id: int,
    measured_at: datetime,
) -> FinalMeasurement | None:
    return session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.service_point_id == service_point_id,
            FinalMeasurement.measuring_component_id == measuring_component_id,
            FinalMeasurement.device_id == device_id,
            FinalMeasurement.measured_at < measured_at,
        )
        .order_by(FinalMeasurement.measured_at.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )


def _find_supporting_next_final_for_context(
    session: Session,
    *,
    service_point_id: int,
    measuring_component_id: int,
    device_id: int,
    measured_at: datetime,
) -> FinalMeasurement | None:
    return session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.service_point_id == service_point_id,
            FinalMeasurement.measuring_component_id == measuring_component_id,
            FinalMeasurement.device_id == device_id,
            FinalMeasurement.measured_at > measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(1)
    )


def _build_estimation_result(
    session: Session,
    *,
    initial_row: InitialMeasurement,
    target_exception: VeeException,
    strategy_code: str,
    correction_policy: CorrectionPolicyDecision,
    allowed_exception_codes: set[str] | None = None,
) -> EstimationComputationResult:
    previous_final = _find_supporting_previous_final(session, initial_row=initial_row)
    next_final = _find_supporting_next_final(session, initial_row=initial_row)
    resolved_allowed_exception_codes = allowed_exception_codes or ESTIMATION_ALLOWED_EXCEPTION_CODES

    if correction_policy.estimation_policy == CORRECTION_POLICY_BLOCKED:
        return EstimationComputationResult(
            estimation_status="blocked",
            result_code=f"blocked_event_policy_{correction_policy.policy_reason_code}",
            estimated_value=None,
            source_previous_final=previous_final,
            source_next_final=next_final,
            details={
                "blocked_reason": "event_policy_blocked",
                "correction_policy_reason_code": correction_policy.policy_reason_code,
                "recommended_action": correction_policy.recommended_action,
            },
        )

    if target_exception.exception_code not in resolved_allowed_exception_codes:
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
    correction_policy = build_correction_policy_decision(
        session,
        target_exception,
        initial_row=initial_row,
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
            "correction_policy_reason_code": correction_policy.policy_reason_code,
            "recommended_action": correction_policy.recommended_action,
        },
    )

    try:
        computation_result = _build_estimation_result(
            session,
            initial_row=initial_row,
            target_exception=target_exception,
            strategy_code=strategy_code,
            correction_policy=correction_policy,
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
                "correction_policy_snapshot": correction_policy.to_snapshot(),
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
                ) = recalculate_downstream_artifacts(
                    session,
                    previous_final=previous_current_final,
                    current_final=current_final,
                    trigger_type="estimation_apply",
                    revision_reason_code=ESTIMATION_REVISION_REASON_CODE,
                    details_context={
                        "trigger_source": "estimation",
                        "estimation_audit_id": audit_row.id,
                        "initial_measurement_id": initial_row.id,
                        "vee_exception_id": target_exception.id,
                        "previous_final_measurement_id": (
                            previous_current_final.id
                            if previous_current_final is not None
                            else None
                        ),
                    },
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


def _get_missing_interval_window_state(
    session: Session,
    *,
    anchor_initial_row: InitialMeasurement,
) -> RawIntervalWindowState | None:
    canonical_row = anchor_initial_row.canonical_measurement
    raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
    if (
        raw_row is None
        or raw_row.source_business_ts is None
        or raw_row.source_system is None
        or raw_row.meter_identifier is None
        or raw_row.channel_identifier is None
    ):
        return None
    return session.scalar(
        select(RawIntervalWindowState)
        .where(
            RawIntervalWindowState.source_system == raw_row.source_system,
            RawIntervalWindowState.meter_identifier == raw_row.meter_identifier,
            RawIntervalWindowState.channel_identifier == raw_row.channel_identifier,
            RawIntervalWindowState.window_start_at == raw_row.source_business_ts,
            RawIntervalWindowState.window_size_minutes == 60,
        )
        .limit(1)
    )


def _resolve_single_missing_slot(
    window_state: RawIntervalWindowState,
) -> tuple[str | None, datetime | None, dict[str, object] | None]:
    if window_state.window_size_minutes != 60:
        return "blocked_missing_interval_invalid_window_state", None, None
    if window_state.interval_size_minutes not in {15, 30, 60}:
        return "blocked_missing_interval_invalid_window_state", None, None

    expected_slot_codes = _expected_slot_codes(window_state.interval_size_minutes)
    details = dict(window_state.details or {})
    configured_expected_slot_codes = details.get("expected_slot_codes")
    if isinstance(configured_expected_slot_codes, list) and configured_expected_slot_codes:
        expected_slot_codes = [str(value) for value in configured_expected_slot_codes]

    received_slot_codes = _decode_slot_bitmap(window_state.received_slot_bitmap)
    missing_slot_codes = sorted(set(expected_slot_codes) - received_slot_codes)
    if len(missing_slot_codes) != 1:
        return "blocked_missing_interval_multi_slot_window", None, None

    missing_slot_code = missing_slot_codes[0]
    target_measured_at = window_state.window_start_at + timedelta(minutes=int(missing_slot_code))
    return (
        None,
        target_measured_at,
        {
            "missing_slot_code": missing_slot_code,
            "expected_slot_codes": expected_slot_codes,
            "received_slot_codes": sorted(received_slot_codes),
        },
    )


def _existing_measurement_present_for_slot(
    session: Session,
    *,
    window_state: RawIntervalWindowState,
    target_measured_at: datetime,
) -> bool:
    return (
        session.scalar(
            select(HesReadRaw.id)
            .where(
                HesReadRaw.source_system == window_state.source_system,
                HesReadRaw.meter_identifier == window_state.meter_identifier,
                HesReadRaw.channel_identifier == window_state.channel_identifier,
                HesReadRaw.measured_at == target_measured_at,
            )
            .limit(1)
        )
        is not None
    )


def _create_synthetic_ingest_batch(
    session: Session,
    *,
    anchor_initial_row: InitialMeasurement,
    anchor_exception: VeeException,
    target_measured_at: datetime,
    strategy_code: str,
    estimated_by: str,
) -> IngestBatch:
    anchor_raw = anchor_initial_row.canonical_measurement.hes_read_raw
    return IngestBatch(
        hes_system_id=anchor_raw.hes_system_id if anchor_raw is not None else None,
        source_system=anchor_raw.source_system if anchor_raw is not None else "HES",
        batch_id=(
            f"synthetic-missing-interval-{anchor_exception.id}-{target_measured_at.isoformat()}"
        ),
        record_type="hes_read_raw",
        received_at=datetime.now(timezone.utc),
        payload={
            "origin": "synthetic_missing_interval_estimation",
            "anchor_vee_exception_id": anchor_exception.id,
            "target_measured_at": target_measured_at.isoformat(),
            "strategy_code": strategy_code,
            "estimated_by": estimated_by,
        },
    )


def _create_synthetic_measurement_chain(
    session: Session,
    *,
    anchor_initial_row: InitialMeasurement,
    window_state: RawIntervalWindowState,
    target_measured_at: datetime,
    missing_slot_code: str,
    estimated_value: Decimal,
    strategy_code: str,
    estimated_by: str,
    ingest_batch: IngestBatch,
) -> InitialMeasurement:
    now = datetime.now(timezone.utc)
    anchor_raw = anchor_initial_row.canonical_measurement.hes_read_raw
    unit_of_measure = (
        (anchor_initial_row.unit_of_measure or "").strip()
        or anchor_initial_row.measuring_component.unit_of_measure
    )
    status_code = "ESTIMATED"
    raw_row = HesReadRaw(
        ingest_batch=ingest_batch,
        hes_system_id=anchor_raw.hes_system_id if anchor_raw is not None else None,
        adapter_instance_id=anchor_raw.adapter_instance_id if anchor_raw is not None else None,
        adapter_run_id=anchor_raw.adapter_run_id if anchor_raw is not None else None,
        source_system=window_state.source_system,
        meter_identifier=window_state.meter_identifier,
        channel_identifier=window_state.channel_identifier,
        measured_at=target_measured_at,
        interval_end_at=target_measured_at + timedelta(minutes=window_state.interval_size_minutes),
        interval_size_minutes=window_state.interval_size_minutes,
        reading_value=estimated_value,
        quality_code=ESTIMATION_QUALITY_CODE,
        status_code=status_code,
        unit_of_measure=unit_of_measure,
        source_business_ts=window_state.window_start_at,
        source_write_ts=now,
        received_at=now,
        canonical_status="mapped",
        is_duplicate=False,
        payload={
            "origin": "synthetic_missing_interval_estimation",
            "source_meter_identifier": window_state.meter_identifier,
            "source_channel_identifier": window_state.channel_identifier,
            "source_business_ts": window_state.window_start_at.isoformat(),
            "source_slot_code": missing_slot_code,
            "strategy_code": strategy_code,
            "estimated_by": estimated_by,
        },
        source_slot_code=missing_slot_code,
        source_slot_index=int(missing_slot_code) // window_state.interval_size_minutes,
    )
    session.add(raw_row)
    session.flush()

    canonical_row = CanonicalMeasurement(
        hes_read_raw=raw_row,
        hes_read_raw_measured_at=raw_row.measured_at,
        measuring_component_id=anchor_initial_row.measuring_component_id,
        device_id=anchor_initial_row.device_id,
        service_point_id=anchor_initial_row.service_point_id,
        measured_at=target_measured_at,
        value=estimated_value,
        quality_code=ESTIMATION_QUALITY_CODE,
        status_code=status_code,
        unit_of_measure=unit_of_measure,
    )
    session.add(canonical_row)
    session.flush()

    synthetic_initial = InitialMeasurement(
        canonical_measurement=canonical_row,
        measuring_component_id=anchor_initial_row.measuring_component_id,
        device_id=anchor_initial_row.device_id,
        service_point_id=anchor_initial_row.service_point_id,
        measured_at=target_measured_at,
        value=estimated_value,
        quality_code=ESTIMATION_QUALITY_CODE,
        status_code=status_code,
        unit_of_measure=unit_of_measure,
        initial_status="ready",
        ready_for_vee_at=now,
        details={
            "origin": "synthetic_missing_interval_estimation",
            "anchor_initial_measurement_id": anchor_initial_row.id,
            "source_business_ts": window_state.window_start_at.isoformat(),
            "source_slot_code": missing_slot_code,
            "strategy_code": strategy_code,
            "estimated_by": estimated_by,
        },
    )
    session.add(synthetic_initial)
    session.flush()
    return synthetic_initial


def _load_window_initial_measurements(
    session: Session,
    *,
    window_state: RawIntervalWindowState,
) -> list[InitialMeasurement]:
    return session.scalars(
        select(InitialMeasurement)
        .join(InitialMeasurement.canonical_measurement)
        .join(CanonicalMeasurement.hes_read_raw)
        .where(HesReadRaw.source_system == window_state.source_system)
        .where(HesReadRaw.meter_identifier == window_state.meter_identifier)
        .where(HesReadRaw.channel_identifier == window_state.channel_identifier)
        .where(HesReadRaw.source_business_ts == window_state.window_start_at)
        .order_by(InitialMeasurement.measured_at.asc(), InitialMeasurement.id.asc())
    ).all()


def apply_synthetic_missing_interval_estimation_from_vee_exception(
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
    if target_exception.exception_code != "vee_missing_interval_detected":
        raise EstimationActionError(
            "unsupported_exception_code",
            "Synthetic missing-interval estimation only supports missing-interval exceptions.",
        )

    anchor_initial = target_exception.initial_measurement
    anchor_current_final = _get_current_final_measurement_for_initial(
        session,
        initial_measurement_id=anchor_initial.id,
    )
    correction_policy = build_correction_policy_decision(
        session,
        target_exception,
        initial_row=anchor_initial,
    )
    window_state = _get_missing_interval_window_state(session, anchor_initial_row=anchor_initial)
    result_code: str | None = None
    target_measured_at = anchor_initial.measured_at
    window_context: dict[str, object] = {}
    computation_result: EstimationComputationResult | None = None
    synthetic_initial: InitialMeasurement | None = None
    audit_row: EstimationAudit | None = None
    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="estimation",
        trigger_type="manual",
        details={
            "vee_exception_id": target_exception.id,
            "initial_measurement_id": anchor_initial.id,
            "strategy_code": strategy_code,
            "estimated_by": estimated_by,
            "estimation_mode": ESTIMATION_MODE_SYNTHETIC_MISSING_INTERVAL,
        },
    )

    try:
        if window_state is None:
            result_code = "blocked_missing_interval_invalid_window_state"
        elif correction_policy.estimation_policy == CORRECTION_POLICY_BLOCKED:
            result_code = f"blocked_event_policy_{correction_policy.policy_reason_code}"
        else:
            result_code, resolved_target_measured_at, resolved_window_context = (
                _resolve_single_missing_slot(window_state)
            )
            if resolved_target_measured_at is not None:
                target_measured_at = resolved_target_measured_at
            if resolved_window_context is not None:
                window_context = resolved_window_context
            if result_code is None and window_state is not None:
                if _existing_measurement_present_for_slot(
                    session,
                    window_state=window_state,
                    target_measured_at=target_measured_at,
                ):
                    result_code = "blocked_missing_interval_existing_measurement_present"

        if result_code is None:
            unit_of_measure = (
                (anchor_initial.unit_of_measure or "").strip()
                or anchor_initial.measuring_component.unit_of_measure
            )
            synthetic_target = InitialMeasurement(
                canonical_measurement_id=anchor_initial.canonical_measurement_id,
                measuring_component_id=anchor_initial.measuring_component_id,
                device_id=anchor_initial.device_id,
                service_point_id=anchor_initial.service_point_id,
                measured_at=target_measured_at,
                value=Decimal("0.0000"),
                quality_code=ESTIMATION_QUALITY_CODE,
                status_code="ESTIMATED",
                unit_of_measure=unit_of_measure,
                initial_status="ready",
                ready_for_vee_at=datetime.now(timezone.utc),
                details={},
            )
            computation_result = _build_estimation_result(
                session,
                initial_row=synthetic_target,
                target_exception=target_exception,
                strategy_code=strategy_code,
                correction_policy=correction_policy,
                allowed_exception_codes={"vee_missing_interval_detected"},
            )
            if computation_result.estimation_status == "blocked":
                result_code = computation_result.result_code

        audit_row = EstimationAudit(
            pipeline_run_id=pipeline_run.id,
            service_point_id=anchor_initial.service_point_id,
            measuring_component_id=anchor_initial.measuring_component_id,
            device_id=anchor_initial.device_id,
            target_initial_measurement_id=anchor_initial.id,
            anchor_vee_exception_id=target_exception.id,
            raw_interval_window_state_id=window_state.id if window_state is not None else None,
            target_measured_at=target_measured_at,
            estimation_mode=ESTIMATION_MODE_SYNTHETIC_MISSING_INTERVAL,
            strategy_code=strategy_code,
            estimation_status="blocked" if result_code is not None else "applied",
            estimated_value=None if computation_result is None else computation_result.estimated_value,
            unit_of_measure=anchor_initial.unit_of_measure or None,
            source_previous_final_measurement_id=(
                computation_result.source_previous_final.id
                if computation_result is not None and computation_result.source_previous_final is not None
                else None
            ),
            source_next_final_measurement_id=(
                computation_result.source_next_final.id
                if computation_result is not None and computation_result.source_next_final is not None
                else None
            ),
            superseded_final_measurement_id=None,
            result_final_measurement_id=None,
            operator_memo=operator_memo,
            details={
                "estimation_mode": ESTIMATION_MODE_SYNTHETIC_MISSING_INTERVAL,
                "anchor_vee_exception_snapshot": {
                    "vee_exception_id": target_exception.id,
                    "exception_code": target_exception.exception_code,
                    "severity": target_exception.severity,
                    "blocking_finalization": target_exception.blocking_finalization,
                },
                "original_initial_measurement_snapshot": _snapshot_initial_measurement(anchor_initial),
                "source_previous_final_snapshot": (
                    None
                    if computation_result is None
                    else _snapshot_final_measurement(computation_result.source_previous_final)
                ),
                "source_next_final_snapshot": (
                    None
                    if computation_result is None
                    else _snapshot_final_measurement(computation_result.source_next_final)
                ),
                "correction_policy_snapshot": correction_policy.to_snapshot(),
                "window_state_snapshot_before": _snapshot_raw_interval_window_state(window_state),
                "window_context": window_context,
                "estimation_result": (
                    {"blocked_reason": result_code} if computation_result is None else computation_result.details
                ),
            },
        )
        session.add(audit_row)
        session.flush()

        if result_code is not None:
            complete_pipeline_run(
                pipeline_run,
                result_code="estimation_blocked",
                details={
                    **pipeline_run.details,
                    "estimation_audit_id": audit_row.id,
                    "result_code": result_code,
                },
            )
            return EstimationSummary(
                estimation_audit_id=audit_row.id,
                pipeline_run_id=pipeline_run.id,
                target_vee_exception_id=target_exception.id,
                initial_measurement_id=anchor_initial.id,
                strategy_code=strategy_code,
                estimation_status="blocked",
                result_code=result_code,
                estimated_value=None,
                vee_execution_log_id=None,
                active_exception_count=1,
                blocking_exception_count=1 if target_exception.blocking_finalization else 0,
                previous_final_id=anchor_current_final.id if anchor_current_final is not None else None,
                current_final_id=anchor_current_final.id if anchor_current_final is not None else None,
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

        assert computation_result is not None
        assert computation_result.estimated_value is not None
        assert window_state is not None
        missing_slot_code = str(window_context["missing_slot_code"])

        synthetic_batch = _create_synthetic_ingest_batch(
            session,
            anchor_initial_row=anchor_initial,
            anchor_exception=target_exception,
            target_measured_at=target_measured_at,
            strategy_code=strategy_code,
            estimated_by=estimated_by,
        )
        session.add(synthetic_batch)
        session.flush()

        synthetic_initial = _create_synthetic_measurement_chain(
            session,
            anchor_initial_row=anchor_initial,
            window_state=window_state,
            target_measured_at=target_measured_at,
            missing_slot_code=missing_slot_code,
            estimated_value=computation_result.estimated_value,
            strategy_code=strategy_code,
            estimated_by=estimated_by,
            ingest_batch=synthetic_batch,
        )
        synthetic_initial.details = {
            **dict(synthetic_initial.details or {}),
            "estimation": {
                "estimation_audit_id": audit_row.id,
                "strategy_code": strategy_code,
                "estimated_at": datetime.now(timezone.utc).isoformat(),
                "estimated_by": estimated_by,
            },
        }

        merged_slot_codes = _decode_slot_bitmap(window_state.received_slot_bitmap)
        merged_slot_codes.add(missing_slot_code)
        details_after = dict(window_state.details or {})
        details_after["synthetic_completion"] = {
            "estimation_audit_id": audit_row.id,
            "anchor_vee_exception_id": target_exception.id,
            "missing_slot_code": missing_slot_code,
            "synthetic_hes_read_raw_id": synthetic_initial.canonical_measurement.hes_read_raw_id,
            "synthetic_initial_measurement_id": synthetic_initial.id,
        }
        window_state.received_slot_bitmap = _encode_slot_bitmap(merged_slot_codes)
        window_state.received_slot_count = len(merged_slot_codes)
        window_state.completion_status = "complete"
        window_state.last_ingest_batch_id = synthetic_batch.id
        window_state.last_source_write_ts = datetime.now(timezone.utc)
        window_state.details = details_after

        resolve_vee_exception(
            session,
            target_exception.id,
            resolution_type="estimated",
            operator_memo=operator_memo,
        )

        reevaluated_initial_measurement_ids: list[int] = []
        synthetic_execution_id: int | None = None
        for row in _load_window_initial_measurements(session, window_state=window_state):
            execution = reevaluate_initial_measurement(
                session,
                row.id,
                reevaluated_by=estimated_by,
                operator_memo=operator_memo,
            )
            reevaluated_initial_measurement_ids.append(row.id)
            if row.id == synthetic_initial.id:
                synthetic_execution_id = execution.id

        active_exceptions = _load_active_vee_exceptions(
            session,
            initial_measurement_id=synthetic_initial.id,
        )
        blocking_exception_count = sum(1 for row in active_exceptions if row.blocking_finalization)

        current_final: FinalMeasurement | None = None
        final_created = False
        daily_usage_groups_updated = 0
        daily_usage_rows_deleted = 0
        monthly_usage_groups_updated = 0
        monthly_usage_rows_deleted = 0
        usage_recalculation_results: list[UsageRecalculationResult] = []
        determinant_summary: BillDeterminantCalculationSummary | None = None
        charge_summary: BillChargeCalculationSummary | None = None

        if blocking_exception_count == 0 and is_initial_measurement_finalizable(synthetic_initial):
            current_final, final_created = create_or_get_final_measurement(
                session,
                synthetic_initial,
                revision_reason_code=ESTIMATION_REVISION_REASON_CODE,
            )
            if final_created and current_final is not None:
                (
                    daily_usage_groups_updated,
                    daily_usage_rows_deleted,
                    monthly_usage_groups_updated,
                    monthly_usage_rows_deleted,
                    usage_recalculation_results,
                    determinant_summary,
                    charge_summary,
                ) = recalculate_downstream_artifacts(
                    session,
                    previous_final=None,
                    current_final=current_final,
                    trigger_type="estimation_apply",
                    revision_reason_code=ESTIMATION_REVISION_REASON_CODE,
                    details_context={
                        "trigger_source": "synthetic_missing_interval_estimation",
                        "estimation_audit_id": audit_row.id,
                        "initial_measurement_id": synthetic_initial.id,
                        "anchor_initial_measurement_id": anchor_initial.id,
                        "vee_exception_id": target_exception.id,
                    },
                )

        audit_row.result_final_measurement_id = current_final.id if current_final is not None else None
        audit_row.details = {
            **audit_row.details,
            "synthetic_hes_read_raw_snapshot": _snapshot_hes_read_raw(
                synthetic_initial.canonical_measurement.hes_read_raw
            ),
            "synthetic_canonical_measurement_snapshot": _snapshot_canonical_measurement(
                synthetic_initial.canonical_measurement
            ),
            "synthetic_initial_measurement_snapshot": _snapshot_initial_measurement(synthetic_initial),
            "result_final_measurement_snapshot": _snapshot_final_measurement(current_final),
            "window_state_snapshot_after": _snapshot_raw_interval_window_state(window_state),
            "re_evaluated_initial_measurement_ids": reevaluated_initial_measurement_ids,
            "vee_execution_log_id": synthetic_execution_id,
            "active_exception_count": len(active_exceptions),
            "blocking_exception_count": blocking_exception_count,
            "downstream_recalculation_summary": {
                "daily_usage_groups_updated": daily_usage_groups_updated,
                "daily_usage_rows_deleted": daily_usage_rows_deleted,
                "monthly_usage_groups_updated": monthly_usage_groups_updated,
                "monthly_usage_rows_deleted": monthly_usage_rows_deleted,
                "usage_recalculation_results": [asdict(row) for row in usage_recalculation_results],
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
                "synthetic_initial_measurement_id": synthetic_initial.id,
                "vee_execution_log_id": synthetic_execution_id,
                "active_exception_count": len(active_exceptions),
                "blocking_exception_count": blocking_exception_count,
                "final_created": final_created,
            },
        )
        return EstimationSummary(
            estimation_audit_id=audit_row.id,
            pipeline_run_id=pipeline_run.id,
            target_vee_exception_id=target_exception.id,
            initial_measurement_id=synthetic_initial.id,
            strategy_code=strategy_code,
            estimation_status="applied",
            result_code=result_code,
            estimated_value=computation_result.estimated_value,
            vee_execution_log_id=synthetic_execution_id,
            active_exception_count=len(active_exceptions),
            blocking_exception_count=blocking_exception_count,
            previous_final_id=None,
            current_final_id=current_final.id if current_final is not None else None,
            final_created=final_created,
            final_superseded=False,
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
