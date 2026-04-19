from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.seeds import seed_demo_environment
from app.services.visibility import (
    VisibilityFilterError,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    list_canonical_measurements,
    list_final_measurements,
    list_ingest_batches,
)
from app.services.finalization import finalize_canonical_measurements


def test_build_ingest_batch_filters_rejects_invalid_date_format():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_ingest_batch_filters({"date_from": "2026/04/18"})

    assert exc_info.value.error_code == "invalid_date_filter"


def test_build_canonical_filters_rejects_reversed_date_range():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_canonical_filters({"date_from": "2026-04-19", "date_to": "2026-04-18"})

    assert exc_info.value.error_code == "invalid_date_range"


def test_build_canonical_filters_uses_app_timezone_for_date_only_inputs(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Seoul")

    filters = build_canonical_filters({"date_from": "2026-04-18", "date_to": "2026-04-18"})

    assert filters.date_from == datetime(2026, 4, 17, 15, 0, tzinfo=timezone.utc)
    assert filters.date_to == datetime(2026, 4, 18, 14, 59, 59, 999999, tzinfo=timezone.utc)


def test_list_ingest_batches_filters_by_batch_and_record_type(session):
    seed_demo_environment(session)
    session.commit()

    rows = list_ingest_batches(
        session,
        build_ingest_batch_filters(
            {
                "batch_id": "demo-event-batch",
                "source_system": "HES",
                "record_type": "hes_event_raw",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].batch_id == "demo-event-batch"
    assert rows[0].record_type == "hes_event_raw"


def test_list_canonical_measurements_filters_by_batch_and_meter_id(session):
    seed_demo_environment(session)
    session.commit()

    matched_rows = list_canonical_measurements(
        session,
        build_canonical_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-1001",
            }
        ),
    )
    unmatched_rows = list_canonical_measurements(
        session,
        build_canonical_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].hes_read_raw.ingest_batch.batch_id == "demo-read-batch"
    assert matched_rows[0].hes_read_raw.meter_identifier == "MTR-1001"
    assert unmatched_rows == []


def test_list_final_measurements_filters_by_batch_and_meter_id(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    matched_rows = list_final_measurements(
        session,
        build_final_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-1001",
            }
        ),
    )
    unmatched_rows = list_final_measurements(
        session,
        build_final_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].canonical_measurement.hes_read_raw.ingest_batch.batch_id == "demo-read-batch"
    assert matched_rows[0].canonical_measurement.hes_read_raw.meter_identifier == "MTR-1001"
    assert unmatched_rows == []
