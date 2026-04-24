from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import HesMeterReference, HesSystem


@dataclass(slots=True)
class HesMeterReferenceValidationError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


def _normalize_required_text(
    value: str | None, *, error_code: str, fallback_message: str
) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HesMeterReferenceValidationError(error_code, fallback_message)
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_optional_interval(value: int | str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HesMeterReferenceValidationError(
            "invalid_lp_interval_minutes",
            "LP interval must be a positive integer when provided.",
        ) from exc
    if parsed <= 0:
        raise HesMeterReferenceValidationError(
            "invalid_lp_interval_minutes",
            "LP interval must be a positive integer when provided.",
        )
    return parsed


def _load_hes_system(session: Session, hes_system_id: int) -> HesSystem:
    hes_system = session.get(HesSystem, hes_system_id)
    if hes_system is None:
        raise HesMeterReferenceValidationError(
            "hes_system_not_found",
            "The selected HES system does not exist.",
        )
    return hes_system


def _ensure_unique_source_meter_key(
    session: Session,
    *,
    hes_system_id: int,
    source_meter_key: str | None,
    exclude_id: int | None = None,
) -> None:
    if source_meter_key is None:
        return

    statement = select(HesMeterReference).where(
        HesMeterReference.hes_system_id == hes_system_id,
        HesMeterReference.source_meter_key == source_meter_key,
    )
    if exclude_id is not None:
        statement = statement.where(HesMeterReference.id != exclude_id)

    duplicate = session.scalar(statement.limit(1))
    if duplicate is not None:
        raise HesMeterReferenceValidationError(
            "duplicate_source_meter_key",
            "A HES meter reference with the same source meter key already exists.",
        )


def upsert_hes_meter_reference(
    session: Session,
    *,
    hes_system_id: int,
    source_table_name: str | None,
    source_meter_id: str | None,
    source_meter_key: str | None = None,
    meter_name: str | None = None,
    meter_status_code: str | None = None,
    lp_interval_minutes: int | str | None = None,
    meter_type_code: str | None = None,
    device_model_code: str | None = None,
    modem_source_id: str | None = None,
    location_source_id: str | None = None,
    supplier_source_id: str | None = None,
    last_read_at_text: str | None = None,
    source_write_at_text: str | None = None,
    source_payload: dict[str, Any] | None = None,
    last_synced_at: datetime | None = None,
) -> HesMeterReference:
    _load_hes_system(session, hes_system_id)
    normalized_source_table_name = _normalize_required_text(
        source_table_name,
        error_code="missing_source_table_name",
        fallback_message="Source table name is required.",
    )
    normalized_source_meter_id = _normalize_required_text(
        source_meter_id,
        error_code="missing_source_meter_id",
        fallback_message="Source meter id is required.",
    )
    normalized_source_meter_key = _normalize_optional_text(source_meter_key)
    if source_payload is None or not isinstance(source_payload, dict):
        raise HesMeterReferenceValidationError(
            "invalid_source_payload",
            "Source payload must be a JSON object.",
        )

    existing = session.scalar(
        select(HesMeterReference)
        .where(
            HesMeterReference.hes_system_id == hes_system_id,
            HesMeterReference.source_meter_id == normalized_source_meter_id,
        )
        .limit(1)
    )

    _ensure_unique_source_meter_key(
        session,
        hes_system_id=hes_system_id,
        source_meter_key=normalized_source_meter_key,
        exclude_id=existing.id if existing is not None else None,
    )

    reference = existing or HesMeterReference(
        hes_system_id=hes_system_id,
        source_table_name=normalized_source_table_name,
        source_meter_id=normalized_source_meter_id,
        source_payload=source_payload,
        last_synced_at=last_synced_at or datetime.now(timezone.utc),
    )

    reference.source_table_name = normalized_source_table_name
    reference.source_meter_id = normalized_source_meter_id
    reference.source_meter_key = normalized_source_meter_key
    reference.meter_name = _normalize_optional_text(meter_name)
    reference.meter_status_code = _normalize_optional_text(meter_status_code)
    reference.lp_interval_minutes = _normalize_optional_interval(lp_interval_minutes)
    reference.meter_type_code = _normalize_optional_text(meter_type_code)
    reference.device_model_code = _normalize_optional_text(device_model_code)
    reference.modem_source_id = _normalize_optional_text(modem_source_id)
    reference.location_source_id = _normalize_optional_text(location_source_id)
    reference.supplier_source_id = _normalize_optional_text(supplier_source_id)
    reference.last_read_at_text = _normalize_optional_text(last_read_at_text)
    reference.source_write_at_text = _normalize_optional_text(source_write_at_text)
    reference.source_payload = source_payload
    reference.last_synced_at = last_synced_at or datetime.now(timezone.utc)

    session.add(reference)
    session.flush()
    return reference


def list_hes_meter_references(
    session: Session,
    *,
    hes_system_id: int,
    limit: int = 200,
) -> list[HesMeterReference]:
    _load_hes_system(session, hes_system_id)
    return session.scalars(
        select(HesMeterReference)
        .where(HesMeterReference.hes_system_id == hes_system_id)
        .order_by(HesMeterReference.id.desc())
        .limit(limit)
    ).all()


def list_prefill_hes_meter_references(
    session: Session,
    *,
    source_system: str | None,
    external_meter_id: str | None,
    limit: int = 20,
) -> list[HesMeterReference]:
    normalized_source_system = _normalize_optional_text(source_system)
    normalized_external_meter_id = _normalize_optional_text(external_meter_id)
    if normalized_source_system is None or normalized_external_meter_id is None:
        return []

    return session.scalars(
        select(HesMeterReference)
        .join(HesSystem)
        .where(
            HesSystem.hes_code == normalized_source_system,
            or_(
                HesMeterReference.source_meter_id == normalized_external_meter_id,
                HesMeterReference.source_meter_key == normalized_external_meter_id,
            ),
        )
        .order_by(HesMeterReference.last_synced_at.desc(), HesMeterReference.id.desc())
        .limit(limit)
    ).all()
