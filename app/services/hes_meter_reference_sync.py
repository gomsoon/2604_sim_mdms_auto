from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HesMeterReference, HesSystem
from app.services.hes_meter_references import upsert_hes_meter_reference
from app.services.nuri_aimir_hes_source import (
    fetch_nuri_aimir_hes_meter_rows,
    parse_nuri_aimir_hes_meter_reference_config,
)


@dataclass(slots=True)
class HesMeterReferenceSyncError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class HesMeterReferenceSyncSummary:
    hes_system_id: int
    hes_code: str
    source_family: str
    rows_fetched: int
    created: int
    updated: int


def _load_hes_system(session: Session, *, hes_code: str | None = None, hes_system_id: int | None = None) -> HesSystem:
    if hes_system_id is not None:
        hes_system = session.get(HesSystem, hes_system_id)
    elif hes_code:
        hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == hes_code).limit(1))
    else:
        raise HesMeterReferenceSyncError(
            "missing_hes_identifier",
            "Either hes_code or hes_system_id is required.",
        )

    if hes_system is None:
        raise HesMeterReferenceSyncError(
            "hes_system_not_found",
            "The selected HES system does not exist.",
        )
    return hes_system


def _normalize_runtime_config(hes_system: HesSystem) -> tuple[dict[str, Any], str | None]:
    runtime_config = dict(hes_system.connection_config_masked or {})
    secret_ref = str(
        runtime_config.get("oracle_secret_ref")
        or runtime_config.get("secret_ref")
        or ""
    ).strip() or None
    return runtime_config, secret_ref


def sync_hes_meter_references(
    session: Session,
    *,
    hes_code: str | None = None,
    hes_system_id: int | None = None,
) -> HesMeterReferenceSyncSummary:
    hes_system = _load_hes_system(session, hes_code=hes_code, hes_system_id=hes_system_id)

    if hes_system.source_family != "nuri_aimir_hes":
        raise HesMeterReferenceSyncError(
            "unsupported_hes_meter_reference_source_family",
            "Meter reference sync is currently supported only for nuri_aimir_hes.",
        )

    runtime_config, secret_ref = _normalize_runtime_config(hes_system)
    meter_config = parse_nuri_aimir_hes_meter_reference_config(
        runtime_config,
        secret_ref=secret_ref,
    )
    rows = fetch_nuri_aimir_hes_meter_rows(meter_config)

    created = 0
    updated = 0
    synced_at = datetime.now(timezone.utc)

    for row in rows:
        source_meter_id = str(row.get("ID") or "").strip()
        existing = None
        if source_meter_id:
            existing = session.scalar(
                select(HesMeterReference)
                .where(
                    HesMeterReference.hes_system_id == hes_system.id,
                    HesMeterReference.source_meter_id == source_meter_id,
                )
                .limit(1)
            )

        upsert_hes_meter_reference(
            session,
            hes_system_id=hes_system.id,
            source_table_name="METER",
            source_meter_id=source_meter_id,
            source_meter_key=str(row.get("MDS_ID") or "").strip() or None,
            meter_name=str(row.get("METER") or "").strip() or None,
            meter_status_code=str(row.get("METER_STATUS") or "").strip() or None,
            lp_interval_minutes=row.get("LP_INTERVAL"),
            meter_type_code=str(row.get("METERTYPE_ID") or "").strip() or None,
            device_model_code=str(row.get("DEVICEMODEL_ID") or "").strip() or None,
            modem_source_id=str(row.get("MODEM_ID") or "").strip() or None,
            location_source_id=str(row.get("LOCATION_ID") or "").strip() or None,
            supplier_source_id=str(row.get("SUPPLIER_ID") or "").strip() or None,
            last_read_at_text=str(row.get("LAST_READ_DATE") or "").strip() or None,
            source_write_at_text=str(row.get("WRITE_DATE") or "").strip() or None,
            source_payload=row,
            last_synced_at=synced_at,
        )
        if existing is None:
            created += 1
        else:
            updated += 1

    return HesMeterReferenceSyncSummary(
        hes_system_id=hes_system.id,
        hes_code=hes_system.hes_code,
        source_family=hes_system.source_family,
        rows_fetched=len(rows),
        created=created,
        updated=updated,
    )
