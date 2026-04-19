from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import CanonicalMeasurement, HesReadRaw, IngestErrorLog, ReprocessRequest
from app.services.exception_queue import (
    ExceptionQueueFilters,
    ExceptionReprocessError,
    build_exception_filters,
    list_exception_queue,
    reprocess_exception,
)
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
