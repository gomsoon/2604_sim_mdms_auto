from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.models import (
    BillDeterminant,
    Device,
    MeasuringComponent,
    PipelineRun,
    ProcessingWatermark,
    ServicePoint,
    UsageTransaction,
)
from app.services.bill_determinants import (
    BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
    calculate_bill_determinants,
)
from app.services.seeds import seed_master_data


def _prepare_bill_determinant_environment(session) -> tuple[int, int, int]:
    seed_master_data(session)
    session.commit()
    service_point_id = session.scalar(select(ServicePoint.id).limit(1))
    device_id = session.scalar(select(Device.id).limit(1))
    measuring_component_id = session.scalar(select(MeasuringComponent.id).limit(1))
    assert service_point_id is not None
    assert device_id is not None
    assert measuring_component_id is not None
    return service_point_id, device_id, measuring_component_id


def _create_usage_transaction(
    session,
    *,
    service_point_id: int,
    device_id: int,
    measuring_component_id: int,
    usage_value: Decimal,
    calculation_status: str,
    quality_summary: str,
    unit_of_measure: str = "kWh",
    period_start_at: datetime | None = None,
    period_end_at: datetime | None = None,
) -> UsageTransaction:
    now = datetime.now(timezone.utc)
    usage_pipeline_run = PipelineRun(
        pipeline_name="usage",
        trigger_type="manual",
        status="completed",
        started_at=now,
        completed_at=now,
        result_code="usage_completed",
        details={"usage_type": "monthly_consumption"},
    )
    session.add(usage_pipeline_run)
    session.flush()

    row = UsageTransaction(
        pipeline_run_id=usage_pipeline_run.id,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        device_id=device_id,
        usage_type="monthly_consumption",
        period_start_at=period_start_at or datetime(2026, 4, 1, tzinfo=timezone.utc),
        period_end_at=period_end_at or datetime(2026, 5, 1, tzinfo=timezone.utc),
        window_timezone_name="Asia/Seoul",
        interval_size_minutes=60,
        unit_of_measure=unit_of_measure,
        usage_value=usage_value,
        source_final_count=720,
        missing_interval_count=0,
        quality_summary=quality_summary,
        calculation_status=calculation_status,
        calculated_at=now,
        details={"provenance": {"trigger_type": "manual"}},
    )
    session.add(row)
    session.commit()
    return row


def test_calculate_bill_determinants_creates_complete_row(session):
    service_point_id, device_id, measuring_component_id = _prepare_bill_determinant_environment(
        session
    )
    _create_usage_transaction(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        usage_value=Decimal("100.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    summary = calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillDeterminant).limit(1))
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.pipeline_name == "bill_determinant")
        .order_by(PipelineRun.id.desc())
        .limit(1)
    )
    watermark = session.scalar(
        select(ProcessingWatermark)
        .where(ProcessingWatermark.pipeline_name == "bill_determinant")
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
    assert row.determinant_type == BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL
    assert row.determinant_value == Decimal("100.0000")
    assert row.calculation_status == "complete"
    assert row.quality_summary == "all_finalized"
    assert row.revision_number == 1
    assert row.is_current is True
    assert row.details["provenance"]["trigger_source"] == "bill_determinant_calculation"
    assert row.details["source_usage_type"] == "monthly_consumption"
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert pipeline_run.result_code == "bill_determinant_completed"
    assert watermark is not None
    assert watermark.record_type == "billing_cycle_total"


def test_calculate_bill_determinants_creates_blocked_row_from_blocked_usage(session):
    service_point_id, device_id, measuring_component_id = _prepare_bill_determinant_environment(
        session
    )
    _create_usage_transaction(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        usage_value=Decimal("0.0000"),
        calculation_status="blocked",
        quality_summary="blocked_mixed_interval",
    )

    summary = calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(BillDeterminant).limit(1))

    assert summary.created == 1
    assert summary.blocked == 1
    assert row is not None
    assert row.calculation_status == "blocked"
    assert row.quality_summary == "blocked_mixed_interval"
    assert row.determinant_value == Decimal("0.0000")


def test_calculate_bill_determinants_reuses_unchanged_current_row(session):
    service_point_id, device_id, measuring_component_id = _prepare_bill_determinant_environment(
        session
    )
    _create_usage_transaction(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        usage_value=Decimal("120.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    first_summary = calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    session.commit()
    second_summary = calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    session.commit()

    rows = session.scalars(
        select(BillDeterminant).order_by(BillDeterminant.id.asc())
    ).all()

    assert first_summary.created == 1
    assert second_summary.created == 0
    assert second_summary.reused == 1
    assert second_summary.superseded == 0
    assert len(rows) == 1
    assert rows[0].revision_number == 1
    assert rows[0].is_current is True


def test_calculate_bill_determinants_supersedes_changed_current_row(session):
    service_point_id, device_id, measuring_component_id = _prepare_bill_determinant_environment(
        session
    )
    usage_row = _create_usage_transaction(
        session,
        service_point_id=service_point_id,
        device_id=device_id,
        measuring_component_id=measuring_component_id,
        usage_value=Decimal("130.0000"),
        calculation_status="complete",
        quality_summary="all_finalized",
    )

    calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
    )
    session.commit()

    usage_row.usage_value = Decimal("150.0000")
    usage_row.calculated_at = datetime.now(timezone.utc)
    session.commit()

    summary = calculate_bill_determinants(
        session,
        determinant_type=BILL_DETERMINANT_TYPE_BILLING_CYCLE_CONSUMPTION_TOTAL,
        service_point_id=service_point_id,
        revision_reason_code="usage_recalculated",
    )
    session.commit()

    rows = session.scalars(
        select(BillDeterminant).order_by(BillDeterminant.id.asc())
    ).all()

    assert summary.created == 0
    assert summary.reused == 0
    assert summary.superseded == 1
    assert len(rows) == 2
    assert rows[0].is_current is False
    assert rows[1].is_current is True
    assert rows[1].revision_number == 2
    assert rows[1].revision_reason_code == "usage_recalculated"
    assert rows[1].supersedes_bill_determinant_id == rows[0].id
    assert rows[1].determinant_value == Decimal("150.0000")
