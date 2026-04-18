from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Device, InstallationHistory, MeasuringComponent, ServicePoint
from app.services.ingestion import ingest_events, ingest_reads


def seed_demo_environment(session: Session) -> dict:
    created = seed_master_data(session)
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
    )

    return {
        "master_data_created": created,
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

