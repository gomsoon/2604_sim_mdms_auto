from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalMeasurement,
    Device,
    IngestionBatch,
    MeasuringComponent,
    ProcessingException,
    RawEvent,
    RawRead,
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

    batch = IngestionBatch(
        source_system=source_system,
        batch_id=batch_reference,
        record_type="raw_read",
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
        raw_read = RawRead(
            ingestion_batch_id=batch.id,
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
        session.add(raw_read)
        session.flush()

        summary["raw_reads_received"] += 1

        if not all(
            [
                raw_read.meter_identifier,
                raw_read.channel_identifier,
                raw_read.measured_at,
                raw_read.reading_value is not None,
            ]
        ):
            raw_read.canonical_status = "exception"
            record_exception(
                session,
                exception_type="validation",
                exception_code="missing_required_fields",
                message="Required raw read fields are missing.",
                details={"raw_read_id": raw_read.id, "payload": item},
                raw_read=raw_read,
            )
            summary["exceptions"] += 1
            continue

        duplicate = session.scalar(
            select(RawRead)
            .where(
                RawRead.id != raw_read.id,
                RawRead.source_system == raw_read.source_system,
                RawRead.meter_identifier == raw_read.meter_identifier,
                RawRead.channel_identifier == raw_read.channel_identifier,
                RawRead.measured_at == raw_read.measured_at,
            )
            .order_by(RawRead.id.asc())
            .limit(1)
        )

        if duplicate is not None:
            raw_read.is_duplicate = True
            raw_read.duplicate_of_id = duplicate.id
            raw_read.canonical_status = "duplicate"
            record_exception(
                session,
                exception_type="duplicate",
                exception_code="duplicate_raw_read",
                message="Duplicate raw read detected for the same source, meter, channel, and timestamp.",
                details={"raw_read_id": raw_read.id, "duplicate_of_id": duplicate.id},
                raw_read=raw_read,
            )
            summary["duplicates"] += 1
            continue

        component = session.scalar(
            select(MeasuringComponent)
            .join(Device)
            .where(
                MeasuringComponent.source_system == raw_read.source_system,
                Device.external_meter_id == raw_read.meter_identifier,
                MeasuringComponent.external_channel_id == raw_read.channel_identifier,
                MeasuringComponent.status == "active",
            )
            .limit(1)
        )

        if component is None:
            raw_read.canonical_status = "exception"
            record_exception(
                session,
                exception_type="mapping",
                exception_code="measuring_component_not_found",
                message="No active measuring component matched the incoming raw read.",
                details={
                    "raw_read_id": raw_read.id,
                    "meter_identifier": raw_read.meter_identifier,
                    "channel_identifier": raw_read.channel_identifier,
                },
                raw_read=raw_read,
            )
            summary["exceptions"] += 1
            continue

        canonical = CanonicalMeasurement(
            raw_read_id=raw_read.id,
            measuring_component_id=component.id,
            device_id=component.device_id,
            service_point_id=component.service_point_id,
            measured_at=raw_read.measured_at,
            value=float(raw_read.reading_value),
            quality_code=raw_read.quality_code,
            status_code=raw_read.status_code,
            unit_of_measure=raw_read.unit_of_measure or component.unit_of_measure,
        )
        session.add(canonical)
        raw_read.canonical_status = "mapped"
        summary["canonical_created"] += 1

    return summary


def ingest_events(session: Session, payload: dict[str, Any]) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    source_system = str(payload.get("source_system", "HES")).strip() or "HES"
    batch_reference = str(payload.get("batch_id") or payload.get("message_id") or now.isoformat())
    received_at = parse_datetime(payload.get("received_at")) or now
    events = payload.get("events") or []

    batch = IngestionBatch(
        source_system=source_system,
        batch_id=batch_reference,
        record_type="raw_event",
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
        raw_event = RawEvent(
            ingestion_batch_id=batch.id,
            source_system=source_system,
            meter_identifier=item.get("meter_id"),
            event_time=parse_datetime(item.get("event_time")),
            event_code=item.get("event_code"),
            severity=item.get("severity"),
            payload=item,
        )
        session.add(raw_event)
        session.flush()

        summary["raw_events_received"] += 1

        if not raw_event.event_code or not raw_event.event_time:
            record_exception(
                session,
                exception_type="validation",
                exception_code="invalid_event_payload",
                message="Raw event is missing event_code or event_time.",
                details={"raw_event_id": raw_event.id, "payload": item},
                raw_event=raw_event,
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
    raw_read: RawRead | None = None,
    raw_event: RawEvent | None = None,
) -> None:
    exception = ProcessingException(
        exception_type=exception_type,
        exception_code=exception_code,
        message=message,
        details=details,
        raw_read_id=raw_read.id if raw_read else None,
        raw_event_id=raw_event.id if raw_event else None,
    )
    session.add(exception)

