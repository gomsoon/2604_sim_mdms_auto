from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    CanonicalMeasurement,
    Device,
    HesEventRaw,
    HesReadRaw,
    IngestErrorLog,
    MeasuringComponent,
    PipelineRun,
    ServicePoint,
)


@dataclass(frozen=True, slots=True)
class StageStatusCard:
    title_key: str
    waiting: int
    processing: int
    completed: int
    failed: int


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    stats: dict[str, int]
    stage_cards: list[StageStatusCard]
    recent_reads: list[HesReadRaw]
    recent_exceptions: list[IngestErrorLog]


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def build_dashboard_snapshot(session: Session) -> DashboardSnapshot:
    stats = {
        "service_points": _count(session, select(func.count()).select_from(ServicePoint)),
        "devices": _count(session, select(func.count()).select_from(Device)),
        "components": _count(session, select(func.count()).select_from(MeasuringComponent)),
        "raw_reads": _count(session, select(func.count()).select_from(HesReadRaw)),
        "raw_events": _count(session, select(func.count()).select_from(HesEventRaw)),
        "canonical": _count(session, select(func.count()).select_from(CanonicalMeasurement)),
        "exceptions": _count(session, select(func.count()).select_from(IngestErrorLog)),
    }

    raw_ingest_waiting = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "raw_ingest", PipelineRun.status == "waiting"),
    )
    raw_ingest_processing = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "raw_ingest", PipelineRun.status == "processing"),
    )
    raw_ingest_completed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "raw_ingest", PipelineRun.status == "completed"),
    )
    raw_ingest_failed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "raw_ingest", PipelineRun.status == "failed"),
    )

    canonical_waiting = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "canonical", PipelineRun.status == "waiting"),
    )
    canonical_processing = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "canonical", PipelineRun.status == "processing"),
    )
    canonical_completed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "canonical", PipelineRun.status == "completed"),
    )
    canonical_failed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "canonical", PipelineRun.status == "failed"),
    )

    queue_waiting = _count(
        session,
        select(func.count()).select_from(IngestErrorLog).where(IngestErrorLog.status == "open"),
    )
    queue_processing = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "exception_reprocess", PipelineRun.status == "processing"),
    )
    queue_completed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "exception_reprocess", PipelineRun.status == "completed"),
    )
    queue_failed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "exception_reprocess", PipelineRun.status == "failed"),
    )

    stage_cards = [
        StageStatusCard(
            title_key="dashboard.stage.raw_ingest",
            waiting=raw_ingest_waiting,
            processing=raw_ingest_processing,
            completed=raw_ingest_completed,
            failed=raw_ingest_failed,
        ),
        StageStatusCard(
            title_key="dashboard.stage.canonical",
            waiting=canonical_waiting,
            processing=canonical_processing,
            completed=canonical_completed,
            failed=canonical_failed,
        ),
        StageStatusCard(
            title_key="dashboard.stage.errors",
            waiting=queue_waiting,
            processing=queue_processing,
            completed=queue_completed,
            failed=queue_failed,
        ),
    ]

    recent_reads = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(10)).all()
    recent_exceptions = session.scalars(
        select(IngestErrorLog).order_by(IngestErrorLog.id.desc()).limit(10)
    ).all()

    return DashboardSnapshot(
        stats=stats,
        stage_cards=stage_cards,
        recent_reads=recent_reads,
        recent_exceptions=recent_exceptions,
    )
