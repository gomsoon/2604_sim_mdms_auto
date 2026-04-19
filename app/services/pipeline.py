from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IngestBatch, PipelineRun, ProcessingWatermark, ReprocessRequest


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def start_pipeline_run(
    session: Session,
    *,
    pipeline_name: str,
    trigger_type: str,
    ingest_batch: IngestBatch | None = None,
    reprocess_request: ReprocessRequest | None = None,
    details: dict[str, Any] | None = None,
) -> PipelineRun:
    run = PipelineRun(
        pipeline_name=pipeline_name,
        trigger_type=trigger_type,
        status="processing",
        ingest_batch=ingest_batch,
        reprocess_request=reprocess_request,
        started_at=datetime.now(timezone.utc),
        details=details or {},
    )
    session.add(run)
    session.flush()
    return run


def complete_pipeline_run(
    run: PipelineRun,
    *,
    result_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> PipelineRun:
    run.status = "completed"
    run.result_code = result_code
    run.completed_at = datetime.now(timezone.utc)
    if details is not None:
        run.details = details
    return run


def fail_pipeline_run(
    run: PipelineRun,
    *,
    result_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> PipelineRun:
    run.status = "failed"
    run.result_code = result_code
    run.completed_at = datetime.now(timezone.utc)
    if details is not None:
        run.details = details
    return run


def upsert_processing_watermark(
    session: Session,
    *,
    pipeline_name: str,
    source_system: str | None,
    record_type: str | None,
    last_processed_at: datetime,
    details: dict[str, Any] | None = None,
) -> ProcessingWatermark:
    normalized_last_processed_at = _normalize_utc(last_processed_at)
    watermark = session.scalar(
        select(ProcessingWatermark)
        .where(ProcessingWatermark.pipeline_name == pipeline_name)
        .where(ProcessingWatermark.source_system == source_system)
        .where(ProcessingWatermark.record_type == record_type)
        .limit(1)
    )

    if watermark is None:
        watermark = ProcessingWatermark(
            pipeline_name=pipeline_name,
            source_system=source_system,
            record_type=record_type,
            last_processed_at=normalized_last_processed_at,
            details=details or {},
        )
        session.add(watermark)
        session.flush()
        return watermark

    current_last_processed_at = _normalize_utc(watermark.last_processed_at)
    if normalized_last_processed_at >= current_last_processed_at:
        watermark.last_processed_at = normalized_last_processed_at
        watermark.details = details or watermark.details
        session.flush()

    return watermark
