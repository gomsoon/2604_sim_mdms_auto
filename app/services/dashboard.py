from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AdapterInstance,
    AdapterRun,
    BillDeterminant,
    CanonicalMeasurement,
    Device,
    FinalMeasurement,
    HesEventRaw,
    HesReadRaw,
    IngestBatch,
    IngestErrorLog,
    MeasuringComponent,
    OperationalEvent,
    PipelineRun,
    ServicePoint,
    UsageTransaction,
    VeeReplayRequest,
)
from app.services.adapters import derive_effective_status
from app.services.adapters import derive_is_overdue, derive_is_stale


@dataclass(frozen=True, slots=True)
class CardSummaryRow:
    label_key: str
    value: object | None
    is_datetime: bool = False
    empty_key: str = "common.none"


@dataclass(frozen=True, slots=True)
class StageStatusCard:
    title_key: str
    waiting: int
    processing: int
    completed: int
    failed: int
    total_count: int | None = None
    waiting_label_key: str = "dashboard.stage.waiting"
    processing_label_key: str = "dashboard.stage.processing"
    completed_label_key: str = "dashboard.stage.completed"
    failed_label_key: str = "dashboard.stage.failed"
    waiting_value_class: str = ""
    processing_value_class: str = ""
    completed_value_class: str = "text-success"
    failed_value_class: str = "text-danger"
    detail_endpoint: str | None = None
    detail_link_key: str | None = None
    summary_rows: list[CardSummaryRow] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    stats: dict[str, int]
    stage_cards: list[StageStatusCard]
    recent_reads: list[HesReadRaw]
    recent_exceptions: list[IngestErrorLog]
    open_alerts: list[OperationalEvent]
    recent_events: list[OperationalEvent]
    recent_recalculated_usage: list[UsageTransaction]
    recent_bill_determinants: list[BillDeterminant]
    recent_vee_replay_requests: list[VeeReplayRequest]


def _count(session: Session, statement) -> int:
    return int(session.scalar(statement) or 0)


def _load_latest_adapter_runs(session: Session, adapter_instance_ids: list[int]) -> dict[int, AdapterRun]:
    if not adapter_instance_ids:
        return {}

    runs = session.scalars(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id.in_(adapter_instance_ids))
        .order_by(AdapterRun.adapter_instance_id.asc(), AdapterRun.id.desc())
    ).all()

    latest_runs: dict[int, AdapterRun] = {}
    for run in runs:
        latest_runs.setdefault(run.adapter_instance_id, run)
    return latest_runs


def _usage_recalculated_after_vee_filter():
    return (
        UsageTransaction.details["provenance"]["trigger_source"].as_string() == "re_vee"
    )


def _bill_determinant_revised_filter():
    return BillDeterminant.is_current.is_(True) & (BillDeterminant.revision_number > 1)


def build_dashboard_snapshot(session: Session) -> DashboardSnapshot:
    stats = {
        "service_points": _count(session, select(func.count()).select_from(ServicePoint)),
        "devices": _count(session, select(func.count()).select_from(Device)),
        "components": _count(session, select(func.count()).select_from(MeasuringComponent)),
        "raw_reads": _count(session, select(func.count()).select_from(HesReadRaw)),
        "raw_events": _count(session, select(func.count()).select_from(HesEventRaw)),
        "canonical": _count(session, select(func.count()).select_from(CanonicalMeasurement)),
        "final": _count(session, select(func.count()).select_from(FinalMeasurement)),
        "exceptions": _count(session, select(func.count()).select_from(IngestErrorLog)),
        "open_alerts": _count(
            session,
            select(func.count())
            .select_from(OperationalEvent)
            .where(
                OperationalEvent.is_alert.is_(True),
                OperationalEvent.alert_status.in_(("open", "acknowledged")),
            ),
        ),
    }

    adapter_instances = session.scalars(
        select(AdapterInstance)
        .options(selectinload(AdapterInstance.adapter_definition))
        .order_by(AdapterInstance.id.asc())
    ).all()
    latest_adapter_runs = _load_latest_adapter_runs(session, [row.id for row in adapter_instances])
    integration_ready = 0
    integration_running = 0
    integration_paused = 0
    integration_error = 0
    integration_overdue = 0
    integration_stale = 0
    for instance in adapter_instances:
        latest_run = latest_adapter_runs.get(instance.id)
        effective_status = derive_effective_status(instance, latest_run)
        if effective_status == "ready":
            integration_ready += 1
        elif effective_status == "running":
            integration_running += 1
        elif effective_status == "paused":
            integration_paused += 1
        elif effective_status == "error":
            integration_error += 1
        if derive_is_overdue(instance, latest_run):
            integration_overdue += 1
        if derive_is_stale(instance, latest_run):
            integration_stale += 1

    integration_last_success = session.scalar(select(func.max(AdapterInstance.last_success_at)))
    integration_pending_runs = _count(
        session,
        select(func.count()).select_from(AdapterRun).where(AdapterRun.run_status == "waiting"),
    )

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

    final_waiting = _count(
        session,
        select(func.count())
        .select_from(CanonicalMeasurement)
        .outerjoin(CanonicalMeasurement.final_measurement)
        .where(FinalMeasurement.id.is_(None))
    )
    final_processing = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "finalization", PipelineRun.status == "processing"),
    )
    final_completed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "finalization", PipelineRun.status == "completed"),
    )
    final_failed = _count(
        session,
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.pipeline_name == "finalization", PipelineRun.status == "failed"),
    )
    usage_complete = _count(
        session,
        select(func.count())
        .select_from(UsageTransaction)
        .where(UsageTransaction.calculation_status == "complete"),
    )
    usage_partial = _count(
        session,
        select(func.count())
        .select_from(UsageTransaction)
        .where(UsageTransaction.calculation_status == "partial"),
    )
    usage_blocked = _count(
        session,
        select(func.count())
        .select_from(UsageTransaction)
        .where(UsageTransaction.calculation_status == "blocked"),
    )
    usage_recalculated = _count(
        session,
        select(func.count())
        .select_from(UsageTransaction)
        .where(_usage_recalculated_after_vee_filter()),
    )
    latest_usage_calculated_at = session.scalar(select(func.max(UsageTransaction.calculated_at)))
    latest_usage_recalculated_at = session.scalar(
        select(func.max(UsageTransaction.calculated_at)).where(_usage_recalculated_after_vee_filter())
    )
    bill_determinant_complete = _count(
        session,
        select(func.count())
        .select_from(BillDeterminant)
        .where(
            BillDeterminant.is_current.is_(True),
            BillDeterminant.calculation_status == "complete",
        ),
    )
    bill_determinant_partial = _count(
        session,
        select(func.count())
        .select_from(BillDeterminant)
        .where(
            BillDeterminant.is_current.is_(True),
            BillDeterminant.calculation_status == "partial",
        ),
    )
    bill_determinant_blocked = _count(
        session,
        select(func.count())
        .select_from(BillDeterminant)
        .where(
            BillDeterminant.is_current.is_(True),
            BillDeterminant.calculation_status == "blocked",
        ),
    )
    bill_determinant_revised = _count(
        session,
        select(func.count())
        .select_from(BillDeterminant)
        .where(_bill_determinant_revised_filter()),
    )
    latest_bill_determinant_calculated_at = session.scalar(
        select(func.max(BillDeterminant.calculated_at)).where(BillDeterminant.is_current.is_(True))
    )
    latest_bill_determinant_revised_at = session.scalar(
        select(func.max(BillDeterminant.calculated_at)).where(_bill_determinant_revised_filter())
    )
    vee_replay_queued = _count(
        session,
        select(func.count())
        .select_from(VeeReplayRequest)
        .where(VeeReplayRequest.status == "queued"),
    )
    vee_replay_processing = _count(
        session,
        select(func.count())
        .select_from(VeeReplayRequest)
        .where(VeeReplayRequest.status == "processing"),
    )
    vee_replay_completed = _count(
        session,
        select(func.count())
        .select_from(VeeReplayRequest)
        .where(VeeReplayRequest.status == "completed"),
    )
    vee_replay_failed = _count(
        session,
        select(func.count())
        .select_from(VeeReplayRequest)
        .where(VeeReplayRequest.status == "failed"),
    )
    vee_replay_cancelled = _count(
        session,
        select(func.count())
        .select_from(VeeReplayRequest)
        .where(VeeReplayRequest.status == "cancelled"),
    )
    latest_vee_replay_requested_at = session.scalar(select(func.max(VeeReplayRequest.created_at)))
    latest_vee_replay_completed_at = session.scalar(select(func.max(VeeReplayRequest.completed_at)))

    stage_cards = [
        StageStatusCard(
            title_key="dashboard.stage.integration",
            waiting=integration_ready,
            processing=integration_running,
            completed=integration_paused,
            failed=integration_error,
            waiting_label_key="adapter_status.ready",
            processing_label_key="adapter_status.running",
            completed_label_key="adapter_status.paused",
            failed_label_key="adapter_status.error",
            processing_value_class="text-primary",
            completed_value_class="text-warning",
            failed_value_class="text-danger",
            detail_endpoint="web.adapters",
            detail_link_key="dashboard.view_adapters",
            summary_rows=[
                CardSummaryRow(
                    label_key="dashboard.integration.last_success",
                    value=integration_last_success,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.integration.pending_runs",
                    value=integration_pending_runs,
                ),
                CardSummaryRow(
                    label_key="dashboard.integration.overdue_adapters",
                    value=integration_overdue,
                ),
                CardSummaryRow(
                    label_key="dashboard.integration.stale_adapters",
                    value=integration_stale,
                ),
            ],
        ),
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
        StageStatusCard(
            title_key="dashboard.stage.final",
            waiting=final_waiting,
            processing=final_processing,
            completed=final_completed,
            failed=final_failed,
        ),
        StageStatusCard(
            title_key="dashboard.stage.usage",
            waiting=usage_complete,
            processing=usage_partial,
            completed=usage_blocked,
            failed=usage_recalculated,
            total_count=usage_complete + usage_partial + usage_blocked,
            waiting_label_key="usage.calculation_status.complete",
            processing_label_key="usage.calculation_status.partial",
            completed_label_key="usage.calculation_status.blocked",
            failed_label_key="dashboard.usage.recalculated",
            waiting_value_class="text-success",
            processing_value_class="text-warning",
            completed_value_class="text-danger",
            failed_value_class="text-primary",
            detail_endpoint="web.usage_transactions",
            detail_link_key="dashboard.view_usage",
            summary_rows=[
                CardSummaryRow(
                    label_key="dashboard.usage.last_calculated",
                    value=latest_usage_calculated_at,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.usage.last_recalculated",
                    value=latest_usage_recalculated_at,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.usage.partial_or_blocked",
                    value=usage_partial + usage_blocked,
                ),
            ],
        ),
        StageStatusCard(
            title_key="dashboard.stage.bill_determinant",
            waiting=bill_determinant_complete,
            processing=bill_determinant_partial,
            completed=bill_determinant_blocked,
            failed=bill_determinant_revised,
            total_count=bill_determinant_complete + bill_determinant_partial + bill_determinant_blocked,
            waiting_label_key="usage.calculation_status.complete",
            processing_label_key="usage.calculation_status.partial",
            completed_label_key="usage.calculation_status.blocked",
            failed_label_key="dashboard.bill_determinant.revised",
            waiting_value_class="text-success",
            processing_value_class="text-warning",
            completed_value_class="text-danger",
            failed_value_class="text-primary",
            detail_endpoint="web.bill_determinants",
            detail_link_key="dashboard.view_bill_determinants",
            summary_rows=[
                CardSummaryRow(
                    label_key="dashboard.bill_determinant.last_calculated",
                    value=latest_bill_determinant_calculated_at,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.bill_determinant.last_revised",
                    value=latest_bill_determinant_revised_at,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.bill_determinant.partial_or_blocked",
                    value=bill_determinant_partial + bill_determinant_blocked,
                ),
            ],
        ),
        StageStatusCard(
            title_key="dashboard.stage.vee_replay",
            waiting=vee_replay_queued,
            processing=vee_replay_processing,
            completed=vee_replay_completed,
            failed=vee_replay_failed,
            detail_endpoint="web.vee_replay_requests",
            detail_link_key="dashboard.view_vee_replay_requests",
            summary_rows=[
                CardSummaryRow(
                    label_key="dashboard.vee_replay.last_requested",
                    value=latest_vee_replay_requested_at,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.vee_replay.last_completed",
                    value=latest_vee_replay_completed_at,
                    is_datetime=True,
                ),
                CardSummaryRow(
                    label_key="dashboard.vee_replay.cancelled",
                    value=vee_replay_cancelled,
                ),
            ],
        ),
    ]

    recent_reads = session.scalars(select(HesReadRaw).order_by(HesReadRaw.id.desc()).limit(10)).all()
    recent_exceptions = session.scalars(
        select(IngestErrorLog).order_by(IngestErrorLog.id.desc()).limit(10)
    ).all()
    open_alerts = session.scalars(
        select(OperationalEvent)
        .where(
            OperationalEvent.is_alert.is_(True),
            OperationalEvent.alert_status.in_(("open", "acknowledged")),
        )
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(5)
    ).all()
    recent_events = session.scalars(
        select(OperationalEvent)
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(12)
    ).all()
    recent_recalculated_usage = session.scalars(
        select(UsageTransaction)
        .options(
            selectinload(UsageTransaction.service_point),
            selectinload(UsageTransaction.measuring_component),
            selectinload(UsageTransaction.device),
        )
        .where(_usage_recalculated_after_vee_filter())
        .order_by(UsageTransaction.calculated_at.desc(), UsageTransaction.id.desc())
        .limit(5)
    ).all()
    recent_bill_determinants = session.scalars(
        select(BillDeterminant)
        .options(
            selectinload(BillDeterminant.service_point),
            selectinload(BillDeterminant.measuring_component),
            selectinload(BillDeterminant.device),
        )
        .where(BillDeterminant.is_current.is_(True))
        .order_by(BillDeterminant.calculated_at.desc(), BillDeterminant.id.desc())
        .limit(5)
    ).all()
    recent_vee_replay_requests = session.scalars(
        select(VeeReplayRequest)
        .options(
            selectinload(VeeReplayRequest.hes_system),
            selectinload(VeeReplayRequest.ingest_batch).selectinload(IngestBatch.hes_system),
        )
        .order_by(VeeReplayRequest.updated_at.desc(), VeeReplayRequest.id.desc())
        .limit(5)
    ).all()

    return DashboardSnapshot(
        stats=stats,
        stage_cards=stage_cards,
        recent_reads=recent_reads,
        recent_exceptions=recent_exceptions,
        open_alerts=open_alerts,
        recent_events=recent_events,
        recent_recalculated_usage=recent_recalculated_usage,
        recent_bill_determinants=recent_bill_determinants,
        recent_vee_replay_requests=recent_vee_replay_requests,
    )
