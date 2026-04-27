from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import CanonicalMeasurement, InitialMeasurement, PipelineRun
from app.services.vee import evaluate_or_get_vee_baseline


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


def ensure_processing_core_lineage(
    session: Session,
    canonical_row: CanonicalMeasurement,
    *,
    pipeline_run: PipelineRun | None = None,
    trigger_type: str = "system",
) -> InitialMeasurement:
    initial_row, _ = create_or_get_initial_measurement(session, canonical_row)

    evaluate_or_get_vee_baseline(
        session,
        initial_row,
        pipeline_run=pipeline_run,
        trigger_type=trigger_type,
    )

    return initial_row
