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

    raw_read_pending = _count(
        session,
        select(func.count()).select_from(HesReadRaw).where(HesReadRaw.canonical_status == "pending"),
    )
    raw_read_mapped = _count(
        session,
        select(func.count()).select_from(HesReadRaw).where(HesReadRaw.canonical_status == "mapped"),
    )
    raw_read_failed = _count(
        session,
        select(func.count())
        .select_from(HesReadRaw)
        .where(HesReadRaw.canonical_status.in_(("duplicate", "exception"))),
    )

    raw_read_validation_errors = _count(
        session,
        select(func.count())
        .select_from(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "missing_required_fields"),
    )
    invalid_event_errors = _count(
        session,
        select(func.count())
        .select_from(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "invalid_event_payload"),
    )

    total_raw_events = stats["raw_events"]
    valid_raw_events = max(total_raw_events - invalid_event_errors, 0)

    queue_waiting = _count(
        session,
        select(func.count()).select_from(IngestErrorLog).where(IngestErrorLog.status == "open"),
    )
    queue_processing = _count(
        session,
        select(func.count()).select_from(IngestErrorLog).where(IngestErrorLog.status == "processing"),
    )
    queue_completed = _count(
        session,
        select(func.count())
        .select_from(IngestErrorLog)
        .where(IngestErrorLog.status.in_(("resolved", "completed", "closed"))),
    )
    queue_failed = _count(
        session,
        select(func.count())
        .select_from(IngestErrorLog)
        .where(IngestErrorLog.status.in_(("failed", "rejected"))),
    )

    stage_cards = [
        StageStatusCard(
            title_key="dashboard.stage.raw_ingest",
            waiting=0,
            processing=0,
            completed=stats["raw_reads"] + valid_raw_events,
            failed=raw_read_validation_errors + invalid_event_errors,
        ),
        StageStatusCard(
            title_key="dashboard.stage.canonical",
            waiting=raw_read_pending,
            processing=0,
            completed=raw_read_mapped,
            failed=raw_read_failed,
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
