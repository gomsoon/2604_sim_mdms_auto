from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.db import check_database_connection, get_session
from app.models import HesEventRaw, HesReadRaw, IngestErrorLog
from app.services.ingestion import ingest_events, ingest_reads


bp = Blueprint("api", __name__)


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
    if not payload:
        return jsonify({"error": "JSON payload is required."}), 400

    session = get_session()
    try:
        summary = ingest_reads(session, payload)
        session.commit()
    except Exception as exc:
        session.rollback()
        return jsonify({"error": str(exc)}), 400

    return jsonify(summary), 201


@bp.post("/ingest/events")
def ingest_events_endpoint():
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "JSON payload is required."}), 400

    session = get_session()
    try:
        summary = ingest_events(session, payload)
        session.commit()
    except Exception as exc:
        session.rollback()
        return jsonify({"error": str(exc)}), 400

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
    rows = session.scalars(
        select(IngestErrorLog).order_by(IngestErrorLog.id.desc()).limit(100)
    ).all()
    return jsonify(
        [
            {
                "id": row.id,
                "type": row.exception_type,
                "code": row.exception_code,
                "status": row.status,
                "message": row.message,
            }
            for row in rows
        ]
    )
