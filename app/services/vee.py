from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InitialMeasurement, PipelineRun, VeeException, VeeExecutionLog

BASELINE_RULE_SET_CODE = "vee_baseline_v1"
BASELINE_EXECUTION_SCOPE = "measurement"


@dataclass(frozen=True, slots=True)
class VeeRuleHit:
    exception_code: str
    severity: str
    blocking_finalization: bool
    details: dict[str, object]


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
    if first_code == "vee_duplicate_detected":
        return "vee_completed_with_duplicate"
    return "vee_completed_with_exception"


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
        if any(
            exception.exception_status == "open" and exception.blocking_finalization
            for exception in initial_row.vee_exceptions
        ):
            initial_row.initial_status = "exception"
        elif existing.execution_status == "passed":
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

    initial_row.initial_status = "exception"
    for hit in rule_hits:
        create_or_get_vee_exception(
            session,
            initial_row=initial_row,
            execution=execution,
            hit=hit,
        )
    return execution, True
