from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import AdapterDefinition, AdapterInstance, AdapterRun, HesSystem, OperationalEvent, UserAccount
from app.services.seeds import seed_demo_environment


def test_adapters_page_renders_seeded_runtime_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/adapters?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "런타임 어댑터" in text
    assert "Demo HES Poll Primary" in text
    assert "준비됨" in text


def test_adapters_page_shows_baseline_empty_guidance(client):
    response = client.get("/adapters?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 등록된 어댑터 인스턴스가 없습니다." in text
    assert "지원되는 어댑터를 등록한 뒤 여기서 상태를 확인합니다." in text


def test_pause_and_enable_adapter_via_web_updates_admin_state(client, session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    pause_response = client.post(
        f"/adapters/{instance.id}/pause",
        data={"next": f"/adapters/{instance.id}"},
        follow_redirects=True,
    )
    enable_response = client.post(
        f"/adapters/{instance.id}/enable",
        data={"next": f"/adapters/{instance.id}"},
        follow_redirects=True,
    )

    updated = session.get(AdapterInstance, instance.id)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert pause_response.status_code == 200
    assert "Adapter instance paused successfully." in pause_response.get_data(as_text=True)
    assert enable_response.status_code == 200
    assert "Adapter instance enabled successfully." in enable_response.get_data(as_text=True)
    assert updated is not None
    assert actor is not None
    assert updated.admin_state == "enabled"
    assert updated.updated_by_user_account_id == actor.id
    latest_event = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.adapter_instance_id == instance.id,
            OperationalEvent.event_code == "adapter_enabled",
        )
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert latest_event is not None
    assert latest_event.details["acted_by"] == actor.login_id
    assert latest_event.details["acted_by_user_account_id"] == actor.id


def test_run_adapter_once_via_web_creates_waiting_run_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    client.get("/adapters?lang=ko")

    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    response = client.post(
        f"/adapters/{instance.id}/run-once",
        data={"next": f"/adapters/{instance.id}"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    run = session.scalar(select(AdapterRun).order_by(AdapterRun.id.desc()).limit(1))

    assert response.status_code == 200
    assert "수동 어댑터 실행 요청이 대기열에 등록되었습니다." in text
    assert "대기" in text
    assert actor is not None
    assert run is not None
    assert run.requested_by == actor.login_id
    assert run.requested_by_user_account_id == actor.id
    assert "Test Admin (admin)" in text
    assert "사람 계정" in text
    assert session.scalar(select(func.count()).select_from(AdapterRun)) == 2


def test_adapters_page_shows_overdue_and_stale_badges_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    instance.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    instance.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=20)
    session.commit()

    response = client.get("/adapters?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "실행 지연" in text
    assert "신선도 저하" in text


def test_new_adapter_page_renders_active_definition(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/adapters/new?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "어댑터 인스턴스 등록" in text
    assert "Company HES Poll" in text


def test_new_adapter_page_from_hes_context_prefills_parent_hes(client, session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert hes_system is not None

    response = client.get(f"/hes-systems/{hes_system.id}/adapters/new?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "HES 시스템" in text
    assert "Demo HES (HES)" in text


def test_new_adapter_page_from_missing_hes_context_returns_404(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/hes-systems/999999/adapters/new")

    assert response.status_code == 404


def test_create_adapter_via_web_creates_runtime_instance(client, session):
    seed_demo_environment(session)
    session.commit()

    definition = session.scalar(select(AdapterDefinition).limit(1))
    assert definition is not None

    response = client.post(
        "/adapters",
        data={
            "adapter_definition_id": str(definition.id),
            "instance_code": "company_hes_poll_web",
            "display_name": "Company HES Poll Web",
            "source_system": "HES",
            "poll_interval_minutes": "15",
            "batch_size": "300",
            "secret_ref": "env://WEB",
            "connection_config_masked": '{"host": "hes-web.internal"}',
            "landing_enabled": "on",
        },
        follow_redirects=True,
    )

    instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "company_hes_poll_web").limit(1)
    )
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "Adapter instance created successfully." in response.get_data(as_text=True)
    assert instance is not None
    assert actor is not None
    assert instance.landing_enabled is True
    assert instance.poll_interval_minutes == 15
    assert instance.created_by_user_account_id == actor.id
    assert instance.updated_by_user_account_id == actor.id


def test_create_adapter_via_hes_context_keeps_parent_hes_lineage(client, session):
    seed_demo_environment(session)
    session.commit()

    definition = session.scalar(select(AdapterDefinition).limit(1))
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert definition is not None
    assert hes_system is not None

    response = client.post(
        "/adapters",
        data={
            "hes_system_id": str(hes_system.id),
            "adapter_definition_id": str(definition.id),
            "instance_code": "company_hes_poll_hes_context",
            "display_name": "Company HES Poll HES Context",
            "source_system": "HES",
            "poll_interval_minutes": "15",
            "batch_size": "300",
            "secret_ref": "env://WEB",
            "connection_config_masked": '{"host": "hes-web.internal"}',
        },
        follow_redirects=True,
    )

    instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "company_hes_poll_hes_context").limit(1)
    )

    assert response.status_code == 200
    assert "Adapter instance created successfully." in response.get_data(as_text=True)
    assert instance is not None
    assert instance.hes_system_id == hes_system.id
    assert instance.source_system == "HES"


def test_create_adapter_via_hes_context_rejects_source_system_mismatch_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    client.get("/hes-systems?lang=ko")

    definition = session.scalar(select(AdapterDefinition).limit(1))
    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert definition is not None
    assert hes_system is not None

    response = client.post(
        "/adapters",
        data={
            "hes_system_id": str(hes_system.id),
            "adapter_definition_id": str(definition.id),
            "instance_code": "company_hes_poll_hes_context_mismatch",
            "display_name": "Company HES Poll HES Context Mismatch",
            "source_system": "OTHER_HES",
            "poll_interval_minutes": "15",
            "batch_size": "300",
            "secret_ref": "",
            "connection_config_masked": "",
        },
        follow_redirects=True,
    )

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "company_hes_poll_hes_context_mismatch")
        .limit(1)
    )

    assert response.status_code == 200
    assert "출처 시스템은 선택한 HES 코드와 일치해야 합니다." in response.get_data(as_text=True)
    assert instance is None


def test_create_adapter_via_web_rejects_invalid_json_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    client.get("/adapters/new?lang=ko")

    definition = session.scalar(select(AdapterDefinition).limit(1))
    assert definition is not None

    response = client.post(
        "/adapters",
        data={
            "adapter_definition_id": str(definition.id),
            "instance_code": "company_hes_poll_bad_json",
            "display_name": "Bad JSON",
            "source_system": "HES",
            "poll_interval_minutes": "10",
            "batch_size": "100",
            "secret_ref": "",
            "connection_config_masked": "not-json",
        },
        follow_redirects=True,
    )

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "company_hes_poll_bad_json")
        .limit(1)
    )

    assert response.status_code == 200
    assert "마스킹된 연결 설정은 유효한 JSON 객체여야 합니다." in response.get_data(as_text=True)
    assert instance is None
