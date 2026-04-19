from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Device, HesReadRaw, IngestErrorLog, MeasuringComponent, ReprocessRequest
from app.services.ingestion import create_or_get_canonical_measurement, find_measuring_component


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
        return request

    component = find_measuring_component(session, raw_row)
    if component is None:
        error_log.status = "failed"
        raw_row.canonical_status = "exception"
        request.status = "failed"
        request.result_code = "measuring_component_not_found"
        request.result_message = "No active measuring component matched the raw read."
        request.completed_at = datetime.now(timezone.utc)
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
    return request
