from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload

from app.models import CanonicalMeasurement, FinalMeasurement, HesReadRaw, UsageTransaction
from app.services.pipeline import (
    complete_pipeline_run,
    fail_pipeline_run,
    start_pipeline_run,
    upsert_processing_watermark,
)


USAGE_TYPE_DAILY = "daily_consumption"
USAGE_TYPE_MONTHLY = "monthly_consumption"
SUPPORTED_USAGE_TYPES = {USAGE_TYPE_DAILY, USAGE_TYPE_MONTHLY}


@dataclass(frozen=True, slots=True)
class UsageCalculationSummary:
    usage_type: str
    groups: int
    created: int
    updated: int
    complete: int
    partial: int
    blocked: int


@dataclass(slots=True)
class _UsageBucket:
    service_point_id: int
    measuring_component_id: int
    device_id: int
    usage_type: str
    period_start_at: datetime
    period_end_at: datetime
    window_timezone_name: str
    timezone_source: str
    timezone_fallback_from: str | None = None
    usage_value: Decimal = Decimal("0.0000")
    source_final_count: int = 0
    unit_of_measure_values: set[str] = field(default_factory=set)
    interval_size_values: set[int | None] = field(default_factory=set)
    quality_codes: set[str] = field(default_factory=set)
    status_codes: set[str] = field(default_factory=set)
    source_systems: set[str] = field(default_factory=set)


def _normalize_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _resolve_usage_timezone(raw_row: HesReadRaw | None) -> tuple[ZoneInfo, str, str, str | None]:
    configured_name = (
        raw_row.hes_system.timezone_name
        if raw_row is not None and raw_row.hes_system is not None
        else None
    )
    if configured_name:
        try:
            return ZoneInfo(configured_name), configured_name, "hes_system", None
        except ZoneInfoNotFoundError:
            pass
    if configured_name:
        return ZoneInfo("UTC"), "UTC", "fallback_utc", configured_name
    return ZoneInfo("UTC"), "UTC", "fallback_utc", None


def _derive_window(
    measured_at: datetime, usage_type: str, usage_timezone: ZoneInfo
) -> tuple[datetime, datetime]:
    local_measured_at = _normalize_utc(measured_at).astimezone(usage_timezone)
    if usage_type == USAGE_TYPE_DAILY:
        period_start_local = local_measured_at.replace(hour=0, minute=0, second=0, microsecond=0)
        period_end_local = period_start_local + timedelta(days=1)
    elif usage_type == USAGE_TYPE_MONTHLY:
        period_start_local = local_measured_at.replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        if period_start_local.month == 12:
            period_end_local = period_start_local.replace(
                year=period_start_local.year + 1,
                month=1,
            )
        else:
            period_end_local = period_start_local.replace(month=period_start_local.month + 1)
    else:
        raise ValueError(f"Unsupported usage type: {usage_type}")
    return (
        period_start_local.astimezone(timezone.utc),
        period_end_local.astimezone(timezone.utc),
    )


def _expected_interval_count(
    period_start_at: datetime,
    period_end_at: datetime,
    *,
    interval_size_minutes: int,
) -> int | None:
    if interval_size_minutes <= 0:
        return None
    duration_minutes = int((period_end_at - period_start_at).total_seconds() // 60)
    if duration_minutes <= 0:
        return None
    if duration_minutes % interval_size_minutes != 0:
        return None
    return duration_minutes // interval_size_minutes


def _build_usage_row_payload(
    bucket: _UsageBucket,
) -> dict[str, object]:
    details: dict[str, object] = {
        "quality_codes": sorted(bucket.quality_codes),
        "status_codes": sorted(bucket.status_codes),
        "source_systems": sorted(bucket.source_systems),
        "timezone_source": bucket.timezone_source,
    }
    if bucket.timezone_fallback_from is not None:
        details["timezone_fallback_from"] = bucket.timezone_fallback_from

    unit_of_measure = (
        next(iter(bucket.unit_of_measure_values))
        if len(bucket.unit_of_measure_values) == 1
        else None
    )
    if len(bucket.unit_of_measure_values) != 1 or unit_of_measure in (None, ""):
        details["blocked_reason"] = "mixed_or_missing_uom"
        return {
            "interval_size_minutes": None,
            "unit_of_measure": None,
            "usage_value": Decimal("0.0000"),
            "missing_interval_count": 0,
            "quality_summary": "blocked_mixed_uom",
            "calculation_status": "blocked",
            "details": details,
        }

    if len(bucket.interval_size_values) != 1:
        details["blocked_reason"] = "mixed_interval_size"
        return {
            "interval_size_minutes": None,
            "unit_of_measure": unit_of_measure,
            "usage_value": Decimal("0.0000"),
            "missing_interval_count": 0,
            "quality_summary": "blocked_mixed_interval",
            "calculation_status": "blocked",
            "details": details,
        }

    interval_size_minutes = next(iter(bucket.interval_size_values))
    if interval_size_minutes is None:
        details["blocked_reason"] = "missing_interval_size"
        return {
            "interval_size_minutes": None,
            "unit_of_measure": unit_of_measure,
            "usage_value": Decimal("0.0000"),
            "missing_interval_count": 0,
            "quality_summary": "blocked_mixed_interval",
            "calculation_status": "blocked",
            "details": details,
        }

    expected_interval_count = _expected_interval_count(
        bucket.period_start_at,
        bucket.period_end_at,
        interval_size_minutes=interval_size_minutes,
    )
    if expected_interval_count is None:
        details["blocked_reason"] = "invalid_interval_window"
        return {
            "interval_size_minutes": interval_size_minutes,
            "unit_of_measure": unit_of_measure,
            "usage_value": Decimal("0.0000"),
            "missing_interval_count": 0,
            "quality_summary": "blocked_mixed_interval",
            "calculation_status": "blocked",
            "details": details,
        }

    missing_interval_count = max(expected_interval_count - bucket.source_final_count, 0)
    details["expected_interval_count"] = expected_interval_count

    non_ok_quality_codes = {code for code in bucket.quality_codes if code != "OK"}
    if missing_interval_count > 0:
        return {
            "interval_size_minutes": interval_size_minutes,
            "unit_of_measure": unit_of_measure,
            "usage_value": bucket.usage_value,
            "missing_interval_count": missing_interval_count,
            "quality_summary": "missing_intervals",
            "calculation_status": "partial",
            "details": details,
        }
    if non_ok_quality_codes:
        return {
            "interval_size_minutes": interval_size_minutes,
            "unit_of_measure": unit_of_measure,
            "usage_value": bucket.usage_value,
            "missing_interval_count": 0,
            "quality_summary": "mixed_quality",
            "calculation_status": "partial",
            "details": details,
        }
    return {
        "interval_size_minutes": interval_size_minutes,
        "unit_of_measure": unit_of_measure,
        "usage_value": bucket.usage_value,
        "missing_interval_count": 0,
        "quality_summary": "all_finalized",
        "calculation_status": "complete",
        "details": details,
    }


def _load_final_measurements(
    session: Session,
    *,
    service_point_id: int | None,
    measuring_component_id: int | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[FinalMeasurement]:
    statement: Select[tuple[FinalMeasurement]] = (
        select(FinalMeasurement)
        .where(FinalMeasurement.final_status == "finalized")
        .options(
            joinedload(FinalMeasurement.initial_measurement),
            joinedload(FinalMeasurement.canonical_measurement)
            .joinedload(CanonicalMeasurement.hes_read_raw)
            .joinedload(HesReadRaw.hes_system),
        )
    )
    if service_point_id is not None:
        statement = statement.where(FinalMeasurement.service_point_id == service_point_id)
    if measuring_component_id is not None:
        statement = statement.where(FinalMeasurement.measuring_component_id == measuring_component_id)
    if date_from is not None:
        statement = statement.where(FinalMeasurement.measured_at >= date_from)
    if date_to is not None:
        statement = statement.where(FinalMeasurement.measured_at <= date_to)
    statement = statement.order_by(FinalMeasurement.id.asc())
    return session.execute(statement).scalars().unique().all()


def _build_usage_buckets(
    final_rows: list[FinalMeasurement],
    *,
    usage_type: str,
) -> dict[
    tuple[int, int, int, str, datetime, datetime, str],
    _UsageBucket,
]:
    buckets: dict[
        tuple[int, int, int, str, datetime, datetime, str],
        _UsageBucket,
    ] = {}
    for row in final_rows:
        canonical_row = row.canonical_measurement
        raw_row = canonical_row.hes_read_raw if canonical_row is not None else None
        usage_timezone, timezone_name, timezone_source, timezone_fallback_from = (
            _resolve_usage_timezone(raw_row)
        )
        period_start_at, period_end_at = _derive_window(
            row.measured_at,
            usage_type,
            usage_timezone,
        )
        key = (
            row.service_point_id,
            row.measuring_component_id,
            row.device_id,
            usage_type,
            period_start_at,
            period_end_at,
            timezone_name,
        )
        bucket = buckets.get(key)
        if bucket is None:
            bucket = _UsageBucket(
                service_point_id=row.service_point_id,
                measuring_component_id=row.measuring_component_id,
                device_id=row.device_id,
                usage_type=usage_type,
                period_start_at=period_start_at,
                period_end_at=period_end_at,
                window_timezone_name=timezone_name,
                timezone_source=timezone_source,
                timezone_fallback_from=timezone_fallback_from,
            )
            buckets[key] = bucket

        bucket.usage_value += row.value
        bucket.source_final_count += 1
        if row.unit_of_measure:
            bucket.unit_of_measure_values.add(row.unit_of_measure)
        interval_size_minutes = raw_row.interval_size_minutes if raw_row is not None else None
        bucket.interval_size_values.add(interval_size_minutes)
        if row.quality_code:
            bucket.quality_codes.add(row.quality_code)
        if row.status_code:
            bucket.status_codes.add(row.status_code)
        if raw_row is not None:
            bucket.source_systems.add(raw_row.source_system)
    return buckets


def calculate_usage_transactions(
    session: Session,
    *,
    usage_type: str,
    service_point_id: int | None = None,
    measuring_component_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    trigger_type: str = "manual",
) -> UsageCalculationSummary:
    if usage_type not in SUPPORTED_USAGE_TYPES:
        raise ValueError(f"Unsupported usage type: {usage_type}")

    final_rows = _load_final_measurements(
        session,
        service_point_id=service_point_id,
        measuring_component_id=measuring_component_id,
        date_from=date_from,
        date_to=date_to,
    )
    pipeline_run = start_pipeline_run(
        session,
        pipeline_name="usage",
        trigger_type=trigger_type,
        details={
            "usage_type": usage_type,
            "service_point_id": service_point_id,
            "measuring_component_id": measuring_component_id,
            "date_from": date_from.isoformat() if date_from is not None else None,
            "date_to": date_to.isoformat() if date_to is not None else None,
        },
    )

    try:
        buckets = _build_usage_buckets(final_rows, usage_type=usage_type)
        created = 0
        updated = 0
        complete = 0
        partial = 0
        blocked = 0
        calculated_at = datetime.now(timezone.utc)
        latest_period_end_at: datetime | None = None

        for bucket in buckets.values():
            payload = _build_usage_row_payload(bucket)
            if payload["calculation_status"] == "complete":
                complete += 1
            elif payload["calculation_status"] == "partial":
                partial += 1
            else:
                blocked += 1

            usage_row = session.scalar(
                select(UsageTransaction)
                .where(UsageTransaction.service_point_id == bucket.service_point_id)
                .where(
                    UsageTransaction.measuring_component_id == bucket.measuring_component_id
                )
                .where(UsageTransaction.usage_type == bucket.usage_type)
                .where(UsageTransaction.period_start_at == bucket.period_start_at)
                .where(UsageTransaction.period_end_at == bucket.period_end_at)
                .limit(1)
            )
            if usage_row is None:
                usage_row = UsageTransaction(
                    pipeline_run_id=pipeline_run.id,
                    service_point_id=bucket.service_point_id,
                    measuring_component_id=bucket.measuring_component_id,
                    device_id=bucket.device_id,
                    usage_type=bucket.usage_type,
                    period_start_at=bucket.period_start_at,
                    period_end_at=bucket.period_end_at,
                    window_timezone_name=bucket.window_timezone_name,
                    interval_size_minutes=payload["interval_size_minutes"],
                    unit_of_measure=payload["unit_of_measure"],
                    usage_value=payload["usage_value"],
                    source_final_count=bucket.source_final_count,
                    missing_interval_count=payload["missing_interval_count"],
                    quality_summary=payload["quality_summary"],
                    calculation_status=payload["calculation_status"],
                    calculated_at=calculated_at,
                    details=payload["details"],
                )
                session.add(usage_row)
                created += 1
            else:
                usage_row.pipeline_run_id = pipeline_run.id
                usage_row.device_id = bucket.device_id
                usage_row.window_timezone_name = bucket.window_timezone_name
                usage_row.interval_size_minutes = payload["interval_size_minutes"]
                usage_row.unit_of_measure = payload["unit_of_measure"]
                usage_row.usage_value = payload["usage_value"]
                usage_row.source_final_count = bucket.source_final_count
                usage_row.missing_interval_count = payload["missing_interval_count"]
                usage_row.quality_summary = payload["quality_summary"]
                usage_row.calculation_status = payload["calculation_status"]
                usage_row.calculated_at = calculated_at
                usage_row.details = payload["details"]
                updated += 1
            latest_period_end_at = (
                bucket.period_end_at
                if latest_period_end_at is None or bucket.period_end_at > latest_period_end_at
                else latest_period_end_at
            )

        session.flush()

        summary = UsageCalculationSummary(
            usage_type=usage_type,
            groups=len(buckets),
            created=created,
            updated=updated,
            complete=complete,
            partial=partial,
            blocked=blocked,
        )
        details = {
            **pipeline_run.details,
            "groups": summary.groups,
            "created": summary.created,
            "updated": summary.updated,
            "complete": summary.complete,
            "partial": summary.partial,
            "blocked": summary.blocked,
            "source_final_count": len(final_rows),
        }

        if latest_period_end_at is not None:
            upsert_processing_watermark(
                session,
                pipeline_name="usage",
                source_system=None,
                record_type=usage_type,
                last_processed_at=latest_period_end_at,
                details=details,
            )

        if summary.groups == 0:
            result_code = "usage_noop"
        elif summary.blocked > 0:
            result_code = "usage_completed_with_blocked"
        elif summary.partial > 0:
            result_code = "usage_completed_with_partial"
        else:
            result_code = "usage_completed"
        complete_pipeline_run(
            pipeline_run,
            result_code=result_code,
            details=details,
        )
        return summary
    except Exception:
        fail_pipeline_run(
            pipeline_run,
            result_code="usage_failed_exception",
            details={
                **pipeline_run.details,
                "source_final_count": len(final_rows),
            },
        )
        raise
