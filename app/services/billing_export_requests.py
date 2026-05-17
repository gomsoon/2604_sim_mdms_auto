from __future__ import annotations

from copy import deepcopy
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
SUPPORTED_BILLING_EXPORT_RECOVERY_ACTION_CODES = {"rerun", "recreate"}
RETRYABLE_BILLING_EXPORT_ITEM_STATUSES = {"failed", "pending"}


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
    requested_by: str,
    requested_by_user_account_id: int | None,
) -> dict[str, object]:
    return {
        "request_scope": request_scope,
        "service_point_id": service_point.id,
        "service_point_external_id": service_point.external_id,
        "billing_period_from": billing_period_from.isoformat(),
        "billing_period_to": billing_period_to.isoformat(),
        "target_system_code": target_system_code,
        "payload_format": payload_format,
        "requested_by": requested_by,
        "requested_by_user_account_id": requested_by_user_account_id,
    }


def _build_request_context_snapshot(
    *,
    request: BillingExportRequest,
    service_point_external_id: str | None,
    source_request: BillingExportRequest | None = None,
) -> dict[str, object]:
    payload = {
        "request_id": request.id,
        "request_scope": request.request_scope,
        "service_point_id": request.service_point_id,
        "service_point_external_id": service_point_external_id,
        "billing_period_from": (
            request.billing_period_from.isoformat() if request.billing_period_from is not None else None
        ),
        "billing_period_to": (
            request.billing_period_to.isoformat() if request.billing_period_to is not None else None
        ),
        "target_system_code": request.target_system_code,
        "payload_format": request.payload_format,
        "requested_by": request.requested_by,
        "requested_by_user_account_id": request.requested_by_user_account_id,
        "requested_at": request.created_at.isoformat(),
    }
    if source_request is not None:
        payload["source_billing_export_request_id"] = source_request.id
        payload["recovery_action_code"] = request.recovery_action_code
    return payload


def _serialize_source_export_item_snapshot(item: BillingExportItem) -> dict[str, object]:
    return {
        "billing_export_item_id": item.id,
        "billing_export_request_id": item.billing_export_request_id,
        "summary_status": item.summary_status,
        "status": item.status,
        "result_code": item.result_code,
        "billing_period_start_at": item.billing_period_start_at.isoformat(),
        "billing_period_end_at": item.billing_period_end_at.isoformat(),
        "currency_code": item.currency_code,
        "tariff_plan_code": item.tariff_plan_code,
    }


def _build_recovery_lineage_snapshot(
    *,
    source_request: BillingExportRequest,
    source_item: BillingExportItem,
    recovery_action_code: str,
) -> dict[str, object]:
    return {
        "source_billing_export_request_id": source_request.id,
        "source_billing_export_item_id": source_item.id,
        "source_request_status": source_request.status,
        "source_item_status": source_item.status,
        "recovery_action_code": recovery_action_code,
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


def _record_billing_export_requested_event(
    session: Session,
    *,
    request: BillingExportRequest,
) -> None:
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
            "requested_by": request.requested_by,
            "requested_by_user_account_id": request.requested_by_user_account_id,
            "service_point_id": request.service_point_id,
            "billing_period_from": (
                request.billing_period_from.isoformat()
                if request.billing_period_from is not None
                else None
            ),
            "billing_period_to": (
                request.billing_period_to.isoformat() if request.billing_period_to is not None else None
            ),
            "item_count": request.item_count,
            "processed_count": request.processed_count,
            "succeeded_count": request.succeeded_count,
            "failed_count": request.failed_count,
            "skipped_count": request.skipped_count,
            "target_system_code": request.target_system_code,
            "payload_format": request.payload_format,
            "source_billing_export_request_id": request.source_billing_export_request_id,
            "recovery_action_code": request.recovery_action_code,
        },
        request_id=request.id,
        request_scope=request.request_scope,
        item_count=request.item_count,
        skipped_count=request.skipped_count,
    )


def _record_billing_export_completed_event(
    session: Session,
    *,
    request: BillingExportRequest,
    completion_reason: str,
) -> None:
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
            "requested_by": request.requested_by,
            "requested_by_user_account_id": request.requested_by_user_account_id,
            "item_count": request.item_count,
            "processed_count": request.processed_count,
            "succeeded_count": request.succeeded_count,
            "failed_count": request.failed_count,
            "skipped_count": request.skipped_count,
            "completion_reason": completion_reason,
            "source_billing_export_request_id": request.source_billing_export_request_id,
            "recovery_action_code": request.recovery_action_code,
        },
        request_id=request.id,
        processed_count=request.processed_count,
        succeeded_count=request.succeeded_count,
        failed_count=request.failed_count,
        skipped_count=request.skipped_count,
    )


def _get_source_billing_export_request(
    session: Session,
    *,
    request_id: int,
    recovery_action_code: str,
) -> BillingExportRequest:
    if recovery_action_code not in SUPPORTED_BILLING_EXPORT_RECOVERY_ACTION_CODES:
        raise BillingExportRequestError(
            "unsupported_recovery_action",
            "Billing export recovery action is not supported.",
        )

    request = session.get(BillingExportRequest, request_id)
    if request is None:
        raise BillingExportRequestError(
            "not_found",
            "The selected billing export request does not exist.",
        )
    if request.status != "failed":
        raise BillingExportRequestError(
            "request_not_failed",
            "Only failed billing export requests can be rerun or recreated.",
        )
    return request


def _find_active_recovery_request(
    session: Session,
    *,
    source_billing_export_request_id: int,
    recovery_action_code: str,
) -> BillingExportRequest | None:
    statement = (
        select(BillingExportRequest)
        .where(BillingExportRequest.source_billing_export_request_id == source_billing_export_request_id)
        .where(BillingExportRequest.recovery_action_code == recovery_action_code)
        .where(BillingExportRequest.status.in_(ACTIVE_BILLING_EXPORT_REQUEST_STATUSES))
        .order_by(BillingExportRequest.id.desc())
        .limit(1)
    )
    return session.scalar(statement)


def _get_retryable_source_items(
    session: Session,
    *,
    source_request_id: int,
) -> list[BillingExportItem]:
    rows = session.scalars(
        select(BillingExportItem)
        .where(BillingExportItem.billing_export_request_id == source_request_id)
        .where(BillingExportItem.status.in_(RETRYABLE_BILLING_EXPORT_ITEM_STATUSES))
        .order_by(BillingExportItem.billing_period_start_at.asc(), BillingExportItem.id.asc())
    ).all()
    if not rows:
        raise BillingExportRequestError(
            "no_retryable_items",
            "The selected billing export request does not have failed or pending items to recover.",
        )
    return rows


def _ensure_recovery_request_can_be_created(
    session: Session,
    *,
    source_request: BillingExportRequest,
    recovery_action_code: str,
) -> None:
    active_recovery = _find_active_recovery_request(
        session,
        source_billing_export_request_id=source_request.id,
        recovery_action_code=recovery_action_code,
    )
    if active_recovery is not None:
        raise BillingExportRequestError(
            "active_recovery_exists",
            "An active recovery request already exists for the selected billing export request.",
        )

    assert source_request.service_point_id is not None
    assert source_request.billing_period_from is not None
    assert source_request.billing_period_to is not None

    existing_request = _find_existing_active_request(
        session,
        request_scope=source_request.request_scope,
        service_point_id=source_request.service_point_id,
        billing_period_from=source_request.billing_period_from,
        billing_period_to=source_request.billing_period_to,
        target_system_code=source_request.target_system_code,
        payload_format=source_request.payload_format,
    )
    if existing_request is not None:
        raise BillingExportRequestError(
            "request_already_active",
            "A billing export request for the same service point and period is already queued or processing.",
        )


def _create_recovery_request(
    session: Session,
    *,
    source_request: BillingExportRequest,
    requested_by: str,
    requested_by_user_account_id: int | None,
    recovery_action_code: str,
    operator_memo: str | None,
) -> tuple[BillingExportRequest, ServicePoint]:
    assert source_request.service_point_id is not None
    assert source_request.billing_period_from is not None
    assert source_request.billing_period_to is not None

    service_point = session.get(ServicePoint, source_request.service_point_id)
    if service_point is None:
        raise BillingExportRequestError(
            "service_point_not_found",
            "The selected service point does not exist.",
        )

    request = BillingExportRequest(
        request_scope=source_request.request_scope,
        status="queued",
        source_billing_export_request_id=source_request.id,
        recovery_action_code=recovery_action_code,
        service_point_id=source_request.service_point_id,
        billing_period_from=source_request.billing_period_from,
        billing_period_to=source_request.billing_period_to,
        target_system_code=source_request.target_system_code,
        payload_format=source_request.payload_format,
        requested_by=requested_by.strip(),
        requested_by_user_account_id=requested_by_user_account_id,
        operator_memo=operator_memo,
        item_count=0,
        processed_count=0,
        succeeded_count=0,
        failed_count=0,
        skipped_count=0,
        details={
            **_build_request_details(
                request_scope=source_request.request_scope,
                service_point=service_point,
                billing_period_from=source_request.billing_period_from,
                billing_period_to=source_request.billing_period_to,
                target_system_code=source_request.target_system_code,
                payload_format=source_request.payload_format,
                requested_by=requested_by.strip(),
                requested_by_user_account_id=requested_by_user_account_id,
            ),
            "source_billing_export_request_id": source_request.id,
            "recovery_action_code": recovery_action_code,
        },
    )
    session.add(request)
    session.flush()
    return request, service_point


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
    requested_by_user_account_id: int | None = None,
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
        requested_by_user_account_id=requested_by_user_account_id,
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
            requested_by=requested_by.strip(),
            requested_by_user_account_id=requested_by_user_account_id,
        ),
    )
    session.add(request)
    session.flush()

    request_context_snapshot = _build_request_context_snapshot(
        request=request,
        service_point_external_id=service_point.external_id,
    )

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

    _record_billing_export_requested_event(session, request=request)
    if request.status == "completed":
        _record_billing_export_completed_event(
            session,
            request=request,
            completion_reason="all_items_skipped",
        )
    session.flush()

    return BillingExportRequestCreationResult(
        request=request,
        created_item_count=len(items),
        eligible_item_count=eligible_item_count,
        skipped_item_count=request.skipped_count,
    )


def rerun_billing_export_request(
    session: Session,
    request_id: int,
    *,
    requested_by: str,
    requested_by_user_account_id: int | None = None,
    operator_memo: str | None = None,
) -> BillingExportRequestCreationResult:
    if not requested_by.strip():
        raise BillingExportRequestError(
            "missing_requested_by",
            "Billing export requests require a non-empty requested_by value.",
        )

    source_request = _get_source_billing_export_request(
        session,
        request_id=request_id,
        recovery_action_code="rerun",
    )
    _ensure_recovery_request_can_be_created(
        session,
        source_request=source_request,
        recovery_action_code="rerun",
    )
    source_items = _get_retryable_source_items(session, source_request_id=source_request.id)
    request, service_point = _create_recovery_request(
        session,
        source_request=source_request,
        requested_by=requested_by,
        requested_by_user_account_id=requested_by_user_account_id,
        recovery_action_code="rerun",
        operator_memo=operator_memo,
    )

    request_context_snapshot = _build_request_context_snapshot(
        request=request,
        service_point_external_id=service_point.external_id,
        source_request=source_request,
    )

    items: list[BillingExportItem] = []
    source_item_ids: list[int] = []
    for source_item in source_items:
        source_item_ids.append(source_item.id)
        payload_snapshot = deepcopy(source_item.payload_snapshot or {})
        original_request_context_snapshot = payload_snapshot.get("request_context_snapshot")
        payload_snapshot.pop("worker_result", None)
        payload_snapshot["request_context_snapshot"] = request_context_snapshot
        payload_snapshot["recovery_lineage_snapshot"] = _build_recovery_lineage_snapshot(
            source_request=source_request,
            source_item=source_item,
            recovery_action_code="rerun",
        )
        if original_request_context_snapshot is not None:
            payload_snapshot["source_request_context_snapshot"] = original_request_context_snapshot
        payload_snapshot["source_export_item_snapshot"] = _serialize_source_export_item_snapshot(
            source_item
        )

        items.append(
            BillingExportItem(
                billing_export_request_id=request.id,
                source_billing_export_item_id=source_item.id,
                service_point_id=source_item.service_point_id,
                billing_period_start_at=source_item.billing_period_start_at,
                billing_period_end_at=source_item.billing_period_end_at,
                currency_code=source_item.currency_code,
                tariff_plan_code=source_item.tariff_plan_code,
                summary_status=source_item.summary_status,
                status="pending",
                result_code=None,
                payload_snapshot=payload_snapshot,
                details={
                    "created_at": request.created_at.isoformat(),
                    "invoice_summary_key": dict(source_item.details or {}).get("invoice_summary_key"),
                    "source_billing_export_request_id": source_request.id,
                    "source_billing_export_item_id": source_item.id,
                    "recovery_action_code": "rerun",
                },
            )
        )

    request.item_count = len(items)
    request.processed_count = 0
    request.succeeded_count = 0
    request.failed_count = 0
    request.skipped_count = 0
    request.details = {
        **dict(request.details or {}),
        "eligible_item_count": len(items),
        "skipped_summaries": [],
        "source_item_ids": source_item_ids,
    }
    _update_request_details(request)

    session.add_all(items)
    session.flush()
    _record_billing_export_requested_event(session, request=request)
    session.flush()

    return BillingExportRequestCreationResult(
        request=request,
        created_item_count=len(items),
        eligible_item_count=len(items),
        skipped_item_count=0,
    )


def recreate_billing_export_request(
    session: Session,
    request_id: int,
    *,
    requested_by: str,
    requested_by_user_account_id: int | None = None,
    operator_memo: str | None = None,
) -> BillingExportRequestCreationResult:
    if not requested_by.strip():
        raise BillingExportRequestError(
            "missing_requested_by",
            "Billing export requests require a non-empty requested_by value.",
        )

    source_request = _get_source_billing_export_request(
        session,
        request_id=request_id,
        recovery_action_code="recreate",
    )
    _ensure_recovery_request_can_be_created(
        session,
        source_request=source_request,
        recovery_action_code="recreate",
    )
    source_items = _get_retryable_source_items(session, source_request_id=source_request.id)
    request, service_point = _create_recovery_request(
        session,
        source_request=source_request,
        requested_by=requested_by,
        requested_by_user_account_id=requested_by_user_account_id,
        recovery_action_code="recreate",
        operator_memo=operator_memo,
    )

    assert source_request.service_point_id is not None
    assert source_request.billing_period_from is not None
    assert source_request.billing_period_to is not None

    request_context_snapshot = _build_request_context_snapshot(
        request=request,
        service_point_external_id=service_point.external_id,
        source_request=source_request,
    )

    summary_rows = [
        row
        for row in list_invoice_summaries(
            session,
            InvoiceSummaryFilters(
                service_point_id=source_request.service_point_id,
                date_from=source_request.billing_period_from,
                date_to=source_request.billing_period_to,
            ),
            limit=None,
        )
        if row.billing_period_start_at >= source_request.billing_period_from
        and row.billing_period_end_at <= source_request.billing_period_to
    ]
    summary_by_key = {_summary_key_from_row(row): row for row in summary_rows}

    source_charge_rows = [
        row
        for row in list_bill_charges(
            session,
            BillChargeFilters(
                service_point_id=source_request.service_point_id,
                date_from=source_request.billing_period_from,
                date_to=source_request.billing_period_to,
                include_history=False,
            ),
            limit=None,
        )
        if row.billing_period_start_at >= source_request.billing_period_from
        and row.billing_period_end_at <= source_request.billing_period_to
    ]
    grouped_charge_rows: dict[
        tuple[int, datetime, datetime, str | None, str | None],
        list[BillCharge],
    ] = {}
    for charge_row in source_charge_rows:
        grouped_charge_rows.setdefault(_summary_key_from_charge_row(charge_row), []).append(charge_row)

    items: list[BillingExportItem] = []
    source_item_ids: list[int] = []
    skipped_summaries: list[dict[str, object]] = []
    eligible_item_count = 0

    for source_item in source_items:
        source_item_ids.append(source_item.id)
        summary_key = _summary_group_key(
            service_point_id=source_item.service_point_id,
            billing_period_start_at=source_item.billing_period_start_at,
            billing_period_end_at=source_item.billing_period_end_at,
            currency_code=source_item.currency_code,
            tariff_plan_code=source_item.tariff_plan_code,
        )
        summary_row = summary_by_key.get(summary_key)
        skip_reason = None
        item_status = "pending"
        result_code = None
        payload_snapshot: dict[str, object]
        summary_status = source_item.summary_status

        if summary_row is None:
            item_status = "skipped"
            result_code = "no_current_invoice_summary"
            skip_reason = result_code
            skipped_summaries.append(
                {
                    "billing_period_start_at": source_item.billing_period_start_at.isoformat(),
                    "billing_period_end_at": source_item.billing_period_end_at.isoformat(),
                    "summary_status": source_item.summary_status,
                    "tariff_plan_code": source_item.tariff_plan_code,
                    "currency_code": source_item.currency_code,
                    "skip_reason": skip_reason,
                }
            )
            payload_snapshot = {
                "invoice_summary_snapshot": None,
                "source_bill_charge_rows": [],
                "request_context_snapshot": request_context_snapshot,
                "recovery_lineage_snapshot": _build_recovery_lineage_snapshot(
                    source_request=source_request,
                    source_item=source_item,
                    recovery_action_code="recreate",
                ),
                "source_export_item_snapshot": _serialize_source_export_item_snapshot(source_item),
                "export_eligibility_snapshot": {
                    "export_eligible": False,
                    "summary_status": None,
                    "skip_reason": skip_reason,
                },
            }
        else:
            summary_status = summary_row.summary_status
            if summary_row.export_eligible:
                eligible_item_count += 1
            else:
                item_status = "skipped"
                result_code = "summary_not_exportable"
                skip_reason = result_code
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
            payload_snapshot = {
                **_build_item_payload_snapshot(
                    summary_row=summary_row,
                    source_charge_rows=grouped_charge_rows.get(summary_key, []),
                    request_context_snapshot=request_context_snapshot,
                    skip_reason=skip_reason,
                ),
                "recovery_lineage_snapshot": _build_recovery_lineage_snapshot(
                    source_request=source_request,
                    source_item=source_item,
                    recovery_action_code="recreate",
                ),
                "source_export_item_snapshot": _serialize_source_export_item_snapshot(source_item),
            }

        items.append(
            BillingExportItem(
                billing_export_request_id=request.id,
                source_billing_export_item_id=source_item.id,
                service_point_id=source_item.service_point_id,
                billing_period_start_at=source_item.billing_period_start_at,
                billing_period_end_at=source_item.billing_period_end_at,
                currency_code=source_item.currency_code,
                tariff_plan_code=source_item.tariff_plan_code,
                summary_status=summary_status,
                status=item_status,
                result_code=result_code,
                payload_snapshot=payload_snapshot,
                details={
                    "created_at": request.created_at.isoformat(),
                    "invoice_summary_key": dict(source_item.details or {}).get("invoice_summary_key"),
                    "skip_reason": skip_reason,
                    "source_billing_export_request_id": source_request.id,
                    "source_billing_export_item_id": source_item.id,
                    "recovery_action_code": "recreate",
                },
            )
        )

    request.item_count = len(items)
    request.skipped_count = len(items) - eligible_item_count
    request.processed_count = request.skipped_count
    request.succeeded_count = 0
    request.failed_count = 0
    request.details = {
        **dict(request.details or {}),
        "eligible_item_count": eligible_item_count,
        "skipped_summaries": skipped_summaries,
        "source_item_ids": source_item_ids,
    }
    _update_request_details(request)

    if eligible_item_count == 0:
        request.status = "completed"
        request.completed_at = _utcnow()
        request.details = {
            **dict(request.details or {}),
            "completion_reason": "all_items_skipped",
        }

    session.add_all(items)
    session.flush()
    _record_billing_export_requested_event(session, request=request)
    if request.status == "completed":
        _record_billing_export_completed_event(
            session,
            request=request,
            completion_reason="all_items_skipped",
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
    cancelled_by_user_account_id: int | None = None,
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
    request.cancelled_by = cancelled_by
    request.cancelled_by_user_account_id = cancelled_by_user_account_id
    request.cancelled_at = cancelled_at
    request.completed_at = cancelled_at
    if operator_memo is not None:
        request.operator_memo = operator_memo
    details = dict(request.details or {})
    details["cancelled_by"] = cancelled_by
    details["cancelled_by_user_account_id"] = cancelled_by_user_account_id
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
            "cancelled_by": request.cancelled_by,
            "cancelled_by_user_account_id": request.cancelled_by_user_account_id,
            "cancelled_at": request.cancelled_at.isoformat()
            if request.cancelled_at is not None
            else None,
            "item_count": request.item_count,
            "processed_count": request.processed_count,
            "skipped_count": request.skipped_count,
        },
        request_id=request.id,
    )
    session.flush()
    return request
