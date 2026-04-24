from __future__ import annotations

from sqlalchemy import select

from app.models import AdapterDefinition, AdapterInstance, AdapterRun, HesEventRaw, HesSystem, IngestBatch
from app.services.seeds import seed_master_data


def _create_receive_adapter(
    session,
    *,
    instance_code: str,
    record_type: str,
    source_system: str = "HES",
    secret_ref: str | None = "env://MDMS_RECEIVE_SECRET",
) -> AdapterInstance:
    hes_system = HesSystem(
        hes_code=source_system,
        display_name=f"{source_system} Receive HES",
        source_family="hes",
        default_delivery_mode="receive",
        status="active",
    )
    session.add(hes_system)
    session.flush()

    definition = AdapterDefinition(
        adapter_code=f"{instance_code}_definition",
        display_name=f"{instance_code} Definition",
        delivery_mode="receive",
        source_family="hes",
        record_type=record_type,
        implementation_key=f"{instance_code}_receive_v1",
        status="active",
    )
    session.add(definition)
    session.flush()

    instance = AdapterInstance(
        hes_system_id=hes_system.id,
        adapter_definition_id=definition.id,
        instance_code=instance_code,
        display_name=f"{instance_code} Receive Adapter",
        source_system=source_system,
        admin_state="enabled",
        status_reason="test_seed",
        secret_ref=secret_ref,
        connection_config_masked={},
    )
    session.add(instance)
    session.flush()
    return instance


def test_receive_reads_endpoint_processes_managed_receive_run(client, session, monkeypatch):
    seed_master_data(session)
    monkeypatch.setenv("MDMS_RECEIVE_SECRET", "top-secret")
    instance = _create_receive_adapter(
        session,
        instance_code="receive_reads_primary",
        record_type="hes_read_raw",
    )
    instance_id = instance.id
    instance_code = instance.instance_code
    session.commit()

    response = client.post(
        f"/api/v1/receive/{instance_code}/reads",
        json={
            "contract_version": "v1",
            "batch_id": "receive-read-batch",
            "received_at": "2026-04-24T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measurement_ts": "2026-04-24T00:15:00+09:00",
                    "value": 12.5,
                    "unit_of_measure": "kWh",
                }
            ],
        },
        headers={"X-Adapter-Secret": "top-secret"},
    )

    run = session.scalar(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance_id)
        .order_by(AdapterRun.id.desc())
        .limit(1)
    )
    batch = session.scalar(
        select(IngestBatch)
        .where(IngestBatch.adapter_instance_id == instance_id)
        .order_by(IngestBatch.id.desc())
        .limit(1)
    )

    assert response.status_code == 201
    assert response.get_json()["raw_reads_received"] == 1
    assert response.get_json()["trigger_type"] == "receive"
    assert run is not None
    assert run.trigger_type == "receive"
    assert run.run_status == "completed"
    assert batch is not None
    assert batch.adapter_run_id == run.id
    assert batch.hes_system_id is not None


def test_receive_events_endpoint_processes_managed_receive_run(client, session, monkeypatch):
    monkeypatch.setenv("MDMS_RECEIVE_SECRET", "top-secret")
    instance = _create_receive_adapter(
        session,
        instance_code="receive_events_primary",
        record_type="hes_event_raw",
    )
    instance_id = instance.id
    instance_code = instance.instance_code
    session.commit()

    response = client.post(
        f"/api/v1/receive/{instance_code}/events",
        json={
            "contract_version": "v1",
            "batch_id": "receive-event-batch",
            "received_at": "2026-04-24T09:05:00+09:00",
            "events": [
                {
                    "meter_id": "MTR-1001",
                    "event_ts": "2026-04-24T00:00:00+09:00",
                    "event_code": "POWER_FAIL",
                    "severity": "high",
                }
            ],
        },
        headers={"X-Adapter-Secret": "top-secret"},
    )

    run = session.scalar(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance_id)
        .order_by(AdapterRun.id.desc())
        .limit(1)
    )
    raw_event = session.scalar(select(HesEventRaw).order_by(HesEventRaw.id.desc()).limit(1))

    assert response.status_code == 201
    assert response.get_json()["raw_events_received"] == 1
    assert run is not None
    assert run.run_status == "completed"
    assert raw_event is not None
    assert raw_event.ingest_batch.adapter_run_id == run.id


def test_receive_reads_endpoint_rejects_invalid_secret(client, session, monkeypatch):
    seed_master_data(session)
    monkeypatch.setenv("MDMS_RECEIVE_SECRET", "top-secret")
    instance = _create_receive_adapter(
        session,
        instance_code="receive_reads_locked",
        record_type="hes_read_raw",
    )
    instance_id = instance.id
    instance_code = instance.instance_code
    session.commit()

    response = client.post(
        f"/api/v1/receive/{instance_code}/reads",
        json={
            "contract_version": "v1",
            "batch_id": "receive-read-unauthorized",
            "received_at": "2026-04-24T09:00:00+09:00",
            "reads": [],
        },
        headers={"X-Adapter-Secret": "wrong-secret"},
    )

    run = session.scalar(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance_id)
        .limit(1)
    )

    assert response.status_code == 403
    assert response.get_json()["error_code"] == "receive_adapter_unauthorized"
    assert run is None
