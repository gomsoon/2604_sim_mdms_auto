from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    BillCharge,
    BillDeterminant,
    FinalMeasurement,
    HesSystem,
    InitialMeasurement,
    ManualEditAudit,
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
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_events, ingest_reads
from app.services.manual_edits import (
    MANUAL_EDIT_REVISION_REASON_CODE,
    apply_manual_edit_from_vee_exception,
)
from app.services.seeds import seed_demo_environment
from app.services.tariff_assignments import create_tariff_assignment
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def _prepare_manual_edit_environment(
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
                "batch_id": "manual-edit-neighbor-read-batch",
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
            "batch_id": "tamper-high-manual-edit-batch",
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


def test_apply_manual_edit_supersedes_final_and_recalculates_downstream(session):
    service_point_id, target_initial_id, measuring_component_id = _prepare_manual_edit_environment(
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

    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        edited_quality_code="MANUAL",
        edited_status_code="OVERRIDDEN",
        reason_code="operator_meter_correction",
        edited_by="operator_ui",
        operator_memo="correct the interval value",
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
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    resolved_exception = session.get(VeeException, vee_exception.id)

    assert refreshed_initial is not None
    assert current_final is not None
    assert current_determinant is not None
    assert current_charge is not None
    assert audit_row is not None
    assert resolved_exception is not None
    assert summary.edit_status == "applied"
    assert summary.result_code == "manual_edit_applied"
    assert summary.edited_value == Decimal("12.5000")
    assert summary.final_superseded is True
    assert summary.daily_usage_groups_updated == 1
    assert summary.monthly_usage_groups_updated == 1
    assert summary.bill_determinant_superseded == 1
    assert summary.bill_charge_superseded == 1
    assert refreshed_initial.value == Decimal("12.5000")
    assert refreshed_initial.quality_code == "MANUAL"
    assert refreshed_initial.status_code == "OVERRIDDEN"
    assert current_final.id != old_final.id
    assert current_final.value == Decimal("12.5000")
    assert current_final.quality_code == "MANUAL"
    assert current_final.status_code == "OVERRIDDEN"
    assert current_final.revision_reason_code == MANUAL_EDIT_REVISION_REASON_CODE
    assert current_determinant.determinant_value == Decimal("42.5000")
    assert current_determinant.revision_reason_code == MANUAL_EDIT_REVISION_REASON_CODE
    assert current_charge.id != old_charge.id
    assert current_charge.quantity_value == Decimal("42.5000")
    assert current_charge.charge_amount == Decimal("4250.0000")
    assert current_charge.revision_reason_code == MANUAL_EDIT_REVISION_REASON_CODE
    assert resolved_exception.exception_status == "resolved"
    assert resolved_exception.resolution_type == "manually_corrected"
    assert audit_row.edit_status == "applied"
    assert audit_row.edited_by == "operator_ui"
    assert audit_row.result_final_measurement_id == current_final.id
    assert audit_row.superseded_final_measurement_id == old_final.id


def test_apply_manual_edit_blocks_for_unsupported_exception_code(session):
    service_point_id, target_initial_id, _ = _prepare_manual_edit_environment(
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

    vee_exception = _open_required_field_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("14.2000"),
        reason_code="operator_source_override",
        edited_by="operator_ui",
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)

    assert refreshed_initial is not None
    assert current_final is not None
    assert audit_row is not None
    assert summary.edit_status == "blocked"
    assert summary.result_code == "blocked_unsupported_exception_code"
    assert summary.final_created is False
    assert summary.final_superseded is False
    assert summary.bill_determinant_groups == 0
    assert summary.bill_charge_groups == 0
    assert refreshed_initial.value == Decimal("14.2000")
    assert current_final.id == old_final.id
    assert audit_row.edit_status == "blocked"
    assert audit_row.result_final_measurement_id is None


def test_apply_manual_edit_blocks_when_no_effective_change(session):
    _, target_initial_id, _ = _prepare_manual_edit_environment(session)
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("-1.0000"),
        reason_code="operator_data_entry_fix",
        edited_by="operator_ui",
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    refreshed_exception = session.get(VeeException, vee_exception.id)
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)

    assert refreshed_initial is not None
    assert refreshed_exception is not None
    assert audit_row is not None
    assert summary.edit_status == "blocked"
    assert summary.result_code == "blocked_no_effective_change"
    assert refreshed_initial.value == Decimal("-1.0000")
    assert refreshed_exception.exception_status == "open"
    assert audit_row.edit_status == "blocked"


def test_apply_manual_edit_records_tamper_correction_policy_snapshot(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    vee_exception = _open_high_value_vee_exception_with_tamper(
        session,
        initial_measurement_id=target_initial_id,
    )

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        reason_code="operator_meter_correction",
        edited_by="operator_ui",
        operator_memo="tamper review complete",
    )
    session.commit()

    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)

    assert audit_row is not None
    assert summary.edit_status == "applied"
    assert (
        audit_row.details["correction_policy_snapshot"]["policy_reason_code"]
        == "tamper_correlated_value_anomaly"
    )
    assert (
        audit_row.details["correction_policy_snapshot"]["recommended_action"]
        == "operator_investigation_then_manual_edit"
    )
