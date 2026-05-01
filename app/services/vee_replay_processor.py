from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PipelineRun, VeeReplayRequest, VeeReplayRequestItem
from app.services.operational_events import record_operational_event
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run
from app.services.processing_replay import reevaluate_vee_exception_and_replay


@dataclass(frozen=True, slots=True)
class VeeReplayProcessorSummary:
    claimed_requests: int
    completed_requests: int
    failed_requests: int
    processed_items: int
    succeeded_items: int
    failed_items: int
    request_ids: tuple[int, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_progress_payload(request: VeeReplayRequest) -> dict[str, object]:
    remaining_count = max(request.target_initial_count - request.processed_count, 0)
    progress_percent = (
        round((request.processed_count / request.target_initial_count) * 100, 2)
        if request.target_initial_count > 0
        else 0.0
    )
    return {
        "remaining_count": remaining_count,
        "progress_percent": progress_percent,
        "processed_count": request.processed_count,
        "succeeded_count": request.succeeded_count,
        "failed_count": request.failed_count,
        "reopened_exception_count": request.reopened_exception_count,
        "cleared_exception_count": request.cleared_exception_count,
        "final_superseded_count": request.final_superseded_count,
        "usage_recalculated_count": request.usage_recalculated_count,
    }


def _update_request_details(
    request: VeeReplayRequest,
    *,
    current_item_id: int | None = None,
    current_initial_measurement_id: int | None = None,
    last_processed_item_id: int | None = None,
    last_processed_result_code: str | None = None,
    last_processed_at: datetime | None = None,
) -> None:
    details = dict(request.details or {})
    details.update(_build_progress_payload(request))
    details["current_item_id"] = current_item_id
    details["current_initial_measurement_id"] = current_initial_measurement_id
    if last_processed_item_id is not None:
        details["last_processed_item_id"] = last_processed_item_id
    if last_processed_result_code is not None:
        details["last_processed_result_code"] = last_processed_result_code
    if last_processed_at is not None:
        details["last_processed_at"] = last_processed_at.isoformat()
    request.details = details


def _claim_next_queued_vee_replay_request(
    session: Session,
    *,
    request_id: int | None = None,
) -> VeeReplayRequest | None:
    statement = (
        select(VeeReplayRequest)
        .where(VeeReplayRequest.status == "queued")
        .order_by(VeeReplayRequest.id.asc())
        .with_for_update(skip_locked=True, of=VeeReplayRequest)
        .limit(1)
    )
    if request_id is not None:
        statement = statement.where(VeeReplayRequest.id == request_id)

    request = session.scalar(statement)
    if request is None:
        return None

    claimed_at = _utcnow()
    request.status = "processing"
    request.started_at = claimed_at
    request.completed_at = None
    request.last_error = None
    _update_request_details(request)
    details = dict(request.details or {})
    details["claimed_at"] = claimed_at.isoformat()
    request.details = details
    session.flush()
    return request


def _start_replay_pipeline_run(
    session: Session,
    *,
    request: VeeReplayRequest,
    processed_by: str,
) -> PipelineRun:
    return start_pipeline_run(
        session,
        pipeline_name="vee_replay",
        trigger_type="async_replay",
        vee_replay_request=request,
        details={
            "request_id": request.id,
            "request_scope": request.request_scope,
            "target_initial_count": request.target_initial_count,
            "processed_by": processed_by,
        },
    )


def _record_request_event(
    session: Session,
    event_code: str,
    *,
    request: VeeReplayRequest,
    pipeline_run: PipelineRun | None = None,
) -> None:
    record_operational_event(
        session,
        event_code,
        entity_type="vee_replay_request",
        entity_id=request.id,
        hes_system=request.hes_system,
        ingest_batch=request.ingest_batch,
        pipeline_run=pipeline_run,
        details={
            "request_id": request.id,
            "request_scope": request.request_scope,
            "status": request.status,
            "target_initial_count": request.target_initial_count,
            "processed_count": request.processed_count,
            "succeeded_count": request.succeeded_count,
            "failed_count": request.failed_count,
            "reopened_exception_count": request.reopened_exception_count,
            "cleared_exception_count": request.cleared_exception_count,
            "final_superseded_count": request.final_superseded_count,
            "usage_recalculated_count": request.usage_recalculated_count,
            "last_error": request.last_error,
        },
        request_id=request.id,
        request_scope=request.request_scope,
        target_initial_count=request.target_initial_count,
        processed_count=request.processed_count,
        failed_count=request.failed_count,
        final_superseded_count=request.final_superseded_count,
        usage_recalculated_count=request.usage_recalculated_count,
        last_error=request.last_error or "-",
    )


def _derive_item_result_code(summary) -> str:
    if summary.exception_reopened:
        return "exception_reopened"
    if summary.final_superseded:
        return "final_superseded"
    if summary.final_created:
        return "final_created"
    if summary.exception_cleared:
        return "exception_cleared"
    return "replay_completed"


def _mark_item_processing(
    session: Session,
    *,
    request_id: int,
    item_id: int,
) -> tuple[VeeReplayRequest, VeeReplayRequestItem]:
    request = session.get(VeeReplayRequest, request_id)
    item = session.get(VeeReplayRequestItem, item_id)
    assert request is not None
    assert item is not None

    item.status = "processing"
    item.result_code = None
    item.details = {
        **dict(item.details or {}),
        "processing_started_at": _utcnow().isoformat(),
    }
    _update_request_details(
        request,
        current_item_id=item.id,
        current_initial_measurement_id=item.initial_measurement_id,
    )
    session.flush()
    return request, item


def _apply_successful_item_result(
    session: Session,
    *,
    request_id: int,
    item_id: int,
    summary,
) -> None:
    request = session.get(VeeReplayRequest, request_id)
    item = session.get(VeeReplayRequestItem, item_id)
    assert request is not None
    assert item is not None

    item_completed_at = _utcnow()
    item.status = "completed"
    item.result_code = _derive_item_result_code(summary)
    item.vee_execution_log_id = summary.vee_execution_log_id
    item.previous_final_measurement_id = summary.previous_final_id
    item.current_final_measurement_id = summary.current_final_id
    item.details = {
        **dict(item.details or {}),
        "processing_completed_at": item_completed_at.isoformat(),
        "replay_summary": asdict(summary),
    }

    request.processed_count += 1
    request.succeeded_count += 1
    request.reopened_exception_count += int(summary.exception_reopened)
    request.cleared_exception_count += int(summary.exception_cleared)
    request.final_superseded_count += int(summary.final_superseded)
    request.usage_recalculated_count += sum(
        1 for row in summary.usage_recalculation_results if row.action != "unchanged"
    )
    _update_request_details(
        request,
        current_item_id=None,
        current_initial_measurement_id=None,
        last_processed_item_id=item.id,
        last_processed_result_code=item.result_code,
        last_processed_at=item_completed_at,
    )
    session.flush()


def _apply_failed_item_result(
    session: Session,
    *,
    request_id: int,
    item_id: int,
    error: Exception,
) -> None:
    request = session.get(VeeReplayRequest, request_id)
    item = session.get(VeeReplayRequestItem, item_id)
    assert request is not None
    assert item is not None

    failed_at = _utcnow()
    item.status = "failed"
    item.result_code = "processing_error"
    item.details = {
        **dict(item.details or {}),
        "processing_failed_at": failed_at.isoformat(),
        "error_type": error.__class__.__name__,
        "error_summary": str(error),
    }

    request.processed_count += 1
    request.failed_count += 1
    request.last_error = str(error)
    _update_request_details(
        request,
        current_item_id=None,
        current_initial_measurement_id=None,
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
    request = session.get(VeeReplayRequest, request_id)
    pipeline_run = session.get(PipelineRun, pipeline_run_id)
    assert request is not None
    assert pipeline_run is not None

    completed_at = _utcnow()
    request.completed_at = completed_at
    request.status = "completed" if request.failed_count == 0 else "failed"
    _update_request_details(request)

    run_details = {
        **dict(pipeline_run.details or {}),
        "request_status": request.status,
        "processed_count": request.processed_count,
        "succeeded_count": request.succeeded_count,
        "failed_count": request.failed_count,
        "reopened_exception_count": request.reopened_exception_count,
        "cleared_exception_count": request.cleared_exception_count,
        "final_superseded_count": request.final_superseded_count,
        "usage_recalculated_count": request.usage_recalculated_count,
    }
    if request.status == "completed":
        complete_pipeline_run(
            pipeline_run,
            result_code="replay_completed",
            details=run_details,
        )
        _record_request_event(
            session,
            "vee_replay_completed",
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
            "vee_replay_failed",
            request=request,
            pipeline_run=pipeline_run,
        )
    session.flush()
    return request.status


def process_queued_vee_replay_requests(
    session: Session,
    *,
    limit: int = 1,
    request_id: int | None = None,
    processed_by: str = "vee_replay_worker",
) -> VeeReplayProcessorSummary:
    claimed_requests = 0
    completed_requests = 0
    failed_requests = 0
    processed_items = 0
    succeeded_items = 0
    failed_items = 0
    processed_request_ids: list[int] = []

    remaining = 1 if request_id is not None else max(limit, 0)
    while remaining > 0:
        request = _claim_next_queued_vee_replay_request(session, request_id=request_id)
        if request is None:
            break

        request_id_value = request.id
        claimed_requests += 1
        processed_request_ids.append(request_id_value)
        session.commit()

        pipeline_run_id: int | None = None
        try:
            request = session.get(VeeReplayRequest, request_id_value)
            assert request is not None
            pipeline_run = _start_replay_pipeline_run(
                session,
                request=request,
                processed_by=processed_by,
            )
            _record_request_event(
                session,
                "vee_replay_started",
                request=request,
                pipeline_run=pipeline_run,
            )
            pipeline_run_id = pipeline_run.id
            session.commit()

            item_ids = session.scalars(
                select(VeeReplayRequestItem.id)
                .where(VeeReplayRequestItem.vee_replay_request_id == request_id_value)
                .where(VeeReplayRequestItem.status == "pending")
                .order_by(VeeReplayRequestItem.id.asc())
            ).all()

            for item_id in item_ids:
                _mark_item_processing(
                    session,
                    request_id=request_id_value,
                    item_id=item_id,
                )
                session.commit()

                item = session.get(VeeReplayRequestItem, item_id)
                assert item is not None
                try:
                    summary = reevaluate_vee_exception_and_replay(
                        session,
                        item.representative_vee_exception_id,
                        reevaluated_by=processed_by,
                        operator_memo=session.get(
                            VeeReplayRequest, request_id_value
                        ).operator_memo,
                    )
                    _apply_successful_item_result(
                        session,
                        request_id=request_id_value,
                        item_id=item_id,
                        summary=summary,
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
            request = session.get(VeeReplayRequest, request_id_value)
            assert request is not None
            request.status = "failed"
            request.completed_at = _utcnow()
            request.last_error = str(exc)
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
                    "vee_replay_failed",
                    request=request,
                    pipeline_run=pipeline_run,
                )
            else:
                _record_request_event(
                    session,
                    "vee_replay_failed",
                    request=request,
                )
            session.commit()
            failed_requests += 1

        remaining -= 1
        if request_id is not None:
            break

    return VeeReplayProcessorSummary(
        claimed_requests=claimed_requests,
        completed_requests=completed_requests,
        failed_requests=failed_requests,
        processed_items=processed_items,
        succeeded_items=succeeded_items,
        failed_items=failed_items,
        request_ids=tuple(processed_request_ids),
    )
