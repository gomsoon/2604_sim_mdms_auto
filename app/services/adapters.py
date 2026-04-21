from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models import AdapterDefinition, AdapterInstance, AdapterRun, AdapterWatermark
from app.services.operational_events import record_operational_event


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


@dataclass(frozen=True, slots=True)
class ScheduledAdapterEnqueueSummary:
    eligible: int
    enqueued: int
    skipped_due_to_active_run: int
    run_ids: list[int]


def list_active_adapter_definitions(session: Session) -> list[AdapterDefinition]:
    return session.scalars(
        select(AdapterDefinition)
        .where(AdapterDefinition.status == "active")
        .order_by(AdapterDefinition.display_name.asc(), AdapterDefinition.id.asc())
    ).all()


def _normalize_required_text(value: str | None, error_code: str, fallback_message: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise AdapterValidationError(error_code, fallback_message)
    return normalized


def _parse_definition_id(raw_value: str | None) -> int:
    normalized = (raw_value or "").strip()
    if not normalized:
        raise AdapterValidationError(
            "missing_adapter_definition_id",
            "Adapter definition selection is required.",
        )
    try:
        return int(normalized)
    except ValueError as exc:
        raise AdapterValidationError(
            "invalid_adapter_definition_id",
            "Adapter definition selection is invalid.",
        ) from exc


def _parse_optional_positive_int(
    raw_value: str | None, *, error_code: str, fallback_message: str
) -> int | None:
    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise AdapterValidationError(error_code, fallback_message) from exc
    if parsed <= 0:
        raise AdapterValidationError(error_code, fallback_message)
    return parsed


def _parse_masked_config(raw_value: str | None) -> dict | None:
    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise AdapterValidationError(
            "invalid_connection_config_masked",
            "Masked connection configuration must be valid JSON.",
        ) from exc
    if not isinstance(parsed, dict):
        raise AdapterValidationError(
            "invalid_connection_config_masked",
            "Masked connection configuration must be a JSON object.",
        )
    return parsed


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


def create_adapter_instance(
    session: Session,
    *,
    adapter_definition_id: str | None,
    instance_code: str | None,
    display_name: str | None,
    source_system: str | None,
    poll_interval_minutes: str | None,
    batch_size: str | None,
    landing_enabled: bool,
    secret_ref: str | None,
    connection_config_masked: str | None,
) -> AdapterInstance:
    definition_id = _parse_definition_id(adapter_definition_id)
    definition = session.get(AdapterDefinition, definition_id)
    if definition is None:
        raise AdapterValidationError(
            "adapter_definition_not_found",
            "The selected adapter definition does not exist.",
        )
    if definition.status != "active":
        raise AdapterValidationError(
            "adapter_definition_inactive",
            "The selected adapter definition is not active.",
        )

    normalized_instance_code = _normalize_required_text(
        instance_code,
        "missing_instance_code",
        "Adapter instance code is required.",
    )
    duplicate = session.scalar(
        select(AdapterInstance.id)
        .where(AdapterInstance.instance_code == normalized_instance_code)
        .limit(1)
    )
    if duplicate is not None:
        raise AdapterValidationError(
            "duplicate_instance_code",
            "An adapter instance with the same code already exists.",
        )

    normalized_display_name = _normalize_required_text(
        display_name,
        "missing_display_name",
        "Adapter display name is required.",
    )
    normalized_source_system = _normalize_required_text(
        source_system,
        "missing_source_system",
        "Source system is required.",
    )
    parsed_poll_interval = _parse_optional_positive_int(
        poll_interval_minutes,
        error_code="invalid_poll_interval_minutes",
        fallback_message="Poll interval must be a positive integer.",
    )
    if definition.delivery_mode == "poll" and parsed_poll_interval is None:
        raise AdapterValidationError(
            "missing_poll_interval_minutes",
            "Poll interval is required for polling adapter definitions.",
        )
    parsed_batch_size = _parse_optional_positive_int(
        batch_size,
        error_code="invalid_batch_size",
        fallback_message="Batch size must be a positive integer.",
    )
    parsed_masked_config = _parse_masked_config(connection_config_masked)
    normalized_secret_ref = (secret_ref or "").strip() or None

    next_run_at = None
    if definition.delivery_mode == "poll" and parsed_poll_interval is not None:
        next_run_at = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(
            minutes=parsed_poll_interval
        )

    instance = AdapterInstance(
        adapter_definition_id=definition.id,
        instance_code=normalized_instance_code,
        display_name=normalized_display_name,
        source_system=normalized_source_system,
        admin_state="enabled",
        status_reason="operator_created",
        poll_interval_minutes=parsed_poll_interval,
        batch_size=parsed_batch_size,
        next_run_at=next_run_at,
        landing_enabled=landing_enabled,
        connection_config_masked=parsed_masked_config,
        secret_ref=normalized_secret_ref,
    )
    session.add(instance)
    session.flush()
    return instance


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
    event_code = "adapter_enabled" if target_state == "enabled" else "adapter_paused"
    record_operational_event(
        session,
        event_code,
        adapter_instance=instance,
        details={"admin_state": target_state, "status_reason": instance.status_reason},
        instance_code=instance.instance_code,
    )
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
    record_operational_event(
        session,
        "adapter_run_queued",
        adapter_instance=instance,
        adapter_run=run,
        details={"trigger_type": run.trigger_type, **run.details},
        instance_code=instance.instance_code,
        trigger_type=run.trigger_type,
    )
    return run


def enqueue_scheduled_adapter_runs(
    session: Session,
    *,
    as_of: datetime | None = None,
    limit: int = 10,
) -> ScheduledAdapterEnqueueSummary:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    effective_as_of = as_of or datetime.now(timezone.utc)
    candidates = session.scalars(
        select(AdapterInstance)
        .join(AdapterInstance.adapter_definition)
        .options(selectinload(AdapterInstance.adapter_definition))
        .where(
            AdapterInstance.admin_state == "enabled",
            AdapterInstance.next_run_at.is_not(None),
            AdapterInstance.next_run_at <= effective_as_of,
            AdapterDefinition.delivery_mode == "poll",
            AdapterDefinition.status == "active",
        )
        .order_by(AdapterInstance.next_run_at.asc(), AdapterInstance.id.asc())
        .limit(limit)
    ).all()

    enqueued_runs: list[int] = []
    skipped_due_to_active_run = 0

    for instance in candidates:
        active_run = session.scalar(
            select(AdapterRun.id)
            .where(
                AdapterRun.adapter_instance_id == instance.id,
                AdapterRun.run_status.in_(("waiting", "running")),
            )
            .order_by(AdapterRun.id.desc())
            .limit(1)
        )
        if active_run is not None:
            skipped_due_to_active_run += 1
            continue

        run = AdapterRun(
            adapter_instance_id=instance.id,
            trigger_type="schedule",
            run_status="waiting",
            requested_at=effective_as_of,
            details={
                "requested_via": "scheduler",
                "scheduled_for": instance.next_run_at.isoformat()
                if instance.next_run_at is not None
                else None,
            },
        )
        session.add(run)
        session.flush()
        record_operational_event(
            session,
            "adapter_run_queued",
            adapter_instance=instance,
            adapter_run=run,
            details={"trigger_type": run.trigger_type, **run.details},
            instance_code=instance.instance_code,
            trigger_type=run.trigger_type,
        )
        enqueued_runs.append(run.id)

    return ScheduledAdapterEnqueueSummary(
        eligible=len(candidates),
        enqueued=len(enqueued_runs),
        skipped_due_to_active_run=skipped_due_to_active_run,
        run_ids=enqueued_runs,
    )
