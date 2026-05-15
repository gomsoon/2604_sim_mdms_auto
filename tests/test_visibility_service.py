from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    BillCharge,
    BillDeterminant,
    BillingExportRequest,
    Device,
    HesSystem,
    InitialMeasurement,
    MeasuringComponent,
    PipelineRun,
    RawIntervalWindowState,
    ServicePoint,
    VeeException,
)
from app.services.billing_export_processor import process_queued_billing_export_requests
from app.services.billing_export_requests import create_billing_export_request
from app.services.bill_charges import calculate_bill_charges
from app.services.bill_determinants import calculate_bill_determinants
from app.services.auth import create_user_account
from app.services.estimation import (
    ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
    apply_estimation_from_vee_exception,
    apply_synthetic_missing_interval_estimation_from_vee_exception,
)
from app.services.tariff_assignments import create_tariff_assignment
from app.services.manual_edits import apply_manual_edit_from_vee_exception
from app.services.seeds import seed_demo_environment, seed_master_data
from app.services.visibility import (
    build_bill_charge_filters,
    build_billing_export_request_filters,
    build_estimation_audit_filters,
    build_manual_edit_audit_filters,
    build_bill_determinant_filters,
    VisibilityFilterError,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    build_operational_event_filters,
    build_usage_transaction_filters,
    get_estimation_audit_detail_context,
    get_manual_edit_audit_detail_context,
    get_billing_export_request_detail_context,
    get_bill_charge_detail_context,
    get_bill_determinant_detail_context,
    get_usage_transaction_detail_context,
    list_billing_export_requests,
    list_estimation_audits,
    list_manual_edit_audits,
    list_bill_charges,
    list_bill_determinants,
    list_canonical_measurements,
    list_final_measurements,
    list_ingest_batches,
    list_operational_events,
    list_usage_transactions,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.operational_events import close_operational_alert
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def _prepare_bill_charge_visibility(session) -> None:
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="estimation-visibility-neighbor")
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
        source_reference="test:bill-charge-visibility",
    )
    session.commit()
    calculate_bill_charges(
        session,
        charge_type="flat_energy_charge",
        unit_rate_value="120.00000000",
    )
    session.commit()


def _prepare_manual_edit_visibility(session) -> int:
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
        source_reference="test:manual-edit-visibility",
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
        operator_memo="visibility-test",
    )
    session.commit()
    return summary.manual_edit_audit_id


def _prepare_estimation_visibility(session) -> int:
    seed_demo_environment(session)
    actor = create_user_account(
        session,
        login_id="visibility-tester",
        password="secret-password",
        display_name="Visibility Tester",
        role_code="operator",
    )
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "estimation-visibility-neighbor",
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
        source_reference="test:estimation-visibility",
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
        operator_memo="visibility-test",
    )
    session.commit()
    return summary.estimation_audit_id


def _prepare_synthetic_estimation_visibility(session) -> int:
    seed_demo_environment(session)
    actor = create_user_account(
        session,
        login_id="visibility-tester",
        password="secret-password",
        display_name="Visibility Tester",
        role_code="operator",
    )
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    assert service_point_id is not None

    window_start = "2026-04-19T00:00:00+09:00"
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "synthetic-estimation-visibility-read-batch",
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
        source_reference="test:synthetic-estimation-visibility",
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
        operator_memo="synthetic-visibility-test",
    )
    session.commit()
    return summary.estimation_audit_id


def _prepare_billing_export_visibility(
    session,
    *,
    process_request: bool = False,
    make_stale: bool = False,
) -> int:
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
            details={"trigger_source": "visibility_test"},
        )
        charge_run = PipelineRun(
            pipeline_name="bill_charge",
            trigger_type="manual",
            status="completed",
            started_at=now,
            completed_at=now,
            result_code="bill_charge_completed",
            details={"trigger_source": "visibility_test"},
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
            details={"trigger_source": "visibility_test"},
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
            details={"trigger_source": "visibility_test"},
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
        requested_by="visibility_tester",
    )
    session.commit()

    request_id = result.request.id
    if process_request:
        process_queued_billing_export_requests(
            session,
            request_id=request_id,
            processed_by="visibility_worker",
        )
        session.commit()
    elif make_stale:
        request = session.get(BillingExportRequest, request_id)
        assert request is not None
        request.status = "processing"
        request.claimed_by = "visibility_worker"
        request.last_heartbeat_at = datetime(2026, 5, 1, tzinfo=timezone.utc)
        details = dict(request.details or {})
        details["progress_percent"] = 50.0
        details["current_item_id"] = request.request_items[0].id if request.request_items else None
        request.details = details
        session.commit()

    session.expire_all()
    return request_id


def test_build_ingest_batch_filters_rejects_invalid_date_format():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_ingest_batch_filters({"date_from": "2026/04/18"})

    assert exc_info.value.error_code == "invalid_date_filter"


def test_build_canonical_filters_rejects_reversed_date_range():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_canonical_filters({"date_from": "2026-04-19", "date_to": "2026-04-18"})

    assert exc_info.value.error_code == "invalid_date_range"


def test_build_canonical_filters_uses_app_timezone_for_date_only_inputs(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Seoul")

    filters = build_canonical_filters({"date_from": "2026-04-18", "date_to": "2026-04-18"})

    assert filters.date_from == datetime(2026, 4, 17, 15, 0, tzinfo=timezone.utc)
    assert filters.date_to == datetime(2026, 4, 18, 14, 59, 59, 999999, tzinfo=timezone.utc)


def test_list_ingest_batches_filters_by_batch_and_record_type(session):
    seed_demo_environment(session)
    session.commit()

    rows = list_ingest_batches(
        session,
        build_ingest_batch_filters(
            {
                "batch_id": "demo-event-batch",
                "source_system": "HES",
                "record_type": "hes_event_raw",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].batch_id == "demo-event-batch"
    assert rows[0].record_type == "hes_event_raw"


def test_list_canonical_measurements_filters_by_batch_and_meter_id(session):
    seed_demo_environment(session)
    session.commit()

    matched_rows = list_canonical_measurements(
        session,
        build_canonical_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-1001",
            }
        ),
    )
    unmatched_rows = list_canonical_measurements(
        session,
        build_canonical_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].hes_read_raw.ingest_batch.batch_id == "demo-read-batch"
    assert matched_rows[0].hes_read_raw.meter_identifier == "MTR-1001"
    assert unmatched_rows == []


def test_list_final_measurements_filters_by_batch_and_meter_id(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    matched_rows = list_final_measurements(
        session,
        build_final_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-1001",
            }
        ),
    )
    unmatched_rows = list_final_measurements(
        session,
        build_final_filters(
            {
                "batch_id": "demo-read-batch",
                "meter_id": "MTR-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].canonical_measurement.hes_read_raw.ingest_batch.batch_id == "demo-read-batch"
    assert matched_rows[0].canonical_measurement.hes_read_raw.meter_identifier == "MTR-1001"
    assert unmatched_rows == []


def test_build_usage_transaction_filters_rejects_invalid_usage_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_usage_transaction_filters({"usage_type": "hourly"})

    assert exc_info.value.error_code == "invalid_usage_type_filter"


def test_list_usage_transactions_filters_by_service_point_channel_and_status(session):
    seed_demo_environment(session)
    session.commit()
    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    session.commit()

    matched_rows = list_usage_transactions(
        session,
        build_usage_transaction_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "usage_type": "daily_consumption",
                "calculation_status": "partial",
            }
        ),
    )
    unmatched_rows = list_usage_transactions(
        session,
        build_usage_transaction_filters(
            {
                "service_point": "SP-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert matched_rows[0].usage_type == "daily_consumption"
    assert matched_rows[0].calculation_status == "partial"
    assert unmatched_rows == []


def test_build_bill_determinant_filters_rejects_invalid_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_bill_determinant_filters({"determinant_type": "daily_total"})

    assert exc_info.value.error_code == "invalid_bill_determinant_type_filter"


def test_list_bill_determinants_filters_by_service_point_channel_and_status(session):
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

    matched_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "determinant_type": "billing_cycle_consumption_total",
                "calculation_status": "partial",
            }
        ),
    )
    unmatched_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "service_point": "SP-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert matched_rows[0].determinant_type == "billing_cycle_consumption_total"
    assert matched_rows[0].calculation_status == "partial"
    assert unmatched_rows == []


def test_list_bill_determinants_filters_by_hes_system(session):
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

    demo_hes = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert demo_hes is not None

    rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "hes_system_id": str(demo_hes.id),
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].service_point.external_id == "SP-1001"


def test_list_bill_determinants_filters_by_billing_cycle_mode_and_quality_summary(session):
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

    rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "billing_cycle_mode": "calendar_month",
                "quality_summary": "missing_intervals",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].details["billing_context_snapshot"]["billing_cycle_mode"] == "calendar_month"
    assert rows[0].quality_summary == "missing_intervals"


def test_list_bill_determinants_filters_by_tariff_assignment_presence_and_plan_code(session):
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

    missing_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "tariff_assignment_presence": "missing",
            }
        ),
    )
    assert len(missing_rows) == 1

    create_tariff_assignment(
        session,
        service_point_id=1,
        tariff_plan_code="RES-A",
        tariff_version_code="v1",
        effective_from="2026-04-01T00:00:00+09:00",
        effective_to=None,
        source_system="manual",
        source_reference="test:visibility",
    )
    session.commit()

    assigned_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "tariff_assignment_presence": "assigned",
                "tariff_plan_code": "RES-A",
            }
        ),
    )
    unmatched_rows = list_bill_determinants(
        session,
        build_bill_determinant_filters(
            {
                "tariff_plan_code": "RES-Z",
            }
        ),
    )

    assert len(assigned_rows) == 1
    assert assigned_rows[0].service_point.external_id == "SP-1001"
    assert unmatched_rows == []


def test_get_bill_determinant_detail_context_loads_source_usage_and_revision_rows(session):
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

    detail = get_bill_determinant_detail_context(session, 1)

    assert detail is not None
    assert detail.bill_determinant.id == 1
    assert len(detail.source_usage_rows) == 1
    assert detail.source_usage_rows[0].usage_type == "monthly_consumption"
    assert len(detail.revision_rows) == 1
    assert detail.applicable_tariff_assignment is None


def test_get_bill_determinant_detail_context_loads_applicable_tariff_assignment(session):
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
        source_reference="test:detail",
    )
    session.commit()

    detail = get_bill_determinant_detail_context(session, 1)

    assert detail is not None
    assert detail.applicable_tariff_assignment is not None
    assert detail.applicable_tariff_assignment.tariff_plan_code == "RES-A"


def test_build_bill_charge_filters_rejects_invalid_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_bill_charge_filters({"charge_type": "demand_charge"})

    assert exc_info.value.error_code == "invalid_bill_charge_type_filter"


def test_list_bill_charges_filters_by_service_point_channel_and_status(session):
    _prepare_bill_charge_visibility(session)

    matched_rows = list_bill_charges(
        session,
        build_bill_charge_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "charge_type": "flat_energy_charge",
                "calculation_status": "partial",
                "tariff_plan_code": "RES-A",
                "currency_code": "KRW",
            }
        ),
    )
    unmatched_rows = list_bill_charges(
        session,
        build_bill_charge_filters(
            {
                "service_point": "SP-4040",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert matched_rows[0].charge_type == "flat_energy_charge"
    assert matched_rows[0].calculation_status == "partial"
    assert matched_rows[0].tariff_plan_code == "RES-A"
    assert matched_rows[0].currency_code == "KRW"
    assert unmatched_rows == []


def test_get_bill_charge_detail_context_loads_source_determinant_and_revision_rows(session):
    _prepare_bill_charge_visibility(session)

    detail = get_bill_charge_detail_context(session, 1)

    assert detail is not None
    assert detail.bill_charge.id == 1
    assert detail.bill_determinant is not None
    assert detail.bill_determinant.id == 1
    assert len(detail.revision_rows) == 1


def test_usage_transaction_detail_context_loads_bill_charge_rows(session):
    _prepare_bill_charge_visibility(session)

    detail = get_usage_transaction_detail_context(session, 1)

    assert detail is not None
    assert len(detail.bill_determinant_rows) == 1
    assert len(detail.bill_charge_rows) == 1
    assert detail.bill_charge_rows[0].charge_type == "flat_energy_charge"


def test_get_bill_determinant_detail_context_loads_bill_charge_rows(session):
    _prepare_bill_charge_visibility(session)

    detail = get_bill_determinant_detail_context(session, 1)

    assert detail is not None
    assert len(detail.bill_charge_rows) == 1
    assert detail.bill_charge_rows[0].bill_determinant_id == detail.bill_determinant.id


def test_list_manual_edit_audits_filters_by_service_point_reason_and_status(session):
    manual_edit_audit_id = _prepare_manual_edit_visibility(session)

    matched_rows = list_manual_edit_audits(
        session,
        build_manual_edit_audit_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "edit_status": "applied",
                "reason_code": "operator_meter_correction",
                "policy_reason_code": "no_event_specific_override",
                "event_context_type": "outage",
            }
        ),
    )
    unmatched_rows = list_manual_edit_audits(
        session,
        build_manual_edit_audit_filters(
            {
                "event_context_type": "tamper",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].id == manual_edit_audit_id
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert matched_rows[0].edit_status == "applied"
    assert matched_rows[0].reason_code == "operator_meter_correction"
    assert unmatched_rows == []


def test_get_manual_edit_audit_detail_context_loads_lineage_and_result_final(session):
    manual_edit_audit_id = _prepare_manual_edit_visibility(session)

    detail = get_manual_edit_audit_detail_context(session, manual_edit_audit_id)

    assert detail is not None
    assert detail.manual_edit_audit.id == manual_edit_audit_id
    assert detail.pipeline_run is not None
    assert detail.related_vee_exception is not None
    assert detail.target_initial_measurement is not None
    assert detail.superseded_final_measurement is not None
    assert detail.result_final_measurement is not None
    assert detail.manual_edit_audit.details["original_initial_measurement_snapshot"]["value"] == "-1.0000"
    assert detail.manual_edit_audit.details["applied_initial_measurement_snapshot"]["value"] == "12.5000"


def test_list_estimation_audits_filters_by_service_point_strategy_status_and_policy(session):
    estimation_audit_id = _prepare_estimation_visibility(session)

    matched_rows = list_estimation_audits(
        session,
        build_estimation_audit_filters(
            {
                "service_point": "SP-1001",
                "external_channel_id": "CH-01",
                "estimation_status": "applied",
                "strategy_code": "previous_value_based",
                "policy_reason_code": "no_event_specific_override",
                "event_context_type": "outage",
            }
        ),
    )
    unmatched_rows = list_estimation_audits(
        session,
        build_estimation_audit_filters(
            {
                "policy_reason_code": "tamper_correlated_value_anomaly",
            }
        ),
    )

    assert len(matched_rows) == 1
    assert matched_rows[0].id == estimation_audit_id
    assert matched_rows[0].service_point.external_id == "SP-1001"
    assert matched_rows[0].measuring_component.external_channel_id == "CH-01"
    assert unmatched_rows == []


def test_get_estimation_audit_detail_context_loads_lineage_and_source_finals(session):
    estimation_audit_id = _prepare_estimation_visibility(session)

    detail = get_estimation_audit_detail_context(session, estimation_audit_id)

    assert detail is not None
    assert detail.estimation_audit.id == estimation_audit_id
    assert detail.pipeline_run is not None
    assert detail.related_vee_exception is not None
    assert detail.target_initial_measurement is not None
    assert detail.source_previous_final_measurement is not None
    assert detail.source_next_final_measurement is not None
    assert detail.result_final_measurement is not None
    assert detail.estimated_actor_display == "Visibility Tester (visibility-tester)"
    assert detail.estimation_audit.details["original_initial_measurement_snapshot"]["value"] == "-1.0000"
    assert detail.estimation_audit.details["applied_initial_measurement_snapshot"]["value"] == "18.4000"
    assert (
        detail.estimation_audit.details["correction_policy_snapshot"]["policy_reason_code"]
        == "no_event_specific_override"
    )


def test_get_estimation_audit_detail_context_loads_synthetic_anchor_and_window_state(session):
    estimation_audit_id = _prepare_synthetic_estimation_visibility(session)

    detail = get_estimation_audit_detail_context(session, estimation_audit_id)

    assert detail is not None
    assert detail.estimation_audit.id == estimation_audit_id
    assert detail.estimation_audit.estimation_mode == "synthetic_missing_interval"
    assert detail.related_vee_exception is not None
    assert detail.anchor_vee_exception is not None
    assert detail.related_vee_exception.id == detail.anchor_vee_exception.id
    assert detail.raw_interval_window_state is not None
    assert detail.raw_interval_window_state.completion_status == "complete"
    assert detail.estimated_actor_display == "Visibility Tester (visibility-tester)"
    assert detail.estimation_audit.details["window_context"]["missing_slot_code"] == "30"
    assert (
        detail.estimation_audit.details["synthetic_initial_measurement_snapshot"]["measured_at"]
        == "2026-04-19T00:30:00+09:00"
    )


def test_list_billing_export_requests_filters_by_status_service_point_and_target(session):
    queued_request_id = _prepare_billing_export_visibility(session)
    request = session.get(BillingExportRequest, queued_request_id)
    assert request is not None
    assert request.service_point is not None

    matched_rows = list_billing_export_requests(
        session,
        build_billing_export_request_filters(
            {
                "status": "queued",
                "service_point": request.service_point.external_id,
                "target_system_code": "generic_json",
                "requested_by": "visibility_tester",
            }
        ),
    )

    assert [row.id for row in matched_rows] == [queued_request_id]
    assert matched_rows[0].service_point is not None
    assert matched_rows[0].service_point.external_id == request.service_point.external_id


def test_get_billing_export_request_detail_context_loads_pipeline_items_and_stale_flag(session):
    request_id = _prepare_billing_export_visibility(session, process_request=True)
    stale_request_id = _prepare_billing_export_visibility(session, make_stale=True)

    detail = get_billing_export_request_detail_context(session, request_id)
    stale_detail = get_billing_export_request_detail_context(session, stale_request_id)

    assert detail is not None
    assert detail.request.id == request_id
    assert detail.latest_pipeline_run is not None
    assert detail.latest_pipeline_run.pipeline_name == "billing_export"
    assert detail.focus_item is not None
    assert detail.focus_item.payload_snapshot["worker_result"]["delivery_mode"] == "staged_only"
    assert detail.recent_items
    assert detail.heartbeat_is_stale is False

    assert stale_detail is not None
    assert stale_detail.request.id == stale_request_id
    assert stale_detail.current_item is not None
    assert stale_detail.heartbeat_is_stale is True


def test_build_operational_event_filters_rejects_invalid_stream_type():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_operational_event_filters({"stream_type": "alerts"})

    assert exc_info.value.error_code == "invalid_stream_type"


def test_build_operational_event_filters_rejects_invalid_hes_system_id():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_operational_event_filters({"hes_system_id": "0"})

    assert exc_info.value.error_code == "invalid_hes_system_filter"


def test_list_operational_events_filters_by_alert_status_and_batch_id(session):
    seed_demo_environment(session)
    session.commit()

    alert = list_operational_events(
        session,
        build_operational_event_filters(
            {
                "stream_type": "alert",
                "event_code": "canonical_failed",
                "batch_id": "demo-read-batch",
            }
        ),
    )[0]
    close_operational_alert(session, alert.id)
    session.commit()

    rows = list_operational_events(
        session,
        build_operational_event_filters(
            {
                "stream_type": "alert",
                "alert_status": "closed",
                "batch_id": "demo-read-batch",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].event_code == "canonical_failed"
    assert rows[0].alert_status == "closed"
    assert rows[0].batch_id == "demo-read-batch"


def test_list_operational_events_filters_by_hes_system(session):
    from app.services.operational_events import record_operational_event

    seed_demo_environment(session)
    session.commit()

    demo_hes = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert demo_hes is not None

    other_hes = HesSystem(
        hes_code="OTHER_HES",
        display_name="Other HES",
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
        instance_code="other_hes_adapter",
    )
    session.commit()

    rows = list_operational_events(
        session,
        build_operational_event_filters({"hes_system_id": str(demo_hes.id)}),
    )

    assert rows
    assert all(row.hes_system_id == demo_hes.id for row in rows)
