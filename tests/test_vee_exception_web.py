from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    BillCharge,
    BillDeterminant,
    EstimationAudit,
    FinalMeasurement,
    HesReadRaw,
    HesSystem,
    InitialMeasurement,
    ManualEditAudit,
    RawIntervalWindowState,
    ServicePoint,
    UserAccount,
    UsageTransaction,
    VeeException,
    VeeExecutionLog,
)
from app.services.bill_charges import (
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
    calculate_bill_charges,
)
from app.services.bill_determinants import (
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
    calculate_bill_determinants,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_events, ingest_reads
from app.services.seeds import seed_demo_environment
from app.services.tariff_assignments import create_tariff_assignment
from app.services.usage import calculate_usage_transactions
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


def _prepare_estimation_environment(session) -> tuple[int, int, int]:
    seed_demo_environment(session)
    hes_system_id = session.scalar(select(HesSystem.id).limit(1))
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    assert hes_system_id is not None
    assert service_point_id is not None

    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "estimation-neighbor-read-batch",
            "received_at": "2026-04-18T09:10:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:00:00+09:00",
                    "value": 10.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:30:00+09:00",
                    "value": 20.0,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
            ],
        },
        hes_system_id=hes_system_id,
    )
    session.commit()

    finalize_canonical_measurements(session, limit=50)
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    create_tariff_assignment(
        session,
        service_point_id=service_point_id,
        tariff_plan_code="KR_BASIC",
        tariff_version_code="v1",
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
        source_system="test",
        source_reference="test:tariff-assignment",
    )
    calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    rows = session.scalars(
        select(InitialMeasurement)
        .where(InitialMeasurement.service_point_id == service_point_id)
        .order_by(InitialMeasurement.measured_at.asc(), InitialMeasurement.id.asc())
    ).all()
    target_row = rows[1]
    return service_point_id, target_row.id, rows[0].measuring_component_id


def _open_negative_vee_exception(session, *, initial_measurement_id: int) -> VeeException:
    initial_row = session.get(InitialMeasurement, initial_measurement_id)
    assert initial_row is not None
    initial_row.value = Decimal("-1.0000")
    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row, force=True)
    session.commit()
    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial_measurement_id)
        .order_by(VeeException.id.desc())
        .limit(1)
    )
    assert vee_exception is not None
    assert vee_exception.exception_code == "vee_negative_value_detected"
    return vee_exception


def _open_missing_interval_vee_exception(session, *, initial_measurement_id: int) -> VeeException:
    initial_row = session.get(InitialMeasurement, initial_measurement_id)
    assert initial_row is not None
    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row, force=True)
    session.commit()
    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial_measurement_id)
        .order_by(VeeException.id.desc())
        .limit(1)
    )
    assert vee_exception is not None
    assert vee_exception.exception_code == "vee_missing_interval_detected"
    return vee_exception


def _open_high_value_vee_exception_with_tamper(session) -> VeeException:
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    assert raw_row.hes_system_id is not None
    assert raw_row.meter_identifier is not None

    ingest_events(
        session,
        {
            "source_system": "HES",
            "batch_id": "tamper-web-batch",
            "received_at": "2026-04-18T09:06:00+09:00",
            "events": [
                {
                    "meter_id": raw_row.meter_identifier,
                    "event_time": "2026-04-18T00:15:00+09:00",
                    "event_code": "METER_TAMPER",
                    "severity": "high",
                }
            ],
        },
        hes_system_id=raw_row.hes_system_id,
    )
    session.commit()

    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    initial.value = Decimal("1500.0000")
    initial.unit_of_measure = "kWh"
    session.flush()

    evaluate_or_get_vee_baseline(session, initial, force=True)
    session.commit()

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.desc())
        .limit(1)
    )
    assert vee_exception is not None
    assert vee_exception.exception_code == "vee_high_value_detected"
    return vee_exception


def _prepare_synthetic_missing_interval_environment(
    session,
    *,
    include_missing_slot_measurement: bool = False,
    multi_missing_window: bool = False,
    with_outage: bool = False,
) -> tuple[int, int, int]:
    seed_demo_environment(session)
    hes_system_id = session.scalar(select(HesSystem.id).limit(1))
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    assert hes_system_id is not None
    assert service_point_id is not None

    window_start = "2026-04-19T00:00:00+09:00"
    reads: list[dict[str, object]] = [
        {
            "meter_id": "MTR-1001",
            "channel_id": "CH-01",
            "measured_at": "2026-04-19T00:00:00+09:00",
            "value": 10.0,
            "quality_code": "OK",
            "status_code": "ACTUAL",
            "unit": "kWh",
            "interval_size_minutes": 15,
            "source_business_ts": window_start,
            "source_slot_code": "00",
        },
        {
            "meter_id": "MTR-1001",
            "channel_id": "CH-01",
            "measured_at": "2026-04-19T00:15:00+09:00",
            "value": 20.0,
            "quality_code": "OK",
            "status_code": "ACTUAL",
            "unit": "kWh",
            "interval_size_minutes": 15,
            "source_business_ts": window_start,
            "source_slot_code": "15",
        },
    ]
    if not multi_missing_window:
        reads.append(
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-19T00:45:00+09:00",
                "value": 40.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": 15,
                "source_business_ts": window_start,
                "source_slot_code": "45",
            }
        )
    if include_missing_slot_measurement:
        reads.append(
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-19T00:30:00+09:00",
                "value": 30.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": 15,
                "source_business_ts": window_start,
                "source_slot_code": "30",
            }
        )
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "synthetic-missing-web-read-batch",
            "received_at": "2026-04-19T09:00:00+09:00",
            "reads": reads,
        },
        hes_system_id=hes_system_id,
    )
    session.commit()

    anchor_initial = session.scalar(
        select(InitialMeasurement)
        .where(InitialMeasurement.measured_at == datetime.fromisoformat("2026-04-19T00:15:00+09:00"))
        .limit(1)
    )
    assert anchor_initial is not None
    anchor_raw = anchor_initial.canonical_measurement.hes_read_raw
    assert anchor_raw is not None

    if with_outage:
        ingest_events(
            session,
            {
                "source_system": "HES",
                "batch_id": "synthetic-missing-web-outage-batch",
                "received_at": "2026-04-19T09:05:00+09:00",
                "events": [
                    {
                        "meter_id": "MTR-1001",
                        "event_time": "2026-04-19T00:00:00+09:00",
                        "event_code": "POWER_FAIL",
                        "severity": "high",
                    }
                ],
            },
            hes_system_id=hes_system_id,
        )
        session.commit()

    session.add(
        RawIntervalWindowState(
            source_system=anchor_raw.source_system,
            meter_identifier=anchor_raw.meter_identifier,
            channel_identifier=anchor_raw.channel_identifier,
            window_start_at=anchor_raw.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=15,
            expected_slot_count=4,
            received_slot_count=2 if multi_missing_window else 3,
            received_slot_bitmap="00,15" if multi_missing_window else "00,15,45",
            completion_status="partial",
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.commit()

    finalize_canonical_measurements(session, limit=100)
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    create_tariff_assignment(
        session,
        service_point_id=service_point_id,
        tariff_plan_code="KR_BASIC",
        tariff_version_code="v1",
        effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
        effective_to=None,
        source_system="test",
        source_reference="test:synthetic-missing-web-tariff-assignment",
    )
    calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    anchor_exception = _open_missing_interval_vee_exception(
        session,
        initial_measurement_id=anchor_initial.id,
    )
    return service_point_id, anchor_initial.id, anchor_exception.id


def test_vee_exceptions_page_renders_exception_in_korean(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.get("/vee-exceptions?lang=ko&exception_status=open")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 예외" in text
    assert "필수 항목 누락" in text
    assert "권장 다음 조치" in text
    assert "운영자 검토가 필요합니다." in text
    assert "최종화를 완료하려면 먼저 이 예외를 정리해야 합니다." in text
    assert f"/vee-exceptions/{vee_exception.id}?lang=ko" in text


def test_vee_exceptions_page_exposes_filtered_replay_request_link(client, session):
    vee_exception = _create_open_vee_exception(session)
    initial = session.get(InitialMeasurement, vee_exception.initial_measurement_id)
    assert initial is not None

    response = client.get(
        "/vee-exceptions?lang=ko&hes_system_id=1&exception_status=open&date_from=2026-04-18&date_to=2026-04-18"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/vee-replay-requests/new?" in text
    assert "request_scope=date_range" in text
    assert "hes_system_id=1" in text
    assert "measured_at_from=2026-04-18T00:00" in text
    assert "measured_at_to=2026-04-18T23:59" in text


def test_vee_exceptions_page_shows_correction_policy_columns_and_filters(client, session):
    vee_exception = _open_high_value_vee_exception_with_tamper(session)

    response = client.get(
        "/vee-exceptions?lang=ko&exception_status=active&policy_reason_code=tamper_correlated_value_anomaly&event_context_type=tamper"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "정책 사유" in text
    assert "권장 다음 조치" in text
    assert "변조 연계 값 이상은 시스템 추정보다 운영자 확인이 우선입니다" in text
    assert "운영자 확인 후 필요한 경우 수동 보정을 적용합니다" in text
    assert "변조" in text
    assert f"/vee-exceptions/{vee_exception.id}?lang=ko" in text


def test_vee_exception_detail_page_shows_lineage(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 예외 상세" in text
    assert "원본 원시 검침" in text
    assert "매핑된 표준 계측" in text
    assert "VEE 평가 요약" in text
    assert "현재 가능한 운영자 조치" in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text


def test_vee_exception_detail_page_shows_event_context_for_tamper_linked_rule(client, session):
    vee_exception = _open_high_value_vee_exception_with_tamper(session)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이벤트 컨텍스트" in text
    assert "변조 이벤트와 연계된 값 이상" in text
    assert "METER_TAMPER" in text


def test_vee_exception_detail_page_shows_correction_policy_for_tamper_value_anomaly(client, session):
    vee_exception = _open_high_value_vee_exception_with_tamper(session)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "보정 정책" in text
    assert "운영자 확인 후 필요한 경우 수동 보정을 적용합니다" in text
    assert "이벤트 연계 보정 정책에 따라 현재 추정 적용이 차단됩니다." in text
    assert "먼저 정책 사유를 확인하고, 필요하면 다른 허용된 운영자 조치를 선택하세요." in text
    assert f"/vee-exceptions/{vee_exception.id}/estimate?lang=ko" not in text
    assert f"/vee-exceptions/{vee_exception.id}/manual-edit?lang=ko" in text


def test_vee_exception_detail_page_shows_estimation_form_for_supported_exception(client, session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_estimation_environment(
        session
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "추정 적용" in text
    assert "지원되는 추정 전략 하나를 적용한 뒤, 현재 interval에 대해 VEE와 downstream 재계산을 다시 닫습니다." in text
    assert "선형 보간" in text
    assert "이전 값 기반" in text
    assert f"/vee-exceptions/{vee_exception.id}/estimate?lang=ko" in text


def test_vee_exception_detail_page_shows_synthetic_estimation_form_for_supported_missing_interval(
    client, session
):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_synthetic_missing_interval_environment(session)
    )

    response = client.get(f"/vee-exceptions/{anchor_exception_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "누락 interval 복구" in text
    assert "누락 slot" in text
    assert "30" in text
    assert f"/vee-exceptions/{anchor_exception_id}/estimate-synthetic-missing-interval?lang=ko" in text
    assert f"/vee-exceptions/{anchor_exception_id}/estimate?lang=ko" not in text


def test_vee_exception_detail_page_shows_synthetic_estimation_block_reason_for_outage_window(
    client, session
):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_synthetic_missing_interval_environment(
            session,
            with_outage=True,
        )
    )

    response = client.get(f"/vee-exceptions/{anchor_exception_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 이 VEE 예외에는 synthetic missing-interval 복구를 적용할 수 없습니다." in text
    assert "정전 연계 구간 누락에는 아직 1차 보정 경로가 없습니다" in text
    assert "먼저 window 맥락을 확인하거나, 이후 지원되는 복구 경로에 남겨 두세요." in text
    assert f"/vee-exceptions/{anchor_exception_id}/estimate-synthetic-missing-interval?lang=ko" not in text


def test_vee_exception_detail_page_shows_manual_edit_form_for_supported_exception(client, session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_estimation_environment(
        session
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "수동 보정" in text
    assert "운영 검토 결과 현재 interval 값을 직접 덮어써야 할 때 수동 보정을 적용합니다." in text
    assert "운영자 계량기 보정" in text
    assert f"/vee-exceptions/{vee_exception.id}/manual-edit?lang=ko" in text


def test_vee_exception_detail_page_hides_estimation_form_for_unsupported_exception(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이 VEE 예외 유형은 현재 추정 적용 범위 밖에 있습니다." in text
    assert f"/vee-exceptions/{vee_exception.id}/estimate?lang=ko" not in text
    assert 'name="strategy_code"' not in text


def test_vee_exception_detail_hides_manual_edit_form_for_unsupported_exception(client, session):
    vee_exception = _create_open_vee_exception(session)

    response = client.get(f"/vee-exceptions/{vee_exception.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이 VEE 예외 유형은 현재 수동 보정 범위 밖에 있습니다." in text
    assert f"/vee-exceptions/{vee_exception.id}/manual-edit?lang=ko" not in text
    assert 'name="reason_code"' not in text


def test_vee_exception_acknowledge_via_web_updates_status(client, session):
    vee_exception = _create_open_vee_exception(session)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

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
    assert updated.acknowledged_by == "admin"
    assert updated.acknowledged_by_user_account_id == actor.id
    assert "Test Admin (admin)" in text


def test_vee_exception_resolve_via_web_updates_status(client, session):
    vee_exception = _create_open_vee_exception(session)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

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
    assert updated.resolved_by == "admin"
    assert updated.resolved_by_user_account_id == actor.id
    assert updated.resolution_type == "operator_resolution"
    assert updated.operator_memo == "운영 확인 완료"
    assert "Test Admin (admin)" in text


def test_vee_exception_re_evaluate_via_web_creates_new_execution(session, client):
    vee_exception = _create_open_vee_exception(session)
    initial = session.get(InitialMeasurement, vee_exception.initial_measurement_id)
    assert initial is not None
    initial.unit_of_measure = "kWh"
    session.commit()

    response = client.post(
        f"/vee-exceptions/{vee_exception.id}/re-evaluate?lang=ko",
        data={"next": f"/vee-exceptions/{vee_exception.id}?lang=ko"},
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)
    updated = session.get(VeeException, vee_exception.id)
    refreshed_initial = session.get(InitialMeasurement, vee_exception.initial_measurement_id)
    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == refreshed_initial.id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    usage_rows = session.scalars(select(UsageTransaction).order_by(UsageTransaction.usage_type.asc())).all()

    assert response.status_code == 200
    assert "VEE 예외가 재평가되었습니다." in text
    assert "재평가 결과" in text
    assert "현재 최종 생성" in text
    assert "일별 사용량 재계산" in text
    assert "영향받은 사용량 window" in text
    assert "일별 사용량" in text
    assert "월별 사용량" in text
    assert "재계산됨" in text
    assert updated is not None
    assert updated.exception_status == "resolved"
    assert updated.resolution_type == "re_evaluated_superseded"
    assert refreshed_initial is not None
    assert refreshed_initial.initial_status == "accepted"
    assert current_final is not None
    assert len(usage_rows) == 2
    for row in usage_rows:
        assert f"/usage-transactions/{row.id}?lang=ko" in text
    assert session.scalar(
        select(func.count())
        .select_from(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == refreshed_initial.id)
    ) == 2


def test_vee_exception_estimate_via_web_applies_estimation_and_shows_result(session, client):
    service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session
    )
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    old_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    assert old_charge is not None

    response = client.post(
        f"/vee-exceptions/{vee_exception.id}/estimate?lang=ko",
        data={
            "next": f"/vee-exceptions/{vee_exception.id}?lang=ko",
            "strategy_code": "previous_value_based",
            "operator_memo": "운영 추정 적용",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    current_determinant = session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == service_point_id)
        .where(BillDeterminant.is_current.is_(True))
        .limit(1)
    )
    current_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    audit_row = session.scalar(
        select(EstimationAudit)
        .where(EstimationAudit.target_initial_measurement_id == target_initial_id)
        .order_by(EstimationAudit.id.desc())
        .limit(1)
    )
    updated_exception = session.get(VeeException, vee_exception.id)

    assert response.status_code == 200
    assert "VEE 예외에 추정값이 적용되었습니다." in text
    assert "추정 결과" in text
    assert "이전 값 기반" in text
    assert "추정 적용 완료" in text
    assert "청구 결정값 재계산" in text
    assert "청구 금액 재계산" in text
    assert refreshed_initial is not None
    assert refreshed_initial.value == Decimal("10.0000")
    assert current_final is not None
    assert current_final.value == Decimal("10.0000")
    assert current_determinant is not None
    assert current_determinant.determinant_value == Decimal("40.0000")
    assert current_charge is not None
    assert current_charge.id != old_charge.id
    assert current_charge.charge_amount == Decimal("4000.0000")
    assert audit_row is not None
    assert updated_exception is not None
    assert updated_exception.exception_status == "resolved"
    assert updated_exception.resolution_type == "estimated"
    assert updated_exception.resolved_by == actor.login_id
    assert updated_exception.resolved_by_user_account_id == actor.id
    assert audit_row.estimated_by == actor.login_id
    assert audit_row.estimated_by_user_account_id == actor.id


def test_vee_exception_synthetic_estimate_via_web_applies_repair_and_shows_result(session, client):
    service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_synthetic_missing_interval_environment(session)
    )
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

    response = client.post(
        f"/vee-exceptions/{anchor_exception_id}/estimate-synthetic-missing-interval?lang=ko",
        data={
            "next": f"/vee-exceptions/{anchor_exception_id}?lang=ko",
            "strategy_code": "linear_interpolation",
            "operator_memo": "누락 slot 복구",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    updated_exception = session.get(VeeException, anchor_exception_id)
    audit_row = session.scalar(
        select(EstimationAudit)
        .where(EstimationAudit.anchor_vee_exception_id == anchor_exception_id)
        .order_by(EstimationAudit.id.desc())
        .limit(1)
    )
    synthetic_row = session.scalar(
        select(HesReadRaw)
        .where(HesReadRaw.measured_at == datetime.fromisoformat("2026-04-19T00:30:00+09:00"))
        .order_by(HesReadRaw.id.desc())
        .limit(1)
    )
    current_determinant = session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == service_point_id)
        .where(BillDeterminant.is_current.is_(True))
        .order_by(BillDeterminant.id.desc())
        .limit(1)
    )
    current_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.is_current.is_(True))
        .order_by(BillCharge.id.desc())
        .limit(1)
    )

    assert response.status_code == 200
    assert "VEE 예외에 synthetic missing-interval 복구가 적용되었습니다." in text
    assert "추정 결과" in text
    assert "선형 보간" in text
    assert audit_row is not None
    assert synthetic_row is not None
    assert updated_exception is not None
    assert updated_exception.exception_status == "resolved"
    assert updated_exception.resolution_type == "estimated"
    assert updated_exception.resolved_by == actor.login_id
    assert updated_exception.resolved_by_user_account_id == actor.id
    assert audit_row.estimated_by == actor.login_id
    assert audit_row.estimated_by_user_account_id == actor.id
    assert current_determinant is not None
    assert current_charge is not None
    assert f"/estimation-audits/{audit_row.id}?lang=ko" in text


def test_vee_exception_synthetic_estimate_via_web_shows_blocked_result(session, client):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_synthetic_missing_interval_environment(
            session,
            include_missing_slot_measurement=True,
        )
    )

    response = client.post(
        f"/vee-exceptions/{anchor_exception_id}/estimate-synthetic-missing-interval?lang=ko",
        data={
            "next": f"/vee-exceptions/{anchor_exception_id}?lang=ko",
            "strategy_code": "previous_value_based",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    audit_row = session.scalar(
        select(EstimationAudit)
        .where(EstimationAudit.anchor_vee_exception_id == anchor_exception_id)
        .order_by(EstimationAudit.id.desc())
        .limit(1)
    )

    assert response.status_code == 200
    assert "이 VEE 예외에는 synthetic missing-interval 복구가 차단되었습니다." in text
    assert "누락 slot에 이미 계측값이 존재합니다" in text
    assert audit_row is not None
    assert audit_row.estimation_status == "blocked"


def test_vee_exception_manual_edit_via_web_applies_edit_and_shows_result(session, client):
    service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None
    old_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    assert old_charge is not None

    response = client.post(
        f"/vee-exceptions/{vee_exception.id}/manual-edit?lang=ko",
        data={
            "next": f"/vee-exceptions/{vee_exception.id}?lang=ko",
            "edited_value": "12.5000",
            "edited_quality_code": "MANUAL",
            "edited_status_code": "OVERRIDDEN",
            "reason_code": "operator_meter_correction",
            "operator_memo": "운영 수동 보정 적용",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    current_determinant = session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == service_point_id)
        .where(BillDeterminant.is_current.is_(True))
        .limit(1)
    )
    current_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    audit_row = session.scalar(
        select(ManualEditAudit)
        .where(ManualEditAudit.target_initial_measurement_id == target_initial_id)
        .order_by(ManualEditAudit.id.desc())
        .limit(1)
    )
    updated_exception = session.get(VeeException, vee_exception.id)

    assert response.status_code == 200
    assert "VEE 예외에 수동 보정이 적용되었습니다." in text
    assert "수동 보정 결과" in text
    assert "운영자 계량기 보정" in text
    assert "수동 보정 적용 완료" in text
    assert "청구 결정값 재계산" in text
    assert "청구 금액 재계산" in text
    assert refreshed_initial is not None
    assert refreshed_initial.value == Decimal("12.5000")
    assert refreshed_initial.quality_code == "MANUAL"
    assert refreshed_initial.status_code == "OVERRIDDEN"
    assert current_final is not None
    assert current_final.value == Decimal("12.5000")
    assert current_determinant is not None
    assert current_determinant.determinant_value == Decimal("42.5000")
    assert current_charge is not None
    assert current_charge.id != old_charge.id
    assert current_charge.charge_amount == Decimal("4250.0000")
    assert audit_row is not None
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert f"/manual-edit-audits/{audit_row.id}?lang=ko" in text
    assert updated_exception is not None
    assert updated_exception.exception_status == "resolved"
    assert updated_exception.resolution_type == "manually_corrected"
    assert updated_exception.resolved_by == actor.login_id
    assert updated_exception.resolved_by_user_account_id == actor.id
