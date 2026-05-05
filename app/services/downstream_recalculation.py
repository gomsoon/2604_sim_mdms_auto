from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillCharge, FinalMeasurement
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
from app.services.processing_replay import (
    UsageRecalculationResult,
    recalculate_impacted_usage_windows,
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


def recalculate_downstream_artifacts(
    session: Session,
    *,
    previous_final: FinalMeasurement | None,
    current_final: FinalMeasurement,
    trigger_type: str,
    revision_reason_code: str,
    details_context: dict[str, object],
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
        trigger_type=trigger_type,
        details_context=details_context,
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
            trigger_type=trigger_type,
            revision_reason_code=revision_reason_code,
            details_context={
                **details_context,
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
            trigger_type=trigger_type,
            revision_reason_code=revision_reason_code,
            details_context={
                **details_context,
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
