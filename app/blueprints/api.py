from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.db import check_database_connection, get_session
from app.i18n import get_locale, translate, translate_visibility_error
from app.models import HesEventRaw, HesReadRaw
from app.services.exception_queue import (
    build_exception_filters,
    get_exception_batch_id,
    get_exception_meter_id,
    list_exception_queue,
)
from app.services.ingest_contract import IngestContractError, validate_ingest_envelope
from app.services.ingestion import ingest_events, ingest_reads
from app.services.visibility import (
    VisibilityFilterError,
    build_canonical_filters,
    build_ingest_batch_filters,
    list_canonical_measurements,
    list_ingest_batches,
)


bp = Blueprint("api", __name__)


def error_response(
    error_code: str,
    status_code: int,
    *,
    details: str | None = None,
    locale: str | None = None,
):
    response_locale = locale or get_locale()
    payload = {
        "error_code": error_code,
        "message": translate(f"api.errors.{error_code}", locale=response_locale),
        "locale": response_locale,
    }
    if details:
        payload["details"] = details

    return jsonify(payload), status_code


@bp.get("/health")
def health_check():
    try:
        check_database_connection()
    except Exception as exc:
        return (
            jsonify(
                {
                    "status": "degraded",
                    "database": "down",
                    "error": str(exc),
                }
            ),
            503,
        )

    return jsonify({"status": "ok", "database": "up"})



@bp.post("/ingest/reads")
def ingest_reads_endpoint():
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return error_response("json_payload_required", 400)

    session = get_session()
    try:
        validate_ingest_envelope(session, payload, record_type="hes_read_raw")
        summary = ingest_reads(session, payload)
        session.commit()
    except IngestContractError as exc:
        session.rollback()
        return error_response(
            exc.error_code,
            exc.status_code,
            details=exc.fallback_message,
            locale=exc.response_locale,
        )
    except Exception as exc:
        session.rollback()
        return error_response("ingest_request_failed", 400, details=str(exc))

    return jsonify(summary), 201


@bp.post("/ingest/events")
def ingest_events_endpoint():
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return error_response("json_payload_required", 400)

    session = get_session()
    try:
        validate_ingest_envelope(session, payload, record_type="hes_event_raw")
        summary = ingest_events(session, payload)
        session.commit()
    except IngestContractError as exc:
        session.rollback()
        return error_response(
            exc.error_code,
            exc.status_code,
            details=exc.fallback_message,
            locale=exc.response_locale,
        )
    except Exception as exc:
        session.rollback()
        return error_response("ingest_request_failed", 400, details=str(exc))

    return jsonify(summary), 201


@bp.get("/raw-reads")
def list_raw_reads():
    session = get_session()
    rows = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(100)).all()
    return jsonify(
        [
            {
                "id": row.id,
                "source_system": row.source_system,
                "meter_id": row.meter_identifier,
                "channel_id": row.channel_identifier,
                "measured_at": row.measured_at.isoformat() if row.measured_at else None,
                "value": row.reading_value,
                "status": row.canonical_status,
                "duplicate": row.is_duplicate,
            }
            for row in rows
        ]
    )


@bp.get("/raw-events")
def list_raw_events():
    session = get_session()
    rows = session.scalars(select(HesEventRaw).order_by(HesEventRaw.id.desc()).limit(100)).all()
    return jsonify(
        [
            {
                "id": row.id,
                "source_system": row.source_system,
                "meter_id": row.meter_identifier,
                "event_time": row.event_time.isoformat() if row.event_time else None,
                "event_code": row.event_code,
                "severity": row.severity,
            }
            for row in rows
        ]
    )


@bp.get("/exceptions")
def list_exceptions():
    session = get_session()
    filters = build_exception_filters(request.args)
    rows = list_exception_queue(session, filters)
    return jsonify(
        [
            {
                "id": row.id,
                "type": row.exception_type,
                "code": row.exception_code,
                "status": row.status,
                "message": row.message,
                "batch_id": get_exception_batch_id(row),
                "meter_id": get_exception_meter_id(row),
            }
            for row in rows
        ]
    )


@bp.get("/ingest-batches")
def list_ingest_batches_endpoint():
    session = get_session()
    try:
        filters = build_ingest_batch_filters(request.args)
    except VisibilityFilterError as exc:
        return (
            jsonify(
                {
                    "error_code": exc.error_code,
                    "message": translate_visibility_error(exc.error_code, exc.fallback_message),
                    "locale": get_locale(),
                }
            ),
            400,
        )

    rows = list_ingest_batches(session, filters)
    return jsonify(
        [
            {
                "id": row.id,
                "source_system": row.source_system,
                "batch_id": row.batch_id,
                "record_type": row.record_type,
                "received_at": row.received_at.isoformat(),
                "raw_reads": len(row.hes_read_rows),
                "raw_events": len(row.hes_event_rows),
            }
            for row in rows
        ]
    )


@bp.get("/canonical-measurements")
def list_canonical_measurements_endpoint():
    session = get_session()
    try:
        filters = build_canonical_filters(request.args)
    except VisibilityFilterError as exc:
        return (
            jsonify(
                {
                    "error_code": exc.error_code,
                    "message": translate_visibility_error(exc.error_code, exc.fallback_message),
                    "locale": get_locale(),
                }
            ),
            400,
        )

    rows = list_canonical_measurements(session, filters)
    return jsonify(
        [
            {
                "id": row.id,
                "batch_id": row.hes_read_raw.ingest_batch.batch_id,
                "source_system": row.hes_read_raw.source_system,
                "meter_id": row.hes_read_raw.meter_identifier,
                "channel_id": row.hes_read_raw.channel_identifier,
                "measured_at": row.measured_at.isoformat(),
                "value": row.value,
                "unit_of_measure": row.unit_of_measure,
                "service_point_id": row.service_point_id,
                "device_id": row.device_id,
            }
            for row in rows
        ]
    )
