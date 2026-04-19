from __future__ import annotations

from sqlalchemy import func, select

from app.models import AdapterInstance, AdapterRun
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
