from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import HesSystem
from app.services.bill_determinants import calculate_bill_determinants
from app.services.seeds import seed_demo_environment
from app.services.visibility import (
    build_bill_determinant_filters,
    VisibilityFilterError,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    build_operational_event_filters,
    build_usage_transaction_filters,
    get_bill_determinant_detail_context,
    list_bill_determinants,
    list_canonical_measurements,
    list_final_measurements,
    list_ingest_batches,
    list_operational_events,
    list_usage_transactions,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.operational_events import close_operational_alert
from app.services.usage import calculate_usage_transactions


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


def test_build_usage_transaction_filters_rejects_invalid_usage_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_usage_transaction_filters({"usage_type": "hourly"})

    assert exc_info.value.error_code == "invalid_usage_type_filter"


def test_list_usage_transactions_filters_by_service_point_channel_and_status(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    matched_rows = list_usage_transactions(
        session,
        build_usage_transaction_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "usage_type": "daily_consumption",
                "calculation_status": "partial",
            }
        ),
    )
    unmatched_rows = list_usage_transactions(
        session,
        build_usage_transaction_filters(
            {
                "service_point": "SP-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert matched_rows[0].usage_type == "daily_consumption"
    assert matched_rows[0].calculation_status == "partial"
    assert unmatched_rows == []


def test_build_bill_determinant_filters_rejects_invalid_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_bill_determinant_filters({"determinant_type": "daily_total"})

    assert exc_info.value.error_code == "invalid_bill_determinant_type_filter"


def test_list_bill_determinants_filters_by_service_point_channel_and_status(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    matched_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "determinant_type": "billing_cycle_consumption_total",
                "calculation_status": "partial",
            }
        ),
    )
    unmatched_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "service_point": "SP-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert matched_rows[0].determinant_type == "billing_cycle_consumption_total"
    assert matched_rows[0].calculation_status == "partial"
    assert unmatched_rows == []


def test_list_bill_determinants_filters_by_hes_system(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    demo_hes = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert demo_hes is not None

    rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "hes_system_id": str(demo_hes.id),
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].service_point.external_id == "SP-1001"


def test_get_bill_determinant_detail_context_loads_source_usage_and_revision_rows(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    detail = get_bill_determinant_detail_context(session, 1)

    assert detail is not None
    assert detail.bill_determinant.id == 1
    assert len(detail.source_usage_rows) == 1
    assert detail.source_usage_rows[0].usage_type == "monthly_consumption"
    assert len(detail.revision_rows) == 1


def test_build_operational_event_filters_rejects_invalid_stream_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_operational_event_filters({"stream_type": "alerts"})

    assert exc_info.value.error_code == "invalid_stream_type"


def test_build_operational_event_filters_rejects_invalid_hes_system_id():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_operational_event_filters({"hes_system_id": "0"})

    assert exc_info.value.error_code == "invalid_hes_system_filter"


def test_list_operational_events_filters_by_alert_status_and_batch_id(session):
    seed_demo_environment(session)
    session.commit()

    alert = list_operational_events(
        session,
        build_operational_event_filters(
            {
                "stream_type": "alert",
                "event_code": "canonical_failed",
                "batch_id": "demo-read-batch",
            }
        ),
    )[0]
    close_operational_alert(session, alert.id)
    session.commit()

    rows = list_operational_events(
        session,
        build_operational_event_filters(
            {
                "stream_type": "alert",
                "alert_status": "closed",
                "batch_id": "demo-read-batch",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].event_code == "canonical_failed"
    assert rows[0].alert_status == "closed"
    assert rows[0].batch_id == "demo-read-batch"


def test_list_operational_events_filters_by_hes_system(session):
    from app.services.operational_events import record_operational_event

    seed_demo_environment(session)
    session.commit()

    demo_hes = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert demo_hes is not None

    other_hes = HesSystem(
        hes_code="OTHER_HES",
        display_name="Other HES",
        source_family="hes",
        status="active",
    )
    session.add(other_hes)
    session.flush()
    record_operational_event(
        session,
        "adapter_enabled",
        hes_system=other_hes,
        details={},
        instance_code="other_hes_adapter",
    )
    session.commit()

    rows = list_operational_events(
        session,
        build_operational_event_filters({"hes_system_id": str(demo_hes.id)}),
    )

    assert rows
    assert all(row.hes_system_id == demo_hes.id for row in rows)
