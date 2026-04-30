from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.models import (
    FinalMeasurement,
    PipelineRun,
    ProcessingWatermark,
    ServicePoint,
    UsageTransaction,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.hes_systems import ensure_hes_system
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_master_data
from app.services.usage import calculate_usage_transactions


def _prepare_usage_environment(session) -> tuple[int, int]:
    seed_master_data(session)
    hes_system = ensure_hes_system(
        session,
        hes_code="HES",
        display_name="Demo HES",
        source_family="hes",
        default_delivery_mode="poll",
        timezone_name="Asia/Seoul",
    )
    session.commit()
    return hes_system.id, session.scalar(select(ServicePoint.id).limit(1))


def _ingest_and_finalize_batch(
    session,
    *,
    hes_system_id: int,
    batch_id: str,
    received_at: str,
    reads: list[dict[str, object]],
) -> None:
    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": batch_id,
            "received_at": received_at,
            "reads": reads,
        },
        hes_system_id=hes_system_id,
    )
    session.commit()
    finalize_canonical_measurements(session, batch_id=batch_id)
    session.commit()


def _build_hourly_reads(
    *,
    local_date: str,
    start_value: Decimal = Decimal("1.0000"),
    interval_size_minutes: int = 60,
) -> list[dict[str, object]]:
    reads: list[dict[str, object]] = []
    value = start_value
    for hour in range(24):
        reads.append(
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": f"{local_date}T{hour:02d}:00:00+09:00",
                "value": float(value),
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": interval_size_minutes,
            }
        )
    return reads


def test_calculate_usage_transactions_creates_complete_daily_usage(session):
    hes_system_id, service_point_id = _prepare_usage_environment(session)
    _ingest_and_finalize_batch(
        session,
        hes_system_id=hes_system_id,
        batch_id="usage-daily-complete",
        received_at="2026-04-19T09:00:00+09:00",
        reads=_build_hourly_reads(local_date="2026-04-19"),
    )

    summary = calculate_usage_transactions(
        session,
        usage_type="daily_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(UsageTransaction).limit(1))
    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.pipeline_name == "usage")
        .order_by(PipelineRun.id.desc())
        .limit(1)
    )
    watermark = session.scalar(
        select(ProcessingWatermark)
        .where(ProcessingWatermark.pipeline_name == "usage")
        .limit(1)
    )

    assert summary.groups == 1
    assert summary.created == 1
    assert summary.updated == 0
    assert summary.complete == 1
    assert summary.partial == 0
    assert summary.blocked == 0
    assert row is not None
    assert row.usage_type == "daily_consumption"
    assert row.window_timezone_name == "Asia/Seoul"
    assert row.interval_size_minutes == 60
    assert row.unit_of_measure == "kWh"
    assert row.usage_value == Decimal("24.0000")
    assert row.source_final_count == 24
    assert row.missing_interval_count == 0
    assert row.quality_summary == "all_finalized"
    assert row.calculation_status == "complete"
    assert row.details["provenance"]["trigger_type"] == "manual"
    assert row.details["provenance"]["trigger_source"] == "usage_calculation"
    assert len(row.details["provenance"]["contributing_final_measurement_ids"]) == 24
    assert len(row.details["provenance"]["contributing_initial_measurement_ids"]) == 24
    assert len(row.details["provenance"]["contributing_canonical_measurement_ids"]) == 24
    assert "replay_context" not in row.details["provenance"]
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert pipeline_run.result_code == "usage_completed"
    assert watermark is not None
    assert watermark.record_type == "daily_consumption"


def test_calculate_usage_transactions_creates_partial_monthly_rows_across_month_boundary(session):
    hes_system_id, service_point_id = _prepare_usage_environment(session)
    _ingest_and_finalize_batch(
        session,
        hes_system_id=hes_system_id,
        batch_id="usage-monthly-boundary",
        received_at="2026-05-01T09:00:00+09:00",
        reads=[
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-30T23:00:00+09:00",
                "value": 1.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": 60,
            },
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-05-01T00:00:00+09:00",
                "value": 2.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": 60,
            },
        ],
    )

    summary = calculate_usage_transactions(
        session,
        usage_type="monthly_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    rows = session.scalars(
        select(UsageTransaction).order_by(UsageTransaction.period_start_at.asc())
    ).all()
    korea = ZoneInfo("Asia/Seoul")

    assert summary.groups == 2
    assert summary.created == 2
    assert summary.complete == 0
    assert summary.partial == 2
    assert summary.blocked == 0
    assert len(rows) == 2
    assert rows[0].period_start_at.astimezone(korea).strftime("%Y-%m-%d") == "2026-04-01"
    assert rows[1].period_start_at.astimezone(korea).strftime("%Y-%m-%d") == "2026-05-01"
    assert rows[0].calculation_status == "partial"
    assert rows[1].calculation_status == "partial"
    assert rows[0].quality_summary == "missing_intervals"
    assert rows[1].quality_summary == "missing_intervals"


def test_calculate_usage_transactions_blocks_mixed_interval_window(session):
    hes_system_id, service_point_id = _prepare_usage_environment(session)
    _ingest_and_finalize_batch(
        session,
        hes_system_id=hes_system_id,
        batch_id="usage-mixed-interval",
        received_at="2026-04-20T09:00:00+09:00",
        reads=[
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-20T00:00:00+09:00",
                "value": 1.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": 60,
            },
            {
                "meter_id": "MTR-1001",
                "channel_id": "CH-01",
                "measured_at": "2026-04-20T00:30:00+09:00",
                "value": 2.0,
                "quality_code": "OK",
                "status_code": "ACTUAL",
                "unit": "kWh",
                "interval_size_minutes": 30,
            },
        ],
    )

    summary = calculate_usage_transactions(
        session,
        usage_type="daily_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(UsageTransaction).limit(1))

    assert summary.groups == 1
    assert summary.complete == 0
    assert summary.partial == 0
    assert summary.blocked == 1
    assert row is not None
    assert row.calculation_status == "blocked"
    assert row.quality_summary == "blocked_mixed_interval"
    assert row.usage_value == Decimal("0.0000")


def test_calculate_usage_transactions_updates_existing_scope_on_recalculation(session):
    hes_system_id, service_point_id = _prepare_usage_environment(session)
    _ingest_and_finalize_batch(
        session,
        hes_system_id=hes_system_id,
        batch_id="usage-recalc",
        received_at="2026-04-21T09:00:00+09:00",
        reads=_build_hourly_reads(local_date="2026-04-21"),
    )

    first_summary = calculate_usage_transactions(
        session,
        usage_type="daily_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    final_row = session.scalar(
        select(FinalMeasurement).order_by(FinalMeasurement.id.asc()).limit(1)
    )
    assert final_row is not None
    final_row.value = Decimal("2.0000")
    session.commit()

    second_summary = calculate_usage_transactions(
        session,
        usage_type="daily_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    rows = session.scalars(select(UsageTransaction)).all()

    assert first_summary.created == 1
    assert second_summary.created == 0
    assert second_summary.updated == 1
    assert len(rows) == 1
    assert rows[0].usage_value == Decimal("25.0000")


def test_calculate_usage_transactions_ignores_non_current_final_rows(session):
    hes_system_id, service_point_id = _prepare_usage_environment(session)
    _ingest_and_finalize_batch(
        session,
        hes_system_id=hes_system_id,
        batch_id="usage-ignore-non-current",
        received_at="2026-04-22T09:00:00+09:00",
        reads=_build_hourly_reads(local_date="2026-04-22"),
    )

    final_rows = session.scalars(select(FinalMeasurement)).all()
    assert final_rows
    for final_row in final_rows:
        final_row.is_current = False
    session.commit()

    summary = calculate_usage_transactions(
        session,
        usage_type="daily_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    rows = session.scalars(select(UsageTransaction)).all()

    assert summary.groups == 0
    assert summary.created == 0
    assert summary.updated == 0
    assert rows == []


def test_calculate_usage_transactions_uses_only_current_final_revision(session):
    hes_system_id, service_point_id = _prepare_usage_environment(session)
    _ingest_and_finalize_batch(
        session,
        hes_system_id=hes_system_id,
        batch_id="usage-current-final-only",
        received_at="2026-04-23T09:00:00+09:00",
        reads=_build_hourly_reads(local_date="2026-04-23"),
    )

    final_rows = session.scalars(select(FinalMeasurement).order_by(FinalMeasurement.id.asc())).all()
    assert final_rows
    superseded_row = final_rows[0]
    superseded_row.is_current = False
    superseded_row.final_status = "superseded"
    session.flush()

    replacement = FinalMeasurement(
        initial_measurement_id=superseded_row.initial_measurement_id,
        canonical_measurement_id=superseded_row.canonical_measurement_id,
        measuring_component_id=superseded_row.measuring_component_id,
        device_id=superseded_row.device_id,
        service_point_id=superseded_row.service_point_id,
        measured_at=superseded_row.measured_at,
        value=Decimal("5.0000"),
        quality_code=superseded_row.quality_code,
        status_code=superseded_row.status_code,
        unit_of_measure=superseded_row.unit_of_measure,
        final_status="finalized",
        finalized_at=superseded_row.finalized_at,
        revision_number=2,
        revision_reason_code="vee_re_evaluated",
        is_current=True,
        supersedes_final_measurement_id=superseded_row.id,
    )
    session.add(replacement)
    session.commit()

    summary = calculate_usage_transactions(
        session,
        usage_type="daily_consumption",
        service_point_id=service_point_id,
    )
    session.commit()

    row = session.scalar(select(UsageTransaction).limit(1))

    assert summary.groups == 1
    assert row is not None
    assert row.usage_value == Decimal("28.0000")
