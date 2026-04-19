from __future__ import annotations

from sqlalchemy import func, select

from app.models import HesEventRaw, HesReadRaw, IngestBatch, IngestErrorLog
from app.services.seeds import seed_master_data


def _base_read_payload() -> dict:
    return {
        "contract_version": "v1",
        "source_system": "HES",
        "batch_id": "contract-read-batch",
        "received_at": "2026-04-19T09:00:00+09:00",
        "reads": [],
    }


def _base_event_payload() -> dict:
    return {
        "contract_version": "v1",
        "source_system": "HES",
        "batch_id": "contract-event-batch",
        "received_at": "2026-04-19T09:05:00+09:00",
        "events": [],
    }


def test_ingest_reads_rejects_missing_envelope_identifier(client):
    payload = {
        "contract_version": "v1",
        "source_system": "HES",
        "reads": [],
    }

    response = client.post("/api/v1/ingest/reads", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "missing_envelope_identifier",
        "message": "Either batch_id or message_id is required.",
        "locale": "en",
        "details": "Either batch_id or message_id is required.",
    }


def test_ingest_reads_rejects_invalid_locale_in_korean_request_context(client):
    payload = _base_read_payload() | {"locale": "jp"}

    response = client.post(
        "/api/v1/ingest/reads?lang=ko",
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_locale",
        "message": "locale 값은 en 또는 ko 여야 합니다.",
        "locale": "ko",
        "details": "Locale must be en or ko.",
    }


def test_ingest_reads_rejects_unsupported_adapter_key(client):
    payload = _base_read_payload() | {"adapter_key": "unknown_v1"}

    response = client.post("/api/v1/ingest/reads", json=payload)

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "unsupported_adapter_key",
        "message": "Adapter key is not supported for this ingest request.",
        "locale": "en",
        "details": "Adapter key 'unknown_v1' is not supported for raw reads.",
    }


def test_ingest_reads_rejects_duplicate_envelope_idempotently(client, session):
    seed_master_data(session)
    session.commit()

    payload = _base_read_payload() | {
        "reads": [
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measurement_ts": "2026-04-19T00:15:00+09:00",
                "value": 10.0,
                "unit_of_measure": "kWh",
            }
        ]
    }

    first_response = client.post("/api/v1/ingest/reads", json=payload)
    second_response = client.post("/api/v1/ingest/reads", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.get_json()["error_code"] == "duplicate_ingest_request"
    assert session.scalar(select(func.count()).select_from(IngestBatch)) == 1


def test_ingest_reads_records_invalid_measurement_timestamp_as_exception(client, session):
    seed_master_data(session)
    session.commit()

    payload = _base_read_payload() | {
        "batch_id": "contract-read-invalid-ts",
        "reads": [
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measurement_ts": "2026-04-19T00:15:00",
                "value": 10.0,
                "unit_of_measure": "kWh",
            }
        ],
    }

    response = client.post("/api/v1/ingest/reads", json=payload)

    error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "invalid_timestamp")
        .limit(1)
    )
    raw_row = session.scalar(select(HesReadRaw).limit(1))

    assert response.status_code == 201
    assert response.get_json()["exceptions"] == 1
    assert error is not None
    assert raw_row is not None
    assert raw_row.canonical_status == "exception"


def test_ingest_reads_records_invalid_numeric_value_as_exception(client, session):
    seed_master_data(session)
    session.commit()

    payload = _base_read_payload() | {
        "batch_id": "contract-read-invalid-value",
        "reads": [
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measurement_ts": "2026-04-19T00:15:00+09:00",
                "value": "bad-number",
                "unit_of_measure": "kWh",
            }
        ],
    }

    response = client.post("/api/v1/ingest/reads", json=payload)

    error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "invalid_numeric_value")
        .limit(1)
    )

    assert response.status_code == 201
    assert response.get_json()["exceptions"] == 1
    assert error is not None


def test_ingest_events_records_invalid_event_timestamp_as_exception(client, session):
    payload = _base_event_payload() | {
        "batch_id": "contract-event-invalid-ts",
        "events": [
            {
                "meter_id": "MTR-1001",
                "event_ts": "2026-04-19T00:00:00",
                "event_code": "POWER_FAIL",
                "severity": "high",
            }
        ],
    }

    response = client.post("/api/v1/ingest/events", json=payload)

    error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "invalid_timestamp")
        .limit(1)
    )
    raw_event = session.scalar(select(HesEventRaw).limit(1))

    assert response.status_code == 201
    assert response.get_json()["exceptions"] == 1
    assert error is not None
    assert raw_event is not None
    assert raw_event.event_time is None


def test_ingest_events_accepts_legacy_adapter_mapping(client, session):
    payload = _base_event_payload() | {
        "adapter_key": "legacy_hes_v1",
        "batch_id": "contract-event-legacy-adapter",
        "events": [
            {
                "mtr_no": "MTR-1001",
                "event_time": "2026-04-19T00:00:00+09:00",
                "event_id": "POWER_FAIL",
                "severity": "high",
                "origin": "meter",
            }
        ],
    }

    response = client.post("/api/v1/ingest/events", json=payload)

    raw_event = session.scalar(select(HesEventRaw).order_by(HesEventRaw.id.desc()).limit(1))
    assert response.status_code == 201
    assert response.get_json()["raw_events_received"] == 1
    assert response.get_json()["exceptions"] == 0
    assert raw_event is not None
    assert raw_event.meter_identifier == "MTR-1001"
    assert raw_event.event_code == "POWER_FAIL"
    assert raw_event.payload["event_id"] == "POWER_FAIL"
