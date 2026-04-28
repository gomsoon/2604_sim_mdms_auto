from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InitialMeasurement, PipelineRun, VeeException, VeeExecutionLog
from app.services.operational_events import (
    acknowledge_operational_alerts,
    close_operational_alerts,
    record_operational_event,
)

BASELINE_RULE_SET_CODE = "vee_baseline_v1"
BASELINE_EXECUTION_SCOPE = "measurement"


@dataclass(frozen=True, slots=True)
class VeeRuleHit:
    exception_code: str
    severity: str
    blocking_finalization: bool
    details: dict[str, object]


@dataclass(frozen=True, slots=True)
class VeeExceptionActionError(Exception):
    error_code: str
    fallback_message: str


def _find_existing_baseline_execution(
    session: Session,
    initial_row: InitialMeasurement,
) -> VeeExecutionLog | None:
    return session.scalar(
        select(VeeExecutionLog)
        .where(
            VeeExecutionLog.initial_measurement_id == initial_row.id,
            VeeExecutionLog.execution_scope == BASELINE_EXECUTION_SCOPE,
            VeeExecutionLog.rule_set_code == BASELINE_RULE_SET_CODE,
        )
        .order_by(VeeExecutionLog.id.asc())
        .limit(1)
    )


def _build_required_field_hit(initial_row: InitialMeasurement) -> VeeRuleHit | None:
    missing_fields: list[str] = []
    if initial_row.measured_at is None:
        missing_fields.append("measured_at")
    if initial_row.value is None:
        missing_fields.append("value")
    if not (initial_row.unit_of_measure or "").strip():
        missing_fields.append("unit_of_measure")
    if initial_row.measuring_component_id is None:
        missing_fields.append("measuring_component_id")
    if initial_row.device_id is None:
        missing_fields.append("device_id")
    if initial_row.service_point_id is None:
        missing_fields.append("service_point_id")

    if not missing_fields:
        return None

    return VeeRuleHit(
        exception_code="vee_required_field_missing",
        severity="error",
        blocking_finalization=True,
        details={"fields": missing_fields},
    )


def _build_negative_value_hit(initial_row: InitialMeasurement) -> VeeRuleHit | None:
    if initial_row.value is None or initial_row.value >= 0:
        return None

    return VeeRuleHit(
        exception_code="vee_negative_value_detected",
        severity="error",
        blocking_finalization=True,
        details={"value": str(initial_row.value)},
    )


def _build_zero_value_hit(initial_row: InitialMeasurement) -> VeeRuleHit | None:
    if initial_row.value is None or initial_row.value != 0:
        return None

    return VeeRuleHit(
        exception_code="vee_zero_value_detected",
        severity="warning",
        blocking_finalization=False,
        details={"value": str(initial_row.value)},
    )


def _build_interval_size_hit(initial_row: InitialMeasurement) -> VeeRuleHit | None:
    canonical_row = initial_row.canonical_measurement
    raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
    interval_size_minutes = raw_row.interval_size_minutes if raw_row is not None else None
    if interval_size_minutes in {15, 30, 60}:
        return None

    return VeeRuleHit(
        exception_code="vee_interval_size_invalid",
        severity="error",
        blocking_finalization=True,
        details={"interval_size_minutes": interval_size_minutes},
    )


def _build_duplicate_hit(initial_row: InitialMeasurement) -> VeeRuleHit | None:
    canonical_row = initial_row.canonical_measurement
    raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
    if raw_row is None or not (raw_row.is_duplicate or raw_row.canonical_status == "duplicate"):
        return None

    return VeeRuleHit(
        exception_code="vee_duplicate_detected",
        severity="error",
        blocking_finalization=True,
        details={
            "hes_read_raw_id": raw_row.id,
            "duplicate_of_id": raw_row.duplicate_of_id,
        },
    )


def evaluate_initial_measurement_rule_hits(initial_row: InitialMeasurement) -> list[VeeRuleHit]:
    hits: list[VeeRuleHit] = []
    for hit in (
        _build_required_field_hit(initial_row),
        _build_negative_value_hit(initial_row),
        _build_zero_value_hit(initial_row),
        _build_interval_size_hit(initial_row),
        _build_duplicate_hit(initial_row),
    ):
        if hit is not None:
            hits.append(hit)
    return hits


def _build_summary_code(rule_hits: list[VeeRuleHit]) -> str:
    if not rule_hits:
        return "vee_passed"

    first_code = rule_hits[0].exception_code
    if first_code == "vee_required_field_missing":
        return "vee_failed_required_field"
    if first_code == "vee_negative_value_detected":
        return "vee_failed_negative_value"
    if first_code == "vee_zero_value_detected":
        return "vee_completed_with_zero_value"
    if first_code == "vee_interval_size_invalid":
        return "vee_failed_interval_size"
    if first_code == "vee_duplicate_detected":
        return "vee_completed_with_duplicate"
    return "vee_completed_with_exception"


def is_vee_exception_active(exception: VeeException) -> bool:
    return exception.exception_status in {"open", "acknowledged"}


def has_active_blocking_vee_exception(initial_row: InitialMeasurement) -> bool:
    return any(
        exception.blocking_finalization and is_vee_exception_active(exception)
        for exception in initial_row.vee_exceptions
    )


def refresh_initial_measurement_status(initial_row: InitialMeasurement) -> None:
    if has_active_blocking_vee_exception(initial_row):
        initial_row.initial_status = "exception"
    elif initial_row.initial_status == "exception":
        initial_row.initial_status = "accepted"


def create_or_get_vee_exception(
    session: Session,
    *,
    initial_row: InitialMeasurement,
    execution: VeeExecutionLog,
    hit: VeeRuleHit,
) -> tuple[VeeException, bool]:
    existing = session.scalar(
        select(VeeException)
        .where(
            VeeException.initial_measurement_id == initial_row.id,
            VeeException.exception_code == hit.exception_code,
        )
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    if existing is not None:
        if existing.vee_execution_log_id is None:
            existing.vee_execution_log = execution
            session.flush()
        return existing, False

    exception = VeeException(
        initial_measurement_id=initial_row.id,
        vee_execution_log_id=execution.id,
        exception_code=hit.exception_code,
        severity=hit.severity,
        exception_status="open",
        blocking_finalization=hit.blocking_finalization,
        detected_at=datetime.now(timezone.utc),
        details=hit.details,
    )
    session.add(exception)
    session.flush()
    _record_vee_exception_opened(
        session,
        exception=exception,
        initial_row=initial_row,
        execution=execution,
    )
    return exception, True


def evaluate_or_get_vee_baseline(
    session: Session,
    initial_row: InitialMeasurement,
    *,
    pipeline_run: PipelineRun | None = None,
    trigger_type: str = "system",
) -> tuple[VeeExecutionLog, bool]:
    existing = _find_existing_baseline_execution(session, initial_row)
    if existing is not None:
        if has_active_blocking_vee_exception(initial_row):
            initial_row.initial_status = "exception"
        elif existing.execution_status in {"passed", "completed_with_exception"}:
            initial_row.initial_status = "accepted"
        return existing, False

    rule_hits = evaluate_initial_measurement_rule_hits(initial_row)
    now = datetime.now(timezone.utc)
    summary_code = _build_summary_code(rule_hits)
    execution = VeeExecutionLog(
        initial_measurement_id=initial_row.id,
        pipeline_run_id=pipeline_run.id if pipeline_run is not None else None,
        execution_scope=BASELINE_EXECUTION_SCOPE,
        trigger_type=trigger_type,
        rule_set_code=BASELINE_RULE_SET_CODE,
        period_start_at=initial_row.measured_at,
        period_end_at=initial_row.measured_at,
        execution_status="passed" if not rule_hits else "completed_with_exception",
        started_at=now,
        completed_at=now,
        summary_code=summary_code,
        details={
            "mode": "baseline_rule_evaluation",
            "active_rules": [
                "required_field_missing",
                "negative_value_detected",
                "zero_value_detected",
                "interval_size_invalid",
                "duplicate_detected",
            ],
            "rule_hits": [hit.exception_code for hit in rule_hits],
        },
    )
    session.add(execution)
    session.flush()

    if not rule_hits:
        initial_row.initial_status = "accepted"
        return execution, True

    initial_row.initial_status = (
        "exception" if any(hit.blocking_finalization for hit in rule_hits) else "accepted"
    )
    for hit in rule_hits:
        create_or_get_vee_exception(
            session,
            initial_row=initial_row,
            execution=execution,
            hit=hit,
        )
    return execution, True


def _get_vee_exception(session: Session, vee_exception_id: int) -> VeeException:
    vee_exception = session.get(VeeException, vee_exception_id)
    if vee_exception is None:
        raise VeeExceptionActionError("not_found", "The selected VEE exception does not exist.")
    return vee_exception


def _record_vee_exception_opened(
    session: Session,
    *,
    exception: VeeException,
    initial_row: InitialMeasurement,
    execution: VeeExecutionLog,
) -> None:
    canonical_row = initial_row.canonical_measurement
    raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
    ingest_batch = raw_row.ingest_batch if raw_row is not None else None
    record_operational_event(
        session,
        "vee_exception_opened",
        severity=exception.severity,
        is_alert=exception.blocking_finalization,
        entity_type="vee_exception",
        entity_id=exception.id,
        pipeline_run=execution.pipeline_run,
        ingest_batch=ingest_batch,
        hes_system=raw_row.hes_system if raw_row is not None else None,
        meter_identifier=raw_row.meter_identifier if raw_row is not None else None,
        batch_id=ingest_batch.batch_id if ingest_batch is not None else None,
        details={
            "vee_exception_id": exception.id,
            "initial_measurement_id": initial_row.id,
            "canonical_measurement_id": canonical_row.id if canonical_row is not None else None,
            "hes_read_raw_id": raw_row.id if raw_row is not None else None,
            "blocking_finalization": exception.blocking_finalization,
        },
        exception_code=exception.exception_code,
        initial_measurement_id=initial_row.id,
    )


def acknowledge_vee_exception(
    session: Session,
    vee_exception_id: int,
    *,
    acknowledged_by: str,
    acknowledged_at: datetime | None = None,
) -> VeeException:
    vee_exception = _get_vee_exception(session, vee_exception_id)
    if vee_exception.exception_status == "resolved":
        raise VeeExceptionActionError(
            "already_resolved", "The selected VEE exception is already resolved."
        )
    if vee_exception.exception_status == "acknowledged":
        raise VeeExceptionActionError(
            "already_acknowledged",
            "The selected VEE exception is already acknowledged.",
        )

    vee_exception.exception_status = "acknowledged"
    vee_exception.acknowledged_at = acknowledged_at or datetime.now(timezone.utc)
    vee_exception.acknowledged_by = acknowledged_by
    if vee_exception.blocking_finalization:
        vee_exception.initial_measurement.initial_status = "exception"
    else:
        refresh_initial_measurement_status(vee_exception.initial_measurement)
    acknowledge_operational_alerts(
        session,
        event_code="vee_exception_opened",
        entity_type="vee_exception",
        entity_id=vee_exception.id,
        acknowledged_by=acknowledged_by,
        acknowledged_at=vee_exception.acknowledged_at,
    )
    session.flush()
    return vee_exception


def resolve_vee_exception(
    session: Session,
    vee_exception_id: int,
    *,
    resolution_type: str,
    operator_memo: str | None = None,
    resolved_at: datetime | None = None,
) -> VeeException:
    vee_exception = _get_vee_exception(session, vee_exception_id)
    if vee_exception.exception_status == "resolved":
        raise VeeExceptionActionError(
            "already_resolved", "The selected VEE exception is already resolved."
        )

    normalized_resolution_type = (resolution_type or "").strip() or "operator_resolution"
    normalized_memo = (operator_memo or "").strip() or None

    vee_exception.exception_status = "resolved"
    vee_exception.resolution_type = normalized_resolution_type
    vee_exception.resolved_at = resolved_at or datetime.now(timezone.utc)
    if normalized_memo:
        vee_exception.operator_memo = normalized_memo
    refresh_initial_measurement_status(vee_exception.initial_measurement)
    close_operational_alerts(
        session,
        event_code="vee_exception_opened",
        entity_type="vee_exception",
        entity_id=vee_exception.id,
        closed_at=vee_exception.resolved_at,
        operator_memo=normalized_memo,
    )
    canonical_row = vee_exception.initial_measurement.canonical_measurement
    raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
    ingest_batch = raw_row.ingest_batch if raw_row is not None else None
    record_operational_event(
        session,
        "vee_exception_resolved",
        entity_type="vee_exception",
        entity_id=vee_exception.id,
        pipeline_run=vee_exception.vee_execution_log.pipeline_run
        if vee_exception.vee_execution_log is not None
        else None,
        ingest_batch=ingest_batch,
        hes_system=raw_row.hes_system if raw_row is not None else None,
        meter_identifier=raw_row.meter_identifier if raw_row is not None else None,
        batch_id=ingest_batch.batch_id if ingest_batch is not None else None,
        details={
            "vee_exception_id": vee_exception.id,
            "initial_measurement_id": vee_exception.initial_measurement_id,
            "resolution_type": normalized_resolution_type,
        },
        exception_code=vee_exception.exception_code,
        resolution_type=normalized_resolution_type,
    )
    session.flush()
    return vee_exception
