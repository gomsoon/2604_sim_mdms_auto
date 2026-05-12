from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BillingExportItem, BillingExportRequest, PipelineRun
from app.services.billing_export_requests import _update_request_details
from app.services.operational_events import record_operational_event
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run


@dataclass(frozen=True, slots=True)
class BillingExportProcessorSummary:
    claimed_requests: int
    completed_requests: int
    failed_requests: int
    processed_items: int
    succeeded_items: int
    failed_items: int
    skipped_items: int
    request_ids: tuple[int, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _record_request_event(
    session: Session,
    event_code: str,
    *,
    request: BillingExportRequest,
    pipeline_run: PipelineRun | None = None,
) -> None:
    record_operational_event(
        session,
        event_code,
        entity_type="billing_export_request",
        entity_id=request.id,
        pipeline_run=pipeline_run,
        details={
            "request_id": request.id,
            "request_scope": request.request_scope,
            "status": request.status,
            "service_point_id": request.service_point_id,
            "item_count": request.item_count,
            "processed_count": request.processed_count,
            "succeeded_count": request.succeeded_count,
            "failed_count": request.failed_count,
            "skipped_count": request.skipped_count,
            "claimed_by": request.claimed_by,
            "last_error": request.last_error,
        },
        request_id=request.id,
        request_scope=request.request_scope,
        item_count=request.item_count,
        processed_count=request.processed_count,
        succeeded_count=request.succeeded_count,
        failed_count=request.failed_count,
        skipped_count=request.skipped_count,
        last_error=request.last_error or "-",
    )


def _claim_next_queued_billing_export_request(
    session: Session,
    *,
    processed_by: str,
    request_id: int | None = None,
) -> BillingExportRequest | None:
    statement = (
        select(BillingExportRequest)
        .where(BillingExportRequest.status == "queued")
        .order_by(BillingExportRequest.id.asc())
        .with_for_update(skip_locked=True, of=BillingExportRequest)
        .limit(1)
    )
    if request_id is not None:
        statement = statement.where(BillingExportRequest.id == request_id)

    request = session.scalar(statement)
    if request is None:
        return None

    claimed_at = _utcnow()
    request.status = "processing"
    request.claimed_by = processed_by
    request.started_at = claimed_at
    request.completed_at = None
    request.last_error = None
    request.last_heartbeat_at = claimed_at
    _update_request_details(request)
    details = dict(request.details or {})
    details["claimed_at"] = claimed_at.isoformat()
    request.details = details
    session.flush()
    return request


def _start_billing_export_pipeline_run(
    session: Session,
    *,
    request: BillingExportRequest,
    processed_by: str,
) -> PipelineRun:
    return start_pipeline_run(
        session,
        pipeline_name="billing_export",
        trigger_type="async_export",
        billing_export_request=request,
        details={
            "request_id": request.id,
            "request_scope": request.request_scope,
            "item_count": request.item_count,
            "processed_by": processed_by,
            "target_system_code": request.target_system_code,
            "payload_format": request.payload_format,
        },
    )


def _touch_heartbeat(
    request: BillingExportRequest,
    *,
    current_item: BillingExportItem | None = None,
    last_processed_item_id: int | None = None,
    last_processed_result_code: str | None = None,
    last_processed_at: datetime | None = None,
) -> None:
    request.last_heartbeat_at = _utcnow()
    _update_request_details(
        request,
        current_item_id=current_item.id if current_item is not None else None,
        current_service_point_id=current_item.service_point_id if current_item is not None else None,
        current_billing_period_start_at=(
            current_item.billing_period_start_at if current_item is not None else None
        ),
        current_billing_period_end_at=(
            current_item.billing_period_end_at if current_item is not None else None
        ),
        last_processed_item_id=last_processed_item_id,
        last_processed_result_code=last_processed_result_code,
        last_processed_at=last_processed_at,
    )


def _mark_item_processing(
    session: Session,
    *,
    request_id: int,
    item_id: int,
) -> tuple[BillingExportRequest, BillingExportItem]:
    request = session.get(BillingExportRequest, request_id)
    item = session.get(BillingExportItem, item_id)
    assert request is not None
    assert item is not None

    item.status = "processing"
    item.result_code = None
    item.details = {
        **dict(item.details or {}),
        "processing_started_at": _utcnow().isoformat(),
    }
    _touch_heartbeat(request, current_item=item)
    session.flush()
    return request, item


def _process_pending_item(
    session: Session,
    *,
    request_id: int,
    item_id: int,
) -> str:
    request = session.get(BillingExportRequest, request_id)
    item = session.get(BillingExportItem, item_id)
    assert request is not None
    assert item is not None

    payload_snapshot = dict(item.payload_snapshot or {})
    payload_snapshot["worker_result"] = {
        "processed_at": _utcnow().isoformat(),
        "processed_by": request.claimed_by,
        "delivery_mode": "staged_only",
        "target_system_code": request.target_system_code,
        "payload_format": request.payload_format,
    }
    item.payload_snapshot = payload_snapshot
    return "payload_snapshot_staged"


def _apply_successful_item_result(
    session: Session,
    *,
    request_id: int,
    item_id: int,
    result_code: str,
) -> None:
    request = session.get(BillingExportRequest, request_id)
    item = session.get(BillingExportItem, item_id)
    assert request is not None
    assert item is not None

    completed_at = _utcnow()
    item.status = "completed"
    item.result_code = result_code
    item.exported_at = completed_at
    item.details = {
        **dict(item.details or {}),
        "processing_completed_at": completed_at.isoformat(),
    }

    request.processed_count += 1
    request.succeeded_count += 1
    request.last_heartbeat_at = completed_at
    _touch_heartbeat(
        request,
        last_processed_item_id=item.id,
        last_processed_result_code=item.result_code,
        last_processed_at=completed_at,
    )
    session.flush()


def _apply_failed_item_result(
    session: Session,
    *,
    request_id: int,
    item_id: int,
    error: Exception,
) -> None:
    request = session.get(BillingExportRequest, request_id)
    item = session.get(BillingExportItem, item_id)
    assert request is not None
    assert item is not None

    failed_at = _utcnow()
    item.status = "failed"
    item.result_code = "processing_error"
    item.last_error = str(error)
    item.details = {
        **dict(item.details or {}),
        "processing_failed_at": failed_at.isoformat(),
        "error_type": error.__class__.__name__,
        "error_summary": str(error),
    }

    request.processed_count += 1
    request.failed_count += 1
    request.last_error = str(error)
    request.last_heartbeat_at = failed_at
    _touch_heartbeat(
        request,
        last_processed_item_id=item.id,
        last_processed_result_code=item.result_code,
        last_processed_at=failed_at,
    )
    session.flush()


def _finalize_request(
    session: Session,
    *,
    request_id: int,
    pipeline_run_id: int,
) -> str:
    request = session.get(BillingExportRequest, request_id)
    pipeline_run = session.get(PipelineRun, pipeline_run_id)
    assert request is not None
    assert pipeline_run is not None

    completed_at = _utcnow()
    request.completed_at = completed_at
    request.last_heartbeat_at = completed_at
    request.status = "completed" if request.failed_count == 0 else "failed"
    _update_request_details(request)

    run_details = {
        **dict(pipeline_run.details or {}),
        "request_status": request.status,
        "processed_count": request.processed_count,
        "succeeded_count": request.succeeded_count,
        "failed_count": request.failed_count,
        "skipped_count": request.skipped_count,
        "claimed_by": request.claimed_by,
        "last_error": request.last_error,
    }
    if request.status == "completed":
        complete_pipeline_run(
            pipeline_run,
            result_code="billing_export_completed",
            details=run_details,
        )
        _record_request_event(
            session,
            "billing_export_completed",
            request=request,
            pipeline_run=pipeline_run,
        )
    else:
        fail_pipeline_run(
            pipeline_run,
            result_code="item_failures_detected",
            details=run_details,
        )
        _record_request_event(
            session,
            "billing_export_failed",
            request=request,
            pipeline_run=pipeline_run,
        )
    session.flush()
    return request.status


def process_queued_billing_export_requests(
    session: Session,
    *,
    limit: int = 1,
    request_id: int | None = None,
    processed_by: str = "billing_export_worker",
) -> BillingExportProcessorSummary:
    claimed_requests = 0
    completed_requests = 0
    failed_requests = 0
    processed_items = 0
    succeeded_items = 0
    failed_items = 0
    skipped_items = 0
    processed_request_ids: list[int] = []

    remaining = 1 if request_id is not None else max(limit, 0)
    while remaining > 0:
        request = _claim_next_queued_billing_export_request(
            session,
            processed_by=processed_by,
            request_id=request_id,
        )
        if request is None:
            break

        request_id_value = request.id
        claimed_requests += 1
        processed_request_ids.append(request_id_value)
        skipped_items += request.skipped_count
        session.commit()

        pipeline_run_id: int | None = None
        try:
            request = session.get(BillingExportRequest, request_id_value)
            assert request is not None
            pipeline_run = _start_billing_export_pipeline_run(
                session,
                request=request,
                processed_by=processed_by,
            )
            _record_request_event(
                session,
                "billing_export_started",
                request=request,
                pipeline_run=pipeline_run,
            )
            pipeline_run_id = pipeline_run.id
            session.commit()

            item_ids = session.scalars(
                select(BillingExportItem.id)
                .where(BillingExportItem.billing_export_request_id == request_id_value)
                .where(BillingExportItem.status == "pending")
                .order_by(BillingExportItem.id.asc())
            ).all()

            for item_id in item_ids:
                _mark_item_processing(
                    session,
                    request_id=request_id_value,
                    item_id=item_id,
                )
                session.commit()

                try:
                    result_code = _process_pending_item(
                        session,
                        request_id=request_id_value,
                        item_id=item_id,
                    )
                    _apply_successful_item_result(
                        session,
                        request_id=request_id_value,
                        item_id=item_id,
                        result_code=result_code,
                    )
                    session.commit()
                    processed_items += 1
                    succeeded_items += 1
                except Exception as exc:
                    session.rollback()
                    _apply_failed_item_result(
                        session,
                        request_id=request_id_value,
                        item_id=item_id,
                        error=exc,
                    )
                    session.commit()
                    processed_items += 1
                    failed_items += 1

            request_status = _finalize_request(
                session,
                request_id=request_id_value,
                pipeline_run_id=pipeline_run_id,
            )
            session.commit()
            if request_status == "completed":
                completed_requests += 1
            else:
                failed_requests += 1
        except Exception as exc:
            session.rollback()
            request = session.get(BillingExportRequest, request_id_value)
            assert request is not None
            request.status = "failed"
            request.completed_at = _utcnow()
            request.last_error = str(exc)
            request.last_heartbeat_at = request.completed_at
            _update_request_details(request)
            if pipeline_run_id is not None:
                pipeline_run = session.get(PipelineRun, pipeline_run_id)
                assert pipeline_run is not None
                fail_pipeline_run(
                    pipeline_run,
                    result_code="request_processing_error",
                    details={
                        **dict(pipeline_run.details or {}),
                        "request_status": "failed",
                        "last_error": str(exc),
                    },
                )
                _record_request_event(
                    session,
                    "billing_export_failed",
                    request=request,
                    pipeline_run=pipeline_run,
                )
            else:
                _record_request_event(
                    session,
                    "billing_export_failed",
                    request=request,
                )
            session.commit()
            failed_requests += 1

        remaining -= 1
        if request_id is not None:
            break

    return BillingExportProcessorSummary(
        claimed_requests=claimed_requests,
        completed_requests=completed_requests,
        failed_requests=failed_requests,
        processed_items=processed_items,
        succeeded_items=succeeded_items,
        failed_items=failed_items,
        skipped_items=skipped_items,
        request_ids=tuple(processed_request_ids),
    )
