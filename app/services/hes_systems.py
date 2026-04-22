from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HesSystem


def _normalize_required_hes_code(hes_code: str | None) -> str:
    normalized = (hes_code or "").strip()
    if not normalized:
        raise ValueError("HES code is required.")
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
