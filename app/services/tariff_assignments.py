from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ServicePoint, ServicePointTariffAssignment
from app.services.master_data import MasterDataValidationError


@dataclass(slots=True)
class TariffAssignmentPayload:
    service_point: ServicePoint
    tariff_plan_code: str
    tariff_version_code: str | None
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


def _require_tariff_plan_code(value: str | None) -> str:
    tariff_plan_code = _normalize_text(value)
    if tariff_plan_code is None:
        raise MasterDataValidationError(
            "missing_tariff_plan_code", "Tariff plan code is required."
        )
    return tariff_plan_code


def _parse_effective_datetime(
    value: str | datetime | None,
    *,
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
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _build_payload(
    session: Session,
    *,
    service_point_id: int | str | None,
    tariff_plan_code: str | None,
    tariff_version_code: str | None,
    effective_from: str | datetime | None,
    effective_to: str | datetime | None,
    source_system: str | None,
    source_reference: str | None,
) -> TariffAssignmentPayload:
    service_point = _load_service_point(session, service_point_id)
    normalized_tariff_plan_code = _require_tariff_plan_code(tariff_plan_code)
    normalized_effective_from = _parse_effective_datetime(
        effective_from,
        required=True,
        missing_error_code="missing_effective_from",
        missing_fallback_message="Effective from time is required.",
        invalid_error_code="invalid_effective_from",
        invalid_fallback_message="Effective from time must be a valid datetime.",
    )
    normalized_effective_to = _parse_effective_datetime(
        effective_to,
        required=False,
        missing_error_code="missing_effective_to",
        missing_fallback_message="Effective to time is required.",
        invalid_error_code="invalid_effective_to",
        invalid_fallback_message="Effective to time must be a valid datetime.",
    )

    assert normalized_effective_from is not None
    if normalized_effective_to is not None and normalized_effective_to <= normalized_effective_from:
        raise MasterDataValidationError(
            "effective_to_before_effective_from",
            "Effective to time must be later than effective from time.",
        )

    return TariffAssignmentPayload(
        service_point=service_point,
        tariff_plan_code=normalized_tariff_plan_code,
        tariff_version_code=_normalize_text(tariff_version_code),
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


def _ensure_no_overlapping_assignment(
    session: Session,
    *,
    service_point_id: int,
    effective_from: datetime,
    effective_to: datetime | None,
    exclude_id: int | None = None,
) -> None:
    rows = session.scalars(
        select(ServicePointTariffAssignment).where(
            ServicePointTariffAssignment.service_point_id == service_point_id
        )
    ).all()

    for row in rows:
        if exclude_id is not None and row.id == exclude_id:
            continue
        if _windows_overlap(row.effective_from, row.effective_to, effective_from, effective_to):
            raise MasterDataValidationError(
                "overlapping_tariff_assignment",
                "Tariff assignment periods must not overlap for the same service point.",
            )


def _close_existing_current_assignment(
    session: Session,
    *,
    service_point_id: int,
    new_effective_from: datetime,
    updated_by_user_account_id: int | None = None,
) -> ServicePointTariffAssignment | None:
    current_row = session.scalar(
        select(ServicePointTariffAssignment)
        .where(
            ServicePointTariffAssignment.service_point_id == service_point_id,
            ServicePointTariffAssignment.is_current.is_(True),
        )
        .order_by(ServicePointTariffAssignment.id.desc())
        .limit(1)
    )
    if current_row is None:
        return None

    if new_effective_from <= current_row.effective_from:
        raise MasterDataValidationError(
            "overlapping_tariff_assignment",
            "A new current tariff assignment must start after the existing current assignment.",
        )

    current_row.is_current = False
    if current_row.effective_to is None or current_row.effective_to > new_effective_from:
        current_row.effective_to = new_effective_from
    current_row.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return current_row


def create_tariff_assignment(
    session: Session,
    *,
    service_point_id: int | str | None,
    tariff_plan_code: str | None,
    tariff_version_code: str | None,
    effective_from: str | datetime | None,
    effective_to: str | datetime | None,
    source_system: str | None,
    source_reference: str | None,
    created_by_user_account_id: int | None = None,
) -> ServicePointTariffAssignment:
    payload = _build_payload(
        session,
        service_point_id=service_point_id,
        tariff_plan_code=tariff_plan_code,
        tariff_version_code=tariff_version_code,
        effective_from=effective_from,
        effective_to=effective_to,
        source_system=source_system,
        source_reference=source_reference,
    )

    _close_existing_current_assignment(
        session,
        service_point_id=payload.service_point.id,
        new_effective_from=payload.effective_from,
        updated_by_user_account_id=created_by_user_account_id,
    )
    _ensure_no_overlapping_assignment(
        session,
        service_point_id=payload.service_point.id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
    )

    row = ServicePointTariffAssignment(
        service_point_id=payload.service_point.id,
        tariff_plan_code=payload.tariff_plan_code,
        tariff_version_code=payload.tariff_version_code,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        is_current=True,
        source_system=payload.source_system,
        source_reference=payload.source_reference,
        details={},
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(row)
    session.flush()
    return row


def update_tariff_assignment(
    session: Session,
    tariff_assignment: ServicePointTariffAssignment,
    *,
    tariff_plan_code: str | None,
    tariff_version_code: str | None,
    effective_from: str | datetime | None,
    effective_to: str | datetime | None,
    source_system: str | None,
    source_reference: str | None,
    updated_by_user_account_id: int | None = None,
) -> ServicePointTariffAssignment:
    payload = _build_payload(
        session,
        service_point_id=tariff_assignment.service_point_id,
        tariff_plan_code=tariff_plan_code,
        tariff_version_code=tariff_version_code,
        effective_from=effective_from,
        effective_to=effective_to,
        source_system=source_system,
        source_reference=source_reference,
    )

    _ensure_no_overlapping_assignment(
        session,
        service_point_id=tariff_assignment.service_point_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        exclude_id=tariff_assignment.id,
    )

    tariff_assignment.tariff_plan_code = payload.tariff_plan_code
    tariff_assignment.tariff_version_code = payload.tariff_version_code
    tariff_assignment.effective_from = payload.effective_from
    tariff_assignment.effective_to = payload.effective_to
    tariff_assignment.source_system = payload.source_system
    tariff_assignment.source_reference = payload.source_reference
    tariff_assignment.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return tariff_assignment


def find_applicable_tariff_assignment(
    session: Session,
    *,
    service_point_id: int,
    target_at: datetime,
) -> ServicePointTariffAssignment | None:
    normalized_target = (
        target_at.replace(tzinfo=timezone.utc)
        if target_at.tzinfo is None
        else target_at.astimezone(timezone.utc)
    )

    return session.scalar(
        select(ServicePointTariffAssignment)
        .where(ServicePointTariffAssignment.service_point_id == service_point_id)
        .where(ServicePointTariffAssignment.effective_from <= normalized_target)
        .where(
            (ServicePointTariffAssignment.effective_to.is_(None))
            | (normalized_target < ServicePointTariffAssignment.effective_to)
        )
        .order_by(
            ServicePointTariffAssignment.effective_from.desc(),
            ServicePointTariffAssignment.id.desc(),
        )
        .limit(1)
    )
