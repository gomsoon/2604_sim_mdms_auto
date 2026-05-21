from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FinalMeasurement,
    InitialMeasurement,
    ManualEditAudit,
    VeeException,
)
from app.services.correction_policy import (
    CORRECTION_POLICY_BLOCKED,
    CorrectionPolicyDecision,
    build_correction_policy_decision,
)
from app.services.bill_charges import BillChargeCalculationSummary
from app.services.bill_determinants import BillDeterminantCalculationSummary
from app.services.downstream_recalculation import recalculate_downstream_artifacts
from app.services.finalization import create_or_get_final_measurement, is_initial_measurement_finalizable
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from app.services.processing_replay import UsageRecalculationResult
from app.services.vee import evaluate_or_get_vee_baseline, resolve_vee_exception


MANUAL_EDIT_ALLOWED_EXCEPTION_CODES = {
    "vee_negative_value_detected",
    "vee_high_value_detected",
    "vee_zero_value_detected",
}
SUPPORTED_MANUAL_EDIT_REASON_CODES = {
    "operator_meter_correction",
    "operator_source_override",
    "operator_data_entry_fix",
    "operator_business_override",
}
MANUAL_EDIT_REVISION_REASON_CODE = "manual_edit_applied"
_VALUE_SCALE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class ManualEditActionError(Exception):
    error_code: str
    fallback_message: str


@dataclass(frozen=True, slots=True)
class ManualEditComputationResult:
    edit_status: str
    result_code: str
    edited_value: Decimal | None
    edited_quality_code: str | None
    edited_status_code: str | None
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class ManualEditSummary:
    manual_edit_audit_id: int
    pipeline_run_id: int
    target_vee_exception_id: int
    initial_measurement_id: int
    reason_code: str
    edit_status: str
    result_code: str
    edited_value: Decimal | None
    edited_quality_code: str | None
    edited_status_code: str | None
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


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_value(value: Decimal | int | float | str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        normalized = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return normalized.quantize(_VALUE_SCALE, rounding=ROUND_HALF_UP)


def _get_active_vee_exception(session: Session, vee_exception_id: int) -> VeeException:
    vee_exception = session.get(VeeException, vee_exception_id)
    if vee_exception is None:
        raise ManualEditActionError("not_found", "The selected VEE exception does not exist.")
    if vee_exception.exception_status not in {"open", "acknowledged"}:
        raise ManualEditActionError(
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


def _build_manual_edit_result(
    *,
    initial_row: InitialMeasurement,
    target_exception: VeeException,
    correction_policy: CorrectionPolicyDecision,
    reason_code: str | None,
    edited_value: Decimal | None,
    edited_quality_code: str | None,
    edited_status_code: str | None,
) -> ManualEditComputationResult:
    if correction_policy.manual_edit_policy == CORRECTION_POLICY_BLOCKED:
        return ManualEditComputationResult(
            edit_status="blocked",
            result_code=f"blocked_event_policy_{correction_policy.policy_reason_code}",
            edited_value=edited_value,
            edited_quality_code=edited_quality_code,
            edited_status_code=edited_status_code,
            details={
                "blocked_reason": "event_policy_blocked",
                "correction_policy_reason_code": correction_policy.policy_reason_code,
                "recommended_action": correction_policy.recommended_action,
            },
        )

    if target_exception.exception_code not in MANUAL_EDIT_ALLOWED_EXCEPTION_CODES:
        return ManualEditComputationResult(
            edit_status="blocked",
            result_code="blocked_unsupported_exception_code",
            edited_value=edited_value,
            edited_quality_code=edited_quality_code,
            edited_status_code=edited_status_code,
            details={
                "blocked_reason": "unsupported_exception_code",
                "exception_code": target_exception.exception_code,
            },
        )

    if reason_code not in SUPPORTED_MANUAL_EDIT_REASON_CODES:
        return ManualEditComputationResult(
            edit_status="blocked",
            result_code="blocked_invalid_reason_code",
            edited_value=edited_value,
            edited_quality_code=edited_quality_code,
            edited_status_code=edited_status_code,
            details={
                "blocked_reason": "invalid_reason_code",
                "reason_code": reason_code,
            },
        )

    if edited_value is None:
        return ManualEditComputationResult(
            edit_status="blocked",
            result_code="blocked_invalid_edited_value",
            edited_value=None,
            edited_quality_code=edited_quality_code,
            edited_status_code=edited_status_code,
            details={"blocked_reason": "invalid_edited_value"},
        )

    effective_quality_code = (
        edited_quality_code if edited_quality_code is not None else initial_row.quality_code
    )
    effective_status_code = (
        edited_status_code if edited_status_code is not None else initial_row.status_code
    )
    if (
        edited_value == initial_row.value
        and effective_quality_code == initial_row.quality_code
        and effective_status_code == initial_row.status_code
    ):
        return ManualEditComputationResult(
            edit_status="blocked",
            result_code="blocked_no_effective_change",
            edited_value=edited_value,
            edited_quality_code=edited_quality_code,
            edited_status_code=edited_status_code,
            details={"blocked_reason": "no_effective_change"},
        )

    return ManualEditComputationResult(
        edit_status="applied",
        result_code="manual_edit_applied",
        edited_value=edited_value,
        edited_quality_code=edited_quality_code,
        edited_status_code=edited_status_code,
        details={
            "effective_quality_code": effective_quality_code,
            "effective_status_code": effective_status_code,
        },
    )


def apply_manual_edit_from_vee_exception(
    session: Session,
    vee_exception_id: int,
    *,
    edited_value: Decimal | int | float | str | None,
    reason_code: str,
    edited_by: str,
    edited_by_user_account_id: int | None = None,
    operator_memo: str | None = None,
    edited_quality_code: str | None = None,
    edited_status_code: str | None = None,
) -> ManualEditSummary:
    normalized_edited_by = _normalize_optional_text(edited_by)
    if normalized_edited_by is None:
        raise ManualEditActionError(
            "missing_edited_by",
            "The editing actor must be provided.",
        )

    target_exception = _get_active_vee_exception(session, vee_exception_id)
    initial_row = target_exception.initial_measurement
    previous_current_final = _get_current_final_measurement_for_initial(
        session,
        initial_measurement_id=initial_row.id,
    )
    normalized_reason_code = _normalize_optional_text(reason_code)
    normalized_edited_value = _normalize_value(edited_value)
    normalized_edited_quality_code = _normalize_optional_text(edited_quality_code)
    normalized_edited_status_code = _normalize_optional_text(edited_status_code)
    normalized_operator_memo = _normalize_optional_text(operator_memo)
    correction_policy = build_correction_policy_decision(
        session,
        target_exception,
        initial_row=initial_row,
    )

    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="manual_edit",
        trigger_type="manual",
        details={
            "vee_exception_id": vee_exception_id,
            "initial_measurement_id": initial_row.id,
            "reason_code": normalized_reason_code,
            "edited_by": normalized_edited_by,
            "edited_by_user_account_id": edited_by_user_account_id,
            "edited_value": None if normalized_edited_value is None else str(normalized_edited_value),
            "edited_quality_code": normalized_edited_quality_code,
            "edited_status_code": normalized_edited_status_code,
            "operator_memo": normalized_operator_memo,
            "correction_policy_reason_code": correction_policy.policy_reason_code,
            "recommended_action": correction_policy.recommended_action,
        },
    )

    try:
        computation_result = _build_manual_edit_result(
            initial_row=initial_row,
            target_exception=target_exception,
            correction_policy=correction_policy,
            reason_code=normalized_reason_code,
            edited_value=normalized_edited_value,
            edited_quality_code=normalized_edited_quality_code,
            edited_status_code=normalized_edited_status_code,
        )
        audit_row = ManualEditAudit(
            pipeline_run_id=pipeline_run.id,
            service_point_id=initial_row.service_point_id,
            measuring_component_id=initial_row.measuring_component_id,
            device_id=initial_row.device_id,
            target_initial_measurement_id=initial_row.id,
            related_vee_exception_id=target_exception.id,
            target_measured_at=initial_row.measured_at,
            reason_code=normalized_reason_code or "invalid_reason_code",
            edit_status=computation_result.edit_status,
            edited_value=computation_result.edited_value,
            edited_quality_code=computation_result.edited_quality_code,
            edited_status_code=computation_result.edited_status_code,
            edited_by=normalized_edited_by,
            edited_by_user_account_id=edited_by_user_account_id,
            operator_memo=normalized_operator_memo,
            superseded_final_measurement_id=None,
            result_final_measurement_id=None,
            details={
                "target_vee_exception_snapshot": {
                    "vee_exception_id": target_exception.id,
                    "exception_code": target_exception.exception_code,
                    "severity": target_exception.severity,
                    "blocking_finalization": target_exception.blocking_finalization,
                },
                "original_initial_measurement_snapshot": _snapshot_initial_measurement(initial_row),
                "correction_policy_snapshot": correction_policy.to_snapshot(),
                "manual_edit_result": computation_result.details,
                "edited_by": normalized_edited_by,
                "edited_by_user_account_id": edited_by_user_account_id,
            },
        )
        session.add(audit_row)
        session.flush()

        if computation_result.edit_status == "blocked":
            complete_pipeline_run(
                pipeline_run,
                result_code="manual_edit_blocked",
                details={
                    **pipeline_run.details,
                    "manual_edit_audit_id": audit_row.id,
                    "result_code": computation_result.result_code,
                },
            )
            return ManualEditSummary(
                manual_edit_audit_id=audit_row.id,
                pipeline_run_id=pipeline_run.id,
                target_vee_exception_id=target_exception.id,
                initial_measurement_id=initial_row.id,
                reason_code=audit_row.reason_code,
                edit_status="blocked",
                result_code=computation_result.result_code,
                edited_value=computation_result.edited_value,
                edited_quality_code=computation_result.edited_quality_code,
                edited_status_code=computation_result.edited_status_code,
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

        assert computation_result.edited_value is not None
        initial_row.value = computation_result.edited_value
        if computation_result.edited_quality_code is not None:
            initial_row.quality_code = computation_result.edited_quality_code
        if computation_result.edited_status_code is not None:
            initial_row.status_code = computation_result.edited_status_code
        updated_details = dict(initial_row.details or {})
        updated_details["manual_edit"] = {
            "manual_edit_audit_id": audit_row.id,
            "reason_code": audit_row.reason_code,
            "edited_at": datetime.now(timezone.utc).isoformat(),
            "edited_by": normalized_edited_by,
            "edited_by_user_account_id": edited_by_user_account_id,
        }
        initial_row.details = updated_details

        resolve_vee_exception(
            session,
            target_exception.id,
            resolution_type="manually_corrected",
            resolved_by=normalized_edited_by,
            resolved_by_user_account_id=edited_by_user_account_id,
            operator_memo=normalized_operator_memo,
        )
        execution, _ = evaluate_or_get_vee_baseline(
            session,
            initial_row,
            pipeline_run=pipeline_run,
            trigger_type="manual_edit_apply",
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
                revision_reason_code=MANUAL_EDIT_REVISION_REASON_CODE,
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
                    trigger_type="manual_edit_apply",
                    revision_reason_code=MANUAL_EDIT_REVISION_REASON_CODE,
                    details_context={
                        "trigger_source": "manual_edit",
                        "manual_edit_audit_id": audit_row.id,
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

        result_code = "manual_edit_applied"
        if blocking_exception_count > 0:
            result_code = "manual_edit_applied_with_open_exceptions"
        elif not final_created:
            result_code = "manual_edit_applied_without_final_change"

        complete_pipeline_run(
            pipeline_run,
            result_code=result_code,
            details={
                **pipeline_run.details,
                "manual_edit_audit_id": audit_row.id,
                "vee_execution_log_id": execution.id,
                "active_exception_count": len(active_exceptions),
                "blocking_exception_count": blocking_exception_count,
                "final_created": final_created,
                "final_superseded": final_superseded,
            },
        )
        return ManualEditSummary(
            manual_edit_audit_id=audit_row.id,
            pipeline_run_id=pipeline_run.id,
            target_vee_exception_id=target_exception.id,
            initial_measurement_id=initial_row.id,
            reason_code=audit_row.reason_code,
            edit_status="applied",
            result_code=result_code,
            edited_value=computation_result.edited_value,
            edited_quality_code=computation_result.edited_quality_code,
            edited_status_code=computation_result.edited_status_code,
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
            result_code="manual_edit_failed_exception",
            details=pipeline_run.details,
        )
        raise
