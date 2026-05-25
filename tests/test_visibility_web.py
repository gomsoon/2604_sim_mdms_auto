from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.services.bill_charges import calculate_bill_charges
from app.services.billing_export_processor import process_queued_billing_export_requests
from app.services.billing_export_requests import (
    cancel_billing_export_request,
    create_billing_export_request,
    rerun_billing_export_request,
)
from app.services.auth import create_user_account
from app.services.bill_determinants import calculate_bill_determinants
from app.services.estimation import (
    ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
    apply_estimation_from_vee_exception,
    apply_synthetic_missing_interval_estimation_from_vee_exception,
)
from app.models import (
    BillCharge,
    BillDeterminant,
    BillingExportRequest,
    Device,
    EstimationAudit,
    FinalMeasurement,
    IngestBatch,
    InitialMeasurement,
    ManualEditAudit,
    MeasuringComponent,
    OperationalEvent,
    PipelineRun,
    RawIntervalWindowState,
    ServicePoint,
    UserAccount,
    UsageTransaction,
    VeeException,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.manual_edits import apply_manual_edit_from_vee_exception
from app.services.operational_events import close_operational_alert
from app.services.seeds import seed_demo_environment, seed_master_data
from app.services.tariff_assignments import create_tariff_assignment
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def _prepare_bill_charge_rows(session) -> None:
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="estimation-web-neighbor")
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
    actor = create_user_account(
        session,
        login_id="manual-web-tester",
        password="secret-password",
        display_name="Manual Web Tester",
        role_code="operator",
    )
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
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
        operator_memo="manual-edit-web",
    )
    session.commit()
    return summary.manual_edit_audit_id


def _prepare_blocked_manual_edit_audit_rows(session) -> int:
    seed_demo_environment(session)
    actor = create_user_account(
        session,
        login_id="manual-blocked-web-tester",
        password="secret-password",
        display_name="Manual Blocked Web Tester",
        role_code="operator",
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
        reason_code="invalid-reason",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
        operator_memo="manual-edit-blocked-web",
    )
    session.commit()
    return summary.manual_edit_audit_id


def _prepare_estimation_audit_rows(session) -> int:
    seed_demo_environment(session)
    actor = create_user_account(
        session,
        login_id="web-tester",
        password="secret-password",
        display_name="Web Tester",
        role_code="operator",
    )
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "estimation-web-neighbor",
            "received_at": "2026-04-18T09:05:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:00:00+09:00",
                    "value": 18.4,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                },
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-18T00:30:00+09:00",
                    "value": 21.7,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()
    finalize_canonical_measurements(session, limit=50)
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
        source_reference="test:estimation-web",
    )
    session.commit()
    calculate_bill_charges(
        session,
        charge_type="flat_energy_charge",
        unit_rate_value="120.00000000",
    )
    session.commit()

    initial_rows = session.scalars(
        select(InitialMeasurement)
        .where(InitialMeasurement.service_point_id == 1)
        .order_by(InitialMeasurement.measured_at.asc(), InitialMeasurement.id.asc())
    ).all()
    initial_row = initial_rows[1] if len(initial_rows) > 1 else None
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

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by=actor.login_id,
        estimated_by_user_account_id=actor.id,
        operator_memo="web-test",
    )
    session.commit()
    return summary.estimation_audit_id


def _prepare_synthetic_estimation_audit_rows(session) -> int:
    seed_demo_environment(session)
    actor = create_user_account(
        session,
        login_id="web-tester",
        password="secret-password",
        display_name="Web Tester",
        role_code="operator",
    )
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    assert service_point_id is not None

    window_start = "2026-04-19T00:00:00+09:00"
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "synthetic-estimation-web-read-batch",
            "received_at": "2026-04-19T09:00:00+09:00",
            "reads": [
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
                },
            ],
        },
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

    session.add(
        RawIntervalWindowState(
            source_system=anchor_raw.source_system,
            meter_identifier=anchor_raw.meter_identifier,
            channel_identifier=anchor_raw.channel_identifier,
            window_start_at=anchor_raw.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=15,
            expected_slot_count=4,
            received_slot_count=3,
            received_slot_bitmap="00,15,45",
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
        source_reference="test:synthetic-estimation-web",
    )
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
        service_point_id=service_point_id,
    )
    calculate_bill_charges(
        session,
        charge_type="flat_energy_charge",
        unit_rate_value="100.00000000",
        service_point_id=service_point_id,
    )
    session.commit()

    for row in list(anchor_initial.vee_exceptions):
        session.delete(row)
    for row in list(anchor_initial.vee_execution_logs):
        session.delete(row)
    anchor_initial.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, anchor_initial, force=True)
    session.commit()

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == anchor_initial.id)
        .order_by(VeeException.id.desc())
        .limit(1)
    )
    assert vee_exception is not None
    assert vee_exception.exception_code == "vee_missing_interval_detected"

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by=actor.login_id,
        estimated_by_user_account_id=actor.id,
        operator_memo="synthetic-web-test",
    )
    session.commit()
    return summary.estimation_audit_id


def _prepare_billing_export_request_rows(
    session,
    *,
    process_request: bool = False,
    make_stale: bool = False,
) -> int:
    actor = session.scalar(
        select(UserAccount).where(UserAccount.login_id == "billing-export-web-tester").limit(1)
    )
    if actor is None:
        actor = create_user_account(
            session,
            login_id="billing-export-web-tester",
            display_name="Billing Export Web Tester",
            role_code="admin",
            password="test-password",
        )
        session.flush()

    existing_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.is_current.is_(True))
        .order_by(BillCharge.billing_period_start_at.asc(), BillCharge.id.asc())
        .limit(1)
    )
    if existing_charge is None:
        seed_master_data(session)
        session.commit()
        service_point_id = session.scalar(select(ServicePoint.id).limit(1))
        device_id = session.scalar(select(Device.id).limit(1))
        measuring_component_id = session.scalar(select(MeasuringComponent.id).limit(1))
        assert service_point_id is not None
        assert device_id is not None
        assert measuring_component_id is not None

        now = datetime.now(timezone.utc)
        determinant_run = PipelineRun(
            pipeline_name="bill_determinant",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_determinant_completed",
            details={"trigger_source": "web_visibility_test"},
        )
        charge_run = PipelineRun(
            pipeline_name="bill_charge",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_charge_completed",
            details={"trigger_source": "web_visibility_test"},
        )
        session.add_all([determinant_run, charge_run])
        session.flush()

        determinant = BillDeterminant(
            pipeline_run_id=determinant_run.id,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            device_id=device_id,
            determinant_type="billing_cycle_consumption_total",
            billing_period_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            billing_period_end_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            window_timezone_name="Asia/Seoul",
            tariff_plan_code="KR_BASIC",
            unit_of_measure="kWh",
            determinant_value=Decimal("100.0000"),
            source_usage_count=1,
            quality_summary="all_finalized",
            calculation_status="complete",
            revision_number=1,
            revision_reason_code=None,
            is_current=True,
            supersedes_bill_determinant_id=None,
            calculated_at=now,
            details={"trigger_source": "web_visibility_test"},
        )
        session.add(determinant)
        session.flush()

        charge_row = BillCharge(
            pipeline_run_id=charge_run.id,
            service_point_id=service_point_id,
            measuring_component_id=measuring_component_id,
            device_id=device_id,
            bill_determinant_id=determinant.id,
            charge_type="flat_energy_charge",
            billing_period_start_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            billing_period_end_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            currency_code="KRW",
            tariff_plan_code="KR_BASIC",
            tariff_version_code="v1",
            quantity_value=Decimal("100.0000"),
            unit_rate_value=Decimal("120.00000000"),
            charge_amount=Decimal("12000.0000"),
            calculation_status="complete",
            quality_summary="all_finalized",
            revision_number=1,
            revision_reason_code=None,
            is_current=True,
            supersedes_bill_charge_id=None,
            calculated_at=now,
            details={"trigger_source": "web_visibility_test"},
        )
        session.add(charge_row)
        session.commit()
    else:
        charge_row = existing_charge

    result = create_billing_export_request(
        session,
        request_scope="service_point_period",
        service_point_id=charge_row.service_point_id,
        billing_period_from=charge_row.billing_period_start_at,
        billing_period_to=charge_row.billing_period_end_at,
        requested_by=actor.login_id,
        requested_by_user_account_id=actor.id,
    )
    session.commit()

    request_id = result.request.id
    if process_request:
        process_queued_billing_export_requests(
            session,
            request_id=request_id,
            processed_by="web_worker",
        )
        session.commit()
    elif make_stale:
        request = session.get(BillingExportRequest, request_id)
        assert request is not None
        request.status = "processing"
        request.claimed_by = "web_worker"
        request.last_heartbeat_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        details = dict(request.details or {})
        details["progress_percent"] = 50.0
        details["current_item_id"] = request.request_items[0].id if request.request_items else None
        request.details = details
        session.commit()

    session.expire_all()
    return request_id


def _prepare_failed_billing_export_request_rows(
    session,
    *,
    retryable_items: bool = True,
) -> int:
    request_id = _prepare_billing_export_request_rows(session)
    export_request = session.get(BillingExportRequest, request_id)
    assert export_request is not None

    export_request.status = "failed"
    export_request.claimed_by = "web_worker"
    export_request.last_error = "forced export failure"
    export_request.completed_at = datetime.now(timezone.utc)
    export_request.processed_count = export_request.item_count
    export_request.succeeded_count = 0
    export_request.failed_count = 1 if retryable_items and export_request.request_items else 0
    export_request.skipped_count = 0

    if export_request.request_items:
        first_item = export_request.request_items[0]
        if retryable_items:
            first_item.status = "failed"
            first_item.result_code = "worker_failed"
            first_item.last_error = "forced export failure"
        else:
            first_item.status = "completed"
            first_item.result_code = "already_staged"
            first_item.last_error = None

    session.commit()
    session.expire_all()
    return request_id


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


def test_canonical_measurements_page_shows_baseline_empty_guidance(client):
    response = client.get("/canonical-measurements?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 표준 계측이 없습니다." in text
    assert "원시 검침 적재와 매핑이 끝나면 여기서 확인합니다." in text


def test_canonical_measurements_page_shows_filtered_empty_guidance(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/canonical-measurements?lang=ko&meter_id=NO-SUCH-METER")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 표준 계측이 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


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


def test_final_measurements_page_shows_baseline_empty_guidance(client):
    response = client.get("/final-measurements?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 최종 계측이 없습니다." in text
    assert "표준 계측 승격이나 최종화가 끝나면 여기서 확인합니다." in text


def test_final_measurements_page_shows_filtered_empty_guidance(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    response = client.get("/final-measurements?lang=ko&meter_id=NO-SUCH-METER")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 최종 계측이 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


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


def test_service_point_usage_api_returns_filtered_rows(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()

    response = client.get(
        "/api/v1/service-points/1/usage"
        "?usage_type=daily_consumption"
        "&external_channel_id=CH-01"
        "&limit=10"
    )

    assert response.status_code == 200
    assert len(response.get_json()) == 1

    row = response.get_json()[0]

    assert row["service_point_id"] == 1
    assert row["service_point_external_id"] == "SP-1001"
    assert row["external_channel_id"] == "CH-01"
    assert row["usage_type"] == "daily_consumption"
    assert row["unit_of_measure"] == "kWh"
    assert row["calculation_status"] == "partial"
    assert row["quality_summary"] == "missing_intervals"
    assert row["pipeline_run_id"] is not None


def test_service_point_usage_api_rejects_invalid_limit_in_korean(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/usage?lang=ko&limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "limit 값은 1 이상 500 이하의 정수여야 합니다.",
        "locale": "ko",
    }


def test_service_point_usage_api_returns_404_for_missing_service_point(client):
    response = client.get("/api/v1/service-points/999999/usage")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "service_point_not_found",
        "message": "The selected service point does not exist.",
        "locale": "en",
    }


def test_service_point_usage_summary_api_returns_summary_and_rows(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()

    response = client.get(
        "/api/v1/service-points/1/usage-summary"
        "?usage_type=daily_consumption"
        "&external_channel_id=CH-01"
        "&limit=10"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["service_point_id"] == 1
    assert payload["service_point_external_id"] == "SP-1001"
    assert payload["filters"] == {
        "service_point_id": 1,
        "service_point_external_id": "SP-1001",
        "usage_type": "daily_consumption",
        "external_channel_id": "CH-01",
        "date_from": None,
        "date_to": None,
        "calculation_status": None,
        "limit": 10,
    }
    assert payload["summary"]["window_count"] == 1
    assert payload["summary"]["complete_count"] == 0
    assert payload["summary"]["partial_count"] == 1
    assert payload["summary"]["blocked_count"] == 0
    assert payload["summary"]["quality_summaries"] == {"missing_intervals": 1}
    assert payload["summary"]["latest_calculated_at"] is not None
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["usage_type"] == "daily_consumption"
    assert payload["rows"][0]["quality_summary"] == "missing_intervals"


def test_service_point_usage_summary_api_filters_by_date_and_status(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()

    response = client.get(
        "/api/v1/service-points/1/usage-summary"
        "?date_from=2026-04-17T00:00:00Z"
        "&date_to=2026-04-17T23:59:59Z"
        "&calculation_status=partial"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["summary"]["window_count"] == 1
    assert payload["summary"]["partial_count"] == 1
    assert payload["summary"]["blocked_count"] == 0
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["usage_type"] == "daily_consumption"


def test_service_point_usage_summary_api_rejects_invalid_limit(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/usage-summary?limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "Limit must be a positive integer and no greater than 500.",
        "locale": "en",
    }


def test_service_point_usage_summary_api_returns_404_for_missing_service_point(client):
    response = client.get("/api/v1/service-points/999999/usage-summary")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "service_point_not_found",
        "message": "The selected service point does not exist.",
        "locale": "en",
    }


def test_service_point_bill_determinants_api_returns_filtered_rows(client, session):
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
        "/api/v1/service-points/1/bill-determinants"
        "?determinant_type=billing_cycle_consumption_total"
        "&external_channel_id=CH-01"
        "&limit=10"
    )

    assert response.status_code == 200
    rows = response.get_json()
    assert len(rows) == 1

    row = rows[0]
    assert row["service_point_id"] == 1
    assert row["service_point_external_id"] == "SP-1001"
    assert row["external_channel_id"] == "CH-01"
    assert row["determinant_type"] == "billing_cycle_consumption_total"
    assert row["billing_cycle_mode"] == "calendar_month"
    assert row["unit_of_measure"] == "kWh"
    assert row["calculation_status"] == "partial"
    assert row["quality_summary"] == "missing_intervals"
    assert row["pipeline_run_id"] is not None


def test_service_point_bill_determinants_api_filters_by_date_and_status(client, session):
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
        "/api/v1/service-points/1/bill-determinants"
        "?date_from=2026-03-31T00:00:00Z"
        "&date_to=2026-04-01T00:00:00Z"
        "&calculation_status=partial"
    )

    assert response.status_code == 200
    rows = response.get_json()
    assert len(rows) == 1
    assert rows[0]["determinant_type"] == "billing_cycle_consumption_total"
    assert rows[0]["calculation_status"] == "partial"


def test_service_point_bill_determinants_api_rejects_invalid_limit(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/bill-determinants?limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "Limit must be a positive integer and no greater than 500.",
        "locale": "en",
    }


def test_service_point_bill_determinants_api_returns_404_for_missing_service_point(client):
    response = client.get("/api/v1/service-points/999999/bill-determinants")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "service_point_not_found",
        "message": "The selected service point does not exist.",
        "locale": "en",
    }


def test_service_point_bill_charges_api_returns_filtered_rows(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get(
        "/api/v1/service-points/1/bill-charges"
        "?charge_type=flat_energy_charge"
        "&external_channel_id=CH-01"
        "&limit=10"
    )

    assert response.status_code == 200
    rows = response.get_json()
    assert len(rows) == 1

    row = rows[0]
    assert row["service_point_id"] == 1
    assert row["service_point_external_id"] == "SP-1001"
    assert row["external_channel_id"] == "CH-01"
    assert row["charge_type"] == "flat_energy_charge"
    assert row["currency_code"] == "KRW"
    assert row["tariff_plan_code"] == "RES-A"
    assert row["calculation_status"] == "partial"
    assert row["quality_summary"] == "missing_intervals"
    assert row["pipeline_run_id"] is not None


def test_service_point_bill_charges_api_filters_by_date_and_status(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get(
        "/api/v1/service-points/1/bill-charges"
        "?date_from=2026-03-31T00:00:00Z"
        "&date_to=2026-04-01T00:00:00Z"
        "&calculation_status=partial"
    )

    assert response.status_code == 200
    rows = response.get_json()
    assert len(rows) == 1
    assert rows[0]["charge_type"] == "flat_energy_charge"
    assert rows[0]["calculation_status"] == "partial"


def test_service_point_bill_charges_api_rejects_invalid_limit(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/bill-charges?limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "Limit must be a positive integer and no greater than 500.",
        "locale": "en",
    }


def test_service_point_bill_charges_api_returns_404_for_missing_service_point(client):
    response = client.get("/api/v1/service-points/999999/bill-charges")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "service_point_not_found",
        "message": "The selected service point does not exist.",
        "locale": "en",
    }


def test_service_point_invoice_summary_api_returns_summaries(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get(
        "/api/v1/service-points/1/invoice-summary"
        "?tariff_plan_code=RES-A"
        "&summary_status=partial"
        "&limit=10"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["service_point_id"] == 1
    assert payload["service_point_external_id"] == "SP-1001"
    assert payload["filters"] == {
        "service_point_id": 1,
        "service_point_external_id": "SP-1001",
        "external_channel_id": None,
        "charge_type": None,
        "tariff_plan_code": "RES-A",
        "calculation_status": None,
        "summary_status": "partial",
        "date_from": None,
        "date_to": None,
        "limit": 10,
    }
    assert len(payload["summaries"]) == 1
    summary = payload["summaries"][0]
    assert summary["service_point_id"] == 1
    assert summary["service_point_external_id"] == "SP-1001"
    assert summary["currency_code"] == "KRW"
    assert summary["tariff_plan_code"] == "RES-A"
    assert summary["charge_count"] == 1
    assert summary["complete_count"] == 0
    assert summary["partial_count"] == 1
    assert summary["blocked_count"] == 0
    assert summary["summary_status"] == "partial"
    assert summary["export_eligible"] is False
    assert summary["subtotal_amount"] is not None
    assert summary["latest_calculated_at"] is not None


def test_service_point_invoice_summary_api_filters_by_date_and_status(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get(
        "/api/v1/service-points/1/invoice-summary"
        "?date_from=2026-03-31T00:00:00Z"
        "&date_to=2026-04-01T00:00:00Z"
        "&summary_status=partial"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert len(payload["summaries"]) == 1
    assert payload["summaries"][0]["summary_status"] == "partial"
    assert payload["summaries"][0]["partial_count"] == 1


def test_service_point_invoice_summary_api_rejects_invalid_summary_status(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/invoice-summary?summary_status=queued")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_invoice_summary_status_filter",
        "message": "Invoice summary status must be complete, partial, or blocked when provided.",
        "locale": "en",
    }


def test_service_point_invoice_summary_api_rejects_invalid_limit(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/invoice-summary?limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "Limit must be a positive integer and no greater than 500.",
        "locale": "en",
    }


def test_service_point_invoice_summary_api_returns_404_for_missing_service_point(client):
    response = client.get("/api/v1/service-points/999999/invoice-summary")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "service_point_not_found",
        "message": "The selected service point does not exist.",
        "locale": "en",
    }


def test_service_point_summary_api_returns_usage_determinant_and_charge_sections(client, session):
    _prepare_bill_charge_rows(session)
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    response = client.get(
        "/api/v1/service-points/1/summary"
        "?external_channel_id=CH-01"
        "&usage_type=daily_consumption"
        "&determinant_type=billing_cycle_consumption_total"
        "&charge_type=flat_energy_charge"
        "&limit=5"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["service_point_id"] == 1
    assert payload["service_point_external_id"] == "SP-1001"
    assert payload["filters"] == {
        "service_point_id": 1,
        "service_point_external_id": "SP-1001",
        "external_channel_id": "CH-01",
        "date_from": None,
        "date_to": None,
        "calculation_status": None,
        "usage_type": "daily_consumption",
        "determinant_type": "billing_cycle_consumption_total",
        "charge_type": "flat_energy_charge",
        "limit": 5,
    }
    assert payload["usage"]["summary"]["window_count"] == 1
    assert payload["usage"]["summary"]["partial_count"] == 1
    assert len(payload["usage"]["rows"]) == 1
    assert payload["bill_determinants"]["summary"]["row_count"] == 1
    assert payload["bill_determinants"]["summary"]["partial_count"] == 1
    assert len(payload["bill_determinants"]["rows"]) == 1
    assert payload["bill_charges"]["summary"]["row_count"] == 1
    assert payload["bill_charges"]["summary"]["partial_count"] == 1
    assert len(payload["bill_charges"]["rows"]) == 1


def test_service_point_summary_api_filters_by_date_and_status(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get(
        "/api/v1/service-points/1/summary"
        "?date_from=2026-03-31T00:00:00Z"
        "&date_to=2026-04-01T00:00:00Z"
        "&calculation_status=partial"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["usage"]["summary"]["window_count"] == 1
    assert payload["bill_determinants"]["summary"]["row_count"] == 1
    assert payload["bill_charges"]["summary"]["row_count"] == 1
    assert payload["usage"]["rows"][0]["usage_type"] == "monthly_consumption"
    assert payload["bill_determinants"]["rows"][0]["calculation_status"] == "partial"
    assert payload["bill_charges"]["rows"][0]["calculation_status"] == "partial"


def test_service_point_summary_api_rejects_invalid_limit(client, session):
    seed_demo_environment(session)
    session.commit()

    response = client.get("/api/v1/service-points/1/summary?limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "Limit must be a positive integer and no greater than 500.",
        "locale": "en",
    }


def test_service_point_summary_api_returns_404_for_missing_service_point(client):
    response = client.get("/api/v1/service-points/999999/summary")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "service_point_not_found",
        "message": "The selected service point does not exist.",
        "locale": "en",
    }


def test_billing_export_requests_api_returns_filtered_rows(client, session):
    request_id = _prepare_billing_export_request_rows(session, make_stale=True)
    request = session.get(BillingExportRequest, request_id)
    assert request is not None
    assert request.service_point is not None

    response = client.get(
        "/api/v1/billing-export-requests"
        f"?status=processing&service_point={request.service_point.external_id}"
        "&target_system_code=generic_json"
        "&requested_by=billing-export-web-tester"
        "&limit=10"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["filters"] == {
        "request_scope": None,
        "status": "processing",
        "service_point_id": None,
        "service_point": request.service_point.external_id,
        "target_system_code": "generic_json",
        "requested_by": "billing-export-web-tester",
        "date_from": None,
        "date_to": None,
        "limit": 10,
    }
    assert len(payload["rows"]) == 1
    row = payload["rows"][0]
    assert row["id"] == request_id
    assert row["status"] == "processing"
    assert row["service_point_external_id"] == request.service_point.external_id
    assert row["target_system_code"] == "generic_json"
    assert row["requested_by"] == "billing-export-web-tester"
    assert row["requested_actor_display"] == "Billing Export Web Tester (billing-export-web-tester)"
    assert row["claimed_by"] == "web_worker"
    assert row["heartbeat_is_stale"] is True
    assert row["progress_percent"] == 50.0


def test_billing_export_requests_api_rejects_invalid_limit(client):
    response = client.get("/api/v1/billing-export-requests?limit=0")

    assert response.status_code == 400
    assert response.get_json() == {
        "error_code": "invalid_limit",
        "message": "Limit must be a positive integer and no greater than 500.",
        "locale": "en",
    }


def test_billing_export_request_detail_api_returns_runtime_and_payload(client, session):
    request_id = _prepare_billing_export_request_rows(session, process_request=True)

    response = client.get(f"/api/v1/billing-export-requests/{request_id}")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["request"]["id"] == request_id
    assert payload["request"]["status"] == "completed"
    assert (
        payload["request"]["requested_actor_display"]
        == "Billing Export Web Tester (billing-export-web-tester)"
    )
    assert payload["latest_pipeline_run"] is not None
    assert payload["latest_pipeline_run"]["pipeline_name"] == "billing_export"
    assert payload["focus_item"] is not None
    assert payload["focus_item"]["payload_snapshot"]["worker_result"]["delivery_mode"] == "staged_only"
    assert payload["recent_items"]
    assert payload["heartbeat_is_stale"] is False


def test_billing_export_request_detail_api_returns_404_for_missing_request(client):
    response = client.get("/api/v1/billing-export-requests/999999")

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "billing_export_request_not_found",
        "message": "The selected billing export request does not exist.",
        "locale": "en",
    }


def test_cancel_billing_export_request_api_cancels_queued_request(client, session):
    request_id = _prepare_billing_export_request_rows(session)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/cancel",
        json={"operator_memo": "cancel from api"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"] == "cancelled"
    assert payload["request"]["id"] == request_id
    assert payload["request"]["status"] == "cancelled"
    assert payload["request"]["cancelled_by"] == actor.login_id
    assert payload["request"]["cancelled_by_user_account_id"] == actor.id

    refreshed = session.get(BillingExportRequest, request_id)
    assert refreshed is not None
    assert refreshed.status == "cancelled"
    assert refreshed.cancelled_by == actor.login_id
    assert refreshed.cancelled_by_user_account_id == actor.id
    assert refreshed.details["cancelled_by"] == actor.login_id
    assert refreshed.details["cancelled_by_user_account_id"] == actor.id
    assert refreshed.details["cancellation_memo"] == "cancel from api"


def test_cancel_billing_export_request_api_returns_404_for_missing_request(client):
    response = client.post("/api/v1/billing-export-requests/999999/cancel", json={})

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "billing_export_request_not_found",
        "message": "The selected billing export request does not exist.",
        "locale": "en",
    }


def test_cancel_billing_export_request_api_rejects_already_cancelled_request(client, session):
    request_id = _prepare_billing_export_request_rows(session)
    cancel_billing_export_request(session, request_id, cancelled_by="operator_ui")
    session.commit()

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/cancel",
        json={"operator_memo": "cancel again"},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error_code": "billing_export_request_already_cancelled",
        "message": "The selected billing export request is already cancelled.",
        "locale": "en",
    }


def test_cancel_billing_export_request_api_rejects_processing_request(client, session):
    request_id = _prepare_billing_export_request_rows(session, make_stale=True)

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/cancel",
        json={"operator_memo": "stop processing"},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error_code": "billing_export_request_not_cancellable",
        "message": "Only queued billing export requests can be cancelled.",
        "locale": "en",
    }


def test_rerun_billing_export_request_api_creates_recovery_request(client, session):
    request_id = _prepare_failed_billing_export_request_rows(session)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/rerun",
        json={"operator_memo": "rerun from api"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"] == "rerun_created"
    assert payload["source_request_id"] == request_id
    assert payload["created_item_count"] == 1
    assert payload["eligible_item_count"] == 1
    assert payload["skipped_item_count"] == 0
    assert payload["recovery_request"]["status"] == "queued"
    assert payload["recovery_request"]["source_billing_export_request_id"] == request_id
    assert payload["recovery_request"]["recovery_action_code"] == "rerun"
    assert payload["recovery_request"]["requested_by"] == actor.login_id
    assert payload["recovery_request"]["requested_by_user_account_id"] == actor.id

    recovery_request = session.get(BillingExportRequest, payload["recovery_request"]["id"])
    assert recovery_request is not None
    assert recovery_request.operator_memo == "rerun from api"
    assert recovery_request.source_billing_export_request_id == request_id
    assert recovery_request.recovery_action_code == "rerun"
    assert recovery_request.requested_by == actor.login_id
    assert recovery_request.requested_by_user_account_id == actor.id


def test_recreate_billing_export_request_api_creates_recovery_request(client, session):
    request_id = _prepare_failed_billing_export_request_rows(session)
    actor = session.scalar(select(UserAccount).where(UserAccount.login_id == "admin").limit(1))
    assert actor is not None

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/recreate",
        json={"operator_memo": "recreate from api"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"] == "recreate_created"
    assert payload["source_request_id"] == request_id
    assert payload["created_item_count"] == 1
    assert payload["eligible_item_count"] == 1
    assert payload["skipped_item_count"] == 0
    assert payload["recovery_request"]["status"] == "queued"
    assert payload["recovery_request"]["source_billing_export_request_id"] == request_id
    assert payload["recovery_request"]["recovery_action_code"] == "recreate"
    assert payload["recovery_request"]["requested_by"] == actor.login_id
    assert payload["recovery_request"]["requested_by_user_account_id"] == actor.id

    recovery_request = session.get(BillingExportRequest, payload["recovery_request"]["id"])
    assert recovery_request is not None
    assert recovery_request.operator_memo == "recreate from api"
    assert recovery_request.source_billing_export_request_id == request_id
    assert recovery_request.recovery_action_code == "recreate"
    assert recovery_request.requested_by == actor.login_id
    assert recovery_request.requested_by_user_account_id == actor.id


def test_rerun_billing_export_request_api_returns_404_for_missing_request(client):
    response = client.post("/api/v1/billing-export-requests/999999/rerun", json={})

    assert response.status_code == 404
    assert response.get_json() == {
        "error_code": "billing_export_request_not_found",
        "message": "The selected billing export request does not exist.",
        "locale": "en",
    }


def test_rerun_billing_export_request_api_rejects_non_failed_request(client, session):
    request_id = _prepare_billing_export_request_rows(session)

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/rerun",
        json={"operator_memo": "rerun queued"},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error_code": "billing_export_request_not_failed",
        "message": "Only failed billing export requests can be recovered.",
        "locale": "en",
    }


def test_rerun_billing_export_request_api_rejects_when_active_recovery_exists(client, session):
    request_id = _prepare_failed_billing_export_request_rows(session)
    rerun_billing_export_request(
        session,
        request_id,
        requested_by="operator_ui",
        operator_memo="existing recovery",
    )
    session.commit()

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/rerun",
        json={"operator_memo": "duplicate recovery"},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error_code": "billing_export_request_active_recovery_exists",
        "message": "An active recovery request already exists for the selected billing export request.",
        "locale": "en",
    }


def test_rerun_billing_export_request_api_rejects_when_no_retryable_items(client, session):
    request_id = _prepare_failed_billing_export_request_rows(session, retryable_items=False)

    response = client.post(
        f"/api/v1/billing-export-requests/{request_id}/rerun",
        json={"operator_memo": "rerun empty"},
    )

    assert response.status_code == 409
    assert response.get_json() == {
        "error_code": "billing_export_request_no_retryable_items",
        "message": "The selected billing export request does not have retryable items.",
        "locale": "en",
    }


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


def test_usage_transactions_page_shows_baseline_empty_guidance(client):
    response = client.get("/usage-transactions?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 기록된 사용량 거래가 없습니다." in text
    assert "최종 계측이 준비된 뒤 사용량 재계산이 실행되면 여기서 확인합니다." in text


def test_usage_transactions_page_shows_filtered_empty_guidance(client, session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    response = client.get("/usage-transactions?lang=ko&service_point=SP-9999")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 사용량 거래가 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


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
    assert "연계 흐름" in text
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


def test_bill_determinants_page_shows_baseline_empty_guidance(client):
    response = client.get("/bill-determinants?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "아직 계산된 청구 결정값이 없습니다." in text
    assert "사용량 거래와 청구 컨텍스트가 준비된 뒤 결정값 계산 결과를 여기서 확인합니다." in text


def test_bill_determinants_page_shows_filtered_empty_guidance(client, session):
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

    response = client.get("/bill-determinants?lang=ko&service_point=SP-9999")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 청구 결정값이 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


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
    assert "연계 흐름" in text
    assert "원본 사용량 거래" in text
    assert "개정 이력" in text
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


def test_bill_charges_page_shows_baseline_empty_guidance(client):
    response = client.get("/bill-charges?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 계산 결과 항목" in text
    assert "아직 계산된 청구 금액이 없습니다." in text
    assert "청구 결정값과 요금 정보가 준비된 뒤 청구 금액 계산 결과를 여기서 확인합니다." in text


def test_bill_charges_page_shows_filtered_empty_guidance(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get("/bill-charges?lang=ko&service_point=SP-9999")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터와 일치하는 청구 금액이 없습니다." in text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in text


def test_bill_charge_detail_page_shows_determinant_tariff_and_revision_context(client, session):
    _prepare_bill_charge_rows(session)

    response = client.get("/bill-charges/1?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 금액 상세" in text
    assert "연계 흐름" in text
    assert "원본 청구 결정값" in text
    assert "요금제 할당" in text
    assert "요율 스냅샷" in text
    assert "개정 이력" in text
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
        "/manual-edit-audits?lang=ko&service_point=SP-1001&external_channel_id=CH-01&edit_status=applied&reason_code=operator_meter_correction&policy_reason_code=no_event_specific_override&event_context_type=outage"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터" in text
    assert "필터를 초기화하면 전체 목록을 다시 볼 수 있습니다." in text
    assert "수동 보정 감사 이력" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "운영자 계량기 보정" in text
    assert "이벤트 기반 보정 override가 적용되지 않습니다" in text
    assert f"/manual-edit-audits/{manual_edit_audit_id}?lang=ko" in text


def test_manual_edit_audits_page_distinguishes_filtered_and_baseline_empty_states(client):
    baseline = client.get("/manual-edit-audits?lang=ko")
    baseline_text = baseline.get_data(as_text=True)

    assert baseline.status_code == 200
    assert "아직 기록된 수동 보정 감사 이력이 없습니다." in baseline_text
    assert "지원되는 VEE 예외에서 수동 보정을 적용하면 여기서 결과를 확인할 수 있습니다." in baseline_text

    filtered = client.get("/manual-edit-audits?lang=ko&edit_status=applied")
    filtered_text = filtered.get_data(as_text=True)

    assert filtered.status_code == 200
    assert "현재 필터와 일치하는 수동 보정 감사 이력이 없습니다." in filtered_text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in filtered_text


def test_estimation_audits_page_renders_filtered_rows(client, session):
    estimation_audit_id = _prepare_estimation_audit_rows(session)

    response = client.get(
        "/estimation-audits?lang=ko&service_point=SP-1001&external_channel_id=CH-01&estimation_status=applied&strategy_code=previous_value_based&policy_reason_code=no_event_specific_override&event_context_type=outage"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터" in text
    assert "필터를 초기화하면 전체 목록을 다시 볼 수 있습니다." in text
    assert "추정 감사 이력" in text
    assert "SP-1001" in text
    assert "MTR-1001" in text
    assert "CH-01" in text
    assert "이전 값 기반" in text
    assert "적용됨" in text
    assert "이벤트 기반 보정 override가 적용되지 않습니다" in text
    assert f"/estimation-audits/{estimation_audit_id}?lang=ko" in text


def test_estimation_audits_page_distinguishes_filtered_and_baseline_empty_states(client):
    baseline = client.get("/estimation-audits?lang=ko")
    baseline_text = baseline.get_data(as_text=True)

    assert baseline.status_code == 200
    assert "아직 기록된 추정 감사 이력이 없습니다." in baseline_text
    assert "지원되는 VEE 예외에서 추정을 적용하면 여기서 결과를 확인할 수 있습니다." in baseline_text

    filtered = client.get("/estimation-audits?lang=ko&estimation_status=applied")
    filtered_text = filtered.get_data(as_text=True)

    assert filtered.status_code == 200
    assert "현재 필터와 일치하는 추정 감사 이력이 없습니다." in filtered_text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in filtered_text


def test_estimation_audit_detail_page_shows_policy_and_source_snapshots(client, session):
    estimation_audit_id = _prepare_estimation_audit_rows(session)
    audit_row = session.get(EstimationAudit, estimation_audit_id)
    assert audit_row is not None

    response = client.get(f"/estimation-audits/{estimation_audit_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "추정 감사 상세" in text
    assert "여기서 운영자, 결과, 차단 사유, 현재 보정 결과를 먼저 확인한 뒤 스냅샷을 읽습니다." in text
    assert "연계 흐름에서 대상 initial, 관련 VEE 예외, 최종 개정 흐름을 따라갑니다." in text
    assert "보정 정책" in text
    assert "관련 VEE 예외 스냅샷" in text
    assert "이전 source final 스냅샷" in text
    assert "결과 final 스냅샷" in text
    assert "현재 기본 보정 흐름을 그대로 따릅니다" in text
    assert "이벤트 기반 보정 override가 적용되지 않습니다" in text
    assert "Web Tester (web-tester)" in text
    assert "사람 계정" in text
    assert "운영 메모" in text
    assert "web-test" in text
    assert "결과" in text
    assert "추정 적용 완료" in text
    assert "18.4000" in text
    assert (
        f"/vee-exceptions/{audit_row.details['target_vee_exception_snapshot']['vee_exception_id']}?lang=ko"
        in text
    )


def test_estimation_audit_detail_page_shows_synthetic_repair_context(client, session):
    estimation_audit_id = _prepare_synthetic_estimation_audit_rows(session)
    audit_row = session.get(EstimationAudit, estimation_audit_id)
    assert audit_row is not None
    assert audit_row.anchor_vee_exception_id is not None

    response = client.get(f"/estimation-audits/{estimation_audit_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "추정 감사 상세" in text
    assert "synthetic 복구 컨텍스트" in text
    assert "추정 모드" in text
    assert "누락 slot" in text
    assert "구간 상태(전)" in text
    assert "구간 상태(후)" in text
    assert "synthetic raw 스냅샷" in text
    assert "synthetic initial 스냅샷" in text
    assert "synthetic missing-interval 복구" in text
    assert "Web Tester (web-tester)" in text
    assert "사람 계정" in text
    assert "운영 메모" in text
    assert "synthetic-web-test" in text
    assert "결과" in text
    assert "00:30:00+09:00" in text
    assert "00,15,30,45" in text
    assert f"/vee-exceptions/{audit_row.anchor_vee_exception_id}?lang=ko" in text


def test_billing_export_requests_page_renders_filtered_rows_and_stale_warning(client, session):
    request_id = _prepare_billing_export_request_rows(session, make_stale=True)
    request = session.get(BillingExportRequest, request_id)
    assert request is not None
    assert request.service_point is not None

    response = client.get(
        f"/billing-export-requests?lang=ko&status=processing&service_point={request.service_point.external_id}&target_system_code=generic_json&requested_by=billing-export-web-tester"
    )
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "현재 필터" in text
    assert "필터를 초기화하면 전체 목록을 다시 볼 수 있습니다." in text
    assert "청구 내보내기 요청" in text
    assert request.service_point.external_id in text
    assert "Billing Export Web Tester (billing-export-web-tester)" in text
    assert "사람 계정" in text
    assert "런타임 작업자" in text
    assert "worker가 export item을 처리 중입니다." in text
    assert "즉시 런타임 확인" in text
    assert "worker heartbeat 지연" in text
    assert "최근 heartbeat와 마지막 오류를 함께 확인해 운영자 확인이 필요한지 판단하세요." in text
    assert f"/billing-export-requests/{request_id}?lang=ko" in text


def test_billing_export_requests_page_distinguishes_filtered_and_baseline_empty_states(client):
    baseline = client.get("/billing-export-requests?lang=ko")
    baseline_text = baseline.get_data(as_text=True)

    assert baseline.status_code == 200
    assert "아직 청구 내보내기 요청이 없습니다." in baseline_text
    assert "내보내기 대상이 준비되면 새 요청을 만들거나 실행한 뒤 여기서 진행 상황을 확인하세요." in baseline_text

    filtered = client.get("/billing-export-requests?lang=ko&status=queued")
    filtered_text = filtered.get_data(as_text=True)

    assert filtered.status_code == 200
    assert "현재 필터와 일치하는 청구 내보내기 요청이 없습니다." in filtered_text
    assert "필터를 완화하거나 초기화한 뒤 다시 확인하세요." in filtered_text


def test_billing_export_requests_page_uses_recorded_actor_fallback(client, session):
    request_id = _prepare_billing_export_request_rows(session)
    request = session.get(BillingExportRequest, request_id)
    assert request is not None
    request.requested_by_user_account_id = None
    session.commit()

    response = client.get(f"/billing-export-requests?lang=ko&requested_by={request.requested_by}")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert request.requested_by in text
    assert "기록된 요청자" in text


def test_billing_export_request_detail_page_shows_progress_pipeline_and_payload(client, session):
    request_id = _prepare_billing_export_request_rows(session, process_request=True)

    response = client.get(f"/billing-export-requests/{request_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "청구 내보내기 요청 상세" in text
    assert "여기서 요청 상태, 요청자와 처리 주체 정보, 취소 이력, 마지막 오류 신호를 먼저 확인합니다." in text
    assert "진행률" in text
    assert "처리/남은/성공/실패/건너뜀 수치를 함께 읽어 요청이 계속 진행 중인지, 후속 확인이 필요한지 판단합니다." in text
    assert "파이프라인 실행" in text
    assert "processing 중이면 지금 worker가 처리 중인 export item을 보여줍니다." in text
    assert "가장 최근에 처리 완료된 export item을 확인합니다." in text
    assert "선택된 payload 스냅샷" in text
    assert "현재 가장 관련 있는 export item의 staged payload를 확인합니다." in text
    assert "요약과 item 정보만으로 부족할 때 참고용 metadata를 확인합니다." in text
    assert "generic_json" in text
    assert "staged_only" in text
    assert "Billing Export Web Tester (billing-export-web-tester)" in text
    assert "사람 계정" in text
    assert "런타임 작업자" in text
    assert "web_worker" in text


def test_billing_export_request_detail_page_shows_workflow_placeholders(client, session):
    request_id = _prepare_billing_export_request_rows(session)

    response = client.get(f"/billing-export-requests/{request_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이 export request와 연결된 파이프라인 실행이 아직 없습니다." in text
    assert "요청이 아직 queued 상태이거나 worker가 첫 pipeline 실행을 시작하지 않았을 수 있습니다." in text
    assert "현재 processing 상태로 표시된 export item이 없습니다." in text
    assert "요청이 processing 상태가 아니라면 정상입니다. 아직 대기 중이거나 이미 끝난 요청에서는 현재 item이 없을 수 있습니다." in text
    assert "이 request에 기록된 실패 export item이 없습니다." in text
    assert "요청이 실패나 부분 완료 상태가 아니라면 정상 신호입니다." in text


def test_billing_export_request_detail_page_shows_stale_runtime_guidance(client, session):
    request_id = _prepare_billing_export_request_rows(session, make_stale=True)

    response = client.get(f"/billing-export-requests/{request_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "이 export request는 아직 processing 상태지만 worker heartbeat가 오래되었습니다." in text
    assert "최근 heartbeat, 런타임 작업자, 마지막 오류를 함께 확인한 뒤 재시도 또는 개입 여부를 판단하세요." in text
    assert "worker heartbeat 지연" in text
    assert "최근 heartbeat와 마지막 오류를 함께 확인해 운영자 확인이 필요한지 판단하세요." in text


def test_billing_export_request_detail_page_shows_failed_follow_up_wording(client, session):
    request_id = _prepare_failed_billing_export_request_rows(session)

    response = client.get(f"/billing-export-requests/{request_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "실패 item 검토가 필요합니다." in text
    assert "실패 또는 부분 완료 요청에서는 이 목록부터 보면 다음 확인할 export item을 빠르게 찾을 수 있습니다." in text
    assert "forced export failure" in text
    assert "마지막 오류는 failed item과 heartbeat 상태를 함께 볼 때 가장 유용합니다." in text


def test_billing_export_request_detail_page_shows_cancelled_lifecycle_wording(client, session):
    request_id = _prepare_billing_export_request_rows(session)
    actor = session.scalar(
        select(UserAccount).where(UserAccount.login_id == "billing-export-web-tester").limit(1)
    )
    assert actor is not None

    cancel_billing_export_request(
        session,
        request_id,
        cancelled_by=actor.login_id,
        cancelled_by_user_account_id=actor.id,
        operator_memo="cancelled-by-web",
    )
    session.commit()

    response = client.get(f"/billing-export-requests/{request_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "모든 export item 처리가 끝나기 전에 취소되었습니다." in text
    assert "이 필드는 모든 export item이 끝나기 전에 운영자 취소로 중단되었는지 보여줍니다." in text
    assert "cancelled-by-web" in text
    assert "Billing Export Web Tester (billing-export-web-tester)" in text
    assert "사람 계정" in text


def test_manual_edit_audit_detail_page_shows_snapshots_and_lineage(client, session):
    manual_edit_audit_id = _prepare_manual_edit_audit_rows(session)
    audit_row = session.get(ManualEditAudit, manual_edit_audit_id)
    assert audit_row is not None

    response = client.get(f"/manual-edit-audits/{manual_edit_audit_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "수동 보정 감사 상세" in text
    assert "여기서 운영자, 결과, 차단 사유, 현재 보정 결과를 먼저 확인한 뒤 스냅샷을 읽습니다." in text
    assert "연계 흐름에서 대상 initial, 관련 VEE 예외, 최종 개정 흐름을 따라갑니다." in text
    assert "원본 initial 스냅샷" in text
    assert "적용된 initial 스냅샷" in text
    assert "관련 VEE 예외" in text
    assert "보정 정책" in text
    assert "현재 기본 보정 흐름을 그대로 따릅니다" in text
    assert "이벤트 기반 보정 override가 적용되지 않습니다" in text
    assert "후속 재계산" in text
    assert "운영자 계량기 보정" in text
    assert "Manual Web Tester (manual-web-tester)" in text
    assert "사람 계정" in text
    assert "운영 메모" in text
    assert "manual-edit-web" in text
    assert "결과" in text
    assert "수동 보정 적용 완료" in text
    assert "12.5000" in text
    assert f"/vee-exceptions/{audit_row.related_vee_exception_id}?lang=ko" in text


def test_manual_edit_audit_detail_page_shows_blocked_reason_in_summary(client, session):
    manual_edit_audit_id = _prepare_blocked_manual_edit_audit_rows(session)

    response = client.get(f"/manual-edit-audits/{manual_edit_audit_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "수동 보정 감사 상세" in text
    assert "Manual Blocked Web Tester (manual-blocked-web-tester)" in text
    assert "사람 계정" in text
    assert "운영 메모" in text
    assert "manual-edit-blocked-web" in text
    assert "결과" in text
    assert "차단: 잘못된 수동 보정 사유" in text
    assert "차단 사유" in text
    assert "권장 다음 조치" in text
    assert "관련 VEE 예외와 보정 정책을 먼저 확인한 뒤, 다른 지원 보정 경로가 있는지 다시 판단합니다." in text
    assert "수동 보정 사유 코드가 유효하지 않습니다" in text


def test_vee_exception_page_links_to_estimation_audit_detail(client, session):
    estimation_audit_id = _prepare_estimation_audit_rows(session)
    audit_row = session.get(EstimationAudit, estimation_audit_id)
    assert audit_row is not None
    vee_exception_id = audit_row.details["target_vee_exception_snapshot"]["vee_exception_id"]

    response = client.get(f"/vee-exceptions/{vee_exception_id}?lang=ko")
    text = response.get_data(as_text=True)

    assert response.status_code == 200
    assert f"/estimation-audits/{estimation_audit_id}?lang=ko" in text


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
    assert "연계 흐름" in text
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
