from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.models import (
    CanonicalMeasurement,
    FinalMeasurement,
    InitialMeasurement,
    PipelineRun,
    ProcessingWatermark,
    RawIntervalWindowState,
    VeeException,
)
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_demo_environment
from app.services.vee import evaluate_or_get_vee_baseline


def test_finalize_canonical_measurements_creates_final_measurement(session):
    seed_demo_environment(session)
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    final_row = session.scalar(select(FinalMeasurement).limit(1))
    pipeline_run = session.scalar(
        select(PipelineRun).where(PipelineRun.pipeline_name == "finalization").limit(1)
    )
    watermark = session.scalar(
        select(ProcessingWatermark)
        .where(ProcessingWatermark.pipeline_name == "finalization")
        .limit(1)
    )

    assert summary.candidates == 1
    assert summary.finalized == 1
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 0
    assert final_row is not None
    assert final_row.final_status == "finalized"
    assert final_row.initial_measurement_id is not None
    assert final_row.revision_number == 1
    assert final_row.revision_reason_code is None
    assert final_row.is_current is True
    assert final_row.supersedes_final_measurement_id is None
    assert pipeline_run is not None
    assert pipeline_run.status == "completed"
    assert pipeline_run.result_code == "finalization_completed"
    assert watermark is not None
    assert watermark.record_type == "final_measurement"


def test_finalize_canonical_measurements_is_idempotent_on_second_run(session):
    seed_demo_environment(session)
    session.commit()

    first_summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    second_summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert first_summary.finalized == 1
    assert second_summary.candidates == 1
    assert second_summary.finalized == 0
    assert second_summary.skipped_existing == 1
    assert second_summary.skipped_not_well_formed == 0
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 1


def test_finalize_canonical_measurements_creates_superseding_revision_when_snapshot_changes(session):
    seed_demo_environment(session)
    session.commit()

    first_summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    initial_row.value = Decimal("42.0000")
    session.commit()

    second_summary = finalize_canonical_measurements(
        session,
        batch_id="demo-read-batch",
        revision_reason_code="vee_re_evaluated",
    )
    session.commit()

    rows = session.scalars(select(FinalMeasurement).order_by(FinalMeasurement.id.asc())).all()
    refreshed_initial = session.scalar(select(InitialMeasurement).limit(1))

    assert first_summary.finalized == 1
    assert second_summary.finalized == 1
    assert len(rows) == 2
    assert rows[0].final_status == "superseded"
    assert rows[0].is_current is False
    assert rows[1].final_status == "finalized"
    assert rows[1].is_current is True
    assert rows[1].revision_number == 2
    assert rows[1].revision_reason_code == "vee_re_evaluated"
    assert rows[1].supersedes_final_measurement_id == rows[0].id
    assert refreshed_initial is not None
    assert refreshed_initial.final_measurement is not None
    assert refreshed_initial.final_measurement.id == rows[1].id


def test_finalize_canonical_measurements_skips_non_well_formed_rows(session):
    seed_demo_environment(session)
    session.commit()

    canonical_row = session.scalar(select(CanonicalMeasurement).limit(1))
    assert canonical_row is not None
    canonical_row.hes_read_raw.canonical_status = "exception"

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    pipeline_run = session.scalar(
        select(PipelineRun)
        .where(PipelineRun.pipeline_name == "finalization")
        .order_by(PipelineRun.id.desc())
        .limit(1)
    )

    assert summary.candidates == 1
    assert summary.finalized == 0
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 1
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0
    assert pipeline_run is not None
    assert pipeline_run.status == "failed"
    assert pipeline_run.result_code == "finalization_completed_with_skips"


def test_finalize_canonical_measurements_skips_rows_with_open_blocking_vee_exception(session):
    seed_demo_environment(session)
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    session.add(
        VeeException(
            initial_measurement_id=initial_row.id,
            exception_code="vee_required_field_missing",
            severity="error",
            exception_status="open",
            blocking_finalization=True,
            detected_at=datetime.now(timezone.utc),
            details={"field": "unit_of_measure"},
        )
    )
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 0
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 1
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0


def test_finalize_canonical_measurements_skips_rows_with_uom_mismatch_vee_exception(session):
    seed_demo_environment(session)
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    assert initial_row.measuring_component is not None
    initial_row.unit_of_measure = "MWh"
    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row)
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 0
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 1
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0


def test_finalize_canonical_measurements_skips_rows_with_multiplier_vee_exception(session):
    seed_demo_environment(session)
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    assert initial_row.measuring_component is not None
    initial_row.measuring_component.multiplier = Decimal("2.0")
    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row)
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 0
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 1
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0


def test_finalize_canonical_measurements_allows_non_blocking_vee_warning(session):
    seed_demo_environment(session)
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    session.add(
        VeeException(
            initial_measurement_id=initial_row.id,
            exception_code="vee_zero_value_detected",
            severity="warning",
            exception_status="open",
            blocking_finalization=False,
            detected_at=datetime.now(timezone.utc),
            details={"value": "0.0000"},
        )
    )
    initial_row.initial_status = "accepted"
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 1
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 0
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 1


def test_finalize_canonical_measurements_allows_high_value_vee_warning(session):
    seed_demo_environment(session)
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    initial_row.value = Decimal("1500.0000")
    initial_row.unit_of_measure = "kWh"
    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row)
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 1
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 0
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 1


def test_finalize_canonical_measurements_allows_low_value_vee_warning(session):
    seed_demo_environment(session)
    session.commit()

    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert initial_row is not None
    initial_row.value = Decimal("0.0001")
    initial_row.unit_of_measure = "kWh"
    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row)
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 1
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 0
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 1


def test_finalize_canonical_measurements_skips_rows_with_missing_interval_vee_exception(session):
    seed_demo_environment(session)
    session.commit()

    canonical_row = session.scalar(select(CanonicalMeasurement).limit(1))
    initial_row = session.scalar(select(InitialMeasurement).limit(1))
    assert canonical_row is not None
    assert initial_row is not None
    assert canonical_row.hes_read_raw is not None
    raw_row = canonical_row.hes_read_raw
    assert raw_row.source_system is not None
    assert raw_row.meter_identifier is not None
    assert raw_row.channel_identifier is not None
    raw_row.source_business_ts = raw_row.measured_at
    assert raw_row.source_business_ts is not None

    for row in list(initial_row.vee_exceptions):
        session.delete(row)
    for row in list(initial_row.vee_execution_logs):
        session.delete(row)
    initial_row.initial_status = "ready"
    session.flush()

    session.add(
        RawIntervalWindowState(
            source_system=raw_row.source_system,
            meter_identifier=raw_row.meter_identifier,
            channel_identifier=raw_row.channel_identifier,
            window_start_at=raw_row.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=raw_row.interval_size_minutes,
            expected_slot_count=4,
            received_slot_count=2,
            received_slot_bitmap="00,15",
            completion_status="partial",
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.flush()
    evaluate_or_get_vee_baseline(session, initial_row)
    session.commit()

    summary = finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    assert summary.candidates == 1
    assert summary.finalized == 0
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 1
    assert session.scalar(select(func.count()).select_from(FinalMeasurement)) == 0


def test_finalize_canonical_measurements_respects_exact_date_boundaries(session):
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

    canonical_rows = session.scalars(
        select(CanonicalMeasurement).order_by(CanonicalMeasurement.id.asc())
    ).all()
    first_row, second_row = canonical_rows

    summary = finalize_canonical_measurements(
        session,
        meter_id="MTR-1001",
        date_from=first_row.measured_at,
        date_to=first_row.measured_at,
    )
    session.commit()

    first_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.canonical_measurement_id == first_row.id)
        .limit(1)
    )
    second_final = session.scalar(
        select(FinalMeasurement)
        .where(FinalMeasurement.canonical_measurement_id == second_row.id)
        .limit(1)
    )

    assert summary.candidates == 1
    assert summary.finalized == 1
    assert summary.skipped_existing == 0
    assert summary.skipped_not_well_formed == 0
    assert first_final is not None
    assert second_final is None
