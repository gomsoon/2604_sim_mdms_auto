from __future__ import annotations

from sqlalchemy import func, select

from app.models import CanonicalMeasurement, FinalMeasurement, PipelineRun, ProcessingWatermark
from app.services.finalization import finalize_canonical_measurements
from app.services.ingestion import ingest_reads
from app.services.seeds import seed_demo_environment


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
