from __future__ import annotations

from sqlalchemy import select

from app.models import InitialMeasurement, VeeException
from app.services.seeds import seed_demo_environment
from app.services.vee import evaluate_or_get_vee_baseline


def _create_open_vee_exception(session) -> VeeException:
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None

    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    initial.unit_of_measure = ""
    session.flush()

    evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert vee_exception is not None
    return vee_exception


def test_vee_exceptions_page_renders_exception_in_korean(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.get("/vee-exceptions?lang=ko&exception_status=open")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 예외" in text
    assert "필수 항목 누락" in text
    assert f"/vee-exceptions/{vee_exception.id}?lang=ko" in text


def test_vee_exception_detail_page_shows_lineage(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 예외 상세" in text
    assert "관련 원시 검침" in text
    assert "관련 표준 계측" in text
    assert "VEE 실행 정보" in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text


def test_vee_exception_acknowledge_via_web_updates_status(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.post(
        f"/vee-exceptions/{vee_exception.id}/acknowledge?lang=ko",
        data={"next": f"/vee-exceptions/{vee_exception.id}?lang=ko"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    updated = session.get(VeeException, vee_exception.id)

    assert response.status_code == 200
    assert "VEE 예외가 확인 상태로 변경되었습니다." in text
    assert updated is not None
    assert updated.exception_status == "acknowledged"
    assert updated.acknowledged_by == "operator_ui"


def test_vee_exception_resolve_via_web_updates_status(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.post(
        f"/vee-exceptions/{vee_exception.id}/resolve?lang=ko",
        data={
            "next": f"/vee-exceptions/{vee_exception.id}?lang=ko",
            "resolution_type": "operator_resolution",
            "operator_memo": "운영 확인 완료",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    updated = session.get(VeeException, vee_exception.id)

    assert response.status_code == 200
    assert "VEE 예외가 해결 상태로 변경되었습니다." in text
    assert updated is not None
    assert updated.exception_status == "resolved"
    assert updated.resolution_type == "operator_resolution"
    assert updated.operator_memo == "운영 확인 완료"
