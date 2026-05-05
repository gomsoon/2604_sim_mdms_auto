from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session

from app.models import (
    IngestBatch,
    PipelineRun,
    ProcessingWatermark,
    ReprocessRequest,
    VeeReplayRequest,
)
from app.services.operational_events import close_operational_alerts, record_operational_event


PIPELINE_SUCCESS_EVENT_CODES = {
    "raw_ingest": "raw_ingest_completed",
    "canonical": "canonical_completed",
    "finalization": "finalization_completed",
    "usage": "usage_completed",
    "bill_determinant": "bill_determinant_completed",
    "bill_charge": "bill_charge_completed",
    "exception_reprocess": "exception_reprocess_completed",
}

PIPELINE_FAILURE_EVENT_CODES = {
    "raw_ingest": "raw_ingest_failed",
    "canonical": "canonical_failed",
    "finalization": "finalization_failed",
    "usage": "usage_failed",
    "bill_determinant": "bill_determinant_failed",
    "bill_charge": "bill_charge_failed",
    "exception_reprocess": "exception_reprocess_failed",
}


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
    vee_replay_request: VeeReplayRequest | None = None,
    details: dict[str, Any] | None = None,
) -> PipelineRun:
    run = PipelineRun(
        pipeline_name=pipeline_name,
        trigger_type=trigger_type,
        status="processing",
        ingest_batch=ingest_batch,
        reprocess_request=reprocess_request,
        vee_replay_request=vee_replay_request,
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
    session = object_session(run)
    event_code = PIPELINE_SUCCESS_EVENT_CODES.get(run.pipeline_name)
    if session is not None and event_code is not None:
        batch_reference = (
            run.ingest_batch.batch_id
            if run.ingest_batch is not None
            else (run.details or {}).get("batch_id")
        )
        record_operational_event(
            session,
            event_code,
            occurred_at=run.completed_at,
            pipeline_run=run,
            ingest_batch=run.ingest_batch,
            reprocess_request=run.reprocess_request,
            meter_identifier=(run.details or {}).get("meter_identifier"),
            details={
                "pipeline_name": run.pipeline_name,
                "trigger_type": run.trigger_type,
                "result_code": result_code,
                **(run.details or {}),
            },
            batch_id=batch_reference,
        )
        failure_event_code = PIPELINE_FAILURE_EVENT_CODES.get(run.pipeline_name)
        if failure_event_code is not None and (
            run.ingest_batch_id is not None or run.reprocess_request_id is not None
        ):
            close_operational_alerts(
                session,
                event_code=failure_event_code,
                ingest_batch_id=run.ingest_batch_id,
                reprocess_request_id=run.reprocess_request_id,
            )
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
    session = object_session(run)
    event_code = PIPELINE_FAILURE_EVENT_CODES.get(run.pipeline_name)
    if session is not None and event_code is not None:
        batch_reference = (
            run.ingest_batch.batch_id
            if run.ingest_batch is not None
            else (run.details or {}).get("batch_id")
        )
        record_operational_event(
            session,
            event_code,
            occurred_at=run.completed_at,
            pipeline_run=run,
            ingest_batch=run.ingest_batch,
            reprocess_request=run.reprocess_request,
            batch_id=batch_reference,
            meter_identifier=(run.details or {}).get("meter_identifier"),
            details={
                "pipeline_name": run.pipeline_name,
                "trigger_type": run.trigger_type,
                "result_code": result_code,
                **(run.details or {}),
            },
        )
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
