from __future__ import annotations

from sqlalchemy import func, select

from app.models import FinalMeasurement, OperationalEvent
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.operational_events import close_operational_alert
from app.services.seeds import seed_demo_environment
from app.services.usage import calculate_usage_transactions


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


def test_usage_transactions_page_filters_by_service_point_and_channel(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    response = client.get(
        "/usage-transactions?lang=ko&service_point=SP-1001&external_channel_id=CH-01&usage_type=daily_consumption"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "사용량 거래" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "일별 사용량" in text


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


def test_operational_events_page_filters_closed_alerts_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    response = client.get(
        "/api/v1/operational-events?stream_type=alert&event_code=canonical_failed&batch_id=demo-read-batch"
    )
    alert_id = response.get_json()[0]["id"]
    close_operational_alert(session, alert_id)
    session.commit()

    response = client.get(
        "/operational-events?lang=ko&stream_type=alert&alert_status=closed&batch_id=demo-read-batch"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "운영 이벤트" in text
    assert "표준화 주의 필요" in text
    assert "종료됨" in text
    assert "demo-read-batch" in text


def test_operational_events_page_includes_detail_link(client, session):
    seed_demo_environment(session)
    session.commit()

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "canonical_failed")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert event is not None

    response = client.get("/operational-events?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"/operational-events/{event.id}?lang=ko" in text


def test_operational_event_detail_page_shows_lineage_and_related_measurements(client, session):
    seed_demo_environment(session)
    session.commit()

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "canonical_failed")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert event is not None

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "운영 이벤트 상세" in text
    assert "표준화 주의 필요" in text
    assert "Lineage" in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert "관련 원시 검침" in text
    assert "관련 표준 계측" in text


def test_operational_event_detail_page_links_to_vee_exception_lineage(client, session):
    from app.models import InitialMeasurement
    from app.services.vee import evaluate_or_get_vee_baseline

    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None
    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    initial.unit_of_measure = ""
    session.flush()
    evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "vee_exception_opened")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert event is not None

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 예외" in text
    assert f"/vee-exceptions/{event.entity_id}?lang=ko" in text


def test_operational_events_api_rejects_invalid_stream_type_in_korean(client):
    response = client.get("/api/v1/operational-events?lang=ko&stream_type=alerts")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_stream_type",
        "message": "조회 유형은 event 또는 alert 여야 합니다.",
        "locale": "ko",
    }


def test_operational_events_api_returns_filtered_closed_alert(client, session):
    seed_demo_environment(session)
    session.commit()
    response = client.get(
        "/api/v1/operational-events?stream_type=alert&event_code=canonical_failed&batch_id=demo-read-batch"
    )
    alert_id = response.get_json()[0]["id"]
    close_operational_alert(session, alert_id)
    session.commit()

    response = client.get(
        "/api/v1/operational-events?stream_type=alert&alert_status=closed&batch_id=demo-read-batch"
    )

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["event_code"] == "canonical_failed"
    assert row["is_alert"] is True
    assert row["alert_status"] == "closed"
    assert row["batch_id"] == "demo-read-batch"
