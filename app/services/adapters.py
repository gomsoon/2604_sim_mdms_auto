from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AdapterDefinition,
    AdapterInstance,
    AdapterRun,
    AdapterWatermark,
    HesSystem,
    OperationalEvent,
)
from app.services.hes_systems import ensure_hes_system
from app.services.operational_events import close_operational_alerts, record_operational_event


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
    is_overdue: bool
    is_stale: bool


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


@dataclass(frozen=True, slots=True)
class AdapterHealthAlertSyncSummary:
    checked: int
    overdue_opened: int
    overdue_closed: int
    stale_opened: int
    stale_closed: int


@dataclass(frozen=True, slots=True)
class AdapterHealthAlertRule:
    event_code: str
    detector: Callable[[AdapterInstance, AdapterRun | None, datetime], bool]
    details_builder: Callable[[AdapterInstance, AdapterRun | None], dict[str, Any]]
    message_kwargs_builder: Callable[[AdapterInstance, AdapterRun | None], dict[str, Any]]
    close_memo: str


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


def _parse_optional_hes_system_id(raw_value: str | None) -> int | None:
    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise AdapterValidationError(
            "invalid_hes_system_id",
            "HES system selection is invalid.",
        ) from exc
    if parsed <= 0:
        raise AdapterValidationError(
            "invalid_hes_system_id",
            "HES system selection is invalid.",
        )
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


def _derive_stale_threshold(instance: AdapterInstance) -> timedelta:
    if instance.adapter_definition.delivery_mode == "poll" and instance.poll_interval_minutes:
        return timedelta(minutes=max(instance.poll_interval_minutes * 3, 15))
    return timedelta(minutes=15)


def _derive_last_activity_at(
    instance: AdapterInstance, latest_run: AdapterRun | None = None
) -> datetime | None:
    if instance.last_heartbeat_at is not None:
        return instance.last_heartbeat_at

    candidates = [
        instance.last_success_at,
        instance.last_failure_at,
    ]
    if latest_run is not None:
        candidates.extend(
            [
                latest_run.completed_at,
                latest_run.started_at,
                latest_run.requested_at,
            ]
        )

    values = [value for value in candidates if value is not None]
    if not values:
        return None
    return max(values)


def derive_is_overdue(
    instance: AdapterInstance,
    latest_run: AdapterRun | None = None,
    *,
    as_of: datetime | None = None,
) -> bool:
    effective_as_of = as_of or datetime.now(timezone.utc)
    if instance.admin_state != "enabled":
        return False
    if instance.adapter_definition.delivery_mode != "poll":
        return False
    if instance.next_run_at is None:
        return False
    if latest_run is not None and latest_run.run_status == "running":
        return False
    return instance.next_run_at <= effective_as_of


def derive_is_stale(
    instance: AdapterInstance,
    latest_run: AdapterRun | None = None,
    *,
    as_of: datetime | None = None,
) -> bool:
    effective_as_of = as_of or datetime.now(timezone.utc)
    if instance.admin_state != "enabled":
        return False
    if latest_run is not None and latest_run.run_status == "running":
        return False

    threshold = _derive_stale_threshold(instance)
    last_activity_at = _derive_last_activity_at(instance, latest_run)
    if last_activity_at is not None:
        return last_activity_at + threshold <= effective_as_of
    if instance.next_run_at is not None:
        return instance.next_run_at + threshold <= effective_as_of
    return False


def _detect_adapter_overdue(
    instance: AdapterInstance, latest_run: AdapterRun | None, as_of: datetime
) -> bool:
    return derive_is_overdue(instance, latest_run, as_of=as_of)


def _detect_adapter_stale(
    instance: AdapterInstance, latest_run: AdapterRun | None, as_of: datetime
) -> bool:
    return derive_is_stale(instance, latest_run, as_of=as_of)


def _serialize_optional_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _format_optional_timestamp(value: datetime | None) -> str:
    return _serialize_optional_timestamp(value) or "-"


def _build_overdue_alert_details(
    instance: AdapterInstance, latest_run: AdapterRun | None
) -> dict[str, Any]:
    return {
        "next_run_at": _serialize_optional_timestamp(instance.next_run_at),
        "latest_run_status": latest_run.run_status if latest_run is not None else None,
    }


def _build_overdue_alert_message_kwargs(
    instance: AdapterInstance, latest_run: AdapterRun | None
) -> dict[str, Any]:
    del latest_run
    return {
        "instance_code": instance.instance_code,
        "next_run_at": _format_optional_timestamp(instance.next_run_at),
    }


def _build_stale_alert_details(
    instance: AdapterInstance, latest_run: AdapterRun | None
) -> dict[str, Any]:
    return {
        "last_heartbeat_at": _serialize_optional_timestamp(instance.last_heartbeat_at),
        "latest_run_status": latest_run.run_status if latest_run is not None else None,
    }


def _build_stale_alert_message_kwargs(
    instance: AdapterInstance, latest_run: AdapterRun | None
) -> dict[str, Any]:
    del latest_run
    return {
        "instance_code": instance.instance_code,
        "last_heartbeat_at": _format_optional_timestamp(instance.last_heartbeat_at),
    }


ADAPTER_HEALTH_ALERT_RULES: tuple[AdapterHealthAlertRule, ...] = (
    AdapterHealthAlertRule(
        event_code="adapter_overdue_detected",
        detector=_detect_adapter_overdue,
        details_builder=_build_overdue_alert_details,
        message_kwargs_builder=_build_overdue_alert_message_kwargs,
        close_memo="Closed automatically because the adapter is no longer overdue.",
    ),
    AdapterHealthAlertRule(
        event_code="adapter_stale_detected",
        detector=_detect_adapter_stale,
        details_builder=_build_stale_alert_details,
        message_kwargs_builder=_build_stale_alert_message_kwargs,
        close_memo="Closed automatically because the adapter is no longer stale.",
    ),
)


def sync_adapter_health_alerts(
    session: Session,
    *,
    adapter_instance_ids: Sequence[int] | None = None,
    as_of: datetime | None = None,
) -> AdapterHealthAlertSyncSummary:
    effective_as_of = as_of or datetime.now(timezone.utc)

    statement: Select[tuple[AdapterInstance]] = (
        select(AdapterInstance)
        .join(AdapterInstance.adapter_definition)
        .options(selectinload(AdapterInstance.adapter_definition))
        .order_by(AdapterInstance.id.asc())
    )
    if adapter_instance_ids:
        statement = statement.where(AdapterInstance.id.in_(adapter_instance_ids))

    instances = session.scalars(statement).all()
    latest_runs = _load_latest_runs(session, [row.id for row in instances])
    alert_event_codes = tuple(rule.event_code for rule in ADAPTER_HEALTH_ALERT_RULES)

    open_alerts_statement = select(OperationalEvent).where(
        OperationalEvent.is_alert.is_(True),
        OperationalEvent.event_code.in_(alert_event_codes),
        OperationalEvent.alert_status.in_(("open", "acknowledged")),
    )
    if adapter_instance_ids:
        open_alerts_statement = open_alerts_statement.where(
            OperationalEvent.adapter_instance_id.in_(adapter_instance_ids)
        )
    open_alerts = session.scalars(open_alerts_statement).all()
    open_alert_keys = {(row.event_code, row.adapter_instance_id) for row in open_alerts}

    opened_counts = {rule.event_code: 0 for rule in ADAPTER_HEALTH_ALERT_RULES}
    closed_counts = {rule.event_code: 0 for rule in ADAPTER_HEALTH_ALERT_RULES}

    for instance in instances:
        latest_run = latest_runs.get(instance.id)
        for rule in ADAPTER_HEALTH_ALERT_RULES:
            alert_key = (rule.event_code, instance.id)
            is_active = rule.detector(instance, latest_run, effective_as_of)

            if is_active:
                if alert_key not in open_alert_keys:
                    record_operational_event(
                        session,
                        rule.event_code,
                        occurred_at=effective_as_of,
                        adapter_instance=instance,
                        details=rule.details_builder(instance, latest_run),
                        **rule.message_kwargs_builder(instance, latest_run),
                    )
                    open_alert_keys.add(alert_key)
                    opened_counts[rule.event_code] += 1
                continue

            closed_count = close_operational_alerts(
                session,
                event_code=rule.event_code,
                adapter_instance_id=instance.id,
                closed_at=effective_as_of,
                operator_memo=rule.close_memo,
            )
            if closed_count:
                open_alert_keys.discard(alert_key)
            closed_counts[rule.event_code] += closed_count

    return AdapterHealthAlertSyncSummary(
        checked=len(instances),
        overdue_opened=opened_counts["adapter_overdue_detected"],
        overdue_closed=closed_counts["adapter_overdue_detected"],
        stale_opened=opened_counts["adapter_stale_detected"],
        stale_closed=closed_counts["adapter_stale_detected"],
    )


def list_adapter_instances(
    session: Session, *, limit: int = 100, hes_system_id: int | None = None
) -> list[AdapterInstanceSnapshot]:
    statement: Select[tuple[AdapterInstance]] = (
        select(AdapterInstance)
        .options(
            selectinload(AdapterInstance.adapter_definition),
            selectinload(AdapterInstance.hes_system),
        )
    )
    if hes_system_id is not None:
        statement = statement.where(AdapterInstance.hes_system_id == hes_system_id)
    statement = statement.order_by(AdapterInstance.id.desc()).limit(limit)
    instances = session.scalars(statement).all()
    latest_runs = _load_latest_runs(session, [row.id for row in instances])

    return [
        AdapterInstanceSnapshot(
            instance=row,
            effective_status=derive_effective_status(row, latest_runs.get(row.id)),
            latest_run=latest_runs.get(row.id),
            is_overdue=derive_is_overdue(row, latest_runs.get(row.id)),
            is_stale=derive_is_stale(row, latest_runs.get(row.id)),
        )
        for row in instances
    ]


def get_adapter_instance_detail(
    session: Session, adapter_instance_id: int
) -> AdapterInstanceDetail | None:
    instance = session.scalar(
        select(AdapterInstance)
        .options(
            selectinload(AdapterInstance.hes_system),
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
            is_overdue=derive_is_overdue(instance, latest_run),
            is_stale=derive_is_stale(instance, latest_run),
        ),
        recent_runs=recent_runs,
        watermarks=sorted(instance.adapter_watermarks, key=lambda row: row.id, reverse=True),
    )


def create_adapter_instance(
    session: Session,
    *,
    adapter_definition_id: str | None,
    hes_system_id: str | None = None,
    instance_code: str | None,
    display_name: str | None,
    source_system: str | None,
    poll_interval_minutes: str | None,
    batch_size: str | None,
    landing_enabled: bool,
    secret_ref: str | None,
    connection_config_masked: str | None,
    created_by_user_account_id: int | None = None,
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
    parsed_hes_system_id = _parse_optional_hes_system_id(hes_system_id)
    selected_hes_system: HesSystem | None = None
    normalized_source_system: str | None = (source_system or "").strip() or None
    if parsed_hes_system_id is not None:
        selected_hes_system = session.get(HesSystem, parsed_hes_system_id)
        if selected_hes_system is None:
            raise AdapterValidationError(
                "hes_system_not_found",
                "The selected HES system does not exist.",
            )
        if normalized_source_system and normalized_source_system != selected_hes_system.hes_code:
            raise AdapterValidationError(
                "source_system_hes_mismatch",
                "Source system must match the selected HES code.",
            )
        normalized_source_system = selected_hes_system.hes_code
    else:
        normalized_source_system = _normalize_required_text(
            normalized_source_system,
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
    hes_system = selected_hes_system or ensure_hes_system(
        session,
        hes_code=normalized_source_system,
        display_name=normalized_source_system,
        source_family=definition.source_family,
        default_delivery_mode=definition.delivery_mode,
        created_by_user_account_id=created_by_user_account_id,
    )

    instance = AdapterInstance(
        hes_system_id=hes_system.id,
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
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(instance)
    session.flush()
    return instance


def update_adapter_admin_state(
    session: Session,
    instance: AdapterInstance,
    target_state: str,
    *,
    updated_by_user_account_id: int | None = None,
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
    instance.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    event_code = "adapter_enabled" if target_state == "enabled" else "adapter_paused"
    record_operational_event(
        session,
        event_code,
        adapter_instance=instance,
        details={"admin_state": target_state, "status_reason": instance.status_reason},
        instance_code=instance.instance_code,
    )
    sync_adapter_health_alerts(session, adapter_instance_ids=[instance.id])
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
