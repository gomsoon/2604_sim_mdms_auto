from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, or_, select
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


def _get_current_final_measurement(
    session: Session,
    initial_row: InitialMeasurement,
) -> FinalMeasurement | None:
    canonical_row = initial_row.canonical_measurement
    if canonical_row is None:
        return None

    return session.scalar(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.is_current.is_(True),
            or_(
                FinalMeasurement.initial_measurement_id == initial_row.id,
                (
                    FinalMeasurement.initial_measurement_id.is_(None)
                    & (FinalMeasurement.canonical_measurement_id == canonical_row.id)
                ),
            ),
        )
        .order_by(FinalMeasurement.revision_number.desc(), FinalMeasurement.id.desc())
        .limit(1)
    )


def _final_measurement_matches_initial(
    final_row: FinalMeasurement,
    initial_row: InitialMeasurement,
) -> bool:
    return (
        final_row.measuring_component_id == initial_row.measuring_component_id
        and final_row.device_id == initial_row.device_id
        and final_row.service_point_id == initial_row.service_point_id
        and final_row.measured_at == initial_row.measured_at
        and final_row.value == initial_row.value
        and final_row.quality_code == initial_row.quality_code
        and final_row.status_code == initial_row.status_code
        and final_row.unit_of_measure == initial_row.unit_of_measure
    )


def create_or_get_final_measurement(
    session: Session,
    initial_row: InitialMeasurement,
    *,
    revision_reason_code: str | None = None,
) -> tuple[FinalMeasurement, bool]:
    canonical_row = initial_row.canonical_measurement
    if canonical_row is None:
        raise ValueError("initial_measurement must link to canonical_measurement")

    current_final = _get_current_final_measurement(session, initial_row)
    if current_final is not None:
        if current_final.initial_measurement_id is None:
            current_final.initial_measurement = initial_row
            session.flush()
        if _final_measurement_matches_initial(current_final, initial_row):
            return current_final, False

        current_final.final_status = "superseded"
        current_final.is_current = False
        session.flush()

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
        revision_number=1 if current_final is None else current_final.revision_number + 1,
        revision_reason_code=None if current_final is None else revision_reason_code or "re_finalized",
        is_current=True,
        supersedes_final_measurement=current_final,
    )
    session.add(final_row)
    session.flush()
    session.expire(initial_row, ["final_measurement", "final_measurements"])
    session.expire(canonical_row, ["final_measurement", "final_measurements"])
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
    revision_reason_code: str | None = None,
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

        if not is_initial_measurement_finalizable(row):
            skipped_not_well_formed += 1
            continue

        final_row, created = create_or_get_final_measurement(
            session,
            row,
            revision_reason_code=revision_reason_code,
        )
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
