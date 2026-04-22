from __future__ import annotations

from sqlalchemy import select

from app.models import AdapterInstance, HesSystem
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
