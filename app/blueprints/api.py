from __future__ import annotations

from datetime import datetime
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
from app.services.invoice_summaries import build_invoice_summary_filters, list_invoice_summaries
from app.services.receive_adapters import ReceiveAdapterError, receive_adapter_payload
from app.services.visibility import (
    build_bill_charge_filters,
    build_billing_export_request_filters,
    VisibilityFilterError,
    build_bill_determinant_filters,
    build_canonical_filters,
    build_final_filters,
    build_ingest_batch_filters,
    build_operational_event_filters,
    build_usage_transaction_filters,
    get_billing_export_request_detail_context,
    list_bill_charges,
    list_bill_determinants,
    list_billing_export_requests,
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
    return _build_calculation_summary(rows, count_key="window_count")


def _build_calculation_summary(rows, *, count_key: str = "row_count") -> dict[str, object]:
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
        count_key: len(rows),
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


def _serialize_service_point_aggregate_filters(
    service_point: ServicePoint,
    filter_args: dict[str, str],
    *,
    limit: int,
) -> dict[str, object]:
    return {
        "service_point_id": service_point.id,
        "service_point_external_id": service_point.external_id,
        "external_channel_id": filter_args.get("external_channel_id"),
        "date_from": filter_args.get("date_from"),
        "date_to": filter_args.get("date_to"),
        "calculation_status": filter_args.get("calculation_status"),
        "usage_type": filter_args.get("usage_type"),
        "determinant_type": filter_args.get("determinant_type"),
        "charge_type": filter_args.get("charge_type"),
        "limit": limit,
    }


def _serialize_invoice_summary_row(row) -> dict[str, object]:
    return {
        "service_point_id": row.service_point_id,
        "service_point_external_id": row.service_point_external_id,
        "billing_period_start_at": row.billing_period_start_at.isoformat(),
        "billing_period_end_at": row.billing_period_end_at.isoformat(),
        "currency_code": row.currency_code,
        "tariff_plan_code": row.tariff_plan_code,
        "charge_count": row.charge_count,
        "complete_count": row.complete_count,
        "partial_count": row.partial_count,
        "blocked_count": row.blocked_count,
        "subtotal_amount": _json_numeric(row.subtotal_amount),
        "summary_status": row.summary_status,
        "export_eligible": row.export_eligible,
        "latest_calculated_at": row.latest_calculated_at.isoformat()
        if row.latest_calculated_at is not None
        else None,
    }


def _serialize_invoice_summary_filters(
    service_point: ServicePoint,
    filter_args: dict[str, str],
    *,
    limit: int,
) -> dict[str, object]:
    return {
        "service_point_id": service_point.id,
        "service_point_external_id": service_point.external_id,
        "external_channel_id": filter_args.get("external_channel_id"),
        "charge_type": filter_args.get("charge_type"),
        "tariff_plan_code": filter_args.get("tariff_plan_code"),
        "calculation_status": filter_args.get("calculation_status"),
        "summary_status": filter_args.get("summary_status"),
        "date_from": filter_args.get("date_from"),
        "date_to": filter_args.get("date_to"),
        "limit": limit,
    }


def _is_processing_heartbeat_stale(status: str, last_heartbeat_at) -> bool:
    if status != "processing" or last_heartbeat_at is None:
        return False
    return (datetime.now(tz=last_heartbeat_at.tzinfo) - last_heartbeat_at).total_seconds() > 300


def _serialize_billing_export_request_row(row) -> dict[str, object]:
    details = row.details or {}
    return {
        "id": row.id,
        "request_scope": row.request_scope,
        "status": row.status,
        "service_point_id": row.service_point_id,
        "service_point_external_id": row.service_point.external_id if row.service_point is not None else None,
        "billing_period_from": row.billing_period_from.isoformat() if row.billing_period_from else None,
        "billing_period_to": row.billing_period_to.isoformat() if row.billing_period_to else None,
        "target_system_code": row.target_system_code,
        "payload_format": row.payload_format,
        "requested_by": row.requested_by,
        "operator_memo": row.operator_memo,
        "item_count": row.item_count,
        "processed_count": row.processed_count,
        "succeeded_count": row.succeeded_count,
        "failed_count": row.failed_count,
        "skipped_count": row.skipped_count,
        "claimed_by": row.claimed_by,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "last_heartbeat_at": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
        "last_error": row.last_error,
        "progress_percent": details.get("progress_percent"),
        "remaining_count": details.get("remaining_count"),
        "current_item_id": details.get("current_item_id"),
        "heartbeat_is_stale": _is_processing_heartbeat_stale(row.status, row.last_heartbeat_at),
    }


def _serialize_billing_export_request_filters(filter_args: dict[str, str], *, limit: int) -> dict[str, object]:
    service_point_id = filter_args.get("service_point_id")
    return {
        "request_scope": filter_args.get("request_scope"),
        "status": filter_args.get("status"),
        "service_point_id": int(service_point_id) if service_point_id else None,
        "service_point": filter_args.get("service_point"),
        "target_system_code": filter_args.get("target_system_code"),
        "requested_by": filter_args.get("requested_by"),
        "date_from": filter_args.get("date_from"),
        "date_to": filter_args.get("date_to"),
        "limit": limit,
    }


def _serialize_pipeline_run_row(row) -> dict[str, object]:
    return {
        "id": row.id,
        "pipeline_name": row.pipeline_name,
        "trigger_type": row.trigger_type,
        "status": row.status,
        "result_code": row.result_code,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "details": row.details or {},
    }


def _serialize_billing_export_item_row(row) -> dict[str, object]:
    return {
        "id": row.id,
        "billing_export_request_id": row.billing_export_request_id,
        "service_point_id": row.service_point_id,
        "service_point_external_id": row.service_point.external_id if row.service_point is not None else None,
        "billing_period_start_at": row.billing_period_start_at.isoformat(),
        "billing_period_end_at": row.billing_period_end_at.isoformat(),
        "currency_code": row.currency_code,
        "tariff_plan_code": row.tariff_plan_code,
        "summary_status": row.summary_status,
        "status": row.status,
        "result_code": row.result_code,
        "exported_at": row.exported_at.isoformat() if row.exported_at else None,
        "last_error": row.last_error,
        "payload_snapshot": row.payload_snapshot or {},
        "details": row.details or {},
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


@bp.get("/service-points/<int:service_point_id>/invoice-summary")
def get_service_point_invoice_summary_endpoint(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        return error_response("service_point_not_found", 404)

    try:
        limit = _parse_api_limit(request.args.get("limit"), default=50)
    except ValueError:
        return error_response("invalid_limit", 400)

    try:
        filter_args = request.args.to_dict(flat=True)
        filter_args["service_point_id"] = str(service_point_id)
        filters = build_invoice_summary_filters(filter_args)
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

    summaries = list_invoice_summaries(session, filters, limit=limit)
    return jsonify(
        {
            "service_point_id": service_point.id,
            "service_point_external_id": service_point.external_id,
            "filters": _serialize_invoice_summary_filters(service_point, filter_args, limit=limit),
            "summaries": [_serialize_invoice_summary_row(row) for row in summaries],
        }
    )


@bp.get("/service-points/<int:service_point_id>/summary")
def get_service_point_summary_endpoint(service_point_id: int):
    session = get_session()
    service_point = session.get(ServicePoint, service_point_id)
    if service_point is None:
        return error_response("service_point_not_found", 404)

    try:
        limit = _parse_api_limit(request.args.get("limit"), default=5)
        filter_args = request.args.to_dict(flat=True)
        filter_args["service_point_id"] = str(service_point_id)
        usage_filters = build_usage_transaction_filters(filter_args)
        determinant_filters = build_bill_determinant_filters(filter_args)
        charge_filters = build_bill_charge_filters(filter_args)
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

    usage_summary_rows = list_usage_transactions(session, usage_filters, limit=None)
    usage_rows = list_usage_transactions(session, usage_filters, limit=limit)
    determinant_summary_rows = list_bill_determinants(session, determinant_filters, limit=None)
    determinant_rows = list_bill_determinants(session, determinant_filters, limit=limit)
    charge_summary_rows = list_bill_charges(session, charge_filters, limit=None)
    charge_rows = list_bill_charges(session, charge_filters, limit=limit)

    return jsonify(
        {
            "service_point_id": service_point.id,
            "service_point_external_id": service_point.external_id,
            "filters": _serialize_service_point_aggregate_filters(
                service_point,
                filter_args,
                limit=limit,
            ),
            "usage": {
                "summary": _build_usage_summary(usage_summary_rows),
                "rows": [_serialize_usage_transaction_row(row) for row in usage_rows],
            },
            "bill_determinants": {
                "summary": _build_calculation_summary(determinant_summary_rows),
                "rows": [_serialize_bill_determinant_row(row) for row in determinant_rows],
            },
            "bill_charges": {
                "summary": _build_calculation_summary(charge_summary_rows),
                "rows": [_serialize_bill_charge_row(row) for row in charge_rows],
            },
        }
    )


@bp.get("/billing-export-requests")
def list_billing_export_requests_endpoint():
    session = get_session()
    try:
        limit = _parse_api_limit(request.args.get("limit"), default=100)
        filter_args = request.args.to_dict(flat=True)
        filters = build_billing_export_request_filters(filter_args)
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

    rows = list_billing_export_requests(session, filters, limit=limit)
    return jsonify(
        {
            "filters": _serialize_billing_export_request_filters(filter_args, limit=limit),
            "rows": [_serialize_billing_export_request_row(row) for row in rows],
        }
    )


@bp.get("/billing-export-requests/<int:request_id>")
def get_billing_export_request_detail_endpoint(request_id: int):
    session = get_session()
    detail = get_billing_export_request_detail_context(session, request_id)
    if detail is None:
        return error_response("billing_export_request_not_found", 404)

    return jsonify(
        {
            "request": _serialize_billing_export_request_row(detail.request),
            "latest_pipeline_run": (
                _serialize_pipeline_run_row(detail.latest_pipeline_run)
                if detail.latest_pipeline_run is not None
                else None
            ),
            "current_item": (
                _serialize_billing_export_item_row(detail.current_item)
                if detail.current_item is not None
                else None
            ),
            "focus_item": (
                _serialize_billing_export_item_row(detail.focus_item)
                if detail.focus_item is not None
                else None
            ),
            "recent_items": [
                _serialize_billing_export_item_row(row) for row in detail.recent_items
            ],
            "failed_items": [
                _serialize_billing_export_item_row(row) for row in detail.failed_items
            ],
            "heartbeat_is_stale": detail.heartbeat_is_stale,
            "request_metadata": detail.request.details or {},
        }
    )


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
