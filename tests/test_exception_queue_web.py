from __future__ import annotations

from sqlalchemy import select

from app.models import IngestErrorLog
from app.services.master_data import create_device, create_measuring_component, create_service_point
from app.services.seeds import seed_demo_environment


def _mapping_error_id(session) -> int:
    error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "measuring_component_not_found")
        .order_by(IngestErrorLog.id.asc())
        .limit(1)
    )
    assert error is not None
    return error.id


def test_exception_detail_page_renders_raw_context(client, session):
    seed_demo_environment(session)
    session.commit()

    error_id = _mapping_error_id(session)
    response = client.get(f"/exceptions/{error_id}")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Exception Detail" in text
    assert "MTR-9999" in text
    assert "CH-99" in text
    assert "Reprocess" in text


def test_exception_queue_page_filters_by_meter_and_code_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get(
        "/exceptions?lang=ko&meter_id=MTR-9999&exception_code=measuring_component_not_found"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "오류 큐" in text
    assert "MTR-9999" in text
    assert "measuring_component_not_found" in text
    assert "duplicate_raw_read" not in text


def test_reprocess_exception_view_supports_korean_success_feedback(client, session):
    seed_demo_environment(session)
    session.commit()
    client.get("/exceptions?lang=ko")

    error_id = _mapping_error_id(session)
    service_point = create_service_point(
        session,
        source_system="HES",
        external_id="SP-WEB-9999",
        service_type="electric",
        name="복구 현장",
        status="active",
    )
    device = create_device(
        session,
        source_system="HES",
        external_meter_id="MTR-9999",
        serial_number="SER-WEB-9999",
        service_point_id=service_point.id,
        status="active",
    )
    create_measuring_component(
        session,
        source_system="HES",
        external_channel_id="CH-99",
        unit_of_measure="kWh",
        multiplier=1,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )
    session.commit()

    response = client.post(f"/exceptions/{error_id}/reprocess", follow_redirects=True)
    text = response.get_data(as_text=True)

    refreshed_error = session.get(IngestErrorLog, error_id)

    assert response.status_code == 200
    assert "표준 계측이 생성되었습니다." in text
    assert "해결됨" in text
    assert refreshed_error is not None
    assert refreshed_error.status == "resolved"


def test_exception_queue_api_filters_by_status_code_and_meter(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get(
        "/api/v1/exceptions?status=open&exception_code=measuring_component_not_found&meter_id=MTR-9999"
    )

    assert response.status_code == 200
    assert response.get_json() == [
        {
            "id": 2,
            "type": "mapping",
            "code": "measuring_component_not_found",
            "status": "open",
            "message": "No active measuring component matched the incoming raw read.",
            "batch_id": "demo-read-batch",
            "meter_id": "MTR-9999",
        }
    ]
