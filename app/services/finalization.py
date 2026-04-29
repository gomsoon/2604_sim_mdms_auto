from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CanonicalMeasurement,
    FinalMeasurement,
    HesReadRaw,
    IngestBatch,
    InitialMeasurement,
)
from app.services.pipeline import (
    complete_pipeline_run,
    fail_pipeline_run,
    start_pipeline_run,
    upsert_processing_watermark,
)
from app.services.processing_core import is_canonical_measurement_pass_through_eligible
from app.services.vee import has_active_blocking_vee_exception


@dataclass(frozen=True, slots=True)
class FinalizationSummary:
    candidates: int
    finalized: int
    skipped_existing: int
    skipped_not_well_formed: int


def is_initial_measurement_finalizable(row: InitialMeasurement) -> bool:
    canonical_row = row.canonical_measurement
    if canonical_row is None or row.initial_status != "accepted":
        return False

    raw_row = canonical_row.hes_read_raw
    return bool(
        raw_row is not None
        and raw_row.canonical_status == "mapped"
        and not raw_row.is_duplicate
        and is_canonical_measurement_pass_through_eligible(canonical_row)
        and not has_active_blocking_vee_exception(row)
    )


def create_or_get_final_measurement(
    session: Session, initial_row: InitialMeasurement
) -> tuple[FinalMeasurement, bool]:
    if initial_row.final_measurement is not None:
        return initial_row.final_measurement, False

    canonical_row = initial_row.canonical_measurement
    if canonical_row is None:
        raise ValueError("initial_measurement must link to canonical_measurement")

    if canonical_row.final_measurement is not None:
        final_row = canonical_row.final_measurement
        if final_row.initial_measurement_id is None:
            final_row.initial_measurement = initial_row
            session.flush()
        return final_row, False

    final_row = FinalMeasurement(
        initial_measurement=initial_row,
        canonical_measurement=canonical_row,
        measuring_component_id=initial_row.measuring_component_id,
        device_id=initial_row.device_id,
        service_point_id=initial_row.service_point_id,
        measured_at=initial_row.measured_at,
        value=initial_row.value,
        quality_code=initial_row.quality_code,
        status_code=initial_row.status_code,
        unit_of_measure=initial_row.unit_of_measure,
        final_status="finalized",
        finalized_at=datetime.now(timezone.utc),
        revision_number=1,
        revision_reason_code=None,
        is_current=True,
    )
    session.add(final_row)
    session.flush()
    return final_row, True


def finalize_canonical_measurements(
    session: Session,
    *,
    batch_id: str | None = None,
    meter_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    trigger_type: str = "manual",
) -> FinalizationSummary:
    ingest_batch = None
    if batch_id:
        ingest_batch = session.scalar(
            select(IngestBatch).where(IngestBatch.batch_id == batch_id).limit(1)
        )

    statement: Select[tuple[InitialMeasurement]] = (
        select(InitialMeasurement)
        .join(InitialMeasurement.canonical_measurement)
        .join(CanonicalMeasurement.hes_read_raw)
        .join(HesReadRaw.ingest_batch)
        .options(
            joinedload(InitialMeasurement.canonical_measurement)
            .joinedload(CanonicalMeasurement.hes_read_raw)
            .joinedload(HesReadRaw.ingest_batch),
            joinedload(InitialMeasurement.canonical_measurement).joinedload(
                CanonicalMeasurement.final_measurement
            ),
            joinedload(InitialMeasurement.final_measurement),
            joinedload(InitialMeasurement.vee_exceptions),
        )
    )
    if batch_id:
        statement = statement.where(IngestBatch.batch_id == batch_id)
    if meter_id:
        statement = statement.where(HesReadRaw.meter_identifier == meter_id)
    if date_from:
        statement = statement.where(InitialMeasurement.measured_at >= date_from)
    if date_to:
        statement = statement.where(InitialMeasurement.measured_at <= date_to)

    statement = statement.order_by(InitialMeasurement.id.asc()).limit(limit)
    rows = session.execute(statement).scalars().unique().all()

    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="finalization",
        trigger_type=trigger_type,
        ingest_batch=ingest_batch,
        details={
            "batch_id": batch_id,
            "meter_id": meter_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "limit": limit,
        },
    )

    candidates = 0
    finalized = 0
    skipped_existing = 0
    skipped_not_well_formed = 0
    finalized_at_values: list[datetime] = []
    source_system = ingest_batch.source_system if ingest_batch is not None else None

    for row in rows:
        candidates += 1
        canonical_row = row.canonical_measurement
        raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
        if source_system is None and raw_row is not None:
            source_system = raw_row.source_system

        if row.final_measurement is not None or (
            canonical_row is not None and canonical_row.final_measurement is not None
        ):
            skipped_existing += 1
            continue

        if not is_initial_measurement_finalizable(row):
            skipped_not_well_formed += 1
            continue

        final_row, created = create_or_get_final_measurement(session, row)
        if created:
            finalized += 1
            finalized_at_values.append(final_row.finalized_at)
        else:
            skipped_existing += 1

    summary = FinalizationSummary(
        candidates=candidates,
        finalized=finalized,
        skipped_existing=skipped_existing,
        skipped_not_well_formed=skipped_not_well_formed,
    )
    details = {
        **pipeline_run.details,
        "candidates": summary.candidates,
        "finalized": summary.finalized,
        "skipped_existing": summary.skipped_existing,
        "skipped_not_well_formed": summary.skipped_not_well_formed,
    }

    if finalized_at_values:
        upsert_processing_watermark(
            session,
            pipeline_name="finalization",
            source_system=source_system,
            record_type="final_measurement",
            last_processed_at=max(finalized_at_values),
            details=details,
        )

    if summary.skipped_not_well_formed > 0:
        fail_pipeline_run(
            pipeline_run,
            result_code="finalization_completed_with_skips",
            details=details,
        )
    elif summary.finalized > 0:
        complete_pipeline_run(
            pipeline_run,
            result_code="finalization_completed",
            details=details,
        )
    else:
        complete_pipeline_run(
            pipeline_run,
            result_code="finalization_noop",
            details=details,
        )

    return summary
