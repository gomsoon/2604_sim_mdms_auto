from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import AdapterInstance, HesEventRaw, HesReadRaw, HesSystem, IngestBatch, OperationalEvent


@dataclass(slots=True)
class HesSystemValidationError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class HesSystemSummary:
    hes_system: HesSystem
    adapter_count: int
    enabled_adapter_count: int
    open_alert_count: int
    latest_success_at: object | None


@dataclass(frozen=True, slots=True)
class HesSystemDetail:
    hes_system: HesSystem
    recent_batches: list[IngestBatch]
    adapter_rows: list[Any]
    open_alert_count: int
    open_alerts: list[OperationalEvent]
    recent_events: list[OperationalEvent]
    raw_reads_count: int
    raw_events_count: int


def _normalize_required_hes_code(hes_code: str | None) -> str:
    normalized = (hes_code or "").strip()
    if not normalized:
        raise HesSystemValidationError("missing_hes_code", "HES code is required.")
    return normalized


def _normalize_required_text(
    value: str | None, *, error_code: str, fallback_message: str
) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HesSystemValidationError(error_code, fallback_message)
    return normalized


def _parse_masked_config(raw_value: str | None) -> dict[str, Any] | None:
    import json

    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise HesSystemValidationError(
            "invalid_connection_config_masked",
            "Masked connection configuration must be a valid JSON object.",
        ) from exc
    if not isinstance(parsed, dict):
        raise HesSystemValidationError(
            "invalid_connection_config_masked",
            "Masked connection configuration must be a valid JSON object.",
        )
    return parsed


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_status(status: str | None) -> str:
    normalized = (status or "").strip() or "active"
    if normalized not in {"active", "inactive"}:
        raise HesSystemValidationError(
            "invalid_status",
            "Status must be active or inactive.",
        )
    return normalized


def _normalize_optional_delivery_mode(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if normalized not in {"poll", "receive"}:
        raise HesSystemValidationError(
            "invalid_default_delivery_mode",
            "Default delivery mode must be poll or receive.",
        )
    return normalized


def ensure_hes_system(
    session: Session,
    *,
    hes_code: str,
    display_name: str | None = None,
    vendor_name: str | None = None,
    source_family: str = "hes",
    default_delivery_mode: str | None = None,
    status: str = "active",
    timezone_name: str | None = None,
    description: str | None = None,
    connection_config_masked: dict[str, Any] | None = None,
) -> HesSystem:
    normalized_hes_code = _normalize_required_hes_code(hes_code)
    existing = session.scalar(
        select(HesSystem).where(HesSystem.hes_code == normalized_hes_code).limit(1)
    )
    if existing is not None:
        return existing

    hes_system = HesSystem(
        hes_code=normalized_hes_code,
        display_name=(display_name or normalized_hes_code).strip() or normalized_hes_code,
        vendor_name=(vendor_name or "").strip() or None,
        source_family=(source_family or "hes").strip() or "hes",
        default_delivery_mode=(default_delivery_mode or "").strip() or None,
        status=(status or "active").strip() or "active",
        timezone_name=(timezone_name or "").strip() or None,
        description=(description or "").strip() or None,
        connection_config_masked=connection_config_masked,
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def list_hes_systems(session: Session, *, limit: int = 100) -> list[HesSystemSummary]:
    rows = session.scalars(
        select(HesSystem).options(selectinload(HesSystem.adapter_instances)).order_by(HesSystem.id.desc()).limit(limit)
    ).all()

    summaries: list[HesSystemSummary] = []
    for row in rows:
        open_alert_count = int(
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(
                    OperationalEvent.hes_system_id == row.id,
                    OperationalEvent.is_alert.is_(True),
                    OperationalEvent.alert_status.in_(("open", "acknowledged")),
                )
            )
            or 0
        )
        latest_success_candidates = [
            adapter.last_success_at for adapter in row.adapter_instances if adapter.last_success_at is not None
        ]
        summaries.append(
            HesSystemSummary(
                hes_system=row,
                adapter_count=len(row.adapter_instances),
                enabled_adapter_count=sum(1 for adapter in row.adapter_instances if adapter.admin_state == "enabled"),
                open_alert_count=open_alert_count,
                latest_success_at=max(latest_success_candidates) if latest_success_candidates else None,
            )
        )
    return summaries


def create_hes_system(
    session: Session,
    *,
    hes_code: str | None,
    display_name: str | None,
    vendor_name: str | None,
    source_family: str | None,
    default_delivery_mode: str | None,
    status: str | None,
    timezone_name: str | None,
    description: str | None,
    connection_config_masked: str | None,
) -> HesSystem:
    normalized_hes_code = _normalize_required_hes_code(hes_code)
    duplicate = session.scalar(select(HesSystem.id).where(HesSystem.hes_code == normalized_hes_code).limit(1))
    if duplicate is not None:
        raise HesSystemValidationError(
            "duplicate_hes_code",
            "A HES system with the same code already exists.",
        )

    hes_system = HesSystem(
        hes_code=normalized_hes_code,
        display_name=_normalize_required_text(
            display_name,
            error_code="missing_display_name",
            fallback_message="HES display name is required.",
        ),
        vendor_name=_normalize_optional_text(vendor_name),
        source_family=_normalize_required_text(
            source_family,
            error_code="missing_source_family",
            fallback_message="Source family is required.",
        ),
        default_delivery_mode=_normalize_optional_delivery_mode(default_delivery_mode),
        status=_normalize_status(status),
        timezone_name=_normalize_optional_text(timezone_name),
        description=_normalize_optional_text(description),
        connection_config_masked=_parse_masked_config(connection_config_masked),
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def update_hes_system(
    session: Session,
    hes_system: HesSystem,
    *,
    hes_code: str | None,
    display_name: str | None,
    vendor_name: str | None,
    source_family: str | None,
    default_delivery_mode: str | None,
    status: str | None,
    timezone_name: str | None,
    description: str | None,
    connection_config_masked: str | None,
) -> HesSystem:
    normalized_hes_code = _normalize_required_hes_code(hes_code)
    duplicate = session.scalar(
        select(HesSystem.id)
        .where(HesSystem.hes_code == normalized_hes_code, HesSystem.id != hes_system.id)
        .limit(1)
    )
    if duplicate is not None:
        raise HesSystemValidationError(
            "duplicate_hes_code",
            "A HES system with the same code already exists.",
        )

    hes_system.hes_code = normalized_hes_code
    hes_system.display_name = _normalize_required_text(
        display_name,
        error_code="missing_display_name",
        fallback_message="HES display name is required.",
    )
    hes_system.vendor_name = _normalize_optional_text(vendor_name)
    hes_system.source_family = _normalize_required_text(
        source_family,
        error_code="missing_source_family",
        fallback_message="Source family is required.",
    )
    hes_system.default_delivery_mode = _normalize_optional_delivery_mode(default_delivery_mode)
    hes_system.status = _normalize_status(status)
    hes_system.timezone_name = _normalize_optional_text(timezone_name)
    hes_system.description = _normalize_optional_text(description)
    hes_system.connection_config_masked = _parse_masked_config(connection_config_masked)
    session.flush()
    return hes_system


def get_hes_system_detail(session: Session, hes_system_id: int) -> HesSystemDetail | None:
    from app.services.adapters import list_adapter_instances

    hes_system = session.scalar(
        select(HesSystem)
        .options(selectinload(HesSystem.adapter_instances).selectinload(AdapterInstance.adapter_definition))
        .where(HesSystem.id == hes_system_id)
        .limit(1)
    )
    if hes_system is None:
        return None

    adapter_rows = list_adapter_instances(session, limit=200, hes_system_id=hes_system.id)
    recent_batches = session.scalars(
        select(IngestBatch)
        .where(IngestBatch.hes_system_id == hes_system.id)
        .order_by(IngestBatch.id.desc())
        .limit(20)
    ).all()

    open_alert_count = int(
        session.scalar(
            select(func.count())
            .select_from(OperationalEvent)
            .where(
                OperationalEvent.hes_system_id == hes_system.id,
                OperationalEvent.is_alert.is_(True),
                OperationalEvent.alert_status.in_(("open", "acknowledged")),
            )
        )
        or 0
    )
    open_alerts = session.scalars(
        select(OperationalEvent)
        .where(
            OperationalEvent.hes_system_id == hes_system.id,
            OperationalEvent.is_alert.is_(True),
            OperationalEvent.alert_status.in_(("open", "acknowledged")),
        )
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(10)
    ).all()
    recent_events = session.scalars(
        select(OperationalEvent)
        .where(OperationalEvent.hes_system_id == hes_system.id)
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(20)
    ).all()

    raw_reads_count = int(
        session.scalar(
            select(func.count()).select_from(HesReadRaw).where(HesReadRaw.hes_system_id == hes_system.id)
        )
        or 0
    )
    raw_events_count = int(
        session.scalar(
            select(func.count()).select_from(HesEventRaw).where(HesEventRaw.hes_system_id == hes_system.id)
        )
        or 0
    )

    return HesSystemDetail(
        hes_system=hes_system,
        recent_batches=recent_batches,
        adapter_rows=adapter_rows,
        open_alert_count=open_alert_count,
        open_alerts=open_alerts,
        recent_events=recent_events,
        raw_reads_count=raw_reads_count,
        raw_events_count=raw_events_count,
    )
