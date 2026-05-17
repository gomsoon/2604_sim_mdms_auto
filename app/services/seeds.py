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
    ServicePointBillingContext,
)
from app.services.hes_meter_references import upsert_hes_meter_reference
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
    seed_hes_meter_references(session, hes_system_id=hes_system.id)
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

    session.add(
        ServicePointBillingContext(
            service_point_id=service_point.id,
            timezone_name="Asia/Seoul",
            billing_cycle_mode="calendar_month",
            billing_cycle_anchor_day=None,
            currency_code="KRW",
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            effective_to=None,
            is_current=True,
            source_system="seed",
            source_reference="seed:service_point_billing_context:SP-1001",
            details={"seeded": True},
        )
    )

    device_without_component = Device(
        source_system="HES",
        external_meter_id="MTR-2001",
        serial_number="SN-2001",
        status="active",
        service_point_id=service_point.id,
    )
    session.add(device_without_component)
    session.flush()

    device_without_installation = Device(
        source_system="HES",
        external_meter_id="MTR-3001",
        serial_number="SN-3001",
        status="active",
        service_point_id=service_point.id,
    )
    session.add(device_without_installation)
    session.flush()

    session.add(
        MeasuringComponent(
            source_system="HES",
            external_channel_id="CH-03",
            unit_of_measure="kWh",
            multiplier=1.0,
            status="active",
            device_id=device_without_installation.id,
            service_point_id=service_point.id,
        )
    )

    return True


def seed_hes_meter_references(session: Session, *, hes_system_id: int) -> bool:
    existing_reference = session.scalar(
        select(Device.id)
        .where(Device.source_system == "HES", Device.external_meter_id == "MTR-1001")
        .limit(1)
    )
    if existing_reference is None:
        return False

    upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system_id,
        source_table_name="METER",
        source_meter_id="AIMIR-32418",
        source_meter_key="MTR-1001",
        meter_name="Matched Demo Meter",
        meter_status_code="140",
        lp_interval_minutes=60,
        meter_type_code="energy",
        device_model_code="demo-model-1",
        location_source_id="LOC-01",
        supplier_source_id="SUP-01",
        source_payload={"ID": "AIMIR-32418", "MDS_ID": "MTR-1001"},
    )
    upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system_id,
        source_table_name="METER",
        source_meter_id="MTR-2001",
        source_meter_key="AIMIR-2001",
        meter_name="Missing Component Meter",
        meter_status_code="151",
        lp_interval_minutes=30,
        meter_type_code="energy",
        device_model_code="demo-model-2",
        location_source_id="LOC-02",
        supplier_source_id="SUP-01",
        source_payload={"ID": "MTR-2001", "MDS_ID": "AIMIR-2001"},
    )
    upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system_id,
        source_table_name="METER",
        source_meter_id="MTR-3001",
        source_meter_key="AIMIR-3001",
        meter_name="Missing Installation Meter",
        meter_status_code="active",
        lp_interval_minutes=15,
        meter_type_code="energy",
        device_model_code="demo-model-3",
        location_source_id="LOC-03",
        supplier_source_id="SUP-01",
        source_payload={"ID": "MTR-3001", "MDS_ID": "AIMIR-3001"},
    )
    upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system_id,
        source_table_name="METER",
        source_meter_id="MTR-9999",
        source_meter_key="AIMIR-9999",
        meter_name="Bootstrap Mapping Meter",
        meter_status_code="active",
        lp_interval_minutes=15,
        meter_type_code="energy",
        device_model_code="demo-model-bootstrap",
        location_source_id="LOC-99",
        supplier_source_id="SUP-03",
        source_payload={"ID": "MTR-9999", "MDS_ID": "AIMIR-9999"},
    )
    upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system_id,
        source_table_name="METER",
        source_meter_id="MTR-4040",
        source_meter_key="AIMIR-4040",
        meter_name="Missing Canonical Meter",
        meter_status_code="inactive",
        lp_interval_minutes=60,
        meter_type_code="energy",
        device_model_code="demo-model-4",
        location_source_id="LOC-04",
        supplier_source_id="SUP-02",
        source_payload={"ID": "MTR-4040", "MDS_ID": "AIMIR-4040"},
    )
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
        requested_by="scheduler",
        requested_by_user_account_id=None,
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
        details={
            "record_type": "hes_read_raw",
            "requested_by": "scheduler",
            "requested_by_user_account_id": None,
            "requested_via": "scheduler",
        },
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
