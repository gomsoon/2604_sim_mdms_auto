from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import (
    AdapterInstance,
    EstimationAudit,
    HesSystem,
    IngestBatch,
    InitialMeasurement,
    ManualEditAudit,
    OperationalEvent,
    UserAccount,
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


def test_operational_events_page_shows_baseline_empty_guidance(client):
    response = client.get("/operational-events?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 기록된 운영 이벤트가 없습니다." in text
    assert "적재, 처리, 런타임 경고나 알림이 발생하면 여기서 확인합니다." in text


def test_operational_events_page_shows_filtered_empty_guidance(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/operational-events?lang=ko&event_code=no-such-event")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 운영 이벤트가 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


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


def test_operational_event_detail_page_shows_missing_context_guidance(client, session):
    seed_demo_environment(session)
    session.commit()

    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    adapter_instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary").limit(1)
    )
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert actor is not None
    assert adapter_instance is not None
    assert hes_system is not None

    event = record_operational_event(
        session,
        "adapter_enabled",
        hes_system=hes_system,
        adapter_instance=adapter_instance,
        details={
            "acted_by": actor.login_id,
            "acted_by_user_account_id": actor.id,
            "previous_admin_state": "paused",
            "target_admin_state": "enabled",
        },
        instance_code=adapter_instance.instance_code,
    )
    session.commit()

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "조치 스냅샷" in text
    assert "조치 주체" in text
    assert "Test Admin (admin)" in text
    assert "사람 계정" in text
    assert "인스턴스 코드" in text
    assert "demo_hes_poll_primary" in text
    assert "이전 상태" in text
    assert "일시중지" in text
    assert "요청 상태" in text
    assert "활성" in text
    assert "이 이벤트와 연결된 원시 검침이 없습니다." in text
    assert "이 경우는 특정 원시 검침 한 건보다 런타임 또는 처리 상태를 설명하는 이벤트일 가능성이 큽니다." in text
    assert "관련 원시 검침에서 생성된 표준 계측이 없습니다." in text
    assert "표준화가 아직 실행되지 않았거나, 표준 계측이 생성되기 전에 기록된 이벤트일 수 있습니다." in text
    assert "관련 표준 계측에서 생성된 최종 계측이 없습니다." in text
    assert "최종화가 아직 실행되지 않았거나, downstream 처리가 끝나기 전에 기록된 이벤트일 수 있습니다." in text
    assert "acted_by_user_account_id" in text
    assert "previous_admin_state" in text


def test_operational_event_detail_page_shows_runtime_action_snapshot(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    adapter_instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary").limit(1)
    )
    assert hes_system is not None
    assert adapter_instance is not None

    event = record_operational_event(
        session,
        "adapter_run_queued",
        hes_system=hes_system,
        adapter_instance=adapter_instance,
        details={
            "requested_by": "scheduler",
            "requested_by_user_account_id": None,
            "trigger_type": "schedule",
        },
        instance_code=adapter_instance.instance_code,
    )
    session.commit()

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "조치 스냅샷" in text
    assert "scheduler" in text
    assert "런타임 주체" in text
    assert "실행 유형" in text
    assert "schedule" in text
    assert "demo_hes_poll_primary" in text


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


def test_dashboard_page_shows_composite_empty_guidance(client):
    response = client.get("/?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "적재된 원시 검침이 없습니다." in text
    assert "어댑터나 적재 파이프라인이 원시 검침을 불러오면 최신 항목이 여기에 표시됩니다." in text
    assert "현재 열린 알림이 없습니다." in text
    assert "현재 대시보드에서 바로 조치할 알림이 없는 조용한 상태입니다." in text
    assert "기록된 최근 보정 감사가 없습니다." in text
    assert "VEE 큐에서 추정 또는 수동 보정을 적용한 뒤 최근 보정 감사를 여기서 확인합니다." in text


def test_dashboard_page_shows_correction_policy_spotlight_and_recent_audits(client, session):
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert initial is not None

    baseline_exception = VeeException(
        initial_measurement_id=initial.id,
        exception_code="vee_zero_value_detected",
        severity="warning",
        exception_status="open",
        blocking_finalization=False,
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        details={},
    )
    tamper_exception = VeeException(
        initial_measurement_id=initial.id,
        exception_code="vee_high_value_detected",
        severity="error",
        exception_status="open",
        blocking_finalization=True,
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        details={
            "event_context_snapshot": {
                "primary_context_type": "tamper",
                "matched_context_types": ["tamper"],
            }
        },
    )
    outage_exception = VeeException(
        initial_measurement_id=initial.id,
        exception_code="vee_missing_interval_detected",
        severity="error",
        exception_status="acknowledged",
        blocking_finalization=True,
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        details={
            "event_context_snapshot": {
                "primary_context_type": "outage",
                "matched_context_types": ["outage"],
            }
        },
    )
    session.add_all([baseline_exception, tamper_exception, outage_exception])
    session.flush()
    session.add_all(
        [
            EstimationAudit(
                service_point_id=initial.service_point_id,
                measuring_component_id=initial.measuring_component_id,
                device_id=initial.device_id,
                target_initial_measurement_id=initial.id,
                target_measured_at=initial.measured_at,
                strategy_code="previous_value_based",
                estimation_status="blocked",
                estimated_value=None,
                unit_of_measure=initial.unit_of_measure,
                operator_memo="blocked by tamper policy",
                details={
                    "correction_policy_snapshot": {
                        "policy_reason_code": "tamper_correlated_value_anomaly",
                        "recommended_action": "operator_investigation_then_manual_edit",
                    }
                },
            ),
            ManualEditAudit(
                service_point_id=initial.service_point_id,
                measuring_component_id=initial.measuring_component_id,
                device_id=initial.device_id,
                target_initial_measurement_id=initial.id,
                related_vee_exception_id=baseline_exception.id,
                target_measured_at=initial.measured_at,
                reason_code="operator_meter_correction",
                edit_status="applied",
                edited_value=initial.value,
                edited_by="operator_dashboard",
                operator_memo="manual correction confirmed",
                details={
                    "correction_policy_snapshot": {
                        "policy_reason_code": "no_event_specific_override",
                        "recommended_action": "follow_existing_baseline",
                    }
                },
            ),
        ]
    )
    session.commit()

    manual_audit = session.scalar(select(ManualEditAudit).order_by(ManualEditAudit.id.desc()).limit(1))
    estimation_audit = session.scalar(
        select(EstimationAudit).order_by(EstimationAudit.id.desc()).limit(1)
    )
    assert manual_audit is not None
    assert estimation_audit is not None

    response = client.get("/?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "보정 정책 스포트라이트" in text
    assert "이벤트 기반 보정 override가 적용되지 않습니다" in text
    assert "변조 연계 값 이상은 시스템 추정보다 운영자 확인이 우선입니다" in text
    assert "정전 연계 구간 누락은 아직 1차 보정 경로가 지원되지 않습니다" in text
    assert "/vee-exceptions?lang=ko&amp;exception_status=active&amp;policy_reason_code=tamper_correlated_value_anomaly" in text
    assert "최근 보정 감사" in text
    assert f"/manual-edit-audits/{manual_audit.id}?lang=ko" in text
    assert f"/estimation-audits/{estimation_audit.id}?lang=ko" in text
