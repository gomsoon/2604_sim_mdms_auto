from __future__ import annotations

from sqlalchemy import select

from app.models import (
    Device,
    HesMeterReference,
    HesSystem,
    InstallationHistory,
    OperationalEvent,
    ServicePoint,
    ServicePointBillingContext,
)
from app.services.billing_contexts import create_billing_context
from app.services.hes_systems import sync_hes_meter_reference_alerts
from app.services.master_data import create_device, create_service_point
from app.services.seeds import seed_demo_environment


def test_create_service_point_via_web_creates_record(client, session):
    response = client.post(
        "/master-data/service-points",
        data={
            "source_system": "HES",
            "external_id": "SP-WEB-1001",
            "service_type": "electric",
            "name": "Web Service Point",
            "status": "active",
        },
        follow_redirects=True,
    )

    service_point = session.scalar(
        select(ServicePoint).where(ServicePoint.external_id == "SP-WEB-1001").limit(1)
    )

    assert response.status_code == 200
    assert "Service point created successfully." in response.get_data(as_text=True)
    assert service_point is not None


def test_master_data_page_prefills_device_and_component_forms_from_query(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-PREFILL-1001",
        service_type="electric",
        name="Prefill Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-PREFILL-1001",
        serial_number="SER-PREFILL-1001",
        service_point_id=service_point.id,
        status="active",
    )
    session.commit()

    response = client.get(
        f"/master-data?prefill_source_system=HES&prefill_external_meter_id=MTR-9999&prefill_external_channel_id=CH-99&prefill_device_id={device.id}&prefill_service_point_id={service_point.id}"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'name="external_meter_id" value="MTR-9999"' in text
    assert 'name="external_channel_id" value="CH-99"' in text
    assert f'<option value="{device.id}" selected>{device.external_meter_id}</option>' in text
    assert f'<option value="{service_point.id}" selected>{service_point.external_id}</option>' in text


def test_master_data_page_shows_matching_hes_meter_references_from_prefill(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get(
        "/master-data?lang=ko&prefill_source_system=HES&prefill_external_meter_id=MTR-9999"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "관련 HES 계량기 참조" in text
    assert "MTR-9999" in text
    assert "AIMIR-9999" in text
    assert "15" in text


def test_create_billing_context_via_web_creates_record(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-BCTX-WEB-1001",
        service_type="electric",
        name="Billing Context Site",
        status="active",
    )
    session.commit()

    response = client.post(
        "/master-data/billing-contexts",
        data={
            "service_point_id": str(service_point.id),
            "timezone_name": "Asia/Seoul",
            "billing_cycle_mode": "calendar_month",
            "billing_cycle_anchor_day": "",
            "currency_code": "KRW",
            "effective_from": "2026-05-01T00:00",
            "effective_to": "",
            "source_system": "manual",
            "source_reference": "web:billing-context",
        },
        follow_redirects=True,
    )

    row = session.scalar(
        select(ServicePointBillingContext)
        .where(ServicePointBillingContext.service_point_id == service_point.id)
        .limit(1)
    )

    assert response.status_code == 200
    assert "Billing context created successfully." in response.get_data(as_text=True)
    assert row is not None
    assert row.timezone_name == "Asia/Seoul"
    assert row.is_current is True


def test_master_data_page_shows_billing_context_rows(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-BCTX-WEB-2001",
        service_type="electric",
        name="Billing Context View Site",
        status="active",
    )
    create_billing_context(
        session,
        service_point_id=service_point.id,
        timezone_name="Asia/Seoul",
        billing_cycle_mode="calendar_month",
        billing_cycle_anchor_day=None,
        currency_code="KRW",
        effective_from="2026-05-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="seed:view",
    )
    session.commit()

    response = client.get("/master-data")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Billing Contexts" in text
    assert "SP-BCTX-WEB-2001" in text
    assert "Asia/Seoul" in text


def test_create_device_via_web_closes_missing_device_alert_and_opens_missing_component_alert(
    client, session
):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    service_point = session.scalar(
        select(ServicePoint).where(ServicePoint.source_system == "HES").limit(1)
    )
    reference = session.scalar(
        select(HesMeterReference).where(HesMeterReference.source_meter_id == "MTR-4040").limit(1)
    )

    assert hes_system is not None
    assert service_point is not None
    assert reference is not None

    sync_hes_meter_reference_alerts(session, hes_system_id=hes_system.id)
    session.commit()

    response = client.post(
        "/master-data/devices",
        data={
            "source_system": "HES",
            "external_meter_id": "MTR-4040",
            "serial_number": "SER-4040",
            "service_point_id": str(service_point.id),
            "status": "active",
        },
        follow_redirects=True,
    )

    missing_device_alert = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.event_code == "hes_meter_reference_missing_device_detected",
            OperationalEvent.entity_type == "hes_meter_reference",
            OperationalEvent.entity_id == reference.id,
        )
        .limit(1)
    )
    missing_component_alert = session.scalar(
        select(OperationalEvent)
        .where(
            OperationalEvent.event_code == "hes_meter_reference_missing_component_detected",
            OperationalEvent.entity_type == "hes_meter_reference",
            OperationalEvent.entity_id == reference.id,
            OperationalEvent.alert_status == "open",
        )
        .limit(1)
    )

    assert response.status_code == 200
    assert "Device created successfully." in response.get_data(as_text=True)
    assert missing_device_alert is not None
    assert missing_device_alert.alert_status == "closed"
    assert missing_component_alert is not None


def test_update_device_via_web_supports_korean_feedback(client, session):
    client.get("/master-data?lang=ko")
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-WEB-2001",
        service_type="electric",
        name="Web Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-WEB-2001",
        serial_number="SER-WEB-2001",
        service_point_id=service_point.id,
        status="active",
    )
    session.commit()

    response = client.post(
        f"/master-data/devices/{device.id}",
        data={
            "source_system": "HES",
            "external_meter_id": "MTR-WEB-2001",
            "serial_number": "SER-WEB-UPDATED",
            "service_point_id": str(service_point.id),
            "status": "inactive",
        },
        follow_redirects=True,
    )

    updated_device = session.get(Device, device.id)

    assert response.status_code == 200
    assert "장치가 수정되었습니다." in response.get_data(as_text=True)
    assert updated_device is not None
    assert updated_device.serial_number == "SER-WEB-UPDATED"
    assert updated_device.status == "inactive"


def test_create_service_point_via_web_rejects_empty_external_id_in_korean(client, session):
    client.get("/master-data?lang=ko")

    response = client.post(
        "/master-data/service-points",
        data={
            "source_system": "HES",
            "external_id": "",
            "service_type": "electric",
            "name": "Broken",
            "status": "active",
        },
        follow_redirects=True,
    )

    service_point = session.scalar(
        select(ServicePoint).where(ServicePoint.name == "Broken").limit(1)
    )

    assert response.status_code == 200
    assert "외부 ID는 필수입니다." in response.get_data(as_text=True)
    assert service_point is None


def test_create_installation_history_via_web_creates_record(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-WEB-3001",
        service_type="electric",
        name="Install Web Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-WEB-3001",
        serial_number="SER-WEB-3001",
        service_point_id=service_point.id,
        status="active",
    )
    session.commit()

    response = client.post(
        "/master-data/installations",
        data={
            "device_id": str(device.id),
            "service_point_id": str(service_point.id),
            "installed_at": "2026-04-19T10:00",
            "removed_at": "",
            "status": "installed",
        },
        follow_redirects=True,
    )

    installation = session.scalar(
        select(InstallationHistory)
        .where(InstallationHistory.device_id == device.id)
        .order_by(InstallationHistory.id.desc())
        .limit(1)
    )

    assert response.status_code == 200
    assert "Installation history created successfully." in response.get_data(as_text=True)
    assert installation is not None
    assert installation.status == "installed"


def test_create_installation_history_via_web_rejects_missing_removed_time_in_korean(client, session):
    client.get("/master-data?lang=ko")
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-WEB-4001",
        service_type="electric",
        name="Install Error Site",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-WEB-4001",
        serial_number="SER-WEB-4001",
        service_point_id=service_point.id,
        status="active",
    )
    session.commit()

    response = client.post(
        "/master-data/installations",
        data={
            "device_id": str(device.id),
            "service_point_id": str(service_point.id),
            "installed_at": "2026-04-19T10:00",
            "removed_at": "",
            "status": "removed",
        },
        follow_redirects=True,
    )

    installation = session.scalar(
        select(InstallationHistory)
        .where(InstallationHistory.device_id == device.id)
        .order_by(InstallationHistory.id.desc())
        .limit(1)
    )

    assert response.status_code == 200
    assert "상태가 철거일 때는 철거 시각이 필요합니다." in response.get_data(as_text=True)
    assert installation is None
