from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models import CanonicalMeasurement, FinalMeasurement, HesReadRaw, IngestBatch
from app.services.pipeline import complete_pipeline_run, fail_pipeline_run, start_pipeline_run, upsert_processing_watermark


@dataclass(frozen=True, slots=True)
class FinalizationSummary:
    candidates: int
    finalized: int
    skipped_existing: int
    skipped_not_well_formed: int


def is_canonical_measurement_well_formed(row: CanonicalMeasurement) -> bool:
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


def create_or_get_final_measurement(
    session: Session, canonical_row: CanonicalMeasurement
) -> tuple[FinalMeasurement, bool]:
    if canonical_row.final_measurement is not None:
        return canonical_row.final_measurement, False

    final_row = FinalMeasurement(
        canonical_measurement=canonical_row,
        measuring_component_id=canonical_row.measuring_component_id,
        device_id=canonical_row.device_id,
        service_point_id=canonical_row.service_point_id,
        measured_at=canonical_row.measured_at,
        value=canonical_row.value,
        quality_code=canonical_row.quality_code,
        status_code=canonical_row.status_code,
        unit_of_measure=canonical_row.unit_of_measure,
        final_status="finalized",
        finalized_at=datetime.now(timezone.utc),
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

    statement: Select[tuple[CanonicalMeasurement]] = (
        select(CanonicalMeasurement)
        .join(CanonicalMeasurement.hes_read_raw)
        .join(HesReadRaw.ingest_batch)
        .options(
            joinedload(CanonicalMeasurement.hes_read_raw).joinedload(HesReadRaw.ingest_batch),
            joinedload(CanonicalMeasurement.final_measurement),
        )
    )
    if batch_id:
        statement = statement.where(IngestBatch.batch_id == batch_id)
    if meter_id:
        statement = statement.where(HesReadRaw.meter_identifier == meter_id)
    if date_from:
        statement = statement.where(CanonicalMeasurement.measured_at >= date_from)
    if date_to:
        statement = statement.where(CanonicalMeasurement.measured_at <= date_to)

    statement = statement.order_by(CanonicalMeasurement.id.asc()).limit(limit)
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
        raw_row = row.hes_read_raw
        if source_system is None and raw_row is not None:
            source_system = raw_row.source_system

        if row.final_measurement is not None:
            skipped_existing += 1
            continue

        if not is_canonical_measurement_well_formed(row):
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
