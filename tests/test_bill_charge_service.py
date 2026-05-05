from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    BillCharge,
    BillDeterminant,
    Device,
    MeasuringComponent,
    PipelineRun,
    ProcessingWatermark,
    ServicePoint,
    ServicePointBillingContext,
)
from app.services.bill_charges import (
    BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
    calculate_bill_charges,
)
from app.services.seeds import seed_master_data
from app.services.tariff_assignments import create_tariff_assignment


def _prepare_bill_charge_environment(session) -> tuple[int, int, int, ServicePointBillingContext]:
    seed_master_data(session)
    session.commit()
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    device_id = session.scalar(select(Device.id).limit(1))
    measuring_component_id = session.scalar(select(MeasuringComponent.id).limit(1))
    billing_context = session.scalar(
        select(ServicePointBillingContext)
        .where(ServicePointBillingContext.service_point_id == service_point_id)
        .where(ServicePointBillingContext.is_current.is_(True))
        .limit(1)
    )
    assert service_point_id is not None
    assert device_id is not None
    assert measuring_component_id is not None
    assert billing_context is not None
    return service_point_id, device_id, measuring_component_id, billing_context


def _ensure_tariff_assignment(session, *, service_point_id: int) -> None:
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
    session.commit()


def _create_current_bill_determinant(
    session,
    *,
    service_point_id: int,
    device_id: int,
    measuring_component_id: int,
    billing_context: ServicePointBillingContext,
    determinant_value: Decimal,
    calculation_status: str,
    quality_summary: str,
    period_start_at: datetime | None = None,
    period_end_at: datetime | None = None,
) -> BillDeterminant:
    now = datetime.now(timezone.utc)
    period_start = period_start_at or datetime(2026, 4, 1, tzinfo=timezone.utc)
    period_end = period_end_at or datetime(2026, 5, 1, tzinfo=timezone.utc)
    source_run = PipelineRun(
        pipeline_name="bill_determinant",
        trigger_type="manual",
        status="completed",
        started_at=now,
        completed_at=now,
        result_code="bill_determinant_completed",
        details={"determinant_type": "billing_cycle_consumption_total"},
    )
    session.add(source_run)
    session.flush()

    row = BillDeterminant(
        pipeline_run_id=source_run.id,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        device_id=device_id,
        determinant_type="billing_cycle_consumption_total",
        billing_period_start_at=period_start,
        billing_period_end_at=period_end,
        window_timezone_name=billing_context.timezone_name,
        tariff_plan_code=None,
        tou_bucket_code=None,
        demand_window_code=None,
        unit_of_measure="kWh",
        determinant_value=determinant_value,
        source_usage_count=1,
        quality_summary=quality_summary,
        calculation_status=calculation_status,
        revision_number=1,
        revision_reason_code=None,
        is_current=True,
        supersedes_bill_determinant_id=None,
        calculated_at=now,
        details={
            "billing_period_source": "billing_context_calendar_month",
            "billing_context_snapshot": {
                "billing_context_id": billing_context.id,
                "timezone_name": billing_context.timezone_name,
                "billing_cycle_mode": billing_context.billing_cycle_mode,
                "billing_cycle_anchor_day": billing_context.billing_cycle_anchor_day,
                "currency_code": billing_context.currency_code,
                "effective_from": billing_context.effective_from.isoformat(),
                "effective_to": (
                    billing_context.effective_to.isoformat()
                    if billing_context.effective_to is not None
                    else None
                ),
            },
            "provenance": {"trigger_source": "bill_determinant_calculation"},
        },
    )
    session.add(row)
    session.commit()
    return row


def test_calculate_bill_charges_creates_complete_row(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _ensure_tariff_assignment(session, service_point_id=service_point_id)
    determinant = _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("100.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("120.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillCharge).limit(1))
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.pipeline_name == "bill_charge")
        .order_by(PipelineRun.id.desc())
        .limit(1)
    )
    watermark = session.scalar(
        select(ProcessingWatermark)
        .where(ProcessingWatermark.pipeline_name == "bill_charge")
        .limit(1)
    )

    assert summary.groups == 1
    assert summary.created == 1
    assert summary.superseded == 0
    assert summary.reused == 0
    assert summary.complete == 1
    assert summary.partial == 0
    assert summary.blocked == 0
    assert row is not None
    assert row.bill_determinant_id == determinant.id
    assert row.charge_type == BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE
    assert row.quantity_value == Decimal("100.0000")
    assert row.unit_rate_value == Decimal("120.00000000")
    assert row.charge_amount == Decimal("12000.0000")
    assert row.calculation_status == "complete"
    assert row.quality_summary == "all_finalized"
    assert row.revision_number == 1
    assert row.is_current is True
    assert row.details["provenance"]["trigger_source"] == "bill_charge_calculation"
    assert row.details["tariff_assignment_snapshot"]["tariff_plan_code"] == "KR_BASIC"
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert pipeline_run.result_code == "bill_charge_completed"
    assert watermark is not None
    assert watermark.record_type == "flat_energy_charge"


def test_calculate_bill_charges_creates_partial_row_from_partial_determinant(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _ensure_tariff_assignment(session, service_point_id=service_point_id)
    _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("88.0000"),
        calculation_status="partial",
        quality_summary="missing_intervals",
    )

    summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillCharge).limit(1))

    assert summary.created == 1
    assert summary.partial == 1
    assert row is not None
    assert row.calculation_status == "partial"
    assert row.quality_summary == "missing_intervals"


def test_calculate_bill_charges_creates_blocked_row_from_blocked_determinant(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _ensure_tariff_assignment(session, service_point_id=service_point_id)
    _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("0.0000"),
        calculation_status="blocked",
        quality_summary="blocked_missing_billing_context",
    )

    summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillCharge).limit(1))

    assert summary.created == 1
    assert summary.blocked == 1
    assert row is not None
    assert row.calculation_status == "blocked"
    assert row.quality_summary == "blocked_source_determinant"
    assert row.charge_amount is None


def test_calculate_bill_charges_creates_blocked_row_without_tariff_assignment(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("42.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillCharge).limit(1))

    assert summary.created == 1
    assert summary.blocked == 1
    assert row is not None
    assert row.quality_summary == "blocked_missing_tariff_assignment"


def test_calculate_bill_charges_creates_blocked_row_without_rate(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _ensure_tariff_assignment(session, service_point_id=service_point_id)
    _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("42.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=None,
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillCharge).limit(1))

    assert summary.created == 1
    assert summary.blocked == 1
    assert row is not None
    assert row.quality_summary == "blocked_missing_tariff_rate"


def test_calculate_bill_charges_reuses_unchanged_current_row(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _ensure_tariff_assignment(session, service_point_id=service_point_id)
    _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("120.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    first_summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()
    second_summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    rows = session.scalars(select(BillCharge).order_by(BillCharge.id.asc())).all()

    assert first_summary.created == 1
    assert second_summary.created == 0
    assert second_summary.reused == 1
    assert second_summary.superseded == 0
    assert len(rows) == 1
    assert rows[0].revision_number == 1
    assert rows[0].is_current is True


def test_calculate_bill_charges_supersedes_when_source_determinant_changes(session):
    service_point_id, device_id, measuring_component_id, billing_context = (
        _prepare_bill_charge_environment(session)
    )
    _ensure_tariff_assignment(session, service_point_id=service_point_id)
    source_row = _create_current_bill_determinant(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        billing_context=billing_context,
        determinant_value=Decimal("130.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
    )
    session.commit()

    source_row.is_current = False
    source_row.revision_reason_code = "re_determined"
    replacement = BillDeterminant(
        pipeline_run_id=source_row.pipeline_run_id,
        service_point_id=source_row.service_point_id,
        measuring_component_id=source_row.measuring_component_id,
        device_id=source_row.device_id,
        determinant_type=source_row.determinant_type,
        billing_period_start_at=source_row.billing_period_start_at,
        billing_period_end_at=source_row.billing_period_end_at,
        window_timezone_name=source_row.window_timezone_name,
        tariff_plan_code=source_row.tariff_plan_code,
        tou_bucket_code=source_row.tou_bucket_code,
        demand_window_code=source_row.demand_window_code,
        unit_of_measure=source_row.unit_of_measure,
        determinant_value=Decimal("150.0000"),
        source_usage_count=source_row.source_usage_count,
        quality_summary=source_row.quality_summary,
        calculation_status=source_row.calculation_status,
        revision_number=source_row.revision_number + 1,
        revision_reason_code="usage_recalculated",
        is_current=True,
        supersedes_bill_determinant_id=source_row.id,
        calculated_at=datetime.now(timezone.utc),
        details=dict(source_row.details),
    )
    session.add(replacement)
    session.commit()

    summary = calculate_bill_charges(
        session,
        charge_type=BILL_CHARGE_TYPE_FLAT_ENERGY_CHARGE,
        unit_rate_value=Decimal("100.00000000"),
        service_point_id=service_point_id,
        revision_reason_code="re_charged_after_determinant_revision",
    )
    session.commit()

    rows = session.scalars(select(BillCharge).order_by(BillCharge.id.asc())).all()

    assert summary.created == 0
    assert summary.reused == 0
    assert summary.superseded == 1
    assert len(rows) == 2
    assert rows[0].is_current is False
    assert rows[1].is_current is True
    assert rows[1].revision_number == 2
    assert rows[1].bill_determinant_id == replacement.id
