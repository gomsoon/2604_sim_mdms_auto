from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AdapterInstance, HesSystem, OperationalEvent
from app.services.seeds import seed_demo_environment


def test_hes_systems_page_renders_seeded_registry_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/hes-systems?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "HES 시스템" in text
    assert "HES" in text
    assert "Company HES Poll Primary" not in text


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

    assert response.status_code == 200
    assert "HES system created successfully." in response.get_data(as_text=True)
    assert hes_system is not None
    assert hes_system.display_name == "AIMIR Overseas HES"
    assert hes_system.default_delivery_mode == "poll"


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

    assert response.status_code == 200
    assert "HES system updated successfully." in response.get_data(as_text=True)
    assert updated is not None
    assert updated.display_name == "Updated Demo HES"
    assert updated.status == "inactive"


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
