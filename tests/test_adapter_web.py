from __future__ import annotations

from sqlalchemy import func, select

from app.models import AdapterDefinition, AdapterInstance, AdapterRun
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

    assert pause_response.status_code == 200
    assert "Adapter instance paused successfully." in pause_response.get_data(as_text=True)
    assert enable_response.status_code == 200
    assert "Adapter instance enabled successfully." in enable_response.get_data(as_text=True)
    assert updated is not None
    assert updated.admin_state == "enabled"


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

    assert response.status_code == 200
    assert "수동 어댑터 실행 요청이 대기열에 등록되었습니다." in text
    assert "대기" in text
    assert session.scalar(select(func.count()).select_from(AdapterRun)) == 2


def test_new_adapter_page_renders_active_definition(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/adapters/new?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "어댑터 인스턴스 등록" in text
    assert "Company HES Poll" in text


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

    assert response.status_code == 200
    assert "Adapter instance created successfully." in response.get_data(as_text=True)
    assert instance is not None
    assert instance.landing_enabled is True
    assert instance.poll_interval_minutes == 15


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
