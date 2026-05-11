from __future__ import annotations

from decimal import Decimal

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from app.db import check_database_connection, get_session
from app.i18n import get_locale, translate, translate_visibility_error
from app.models import HesEventRaw, HesReadRaw, ServicePoint
from app.services.exception_queue import (
    build_exception_filters,
    get_exception_batch_id,
    get_exception_meter_id,
    list_exception_queue,
)
from app.services.ingest_contract import IngestContractError, validate_ingest_envelope
from app.services.ingestion import ingest_events, ingest_reads
from app.services.receive_adapters import ReceiveAdapterError, receive_adapter_payload
from app.services.visibility import (
    build_bill_charge_filters,
    VisibilityFilterError,
    build_bill_determinant_filters,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    build_operational_event_filters,
    build_usage_transaction_filters,
    list_bill_charges,
    list_bill_determinants,
    list_canonical_measurements,
    list_final_measurements,
    list_ingest_batches,
    list_operational_events,
    list_usage_transactions,
)


bp = Blueprint("api", __name__)


def _json_numeric(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


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


def _parse_api_limit(
    value: str | None,
    *,
    default: int = 200,
    maximum: int = 500,
) -> int:
    if value in {None, ""}:
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid_limit") from exc

    if parsed <= 0 or parsed > maximum:
        raise ValueError("invalid_limit")
    return parsed


def _serialize_usage_transaction_row(row) -> dict[str, object]:
    return {
        "id": row.id,
        "service_point_id": row.service_point_id,
        "service_point_external_id": row.service_point.external_id,
        "device_id": row.device_id,
        "measuring_component_id": row.measuring_component_id,
        "external_channel_id": row.measuring_component.external_channel_id,
        "usage_type": row.usage_type,
        "period_start_at": row.period_start_at.isoformat(),
        "period_end_at": row.period_end_at.isoformat(),
        "window_timezone_name": row.window_timezone_name,
        "interval_size_minutes": row.interval_size_minutes,
        "unit_of_measure": row.unit_of_measure,
        "usage_value": _json_numeric(row.usage_value),
        "source_final_count": row.source_final_count,
        "missing_interval_count": row.missing_interval_count,
        "quality_summary": row.quality_summary,
        "calculation_status": row.calculation_status,
        "calculated_at": row.calculated_at.isoformat(),
        "pipeline_run_id": row.pipeline_run_id,
    }


def _serialize_usage_summary_filters(
    service_point: ServicePoint,
    filter_args: dict[str, str],
    *,
    limit: int,
) -> dict[str, object]:
    return {
        "service_point_id": service_point.id,
        "service_point_external_id": service_point.external_id,
        "usage_type": filter_args.get("usage_type"),
        "external_channel_id": filter_args.get("external_channel_id"),
        "date_from": filter_args.get("date_from"),
        "date_to": filter_args.get("date_to"),
        "calculation_status": filter_args.get("calculation_status"),
        "limit": limit,
    }


def _build_usage_summary(rows) -> dict[str, object]:
    quality_summaries: dict[str, int] = {}
    latest_calculated_at = None
    complete_count = 0
    partial_count = 0
    blocked_count = 0

    for row in rows:
        if row.calculation_status == "complete":
            complete_count += 1
        elif row.calculation_status == "partial":
            partial_count += 1
        elif row.calculation_status == "blocked":
            blocked_count += 1

        quality_key = row.quality_summary or "none"
        quality_summaries[quality_key] = quality_summaries.get(quality_key, 0) + 1

        if latest_calculated_at is None or row.calculated_at > latest_calculated_at:
            latest_calculated_at = row.calculated_at

    return {
        "window_count": len(rows),
        "complete_count": complete_count,
        "partial_count": partial_count,
        "blocked_count": blocked_count,
        "latest_calculated_at": latest_calculated_at.isoformat()
        if latest_calculated_at is not None
        else None,
        "quality_summaries": quality_summaries,
    }


def _serialize_bill_determinant_row(row) -> dict[str, object]:
    billing_context_snapshot = {}
    if isinstance(row.details, dict):
        billing_context_snapshot = row.details.get("billing_context_snapshot") or {}

    return {
        "id": row.id,
        "service_point_id": row.service_point_id,
        "service_point_external_id": row.service_point.external_id,
        "device_id": row.device_id,
        "measuring_component_id": row.measuring_component_id,
        "external_channel_id": (
            row.measuring_component.external_channel_id if row.measuring_component is not None else None
        ),
        "determinant_type": row.determinant_type,
        "billing_period_start_at": row.billing_period_start_at.isoformat(),
        "billing_period_end_at": row.billing_period_end_at.isoformat(),
        "window_timezone_name": row.window_timezone_name,
        "billing_cycle_mode": billing_context_snapshot.get("billing_cycle_mode"),
        "unit_of_measure": row.unit_of_measure,
        "determinant_value": _json_numeric(row.determinant_value),
        "source_usage_count": row.source_usage_count,
        "quality_summary": row.quality_summary,
        "calculation_status": row.calculation_status,
        "revision_number": row.revision_number,
        "is_current": row.is_current,
        "calculated_at": row.calculated_at.isoformat(),
        "pipeline_run_id": row.pipeline_run_id,
    }


def _serialize_bill_charge_row(row) -> dict[str, object]:
    return {
        "id": row.id,
        "service_point_id": row.service_point_id,
        "service_point_external_id": row.service_point.external_id,
        "device_id": row.device_id,
        "measuring_component_id": row.measuring_component_id,
        "external_channel_id": (
            row.measuring_component.external_channel_id if row.measuring_component is not None else None
        ),
        "bill_determinant_id": row.bill_determinant_id,
        "charge_type": row.charge_type,
        "billing_period_start_at": row.billing_period_start_at.isoformat(),
        "billing_period_end_at": row.billing_period_end_at.isoformat(),
        "currency_code": row.currency_code,
        "tariff_plan_code": row.tariff_plan_code,
        "tariff_version_code": row.tariff_version_code,
        "quantity_value": _json_numeric(row.quantity_value),
        "unit_rate_value": _json_numeric(row.unit_rate_value),
        "charge_amount": _json_numeric(row.charge_amount),
        "quality_summary": row.quality_summary,
        "calculation_status": row.calculation_status,
        "revision_number": row.revision_number,
        "is_current": row.is_current,
        "calculated_at": row.calculated_at.isoformat(),
        "pipeline_run_id": row.pipeline_run_id,
    }


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


def _receive_adapter_secret() -> str | None:
    return request.headers.get("X-Adapter-Secret")


@bp.post("/receive/<string:instance_code>/reads")
def receive_reads_endpoint(instance_code: str):
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return error_response("json_payload_required", 400)

    session = get_session()
    try:
        summary = receive_adapter_payload(
            session,
            instance_code=instance_code,
            record_type="hes_read_raw",
            payload=payload,
            shared_secret=_receive_adapter_secret(),
        )
        session.commit()
    except ReceiveAdapterError as exc:
        session.rollback()
        return error_response(exc.error_code, exc.status_code, details=exc.fallback_message)
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


@bp.post("/receive/<string:instance_code>/events")
def receive_events_endpoint(instance_code: str):
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return error_response("json_payload_required", 400)

    session = get_session()
    try:
        summary = receive_adapter_payload(
            session,
            instance_code=instance_code,
            record_type="hes_event_raw",
            payload=payload,
            shared_secret=_receive_adapter_secret(),
        )
        session.commit()
    except ReceiveAdapterError as exc:
        session.rollback()
        return error_response(exc.error_code, exc.status_code, details=exc.fallback_message)
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
                "value": _json_numeric(row.reading_value),
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
                "value": _json_numeric(row.value),
                "unit_of_measure": row.unit_of_measure,
                "service_point_id": row.service_point_id,
                "device_id": row.device_id,
            }
            for row in rows
        ]
    )


@bp.get("/final-measurements")
def list_final_measurements_endpoint():
    session = get_session()
    try:
        filters = build_final_filters(request.args)
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

    rows = list_final_measurements(session, filters)
    return jsonify(
        [
            {
                "id": row.id,
                "batch_id": row.canonical_measurement.hes_read_raw.ingest_batch.batch_id,
                "source_system": row.canonical_measurement.hes_read_raw.source_system,
                "meter_id": row.canonical_measurement.hes_read_raw.meter_identifier,
                "channel_id": row.canonical_measurement.hes_read_raw.channel_identifier,
                "measured_at": row.measured_at.isoformat(),
                "value": _json_numeric(row.value),
                "unit_of_measure": row.unit_of_measure,
                "final_status": row.final_status,
                "finalized_at": row.finalized_at.isoformat(),
                "service_point_id": row.service_point_id,
                "device_id": row.device_id,
            }
            for row in rows
        ]
    )


@bp.get("/service-points/<int:service_point_id>/usage")
def list_service_point_usage_endpoint(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        return error_response("service_point_not_found", 404)

    try:
        limit = _parse_api_limit(request.args.get("limit"))
        filter_args = request.args.to_dict(flat=True)
        filter_args["service_point_id"] = str(service_point_id)
        filters = build_usage_transaction_filters(filter_args)
    except ValueError:
        return error_response("invalid_limit", 400)
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

    rows = list_usage_transactions(session, filters, limit=limit)
    return jsonify([_serialize_usage_transaction_row(row) for row in rows])


@bp.get("/service-points/<int:service_point_id>/usage-summary")
def get_service_point_usage_summary_endpoint(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        return error_response("service_point_not_found", 404)

    try:
        limit = _parse_api_limit(request.args.get("limit"), default=50)
        filter_args = request.args.to_dict(flat=True)
        filter_args["service_point_id"] = str(service_point_id)
        filters = build_usage_transaction_filters(filter_args)
    except ValueError:
        return error_response("invalid_limit", 400)
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

    summary_rows = list_usage_transactions(session, filters, limit=None)
    rows = list_usage_transactions(session, filters, limit=limit)
    return jsonify(
        {
            "service_point_id": service_point.id,
            "service_point_external_id": service_point.external_id,
            "filters": _serialize_usage_summary_filters(service_point, filter_args, limit=limit),
            "summary": _build_usage_summary(summary_rows),
            "rows": [_serialize_usage_transaction_row(row) for row in rows],
        }
    )


@bp.get("/service-points/<int:service_point_id>/bill-determinants")
def list_service_point_bill_determinants_endpoint(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        return error_response("service_point_not_found", 404)

    try:
        limit = _parse_api_limit(request.args.get("limit"))
        filter_args = request.args.to_dict(flat=True)
        filter_args["service_point_id"] = str(service_point_id)
        filters = build_bill_determinant_filters(filter_args)
    except ValueError:
        return error_response("invalid_limit", 400)
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

    rows = list_bill_determinants(session, filters, limit=limit)
    return jsonify([_serialize_bill_determinant_row(row) for row in rows])


@bp.get("/service-points/<int:service_point_id>/bill-charges")
def list_service_point_bill_charges_endpoint(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        return error_response("service_point_not_found", 404)

    try:
        limit = _parse_api_limit(request.args.get("limit"))
        filter_args = request.args.to_dict(flat=True)
        filter_args["service_point_id"] = str(service_point_id)
        filters = build_bill_charge_filters(filter_args)
    except ValueError:
        return error_response("invalid_limit", 400)
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

    rows = list_bill_charges(session, filters, limit=limit)
    return jsonify([_serialize_bill_charge_row(row) for row in rows])


@bp.get("/operational-events")
def list_operational_events_endpoint():
    session = get_session()
    try:
        filters = build_operational_event_filters(request.args)
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

    rows = list_operational_events(session, filters)
    return jsonify(
        [
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat(),
                "hes_system_id": row.hes_system_id,
                "hes_code": row.hes_system.hes_code if row.hes_system is not None else None,
                "hes_display_name": (
                    row.hes_system.display_name if row.hes_system is not None else None
                ),
                "source_layer": row.source_layer,
                "event_category": row.event_category,
                "event_code": row.event_code,
                "severity": row.severity,
                "is_alert": row.is_alert,
                "alert_status": row.alert_status,
                "opened_at": row.opened_at.isoformat() if row.opened_at else None,
                "acknowledged_at": row.acknowledged_at.isoformat() if row.acknowledged_at else None,
                "closed_at": row.closed_at.isoformat() if row.closed_at else None,
                "acknowledged_by": row.acknowledged_by,
                "operator_memo": row.operator_memo,
                "batch_id": row.batch_id,
                "meter_id": row.meter_identifier,
                "title_en": row.title_en,
                "title_ko": row.title_ko,
                "message_en": row.message_en,
                "message_ko": row.message_ko,
            }
            for row in rows
        ]
    )
