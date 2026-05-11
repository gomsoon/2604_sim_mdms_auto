from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import HesSystem, InitialMeasurement, VeeException
from app.services.bill_charges import calculate_bill_charges
from app.services.bill_determinants import calculate_bill_determinants
from app.services.estimation import (
    ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
    apply_estimation_from_vee_exception,
)
from app.services.tariff_assignments import create_tariff_assignment
from app.services.manual_edits import apply_manual_edit_from_vee_exception
from app.services.seeds import seed_demo_environment
from app.services.visibility import (
    build_bill_charge_filters,
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
    get_bill_charge_detail_context,
    get_bill_determinant_detail_context,
    get_usage_transaction_detail_context,
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
        estimated_by="visibility-tester",
        operator_memo="visibility-test",
    )
    session.commit()
    return summary.estimation_audit_id


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
    assert detail.estimation_audit.details["original_initial_measurement_snapshot"]["value"] == "-1.0000"
    assert detail.estimation_audit.details["applied_initial_measurement_snapshot"]["value"] == "18.4000"
    assert (
        detail.estimation_audit.details["correction_policy_snapshot"]["policy_reason_code"]
        == "no_event_specific_override"
    )


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
