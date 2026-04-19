from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, aliased, joinedload, selectinload

from app.models import (
    Device,
    HesEventRaw,
    HesReadRaw,
    IngestBatch,
    IngestErrorLog,
    MeasuringComponent,
    ReprocessRequest,
)
from app.services.ingestion import create_or_get_canonical_measurement, find_measuring_component
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run


REPROCESSABLE_EXCEPTION_CODES = frozenset({"measuring_component_not_found"})


@dataclass(slots=True)
class ExceptionReprocessError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class ExceptionDetailContext:
    error_log: IngestErrorLog
    candidate_devices: list[Device]
    candidate_components: list[MeasuringComponent]
    exact_component_matches: list[MeasuringComponent]
    reprocess_requests: list[ReprocessRequest]
    can_reprocess: bool


@dataclass(frozen=True, slots=True)
class ExceptionQueueFilters:
    batch_id: str | None = None
    meter_id: str | None = None
    status: str | None = None
    exception_code: str | None = None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def build_exception_filters(args) -> ExceptionQueueFilters:
    return ExceptionQueueFilters(
        batch_id=_normalize_text(args.get("batch_id")),
        meter_id=_normalize_text(args.get("meter_id")),
        status=_normalize_text(args.get("status")),
        exception_code=_normalize_text(args.get("exception_code")),
    )


def get_exception_batch_id(error_log: IngestErrorLog) -> str | None:
    if error_log.hes_read_raw is not None and error_log.hes_read_raw.ingest_batch is not None:
        return error_log.hes_read_raw.ingest_batch.batch_id
    if error_log.hes_event_raw is not None and error_log.hes_event_raw.ingest_batch is not None:
        return error_log.hes_event_raw.ingest_batch.batch_id
    return None


def get_exception_meter_id(error_log: IngestErrorLog) -> str | None:
    if error_log.hes_read_raw is not None:
        return error_log.hes_read_raw.meter_identifier
    if error_log.hes_event_raw is not None:
        return error_log.hes_event_raw.meter_identifier
    return None


def list_exception_queue(
    session: Session, filters: ExceptionQueueFilters, *, limit: int = 100
) -> list[IngestErrorLog]:
    read_raw = aliased(HesReadRaw)
    event_raw = aliased(HesEventRaw)
    read_batch = aliased(IngestBatch)
    event_batch = aliased(IngestBatch)

    statement: Select[tuple[IngestErrorLog]] = (
        select(IngestErrorLog)
        .outerjoin(read_raw, IngestErrorLog.hes_read_raw)
        .outerjoin(read_batch, read_raw.ingest_batch)
        .outerjoin(event_raw, IngestErrorLog.hes_event_raw)
        .outerjoin(event_batch, event_raw.ingest_batch)
        .options(
            joinedload(IngestErrorLog.hes_read_raw).joinedload(HesReadRaw.ingest_batch),
            joinedload(IngestErrorLog.hes_event_raw).joinedload(HesEventRaw.ingest_batch),
        )
    )

    if filters.batch_id:
        statement = statement.where(
            or_(read_batch.batch_id == filters.batch_id, event_batch.batch_id == filters.batch_id)
        )
    if filters.meter_id:
        statement = statement.where(
            or_(
                read_raw.meter_identifier == filters.meter_id,
                event_raw.meter_identifier == filters.meter_id,
            )
        )
    if filters.status:
        statement = statement.where(IngestErrorLog.status == filters.status)
    if filters.exception_code:
        statement = statement.where(IngestErrorLog.exception_code == filters.exception_code)

    statement = statement.order_by(IngestErrorLog.id.desc()).limit(limit)
    return session.execute(statement).scalars().unique().all()


def get_exception_detail_context(
    session: Session, exception_id: int
) -> ExceptionDetailContext | None:
    error_log = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.id == exception_id)
        .options(
            joinedload(IngestErrorLog.hes_read_raw)
            .joinedload(HesReadRaw.ingest_batch),
            joinedload(IngestErrorLog.hes_read_raw)
            .joinedload(HesReadRaw.canonical_measurement),
            selectinload(IngestErrorLog.reprocess_requests),
        )
        .limit(1)
    )
    if error_log is None:
        return None

    raw_row = error_log.hes_read_raw
    if raw_row is None:
        return ExceptionDetailContext(
            error_log=error_log,
            candidate_devices=[],
            candidate_components=[],
            exact_component_matches=[],
            reprocess_requests=[],
            can_reprocess=False,
        )

    candidate_devices = session.scalars(
        select(Device)
        .options(joinedload(Device.service_point))
        .where(
            Device.source_system == raw_row.source_system,
            Device.external_meter_id == raw_row.meter_identifier,
        )
        .order_by(Device.id.asc())
    ).all()
    candidate_components = session.scalars(
        select(MeasuringComponent)
        .options(
            joinedload(MeasuringComponent.device),
            joinedload(MeasuringComponent.service_point),
        )
        .where(
            MeasuringComponent.source_system == raw_row.source_system,
            MeasuringComponent.external_channel_id == raw_row.channel_identifier,
        )
        .order_by(MeasuringComponent.id.asc())
    ).all()
    exact_component_matches = session.scalars(
        select(MeasuringComponent)
        .join(Device)
        .options(
            joinedload(MeasuringComponent.device),
            joinedload(MeasuringComponent.service_point),
        )
        .where(
            MeasuringComponent.source_system == raw_row.source_system,
            Device.external_meter_id == raw_row.meter_identifier,
            MeasuringComponent.external_channel_id == raw_row.channel_identifier,
            MeasuringComponent.status == "active",
        )
        .order_by(MeasuringComponent.id.asc())
    ).all()

    reprocess_requests = sorted(
        error_log.reprocess_requests,
        key=lambda row: (row.created_at or datetime.min.replace(tzinfo=timezone.utc), row.id),
        reverse=True,
    )

    return ExceptionDetailContext(
        error_log=error_log,
        candidate_devices=candidate_devices,
        candidate_components=candidate_components,
        exact_component_matches=exact_component_matches,
        reprocess_requests=reprocess_requests,
        can_reprocess=can_reprocess_exception(error_log),
    )


def can_reprocess_exception(error_log: IngestErrorLog) -> bool:
    return (
        error_log.exception_code in REPROCESSABLE_EXCEPTION_CODES
        and error_log.hes_read_raw is not None
        and error_log.status in {"open", "failed"}
    )


def reprocess_exception(
    session: Session,
    error_log: IngestErrorLog,
) -> ReprocessRequest:
    if error_log.exception_code not in REPROCESSABLE_EXCEPTION_CODES:
        raise ExceptionReprocessError(
            "unsupported_exception_code",
            "This exception type cannot be reprocessed yet.",
        )
    if error_log.hes_read_raw is None:
        raise ExceptionReprocessError(
            "missing_raw_record",
            "The exception does not have a linked raw read.",
        )
    if error_log.status == "processing":
        raise ExceptionReprocessError(
            "processing_in_progress",
            "A reprocess request is already in progress for this exception.",
        )

    raw_row = error_log.hes_read_raw
    request = ReprocessRequest(
        ingest_error_log_id=error_log.id,
        hes_read_raw_id=raw_row.id,
        status="processing",
        details={
            "exception_code": error_log.exception_code,
            "meter_identifier": raw_row.meter_identifier,
            "channel_identifier": raw_row.channel_identifier,
        },
    )
    session.add(request)
    session.flush()

    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="exception_reprocess",
        trigger_type="reprocess",
        reprocess_request=request,
        details={
            "exception_id": error_log.id,
            "exception_code": error_log.exception_code,
            "meter_identifier": raw_row.meter_identifier,
            "channel_identifier": raw_row.channel_identifier,
        },
    )

    error_log.status = "processing"

    if raw_row.canonical_measurement is not None:
        raw_row.canonical_status = "mapped"
        error_log.status = "resolved"
        request.status = "completed"
        request.result_code = "already_mapped"
        request.result_message = "The raw read already has a canonical measurement."
        request.completed_at = datetime.now(timezone.utc)
        request.details = {
            **request.details,
            "canonical_measurement_id": raw_row.canonical_measurement.id,
        }
        complete_pipeline_run(
            pipeline_run,
            result_code="already_mapped",
            details={
                **pipeline_run.details,
                "canonical_measurement_id": raw_row.canonical_measurement.id,
            },
        )
        return request

    component = find_measuring_component(session, raw_row)
    if component is None:
        error_log.status = "failed"
        raw_row.canonical_status = "exception"
        request.status = "failed"
        request.result_code = "measuring_component_not_found"
        request.result_message = "No active measuring component matched the raw read."
        request.completed_at = datetime.now(timezone.utc)
        fail_pipeline_run(
            pipeline_run,
            result_code="measuring_component_not_found",
            details={
                **pipeline_run.details,
                "status": "failed",
            },
        )
        return request

    canonical = create_or_get_canonical_measurement(session, raw_row, component)
    session.flush()

    error_log.status = "resolved"
    request.status = "completed"
    request.result_code = "canonical_created"
    request.result_message = "Canonical measurement created during reprocess."
    request.completed_at = datetime.now(timezone.utc)
    request.details = {
        **request.details,
        "canonical_measurement_id": canonical.id,
        "measuring_component_id": component.id,
    }
    complete_pipeline_run(
        pipeline_run,
        result_code="canonical_created",
        details={
            **pipeline_run.details,
            "canonical_measurement_id": canonical.id,
            "measuring_component_id": component.id,
        },
    )
    return request
