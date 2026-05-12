from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingExportItem, BillingExportRequest, BillCharge, ServicePoint
from app.services.invoice_summaries import (
    InvoiceSummaryFilters,
    InvoiceSummaryRow,
    list_invoice_summaries,
)
from app.services.operational_events import record_operational_event
from app.services.visibility import BillChargeFilters, list_bill_charges

ACTIVE_BILLING_EXPORT_REQUEST_STATUSES = ("queued", "processing")
SUPPORTED_BILLING_EXPORT_REQUEST_SCOPES = {"service_point_period"}
SUPPORTED_BILLING_EXPORT_TARGET_SYSTEM_CODES = {"generic_json"}
SUPPORTED_BILLING_EXPORT_PAYLOAD_FORMATS = {"generic_json"}


@dataclass(frozen=True, slots=True)
class BillingExportRequestError(Exception):
    error_code: str
    fallback_message: str


@dataclass(frozen=True, slots=True)
class BillingExportRequestCreationResult:
    request: BillingExportRequest
    created_item_count: int
    eligible_item_count: int
    skipped_item_count: int


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _serialize_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _build_progress_payload(request: BillingExportRequest) -> dict[str, object]:
    remaining_count = max(request.item_count - request.processed_count, 0)
    progress_percent = (
        round((request.processed_count / request.item_count) * 100, 2)
        if request.item_count > 0
        else 0.0
    )
    return {
        "remaining_count": remaining_count,
        "progress_percent": progress_percent,
        "processed_count": request.processed_count,
        "succeeded_count": request.succeeded_count,
        "failed_count": request.failed_count,
        "skipped_count": request.skipped_count,
    }


def _update_request_details(
    request: BillingExportRequest,
    *,
    current_item_id: int | None = None,
    current_service_point_id: int | None = None,
    current_billing_period_start_at: datetime | None = None,
    current_billing_period_end_at: datetime | None = None,
    last_processed_item_id: int | None = None,
    last_processed_result_code: str | None = None,
    last_processed_at: datetime | None = None,
) -> None:
    details = dict(request.details or {})
    details.update(_build_progress_payload(request))
    details["current_item_id"] = current_item_id
    details["current_service_point_id"] = current_service_point_id
    details["current_billing_period_start_at"] = (
        current_billing_period_start_at.isoformat()
        if current_billing_period_start_at is not None
        else None
    )
    details["current_billing_period_end_at"] = (
        current_billing_period_end_at.isoformat()
        if current_billing_period_end_at is not None
        else None
    )
    if last_processed_item_id is not None:
        details["last_processed_item_id"] = last_processed_item_id
    if last_processed_result_code is not None:
        details["last_processed_result_code"] = last_processed_result_code
    if last_processed_at is not None:
        details["last_processed_at"] = last_processed_at.isoformat()
    request.details = details


def _validate_scope(
    *,
    request_scope: str,
    service_point_id: int | None,
    billing_period_from: datetime | None,
    billing_period_to: datetime | None,
    target_system_code: str,
    payload_format: str,
    requested_by: str,
) -> None:
    if request_scope not in SUPPORTED_BILLING_EXPORT_REQUEST_SCOPES:
        raise BillingExportRequestError(
            "unsupported_scope",
            "Billing export request scope is not supported.",
        )
    if service_point_id is None:
        raise BillingExportRequestError(
            "missing_service_point_id",
            "Billing export requests require a service_point_id.",
        )
    if (
        billing_period_from is None
        or billing_period_to is None
        or _normalize_utc(billing_period_from) >= _normalize_utc(billing_period_to)
    ):
        raise BillingExportRequestError(
            "invalid_billing_period_window",
            "Billing export requests require a valid billing_period_from and billing_period_to window.",
        )
    if target_system_code not in SUPPORTED_BILLING_EXPORT_TARGET_SYSTEM_CODES:
        raise BillingExportRequestError(
            "unsupported_target_system_code",
            "Billing export target_system_code is not supported.",
        )
    if payload_format not in SUPPORTED_BILLING_EXPORT_PAYLOAD_FORMATS:
        raise BillingExportRequestError(
            "unsupported_payload_format",
            "Billing export payload_format is not supported.",
        )
    if not requested_by.strip():
        raise BillingExportRequestError(
            "missing_requested_by",
            "Billing export requests require a non-empty requested_by value.",
        )


def _find_existing_active_request(
    session: Session,
    *,
    request_scope: str,
    service_point_id: int,
    billing_period_from: datetime,
    billing_period_to: datetime,
    target_system_code: str,
    payload_format: str,
) -> BillingExportRequest | None:
    statement = (
        select(BillingExportRequest)
        .where(BillingExportRequest.request_scope == request_scope)
        .where(BillingExportRequest.service_point_id == service_point_id)
        .where(BillingExportRequest.billing_period_from == billing_period_from)
        .where(BillingExportRequest.billing_period_to == billing_period_to)
        .where(BillingExportRequest.target_system_code == target_system_code)
        .where(BillingExportRequest.payload_format == payload_format)
        .where(BillingExportRequest.status.in_(ACTIVE_BILLING_EXPORT_REQUEST_STATUSES))
        .order_by(BillingExportRequest.id.desc())
        .limit(1)
    )
    return session.scalar(statement)


def _build_request_details(
    *,
    request_scope: str,
    service_point: ServicePoint,
    billing_period_from: datetime,
    billing_period_to: datetime,
    target_system_code: str,
    payload_format: str,
) -> dict[str, object]:
    return {
        "request_scope": request_scope,
        "service_point_id": service_point.id,
        "service_point_external_id": service_point.external_id,
        "billing_period_from": billing_period_from.isoformat(),
        "billing_period_to": billing_period_to.isoformat(),
        "target_system_code": target_system_code,
        "payload_format": payload_format,
    }


def _summary_group_key(
    *,
    service_point_id: int,
    billing_period_start_at: datetime,
    billing_period_end_at: datetime,
    currency_code: str | None,
    tariff_plan_code: str | None,
) -> tuple[int, datetime, datetime, str | None, str | None]:
    return (
        service_point_id,
        billing_period_start_at,
        billing_period_end_at,
        currency_code,
        tariff_plan_code,
    )


def _summary_key_from_row(summary_row: InvoiceSummaryRow) -> tuple[int, datetime, datetime, str | None, str | None]:
    return _summary_group_key(
        service_point_id=summary_row.service_point_id,
        billing_period_start_at=summary_row.billing_period_start_at,
        billing_period_end_at=summary_row.billing_period_end_at,
        currency_code=summary_row.currency_code,
        tariff_plan_code=summary_row.tariff_plan_code,
    )


def _summary_key_from_charge_row(charge_row: BillCharge) -> tuple[int, datetime, datetime, str | None, str | None]:
    return _summary_group_key(
        service_point_id=charge_row.service_point_id,
        billing_period_start_at=charge_row.billing_period_start_at,
        billing_period_end_at=charge_row.billing_period_end_at,
        currency_code=charge_row.currency_code,
        tariff_plan_code=charge_row.tariff_plan_code,
    )


def _serialize_invoice_summary(summary_row: InvoiceSummaryRow) -> dict[str, object]:
    return {
        "service_point_id": summary_row.service_point_id,
        "service_point_external_id": summary_row.service_point_external_id,
        "billing_period_start_at": summary_row.billing_period_start_at.isoformat(),
        "billing_period_end_at": summary_row.billing_period_end_at.isoformat(),
        "currency_code": summary_row.currency_code,
        "tariff_plan_code": summary_row.tariff_plan_code,
        "charge_count": summary_row.charge_count,
        "complete_count": summary_row.complete_count,
        "partial_count": summary_row.partial_count,
        "blocked_count": summary_row.blocked_count,
        "subtotal_amount": _serialize_decimal(summary_row.subtotal_amount),
        "summary_status": summary_row.summary_status,
        "export_eligible": summary_row.export_eligible,
        "latest_calculated_at": (
            summary_row.latest_calculated_at.isoformat()
            if summary_row.latest_calculated_at is not None
            else None
        ),
    }


def _serialize_bill_charge_row(charge_row: BillCharge) -> dict[str, object]:
    return {
        "bill_charge_id": charge_row.id,
        "bill_determinant_id": charge_row.bill_determinant_id,
        "charge_type": charge_row.charge_type,
        "billing_period_start_at": charge_row.billing_period_start_at.isoformat(),
        "billing_period_end_at": charge_row.billing_period_end_at.isoformat(),
        "currency_code": charge_row.currency_code,
        "tariff_plan_code": charge_row.tariff_plan_code,
        "tariff_version_code": charge_row.tariff_version_code,
        "quantity_value": _serialize_decimal(charge_row.quantity_value),
        "unit_rate_value": _serialize_decimal(charge_row.unit_rate_value),
        "charge_amount": _serialize_decimal(charge_row.charge_amount),
        "calculation_status": charge_row.calculation_status,
        "quality_summary": charge_row.quality_summary,
        "revision_number": charge_row.revision_number,
        "is_current": charge_row.is_current,
        "calculated_at": charge_row.calculated_at.isoformat(),
    }


def _build_item_payload_snapshot(
    *,
    summary_row: InvoiceSummaryRow,
    source_charge_rows: list[BillCharge],
    request_context_snapshot: dict[str, object],
    skip_reason: str | None,
) -> dict[str, object]:
    return {
        "invoice_summary_snapshot": _serialize_invoice_summary(summary_row),
        "source_bill_charge_rows": [
            _serialize_bill_charge_row(charge_row) for charge_row in source_charge_rows
        ],
        "request_context_snapshot": request_context_snapshot,
        "export_eligibility_snapshot": {
            "export_eligible": summary_row.export_eligible,
            "summary_status": summary_row.summary_status,
            "skip_reason": skip_reason,
        },
    }


def create_billing_export_request(
    session: Session,
    *,
    request_scope: str,
    service_point_id: int | None,
    billing_period_from: datetime | None,
    billing_period_to: datetime | None,
    requested_by: str,
    target_system_code: str = "generic_json",
    payload_format: str = "generic_json",
    operator_memo: str | None = None,
) -> BillingExportRequestCreationResult:
    _validate_scope(
        request_scope=request_scope,
        service_point_id=service_point_id,
        billing_period_from=billing_period_from,
        billing_period_to=billing_period_to,
        target_system_code=target_system_code,
        payload_format=payload_format,
        requested_by=requested_by,
    )

    assert service_point_id is not None
    assert billing_period_from is not None
    assert billing_period_to is not None

    normalized_from = _normalize_utc(billing_period_from)
    normalized_to = _normalize_utc(billing_period_to)

    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        raise BillingExportRequestError(
            "service_point_not_found",
            "The selected service point does not exist.",
        )

    existing_request = _find_existing_active_request(
        session,
        request_scope=request_scope,
        service_point_id=service_point_id,
        billing_period_from=normalized_from,
        billing_period_to=normalized_to,
        target_system_code=target_system_code,
        payload_format=payload_format,
    )
    if existing_request is not None:
        raise BillingExportRequestError(
            "request_already_active",
            "A billing export request for the same service point and period is already queued or processing.",
        )

    summary_filters = InvoiceSummaryFilters(
        service_point_id=service_point_id,
        date_from=normalized_from,
        date_to=normalized_to,
    )
    summary_rows = [
        row
        for row in list_invoice_summaries(session, summary_filters, limit=None)
        if row.billing_period_start_at >= normalized_from and row.billing_period_end_at <= normalized_to
    ]
    if not summary_rows:
        raise BillingExportRequestError(
            "no_invoice_summaries_found",
            "No invoice summaries were found for the selected service point and billing period window.",
        )

    source_charge_rows = [
        row
        for row in list_bill_charges(
            session,
            BillChargeFilters(
                service_point_id=service_point_id,
                date_from=normalized_from,
                date_to=normalized_to,
                include_history=False,
            ),
            limit=None,
        )
        if row.billing_period_start_at >= normalized_from and row.billing_period_end_at <= normalized_to
    ]
    grouped_charge_rows: dict[
        tuple[int, datetime, datetime, str | None, str | None],
        list[BillCharge],
    ] = {}
    for charge_row in source_charge_rows:
        grouped_charge_rows.setdefault(_summary_key_from_charge_row(charge_row), []).append(charge_row)

    request = BillingExportRequest(
        request_scope=request_scope,
        status="queued",
        service_point_id=service_point_id,
        billing_period_from=normalized_from,
        billing_period_to=normalized_to,
        target_system_code=target_system_code,
        payload_format=payload_format,
        requested_by=requested_by.strip(),
        operator_memo=operator_memo,
        item_count=0,
        processed_count=0,
        succeeded_count=0,
        failed_count=0,
        skipped_count=0,
        details=_build_request_details(
            request_scope=request_scope,
            service_point=service_point,
            billing_period_from=normalized_from,
            billing_period_to=normalized_to,
            target_system_code=target_system_code,
            payload_format=payload_format,
        ),
    )
    session.add(request)
    session.flush()

    request_context_snapshot = {
        "request_id": request.id,
        "request_scope": request.request_scope,
        "service_point_id": request.service_point_id,
        "service_point_external_id": service_point.external_id,
        "billing_period_from": normalized_from.isoformat(),
        "billing_period_to": normalized_to.isoformat(),
        "target_system_code": request.target_system_code,
        "payload_format": request.payload_format,
        "requested_by": request.requested_by,
        "requested_at": request.created_at.isoformat(),
    }

    items: list[BillingExportItem] = []
    skipped_summaries: list[dict[str, object]] = []
    eligible_item_count = 0
    for summary_row in summary_rows:
        skip_reason = None if summary_row.export_eligible else "summary_not_exportable"
        if summary_row.export_eligible:
            eligible_item_count += 1
        else:
            skipped_summaries.append(
                {
                    "billing_period_start_at": summary_row.billing_period_start_at.isoformat(),
                    "billing_period_end_at": summary_row.billing_period_end_at.isoformat(),
                    "summary_status": summary_row.summary_status,
                    "tariff_plan_code": summary_row.tariff_plan_code,
                    "currency_code": summary_row.currency_code,
                    "skip_reason": skip_reason,
                }
            )

        items.append(
            BillingExportItem(
                billing_export_request_id=request.id,
                service_point_id=summary_row.service_point_id,
                billing_period_start_at=summary_row.billing_period_start_at,
                billing_period_end_at=summary_row.billing_period_end_at,
                currency_code=summary_row.currency_code,
                tariff_plan_code=summary_row.tariff_plan_code,
                summary_status=summary_row.summary_status,
                status="pending" if summary_row.export_eligible else "skipped",
                result_code=None if summary_row.export_eligible else skip_reason,
                payload_snapshot=_build_item_payload_snapshot(
                    summary_row=summary_row,
                    source_charge_rows=grouped_charge_rows.get(_summary_key_from_row(summary_row), []),
                    request_context_snapshot=request_context_snapshot,
                    skip_reason=skip_reason,
                ),
                details={
                    "invoice_summary_key": {
                        "service_point_id": summary_row.service_point_id,
                        "billing_period_start_at": summary_row.billing_period_start_at.isoformat(),
                        "billing_period_end_at": summary_row.billing_period_end_at.isoformat(),
                        "currency_code": summary_row.currency_code,
                        "tariff_plan_code": summary_row.tariff_plan_code,
                    },
                    "created_at": request.created_at.isoformat(),
                    "skip_reason": skip_reason,
                },
            )
        )

    request.item_count = len(items)
    request.skipped_count = len(items) - eligible_item_count
    request.processed_count = request.skipped_count
    details = dict(request.details or {})
    details["eligible_item_count"] = eligible_item_count
    details["skipped_summaries"] = skipped_summaries
    request.details = details
    _update_request_details(request)

    if eligible_item_count == 0:
        request.status = "completed"
        request.completed_at = _utcnow()
        details = dict(request.details or {})
        details["completion_reason"] = "all_items_skipped"
        request.details = details

    session.add_all(items)
    session.flush()

    record_operational_event(
        session,
        "billing_export_requested",
        occurred_at=request.created_at,
        entity_type="billing_export_request",
        entity_id=request.id,
        details={
            "request_id": request.id,
            "request_scope": request.request_scope,
            "status": request.status,
            "service_point_id": request.service_point_id,
            "billing_period_from": normalized_from.isoformat(),
            "billing_period_to": normalized_to.isoformat(),
            "item_count": request.item_count,
            "processed_count": request.processed_count,
            "succeeded_count": request.succeeded_count,
            "failed_count": request.failed_count,
            "skipped_count": request.skipped_count,
            "target_system_code": request.target_system_code,
            "payload_format": request.payload_format,
        },
        request_id=request.id,
        request_scope=request.request_scope,
        item_count=request.item_count,
        skipped_count=request.skipped_count,
    )
    if request.status == "completed":
        record_operational_event(
            session,
            "billing_export_completed",
            occurred_at=request.completed_at,
            entity_type="billing_export_request",
            entity_id=request.id,
            details={
                "request_id": request.id,
                "request_scope": request.request_scope,
                "status": request.status,
                "item_count": request.item_count,
                "processed_count": request.processed_count,
                "succeeded_count": request.succeeded_count,
                "failed_count": request.failed_count,
                "skipped_count": request.skipped_count,
                "completion_reason": "all_items_skipped",
            },
            request_id=request.id,
            processed_count=request.processed_count,
            succeeded_count=request.succeeded_count,
            failed_count=request.failed_count,
            skipped_count=request.skipped_count,
        )
    session.flush()

    return BillingExportRequestCreationResult(
        request=request,
        created_item_count=len(items),
        eligible_item_count=eligible_item_count,
        skipped_item_count=request.skipped_count,
    )


def cancel_billing_export_request(
    session: Session,
    request_id: int,
    *,
    cancelled_by: str,
    operator_memo: str | None = None,
) -> BillingExportRequest:
    request = session.get(BillingExportRequest, request_id)
    if request is None:
        raise BillingExportRequestError(
            "not_found",
            "The selected billing export request does not exist.",
        )
    if request.status == "cancelled":
        raise BillingExportRequestError(
            "already_cancelled",
            "The selected billing export request is already cancelled.",
        )
    if request.status != "queued":
        raise BillingExportRequestError(
            "request_not_cancellable",
            "Only queued billing export requests can be cancelled.",
        )

    cancelled_at = _utcnow()
    request.status = "cancelled"
    request.completed_at = cancelled_at
    if operator_memo is not None:
        request.operator_memo = operator_memo
    details = dict(request.details or {})
    details["cancelled_by"] = cancelled_by
    details["cancelled_at"] = cancelled_at.isoformat()
    if operator_memo:
        details["cancellation_memo"] = operator_memo
    request.details = details
    _update_request_details(request)

    record_operational_event(
        session,
        "billing_export_cancelled",
        occurred_at=cancelled_at,
        entity_type="billing_export_request",
        entity_id=request.id,
        details={
            "request_id": request.id,
            "status": request.status,
            "item_count": request.item_count,
            "processed_count": request.processed_count,
            "skipped_count": request.skipped_count,
        },
        request_id=request.id,
    )
    session.flush()
    return request
