from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.models import (
    InitialMeasurement,
    PipelineRun,
    VeeException,
    VeeExecutionLog,
    VeeReplayRequest,
    VeeReplayRequestItem,
)
from app.services.hes_systems import ensure_hes_system
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_master_data
from app.services.vee_replay_requests import create_vee_replay_request


def _prepare_replay_environment(session) -> int:
    seed_master_data(session)
    hes_system = ensure_hes_system(
        session,
        hes_code="HES",
        display_name="Demo HES",
        source_family="hes",
        default_delivery_mode="poll",
        timezone_name="Asia/Seoul",
    )
    session.commit()
    return hes_system.id


def _ingest_initial_measurement(
    session,
    *,
    hes_system_id: int,
    batch_id: str,
    measured_at: str,
) -> InitialMeasurement:
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": batch_id,
            "received_at": "2026-05-01T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": measured_at,
                    "value": 1.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                    "interval_size_minutes": 60,
                }
            ],
        },
        hes_system_id=hes_system_id,
    )
    session.commit()

    initial = session.scalar(
        select(InitialMeasurement)
        .where(InitialMeasurement.measured_at == datetime.fromisoformat(measured_at))
        .order_by(InitialMeasurement.id.desc())
        .limit(1)
    )
    assert initial is not None
    return initial


def _attach_vee_exception(session, initial: InitialMeasurement) -> VeeException:
    detected = datetime.now(timezone.utc)
    pipeline_run = PipelineRun(
        pipeline_name="vee",
        trigger_type="manual",
        status="processing",
        started_at=detected,
        details={"scope": "measurement"},
    )
    session.add(pipeline_run)
    session.flush()

    execution = VeeExecutionLog(
        initial_measurement_id=initial.id,
        pipeline_run_id=pipeline_run.id,
        execution_scope="measurement",
        trigger_type="manual",
        rule_set_code="vee_baseline_v1",
        execution_status="completed_with_exception",
        started_at=detected,
        completed_at=detected,
        summary_code="vee_required_field_missing",
        details={"rule_hits": 1},
    )
    session.add(execution)
    session.flush()

    vee_exception = VeeException(
        initial_measurement_id=initial.id,
        vee_execution_log_id=execution.id,
        exception_code="vee_required_field_missing",
        severity="error",
        exception_status="open",
        blocking_finalization=True,
        detected_at=detected,
        details={"source": "test"},
    )
    session.add(vee_exception)
    session.commit()
    return vee_exception


def test_vee_replay_requests_page_renders_request_list_and_progress(client, session):
    hes_system_id = _prepare_replay_environment(session)
    initial = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-web-list",
        measured_at="2026-05-14T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial)
    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )
    created.request.details = {
        **dict(created.request.details or {}),
        "progress_percent": 40.0,
        "remaining_count": 3,
    }
    created.request.processed_count = 2
    created.request.failed_count = 1
    session.commit()

    response = client.get("/vee-replay-requests?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 재평가 요청" in text
    assert "Demo HES" in text
    assert "40.0%" in text
    assert "operator_ui" in text


def test_vee_replay_request_detail_page_shows_progress_and_failed_items(client, session):
    hes_system_id = _prepare_replay_environment(session)
    initial_one = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-web-detail-a",
        measured_at="2026-05-15T00:00:00+09:00",
    )
    initial_two = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-web-detail-b",
        measured_at="2026-05-16T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial_one)
    _attach_vee_exception(session, initial_two)
    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )

    request = created.request
    items = session.scalars(
        select(VeeReplayRequestItem)
        .where(VeeReplayRequestItem.vee_replay_request_id == request.id)
        .order_by(VeeReplayRequestItem.id.asc())
    ).all()
    request.status = "processing"
    request.started_at = datetime.now(timezone.utc)
    request.processed_count = 1
    request.succeeded_count = 0
    request.failed_count = 1
    request.last_error = "forced replay failure"
    request.details = {
        **dict(request.details or {}),
        "progress_percent": 50.0,
        "remaining_count": 1,
        "current_item_id": items[1].id,
        "last_processed_item_id": items[0].id,
    }
    items[0].status = "failed"
    items[0].result_code = "processing_error"
    items[0].details = {
        **dict(items[0].details or {}),
        "error_summary": "forced replay failure",
    }
    items[1].status = "processing"
    pipeline_run = PipelineRun(
        pipeline_name="vee_replay",
        trigger_type="async_replay",
        status="processing",
        vee_replay_request_id=request.id,
        started_at=datetime.now(timezone.utc),
        details={"request_id": request.id},
    )
    session.add(pipeline_run)
    session.commit()

    response = client.get(f"/vee-replay-requests/{request.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 재평가 요청 상세" in text
    assert "50.0%" in text
    assert "자동으로 새로고침" in text
    assert "forced replay failure" in text
    assert str(items[1].representative_vee_exception_id) in text


def test_cancel_queued_vee_replay_request_via_web(client, session):
    hes_system_id = _prepare_replay_environment(session)
    initial = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-web-cancel",
        measured_at="2026-05-17T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial)
    created = create_vee_replay_request(
        session,
        request_scope="hes_system",
        requested_by="operator_ui",
        hes_system_id=hes_system_id,
    )
    session.commit()

    response = client.post(
        f"/vee-replay-requests/{created.request.id}/cancel?lang=ko",
        data={"operator_memo": "queued cancel"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    refreshed = session.get(VeeReplayRequest, created.request.id)

    assert response.status_code == 200
    assert "VEE 재평가 요청이 처리 시작 전에 취소되었습니다." in text
    assert refreshed is not None
    assert refreshed.status == "cancelled"


def test_new_vee_replay_request_page_prefills_hes_system_scope(client, session):
    hes_system_id = _prepare_replay_environment(session)

    response = client.get(
        f"/vee-replay-requests/new?lang=ko&request_scope=hes_system&hes_system_id={hes_system_id}&window_timezone_name=Asia/Seoul"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 재평가 요청 등록" in text
    assert 'value="hes_system" selected' in text
    assert f'value="{hes_system_id}" selected' in text
    assert 'value="Asia/Seoul"' in text


def test_create_vee_replay_request_via_web_redirects_to_detail(client, session):
    hes_system_id = _prepare_replay_environment(session)
    initial = _ingest_initial_measurement(
        session,
        hes_system_id=hes_system_id,
        batch_id="replay-web-create",
        measured_at="2026-05-18T00:00:00+09:00",
    )
    _attach_vee_exception(session, initial)

    response = client.post(
        "/vee-replay-requests?lang=ko",
        data={
            "request_scope": "hes_system",
            "requested_by": "operator_ui",
            "hes_system_id": str(hes_system_id),
            "window_timezone_name": "Asia/Seoul",
            "operator_memo": "queue from web",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    created = session.scalar(
        select(VeeReplayRequest)
        .where(VeeReplayRequest.requested_by == "operator_ui")
        .order_by(VeeReplayRequest.id.desc())
        .limit(1)
    )

    assert response.status_code == 200
    assert "VEE 재평가 요청이 대기열에 등록되었습니다." in text
    assert "VEE 재평가 요청 상세" in text
    assert created is not None
    assert created.request_scope == "hes_system"
    assert created.hes_system_id == hes_system_id
