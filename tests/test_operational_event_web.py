from __future__ import annotations

from sqlalchemy import select

from app.models import (
    HesSystem,
    IngestBatch,
    InitialMeasurement,
    OperationalEvent,
    UsageTransaction,
    VeeException,
    VeeReplayRequest,
)
from app.services.operational_events import record_operational_event
from app.services.processing_replay import reevaluate_vee_exception_and_replay
from app.services.seeds import seed_demo_environment
from app.services.vee import evaluate_or_get_vee_baseline


def _get_open_alert(session):
    return session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.is_alert.is_(True), OperationalEvent.alert_status == "open")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )


def _create_usage_recalculation_event(session) -> tuple[OperationalEvent, list[UsageTransaction]]:
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

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert vee_exception is not None

    initial.unit_of_measure = "kWh"
    session.commit()

    reevaluate_vee_exception_and_replay(
        session,
        vee_exception.id,
        reevaluated_by="operator_ui",
    )
    session.commit()

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "usage_recalculated_after_vee")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    usage_rows = session.scalars(select(UsageTransaction).order_by(UsageTransaction.id.asc())).all()
    assert event is not None
    assert usage_rows
    return event, usage_rows


def test_dashboard_acknowledge_alert_via_web_updates_alert_status_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    client.get("/?lang=ko")

    alert = _get_open_alert(session)
    assert alert is not None

    response = client.post(
        f"/operational-events/{alert.id}/acknowledge",
        data={"next": "/?lang=ko"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    updated = session.get(OperationalEvent, alert.id)

    assert response.status_code == 200
    assert "알림이 확인 상태로 변경되었습니다." in text
    assert updated is not None
    assert updated.alert_status == "acknowledged"
    assert updated.acknowledged_by == "operator_ui"
    assert updated.acknowledged_at is not None


def test_dashboard_close_alert_via_web_stores_operator_memo(client, session):
    seed_demo_environment(session)
    session.commit()

    alert = _get_open_alert(session)
    assert alert is not None

    response = client.post(
        f"/operational-events/{alert.id}/close",
        data={
            "next": "/",
            "operator_memo": "Reviewed and handed off to operations.",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    updated = session.get(OperationalEvent, alert.id)

    assert response.status_code == 200
    assert "Alert has been closed." in text
    assert updated is not None
    assert updated.alert_status == "closed"
    assert updated.closed_at is not None
    assert updated.operator_memo == "Reviewed and handed off to operations."


def test_operational_events_page_filters_by_hes_system(client, session):
    seed_demo_environment(session)
    session.commit()

    demo_hes = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert demo_hes is not None

    other_hes = HesSystem(
        hes_code="OTHER_HES_WEB",
        display_name="Other Web HES",
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
        instance_code="other_web_adapter",
    )
    session.commit()

    response = client.get(f"/operational-events?hes_system_id={demo_hes.id}&lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Demo HES" in text
    assert "other_web_adapter" not in text
    assert f'value="{demo_hes.id}" selected' in text


def test_operational_event_detail_page_links_to_usage_transactions(client, session):
    event, usage_rows = _create_usage_recalculation_event(session)

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "관련 사용량 재계산" in text
    assert "일별 사용량" in text
    assert "월별 사용량" in text
    for row in usage_rows:
        assert f"/usage-transactions/{row.id}?lang=ko" in text


def test_dashboard_page_lists_recent_recalculated_usage(client, session):
    _, usage_rows = _create_usage_recalculation_event(session)

    response = client.get("/?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최근 재계산 사용량" in text
    for row in usage_rows:
        assert f"/usage-transactions/{row.id}?lang=ko" in text


def test_dashboard_page_lists_recent_vee_replay_requests(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    ingest_batch = session.scalar(
        select(IngestBatch).where(IngestBatch.batch_id == "demo-read-batch").limit(1)
    )
    assert hes_system is not None
    assert ingest_batch is not None

    queued_request = VeeReplayRequest(
        request_scope="hes_system",
        status="queued",
        requested_by="operator_dashboard",
        hes_system_id=hes_system.id,
        target_initial_count=3,
        details={"progress_percent": 0},
    )
    processing_request = VeeReplayRequest(
        request_scope="ingest_batch",
        status="processing",
        requested_by="operator_dashboard",
        ingest_batch_id=ingest_batch.id,
        target_initial_count=4,
        processed_count=2,
        details={"progress_percent": 50},
    )
    session.add_all([queued_request, processing_request])
    session.commit()

    response = client.get("/?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최근 VEE 재평가 요청" in text
    assert f"/vee-replay-requests/{queued_request.id}" in text
    assert f"/vee-replay-requests/{processing_request.id}" in text
    assert "0% (0/3)" in text
    assert "50% (2/4)" in text
