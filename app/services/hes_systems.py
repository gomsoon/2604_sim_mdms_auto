from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AdapterInstance,
    AdapterRun,
    BillDeterminant,
    CanonicalMeasurement,
    Device,
    FinalMeasurement,
    HesEventRaw,
    HesMeterReference,
    HesReadRaw,
    HesSystem,
    IngestBatch,
    OperationalEvent,
    ServicePoint,
    UsageTransaction,
    VeeReplayRequest,
)
from app.services.operational_events import close_operational_alerts, record_operational_event


@dataclass(slots=True)
class HesSystemValidationError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class HesSystemSummary:
    hes_system: HesSystem
    adapter_count: int
    enabled_adapter_count: int
    running_adapter_count: int
    overdue_adapter_count: int
    stale_adapter_count: int
    open_alert_count: int
    latest_success_at: object | None
    latest_ingest_at: object | None


@dataclass(frozen=True, slots=True)
class HesSystemDetail:
    hes_system: HesSystem
    recent_batches: list[IngestBatch]
    adapter_rows: list[Any]
    running_adapter_count: int
    overdue_adapter_count: int
    stale_adapter_count: int
    open_alert_count: int
    latest_success_at: object | None
    latest_ingest_at: object | None
    latest_event_at: object | None
    open_alerts: list[OperationalEvent]
    recent_events: list[OperationalEvent]
    raw_reads_count: int
    raw_events_count: int
    usage_transaction_count: int
    partial_usage_transaction_count: int
    blocked_usage_transaction_count: int
    latest_usage_recalculated_at: object | None
    recent_recalculated_usage_rows: list[UsageTransaction]
    bill_determinant_count: int
    partial_bill_determinant_count: int
    blocked_bill_determinant_count: int
    latest_bill_determinant_calculated_at: object | None
    recent_bill_determinant_rows: list[BillDeterminant]
    active_vee_replay_request_count: int
    failed_vee_replay_request_count: int
    latest_vee_replay_requested_at: object | None
    latest_vee_replay_completed_at: object | None
    recent_vee_replay_requests: list[VeeReplayRequest]
    meter_reference_rows: list["HesMeterReferenceComparisonRow"]
    meter_reference_count: int
    matched_meter_reference_count: int
    missing_device_meter_reference_count: int
    missing_component_meter_reference_count: int
    missing_installation_meter_reference_count: int


@dataclass(frozen=True, slots=True)
class HesMeterReferenceComparisonRow:
    reference: HesMeterReference
    matched_device: Device | None
    matched_service_point: ServicePoint | None
    match_basis: str | None
    active_component_count: int
    active_installation_count: int
    comparison_status: str
    suggested_action: str
    suggested_fragment: str
    suggested_meter_id: str


@dataclass(frozen=True, slots=True)
class HesMeterReferenceAlertRule:
    comparison_status: str
    event_code: str
    close_memo: str


@dataclass(frozen=True, slots=True)
class HesMeterReferenceAlertSyncSummary:
    checked: int
    opened: int
    closed: int


def _normalize_required_hes_code(hes_code: str | None) -> str:
    normalized = (hes_code or "").strip()
    if not normalized:
        raise HesSystemValidationError("missing_hes_code", "HES code is required.")
    return normalized


def _normalize_required_text(
    value: str | None, *, error_code: str, fallback_message: str
) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise HesSystemValidationError(error_code, fallback_message)
    return normalized


def _parse_masked_config(raw_value: str | None) -> dict[str, Any] | None:
    import json

    normalized = (raw_value or "").strip()
    if not normalized:
        return None
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise HesSystemValidationError(
            "invalid_connection_config_masked",
            "Masked connection configuration must be a valid JSON object.",
        ) from exc
    if not isinstance(parsed, dict):
        raise HesSystemValidationError(
            "invalid_connection_config_masked",
            "Masked connection configuration must be a valid JSON object.",
        )
    return parsed


def _normalize_optional_text(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None


def _normalize_status(status: str | None) -> str:
    normalized = (status or "").strip() or "active"
    if normalized not in {"active", "inactive"}:
        raise HesSystemValidationError(
            "invalid_status",
            "Status must be active or inactive.",
        )
    return normalized


def _normalize_optional_delivery_mode(value: str | None) -> str | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    if normalized not in {"poll", "receive"}:
        raise HesSystemValidationError(
            "invalid_default_delivery_mode",
            "Default delivery mode must be poll or receive.",
        )
    return normalized


def _load_latest_runs(session: Session, adapter_instance_ids: list[int]) -> dict[int, AdapterRun]:
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


def _summarize_adapter_runtime(
    adapter_instances: list[AdapterInstance],
    latest_runs: dict[int, AdapterRun],
) -> tuple[int, int, int, object | None]:
    from app.services.adapters import derive_effective_status, derive_is_overdue, derive_is_stale

    running_count = 0
    overdue_count = 0
    stale_count = 0
    latest_success_candidates: list[object] = []

    for instance in adapter_instances:
        latest_run = latest_runs.get(instance.id)
        if derive_effective_status(instance, latest_run) == "running":
            running_count += 1
        if derive_is_overdue(instance, latest_run):
            overdue_count += 1
        if derive_is_stale(instance, latest_run):
            stale_count += 1
        if instance.last_success_at is not None:
            latest_success_candidates.append(instance.last_success_at)

    latest_success_at = max(latest_success_candidates) if latest_success_candidates else None
    return running_count, overdue_count, stale_count, latest_success_at


def _derive_hes_meter_reference_suggestion(
    reference: HesMeterReference,
    *,
    matched_device: Device | None,
    comparison_status: str,
) -> tuple[str, str, str]:
    if comparison_status == "missing_device":
        return (
            "create_device",
            "devices",
            reference.source_meter_key or reference.source_meter_id,
        )
    if comparison_status == "missing_component":
        return (
            "create_component",
            "components",
            matched_device.external_meter_id if matched_device is not None else reference.source_meter_id,
        )
    if comparison_status == "missing_installation":
        return (
            "create_installation",
            "installations",
            matched_device.external_meter_id if matched_device is not None else reference.source_meter_id,
        )
    return (
        "review_mapping",
        "devices",
        matched_device.external_meter_id if matched_device is not None else reference.source_meter_id,
    )


def _build_hes_meter_reference_comparison_rows(
    session: Session,
    hes_system: HesSystem,
) -> list[HesMeterReferenceComparisonRow]:
    references = session.scalars(
        select(HesMeterReference)
        .where(HesMeterReference.hes_system_id == hes_system.id)
        .order_by(HesMeterReference.last_synced_at.desc(), HesMeterReference.id.desc())
    ).all()
    if not references:
        return []

    candidate_meter_ids = {
        value
        for reference in references
        for value in (reference.source_meter_key, reference.source_meter_id)
        if value
    }
    devices = session.scalars(
        select(Device)
        .options(
            selectinload(Device.service_point),
            selectinload(Device.measuring_components),
            selectinload(Device.installation_history),
        )
        .where(
            Device.source_system == hes_system.hes_code,
            Device.external_meter_id.in_(sorted(candidate_meter_ids)),
        )
    ).all()
    device_by_external_meter_id = {device.external_meter_id: device for device in devices}

    rows: list[HesMeterReferenceComparisonRow] = []
    for reference in references:
        matched_device = None
        match_basis = None

        if reference.source_meter_key:
            matched_device = device_by_external_meter_id.get(reference.source_meter_key)
            if matched_device is not None:
                match_basis = "source_meter_key"

        if matched_device is None:
            matched_device = device_by_external_meter_id.get(reference.source_meter_id)
            if matched_device is not None:
                match_basis = "source_meter_id"

        active_component_count = 0
        active_installation_count = 0
        matched_service_point = None
        comparison_status = "missing_device"

        if matched_device is not None:
            matched_service_point = matched_device.service_point
            active_component_count = sum(
                1
                for component in matched_device.measuring_components
                if component.status == "active"
            )
            active_installation_count = sum(
                1
                for installation in matched_device.installation_history
                if installation.removed_at is None
            )

            if active_component_count == 0:
                comparison_status = "missing_component"
            elif active_installation_count == 0:
                comparison_status = "missing_installation"
            else:
                comparison_status = "matched"

        suggested_action, suggested_fragment, suggested_meter_id = _derive_hes_meter_reference_suggestion(
            reference,
            matched_device=matched_device,
            comparison_status=comparison_status,
        )
        rows.append(
            HesMeterReferenceComparisonRow(
                reference=reference,
                matched_device=matched_device,
                matched_service_point=matched_service_point,
                match_basis=match_basis,
                active_component_count=active_component_count,
                active_installation_count=active_installation_count,
                comparison_status=comparison_status,
                suggested_action=suggested_action,
                suggested_fragment=suggested_fragment,
                suggested_meter_id=suggested_meter_id,
            )
        )
    return rows


def _filter_hes_meter_reference_comparison_rows(
    rows: list[HesMeterReferenceComparisonRow],
    *,
    comparison_status: str | None = None,
    meter_query: str | None = None,
    limit: int | None = None,
) -> list[HesMeterReferenceComparisonRow]:
    normalized_status = (comparison_status or "").strip()
    normalized_query = (meter_query or "").strip().lower()

    filtered_rows = rows
    if normalized_status:
        filtered_rows = [row for row in filtered_rows if row.comparison_status == normalized_status]

    if normalized_query:
        filtered_rows = [
            row
            for row in filtered_rows
            if any(
                normalized_query in value.lower()
                for value in (
                    row.reference.source_meter_id,
                    row.reference.source_meter_key or "",
                    row.reference.meter_name or "",
                    row.reference.meter_status_code or "",
                    row.matched_device.external_meter_id if row.matched_device is not None else "",
                    row.matched_service_point.external_id
                    if row.matched_service_point is not None
                    else "",
                    row.matched_service_point.name if row.matched_service_point is not None else "",
                )
            )
        ]

    if limit is not None:
        return filtered_rows[:limit]
    return filtered_rows


def _summarize_hes_meter_reference_comparison_rows(
    rows: list[HesMeterReferenceComparisonRow],
) -> dict[str, int]:
    return {
        "meter_reference_count": len(rows),
        "matched_meter_reference_count": sum(
            1 for row in rows if row.comparison_status == "matched"
        ),
        "missing_device_meter_reference_count": sum(
            1 for row in rows if row.comparison_status == "missing_device"
        ),
        "missing_component_meter_reference_count": sum(
            1 for row in rows if row.comparison_status == "missing_component"
        ),
        "missing_installation_meter_reference_count": sum(
            1 for row in rows if row.comparison_status == "missing_installation"
        ),
    }


def _usage_transaction_matches_hes_clause(hes_system_id: int):
    return (
        select(FinalMeasurement.id)
        .join(
            CanonicalMeasurement,
            FinalMeasurement.canonical_measurement_id == CanonicalMeasurement.id,
        )
        .join(HesReadRaw, CanonicalMeasurement.hes_read_raw_id == HesReadRaw.id)
        .where(
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.service_point_id == UsageTransaction.service_point_id,
            FinalMeasurement.measuring_component_id == UsageTransaction.measuring_component_id,
            FinalMeasurement.measured_at >= UsageTransaction.period_start_at,
            FinalMeasurement.measured_at < UsageTransaction.period_end_at,
            HesReadRaw.hes_system_id == hes_system_id,
        )
        .exists()
    )


def _usage_recalculated_after_vee_filter():
    return UsageTransaction.details["provenance"]["trigger_source"].as_string() == "re_vee"


def _bill_determinant_matches_hes_clause(hes_system_id: int):
    return (
        select(UsageTransaction.id)
        .where(
            UsageTransaction.service_point_id == BillDeterminant.service_point_id,
            UsageTransaction.measuring_component_id == BillDeterminant.measuring_component_id,
            UsageTransaction.period_start_at == BillDeterminant.billing_period_start_at,
            UsageTransaction.period_end_at == BillDeterminant.billing_period_end_at,
            UsageTransaction.usage_type == "monthly_consumption",
        )
        .where(_usage_transaction_matches_hes_clause(hes_system_id))
        .exists()
    )


def _vee_replay_request_matches_hes_clause(hes_system_id: int):
    return or_(
        VeeReplayRequest.hes_system_id == hes_system_id,
        VeeReplayRequest.ingest_batch_id.in_(
            select(IngestBatch.id).where(IngestBatch.hes_system_id == hes_system_id)
        ),
    )


HES_METER_REFERENCE_ALERT_RULES: tuple[HesMeterReferenceAlertRule, ...] = (
    HesMeterReferenceAlertRule(
        comparison_status="missing_device",
        event_code="hes_meter_reference_missing_device_detected",
        close_memo="Closed automatically because the HES meter reference now has a canonical device mapping.",
    ),
    HesMeterReferenceAlertRule(
        comparison_status="missing_component",
        event_code="hes_meter_reference_missing_component_detected",
        close_memo="Closed automatically because the HES meter reference now has an active canonical component.",
    ),
    HesMeterReferenceAlertRule(
        comparison_status="missing_installation",
        event_code="hes_meter_reference_missing_installation_detected",
        close_memo="Closed automatically because the HES meter reference now has an active installation mapping.",
    ),
)


def sync_hes_meter_reference_alerts(
    session: Session,
    *,
    hes_system_id: int,
    occurred_at: datetime | None = None,
) -> HesMeterReferenceAlertSyncSummary | None:
    hes_system = session.get(HesSystem, hes_system_id)
    if hes_system is None:
        return None

    effective_occurred_at = occurred_at or datetime.now(timezone.utc)
    rows = _build_hes_meter_reference_comparison_rows(session, hes_system)
    open_alerts = session.scalars(
        select(OperationalEvent).where(
            OperationalEvent.hes_system_id == hes_system.id,
            OperationalEvent.is_alert.is_(True),
            OperationalEvent.event_code.in_(
                tuple(rule.event_code for rule in HES_METER_REFERENCE_ALERT_RULES)
            ),
            OperationalEvent.entity_type == "hes_meter_reference",
            OperationalEvent.alert_status.in_(("open", "acknowledged")),
        )
    ).all()
    open_alert_keys = {(row.event_code, row.entity_id) for row in open_alerts}

    opened = 0
    closed = 0
    for row in rows:
        for rule in HES_METER_REFERENCE_ALERT_RULES:
            alert_key = (rule.event_code, row.reference.id)
            is_active = row.comparison_status == rule.comparison_status
            if is_active:
                if alert_key not in open_alert_keys:
                    record_operational_event(
                        session,
                        rule.event_code,
                        occurred_at=effective_occurred_at,
                        hes_system=hes_system,
                        entity_type="hes_meter_reference",
                        entity_id=row.reference.id,
                        meter_identifier=row.reference.source_meter_key or row.reference.source_meter_id,
                        details={
                            "comparison_status": row.comparison_status,
                            "suggested_action": row.suggested_action,
                            "suggested_fragment": row.suggested_fragment,
                            "source_meter_id": row.reference.source_meter_id,
                            "source_meter_key": row.reference.source_meter_key,
                            "meter_status_code": row.reference.meter_status_code,
                            "lp_interval_minutes": row.reference.lp_interval_minutes,
                            "matched_device_id": row.matched_device.id if row.matched_device is not None else None,
                            "matched_service_point_id": (
                                row.matched_service_point.id
                                if row.matched_service_point is not None
                                else None
                            ),
                        },
                        source_meter_id=row.reference.source_meter_id,
                        source_meter_key=row.reference.source_meter_key or "-",
                        suggested_action=row.suggested_action,
                    )
                    open_alert_keys.add(alert_key)
                    opened += 1
                continue

            closed_count = close_operational_alerts(
                session,
                event_code=rule.event_code,
                entity_type="hes_meter_reference",
                entity_id=row.reference.id,
                closed_at=effective_occurred_at,
                operator_memo=rule.close_memo,
            )
            if closed_count:
                open_alert_keys.discard(alert_key)
            closed += closed_count

    return HesMeterReferenceAlertSyncSummary(
        checked=len(rows),
        opened=opened,
        closed=closed,
    )


def list_hes_meter_reference_comparisons(
    session: Session,
    *,
    hes_system_id: int,
    comparison_status: str | None = None,
    meter_query: str | None = None,
    limit: int = 200,
) -> tuple[HesSystem, list[HesMeterReferenceComparisonRow], dict[str, int]] | None:
    hes_system = session.get(HesSystem, hes_system_id)
    if hes_system is None:
        return None

    rows = _build_hes_meter_reference_comparison_rows(session, hes_system)
    filtered_rows = _filter_hes_meter_reference_comparison_rows(
        rows,
        comparison_status=comparison_status,
        meter_query=meter_query,
        limit=limit,
    )
    return hes_system, filtered_rows, _summarize_hes_meter_reference_comparison_rows(filtered_rows)


def ensure_hes_system(
    session: Session,
    *,
    hes_code: str,
    display_name: str | None = None,
    vendor_name: str | None = None,
    source_family: str = "hes",
    default_delivery_mode: str | None = None,
    status: str = "active",
    timezone_name: str | None = None,
    description: str | None = None,
    connection_config_masked: dict[str, Any] | None = None,
    created_by_user_account_id: int | None = None,
) -> HesSystem:
    normalized_hes_code = _normalize_required_hes_code(hes_code)
    existing = session.scalar(
        select(HesSystem).where(HesSystem.hes_code == normalized_hes_code).limit(1)
    )
    if existing is not None:
        return existing

    hes_system = HesSystem(
        hes_code=normalized_hes_code,
        display_name=(display_name or normalized_hes_code).strip() or normalized_hes_code,
        vendor_name=(vendor_name or "").strip() or None,
        source_family=(source_family or "hes").strip() or "hes",
        default_delivery_mode=(default_delivery_mode or "").strip() or None,
        status=(status or "active").strip() or "active",
        timezone_name=(timezone_name or "").strip() or None,
        description=(description or "").strip() or None,
        connection_config_masked=connection_config_masked,
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def list_hes_systems(session: Session, *, limit: int = 100) -> list[HesSystemSummary]:
    rows = session.scalars(
        select(HesSystem)
        .options(
            selectinload(HesSystem.adapter_instances).selectinload(AdapterInstance.adapter_definition)
        )
        .order_by(HesSystem.id.desc())
        .limit(limit)
    ).all()
    latest_runs = _load_latest_runs(
        session,
        [adapter.id for row in rows for adapter in row.adapter_instances],
    )

    summaries: list[HesSystemSummary] = []
    for row in rows:
        (
            running_adapter_count,
            overdue_adapter_count,
            stale_adapter_count,
            latest_success_at,
        ) = _summarize_adapter_runtime(row.adapter_instances, latest_runs)
        open_alert_count = int(
            session.scalar(
                select(func.count())
                .select_from(OperationalEvent)
                .where(
                    OperationalEvent.hes_system_id == row.id,
                    OperationalEvent.is_alert.is_(True),
                    OperationalEvent.alert_status.in_(("open", "acknowledged")),
                )
            )
            or 0
        )
        latest_ingest_at = session.scalar(
            select(func.max(IngestBatch.received_at)).where(IngestBatch.hes_system_id == row.id)
        )
        summaries.append(
            HesSystemSummary(
                hes_system=row,
                adapter_count=len(row.adapter_instances),
                enabled_adapter_count=sum(1 for adapter in row.adapter_instances if adapter.admin_state == "enabled"),
                running_adapter_count=running_adapter_count,
                overdue_adapter_count=overdue_adapter_count,
                stale_adapter_count=stale_adapter_count,
                open_alert_count=open_alert_count,
                latest_success_at=latest_success_at,
                latest_ingest_at=latest_ingest_at,
            )
        )
    return summaries


def create_hes_system(
    session: Session,
    *,
    hes_code: str | None,
    display_name: str | None,
    vendor_name: str | None,
    source_family: str | None,
    default_delivery_mode: str | None,
    status: str | None,
    timezone_name: str | None,
    description: str | None,
    connection_config_masked: str | None,
    created_by_user_account_id: int | None = None,
) -> HesSystem:
    normalized_hes_code = _normalize_required_hes_code(hes_code)
    duplicate = session.scalar(select(HesSystem.id).where(HesSystem.hes_code == normalized_hes_code).limit(1))
    if duplicate is not None:
        raise HesSystemValidationError(
            "duplicate_hes_code",
            "A HES system with the same code already exists.",
        )

    hes_system = HesSystem(
        hes_code=normalized_hes_code,
        display_name=_normalize_required_text(
            display_name,
            error_code="missing_display_name",
            fallback_message="HES display name is required.",
        ),
        vendor_name=_normalize_optional_text(vendor_name),
        source_family=_normalize_required_text(
            source_family,
            error_code="missing_source_family",
            fallback_message="Source family is required.",
        ),
        default_delivery_mode=_normalize_optional_delivery_mode(default_delivery_mode),
        status=_normalize_status(status),
        timezone_name=_normalize_optional_text(timezone_name),
        description=_normalize_optional_text(description),
        connection_config_masked=_parse_masked_config(connection_config_masked),
        created_by_user_account_id=created_by_user_account_id,
        updated_by_user_account_id=created_by_user_account_id,
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def update_hes_system(
    session: Session,
    hes_system: HesSystem,
    *,
    hes_code: str | None,
    display_name: str | None,
    vendor_name: str | None,
    source_family: str | None,
    default_delivery_mode: str | None,
    status: str | None,
    timezone_name: str | None,
    description: str | None,
    connection_config_masked: str | None,
    updated_by_user_account_id: int | None = None,
) -> HesSystem:
    normalized_hes_code = _normalize_required_hes_code(hes_code)
    duplicate = session.scalar(
        select(HesSystem.id)
        .where(HesSystem.hes_code == normalized_hes_code, HesSystem.id != hes_system.id)
        .limit(1)
    )
    if duplicate is not None:
        raise HesSystemValidationError(
            "duplicate_hes_code",
            "A HES system with the same code already exists.",
        )

    hes_system.hes_code = normalized_hes_code
    hes_system.display_name = _normalize_required_text(
        display_name,
        error_code="missing_display_name",
        fallback_message="HES display name is required.",
    )
    hes_system.vendor_name = _normalize_optional_text(vendor_name)
    hes_system.source_family = _normalize_required_text(
        source_family,
        error_code="missing_source_family",
        fallback_message="Source family is required.",
    )
    hes_system.default_delivery_mode = _normalize_optional_delivery_mode(default_delivery_mode)
    hes_system.status = _normalize_status(status)
    hes_system.timezone_name = _normalize_optional_text(timezone_name)
    hes_system.description = _normalize_optional_text(description)
    hes_system.connection_config_masked = _parse_masked_config(connection_config_masked)
    hes_system.updated_by_user_account_id = updated_by_user_account_id
    session.flush()
    return hes_system


def get_hes_system_detail(session: Session, hes_system_id: int) -> HesSystemDetail | None:
    from app.services.adapters import list_adapter_instances

    hes_system = session.scalar(
        select(HesSystem)
        .options(
            selectinload(HesSystem.adapter_instances).selectinload(AdapterInstance.adapter_definition),
            selectinload(HesSystem.created_by_user_account),
            selectinload(HesSystem.updated_by_user_account),
        )
        .where(HesSystem.id == hes_system_id)
        .limit(1)
    )
    if hes_system is None:
        return None

    adapter_rows = list_adapter_instances(session, limit=200, hes_system_id=hes_system.id)
    recent_batches = session.scalars(
        select(IngestBatch)
        .where(IngestBatch.hes_system_id == hes_system.id)
        .order_by(IngestBatch.id.desc())
        .limit(20)
    ).all()

    open_alert_count = int(
        session.scalar(
            select(func.count())
            .select_from(OperationalEvent)
            .where(
                OperationalEvent.hes_system_id == hes_system.id,
                OperationalEvent.is_alert.is_(True),
                OperationalEvent.alert_status.in_(("open", "acknowledged")),
            )
        )
        or 0
    )
    open_alerts = session.scalars(
        select(OperationalEvent)
        .where(
            OperationalEvent.hes_system_id == hes_system.id,
            OperationalEvent.is_alert.is_(True),
            OperationalEvent.alert_status.in_(("open", "acknowledged")),
        )
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(10)
    ).all()
    recent_events = session.scalars(
        select(OperationalEvent)
        .where(OperationalEvent.hes_system_id == hes_system.id)
        .order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc())
        .limit(20)
    ).all()
    running_adapter_count = sum(1 for row in adapter_rows if row.effective_status == "running")
    overdue_adapter_count = sum(1 for row in adapter_rows if row.is_overdue)
    stale_adapter_count = sum(1 for row in adapter_rows if row.is_stale)
    latest_success_candidates = [
        row.instance.last_success_at for row in adapter_rows if row.instance.last_success_at is not None
    ]
    latest_success_at = max(latest_success_candidates) if latest_success_candidates else None
    latest_ingest_at = recent_batches[0].received_at if recent_batches else None
    latest_event_at = recent_events[0].occurred_at if recent_events else None

    raw_reads_count = int(
        session.scalar(
            select(func.count()).select_from(HesReadRaw).where(HesReadRaw.hes_system_id == hes_system.id)
        )
        or 0
    )
    raw_events_count = int(
        session.scalar(
            select(func.count()).select_from(HesEventRaw).where(HesEventRaw.hes_system_id == hes_system.id)
        )
        or 0
    )
    usage_scope_clause = _usage_transaction_matches_hes_clause(hes_system.id)
    usage_transaction_count = int(
        session.scalar(
            select(func.count()).select_from(UsageTransaction).where(usage_scope_clause)
        )
        or 0
    )
    partial_usage_transaction_count = int(
        session.scalar(
            select(func.count())
            .select_from(UsageTransaction)
            .where(
                usage_scope_clause,
                UsageTransaction.calculation_status == "partial",
            )
        )
        or 0
    )
    blocked_usage_transaction_count = int(
        session.scalar(
            select(func.count())
            .select_from(UsageTransaction)
            .where(
                usage_scope_clause,
                UsageTransaction.calculation_status == "blocked",
            )
        )
        or 0
    )
    latest_usage_recalculated_at = session.scalar(
        select(func.max(UsageTransaction.calculated_at)).where(
            usage_scope_clause,
            _usage_recalculated_after_vee_filter(),
        )
    )
    recent_recalculated_usage_rows = session.scalars(
        select(UsageTransaction)
        .options(
            selectinload(UsageTransaction.service_point),
            selectinload(UsageTransaction.measuring_component),
            selectinload(UsageTransaction.device),
        )
        .where(
            usage_scope_clause,
            _usage_recalculated_after_vee_filter(),
        )
        .order_by(UsageTransaction.calculated_at.desc(), UsageTransaction.id.desc())
        .limit(5)
    ).all()
    bill_determinant_scope_clause = _bill_determinant_matches_hes_clause(hes_system.id)
    bill_determinant_count = int(
        session.scalar(
            select(func.count())
            .select_from(BillDeterminant)
            .where(
                bill_determinant_scope_clause,
                BillDeterminant.is_current.is_(True),
            )
        )
        or 0
    )
    partial_bill_determinant_count = int(
        session.scalar(
            select(func.count())
            .select_from(BillDeterminant)
            .where(
                bill_determinant_scope_clause,
                BillDeterminant.is_current.is_(True),
                BillDeterminant.calculation_status == "partial",
            )
        )
        or 0
    )
    blocked_bill_determinant_count = int(
        session.scalar(
            select(func.count())
            .select_from(BillDeterminant)
            .where(
                bill_determinant_scope_clause,
                BillDeterminant.is_current.is_(True),
                BillDeterminant.calculation_status == "blocked",
            )
        )
        or 0
    )
    latest_bill_determinant_calculated_at = session.scalar(
        select(func.max(BillDeterminant.calculated_at)).where(
            bill_determinant_scope_clause,
            BillDeterminant.is_current.is_(True),
        )
    )
    recent_bill_determinant_rows = session.scalars(
        select(BillDeterminant)
        .options(
            selectinload(BillDeterminant.service_point),
            selectinload(BillDeterminant.measuring_component),
            selectinload(BillDeterminant.device),
        )
        .where(
            bill_determinant_scope_clause,
            BillDeterminant.is_current.is_(True),
        )
        .order_by(BillDeterminant.calculated_at.desc(), BillDeterminant.id.desc())
        .limit(5)
    ).all()
    vee_replay_scope_clause = _vee_replay_request_matches_hes_clause(hes_system.id)
    active_vee_replay_request_count = int(
        session.scalar(
            select(func.count())
            .select_from(VeeReplayRequest)
            .where(
                vee_replay_scope_clause,
                VeeReplayRequest.status.in_(("queued", "processing")),
            )
        )
        or 0
    )
    failed_vee_replay_request_count = int(
        session.scalar(
            select(func.count())
            .select_from(VeeReplayRequest)
            .where(
                vee_replay_scope_clause,
                VeeReplayRequest.status == "failed",
            )
        )
        or 0
    )
    latest_vee_replay_requested_at = session.scalar(
        select(func.max(VeeReplayRequest.created_at)).where(vee_replay_scope_clause)
    )
    latest_vee_replay_completed_at = session.scalar(
        select(func.max(VeeReplayRequest.completed_at)).where(vee_replay_scope_clause)
    )
    recent_vee_replay_requests = session.scalars(
        select(VeeReplayRequest)
        .options(
            selectinload(VeeReplayRequest.hes_system),
            selectinload(VeeReplayRequest.ingest_batch).selectinload(IngestBatch.hes_system),
        )
        .where(vee_replay_scope_clause)
        .order_by(VeeReplayRequest.updated_at.desc(), VeeReplayRequest.id.desc())
        .limit(5)
    ).all()
    all_meter_reference_rows = _build_hes_meter_reference_comparison_rows(session, hes_system)
    meter_reference_summary = _summarize_hes_meter_reference_comparison_rows(
        all_meter_reference_rows
    )

    return HesSystemDetail(
        hes_system=hes_system,
        recent_batches=recent_batches,
        adapter_rows=adapter_rows,
        running_adapter_count=running_adapter_count,
        overdue_adapter_count=overdue_adapter_count,
        stale_adapter_count=stale_adapter_count,
        open_alert_count=open_alert_count,
        latest_success_at=latest_success_at,
        latest_ingest_at=latest_ingest_at,
        latest_event_at=latest_event_at,
        open_alerts=open_alerts,
        recent_events=recent_events,
        raw_reads_count=raw_reads_count,
        raw_events_count=raw_events_count,
        usage_transaction_count=usage_transaction_count,
        partial_usage_transaction_count=partial_usage_transaction_count,
        blocked_usage_transaction_count=blocked_usage_transaction_count,
        latest_usage_recalculated_at=latest_usage_recalculated_at,
        recent_recalculated_usage_rows=recent_recalculated_usage_rows,
        bill_determinant_count=bill_determinant_count,
        partial_bill_determinant_count=partial_bill_determinant_count,
        blocked_bill_determinant_count=blocked_bill_determinant_count,
        latest_bill_determinant_calculated_at=latest_bill_determinant_calculated_at,
        recent_bill_determinant_rows=recent_bill_determinant_rows,
        active_vee_replay_request_count=active_vee_replay_request_count,
        failed_vee_replay_request_count=failed_vee_replay_request_count,
        latest_vee_replay_requested_at=latest_vee_replay_requested_at,
        latest_vee_replay_completed_at=latest_vee_replay_completed_at,
        recent_vee_replay_requests=recent_vee_replay_requests,
        meter_reference_rows=all_meter_reference_rows[:10],
        meter_reference_count=meter_reference_summary["meter_reference_count"],
        matched_meter_reference_count=meter_reference_summary["matched_meter_reference_count"],
        missing_device_meter_reference_count=meter_reference_summary[
            "missing_device_meter_reference_count"
        ],
        missing_component_meter_reference_count=meter_reference_summary[
            "missing_component_meter_reference_count"
        ],
        missing_installation_meter_reference_count=meter_reference_summary[
            "missing_installation_meter_reference_count"
        ],
    )
