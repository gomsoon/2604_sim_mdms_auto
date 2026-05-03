from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ServicePoint, ServicePointBillingContext
from app.services.master_data import MasterDataValidationError


VALID_BILLING_CYCLE_MODES = {"calendar_month", "anchored_month"}


@dataclass(slots=True)
class BillingContextPayload:
    service_point: ServicePoint
    timezone_name: str
    billing_cycle_mode: str
    billing_cycle_anchor_day: int | None
    currency_code: str | None
    effective_from: datetime
    effective_to: datetime | None
    source_system: str
    source_reference: str | None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def _load_service_point(session: Session, service_point_id: int | str | None) -> ServicePoint:
    if service_point_id in (None, ""):
        raise MasterDataValidationError(
            "missing_service_point_id", "Service point selection is required."
        )

    service_point = session.get(ServicePoint, int(service_point_id))
    if service_point is None:
        raise MasterDataValidationError(
            "service_point_not_found", "The selected service point does not exist."
        )
    return service_point


def _validate_timezone_name(value: str | None) -> str:
    timezone_name = _normalize_text(value)
    if timezone_name is None:
        raise MasterDataValidationError(
            "missing_timezone_name", "Billing timezone is required."
        )

    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise MasterDataValidationError(
            "invalid_timezone_name", "Billing timezone must be a valid IANA timezone name."
        ) from exc

    return timezone_name


def _validate_billing_cycle_mode(value: str | None) -> str:
    normalized = (_normalize_text(value) or "").lower()
    if not normalized:
        raise MasterDataValidationError(
            "missing_billing_cycle_mode", "Billing cycle mode is required."
        )
    if normalized not in VALID_BILLING_CYCLE_MODES:
        raise MasterDataValidationError(
            "invalid_billing_cycle_mode",
            "Billing cycle mode must be calendar_month or anchored_month.",
        )
    return normalized


def _validate_anchor_day(value: int | str | None, *, billing_cycle_mode: str) -> int | None:
    if billing_cycle_mode == "calendar_month":
        return None

    if value in (None, ""):
        raise MasterDataValidationError(
            "missing_billing_cycle_anchor_day",
            "Billing cycle anchor day is required for anchored month mode.",
        )

    try:
        anchor_day = int(value)
    except (TypeError, ValueError) as exc:
        raise MasterDataValidationError(
            "invalid_billing_cycle_anchor_day",
            "Billing cycle anchor day must be an integer between 1 and 28.",
        ) from exc

    if anchor_day < 1 or anchor_day > 28:
        raise MasterDataValidationError(
            "invalid_billing_cycle_anchor_day",
            "Billing cycle anchor day must be between 1 and 28.",
        )

    return anchor_day


def _parse_effective_datetime(
    value: str | datetime | None,
    *,
    timezone_name: str,
    required: bool,
    missing_error_code: str,
    missing_fallback_message: str,
    invalid_error_code: str,
    invalid_fallback_message: str,
) -> datetime | None:
    if value in (None, ""):
        if required:
            raise MasterDataValidationError(missing_error_code, missing_fallback_message)
        return None

    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise MasterDataValidationError(invalid_error_code, invalid_fallback_message) from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
    return parsed.astimezone(timezone.utc)


def _build_payload(
    session: Session,
    *,
    service_point_id: int | str | None,
    timezone_name: str | None,
    billing_cycle_mode: str | None,
    billing_cycle_anchor_day: int | str | None,
    currency_code: str | None,
    effective_from: str | datetime | None,
    effective_to: str | datetime | None,
    source_system: str | None,
    source_reference: str | None,
) -> BillingContextPayload:
    service_point = _load_service_point(session, service_point_id)
    normalized_timezone_name = _validate_timezone_name(timezone_name)
    normalized_cycle_mode = _validate_billing_cycle_mode(billing_cycle_mode)
    normalized_anchor_day = _validate_anchor_day(
        billing_cycle_anchor_day,
        billing_cycle_mode=normalized_cycle_mode,
    )
    normalized_effective_from = _parse_effective_datetime(
        effective_from,
        timezone_name=normalized_timezone_name,
        required=True,
        missing_error_code="missing_effective_from",
        missing_fallback_message="Effective from time is required.",
        invalid_error_code="invalid_effective_from",
        invalid_fallback_message="Effective from time must be a valid datetime.",
    )
    normalized_effective_to = _parse_effective_datetime(
        effective_to,
        timezone_name=normalized_timezone_name,
        required=False,
        missing_error_code="missing_effective_to",
        missing_fallback_message="Effective to time is required.",
        invalid_error_code="invalid_effective_to",
        invalid_fallback_message="Effective to time must be a valid datetime.",
    )

    assert normalized_effective_from is not None
    if (
        normalized_effective_to is not None
        and normalized_effective_to <= normalized_effective_from
    ):
        raise MasterDataValidationError(
            "effective_to_before_effective_from",
            "Effective to time must be later than effective from time.",
        )

    return BillingContextPayload(
        service_point=service_point,
        timezone_name=normalized_timezone_name,
        billing_cycle_mode=normalized_cycle_mode,
        billing_cycle_anchor_day=normalized_anchor_day,
        currency_code=_normalize_text(currency_code),
        effective_from=normalized_effective_from,
        effective_to=normalized_effective_to,
        source_system=_normalize_text(source_system) or "manual",
        source_reference=_normalize_text(source_reference),
    )


def _windows_overlap(
    left_start: datetime,
    left_end: datetime | None,
    right_start: datetime,
    right_end: datetime | None,
) -> bool:
    left_end_value = left_end or datetime.max.replace(tzinfo=timezone.utc)
    right_end_value = right_end or datetime.max.replace(tzinfo=timezone.utc)
    return left_start < right_end_value and right_start < left_end_value


def _ensure_no_overlapping_context(
    session: Session,
    *,
    service_point_id: int,
    effective_from: datetime,
    effective_to: datetime | None,
    exclude_id: int | None = None,
) -> None:
    rows = session.scalars(
        select(ServicePointBillingContext).where(
            ServicePointBillingContext.service_point_id == service_point_id
        )
    ).all()

    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        if _windows_overlap(row.effective_from, row.effective_to, effective_from, effective_to):
            raise MasterDataValidationError(
                "overlapping_billing_context",
                "Billing context periods must not overlap for the same service point.",
            )


def _close_existing_current_context(
    session: Session,
    *,
    service_point_id: int,
    new_effective_from: datetime,
) -> ServicePointBillingContext | None:
    current_row = session.scalar(
        select(ServicePointBillingContext)
        .where(
            ServicePointBillingContext.service_point_id == service_point_id,
            ServicePointBillingContext.is_current.is_(True),
        )
        .order_by(ServicePointBillingContext.id.desc())
        .limit(1)
    )
    if current_row is None:
        return None

    if new_effective_from <= current_row.effective_from:
        raise MasterDataValidationError(
            "overlapping_billing_context",
            "A new current billing context must start after the existing current context.",
        )

    current_row.is_current = False
    if current_row.effective_to is None or current_row.effective_to > new_effective_from:
        current_row.effective_to = new_effective_from
    session.flush()
    return current_row


def create_billing_context(
    session: Session,
    *,
    service_point_id: int | str | None,
    timezone_name: str | None,
    billing_cycle_mode: str | None,
    billing_cycle_anchor_day: int | str | None,
    currency_code: str | None,
    effective_from: str | datetime | None,
    effective_to: str | datetime | None,
    source_system: str | None,
    source_reference: str | None,
) -> ServicePointBillingContext:
    payload = _build_payload(
        session,
        service_point_id=service_point_id,
        timezone_name=timezone_name,
        billing_cycle_mode=billing_cycle_mode,
        billing_cycle_anchor_day=billing_cycle_anchor_day,
        currency_code=currency_code,
        effective_from=effective_from,
        effective_to=effective_to,
        source_system=source_system,
        source_reference=source_reference,
    )

    _close_existing_current_context(
        session,
        service_point_id=payload.service_point.id,
        new_effective_from=payload.effective_from,
    )
    _ensure_no_overlapping_context(
        session,
        service_point_id=payload.service_point.id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )

    row = ServicePointBillingContext(
        service_point_id=payload.service_point.id,
        timezone_name=payload.timezone_name,
        billing_cycle_mode=payload.billing_cycle_mode,
        billing_cycle_anchor_day=payload.billing_cycle_anchor_day,
        currency_code=payload.currency_code,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_current=True,
        source_system=payload.source_system,
        source_reference=payload.source_reference,
        details={},
    )
    session.add(row)
    session.flush()
    return row


def update_billing_context(
    session: Session,
    billing_context: ServicePointBillingContext,
    *,
    timezone_name: str | None,
    billing_cycle_mode: str | None,
    billing_cycle_anchor_day: int | str | None,
    currency_code: str | None,
    effective_from: str | datetime | None,
    effective_to: str | datetime | None,
    source_system: str | None,
    source_reference: str | None,
) -> ServicePointBillingContext:
    payload = _build_payload(
        session,
        service_point_id=billing_context.service_point_id,
        timezone_name=timezone_name,
        billing_cycle_mode=billing_cycle_mode,
        billing_cycle_anchor_day=billing_cycle_anchor_day,
        currency_code=currency_code,
        effective_from=effective_from,
        effective_to=effective_to,
        source_system=source_system,
        source_reference=source_reference,
    )

    _ensure_no_overlapping_context(
        session,
        service_point_id=billing_context.service_point_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        exclude_id=billing_context.id,
    )

    billing_context.timezone_name = payload.timezone_name
    billing_context.billing_cycle_mode = payload.billing_cycle_mode
    billing_context.billing_cycle_anchor_day = payload.billing_cycle_anchor_day
    billing_context.currency_code = payload.currency_code
    billing_context.effective_from = payload.effective_from
    billing_context.effective_to = payload.effective_to
    billing_context.source_system = payload.source_system
    billing_context.source_reference = payload.source_reference
    session.flush()
    return billing_context
