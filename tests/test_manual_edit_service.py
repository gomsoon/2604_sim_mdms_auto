from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

import app.services.manual_edits as manual_edit_service
from app.models import (
    BillCharge,
    BillDeterminant,
    FinalMeasurement,
    HesSystem,
    InitialMeasurement,
    ManualEditAudit,
    PipelineRun,
    RawIntervalWindowState,
    ServicePoint,
    VeeException,
)
from app.services.auth import create_user_account
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
    ManualEditActionError,
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


def _open_zero_value_vee_exception(session, *, initial_measurement_id: int) -> VeeException:
    initial_row = session.get(InitialMeasurement, initial_measurement_id)
    assert initial_row is not None
    initial_row.value = Decimal("0.0000")
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
    assert vee_exception.exception_code == "vee_zero_value_detected"
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


def _prepare_outage_correlated_missing_interval_environment(session) -> int:
    seed_demo_environment(session)
    hes_system_id = session.scalar(select(HesSystem.id).limit(1))
    assert hes_system_id is not None

    window_start = "2026-04-19T00:00:00+09:00"
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "manual-edit-missing-interval-read-batch",
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

    ingest_events(
        session,
        {
            "source_system": "HES",
            "batch_id": "manual-edit-missing-interval-outage-batch",
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
            received_slot_count=3,
            received_slot_bitmap="00,15,45",
            completion_status="partial",
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.commit()
    return anchor_initial.id


def _count_manual_edit_audits(session) -> int:
    return session.scalar(select(func.count()).select_from(ManualEditAudit)) or 0


def _count_manual_edit_pipeline_runs(session) -> int:
    return session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "manual_edit")
    ) or 0


def test_apply_manual_edit_requires_editing_actor(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    audit_count_before = _count_manual_edit_audits(session)
    pipeline_count_before = _count_manual_edit_pipeline_runs(session)

    with pytest.raises(ManualEditActionError) as exc_info:
        apply_manual_edit_from_vee_exception(
            session,
            vee_exception.id,
            edited_value=Decimal("12.5000"),
            reason_code="operator_meter_correction",
            edited_by="   ",
        )

    assert exc_info.value.error_code == "missing_edited_by"
    assert _count_manual_edit_audits(session) == audit_count_before
    assert _count_manual_edit_pipeline_runs(session) == pipeline_count_before


def test_apply_manual_edit_rejects_missing_exception(session):
    actor = create_user_account(
        session,
        login_id="manual-edit-missing-exception",
        password="secret-password",
        display_name="Manual Edit Missing Exception",
        role_code="operator",
    )
    audit_count_before = _count_manual_edit_audits(session)
    pipeline_count_before = _count_manual_edit_pipeline_runs(session)

    with pytest.raises(ManualEditActionError) as exc_info:
        apply_manual_edit_from_vee_exception(
            session,
            999999,
            edited_value=Decimal("12.5000"),
            reason_code="operator_meter_correction",
            edited_by=actor.login_id,
            edited_by_user_account_id=actor.id,
        )

    assert exc_info.value.error_code == "not_found"
    assert _count_manual_edit_audits(session) == audit_count_before
    assert _count_manual_edit_pipeline_runs(session) == pipeline_count_before


def test_apply_manual_edit_rejects_inactive_exception(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-inactive",
        password="secret-password",
        display_name="Manual Edit Inactive",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    vee_exception.exception_status = "resolved"
    vee_exception.resolution_type = "test_resolution"
    session.commit()

    audit_count_before = _count_manual_edit_audits(session)
    pipeline_count_before = _count_manual_edit_pipeline_runs(session)

    with pytest.raises(ManualEditActionError) as exc_info:
        apply_manual_edit_from_vee_exception(
            session,
            vee_exception.id,
            edited_value=Decimal("12.5000"),
            reason_code="operator_meter_correction",
            edited_by=actor.login_id,
            edited_by_user_account_id=actor.id,
        )

    assert exc_info.value.error_code == "exception_not_active"
    assert _count_manual_edit_audits(session) == audit_count_before
    assert _count_manual_edit_pipeline_runs(session) == pipeline_count_before


def test_apply_manual_edit_blocks_for_invalid_reason_code_and_records_actor_lineage(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-invalid-reason",
        password="secret-password",
        display_name="Manual Edit Invalid Reason",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        reason_code="unsupported_reason_code",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
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
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)

    assert refreshed_initial is not None
    assert current_final is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert summary.edit_status == "blocked"
    assert summary.result_code == "blocked_invalid_reason_code"
    assert summary.current_final_id == old_final.id
    assert refreshed_initial.value == Decimal("-1.0000")
    assert current_final.id == old_final.id
    assert audit_row.edit_status == "blocked"
    assert audit_row.reason_code == "unsupported_reason_code"
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.details["manual_edit_result"]["blocked_reason"] == "invalid_reason_code"
    assert pipeline_run.result_code == "manual_edit_blocked"
    assert pipeline_run.details["edited_by"] == actor.login_id
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["reason_code"] == "unsupported_reason_code"
    assert pipeline_run.details["result_code"] == "blocked_invalid_reason_code"


def test_apply_manual_edit_blocks_for_invalid_edited_value_and_records_actor_lineage(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-invalid-value",
        password="secret-password",
        display_name="Manual Edit Invalid Value",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value="not-a-number",
        reason_code="operator_data_entry_fix",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
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
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)

    assert refreshed_initial is not None
    assert current_final is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert summary.edit_status == "blocked"
    assert summary.result_code == "blocked_invalid_edited_value"
    assert refreshed_initial.value == Decimal("-1.0000")
    assert current_final.id == old_final.id
    assert audit_row.edited_value is None
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.details["manual_edit_result"]["blocked_reason"] == "invalid_edited_value"
    assert pipeline_run.result_code == "manual_edit_blocked"
    assert pipeline_run.details["edited_by"] == actor.login_id
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["edited_value"] is None
    assert pipeline_run.details["result_code"] == "blocked_invalid_edited_value"


def test_apply_manual_edit_policy_block_precedes_later_validation_checks(session):
    target_initial_id = _prepare_outage_correlated_missing_interval_environment(session)
    actor = create_user_account(
        session,
        login_id="manual-edit-policy-blocked",
        password="secret-password",
        display_name="Manual Edit Policy Blocked",
        role_code="operator",
    )
    vee_exception = _open_missing_interval_vee_exception(
        session,
        initial_measurement_id=target_initial_id,
    )

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value="not-a-number",
        reason_code="invalid_reason_code",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
    )
    session.commit()

    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)
    refreshed_exception = session.get(VeeException, vee_exception.id)

    assert audit_row is not None
    assert pipeline_run is not None
    assert refreshed_exception is not None
    assert summary.edit_status == "blocked"
    assert summary.result_code == "blocked_event_policy_outage_correlated_missing_interval"
    assert refreshed_exception.exception_status == "open"
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.details["manual_edit_result"]["blocked_reason"] == "event_policy_blocked"
    assert (
        audit_row.details["manual_edit_result"]["correction_policy_reason_code"]
        == "outage_correlated_missing_interval"
    )
    assert pipeline_run.result_code == "manual_edit_blocked"
    assert pipeline_run.details["edited_by"] == actor.login_id
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["result_code"] == (
        "blocked_event_policy_outage_correlated_missing_interval"
    )


@pytest.mark.parametrize(
    ("edited_quality_code", "edited_status_code", "expected_quality_code", "expected_status_code"),
    [
        ("MANUAL", None, "MANUAL", "ACTUAL"),
        (None, "OVERRIDDEN", "OK", "OVERRIDDEN"),
    ],
)
def test_apply_manual_edit_treats_quality_or_status_only_change_as_effective_change(
    session,
    *,
    edited_quality_code,
    edited_status_code,
    expected_quality_code,
    expected_status_code,
):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id=f"manual-edit-effective-{expected_quality_code}-{expected_status_code}",
        password="secret-password",
        display_name="Manual Edit Effective Change",
        role_code="operator",
    )
    vee_exception = _open_zero_value_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("0.0000"),
        edited_quality_code=edited_quality_code,
        edited_status_code=edited_status_code,
        reason_code="  operator_source_override  ",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)

    assert refreshed_initial is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert summary.edit_status == "applied"
    assert summary.result_code == "manual_edit_applied"
    assert summary.reason_code == "operator_source_override"
    assert refreshed_initial.value == Decimal("0.0000")
    assert refreshed_initial.quality_code == expected_quality_code
    assert refreshed_initial.status_code == expected_status_code
    assert audit_row.reason_code == "operator_source_override"
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert refreshed_initial.details["manual_edit"]["edited_by"] == actor.login_id
    assert refreshed_initial.details["manual_edit"]["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["reason_code"] == "operator_source_override"
    assert pipeline_run.details["edited_by"] == actor.login_id


def test_apply_manual_edit_blank_quality_and_status_fall_back_to_no_effective_change(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-blank-fallback",
        password="secret-password",
        display_name="Manual Edit Blank Fallback",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("-1.0000"),
        edited_quality_code="   ",
        edited_status_code="   ",
        reason_code="operator_data_entry_fix",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    refreshed_exception = session.get(VeeException, vee_exception.id)
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)

    assert refreshed_initial is not None
    assert refreshed_exception is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert summary.edit_status == "blocked"
    assert summary.result_code == "blocked_no_effective_change"
    assert refreshed_initial.quality_code == "OK"
    assert refreshed_initial.status_code == "ACTUAL"
    assert refreshed_exception.exception_status == "open"
    assert audit_row.details["manual_edit_result"]["blocked_reason"] == "no_effective_change"
    assert pipeline_run.details["result_code"] == "blocked_no_effective_change"


def test_apply_manual_edit_supersedes_final_and_recalculates_downstream(session):
    service_point_id, target_initial_id, measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-actor",
        password="secret-password",
        display_name="Manual Edit Actor",
        role_code="operator",
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
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
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
    assert summary.active_exception_count == 0
    assert summary.blocking_exception_count == 0
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
    assert resolved_exception.resolved_by == actor.login_id
    assert resolved_exception.resolved_by_user_account_id == actor.id
    assert resolved_exception.operator_memo == "correct the interval value"
    assert audit_row.edit_status == "applied"
    assert audit_row.operator_memo == "correct the interval value"
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert refreshed_initial.details["manual_edit"]["manual_edit_audit_id"] == audit_row.id
    assert refreshed_initial.details["manual_edit"]["reason_code"] == "operator_meter_correction"
    assert refreshed_initial.details["manual_edit"]["edited_by"] == actor.login_id
    assert refreshed_initial.details["manual_edit"]["edited_by_user_account_id"] == actor.id
    assert (
        audit_row.details["target_vee_exception_snapshot"]["vee_exception_id"] == vee_exception.id
    )
    assert audit_row.details["original_initial_measurement_snapshot"]["value"] == "-1.0000"
    assert audit_row.details["applied_initial_measurement_snapshot"]["value"] == "12.5000"
    assert audit_row.details["applied_initial_measurement_snapshot"]["quality_code"] == "MANUAL"
    assert (
        audit_row.details["applied_initial_measurement_snapshot"]["status_code"] == "OVERRIDDEN"
    )
    assert audit_row.details["vee_execution_log_id"] == summary.vee_execution_log_id
    assert audit_row.details["blocking_exception_count"] == 0
    assert audit_row.details["downstream_recalculation_summary"]["daily_usage_groups_updated"] == 1
    assert (
        audit_row.details["downstream_recalculation_summary"]["bill_determinant"]["superseded"]
        == 1
    )
    assert audit_row.details["downstream_recalculation_summary"]["bill_charge"]["superseded"] == 1
    assert audit_row.details["result_final_measurement_snapshot"]["final_measurement_id"] == current_final.id
    assert audit_row.result_final_measurement_id == current_final.id
    assert audit_row.superseded_final_measurement_id == old_final.id
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)
    assert pipeline_run is not None
    assert pipeline_run.result_code == "manual_edit_applied"
    assert pipeline_run.details["manual_edit_audit_id"] == audit_row.id
    assert pipeline_run.details["vee_execution_log_id"] == summary.vee_execution_log_id
    assert pipeline_run.details["active_exception_count"] == 0
    assert pipeline_run.details["blocking_exception_count"] == 0
    assert pipeline_run.details["edited_by"] == actor.login_id
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["operator_memo"] == "correct the interval value"
    assert pipeline_run.details["final_created"] is True
    assert pipeline_run.details["final_superseded"] is True


def test_apply_manual_edit_can_reopen_same_zero_value_exception_after_quality_only_change(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-zero-reopen",
        password="secret-password",
        display_name="Manual Edit Zero Reopen",
        role_code="operator",
    )
    vee_exception = _open_zero_value_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("0.0000"),
        edited_quality_code="MANUAL",
        reason_code="operator_source_override",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
        operator_memo="reclassify quality only",
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)
    original_exception = session.get(VeeException, vee_exception.id)
    same_code_exceptions = session.scalars(
        select(VeeException)
        .where(VeeException.initial_measurement_id == target_initial_id)
        .where(VeeException.exception_code == "vee_zero_value_detected")
        .order_by(VeeException.id.asc())
    ).all()
    active_same_code_exceptions = [
        row
        for row in same_code_exceptions
        if row.exception_status in {"open", "acknowledged"}
    ]

    assert refreshed_initial is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert original_exception is not None
    assert summary.edit_status == "applied"
    assert summary.result_code == "manual_edit_applied"
    assert summary.active_exception_count == 1
    assert summary.blocking_exception_count == 0
    assert refreshed_initial.value == Decimal("0.0000")
    assert refreshed_initial.quality_code == "MANUAL"
    assert refreshed_initial.details["manual_edit"]["manual_edit_audit_id"] == audit_row.id
    assert refreshed_initial.details["manual_edit"]["edited_by_user_account_id"] == actor.id
    assert original_exception.exception_status == "resolved"
    assert original_exception.resolution_type == "manually_corrected"
    assert original_exception.resolved_by == actor.login_id
    assert original_exception.resolved_by_user_account_id == actor.id
    assert original_exception.operator_memo == "reclassify quality only"
    assert len(same_code_exceptions) == 2
    assert len(active_same_code_exceptions) == 1
    assert active_same_code_exceptions[0].id != original_exception.id
    assert active_same_code_exceptions[0].exception_code == "vee_zero_value_detected"
    assert active_same_code_exceptions[0].blocking_finalization is False
    assert audit_row.operator_memo == "reclassify quality only"
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.details["active_exception_count"] == 1
    assert audit_row.details["blocking_exception_count"] == 0
    assert pipeline_run.result_code == "manual_edit_applied"
    assert pipeline_run.details["manual_edit_audit_id"] == audit_row.id
    assert pipeline_run.details["active_exception_count"] == 1
    assert pipeline_run.details["blocking_exception_count"] == 0
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["operator_memo"] == "reclassify quality only"


def test_apply_manual_edit_normalizes_blank_operator_memo_across_resolution_audit_and_pipeline(
    session,
):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-blank-memo",
        password="secret-password",
        display_name="Manual Edit Blank Memo",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        reason_code="operator_meter_correction",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
        operator_memo="   ",
    )
    session.commit()

    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)
    resolved_exception = session.get(VeeException, vee_exception.id)

    assert audit_row is not None
    assert pipeline_run is not None
    assert resolved_exception is not None
    assert summary.result_code == "manual_edit_applied"
    assert resolved_exception.operator_memo is None
    assert audit_row.operator_memo is None
    assert pipeline_run.details["operator_memo"] is None


def test_apply_manual_edit_can_leave_open_blocking_exceptions_after_edit_is_applied(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-open-blocker",
        password="secret-password",
        display_name="Manual Edit Open Blocker",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    target_initial = session.get(InitialMeasurement, target_initial_id)
    assert target_initial is not None
    old_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert old_final is not None
    target_initial.measuring_component.multiplier = Decimal("0")
    session.commit()

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        reason_code="operator_meter_correction",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
        operator_memo="apply value even though structural blocker remains",
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
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)
    resolved_target_exception = session.get(VeeException, vee_exception.id)
    active_exceptions = session.scalars(
        select(VeeException)
        .where(VeeException.initial_measurement_id == target_initial_id)
        .where(VeeException.exception_status.in_(("open", "acknowledged")))
        .order_by(VeeException.id.asc())
    ).all()

    assert refreshed_initial is not None
    assert current_final is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert resolved_target_exception is not None
    assert summary.edit_status == "applied"
    assert summary.result_code == "manual_edit_applied_with_open_exceptions"
    assert summary.blocking_exception_count > 0
    assert summary.current_final_id == old_final.id
    assert summary.final_created is False
    assert summary.final_superseded is False
    assert summary.daily_usage_groups_updated == 0
    assert summary.monthly_usage_groups_updated == 0
    assert summary.bill_determinant_groups == 0
    assert summary.bill_charge_groups == 0
    assert refreshed_initial.value == Decimal("12.5000")
    assert current_final.id == old_final.id
    assert resolved_target_exception.exception_status == "resolved"
    assert resolved_target_exception.resolved_by == actor.login_id
    assert resolved_target_exception.resolved_by_user_account_id == actor.id
    assert resolved_target_exception.operator_memo == (
        "apply value even though structural blocker remains"
    )
    assert {row.exception_code for row in active_exceptions} == {
        "vee_multiplier_invalid_detected"
    }
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.result_final_measurement_id is None
    assert audit_row.details["blocking_exception_count"] == summary.blocking_exception_count
    assert audit_row.details["result_final_measurement_snapshot"] is None
    assert (
        audit_row.details["downstream_recalculation_summary"]["daily_usage_groups_updated"] == 0
    )
    assert audit_row.details["downstream_recalculation_summary"]["bill_determinant"] is None
    assert audit_row.details["downstream_recalculation_summary"]["bill_charge"] is None
    assert pipeline_run.result_code == "manual_edit_applied_with_open_exceptions"
    assert pipeline_run.details["edited_by"] == actor.login_id
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["blocking_exception_count"] == summary.blocking_exception_count
    assert pipeline_run.details["final_created"] is False
    assert pipeline_run.details["final_superseded"] is False


def test_apply_manual_edit_can_finish_without_creating_new_final_when_current_final_is_reused(
    session,
    monkeypatch,
):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-no-final-change",
        password="secret-password",
        display_name="Manual Edit No Final Change",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)
    current_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.initial_measurement_id == target_initial_id)
        .where(FinalMeasurement.is_current.is_(True))
        .limit(1)
    )
    assert current_final is not None
    old_final_value = current_final.value
    old_final_quality_code = current_final.quality_code
    old_final_status_code = current_final.status_code

    monkeypatch.setattr(
        manual_edit_service,
        "create_or_get_final_measurement",
        lambda _session, _initial_row, revision_reason_code=None: (current_final, False),
    )

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("12.5000"),
        reason_code="operator_meter_correction",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
        operator_memo="apply manual edit without new final revision",
    )
    session.commit()

    refreshed_initial = session.get(InitialMeasurement, target_initial_id)
    refreshed_final = session.get(FinalMeasurement, current_final.id)
    audit_row = session.get(ManualEditAudit, summary.manual_edit_audit_id)
    pipeline_run = session.get(PipelineRun, summary.pipeline_run_id)
    resolved_exception = session.get(VeeException, vee_exception.id)

    assert refreshed_initial is not None
    assert refreshed_final is not None
    assert audit_row is not None
    assert pipeline_run is not None
    assert resolved_exception is not None
    assert summary.edit_status == "applied"
    assert summary.result_code == "manual_edit_applied_without_final_change"
    assert summary.final_created is False
    assert summary.final_superseded is False
    assert summary.blocking_exception_count == 0
    assert summary.current_final_id == refreshed_final.id
    assert summary.daily_usage_groups_updated == 0
    assert summary.monthly_usage_groups_updated == 0
    assert summary.bill_determinant_groups == 0
    assert summary.bill_charge_groups == 0
    assert refreshed_initial.value == Decimal("12.5000")
    assert refreshed_initial.details["manual_edit"]["edited_by"] == actor.login_id
    assert refreshed_initial.details["manual_edit"]["edited_by_user_account_id"] == actor.id
    assert refreshed_final.value == old_final_value
    assert refreshed_final.quality_code == old_final_quality_code
    assert refreshed_final.status_code == old_final_status_code
    assert resolved_exception.exception_status == "resolved"
    assert resolved_exception.resolved_by == actor.login_id
    assert resolved_exception.resolved_by_user_account_id == actor.id
    assert resolved_exception.operator_memo == "apply manual edit without new final revision"
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.result_final_measurement_id is None
    assert audit_row.superseded_final_measurement_id is None
    assert audit_row.details["blocking_exception_count"] == 0
    assert audit_row.details["result_final_measurement_snapshot"] is None
    assert (
        audit_row.details["downstream_recalculation_summary"]["daily_usage_groups_updated"] == 0
    )
    assert audit_row.details["downstream_recalculation_summary"]["bill_determinant"] is None
    assert audit_row.details["downstream_recalculation_summary"]["bill_charge"] is None
    assert pipeline_run.result_code == "manual_edit_applied_without_final_change"
    assert pipeline_run.details["edited_by"] == actor.login_id
    assert pipeline_run.details["edited_by_user_account_id"] == actor.id
    assert pipeline_run.details["blocking_exception_count"] == 0
    assert pipeline_run.details["final_created"] is False
    assert pipeline_run.details["final_superseded"] is False


def test_apply_manual_edit_blocks_for_unsupported_exception_code(session):
    service_point_id, target_initial_id, _ = _prepare_manual_edit_environment(
        session,
        include_previous=False,
        include_next=False,
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-blocked",
        password="secret-password",
        display_name="Manual Edit Blocked",
        role_code="operator",
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
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
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
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
    assert audit_row.result_final_measurement_id is None


def test_apply_manual_edit_blocks_when_no_effective_change(session):
    _, target_initial_id, _ = _prepare_manual_edit_environment(session)
    actor = create_user_account(
        session,
        login_id="manual-edit-nochange",
        password="secret-password",
        display_name="Manual Edit No Change",
        role_code="operator",
    )
    vee_exception = _open_negative_vee_exception(session, initial_measurement_id=target_initial_id)

    summary = apply_manual_edit_from_vee_exception(
        session,
        vee_exception.id,
        edited_value=Decimal("-1.0000"),
        reason_code="operator_data_entry_fix",
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
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
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id


def test_apply_manual_edit_records_tamper_correction_policy_snapshot(session):
    _service_point_id, target_initial_id, _measuring_component_id = _prepare_manual_edit_environment(
        session
    )
    actor = create_user_account(
        session,
        login_id="manual-edit-tamper",
        password="secret-password",
        display_name="Manual Edit Tamper",
        role_code="operator",
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
        edited_by=actor.login_id,
        edited_by_user_account_id=actor.id,
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
    assert audit_row.edited_by == actor.login_id
    assert audit_row.edited_by_user_account_id == actor.id
