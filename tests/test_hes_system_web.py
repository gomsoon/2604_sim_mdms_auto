from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import (
    AdapterInstance,
    BillDeterminant,
    HesSystem,
    IngestBatch,
    InitialMeasurement,
    OperationalEvent,
    UsageTransaction,
    UserAccount,
    VeeException,
    VeeReplayRequest,
)
from app.services.processing_replay import reevaluate_vee_exception_and_replay
from app.services.bill_determinants import calculate_bill_determinants
from app.services.seeds import seed_demo_environment
from app.services.vee import evaluate_or_get_vee_baseline


def test_hes_systems_page_renders_seeded_registry_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/hes-systems?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "HES 시스템" in text
    assert "HES" in text
    assert "Company HES Poll Primary" not in text


def test_hes_systems_page_shows_baseline_empty_guidance(client):
    response = client.get("/hes-systems?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 등록된 HES 시스템이 없습니다." in text
    assert "오른쪽 등록 폼에서 첫 HES 시스템을 추가하세요." in text


def test_create_hes_system_via_web_creates_registry_entry(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.post(
        "/hes-systems",
        data={
            "hes_code": "AIMIR_OVERSEAS",
            "display_name": "AIMIR Overseas HES",
            "vendor_name": "NURI",
            "source_family": "hes",
            "default_delivery_mode": "poll",
            "status": "active",
            "timezone_name": "Asia/Seoul",
            "description": "Primary overseas AMI HES",
            "connection_config_masked": '{"host": "172.16.10.111", "port": 1521}',
        },
        follow_redirects=True,
    )

    hes_system = session.scalar(
        select(HesSystem).where(HesSystem.hes_code == "AIMIR_OVERSEAS").limit(1)
    )
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "HES system created successfully." in response.get_data(as_text=True)
    assert hes_system is not None
    assert actor is not None
    assert hes_system.display_name == "AIMIR Overseas HES"
    assert hes_system.default_delivery_mode == "poll"
    assert hes_system.created_by_user_account_id == actor.id
    assert hes_system.updated_by_user_account_id == actor.id


def test_create_hes_system_via_web_rejects_invalid_json_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    client.get("/hes-systems?lang=ko")

    response = client.post(
        "/hes-systems",
        data={
            "hes_code": "BAD_JSON_HES",
            "display_name": "Bad JSON HES",
            "vendor_name": "",
            "source_family": "hes",
            "default_delivery_mode": "",
            "status": "active",
            "timezone_name": "",
            "description": "",
            "connection_config_masked": "not-json",
        },
        follow_redirects=True,
    )

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "BAD_JSON_HES").limit(1))

    assert response.status_code == 200
    assert "마스킹된 연결 설정은 유효한 JSON 객체여야 합니다." in response.get_data(as_text=True)
    assert hes_system is None


def test_hes_system_detail_page_renders_linked_adapter_and_recent_batch(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.get(f"/hes-systems/{hes_system.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "연결된 어댑터" in text
    assert "Demo HES Poll Primary" in text
    assert "demo-read-batch" in text
    assert "최근 적재" in text
    assert "최근 이벤트" in text
    assert "사용량 요약" in text
    assert "계량기 참조" in text
    assert "정상 매핑" in text
    assert "장치 누락" in text


def test_hes_system_detail_page_renders_recent_alerts_and_events(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    recent_event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.hes_system_id == hes_system.id)
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(1)
    )
    open_alert = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.hes_system_id == hes_system.id,
            OperationalEvent.is_alert.is_(True),
            OperationalEvent.alert_status.in_(("open", "acknowledged")),
        )
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(1)
    )

    assert hes_system is not None
    assert recent_event is not None
    assert open_alert is not None

    response = client.get(f"/hes-systems/{hes_system.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최근 알림" in text
    assert "최근 이벤트" in text
    assert open_alert.event_code in text
    assert recent_event.event_code in text
    assert f"/operational-events?hes_system_id={hes_system.id}" in text


def test_hes_system_detail_page_shows_composite_empty_guidance(client, session):
    hes_system = HesSystem(
        hes_code="EMPTY_DETAIL_HES",
        display_name="Empty Detail HES",
        source_family="hes",
        status="active",
    )
    session.add(hes_system)
    session.commit()

    response = client.get(f"/hes-systems/{hes_system.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이 HES 시스템에 연결된 어댑터가 없습니다." in text
    assert "이 HES 시스템에 어댑터를 등록하거나 연결한 뒤 여기서 런타임 상태를 확인합니다." in text
    assert "이 HES 시스템의 적재 배치 이력이 없습니다." in text
    assert "이 HES 시스템으로 적재 배치가 들어오면 최신 배치 이력이 여기에 표시됩니다." in text
    assert "이 HES 시스템에 연결된 열린 알림이 없습니다." in text
    assert "현재 검토가 필요한 열린 알림이 없다는 뜻입니다." in text


def test_hes_system_detail_page_lists_recent_recalculated_usage(client, session):
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

    usage_row = session.scalar(select(UsageTransaction).order_by(UsageTransaction.id.asc()).limit(1))
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert usage_row is not None
    assert hes_system is not None

    response = client.get(f"/hes-systems/{hes_system.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "사용량 요약" in text
    assert "최근 사용량 재계산" in text
    assert f"/usage-transactions/{usage_row.id}?lang=ko" in text


def test_hes_system_detail_page_lists_recent_bill_determinants(client, session):
    seed_demo_environment(session)
    session.commit()

    from app.services.finalization import finalize_canonical_measurements
    from app.services.usage import calculate_usage_transactions

    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    determinant = session.scalar(select(BillDeterminant).limit(1))
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert determinant is not None
    assert hes_system is not None

    response = client.get(f"/hes-systems/{hes_system.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 결정값 요약" in text
    assert "최근 current 청구 결정값" in text
    assert f"/bill-determinants/{determinant.id}?lang=ko" in text
    assert "/bill-determinants?" in text
    assert f"hes_system_id={hes_system.id}" in text


def test_hes_system_detail_page_lists_recent_vee_replay_requests(client, session):
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
        requested_by="operator_ui",
        hes_system_id=hes_system.id,
        target_initial_count=3,
        details={"progress_percent": 0},
    )
    failed_request = VeeReplayRequest(
        request_scope="ingest_batch",
        status="failed",
        requested_by="operator_ui",
        ingest_batch_id=ingest_batch.id,
        target_initial_count=2,
        processed_count=2,
        failed_count=1,
        details={"progress_percent": 100},
    )
    session.add_all([queued_request, failed_request])
    session.commit()

    response = client.get(f"/hes-systems/{hes_system.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 재평가 요약" in text
    assert "진행 중 재평가 요청" in text
    assert "실패한 재평가 요청" in text
    assert f"/vee-replay-requests/{queued_request.id}?lang=ko" in text
    assert f"/vee-replay-requests/{failed_request.id}?lang=ko" in text


def test_hes_meter_references_page_renders_comparison_rows(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.get(f"/hes-systems/{hes_system.id}/meter-references?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "HES 계량기 참조" in text
    assert "원본 계량기 ID" in text
    assert "AIMIR-32418" in text
    assert "MTR-1001" in text
    assert "정상 매핑" in text
    assert "컴포넌트 누락" in text
    assert "설치 누락" in text
    assert "장치 누락" in text
    assert "권장 조치" in text
    assert "장치 생성" in text
    assert "컴포넌트 생성" in text
    assert "설치 이력 생성" in text
    assert "매핑 검토" in text


def test_hes_meter_references_page_filters_by_comparison_status(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.get(
        f"/hes-systems/{hes_system.id}/meter-references?lang=ko&comparison_status=missing_device"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MTR-4040" in text
    assert "AIMIR-32418" not in text


def test_hes_meter_references_page_shows_baseline_empty_guidance(client, session):
    hes_system = HesSystem(
        hes_code="EMPTY_WEB_HES",
        display_name="Empty Web HES",
        source_family="hes",
        status="active",
    )
    session.add(hes_system)
    session.commit()

    response = client.get(f"/hes-systems/{hes_system.id}/meter-references?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이 HES 시스템에 연결된 계량기 참조가 아직 없습니다." in text
    assert "계량기 참조 동기화 이후 매핑 비교 결과를 여기서 확인합니다." in text


def test_hes_meter_references_page_shows_filtered_empty_guidance(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.get(
        f"/hes-systems/{hes_system.id}/meter-references?lang=ko&meter_query=NO-SUCH-METER"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 HES 계량기 참조가 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


def test_hes_meter_references_page_offers_master_data_bootstrap_link(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.get(f"/hes-systems/{hes_system.id}/meter-references?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "마스터 데이터 열기" in text
    assert "prefill_source_system=HES" in text
    assert "prefill_external_meter_id=AIMIR-4040" in text


def test_update_hes_system_via_web_updates_registry(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.post(
        f"/hes-systems/{hes_system.id}",
        data={
            "hes_code": "HES",
            "display_name": "Updated Demo HES",
            "vendor_name": "NURI",
            "source_family": "hes",
            "default_delivery_mode": "poll",
            "status": "inactive",
            "timezone_name": "Asia/Seoul",
            "description": "Updated from operator UI",
            "connection_config_masked": '{"host": "hes.local"}',
        },
        follow_redirects=True,
    )

    updated = session.get(HesSystem, hes_system.id)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "HES system updated successfully." in response.get_data(as_text=True)
    assert updated is not None
    assert actor is not None
    assert updated.display_name == "Updated Demo HES"
    assert updated.status == "inactive"
    assert updated.updated_by_user_account_id == actor.id


def test_adapters_page_shows_parent_hes_link(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/adapters")
    text = response.get_data(as_text=True)

    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    assert response.status_code == 200
    assert "Demo HES" in text
    assert f"/hes-systems/{instance.hes_system_id}" in text


def test_hes_systems_page_renders_runtime_health_summary(client, session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary"))
    assert instance is not None

    as_of = datetime.now(timezone.utc)
    instance.next_run_at = as_of - timedelta(minutes=30)
    instance.last_heartbeat_at = as_of - timedelta(minutes=30)
    session.commit()

    response = client.get("/hes-systems?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "상태 요약" in text
    assert "실행 중: 0" in text
    assert "실행 지연: 1" in text
    assert "신선도 저하: 1" in text
