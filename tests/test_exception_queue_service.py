from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models import (
    CanonicalMeasurement,
    HesReadRaw,
    IngestBatch,
    IngestErrorLog,
    PipelineRun,
    ReprocessRequest,
)
from app.services.exception_queue import (
    ExceptionQueueFilters,
    ExceptionReprocessError,
    build_exception_filters,
    list_exception_queue,
    reprocess_exception,
)
from app.services.ingestion import ingest_reads
from app.services.master_data import create_device, create_measuring_component, create_service_point
from app.services.seeds import seed_demo_environment


def _load_error(session, code: str) -> IngestErrorLog:
    error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == code)
        .order_by(IngestErrorLog.id.asc())
        .limit(1)
    )
    assert error is not None
    return error


def _create_legacy_read_error(
    session,
    *,
    exception_code: str,
    payload: dict,
    meter_identifier: str | None,
    channel_identifier: str | None,
    measured_at,
    reading_value,
) -> IngestErrorLog:
    existing_batches = session.scalar(select(func.count()).select_from(IngestBatch)) or 0
    batch = IngestBatch(
        source_system="HES",
        batch_id=f"legacy-{exception_code}-{existing_batches + 1}",
        record_type="hes_read_raw",
        received_at=datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc),
        payload={"source_system": "HES", "reads": [payload]},
    )
    session.add(batch)
    session.flush()

    raw_row = HesReadRaw(
        ingest_batch_id=batch.id,
        source_system="HES",
        meter_identifier=meter_identifier,
        channel_identifier=channel_identifier,
        measured_at=measured_at,
        reading_value=reading_value,
        quality_code=payload.get("quality_code"),
        status_code=payload.get("status_code"),
        unit_of_measure=payload.get("unit_of_measure", payload.get("unit")),
        received_at=batch.received_at,
        canonical_status="exception",
        payload=payload,
    )
    session.add(raw_row)
    session.flush()

    error = IngestErrorLog(
        exception_type="validation",
        exception_code=exception_code,
        status="open",
        message=f"Legacy {exception_code} error.",
        details={"hes_read_raw_id": raw_row.id, "payload": payload},
        hes_read_raw_id=raw_row.id,
    )
    session.add(error)
    session.flush()
    return error


def test_build_exception_filters_normalizes_blank_values():
    filters = build_exception_filters(
        {
            "batch_id": "  demo-read-batch  ",
            "meter_id": "   ",
            "status": "",
            "exception_code": " measuring_component_not_found ",
        }
    )

    assert filters == ExceptionQueueFilters(
        batch_id="demo-read-batch",
        meter_id=None,
        status=None,
        exception_code="measuring_component_not_found",
    )


def test_list_exception_queue_filters_by_batch_meter_status_and_code(session):
    seed_demo_environment(session)
    session.commit()

    rows = list_exception_queue(
        session,
        build_exception_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-9999",
                "status": "open",
                "exception_code": "measuring_component_not_found",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].exception_code == "measuring_component_not_found"
    assert rows[0].status == "open"
    assert rows[0].hes_read_raw is not None
    assert rows[0].hes_read_raw.meter_identifier == "MTR-9999"


def test_reprocess_exception_rejects_unsupported_duplicate_exception(session):
    seed_demo_environment(session)
    session.commit()

    duplicate_error = _load_error(session, "duplicate_raw_read")

    with pytest.raises(ExceptionReprocessError) as exc_info:
        reprocess_exception(session, duplicate_error)

    assert exc_info.value.error_code == "unsupported_exception_code"
    assert session.scalar(select(func.count()).select_from(ReprocessRequest)) == 0


def test_reprocess_exception_marks_attempt_failed_when_mapping_is_still_missing(session):
    seed_demo_environment(session)
    session.commit()

    mapping_error = _load_error(session, "measuring_component_not_found")

    request = reprocess_exception(session, mapping_error)
    session.commit()

    refreshed_error = session.get(IngestErrorLog, mapping_error.id)
    raw_row = session.get(HesReadRaw, mapping_error.hes_read_raw_id)
    stored_request = session.get(ReprocessRequest, request.id)

    assert stored_request is not None
    assert stored_request.status == "failed"
    assert stored_request.result_code == "measuring_component_not_found"
    assert refreshed_error is not None
    assert refreshed_error.status == "failed"
    assert raw_row is not None
    assert raw_row.canonical_status == "exception"
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 1
    run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.reprocess_request_id == request.id)
        .limit(1)
    )
    assert run is not None
    assert run.pipeline_name == "exception_reprocess"
    assert run.status == "failed"
    assert run.result_code == "measuring_component_not_found"


def test_reprocess_exception_creates_canonical_after_master_data_is_added(session):
    seed_demo_environment(session)
    session.commit()

    mapping_error = _load_error(session, "measuring_component_not_found")

    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-9999",
        service_type="electric",
        name="Recovered Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-9999",
        serial_number="SER-9999",
        service_point_id=service_point.id,
        status="active",
    )
    create_measuring_component(
        session,
        source_system="HES",
        external_channel_id="CH-99",
        unit_of_measure="kWh",
        multiplier=1.0,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )

    request = reprocess_exception(session, mapping_error)
    session.commit()

    refreshed_error = session.get(IngestErrorLog, mapping_error.id)
    raw_row = session.get(HesReadRaw, mapping_error.hes_read_raw_id)
    stored_request = session.get(ReprocessRequest, request.id)

    assert stored_request is not None
    assert stored_request.status == "completed"
    assert stored_request.result_code == "canonical_created"
    assert refreshed_error is not None
    assert refreshed_error.status == "resolved"
    assert raw_row is not None
    assert raw_row.canonical_status == "mapped"
    assert raw_row.canonical_measurement is not None
    assert raw_row.canonical_measurement.device_id == device.id
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 2
    run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.reprocess_request_id == request.id)
        .limit(1)
    )
    assert run is not None
    assert run.pipeline_name == "exception_reprocess"
    assert run.status == "completed"
    assert run.result_code == "canonical_created"


def test_reprocess_exception_recovers_legacy_missing_required_fields_payload(session):
    session.commit()

    error = _create_legacy_read_error(
        session,
        exception_code="missing_required_fields",
        payload={
            "meter_id": "MTR-1001",
            "channel_id": "CH-01",
            "measurement_ts": "2026-04-18T01:00:00+09:00",
            "value": "12.5",
            "quality_code": "OK",
            "status_code": "ACTUAL",
            "unit_of_measure": "kWh",
        },
        meter_identifier="MTR-1001",
        channel_identifier="CH-01",
        measured_at=None,
        reading_value=None,
    )
    session.commit()

    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-1001",
        service_type="electric",
        name="Legacy Recover Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-1001",
        serial_number="SER-1001",
        service_point_id=service_point.id,
        status="active",
    )
    create_measuring_component(
        session,
        source_system="HES",
        external_channel_id="CH-01",
        unit_of_measure="kWh",
        multiplier=1.0,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )

    request = reprocess_exception(session, error)
    session.commit()

    refreshed_error = session.get(IngestErrorLog, error.id)
    raw_row = session.get(HesReadRaw, error.hes_read_raw_id)
    stored_request = session.get(ReprocessRequest, request.id)

    assert stored_request is not None
    assert stored_request.status == "completed"
    assert stored_request.result_code == "canonical_created"
    assert refreshed_error is not None
    assert refreshed_error.status == "resolved"
    assert raw_row is not None
    assert raw_row.measured_at == datetime.fromisoformat("2026-04-18T01:00:00+09:00")
    assert raw_row.reading_value == 12.5
    assert raw_row.canonical_status == "mapped"
    assert raw_row.canonical_measurement is not None
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 1


def test_reprocess_exception_recovers_legacy_invalid_numeric_value_payload(session):
    session.commit()

    error = _create_legacy_read_error(
        session,
        exception_code="invalid_numeric_value",
        payload={
            "meter_id": "MTR-2001",
            "channel_id": "CH-21",
            "measured_at": "2026-04-18T02:00:00+09:00",
            "value": "7.25",
            "quality_code": "OK",
            "status_code": "ACTUAL",
            "unit": "kWh",
        },
        meter_identifier="MTR-2001",
        channel_identifier="CH-21",
        measured_at=datetime.fromisoformat("2026-04-18T02:00:00+09:00"),
        reading_value=None,
    )
    session.commit()

    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-2001",
        service_type="electric",
        name="Legacy Numeric Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-2001",
        serial_number="SER-2001",
        service_point_id=service_point.id,
        status="active",
    )
    create_measuring_component(
        session,
        source_system="HES",
        external_channel_id="CH-21",
        unit_of_measure="kWh",
        multiplier=1.0,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )

    request = reprocess_exception(session, error)
    session.commit()

    refreshed_error = session.get(IngestErrorLog, error.id)
    raw_row = session.get(HesReadRaw, error.hes_read_raw_id)
    stored_request = session.get(ReprocessRequest, request.id)

    assert stored_request is not None
    assert stored_request.status == "completed"
    assert stored_request.result_code == "canonical_created"
    assert refreshed_error is not None
    assert refreshed_error.status == "resolved"
    assert raw_row is not None
    assert raw_row.reading_value == 7.25
    assert raw_row.canonical_status == "mapped"
    assert raw_row.canonical_measurement is not None
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 1


def test_reprocess_exception_keeps_invalid_timestamp_when_payload_is_still_bad(session):
    session.commit()

    error = _create_legacy_read_error(
        session,
        exception_code="invalid_timestamp",
        payload={
            "meter_id": "MTR-3001",
            "channel_id": "CH-31",
            "measurement_ts": "2026/04/18 03:00:00",
            "value": 4.0,
            "quality_code": "WARN",
            "status_code": "ACTUAL",
            "unit_of_measure": "kWh",
        },
        meter_identifier="MTR-3001",
        channel_identifier="CH-31",
        measured_at=None,
        reading_value=4.0,
    )
    session.commit()

    request = reprocess_exception(session, error)
    session.commit()

    refreshed_error = session.get(IngestErrorLog, error.id)
    raw_row = session.get(HesReadRaw, error.hes_read_raw_id)
    stored_request = session.get(ReprocessRequest, request.id)

    assert stored_request is not None
    assert stored_request.status == "failed"
    assert stored_request.result_code == "invalid_timestamp"
    assert refreshed_error is not None
    assert refreshed_error.status == "failed"
    assert raw_row is not None
    assert raw_row.measured_at is None
    assert raw_row.canonical_status == "exception"
    assert raw_row.canonical_measurement is None


def test_reprocess_exception_marks_legacy_payload_as_duplicate_when_it_now_matches_existing_read(
    session,
):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-4001",
        service_type="electric",
        name="Duplicate Target Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-4001",
        serial_number="SER-4001",
        service_point_id=service_point.id,
        status="active",
    )
    create_measuring_component(
        session,
        source_system="HES",
        external_channel_id="CH-41",
        unit_of_measure="kWh",
        multiplier=1.0,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )
    session.commit()

    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "existing-duplicate-target",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-4001",
                    "channel_id": "CH-41",
                    "measured_at": "2026-04-18T04:00:00+09:00",
                    "value": 9.5,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    existing_row = session.scalar(
        select(HesReadRaw)
        .where(HesReadRaw.meter_identifier == "MTR-4001")
        .order_by(HesReadRaw.id.asc())
        .limit(1)
    )
    assert existing_row is not None

    error = _create_legacy_read_error(
        session,
        exception_code="missing_required_fields",
        payload={
            "meter_id": "MTR-4001",
            "channel_id": "CH-41",
            "measurement_ts": "2026-04-18T04:00:00+09:00",
            "value": "9.5",
            "quality_code": "OK",
            "status_code": "ACTUAL",
            "unit_of_measure": "kWh",
        },
        meter_identifier="MTR-4001",
        channel_identifier="CH-41",
        measured_at=None,
        reading_value=None,
    )
    session.commit()

    request = reprocess_exception(session, error)
    session.commit()

    refreshed_error = session.get(IngestErrorLog, error.id)
    raw_row = session.get(HesReadRaw, error.hes_read_raw_id)
    stored_request = session.get(ReprocessRequest, request.id)

    assert stored_request is not None
    assert stored_request.status == "failed"
    assert stored_request.result_code == "duplicate_raw_read"
    assert refreshed_error is not None
    assert refreshed_error.status == "failed"
    assert raw_row is not None
    assert raw_row.canonical_status == "duplicate"
    assert raw_row.is_duplicate is True
    assert raw_row.duplicate_of_id == existing_row.id
    assert raw_row.canonical_measurement is None
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 1
