from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.services.visibility import (
    BillChargeFilters,
    VisibilityFilterError,
    build_bill_charge_filters,
    list_bill_charges,
)

SUPPORTED_INVOICE_SUMMARY_STATUSES = ("complete", "partial", "blocked")


@dataclass(frozen=True, slots=True)
class InvoiceSummaryFilters:
    service_point_id: int | None = None
    service_point: str | None = None
    external_channel_id: str | None = None
    charge_type: str | None = None
    calculation_status: str | None = None
    tariff_plan_code: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    summary_status: str | None = None


@dataclass(frozen=True, slots=True)
class InvoiceSummaryRow:
    service_point_id: int
    service_point_external_id: str
    billing_period_start_at: datetime
    billing_period_end_at: datetime
    currency_code: str | None
    tariff_plan_code: str | None
    charge_count: int
    complete_count: int
    partial_count: int
    blocked_count: int
    subtotal_amount: Decimal | None
    summary_status: str
    export_eligible: bool
    latest_calculated_at: datetime | None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def build_invoice_summary_filters(args) -> InvoiceSummaryFilters:
    charge_filters = build_bill_charge_filters(args)
    summary_status = _normalize_text(args.get("summary_status"))
    if summary_status not in {None, *SUPPORTED_INVOICE_SUMMARY_STATUSES}:
        raise VisibilityFilterError(
            "invalid_invoice_summary_status_filter",
            "Invoice summary status must be complete, partial, or blocked when provided.",
        )

    return InvoiceSummaryFilters(
        service_point_id=charge_filters.service_point_id,
        service_point=charge_filters.service_point,
        external_channel_id=charge_filters.external_channel_id,
        charge_type=charge_filters.charge_type,
        calculation_status=charge_filters.calculation_status,
        tariff_plan_code=charge_filters.tariff_plan_code,
        date_from=charge_filters.date_from,
        date_to=charge_filters.date_to,
        summary_status=summary_status,
    )


def _build_charge_filters(filters: InvoiceSummaryFilters) -> BillChargeFilters:
    return BillChargeFilters(
        service_point_id=filters.service_point_id,
        service_point=filters.service_point,
        external_channel_id=filters.external_channel_id,
        charge_type=filters.charge_type,
        calculation_status=filters.calculation_status,
        tariff_plan_code=filters.tariff_plan_code,
        date_from=filters.date_from,
        date_to=filters.date_to,
        include_history=False,
    )


def _derive_summary_status(
    *,
    complete_count: int,
    partial_count: int,
    blocked_count: int,
) -> str:
    if blocked_count > 0:
        return "blocked"
    if partial_count > 0:
        return "partial"
    return "complete"


def list_invoice_summaries(
    session: Session,
    filters: InvoiceSummaryFilters,
    *,
    limit: int = 50,
) -> list[InvoiceSummaryRow]:
    charge_rows = list_bill_charges(session, _build_charge_filters(filters), limit=None)

    grouped_rows: dict[
        tuple[int, datetime, datetime, str | None, str | None],
        list,
    ] = {}
    for row in charge_rows:
        group_key = (
            row.service_point_id,
            row.billing_period_start_at,
            row.billing_period_end_at,
            row.currency_code,
            row.tariff_plan_code,
        )
        grouped_rows.setdefault(group_key, []).append(row)

    summaries: list[InvoiceSummaryRow] = []
    for group_rows in grouped_rows.values():
        first_row = group_rows[0]
        complete_count = sum(1 for row in group_rows if row.calculation_status == "complete")
        partial_count = sum(1 for row in group_rows if row.calculation_status == "partial")
        blocked_count = sum(1 for row in group_rows if row.calculation_status == "blocked")
        summary_status = _derive_summary_status(
            complete_count=complete_count,
            partial_count=partial_count,
            blocked_count=blocked_count,
        )
        if filters.summary_status is not None and summary_status != filters.summary_status:
            continue

        subtotal_amount = Decimal("0")
        amount_present = False
        latest_calculated_at = None
        for row in group_rows:
            if row.charge_amount is not None:
                subtotal_amount += row.charge_amount
                amount_present = True
            if latest_calculated_at is None or row.calculated_at > latest_calculated_at:
                latest_calculated_at = row.calculated_at

        summaries.append(
            InvoiceSummaryRow(
                service_point_id=first_row.service_point_id,
                service_point_external_id=first_row.service_point.external_id,
                billing_period_start_at=first_row.billing_period_start_at,
                billing_period_end_at=first_row.billing_period_end_at,
                currency_code=first_row.currency_code,
                tariff_plan_code=first_row.tariff_plan_code,
                charge_count=len(group_rows),
                complete_count=complete_count,
                partial_count=partial_count,
                blocked_count=blocked_count,
                subtotal_amount=subtotal_amount if amount_present else None,
                summary_status=summary_status,
                export_eligible=summary_status == "complete",
                latest_calculated_at=latest_calculated_at,
            )
        )

    summaries.sort(
        key=lambda row: (
            -row.billing_period_start_at.timestamp(),
            -row.billing_period_end_at.timestamp(),
            row.tariff_plan_code or "",
            row.currency_code or "",
        )
    )
    return summaries[:limit]
