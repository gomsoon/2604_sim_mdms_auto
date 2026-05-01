from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CanonicalMeasurement,
    HesReadRaw,
    InitialMeasurement,
    VeeException,
    VeeReplayRequest,
    VeeReplayRequestItem,
)
from app.services.operational_events import record_operational_event

ACTIVE_VEE_EXCEPTION_STATUSES = ("open", "acknowledged")
ACTIVE_VEE_REPLAY_REQUEST_STATUSES = ("queued", "processing")
SUPPORTED_VEE_REPLAY_REQUEST_SCOPES = {"hes_system", "ingest_batch", "date_range"}


@dataclass(frozen=True, slots=True)
class VeeReplayRequestError(Exception):
    error_code: str
    fallback_message: str


@dataclass(frozen=True, slots=True)
class VeeReplayRequestCreationResult:
    request: VeeReplayRequest
    created_item_count: int


def _validate_scope(
    *,
    request_scope: str,
    hes_system_id: int | None,
    ingest_batch_id: int | None,
    measured_at_from: datetime | None,
    measured_at_to: datetime | None,
) -> None:
    if request_scope not in SUPPORTED_VEE_REPLAY_REQUEST_SCOPES:
        raise VeeReplayRequestError(
            "unsupported_scope",
            "Replay request scope is not supported.",
        )

    if request_scope == "hes_system":
        if hes_system_id is None:
            raise VeeReplayRequestError(
                "missing_hes_system_id",
                "HES replay requests require a hes_system_id.",
            )
        return

    if request_scope == "ingest_batch":
        if ingest_batch_id is None:
            raise VeeReplayRequestError(
                "missing_ingest_batch_id",
                "Batch replay requests require an ingest_batch_id.",
            )
        return

    if measured_at_from is None or measured_at_to is None or measured_at_from >= measured_at_to:
        raise VeeReplayRequestError(
            "invalid_date_range",
            "Date-range replay requests require a valid measured_at_from and measured_at_to window.",
        )


def _find_existing_active_request(
    session: Session,
    *,
    request_scope: str,
    hes_system_id: int | None,
    ingest_batch_id: int | None,
    measured_at_from: datetime | None,
    measured_at_to: datetime | None,
    window_timezone_name: str | None,
) -> VeeReplayRequest | None:
    statement = (
        select(VeeReplayRequest)
        .where(VeeReplayRequest.request_scope == request_scope)
        .where(VeeReplayRequest.status.in_(ACTIVE_VEE_REPLAY_REQUEST_STATUSES))
    )
    if request_scope == "hes_system":
        statement = statement.where(VeeReplayRequest.hes_system_id == hes_system_id)
    elif request_scope == "ingest_batch":
        statement = statement.where(VeeReplayRequest.ingest_batch_id == ingest_batch_id)
    else:
        statement = statement.where(VeeReplayRequest.measured_at_from == measured_at_from).where(
            VeeReplayRequest.measured_at_to == measured_at_to
        )
        if window_timezone_name is None:
            statement = statement.where(VeeReplayRequest.window_timezone_name.is_(None))
        else:
            statement = statement.where(VeeReplayRequest.window_timezone_name == window_timezone_name)

    return session.scalar(statement.order_by(VeeReplayRequest.id.desc()).limit(1))


def _build_active_exception_statement(
    *,
    request_scope: str,
    hes_system_id: int | None,
    ingest_batch_id: int | None,
    measured_at_from: datetime | None,
    measured_at_to: datetime | None,
):
    statement = (
        select(VeeException)
        .options(
            joinedload(VeeException.initial_measurement)
            .joinedload(InitialMeasurement.canonical_measurement)
            .joinedload(CanonicalMeasurement.hes_read_raw)
        )
        .join(VeeException.initial_measurement)
        .where(VeeException.exception_status.in_(ACTIVE_VEE_EXCEPTION_STATUSES))
    )

    if request_scope == "hes_system":
        statement = (
            statement.join(InitialMeasurement.canonical_measurement)
            .join(CanonicalMeasurement.hes_read_raw)
            .where(HesReadRaw.hes_system_id == hes_system_id)
        )
    elif request_scope == "ingest_batch":
        statement = (
            statement.join(InitialMeasurement.canonical_measurement)
            .join(CanonicalMeasurement.hes_read_raw)
            .where(HesReadRaw.ingest_batch_id == ingest_batch_id)
        )
    else:
        statement = statement.where(InitialMeasurement.measured_at >= measured_at_from).where(
            InitialMeasurement.measured_at < measured_at_to
        )

    return statement.order_by(
        InitialMeasurement.id.asc(),
        VeeException.blocking_finalization.desc(),
        VeeException.detected_at.desc(),
        VeeException.id.desc(),
    )


def _select_representative_exceptions(
    session: Session,
    *,
    request_scope: str,
    hes_system_id: int | None,
    ingest_batch_id: int | None,
    measured_at_from: datetime | None,
    measured_at_to: datetime | None,
) -> list[VeeException]:
    statement = _build_active_exception_statement(
        request_scope=request_scope,
        hes_system_id=hes_system_id,
        ingest_batch_id=ingest_batch_id,
        measured_at_from=measured_at_from,
        measured_at_to=measured_at_to,
    )
    selected: list[VeeException] = []
    seen_initial_ids: set[int] = set()
    for vee_exception in session.scalars(statement):
        if vee_exception.initial_measurement_id in seen_initial_ids:
            continue
        seen_initial_ids.add(vee_exception.initial_measurement_id)
        selected.append(vee_exception)
    return selected


def _build_request_details(
    *,
    request_scope: str,
    hes_system_id: int | None,
    ingest_batch_id: int | None,
    measured_at_from: datetime | None,
    measured_at_to: datetime | None,
    window_timezone_name: str | None,
) -> dict[str, object]:
    return {
        "request_scope": request_scope,
        "hes_system_id": hes_system_id,
        "ingest_batch_id": ingest_batch_id,
        "measured_at_from": measured_at_from.isoformat() if measured_at_from else None,
        "measured_at_to": measured_at_to.isoformat() if measured_at_to else None,
        "window_timezone_name": window_timezone_name,
    }


def _build_request_item_details(vee_exception: VeeException) -> dict[str, object]:
    initial_row = vee_exception.initial_measurement
    return {
        "exception_code": vee_exception.exception_code,
        "severity": vee_exception.severity,
        "blocking_finalization": vee_exception.blocking_finalization,
        "detected_at": vee_exception.detected_at.isoformat(),
        "measured_at": initial_row.measured_at.isoformat(),
        "service_point_id": initial_row.service_point_id,
        "measuring_component_id": initial_row.measuring_component_id,
    }


def create_vee_replay_request(
    session: Session,
    *,
    request_scope: str,
    requested_by: str,
    operator_memo: str | None = None,
    hes_system_id: int | None = None,
    ingest_batch_id: int | None = None,
    measured_at_from: datetime | None = None,
    measured_at_to: datetime | None = None,
    window_timezone_name: str | None = None,
) -> VeeReplayRequestCreationResult:
    _validate_scope(
        request_scope=request_scope,
        hes_system_id=hes_system_id,
        ingest_batch_id=ingest_batch_id,
        measured_at_from=measured_at_from,
        measured_at_to=measured_at_to,
    )

    existing_request = _find_existing_active_request(
        session,
        request_scope=request_scope,
        hes_system_id=hes_system_id,
        ingest_batch_id=ingest_batch_id,
        measured_at_from=measured_at_from,
        measured_at_to=measured_at_to,
        window_timezone_name=window_timezone_name,
    )
    if existing_request is not None:
        raise VeeReplayRequestError(
            "request_already_active",
            "A replay request for the same scope is already queued or processing.",
        )

    targets = _select_representative_exceptions(
        session,
        request_scope=request_scope,
        hes_system_id=hes_system_id,
        ingest_batch_id=ingest_batch_id,
        measured_at_from=measured_at_from,
        measured_at_to=measured_at_to,
    )
    if not targets:
        raise VeeReplayRequestError(
            "no_targets_found",
            "No active VEE exceptions were found for the selected replay scope.",
        )

    request = VeeReplayRequest(
        request_scope=request_scope,
        status="queued",
        requested_by=requested_by,
        operator_memo=operator_memo,
        hes_system_id=hes_system_id,
        ingest_batch_id=ingest_batch_id,
        measured_at_from=measured_at_from,
        measured_at_to=measured_at_to,
        window_timezone_name=window_timezone_name,
        target_initial_count=len(targets),
        processed_count=0,
        succeeded_count=0,
        failed_count=0,
        reopened_exception_count=0,
        cleared_exception_count=0,
        final_superseded_count=0,
        usage_recalculated_count=0,
        details=_build_request_details(
            request_scope=request_scope,
            hes_system_id=hes_system_id,
            ingest_batch_id=ingest_batch_id,
            measured_at_from=measured_at_from,
            measured_at_to=measured_at_to,
            window_timezone_name=window_timezone_name,
        ),
    )
    session.add(request)
    session.flush()

    items = [
        VeeReplayRequestItem(
            vee_replay_request_id=request.id,
            initial_measurement_id=vee_exception.initial_measurement_id,
            representative_vee_exception_id=vee_exception.id,
            status="pending",
            details=_build_request_item_details(vee_exception),
        )
        for vee_exception in targets
    ]
    session.add_all(items)
    session.flush()

    record_operational_event(
        session,
        "vee_replay_requested",
        occurred_at=request.created_at,
        entity_type="vee_replay_request",
        entity_id=request.id,
        hes_system=request.hes_system,
        ingest_batch=request.ingest_batch,
        details={
            "request_id": request.id,
            "request_scope": request.request_scope,
            "target_initial_count": request.target_initial_count,
            "requested_by": request.requested_by,
        },
        request_id=request.id,
        request_scope=request.request_scope,
        target_initial_count=request.target_initial_count,
    )
    session.flush()

    return VeeReplayRequestCreationResult(
        request=request,
        created_item_count=len(items),
    )


def cancel_vee_replay_request(
    session: Session,
    request_id: int,
    *,
    cancelled_by: str,
    operator_memo: str | None = None,
) -> VeeReplayRequest:
    request = session.get(VeeReplayRequest, request_id)
    if request is None:
        raise VeeReplayRequestError(
            "not_found",
            "The selected VEE replay request does not exist.",
        )
    if request.status == "cancelled":
        raise VeeReplayRequestError(
            "already_cancelled",
            "The selected VEE replay request is already cancelled.",
        )
    if request.status != "queued":
        raise VeeReplayRequestError(
            "request_not_cancellable",
            "Only queued VEE replay requests can be cancelled.",
        )

    details = dict(request.details or {})
    details["cancelled_by"] = cancelled_by
    details["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    if operator_memo:
        details["cancellation_memo"] = operator_memo

    request.status = "cancelled"
    if operator_memo is not None:
        request.operator_memo = operator_memo
    request.details = details
    session.flush()
    return request
