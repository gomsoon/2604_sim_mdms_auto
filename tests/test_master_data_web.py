from __future__ import annotations

from sqlalchemy import select

from app.models import Device, InstallationHistory, ServicePoint
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
