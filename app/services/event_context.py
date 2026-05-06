from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HesEventRaw, InitialMeasurement

EVENT_CONTEXT_TOLERANCE_MINUTES = 15
OUTAGE_EVENT_CODES = {
    "POWER_FAIL",
    "POWER_OUTAGE",
    "OUTAGE",
    "OUTAGE_START",
}
TAMPER_EVENT_CODES = {
    "METER_TAMPER",
    "METER_OPEN",
    "REVERSE_ENERGY",
    "TAMPER",
    "TAMPER_ALARM",
}


def classify_event_context_type(event_code: str | None) -> str | None:
    normalized = str(event_code or "").strip().upper()
    if not normalized:
        return None
    if normalized in TAMPER_EVENT_CODES:
        return "tamper"
    if normalized in OUTAGE_EVENT_CODES:
        return "outage"
    return None


def has_event_context_type(
    event_context_snapshot: dict[str, object] | None,
    context_type: str,
) -> bool:
    if not event_context_snapshot:
        return False
    matched_types = event_context_snapshot.get("matched_context_types")
    if not isinstance(matched_types, list):
        return False
    return context_type in matched_types


def lookup_event_context_snapshot(
    session: Session,
    initial_row: InitialMeasurement,
    *,
    tolerance_minutes: int = EVENT_CONTEXT_TOLERANCE_MINUTES,
) -> dict[str, object] | None:
    canonical_row = initial_row.canonical_measurement
    raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
    if raw_row is None:
        return None
    if raw_row.measured_at is None:
        return None
    if not (raw_row.source_system or "").strip():
        return None
    if not (raw_row.meter_identifier or "").strip():
        return None

    window_start = raw_row.measured_at - timedelta(minutes=tolerance_minutes)
    window_end = raw_row.measured_at + timedelta(minutes=tolerance_minutes)

    statement = (
        select(HesEventRaw)
        .where(
            HesEventRaw.source_system == raw_row.source_system,
            HesEventRaw.meter_identifier == raw_row.meter_identifier,
            HesEventRaw.event_time.is_not(None),
            HesEventRaw.event_time >= window_start,
            HesEventRaw.event_time <= window_end,
        )
        .order_by(HesEventRaw.event_time.asc(), HesEventRaw.id.asc())
    )
    if raw_row.hes_system_id is not None:
        statement = statement.where(HesEventRaw.hes_system_id == raw_row.hes_system_id)

    matched_rows = []
    matched_context_types: list[str] = []
    for event_row in session.scalars(statement).all():
        context_type = classify_event_context_type(event_row.event_code)
        if context_type is None:
            continue
        matched_rows.append(event_row)
        if context_type not in matched_context_types:
            matched_context_types.append(context_type)

    if not matched_rows:
        return None

    primary_context_type = "tamper" if "tamper" in matched_context_types else matched_context_types[0]
    return {
        "primary_context_type": primary_context_type,
        "matched_context_types": matched_context_types,
        "correlation_reason": "meter_and_time_window_match",
        "tolerance_minutes": tolerance_minutes,
        "meter_identifier": raw_row.meter_identifier,
        "source_system": raw_row.source_system,
        "measured_at": raw_row.measured_at.isoformat(),
        "matched_event_ids": [row.id for row in matched_rows],
        "matched_event_codes": [row.event_code for row in matched_rows if row.event_code],
        "matched_event_times": [
            row.event_time.isoformat() for row in matched_rows if row.event_time is not None
        ],
        "matched_event_severities": [row.severity for row in matched_rows if row.severity],
        "matched_event_count": len(matched_rows),
    }
