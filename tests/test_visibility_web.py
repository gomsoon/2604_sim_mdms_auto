from __future__ import annotations

from sqlalchemy import func, select

from app.models import FinalMeasurement
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_demo_environment


def test_ingest_batches_page_renders_filtered_results_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/ingest-batches?lang=ko&record_type=hes_event_raw")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "적재 배치" in text
    assert "demo-event-batch" in text
    assert "원시 이벤트" in text


def test_canonical_measurements_page_filters_by_batch_and_meter(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/canonical-measurements?batch_id=demo-read-batch&meter_id=MTR-1001")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert "CH-01" in text


def test_ingest_batches_api_rejects_invalid_date_range_in_korean(client):
    response = client.get(
        "/api/v1/ingest-batches?lang=ko&date_from=2026-04-19&date_to=2026-04-18"
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_date_range",
        "message": "시작일은 종료일보다 늦을 수 없습니다.",
        "locale": "ko",
    }


def test_canonical_measurements_api_returns_filtered_measurement(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get(
        "/api/v1/canonical-measurements?batch_id=demo-read-batch&meter_id=MTR-1001"
    )

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["id"] == 1
    assert row["batch_id"] == "demo-read-batch"
    assert row["source_system"] == "HES"
    assert row["meter_id"] == "MTR-1001"
    assert row["channel_id"] == "CH-01"
    assert row["measured_at"].startswith("2026-04-18T00:15:00")
    assert row["value"] == 14.2
    assert row["unit_of_measure"] == "kWh"
    assert row["service_point_id"] == 1
    assert row["device_id"] == 1


def test_final_measurements_page_filters_by_batch_and_meter(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    response = client.get("/final-measurements?lang=ko&batch_id=demo-read-batch&meter_id=MTR-1001")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최종 계측" in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert "최종화" in text


def test_final_measurements_api_returns_filtered_measurement(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    response = client.get("/api/v1/final-measurements?batch_id=demo-read-batch&meter_id=MTR-1001")

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["batch_id"] == "demo-read-batch"
    assert row["source_system"] == "HES"
    assert row["meter_id"] == "MTR-1001"
    assert row["channel_id"] == "CH-01"
    assert row["value"] == 14.2
    assert row["unit_of_measure"] == "kWh"
    assert row["final_status"] == "finalized"


def test_canonical_measurements_promote_final_via_web_uses_current_filters(client, session):
    seed_demo_environment(session)
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "demo-read-batch-2",
            "received_at": "2026-04-19T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-19T00:15:00+09:00",
                    "value": 18.4,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    response = client.post(
        "/canonical-measurements/promote-final?lang=ko",
        data={
            "batch_id": "demo-read-batch",
            "meter_id": "MTR-1001",
            "date_from": "2026-04-18",
            "date_to": "2026-04-18",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최종 계측 승격이 완료되었습니다." in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 1


def test_canonical_measurements_promote_final_rejects_invalid_date_range_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.post(
        "/canonical-measurements/promote-final?lang=ko",
        data={
            "batch_id": "demo-read-batch",
            "meter_id": "MTR-1001",
            "date_from": "2026-04-19",
            "date_to": "2026-04-18",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "시작일은 종료일보다 늦을 수 없습니다." in text
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0
