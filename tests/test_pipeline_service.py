from __future__ import annotations

from sqlalchemy import select

from app.models import PipelineRun, ProcessingWatermark
from app.services.ingestion import ingest_events, ingest_reads
from app.services.seeds import seed_master_data


def test_ingest_reads_creates_pipeline_runs_and_watermarks(session):
    seed_master_data(session)
    session.commit()

    summary = ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "pipeline-read-batch",
            "received_at": "2026-04-19T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-19T00:15:00+09:00",
                    "value": 10.5,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    runs = session.scalars(select(PipelineRun).order_by(PipelineRun.id.asc())).all()
    watermarks = session.scalars(
        select(ProcessingWatermark).order_by(ProcessingWatermark.pipeline_name.asc())
    ).all()

    assert summary["canonical_created"] == 1
    assert [run.pipeline_name for run in runs] == ["raw_ingest", "canonical"]
    assert all(run.status == "completed" for run in runs)
    assert runs[0].details["batch_id"] == "pipeline-read-batch"
    assert runs[1].details["canonical_created"] == 1
    assert len(watermarks) == 2
    assert {row.pipeline_name for row in watermarks} == {"raw_ingest", "canonical"}
    assert {row.record_type for row in watermarks} == {"hes_read_raw"}


def test_ingest_events_creates_raw_ingest_pipeline_run_and_watermark(session):
    summary = ingest_events(
        session,
        {
            "source_system": "HES",
            "batch_id": "pipeline-event-batch",
            "received_at": "2026-04-19T09:05:00+09:00",
            "events": [
                {
                    "meter_id": "MTR-7001",
                    "event_time": "2026-04-19T00:00:00+09:00",
                    "event_code": "POWER_FAIL",
                    "severity": "high",
                }
            ],
        },
    )
    session.commit()

    runs = session.scalars(select(PipelineRun).order_by(PipelineRun.id.asc())).all()
    watermarks = session.scalars(select(ProcessingWatermark)).all()

    assert summary["raw_events_received"] == 1
    assert len(runs) == 1
    assert runs[0].pipeline_name == "raw_ingest"
    assert runs[0].status == "completed"
    assert runs[0].details["record_type"] == "hes_event_raw"
    assert len(watermarks) == 1
    assert watermarks[0].record_type == "hes_event_raw"


def test_ingest_reads_updates_existing_watermark_across_multiple_batches(session):
    seed_master_data(session)
    session.commit()

    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "pipeline-read-batch-1",
            "received_at": "2026-04-19T09:00:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-19T00:15:00+09:00",
                    "value": 10.5,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    ingest_reads(
        session,
        {
            "source_system": "HES",
            "batch_id": "pipeline-read-batch-2",
            "received_at": "2026-04-19T09:05:00+09:00",
            "reads": [
                {
                    "meter_id": "MTR-1001",
                    "channel_id": "CH-01",
                    "measured_at": "2026-04-19T00:30:00+09:00",
                    "value": 11.1,
                    "quality_code": "OK",
                    "status_code": "ACTUAL",
                    "unit": "kWh",
                }
            ],
        },
    )
    session.commit()

    watermarks = session.scalars(
        select(ProcessingWatermark)
        .where(ProcessingWatermark.source_system == "HES")
        .where(ProcessingWatermark.record_type == "hes_read_raw")
        .order_by(ProcessingWatermark.pipeline_name.asc())
    ).all()

    assert len(watermarks) == 2
    assert watermarks[0].details["batch_id"] == "pipeline-read-batch-2"
    assert watermarks[1].details["batch_id"] == "pipeline-read-batch-2"
