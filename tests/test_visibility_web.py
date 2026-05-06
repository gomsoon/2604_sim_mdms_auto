from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.services.bill_charges import calculate_bill_charges
from app.services.bill_determinants import calculate_bill_determinants
from app.models import (
    FinalMeasurement,
    IngestBatch,
    InitialMeasurement,
    ManualEditAudit,
    OperationalEvent,
    UsageTransaction,
    VeeException,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.manual_edits import apply_manual_edit_from_vee_exception
from app.services.operational_events import close_operational_alert
from app.services.seeds import seed_demo_environment
from app.services.tariff_assignments import create_tariff_assignment
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def _prepare_bill_charge_rows(session) -> None:
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    create_tariff_assignment(
        session,
        service_point_id=1,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-04-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="test:bill-charge-web",
    )
    session.commit()
    calculate_bill_charges(
        session,
        charge_type="flat_energy_charge",
        unit_rate_value="120.00000000",
    )
    session.commit()


def _prepare_manual_edit_audit_rows(session) -> int:
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    create_tariff_assignment(
        session,
        service_point_id=1,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-04-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="test:manual-edit-web",
    )
    session.commit()
    calculate_bill_charges(
        session,
        charge_type="flat_energy_charge",
        unit_rate_value="120.00000000",
    )
    session.commit()

    initial_row = session.scalar(
        select(InitialMeasurement)
        .where(InitialMeasurement.service_point_id == 1)
        .order_by(InitialMeasurement.measured_at.asc(), InitialMeasurement.id.asc())
        .limit(1)
    )
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
        .where(VeeException.initial_measurement_id == initial_row.id)
        .order_by(VeeException.id.desc())
        .limit(1)
    )
    assert vee_exception is not None

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        edited_quality_code="MANUAL",
        edited_status_code="OVERRIDDEN",
        reason_code="operator_meter_correction",
        edited_by="operator_ui",
        operator_memo="manual-edit-web",
    )
    session.commit()
    return summary.manual_edit_audit_id


def test_ingest_batches_page_renders_filtered_results_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/ingest-batches?lang=ko&record_type=hes_event_raw")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "적재 배치" in text
    assert "demo-event-batch" in text
    assert "원시 이벤트" in text


def test_ingest_batches_page_exposes_replay_request_link(client, session):
    seed_demo_environment(session)
    session.commit()
    batch = session.scalar(select(IngestBatch).where(IngestBatch.batch_id == "demo-read-batch").limit(1))
    assert batch is not None

    response = client.get("/ingest-batches?lang=ko&batch_id=demo-read-batch")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/vee-replay-requests/new?request_scope=ingest_batch" in text
    assert f"ingest_batch_id={batch.id}" in text


def test_canonical_measurements_page_filters_by_batch_and_meter(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/canonical-measurements?batch_id=demo-read-batch&meter_id=MTR-1001")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert "CH-01" in text


def test_ingest_batches_api_rejects_invalid_date_range_in_korean(client):
    response = client.get(
        "/api/v1/ingest-batches?lang=ko&date_from=2026-04-19&date_to=2026-04-18"
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_date_range",
        "message": "시작일은 종료일보다 늦을 수 없습니다.",
        "locale": "ko",
    }


def test_canonical_measurements_api_returns_filtered_measurement(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get(
        "/api/v1/canonical-measurements?batch_id=demo-read-batch&meter_id=MTR-1001"
    )

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["id"] == 1
    assert row["batch_id"] == "demo-read-batch"
    assert row["source_system"] == "HES"
    assert row["meter_id"] == "MTR-1001"
    assert row["channel_id"] == "CH-01"
    assert row["measured_at"].startswith("2026-04-18T00:15:00")
    assert row["value"] == 14.2
    assert row["unit_of_measure"] == "kWh"
    assert row["service_point_id"] == 1
    assert row["device_id"] == 1


def test_final_measurements_page_filters_by_batch_and_meter(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    response = client.get("/final-measurements?lang=ko&batch_id=demo-read-batch&meter_id=MTR-1001")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최종 계측" in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert "최종화" in text


def test_final_measurements_api_returns_filtered_measurement(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    response = client.get("/api/v1/final-measurements?batch_id=demo-read-batch&meter_id=MTR-1001")

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["batch_id"] == "demo-read-batch"
    assert row["source_system"] == "HES"
    assert row["meter_id"] == "MTR-1001"
    assert row["channel_id"] == "CH-01"
    assert row["value"] == 14.2
    assert row["unit_of_measure"] == "kWh"
    assert row["final_status"] == "finalized"


def test_usage_transactions_page_filters_by_service_point_and_channel(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    response = client.get(
        "/usage-transactions?lang=ko&service_point=SP-1001&external_channel_id=CH-01&usage_type=daily_consumption"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "사용량 거래" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "일별 사용량" in text


def test_usage_transaction_detail_page_shows_lineage_and_final_context(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    response = client.get("/usage-transactions/1?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "사용량 거래 상세" in text
    assert "계산 근거" in text
    assert "수동 사용량 계산" in text
    assert "구성 최종 계측" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text


def test_bill_determinants_page_filters_by_service_point_and_channel(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    response = client.get(
        "/bill-determinants?lang=ko&service_point=SP-1001&external_channel_id=CH-01&determinant_type=billing_cycle_consumption_total"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 결정값" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "청구 주기 총 사용량" in text


def test_bill_determinant_detail_page_shows_usage_lineage_and_revision_context(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    response = client.get("/bill-determinants/1?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 결정값 상세" in text
    assert "원본 사용량 거래" in text
    assert "리비전 이력" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "/usage-transactions/1?lang=ko" in text
    assert "청구 컨텍스트" in text
    assert "청구 컨텍스트 달력 월" in text
    assert "Asia/Seoul" in text
    assert "적용 가능한 요금제 할당이 아직 없습니다" in text


def test_bill_determinant_detail_page_shows_applicable_tariff_assignment(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    create_tariff_assignment(
        session,
        service_point_id=1,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-04-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="test:web-detail",
    )
    session.commit()

    response = client.get("/bill-determinants/1?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "요금제 할당" in text
    assert "RES-A" in text
    assert "v1" in text
    assert "적용 가능한 요금제 할당이 있습니다" in text


def test_usage_transaction_detail_page_links_to_related_bill_determinants(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()
    usage_row = session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.usage_type == "monthly_consumption")
        .limit(1)
    )
    assert usage_row is not None

    response = client.get(f"/usage-transactions/{usage_row.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "관련 청구 결정값" in text
    assert "/bill-determinants/1?lang=ko" in text


def test_bill_determinants_page_filters_by_billing_cycle_mode_and_quality_summary(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    response = client.get(
        "/bill-determinants?lang=ko&billing_cycle_mode=calendar_month&quality_summary=missing_intervals"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 주기 총 사용량" in text
    assert "누락 구간" in text


def test_bill_determinants_page_filters_by_tariff_assignment_presence_and_plan_code(
    client, session
):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    create_tariff_assignment(
        session,
        service_point_id=1,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-04-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="test:web-list",
    )
    session.commit()

    response = client.get(
        "/bill-determinants?lang=ko&tariff_assignment_presence=assigned&tariff_plan_code=RES-A"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 결정값" in text
    assert "SP-1001" in text
    assert "/bill-determinants/1?lang=ko" in text


def test_bill_charges_page_filters_by_service_point_and_channel(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get(
        "/bill-charges?lang=ko&service_point=SP-1001&external_channel_id=CH-01&charge_type=flat_energy_charge"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 금액" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "정액 에너지 요금" in text


def test_bill_charge_detail_page_shows_determinant_tariff_and_revision_context(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get("/bill-charges/1?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 금액 상세" in text
    assert "원본 청구 결정값" in text
    assert "요금제 할당" in text
    assert "요율 스냅샷" in text
    assert "리비전 이력" in text
    assert "RES-A" in text
    assert "/bill-determinants/1?lang=ko" in text


def test_bill_determinant_detail_page_links_to_related_bill_charges(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get("/bill-determinants/1?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "관련 청구 금액" in text
    assert "/bill-charges/1?lang=ko" in text


def test_usage_transaction_detail_page_links_to_related_bill_charges(client, session):
    _prepare_bill_charge_rows(session)
    usage_row = session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.usage_type == "monthly_consumption")
        .limit(1)
    )
    assert usage_row is not None

    response = client.get(f"/usage-transactions/{usage_row.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "관련 청구 금액" in text
    assert "/bill-charges/1?lang=ko" in text


def test_manual_edit_audits_page_renders_filtered_rows(client, session):
    manual_edit_audit_id = _prepare_manual_edit_audit_rows(session)

    response = client.get(
        "/manual-edit-audits?lang=ko&service_point=SP-1001&external_channel_id=CH-01&edit_status=applied&reason_code=operator_meter_correction"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "수동 보정 감사 이력" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "운영자 계량기 보정" in text
    assert f"/manual-edit-audits/{manual_edit_audit_id}?lang=ko" in text


def test_manual_edit_audit_detail_page_shows_snapshots_and_lineage(client, session):
    manual_edit_audit_id = _prepare_manual_edit_audit_rows(session)
    audit_row = session.get(ManualEditAudit, manual_edit_audit_id)
    assert audit_row is not None

    response = client.get(f"/manual-edit-audits/{manual_edit_audit_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "수동 보정 감사 상세" in text
    assert "원본 initial 스냅샷" in text
    assert "적용된 initial 스냅샷" in text
    assert "관련 VEE 예외" in text
    assert "downstream 재계산" in text
    assert "운영자 계량기 보정" in text
    assert "operator_ui" in text
    assert "12.5000" in text
    assert f"/vee-exceptions/{audit_row.related_vee_exception_id}?lang=ko" in text


def test_master_data_page_billing_context_rows_link_to_bill_determinants(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    response = client.get("/master-data?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/bill-determinants?lang=ko&amp;service_point_id=1" in text
    assert "/bill-determinants?lang=ko&amp;service_point_id=1&amp;calculation_status=blocked" in text


def test_master_data_page_tariff_assignment_rows_link_to_bill_determinants(client, session):
    seed_demo_environment(session)
    create_tariff_assignment(
        session,
        service_point_id=1,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-04-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="test:master-data-link",
    )
    session.commit()

    response = client.get("/master-data?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "/bill-determinants?lang=ko&amp;service_point_id=1&amp;tariff_plan_code=RES-A" in text


def test_canonical_measurements_promote_final_via_web_uses_current_filters(client, session):
    seed_demo_environment(session)
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "demo-read-batch-2",
            "received_at": "2026-04-19T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-19T00:15:00+09:00",
                    "value": 18.4,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    response = client.post(
        "/canonical-measurements/promote-final?lang=ko",
        data={
            "batch_id": "demo-read-batch",
            "meter_id": "MTR-1001",
            "date_from": "2026-04-18",
            "date_to": "2026-04-18",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "최종 계측 승격이 완료되었습니다." in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 1


def test_canonical_measurements_promote_final_rejects_invalid_date_range_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.post(
        "/canonical-measurements/promote-final?lang=ko",
        data={
            "batch_id": "demo-read-batch",
            "meter_id": "MTR-1001",
            "date_from": "2026-04-19",
            "date_to": "2026-04-18",
        },
        follow_redirects=True,
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "시작일은 종료일보다 늦을 수 없습니다." in text
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0


def test_operational_events_page_filters_closed_alerts_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()
    response = client.get(
        "/api/v1/operational-events?stream_type=alert&event_code=canonical_failed&batch_id=demo-read-batch"
    )
    alert_id = response.get_json()[0]["id"]
    close_operational_alert(session, alert_id)
    session.commit()

    response = client.get(
        "/operational-events?lang=ko&stream_type=alert&alert_status=closed&batch_id=demo-read-batch"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "운영 이벤트" in text
    assert "표준화 주의 필요" in text
    assert "종료됨" in text
    assert "demo-read-batch" in text


def test_operational_events_page_includes_detail_link(client, session):
    seed_demo_environment(session)
    session.commit()

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "canonical_failed")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert event is not None

    response = client.get("/operational-events?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"/operational-events/{event.id}?lang=ko" in text


def test_operational_event_detail_page_shows_lineage_and_related_measurements(client, session):
    seed_demo_environment(session)
    session.commit()

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "canonical_failed")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert event is not None

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "운영 이벤트 상세" in text
    assert "표준화 주의 필요" in text
    assert "Lineage" in text
    assert "demo-read-batch" in text
    assert "MTR-1001" in text
    assert "관련 원시 검침" in text
    assert "관련 표준 계측" in text


def test_operational_event_detail_page_links_to_vee_exception_lineage(client, session):
    from app.models import InitialMeasurement
    from app.services.vee import evaluate_or_get_vee_baseline

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

    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.event_code == "vee_exception_opened")
        .order_by(OperationalEvent.id.desc())
        .limit(1)
    )
    assert event is not None

    response = client.get(f"/operational-events/{event.id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "VEE 예외" in text
    assert f"/vee-exceptions/{event.entity_id}?lang=ko" in text


def test_operational_events_api_rejects_invalid_stream_type_in_korean(client):
    response = client.get("/api/v1/operational-events?lang=ko&stream_type=alerts")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_stream_type",
        "message": "조회 유형은 event 또는 alert 여야 합니다.",
        "locale": "ko",
    }


def test_operational_events_api_returns_filtered_closed_alert(client, session):
    seed_demo_environment(session)
    session.commit()
    response = client.get(
        "/api/v1/operational-events?stream_type=alert&event_code=canonical_failed&batch_id=demo-read-batch"
    )
    alert_id = response.get_json()[0]["id"]
    close_operational_alert(session, alert_id)
    session.commit()

    response = client.get(
        "/api/v1/operational-events?stream_type=alert&alert_status=closed&batch_id=demo-read-batch"
    )

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["event_code"] == "canonical_failed"
    assert row["is_alert"] is True
    assert row["alert_status"] == "closed"
    assert row["batch_id"] == "demo-read-batch"
