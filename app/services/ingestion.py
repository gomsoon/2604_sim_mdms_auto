from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalMeasurement,
    Device,
    HesEventRaw,
    HesReadRaw,
    IngestBatch,
    IngestErrorLog,
    MeasuringComponent,
)


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    return datetime.fromisoformat(text)


def ingest_reads(session: Session, payload: dict[str, Any]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    source_system = str(payload.get("source_system", "HES")).strip() or "HES"
    batch_reference = str(payload.get("batch_id") or payload.get("message_id") or now.isoformat())
    received_at = parse_datetime(payload.get("received_at")) or now
    reads = payload.get("reads") or []

    batch = IngestBatch(
        source_system=source_system,
        batch_id=batch_reference,
        record_type="hes_read_raw",
        received_at=received_at,
        payload=payload,
    )
    session.add(batch)
    session.flush()

    summary = {
        "batches_created": 1,
        "raw_reads_received": 0,
        "canonical_created": 0,
        "duplicates": 0,
        "exceptions": 0,
    }

    for item in reads:
        hes_read_raw = HesReadRaw(
            ingest_batch_id=batch.id,
            source_system=source_system,
            meter_identifier=item.get("meter_id"),
            channel_identifier=item.get("channel_id"),
            measured_at=parse_datetime(item.get("measured_at")),
            reading_value=item.get("value"),
            quality_code=item.get("quality_code"),
            status_code=item.get("status_code"),
            unit_of_measure=item.get("unit"),
            received_at=received_at,
            payload=item,
        )
        session.add(hes_read_raw)
        session.flush()

        summary["raw_reads_received"] += 1

        if not all(
            [
                hes_read_raw.meter_identifier,
                hes_read_raw.channel_identifier,
                hes_read_raw.measured_at,
                hes_read_raw.reading_value is not None,
            ]
        ):
            hes_read_raw.canonical_status = "exception"
            record_exception(
                session,
                exception_type="validation",
                exception_code="missing_required_fields",
                message="Required raw read fields are missing.",
                details={"hes_read_raw_id": hes_read_raw.id, "payload": item},
                hes_read_raw=hes_read_raw,
            )
            summary["exceptions"] += 1
            continue

        duplicate = session.scalar(
            select(HesReadRaw)
            .where(
                HesReadRaw.id != hes_read_raw.id,
                HesReadRaw.source_system == hes_read_raw.source_system,
                HesReadRaw.meter_identifier == hes_read_raw.meter_identifier,
                HesReadRaw.channel_identifier == hes_read_raw.channel_identifier,
                HesReadRaw.measured_at == hes_read_raw.measured_at,
            )
            .order_by(HesReadRaw.id.asc())
            .limit(1)
        )

        if duplicate is not None:
            hes_read_raw.is_duplicate = True
            hes_read_raw.duplicate_of_id = duplicate.id
            hes_read_raw.canonical_status = "duplicate"
            record_exception(
                session,
                exception_type="duplicate",
                exception_code="duplicate_raw_read",
                message="Duplicate raw read detected for the same source, meter, channel, and timestamp.",
                details={"hes_read_raw_id": hes_read_raw.id, "duplicate_of_id": duplicate.id},
                hes_read_raw=hes_read_raw,
            )
            summary["duplicates"] += 1
            continue

        component = session.scalar(
            select(MeasuringComponent)
            .join(Device)
            .where(
                MeasuringComponent.source_system == hes_read_raw.source_system,
                Device.external_meter_id == hes_read_raw.meter_identifier,
                MeasuringComponent.external_channel_id == hes_read_raw.channel_identifier,
                MeasuringComponent.status == "active",
            )
            .limit(1)
        )

        if component is None:
            hes_read_raw.canonical_status = "exception"
            record_exception(
                session,
                exception_type="mapping",
                exception_code="measuring_component_not_found",
                message="No active measuring component matched the incoming raw read.",
                details={
                    "hes_read_raw_id": hes_read_raw.id,
                    "meter_identifier": hes_read_raw.meter_identifier,
                    "channel_identifier": hes_read_raw.channel_identifier,
                },
                hes_read_raw=hes_read_raw,
            )
            summary["exceptions"] += 1
            continue

        canonical = CanonicalMeasurement(
            hes_read_raw_id=hes_read_raw.id,
            measuring_component_id=component.id,
            device_id=component.device_id,
            service_point_id=component.service_point_id,
            measured_at=hes_read_raw.measured_at,
            value=float(hes_read_raw.reading_value),
            quality_code=hes_read_raw.quality_code,
            status_code=hes_read_raw.status_code,
            unit_of_measure=hes_read_raw.unit_of_measure or component.unit_of_measure,
        )
        session.add(canonical)
        hes_read_raw.canonical_status = "mapped"
        summary["canonical_created"] += 1

    return summary


def ingest_events(session: Session, payload: dict[str, Any]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    source_system = str(payload.get("source_system", "HES")).strip() or "HES"
    batch_reference = str(payload.get("batch_id") or payload.get("message_id") or now.isoformat())
    received_at = parse_datetime(payload.get("received_at")) or now
    events = payload.get("events") or []

    batch = IngestBatch(
        source_system=source_system,
        batch_id=batch_reference,
        record_type="hes_event_raw",
        received_at=received_at,
        payload=payload,
    )
    session.add(batch)
    session.flush()

    summary = {
        "batches_created": 1,
        "raw_events_received": 0,
        "exceptions": 0,
    }

    for item in events:
        hes_event_raw = HesEventRaw(
            ingest_batch_id=batch.id,
            source_system=source_system,
            meter_identifier=item.get("meter_id"),
            event_time=parse_datetime(item.get("event_time")),
            event_code=item.get("event_code"),
            severity=item.get("severity"),
            payload=item,
        )
        session.add(hes_event_raw)
        session.flush()

        summary["raw_events_received"] += 1

        if not hes_event_raw.event_code or not hes_event_raw.event_time:
            record_exception(
                session,
                exception_type="validation",
                exception_code="invalid_event_payload",
                message="Raw event is missing event_code or event_time.",
                details={"hes_event_raw_id": hes_event_raw.id, "payload": item},
                hes_event_raw=hes_event_raw,
            )
            summary["exceptions"] += 1

    return summary


def record_exception(
    session: Session,
    *,
    exception_type: str,
    exception_code: str,
    message: str,
    details: dict[str, Any],
    hes_read_raw: HesReadRaw | None = None,
    hes_event_raw: HesEventRaw | None = None,
) -> None:
    exception = IngestErrorLog(
        exception_type=exception_type,
        exception_code=exception_code,
        message=message,
        details=details,
        hes_read_raw_id=hes_read_raw.id if hes_read_raw else None,
        hes_event_raw_id=hes_event_raw.id if hes_event_raw else None,
    )
    session.add(exception)
