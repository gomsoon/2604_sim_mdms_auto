from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdapterDefinition,
    AdapterInstance,
    AdapterRun,
    AdapterWatermark,
    Device,
    InstallationHistory,
    MeasuringComponent,
    ServicePoint,
)
from app.services.hes_systems import ensure_hes_system
from app.services.ingestion import ingest_events, ingest_reads


def seed_demo_environment(session: Session) -> dict:
    created = seed_master_data(session)
    adapter_runtime_created = seed_adapter_runtime(session)
    hes_system = ensure_hes_system(
        session,
        hes_code="HES",
        display_name="Demo HES",
        source_family="hes",
        default_delivery_mode="poll",
    )
    read_summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "demo-read-batch",
            "received_at": "2026-04-18T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:15:00+09:00",
                    "value": 14.2,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:15:00+09:00",
                    "value": 14.2,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
                {
                    "meter_id": "MTR-9999",
                    "channel_id": "CH-99",
                    "measured_at": "2026-04-18T00:30:00+09:00",
                    "value": 1.0,
                    "quality_code": "WARN",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
            ],
        },
        hes_system_id=hes_system.id,
    )
    event_summary = ingest_events(
        session,
        {
            "source_system": "HES",
            "batch_id": "demo-event-batch",
            "received_at": "2026-04-18T09:05:00+09:00",
            "events": [
                {
                    "meter_id": "MTR-1001",
                    "event_time": "2026-04-18T00:00:00+09:00",
                    "event_code": "POWER_FAIL",
                    "severity": "high",
                }
            ],
        },
        hes_system_id=hes_system.id,
    )

    return {
        "master_data_created": created,
        "adapter_runtime_created": adapter_runtime_created,
        "read_summary": read_summary,
        "event_summary": event_summary,
    }


def seed_master_data(session: Session) -> bool:
    existing_service_point = session.scalar(select(ServicePoint.id).limit(1))
    if existing_service_point is not None:
        return False

    service_point = ServicePoint(
        source_system="HES",
        external_id="SP-1001",
        service_type="electric",
        name="Demo Apartment 101",
        status="active",
    )
    session.add(service_point)
    session.flush()

    device = Device(
        source_system="HES",
        external_meter_id="MTR-1001",
        serial_number="SN-1001",
        status="active",
        service_point_id=service_point.id,
    )
    session.add(device)
    session.flush()

    component = MeasuringComponent(
        source_system="HES",
        external_channel_id="CH-01",
        unit_of_measure="kWh",
        multiplier=1.0,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )
    session.add(component)

    installation = InstallationHistory(
        device_id=device.id,
        service_point_id=service_point.id,
        installed_at=datetime.now(timezone.utc) - timedelta(days=60),
        removed_at=None,
        status="installed",
    )
    session.add(installation)

    return True


def seed_adapter_runtime(session: Session) -> bool:
    existing_instance = session.scalar(
        select(AdapterInstance.id)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    if existing_instance is not None:
        return False

    definition = AdapterDefinition(
        adapter_code="company_hes_poll_v1",
        display_name="Company HES Poll",
        delivery_mode="poll",
        source_family="hes",
        record_type="hes_read_raw",
        adapter_profile_key="common_raw_v1",
        implementation_key="company_hes_poll_v1",
        status="active",
        description="Demo polling adapter definition for the minimal operator flow.",
    )
    session.add(definition)
    session.flush()

    hes_system = ensure_hes_system(
        session,
        hes_code="HES",
        display_name="Demo HES",
        source_family=definition.source_family,
        default_delivery_mode=definition.delivery_mode,
    )

    instance = AdapterInstance(
        hes_system_id=hes_system.id,
        adapter_definition_id=definition.id,
        instance_code="demo_hes_poll_primary",
        display_name="Demo HES Poll Primary",
        source_system="HES",
        admin_state="enabled",
        status_reason="demo_seed",
        poll_interval_minutes=5,
        batch_size=500,
        next_run_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        last_success_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        last_heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        landing_enabled=False,
        connection_config_masked={
            "host": "hes-db.internal",
            "database": "hes",
            "sample_reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:45:00+09:00",
                    "value": 5.25,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T01:00:00+09:00",
                    "value": 6.1,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
            ],
        },
        secret_ref="env://MDMS_HES_PRIMARY",
    )
    session.add(instance)
    session.flush()

    run = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="schedule",
        run_status="completed",
        requested_at=datetime.now(timezone.utc) - timedelta(minutes=3),
        started_at=datetime.now(timezone.utc) - timedelta(minutes=3),
        completed_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        source_rows_fetched=3,
        ingest_batches_created=1,
        ingest_records_created=3,
        watermark_before="2026-04-17T23:45:00+09:00",
        watermark_after="2026-04-18T00:15:00+09:00",
        details={"record_type": "hes_read_raw"},
    )
    session.add(run)

    watermark = AdapterWatermark(
        adapter_instance_id=instance.id,
        record_type="hes_read_raw",
        cursor_type="timestamp",
        cursor_value="2026-04-18T00:15:00+09:00",
        last_source_timestamp=datetime.now(timezone.utc) - timedelta(minutes=2),
        last_polled_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        details={"column": "measured_at"},
    )
    session.add(watermark)

    return True
