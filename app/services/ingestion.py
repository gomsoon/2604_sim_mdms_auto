from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
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
from app.services.ingest_adapters import adapt_event_records, adapt_read_records
from app.services.ingest_contract import coerce_numeric, parse_datetime
from app.services.pipeline import (
    complete_pipeline_run,
    fail_pipeline_run,
    start_pipeline_run,
    upsert_processing_watermark,
)


@dataclass(frozen=True, slots=True)
class ParsedRawReadPayload:
    meter_identifier: str | None
    channel_identifier: str | None
    measured_at: datetime | None
    reading_value: float | None
    quality_code: str | None
    status_code: str | None
    unit_of_measure: str | None
    interval_size_minutes: int | None = None
    landing_lp_em_read_block_id: int | None = None
    source_table_name: str | None = None
    source_block_key: str | None = None
    source_record_key: str | None = None
    device_identifier: str | None = None
    source_slot_code: str | None = None
    source_slot_index: int | None = None
    source_business_ts: datetime | None = None
    source_write_ts: datetime | None = None
    exception_code: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedRawEventPayload:
    meter_identifier: str | None
    event_time: datetime | None
    event_code: str | None
    severity: str | None
    exception_code: str | None = None
    exception_type: str | None = None
    exception_message: str | None = None


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return parse_datetime(value, require_timezone=True)
    except ValueError:
        return None


def _parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_hes_read_payload(item: dict[str, Any]) -> ParsedRawReadPayload:
    measurement_value = item.get("measurement_ts", item.get("measured_at"))
    measured_at = None
    try:
        measured_at = parse_datetime(measurement_value, require_timezone=True)
    except ValueError:
        measured_at = None

    reading_value = item.get("value")
    try:
        reading_value = coerce_numeric(item.get("value"))
    except (TypeError, ValueError):
        reading_value = None

    parsed = ParsedRawReadPayload(
        meter_identifier=item.get("meter_id"),
        channel_identifier=item.get("channel_id"),
        measured_at=measured_at,
        reading_value=reading_value,
        quality_code=item.get("quality_code"),
        status_code=item.get("status_code"),
        unit_of_measure=item.get("unit_of_measure", item.get("unit")),
        interval_size_minutes=_parse_optional_int(item.get("interval_size_minutes")),
        landing_lp_em_read_block_id=_parse_optional_int(item.get("landing_lp_em_read_block_id")),
        source_table_name=item.get("source_table_name"),
        source_block_key=item.get("source_block_key"),
        source_record_key=item.get("source_record_key"),
        device_identifier=item.get("device_identifier"),
        source_slot_code=item.get("source_slot_code"),
        source_slot_index=_parse_optional_int(item.get("source_slot_index")),
        source_business_ts=_parse_optional_datetime(item.get("source_business_ts")),
        source_write_ts=_parse_optional_datetime(item.get("source_write_ts")),
    )

    if measurement_value not in (None, "") and measured_at is None:
        return replace(
            parsed,
            exception_code="invalid_timestamp",
            exception_type="validation",
            exception_message=(
                "Measurement timestamp must use ISO 8601 format with timezone information."
            ),
        )

    if item.get("value") not in (None, "") and reading_value is None:
        return replace(
            parsed,
            exception_code="invalid_numeric_value",
            exception_type="validation",
            exception_message="Measurement value must be numeric.",
        )

    if not all(
        [
            parsed.meter_identifier,
            parsed.channel_identifier,
            parsed.measured_at,
            parsed.reading_value is not None,
        ]
    ):
        return replace(
            parsed,
            exception_code="missing_required_fields",
            exception_type="validation",
            exception_message="Required raw read fields are missing.",
        )

    return parsed


def apply_parsed_hes_read_payload(hes_read_raw: HesReadRaw, parsed: ParsedRawReadPayload) -> None:
    hes_read_raw.meter_identifier = parsed.meter_identifier
    hes_read_raw.channel_identifier = parsed.channel_identifier
    hes_read_raw.measured_at = parsed.measured_at
    hes_read_raw.reading_value = parsed.reading_value
    hes_read_raw.quality_code = parsed.quality_code
    hes_read_raw.status_code = parsed.status_code
    hes_read_raw.unit_of_measure = parsed.unit_of_measure
    hes_read_raw.interval_size_minutes = parsed.interval_size_minutes or 60
    hes_read_raw.landing_lp_em_read_block_id = parsed.landing_lp_em_read_block_id
    hes_read_raw.source_table_name = parsed.source_table_name
    hes_read_raw.source_block_key = parsed.source_block_key
    hes_read_raw.source_record_key = parsed.source_record_key
    hes_read_raw.device_identifier = parsed.device_identifier
    hes_read_raw.source_slot_code = parsed.source_slot_code
    hes_read_raw.source_slot_index = parsed.source_slot_index
    hes_read_raw.source_business_ts = parsed.source_business_ts
    hes_read_raw.source_write_ts = parsed.source_write_ts
    if parsed.interval_size_minutes is not None and parsed.measured_at is not None:
        hes_read_raw.interval_end_at = parsed.measured_at + timedelta(
            minutes=parsed.interval_size_minutes
        )
    else:
        hes_read_raw.interval_end_at = None


def parse_hes_event_payload(item: dict[str, Any]) -> ParsedRawEventPayload:
    event_timestamp = item.get("event_ts", item.get("event_time"))
    event_time = None
    try:
        event_time = parse_datetime(event_timestamp, require_timezone=True)
    except ValueError:
        event_time = None

    parsed = ParsedRawEventPayload(
        meter_identifier=item.get("meter_id"),
        event_time=event_time,
        event_code=item.get("event_code"),
        severity=item.get("severity"),
    )

    if event_timestamp not in (None, "") and event_time is None:
        return replace(
            parsed,
            exception_code="invalid_timestamp",
            exception_type="validation",
            exception_message="Event timestamp must use ISO 8601 format with timezone information.",
        )

    if not parsed.event_code or not parsed.event_time:
        return replace(
            parsed,
            exception_code="invalid_event_payload",
            exception_type="validation",
            exception_message="Raw event is missing event_code or event_time.",
        )

    return parsed


def apply_parsed_hes_event_payload(
    hes_event_raw: HesEventRaw, parsed: ParsedRawEventPayload
) -> None:
    hes_event_raw.meter_identifier = parsed.meter_identifier
    hes_event_raw.event_time = parsed.event_time
    hes_event_raw.event_code = parsed.event_code
    hes_event_raw.severity = parsed.severity


def find_duplicate_hes_read_raw(session: Session, hes_read_raw: HesReadRaw) -> HesReadRaw | None:
    return session.scalar(
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


def ingest_reads(
    session: Session,
    payload: dict[str, Any],
    *,
    adapter_instance_id: int | None = None,
    adapter_run_id: int | None = None,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    source_system = str(payload.get("source_system", "HES")).strip() or "HES"
    batch_reference = str(payload.get("batch_id") or payload.get("message_id") or now.isoformat())
    received_at = parse_datetime(payload.get("received_at")) or now
    adapter_key, reads = adapt_read_records(payload)

    batch = IngestBatch(
        source_system=source_system,
        batch_id=batch_reference,
        record_type="hes_read_raw",
        received_at=received_at,
        payload=payload,
        adapter_instance_id=adapter_instance_id,
        adapter_run_id=adapter_run_id,
    )
    session.add(batch)
    session.flush()

    raw_ingest_run = start_pipeline_run(
        session,
        pipeline_name="raw_ingest",
        trigger_type="ingest",
        ingest_batch=batch,
        details={
            "batch_id": batch.batch_id,
            "record_type": batch.record_type,
            "source_system": source_system,
            "adapter_key": adapter_key,
        },
    )
    canonical_run = start_pipeline_run(
        session,
        pipeline_name="canonical",
        trigger_type="ingest",
        ingest_batch=batch,
        details={
            "batch_id": batch.batch_id,
            "record_type": batch.record_type,
            "source_system": source_system,
            "adapter_key": adapter_key,
        },
    )

    summary = {
        "batches_created": 1,
        "ingest_batch_id": batch.id,
        "raw_reads_received": 0,
        "canonical_created": 0,
        "duplicates": 0,
        "exceptions": 0,
    }
    validation_errors = 0
    mapping_errors = 0

    for item in reads:
        parsed = parse_hes_read_payload(item.normalized_payload)

        hes_read_raw = HesReadRaw(
            ingest_batch_id=batch.id,
            adapter_instance_id=adapter_instance_id,
            adapter_run_id=adapter_run_id,
            source_system=source_system,
            received_at=received_at,
            payload=item.original_payload,
        )
        apply_parsed_hes_read_payload(hes_read_raw, parsed)
        session.add(hes_read_raw)
        session.flush()

        summary["raw_reads_received"] += 1

        if parsed.exception_code is not None:
            hes_read_raw.canonical_status = "exception"
            record_exception(
                session,
                exception_type=str(parsed.exception_type),
                exception_code=parsed.exception_code,
                message=str(parsed.exception_message),
                details={"hes_read_raw_id": hes_read_raw.id, "payload": item.original_payload},
                hes_read_raw=hes_read_raw,
            )
            summary["exceptions"] += 1
            validation_errors += 1
            continue

        duplicate = find_duplicate_hes_read_raw(session, hes_read_raw)

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

        component = find_measuring_component(session, hes_read_raw)

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
            mapping_errors += 1
            continue

        create_or_get_canonical_measurement(session, hes_read_raw, component)
        summary["canonical_created"] += 1

    raw_ingest_details = {
        "batch_id": batch.batch_id,
        "record_type": batch.record_type,
        "source_system": source_system,
        "adapter_key": adapter_key,
        **summary,
        "validation_errors": validation_errors,
    }
    canonical_details = {
        "batch_id": batch.batch_id,
        "record_type": batch.record_type,
        "source_system": source_system,
        "adapter_key": adapter_key,
        "raw_reads_received": summary["raw_reads_received"],
        "canonical_created": summary["canonical_created"],
        "duplicates": summary["duplicates"],
        "mapping_errors": mapping_errors,
        "exceptions": summary["exceptions"],
    }

    if validation_errors > 0:
        fail_pipeline_run(
            raw_ingest_run,
            result_code="ingest_completed_with_validation_errors",
            details=raw_ingest_details,
        )
    else:
        complete_pipeline_run(
            raw_ingest_run,
            result_code="ingest_completed",
            details=raw_ingest_details,
        )

    if mapping_errors > 0 or summary["duplicates"] > 0:
        fail_pipeline_run(
            canonical_run,
            result_code="canonical_completed_with_exceptions",
            details=canonical_details,
        )
    else:
        complete_pipeline_run(
            canonical_run,
            result_code="canonical_completed",
            details=canonical_details,
        )
    upsert_processing_watermark(
        session,
        pipeline_name="raw_ingest",
        source_system=source_system,
        record_type=batch.record_type,
        last_processed_at=received_at,
        details={
            "batch_id": batch.batch_id,
            "ingest_batch_id": batch.id,
            "adapter_key": adapter_key,
        },
    )
    upsert_processing_watermark(
        session,
        pipeline_name="canonical",
        source_system=source_system,
        record_type=batch.record_type,
        last_processed_at=received_at,
        details={
            "batch_id": batch.batch_id,
            "ingest_batch_id": batch.id,
            "adapter_key": adapter_key,
        },
    )

    return summary


def ingest_events(
    session: Session,
    payload: dict[str, Any],
    *,
    adapter_instance_id: int | None = None,
    adapter_run_id: int | None = None,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    source_system = str(payload.get("source_system", "HES")).strip() or "HES"
    batch_reference = str(payload.get("batch_id") or payload.get("message_id") or now.isoformat())
    received_at = parse_datetime(payload.get("received_at")) or now
    adapter_key, events = adapt_event_records(payload)

    batch = IngestBatch(
        source_system=source_system,
        batch_id=batch_reference,
        record_type="hes_event_raw",
        received_at=received_at,
        payload=payload,
        adapter_instance_id=adapter_instance_id,
        adapter_run_id=adapter_run_id,
    )
    session.add(batch)
    session.flush()

    raw_ingest_run = start_pipeline_run(
        session,
        pipeline_name="raw_ingest",
        trigger_type="ingest",
        ingest_batch=batch,
        details={
            "batch_id": batch.batch_id,
            "record_type": batch.record_type,
            "source_system": source_system,
            "adapter_key": adapter_key,
        },
    )

    summary = {
        "batches_created": 1,
        "ingest_batch_id": batch.id,
        "raw_events_received": 0,
        "exceptions": 0,
    }
    validation_errors = 0

    for item in events:
        parsed = parse_hes_event_payload(item.normalized_payload)

        hes_event_raw = HesEventRaw(
            ingest_batch_id=batch.id,
            source_system=source_system,
            meter_identifier=parsed.meter_identifier,
            event_time=parsed.event_time,
            event_code=parsed.event_code,
            severity=parsed.severity,
            payload=item.original_payload,
        )
        session.add(hes_event_raw)
        session.flush()

        summary["raw_events_received"] += 1

        if parsed.exception_code is not None:
            record_exception(
                session,
                exception_type=str(parsed.exception_type),
                exception_code=parsed.exception_code,
                message=str(parsed.exception_message),
                details={"hes_event_raw_id": hes_event_raw.id, "payload": item.original_payload},
                hes_event_raw=hes_event_raw,
            )
            summary["exceptions"] += 1
            validation_errors += 1

    raw_ingest_details = {
        "batch_id": batch.batch_id,
        "record_type": batch.record_type,
        "source_system": source_system,
        "adapter_key": adapter_key,
        **summary,
        "validation_errors": validation_errors,
    }
    if validation_errors > 0:
        fail_pipeline_run(
            raw_ingest_run,
            result_code="ingest_completed_with_validation_errors",
            details=raw_ingest_details,
        )
    else:
        complete_pipeline_run(
            raw_ingest_run,
            result_code="ingest_completed",
            details=raw_ingest_details,
        )
    upsert_processing_watermark(
        session,
        pipeline_name="raw_ingest",
        source_system=source_system,
        record_type=batch.record_type,
        last_processed_at=received_at,
        details={
            "batch_id": batch.batch_id,
            "ingest_batch_id": batch.id,
            "adapter_key": adapter_key,
        },
    )

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


def find_measuring_component(
    session: Session, hes_read_raw: HesReadRaw
) -> MeasuringComponent | None:
    return session.scalar(
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


def create_or_get_canonical_measurement(
    session: Session,
    hes_read_raw: HesReadRaw,
    component: MeasuringComponent,
) -> CanonicalMeasurement:
    if hes_read_raw.canonical_measurement is not None:
        hes_read_raw.canonical_status = "mapped"
        return hes_read_raw.canonical_measurement

    canonical = CanonicalMeasurement(
        hes_read_raw=hes_read_raw,
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
    return canonical
