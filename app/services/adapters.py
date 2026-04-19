from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models import AdapterInstance, AdapterRun, AdapterWatermark


@dataclass(slots=True)
class AdapterValidationError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class AdapterInstanceSnapshot:
    instance: AdapterInstance
    effective_status: str
    latest_run: AdapterRun | None


@dataclass(frozen=True, slots=True)
class AdapterInstanceDetail:
    snapshot: AdapterInstanceSnapshot
    recent_runs: list[AdapterRun]
    watermarks: list[AdapterWatermark]


def _load_latest_runs(
    session: Session, adapter_instance_ids: Sequence[int]
) -> dict[int, AdapterRun]:
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


def derive_effective_status(
    instance: AdapterInstance, latest_run: AdapterRun | None = None
) -> str:
    if instance.admin_state == "retired":
        return "retired"
    if instance.admin_state == "paused":
        return "paused"
    if latest_run is not None and latest_run.run_status == "running":
        return "running"
    if instance.last_failure_at is not None and (
        instance.last_success_at is None or instance.last_failure_at >= instance.last_success_at
    ):
        return "error"
    return "ready"


def list_adapter_instances(session: Session, *, limit: int = 100) -> list[AdapterInstanceSnapshot]:
    statement: Select[tuple[AdapterInstance]] = (
        select(AdapterInstance)
        .options(selectinload(AdapterInstance.adapter_definition))
        .order_by(AdapterInstance.id.desc())
        .limit(limit)
    )
    instances = session.scalars(statement).all()
    latest_runs = _load_latest_runs(session, [row.id for row in instances])

    return [
        AdapterInstanceSnapshot(
            instance=row,
            effective_status=derive_effective_status(row, latest_runs.get(row.id)),
            latest_run=latest_runs.get(row.id),
        )
        for row in instances
    ]


def get_adapter_instance_detail(
    session: Session, adapter_instance_id: int
) -> AdapterInstanceDetail | None:
    instance = session.scalar(
        select(AdapterInstance)
        .options(
            selectinload(AdapterInstance.adapter_definition),
            selectinload(AdapterInstance.adapter_watermarks),
        )
        .where(AdapterInstance.id == adapter_instance_id)
        .limit(1)
    )
    if instance is None:
        return None

    recent_runs = session.scalars(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance.id)
        .order_by(AdapterRun.id.desc())
        .limit(20)
    ).all()
    latest_run = recent_runs[0] if recent_runs else None

    return AdapterInstanceDetail(
        snapshot=AdapterInstanceSnapshot(
            instance=instance,
            effective_status=derive_effective_status(instance, latest_run),
            latest_run=latest_run,
        ),
        recent_runs=recent_runs,
        watermarks=sorted(instance.adapter_watermarks, key=lambda row: row.id, reverse=True),
    )


def update_adapter_admin_state(
    session: Session, instance: AdapterInstance, target_state: str
) -> AdapterInstance:
    current_state = instance.admin_state
    if current_state == target_state:
        return instance

    allowed_transitions = {
        "enabled": {"paused", "retired"},
        "paused": {"enabled", "retired"},
        "retired": set(),
    }
    if target_state not in allowed_transitions.get(current_state, set()):
        raise AdapterValidationError(
            "invalid_admin_state_transition",
            "The requested adapter state transition is not allowed.",
        )

    instance.admin_state = target_state
    instance.status_reason = f"manual_{target_state}"
    session.flush()
    return instance


def queue_adapter_run_once(session: Session, instance: AdapterInstance) -> AdapterRun:
    if instance.admin_state == "retired":
        raise AdapterValidationError(
            "retired_instance_not_runnable",
            "A retired adapter instance cannot be run again.",
        )

    active_run = session.scalar(
        select(AdapterRun)
        .where(
            AdapterRun.adapter_instance_id == instance.id,
            AdapterRun.run_status.in_(("waiting", "running")),
        )
        .order_by(AdapterRun.id.desc())
        .limit(1)
    )
    if active_run is not None:
        raise AdapterValidationError(
            "run_already_pending",
            "A waiting or running adapter execution already exists for this instance.",
        )

    run = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="manual",
        run_status="waiting",
        requested_at=datetime.now(timezone.utc),
        details={"requested_via": "operator_ui"},
    )
    session.add(run)
    session.flush()
    return run
