from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

import app.services.estimation as estimation_service
from app.models import (
    BillCharge,
    BillDeterminant,
    EstimationAudit,
    FinalMeasurement,
    HesReadRaw,
    HesSystem,
    InitialMeasurement,
    RawIntervalWindowState,
    ServicePoint,
    VeeException,
)
from app.services.bill_charges import (
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
    calculate_bill_charges,
)
from app.services.bill_determinants import (
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
    calculate_bill_determinants,
)
from app.services.auth import create_user_account
from app.services.estimation import (
    ESTIMATION_REVISION_REASON_CODE,
    ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
    ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
    ESTIMATION_QUALITY_CODE,
    apply_estimation_from_vee_exception,
    apply_synthetic_missing_interval_estimation_from_vee_exception,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_events, ingest_reads
from app.services.seeds import seed_demo_environment
from app.services.tariff_assignments import create_tariff_assignment
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def _prepare_estimation_environment(
    session,
    *,
    include_previous: bool = True,
    include_next: bool = True,
) -> tuple[int, int, int]:
    seed_demo_environment(session)
    hes_system_id = session.scalar(select(HesSystem.id).limit(1))
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    assert hes_system_id is not None
    assert service_point_id is not None

    extra_reads: list[dict[str, object]] = []
    if include_previous:
        extra_reads.append(
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-18T00:00:00+09:00",
                "value": 10.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
            }
        )
    if include_next:
        extra_reads.append(
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-18T00:30:00+09:00",
                "value": 20.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
            }
        )
    if extra_reads:
        ingest_reads(
            session,
            {
                "source_system": "HES",
                "batch_id": "estimation-neighbor-read-batch",
                "received_at": "2026-04-18T09:10:00+09:00",
                "reads": extra_reads,
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
    if include_previous and include_next:
        target_row = rows[1]
    else:
        target_row = rows[0]
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


def _open_high_value_vee_exception_with_tamper(
    session,
    *,
    initial_measurement_id: int,
) -> VeeException:
    initial_row = session.get(InitialMeasurement, initial_measurement_id)
    assert initial_row is not None
    raw_row = initial_row.canonical_measurement.hes_read_raw
    assert raw_row is not None
    assert raw_row.hes_system_id is not None
    assert raw_row.meter_identifier is not None

    ingest_events(
        session,
        {
            "source_system": "HES",
            "batch_id": "tamper-high-estimation-batch",
            "received_at": "2026-04-18T09:07:00+09:00",
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

    initial_row.value = Decimal("1500.0000")
    initial_row.unit_of_measure = "kWh"
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
    assert vee_exception.exception_code == "vee_high_value_detected"
    return vee_exception


def _open_required_field_exception(session, *, initial_measurement_id: int) -> VeeException:
    initial_row = session.get(InitialMeasurement, initial_measurement_id)
    assert initial_row is not None
    initial_row.unit_of_measure = ""
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
    assert vee_exception.exception_code == "vee_required_field_missing"
    return vee_exception


def _open_missing_interval_exception(session, *, initial_measurement_id: int) -> VeeException:
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


def _prepare_single_slot_missing_interval_environment(
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
            "batch_id": "synthetic-missing-read-batch",
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
                "batch_id": "synthetic-missing-outage-batch",
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

    received_slot_bitmap = "00,15"
    received_slot_count = 2
    if not multi_missing_window:
        if include_missing_slot_measurement:
            received_slot_bitmap = "00,15,45"
            received_slot_count = 3
        else:
            received_slot_bitmap = "00,15,45"
            received_slot_count = 3

    session.add(
        RawIntervalWindowState(
            source_system=anchor_raw.source_system,
            meter_identifier=anchor_raw.meter_identifier,
            channel_identifier=anchor_raw.channel_identifier,
            window_start_at=anchor_raw.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=15,
            expected_slot_count=4,
            received_slot_count=received_slot_count,
            received_slot_bitmap=received_slot_bitmap,
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
        source_reference="test:synthetic-missing-tariff-assignment",
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

    anchor_exception = _open_missing_interval_exception(
        session,
        initial_measurement_id=anchor_initial.id,
    )
    return service_point_id, anchor_initial.id, anchor_exception.id


def test_apply_previous_value_estimation_supersedes_final_and_recalculates_downstream(session):
    service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session
    )
    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    old_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None
    assert old_charge is not None
    actor = create_user_account(
        session,
        login_id="estimation-actor",
        password="secret-password",
        display_name="Estimation Actor",
        role_code="operator",
    )

    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by=actor.login_id,
        estimated_by_user_account_id=actor.id,
        operator_memo="apply previous value",
    )
    session.commit()

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
    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)
    resolved_exception = session.get(VeeException, vee_exception.id)

    assert refreshed_initial is not None
    assert current_final is not None
    assert current_determinant is not None
    assert current_charge is not None
    assert audit_row is not None
    assert resolved_exception is not None
    assert summary.estimation_status == "applied"
    assert summary.result_code == "estimation_applied"
    assert summary.estimated_value == Decimal("10.0000")
    assert summary.final_superseded is True
    assert summary.daily_usage_groups_updated == 1
    assert summary.monthly_usage_groups_updated == 1
    assert summary.bill_determinant_superseded == 1
    assert summary.bill_charge_superseded == 1
    assert refreshed_initial.value == Decimal("10.0000")
    assert refreshed_initial.quality_code == ESTIMATION_QUALITY_CODE
    assert current_final.id != old_final.id
    assert current_final.value == Decimal("10.0000")
    assert current_final.revision_reason_code == ESTIMATION_REVISION_REASON_CODE
    assert current_determinant.determinant_value == Decimal("40.0000")
    assert current_determinant.revision_reason_code == ESTIMATION_REVISION_REASON_CODE
    assert current_charge.id != old_charge.id
    assert current_charge.quantity_value == Decimal("40.0000")
    assert current_charge.charge_amount == Decimal("4000.0000")
    assert current_charge.revision_reason_code == ESTIMATION_REVISION_REASON_CODE
    assert resolved_exception.exception_status == "resolved"
    assert resolved_exception.resolution_type == "estimated"
    assert resolved_exception.resolved_by == actor.login_id
    assert resolved_exception.resolved_by_user_account_id == actor.id
    assert audit_row.estimation_status == "applied"
    assert audit_row.estimated_by == actor.login_id
    assert audit_row.estimated_by_user_account_id == actor.id
    assert audit_row.source_previous_final_measurement_id is not None
    assert audit_row.result_final_measurement_id == current_final.id
    assert audit_row.superseded_final_measurement_id == old_final.id


def test_apply_linear_interpolation_estimation_recalculates_charge_chain(session):
    service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
        operator_memo="apply interpolation",
    )
    session.commit()

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

    assert current_final is not None
    assert current_determinant is not None
    assert current_charge is not None
    assert summary.estimation_status == "applied"
    assert summary.estimated_value == Decimal("15.0000")
    assert current_final.value == Decimal("15.0000")
    assert current_determinant.determinant_value == Decimal("45.0000")
    assert current_charge.quantity_value == Decimal("45.0000")
    assert current_charge.charge_amount == Decimal("4500.0000")


def test_apply_estimation_blocks_for_unsupported_exception_code(session):
    service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session,
        include_previous=False,
        include_next=False,
    )
    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None
    actor = create_user_account(
        session,
        login_id="estimation-blocked",
        password="secret-password",
        display_name="Estimation Blocked",
        role_code="operator",
    )

    vee_exception = _open_required_field_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by=actor.login_id,
        estimated_by_user_account_id=actor.id,
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert refreshed_initial is not None
    assert current_final is not None
    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_unsupported_exception_code"
    assert summary.final_created is False
    assert summary.final_superseded is False
    assert summary.bill_determinant_groups == 0
    assert summary.bill_charge_groups == 0
    assert refreshed_initial.value == Decimal("14.2000")
    assert current_final.id == old_final.id
    assert audit_row.estimation_status == "blocked"
    assert audit_row.estimated_by == actor.login_id
    assert audit_row.estimated_by_user_account_id == actor.id
    assert audit_row.result_final_measurement_id is None


def test_apply_estimation_blocks_when_tamper_policy_requires_manual_review(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_estimation_environment(
        session
    )
    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None

    vee_exception = _open_high_value_vee_exception_with_tamper(
        session,
        initial_measurement_id=target_initial_id,
    )

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
        operator_memo="try estimation despite tamper",
    )
    session.commit()

    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert current_final is not None
    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert (
        summary.result_code
        == "blocked_event_policy_tamper_correlated_value_anomaly"
    )
    assert current_final.id == old_final.id
    assert audit_row.estimation_status == "blocked"
    assert (
        audit_row.details["correction_policy_snapshot"]["policy_reason_code"]
        == "tamper_correlated_value_anomaly"
    )


def test_apply_estimation_blocks_when_target_unit_of_measure_is_missing(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_estimation_environment(
        session
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    target_initial = session.get(InitialMeasurement, target_initial_id)
    assert target_initial is not None
    target_initial.unit_of_measure = ""
    session.flush()

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_invalid_target_state"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "missing_unit_of_measure"


def test_apply_estimation_blocks_previous_value_when_previous_final_is_missing(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_estimation_environment(
        session,
        include_previous=False,
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_missing_previous_final"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "missing_previous_final"


def test_apply_estimation_blocks_previous_value_when_previous_final_uom_mismatches(session):
    _service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session
    )
    target_initial = session.get(InitialMeasurement, target_initial_id)
    assert target_initial is not None
    previous_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.measuring_component_id == measuring_component_id,
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.measured_at < target_initial.measured_at,
        )
        .order_by(FinalMeasurement.measured_at.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )
    assert previous_final is not None
    previous_final.unit_of_measure = "MWh"
    session.flush()

    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_uom_mismatch"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "uom_mismatch"
    assert audit_row.details["estimation_result"]["previous_unit_of_measure"] == "MWh"


def test_apply_estimation_policy_block_precedes_neighbor_missing_checks(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_estimation_environment(
        session,
        include_previous=False,
    )
    vee_exception = _open_high_value_vee_exception_with_tamper(
        session,
        initial_measurement_id=target_initial_id,
    )

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_event_policy_tamper_correlated_value_anomaly"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "event_policy_blocked"


def test_apply_linear_interpolation_blocks_when_next_final_is_missing(session):
    _service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(session)
    target_initial = session.get(InitialMeasurement, target_initial_id)
    assert target_initial is not None
    next_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.measuring_component_id == measuring_component_id,
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.measured_at > target_initial.measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(1)
    )
    assert next_final is not None
    next_final.is_current = False
    next_final.final_status = "superseded"
    session.flush()

    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_missing_next_final"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "missing_next_final"


def test_apply_linear_interpolation_blocks_when_neighbor_order_is_invalid(session, monkeypatch):
    _service_point_id, target_initial_id, measuring_component_id = _prepare_estimation_environment(
        session
    )
    target_initial = session.get(InitialMeasurement, target_initial_id)
    assert target_initial is not None
    previous_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.measuring_component_id == measuring_component_id,
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.measured_at < target_initial.measured_at,
        )
        .order_by(FinalMeasurement.measured_at.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )
    next_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.measuring_component_id == measuring_component_id,
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.measured_at > target_initial.measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(1)
    )
    assert previous_final is not None
    assert next_final is not None

    monkeypatch.setattr(
        estimation_service,
        "_find_supporting_previous_final",
        lambda _session, *, initial_row: next_final,
    )
    monkeypatch.setattr(
        estimation_service,
        "_find_supporting_next_final",
        lambda _session, *, initial_row: previous_final,
    )

    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    summary = apply_estimation_from_vee_exception(
        session,
        vee_exception.id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_context_mismatch"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "invalid_neighbor_order"


def test_apply_synthetic_missing_interval_linear_interpolation_creates_synthetic_chain(session):
    service_point_id, anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_initial = session.get(InitialMeasurement, anchor_initial_id)
    assert anchor_initial is not None
    measuring_component_id = anchor_initial.measuring_component_id
    old_determinant = session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == service_point_id)
        .where(BillDeterminant.measuring_component_id == measuring_component_id)
        .where(BillDeterminant.is_current.is_(True))
        .order_by(BillDeterminant.id.desc())
        .limit(1)
    )
    old_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .order_by(BillCharge.id.desc())
        .limit(1)
    )
    window_state = session.scalar(select(RawIntervalWindowState).limit(1))
    assert old_determinant is not None
    assert old_charge is not None
    assert window_state is not None
    actor = create_user_account(
        session,
        login_id="synthetic-estimation-actor",
        password="secret-password",
        display_name="Synthetic Estimation Actor",
        role_code="operator",
    )

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by=actor.login_id,
        estimated_by_user_account_id=actor.id,
        operator_memo="fill missing 00:30",
    )
    session.commit()

    synthetic_initial = session.get(InitialMeasurement, summary.initial_measurement_id)
    synthetic_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == summary.initial_measurement_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    current_determinant = session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == service_point_id)
        .where(BillDeterminant.measuring_component_id == measuring_component_id)
        .where(BillDeterminant.is_current.is_(True))
        .order_by(BillDeterminant.id.desc())
        .limit(1)
    )
    current_charge = session.scalar(
        select(BillCharge)
        .where(BillCharge.service_point_id == service_point_id)
        .where(BillCharge.measuring_component_id == measuring_component_id)
        .where(BillCharge.is_current.is_(True))
        .order_by(BillCharge.id.desc())
        .limit(1)
    )
    refreshed_window_state = session.get(RawIntervalWindowState, window_state.id)
    anchor_exception = session.get(VeeException, anchor_exception_id)
    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert synthetic_initial is not None
    assert synthetic_final is not None
    synthetic_raw = synthetic_initial.canonical_measurement.hes_read_raw
    assert synthetic_raw is not None
    assert current_determinant is not None
    assert current_charge is not None
    assert refreshed_window_state is not None
    assert anchor_exception is not None
    assert audit_row is not None
    assert summary.estimation_status == "applied"
    assert summary.estimated_value == Decimal("30.0000")
    assert summary.final_created is True
    assert synthetic_initial.value == Decimal("30.0000")
    assert synthetic_initial.quality_code == ESTIMATION_QUALITY_CODE
    assert synthetic_final.value == Decimal("30.0000")
    assert synthetic_raw.payload["origin"] == "synthetic_missing_interval_estimation"
    assert refreshed_window_state.completion_status == "complete"
    assert refreshed_window_state.received_slot_count == 4
    assert refreshed_window_state.received_slot_bitmap == "00,15,30,45"
    assert anchor_exception.exception_status == "resolved"
    assert anchor_exception.resolution_type == "estimated"
    assert anchor_exception.resolved_by == actor.login_id
    assert anchor_exception.resolved_by_user_account_id == actor.id
    assert summary.bill_determinant_groups == 1
    assert summary.bill_charge_groups == 1
    assert summary.daily_usage_groups_updated == 1
    assert len(summary.usage_recalculation_results) >= 1
    assert audit_row.estimation_mode == "synthetic_missing_interval"
    assert audit_row.estimated_by == actor.login_id
    assert audit_row.estimated_by_user_account_id == actor.id
    assert audit_row.anchor_vee_exception_id == anchor_exception_id
    assert audit_row.raw_interval_window_state_id == window_state.id
    assert audit_row.result_final_measurement_id == synthetic_final.id
    assert audit_row.details["window_context"]["missing_slot_code"] == "30"
    assert audit_row.details["synthetic_initial_measurement_snapshot"]["initial_measurement_id"] == synthetic_initial.id


def test_apply_synthetic_missing_interval_blocks_for_multi_slot_window(session):
    _service_point_id, anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(
            session,
            multi_missing_window=True,
        )
    )

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    anchor_initial = session.get(InitialMeasurement, anchor_initial_id)
    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)
    synthetic_row = session.scalar(
        select(HesReadRaw)
        .where(HesReadRaw.measured_at == datetime.fromisoformat("2026-04-19T00:30:00+09:00"))
        .limit(1)
    )

    assert anchor_initial is not None
    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_missing_interval_multi_slot_window"
    assert audit_row.estimation_status == "blocked"
    assert synthetic_row is None


def test_apply_synthetic_missing_interval_blocks_for_outage_correlated_window(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(
            session,
            with_outage=True,
        )
    )

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert (
        summary.result_code
        == "blocked_event_policy_outage_correlated_missing_interval"
    )
    assert audit_row.estimation_status == "blocked"
    assert (
        audit_row.details["correction_policy_snapshot"]["policy_reason_code"]
        == "outage_correlated_missing_interval"
    )


def test_apply_synthetic_missing_interval_blocks_when_measurement_already_exists(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(
            session,
            include_missing_slot_measurement=True,
        )
    )

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)

    assert audit_row is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_missing_interval_existing_measurement_present"
    assert audit_row.estimation_status == "blocked"


def test_get_synthetic_missing_interval_precheck_blocks_when_window_state_is_missing(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    window_state = session.scalar(select(RawIntervalWindowState).limit(1))

    assert anchor_exception is not None
    assert window_state is not None

    session.delete(window_state)
    session.flush()

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )

    assert precheck is not None
    assert precheck.available is False
    assert precheck.reason_code == "blocked_missing_interval_invalid_window_state"
    assert precheck.raw_interval_window_state_id is None


def test_get_synthetic_missing_interval_precheck_blocks_for_invalid_window_size(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    window_state = session.scalar(select(RawIntervalWindowState).limit(1))

    assert anchor_exception is not None
    assert window_state is not None

    window_state.window_size_minutes = 30
    session.flush()

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )

    assert precheck is not None
    assert precheck.available is False
    assert precheck.reason_code == "blocked_missing_interval_invalid_window_state"
    assert precheck.raw_interval_window_state_id is None


def test_get_synthetic_missing_interval_precheck_blocks_for_invalid_interval_size(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    window_state = session.scalar(select(RawIntervalWindowState).limit(1))

    assert anchor_exception is not None
    assert window_state is not None

    window_state.interval_size_minutes = 20
    session.flush()

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )

    assert precheck is not None
    assert precheck.available is False
    assert precheck.reason_code == "blocked_missing_interval_invalid_window_state"
    assert precheck.raw_interval_window_state_id == window_state.id


def test_get_synthetic_missing_interval_precheck_is_available_for_clean_single_slot_window(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)

    assert anchor_exception is not None

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )

    assert precheck is not None
    assert precheck.available is True
    assert precheck.reason_code is None
    assert precheck.missing_slot_code == "30"
    assert precheck.target_measured_at == datetime.fromisoformat("2026-04-19T00:30:00+09:00")
    assert precheck.window_start_at == datetime.fromisoformat("2026-04-19T00:00:00+09:00")
    assert precheck.window_size_minutes == 60
    assert precheck.interval_size_minutes == 15
    assert precheck.raw_interval_window_state_id is not None


def test_get_synthetic_missing_interval_precheck_blocks_when_measurement_already_exists(session):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(
            session,
            include_missing_slot_measurement=True,
        )
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)

    assert anchor_exception is not None

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )

    assert precheck is not None
    assert precheck.available is False
    assert precheck.reason_code == "blocked_missing_interval_existing_measurement_present"
    assert precheck.missing_slot_code == "30"


def test_apply_synthetic_previous_value_blocks_when_previous_final_is_missing_after_available_precheck(
    session,
):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    target_measured_at = datetime.fromisoformat("2026-04-19T00:30:00+09:00")

    assert anchor_exception is not None

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )
    assert precheck is not None
    assert precheck.available is True

    previous_finals = session.scalars(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.measured_at < target_measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
    ).all()
    assert previous_finals
    for row in previous_finals:
        row.is_current = False
        row.final_status = "superseded"
    session.flush()

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_PREVIOUS_VALUE_BASED,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)
    refreshed_exception = session.get(VeeException, anchor_exception_id)
    synthetic_row = session.scalar(
        select(HesReadRaw)
        .where(HesReadRaw.measured_at == target_measured_at)
        .where(HesReadRaw.source_slot_code == "30")
        .order_by(HesReadRaw.id.desc())
        .limit(1)
    )

    assert audit_row is not None
    assert refreshed_exception is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_missing_previous_final"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["window_context"]["missing_slot_code"] == "30"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "missing_previous_final"
    assert refreshed_exception.exception_status == "open"
    assert synthetic_row is None


def test_apply_synthetic_linear_interpolation_blocks_when_next_final_is_missing_after_available_precheck(
    session,
):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    target_measured_at = datetime.fromisoformat("2026-04-19T00:30:00+09:00")

    assert anchor_exception is not None

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )
    assert precheck is not None
    assert precheck.available is True

    next_finals = session.scalars(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.measured_at > target_measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
    ).all()
    assert next_finals
    for row in next_finals:
        row.is_current = False
        row.final_status = "superseded"
    session.flush()

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)
    refreshed_exception = session.get(VeeException, anchor_exception_id)
    synthetic_row = session.scalar(
        select(HesReadRaw)
        .where(HesReadRaw.measured_at == target_measured_at)
        .where(HesReadRaw.source_slot_code == "30")
        .order_by(HesReadRaw.id.desc())
        .limit(1)
    )

    assert audit_row is not None
    assert refreshed_exception is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_missing_next_final"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["window_context"]["missing_slot_code"] == "30"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "missing_next_final"
    assert refreshed_exception.exception_status == "open"
    assert synthetic_row is None


def test_apply_synthetic_linear_interpolation_blocks_for_neighbor_uom_mismatch_after_available_precheck(
    session,
):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    target_measured_at = datetime.fromisoformat("2026-04-19T00:30:00+09:00")

    assert anchor_exception is not None

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )
    assert precheck is not None
    assert precheck.available is True

    next_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.measured_at > target_measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(1)
    )
    assert next_final is not None
    next_final.unit_of_measure = "MWh"
    session.flush()

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)
    refreshed_exception = session.get(VeeException, anchor_exception_id)

    assert audit_row is not None
    assert refreshed_exception is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_uom_mismatch"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["window_context"]["missing_slot_code"] == "30"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "uom_mismatch"
    assert audit_row.details["estimation_result"]["next_unit_of_measure"] == "MWh"
    assert refreshed_exception.exception_status == "open"


def test_apply_synthetic_linear_interpolation_blocks_for_invalid_neighbor_order_after_available_precheck(
    session,
    monkeypatch,
):
    _service_point_id, _anchor_initial_id, anchor_exception_id = (
        _prepare_single_slot_missing_interval_environment(session)
    )
    anchor_exception = session.get(VeeException, anchor_exception_id)
    target_measured_at = datetime.fromisoformat("2026-04-19T00:30:00+09:00")

    assert anchor_exception is not None

    precheck = estimation_service.get_synthetic_missing_interval_estimation_precheck(
        session,
        vee_exception=anchor_exception,
    )
    assert precheck is not None
    assert precheck.available is True

    previous_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.measured_at < target_measured_at,
        )
        .order_by(FinalMeasurement.measured_at.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )
    next_final = session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.measured_at > target_measured_at,
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(1)
    )
    assert previous_final is not None
    assert next_final is not None

    monkeypatch.setattr(
        estimation_service,
        "_find_supporting_previous_final",
        lambda _session, *, initial_row: next_final,
    )
    monkeypatch.setattr(
        estimation_service,
        "_find_supporting_next_final",
        lambda _session, *, initial_row: previous_final,
    )

    summary = apply_synthetic_missing_interval_estimation_from_vee_exception(
        session,
        anchor_exception_id,
        strategy_code=ESTIMATION_STRATEGY_LINEAR_INTERPOLATION,
        estimated_by="operator_ui",
    )
    session.commit()

    audit_row = session.get(EstimationAudit, summary.estimation_audit_id)
    refreshed_exception = session.get(VeeException, anchor_exception_id)

    assert audit_row is not None
    assert refreshed_exception is not None
    assert summary.estimation_status == "blocked"
    assert summary.result_code == "blocked_context_mismatch"
    assert audit_row.estimation_status == "blocked"
    assert audit_row.details["window_context"]["missing_slot_code"] == "30"
    assert audit_row.details["estimation_result"]["blocked_reason"] == "invalid_neighbor_order"
    assert refreshed_exception.exception_status == "open"
