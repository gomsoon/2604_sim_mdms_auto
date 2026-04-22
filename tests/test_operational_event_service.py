from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import IngestBatch, OperationalEvent
from app.services.operational_events import (
    OperationalAlertError,
    acknowledge_operational_alert,
    close_operational_alert,
    close_operational_alerts,
    record_operational_event,
)
from app.services.seeds import seed_demo_environment


def test_record_operational_event_creates_open_alert_with_lifecycle_fields(session):
    event = record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        details={"error_code": "sample_failure"},
        instance_code="demo_adapter",
        error_summary="Sample failure",
    )
    session.commit()

    stored = session.get(OperationalEvent, event.id)

    assert stored is not None
    assert stored.is_alert is True
    assert stored.alert_status == "open"
    assert stored.opened_at == datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc)
    assert stored.closed_at is None
    assert stored.title_en == "Adapter run failed"


def test_record_operational_event_infers_hes_system_from_ingest_batch(session):
    seed_demo_environment(session)
    session.commit()

    ingest_batch = session.scalar(
        select(IngestBatch).where(IngestBatch.batch_id == "demo-read-batch").limit(1)
    )
    assert ingest_batch is not None
    assert ingest_batch.hes_system_id is not None

    event = record_operational_event(
        session,
        "raw_ingest_completed",
        ingest_batch=ingest_batch,
    )
    session.commit()

    stored = session.get(OperationalEvent, event.id)

    assert stored is not None
    assert stored.hes_system_id == ingest_batch.hes_system_id
    assert stored.batch_id == "demo-read-batch"


def test_close_operational_alerts_marks_matching_rows_closed(session):
    event = record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        details={},
        instance_code="demo_adapter",
        error_summary="Sample failure",
        entity_type="adapter_instance",
        entity_id=101,
    )
    session.flush()

    closed = close_operational_alerts(
        session,
        event_code="adapter_run_failed",
        entity_type="adapter_instance",
        entity_id=101,
        closed_at=datetime(2026, 4, 21, 12, 5, tzinfo=timezone.utc),
        operator_memo="Resolved automatically after success.",
    )
    session.commit()

    stored = session.scalar(select(OperationalEvent).where(OperationalEvent.id == event.id).limit(1))

    assert closed == 1
    assert stored is not None
    assert stored.alert_status == "closed"
    assert stored.closed_at == datetime(2026, 4, 21, 12, 5, tzinfo=timezone.utc)
    assert stored.operator_memo == "Resolved automatically after success."


def test_acknowledge_operational_alert_marks_alert_acknowledged(session):
    event = record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        details={},
        instance_code="demo_adapter",
        error_summary="Sample failure",
    )
    session.flush()

    updated = acknowledge_operational_alert(
        session,
        event.id,
        acknowledged_by="operator_ui",
        acknowledged_at=datetime(2026, 4, 21, 12, 1, tzinfo=timezone.utc),
    )
    session.commit()

    stored = session.get(OperationalEvent, event.id)

    assert updated.alert_status == "acknowledged"
    assert stored is not None
    assert stored.alert_status == "acknowledged"
    assert stored.acknowledged_by == "operator_ui"
    assert stored.acknowledged_at == datetime(2026, 4, 21, 12, 1, tzinfo=timezone.utc)
    assert stored.closed_at is None


def test_close_operational_alert_marks_single_alert_closed_with_memo(session):
    event = record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        details={},
        instance_code="demo_adapter",
        error_summary="Sample failure",
    )
    session.flush()

    updated = close_operational_alert(
        session,
        event.id,
        closed_at=datetime(2026, 4, 21, 12, 10, tzinfo=timezone.utc),
        operator_memo="Reviewed on dashboard.",
    )
    session.commit()

    stored = session.get(OperationalEvent, event.id)

    assert updated.alert_status == "closed"
    assert stored is not None
    assert stored.alert_status == "closed"
    assert stored.closed_at == datetime(2026, 4, 21, 12, 10, tzinfo=timezone.utc)
    assert stored.operator_memo == "Reviewed on dashboard."


def test_acknowledge_operational_alert_rejects_already_closed_alert(session):
    event = record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=datetime(2026, 4, 21, 12, 0, tzinfo=timezone.utc),
        details={},
        instance_code="demo_adapter",
        error_summary="Sample failure",
        alert_status="closed",
        closed_at=datetime(2026, 4, 21, 12, 2, tzinfo=timezone.utc),
    )
    session.flush()

    try:
        acknowledge_operational_alert(session, event.id, acknowledged_by="operator_ui")
    except OperationalAlertError as exc:
        assert exc.error_code == "already_closed"
    else:
        raise AssertionError("Expected acknowledge_operational_alert to reject closed alerts")
