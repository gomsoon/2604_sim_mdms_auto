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
    ServicePointTariffAssignment,
    UserAccount,
)
from app.services.billing_contexts import create_billing_context
from app.services.hes_systems import sync_hes_meter_reference_alerts
from app.services.installations import create_installation_history
from app.services.master_data import create_device, create_measuring_component, create_service_point
from app.services.tariff_assignments import create_tariff_assignment
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
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "Service point created successfully." in response.get_data(as_text=True)
    assert service_point is not None
    assert actor is not None
    assert service_point.created_by_user_account_id == actor.id
    assert service_point.updated_by_user_account_id == actor.id


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


def test_master_data_page_shows_dependency_aware_empty_guidance_without_prerequisites(client):
    response = client.get("/master-data?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 등록된 서비스 포인트가 없습니다." in text
    assert "왼쪽 등록 폼에서 첫 서비스 포인트를 추가하세요." in text
    assert "청구 컨텍스트를 추가하기 전에 서비스 포인트를 먼저 등록하세요." in text
    assert "장치를 추가하기 전에 서비스 포인트를 먼저 등록하세요." in text
    assert "측정 컴포넌트를 추가하기 전에 장치를 먼저 등록하세요." in text
    assert "설치 이력을 추가하기 전에 장치를 먼저 등록하세요." in text


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
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "Billing context created successfully." in response.get_data(as_text=True)
    assert row is not None
    assert actor is not None
    assert row.timezone_name == "Asia/Seoul"
    assert row.is_current is True
    assert row.created_by_user_account_id == actor.id
    assert row.updated_by_user_account_id == actor.id


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


def test_create_tariff_assignment_via_web_creates_record(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-WEB-1001",
        service_type="electric",
        name="Tariff Assignment Site",
        status="active",
    )
    session.commit()

    response = client.post(
        "/master-data/tariff-assignments",
        data={
            "service_point_id": str(service_point.id),
            "tariff_plan_code": "RES-A",
            "tariff_version_code": "v1",
            "effective_from": "2026-05-01T00:00",
            "effective_to": "",
            "source_system": "manual",
            "source_reference": "web:tariff-assignment",
        },
        follow_redirects=True,
    )

    row = session.scalar(
        select(ServicePointTariffAssignment)
        .where(ServicePointTariffAssignment.service_point_id == service_point.id)
        .limit(1)
    )
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "Tariff assignment created successfully." in response.get_data(as_text=True)
    assert row is not None
    assert actor is not None
    assert row.tariff_plan_code == "RES-A"
    assert row.is_current is True
    assert row.created_by_user_account_id == actor.id
    assert row.updated_by_user_account_id == actor.id


def test_master_data_page_shows_tariff_assignment_rows(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-WEB-2001",
        service_type="electric",
        name="Tariff Assignment View Site",
        status="active",
    )
    create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="RES-B",
        tariff_version_code="v2",
        effective_from="2026-05-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="seed:tariff-view",
    )
    session.commit()

    response = client.get("/master-data")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Tariff Assignments" in text
    assert "SP-TARIFF-WEB-2001" in text
    assert "RES-B" in text


def test_master_data_page_shows_empty_guidance_after_service_point_exists(client, session):
    create_service_point(
        session,
        source_system="HES",
        external_id="SP-EMPTY-GUIDE-1001",
        service_type="electric",
        name="Empty Guide Site",
        status="active",
    )
    session.commit()

    response = client.get("/master-data?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 등록된 청구 컨텍스트가 없습니다." in text
    assert "서비스 포인트를 선택해 현재 또는 이력 청구 컨텍스트를 추가하세요." in text
    assert "아직 등록된 요금제 할당이 없습니다." in text
    assert "서비스 포인트를 선택해 현재 또는 이력 요금제 할당을 추가하세요." in text
    assert "아직 등록된 장치가 없습니다." in text
    assert "왼쪽 등록 폼에서 첫 장치를 추가하고 서비스 포인트에 연결하세요." in text


def test_master_data_page_service_point_row_links_to_tariff_assignment_section(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-TARIFF-WEB-3001",
        service_type="electric",
        name="Tariff Jump Site",
        status="active",
    )
    session.commit()

    response = client.get("/master-data")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f'/master-data?prefill_service_point_id={service_point.id}#tariff-assignments' in text


def test_master_data_page_shows_component_and_installation_guidance_after_device_exists(client, session):
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-COMP-EMPTY-1001",
        service_type="electric",
        name="Component Empty Site",
        status="active",
    )
    create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-COMP-EMPTY-1001",
        serial_number="SER-COMP-EMPTY-1001",
        service_point_id=service_point.id,
        status="active",
    )
    session.commit()

    response = client.get("/master-data?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 등록된 측정 컴포넌트가 없습니다." in text
    assert "장치와 서비스 포인트를 선택한 뒤 채널 매핑을 추가하세요." in text
    assert "아직 등록된 설치 이력이 없습니다." in text
    assert "첫 설치 이력을 추가해 장치와 서비스 포인트 연결을 기록하세요." in text


def test_master_data_page_shows_actor_visibility_for_admin_managed_rows(client, session):
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-ACTOR-VIS-1001",
        service_type="electric",
        name="Actor Visibility Site",
        status="active",
        created_by_user_account_id=actor.id,
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
        source_reference="actor:billing-context",
        created_by_user_account_id=actor.id,
    )
    create_tariff_assignment(
        session,
        service_point_id=service_point.id,
        tariff_plan_code="ACTOR-RES-A",
        tariff_version_code="v1",
        effective_from="2026-05-01T00:00",
        effective_to=None,
        source_system="manual",
        source_reference="actor:tariff-assignment",
        created_by_user_account_id=actor.id,
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-ACTOR-VIS-1001",
        serial_number="SER-ACTOR-VIS-1001",
        service_point_id=service_point.id,
        status="active",
        created_by_user_account_id=actor.id,
    )
    create_measuring_component(
        session,
        source_system="HES",
        external_channel_id="CH-ACTOR-VIS-1001",
        unit_of_measure="kWh",
        multiplier="1",
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
        created_by_user_account_id=actor.id,
    )
    create_installation_history(
        session,
        device_id=device.id,
        service_point_id=service_point.id,
        installed_at="2026-05-01T00:00",
        removed_at=None,
        status="installed",
        created_by_user_account_id=actor.id,
    )
    session.commit()

    response = client.get("/master-data?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "생성 주체" in text
    assert "마지막 수정 주체" in text
    assert "Test Admin (admin)" in text
    assert "SP-ACTOR-VIS-1001" in text
    assert "MTR-ACTOR-VIS-1001" in text


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
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "장치가 수정되었습니다." in response.get_data(as_text=True)
    assert updated_device is not None
    assert actor is not None
    assert updated_device.serial_number == "SER-WEB-UPDATED"
    assert updated_device.status == "inactive"
    assert updated_device.updated_by_user_account_id == actor.id


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
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))

    assert response.status_code == 200
    assert "Installation history created successfully." in response.get_data(as_text=True)
    assert installation is not None
    assert actor is not None
    assert installation.status == "installed"
    assert installation.created_by_user_account_id == actor.id
    assert installation.updated_by_user_account_id == actor.id


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
