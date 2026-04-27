from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CanonicalMeasurement, InitialMeasurement, PipelineRun, VeeExecutionLog


def is_canonical_measurement_pass_through_eligible(row: CanonicalMeasurement) -> bool:
    raw_row = row.hes_read_raw
    return bool(
        raw_row is not None
        and raw_row.canonical_status == "mapped"
        and not raw_row.is_duplicate
        and row.measured_at is not None
        and row.value is not None
        and row.unit_of_measure
        and row.measuring_component_id
        and row.device_id
        and row.service_point_id
    )


def create_or_get_initial_measurement(
    session: Session,
    canonical_row: CanonicalMeasurement,
) -> tuple[InitialMeasurement, bool]:
    if canonical_row.initial_measurement is not None:
        return canonical_row.initial_measurement, False

    initial_row = InitialMeasurement(
        canonical_measurement=canonical_row,
        measuring_component_id=canonical_row.measuring_component_id,
        device_id=canonical_row.device_id,
        service_point_id=canonical_row.service_point_id,
        measured_at=canonical_row.measured_at,
        value=canonical_row.value,
        quality_code=canonical_row.quality_code,
        status_code=canonical_row.status_code,
        unit_of_measure=canonical_row.unit_of_measure,
        initial_status="ready",
        ready_for_vee_at=datetime.now(timezone.utc),
        details={"origin": "canonical_measurement"},
    )
    session.add(initial_row)
    session.flush()
    return initial_row, True


def create_or_get_pass_through_vee_execution(
    session: Session,
    initial_row: InitialMeasurement,
    *,
    pipeline_run: PipelineRun | None = None,
    trigger_type: str = "system",
) -> tuple[VeeExecutionLog, bool]:
    existing = session.scalar(
        select(VeeExecutionLog)
        .where(
            VeeExecutionLog.initial_measurement_id == initial_row.id,
            VeeExecutionLog.execution_scope == "measurement",
            VeeExecutionLog.rule_set_code == "vee_baseline_v1",
            VeeExecutionLog.summary_code == "vee_passed",
        )
        .order_by(VeeExecutionLog.id.asc())
        .limit(1)
    )
    if existing is not None:
        return existing, False

    now = datetime.now(timezone.utc)
    execution = VeeExecutionLog(
        initial_measurement_id=initial_row.id,
        pipeline_run_id=pipeline_run.id if pipeline_run is not None else None,
        execution_scope="measurement",
        trigger_type=trigger_type,
        rule_set_code="vee_baseline_v1",
        period_start_at=initial_row.measured_at,
        period_end_at=initial_row.measured_at,
        execution_status="passed",
        started_at=now,
        completed_at=now,
        summary_code="vee_passed",
        details={"mode": "pass_through", "source": "canonical_measurement"},
    )
    session.add(execution)
    session.flush()
    return execution, True


def ensure_processing_core_lineage(
    session: Session,
    canonical_row: CanonicalMeasurement,
    *,
    pipeline_run: PipelineRun | None = None,
    trigger_type: str = "system",
) -> InitialMeasurement:
    initial_row, _ = create_or_get_initial_measurement(session, canonical_row)

    if is_canonical_measurement_pass_through_eligible(canonical_row):
        initial_row.initial_status = "accepted"
        create_or_get_pass_through_vee_execution(
            session,
            initial_row,
            pipeline_run=pipeline_run,
            trigger_type=trigger_type,
        )

    return initial_row
