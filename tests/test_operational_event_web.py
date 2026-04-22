from __future__ import annotations

from sqlalchemy import select

from app.models import HesSystem, OperationalEvent
from app.services.operational_events import record_operational_event
from app.services.seeds import seed_demo_environment


def _get_open_alert(session):
    return session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.is_alert.is_(True), OperationalEvent.alert_status == "open")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )


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
