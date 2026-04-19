from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AdapterInstance, AdapterRun, AdapterWatermark
from app.services.ingest_adapters import DEFAULT_ADAPTER_KEY
from app.services.ingest_contract import parse_datetime
from app.services.ingestion import ingest_events, ingest_reads


@dataclass(slots=True)
class AdapterExecutionError(RuntimeError):
    error_code: str
    fallback_message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class AdapterIngestEnvelope:
    record_type: str
    payload: dict[str, Any]
    source_rows_fetched: int
    watermark_before: str | None
    watermark_after: str | None
    cursor_type: str
    last_source_timestamp: datetime | None
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AdapterRunExecutionResult:
    run_id: int
    run_status: str
    source_rows_fetched: int
    ingest_batches_created: int
    ingest_records_created: int
    watermark_before: str | None
    watermark_after: str | None
    error_code: str | None = None
    error_summary: str | None = None


@dataclass(frozen=True, slots=True)
class AdapterRunProcessingSummary:
    processed: int
    completed: int
    failed: int
    results: list[AdapterRunExecutionResult]


class RuntimeAdapter(Protocol):
    def build_ingest_envelope(
        self,
        session: Session,
        instance: AdapterInstance,
        run: AdapterRun,
    ) -> AdapterIngestEnvelope: ...


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _coerce_details(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _parse_runtime_timestamp(value: Any, *, error_code: str, fallback_message: str) -> datetime:
    try:
        parsed = parse_datetime(value, require_timezone=True)
    except ValueError as exc:
        raise AdapterExecutionError(error_code, fallback_message) from exc
    if parsed is None:
        raise AdapterExecutionError(error_code, fallback_message)
    return parsed


def _load_adapter_watermark(
    session: Session, *, adapter_instance_id: int, record_type: str
) -> AdapterWatermark | None:
    return session.scalar(
        select(AdapterWatermark)
        .where(
            AdapterWatermark.adapter_instance_id == adapter_instance_id,
            AdapterWatermark.record_type == record_type,
        )
        .limit(1)
    )


class CompanyHesPollRuntime:
    record_type = "hes_read_raw"

    def build_ingest_envelope(
        self,
        session: Session,
        instance: AdapterInstance,
        run: AdapterRun,
    ) -> AdapterIngestEnvelope:
        definition = instance.adapter_definition
        if definition.delivery_mode != "poll":
            raise AdapterExecutionError(
                "unsupported_delivery_mode",
                "The selected adapter implementation only supports polling instances.",
            )
        if definition.record_type != self.record_type:
            raise AdapterExecutionError(
                "unsupported_runtime_record_type",
                "The selected adapter implementation only supports raw read polling.",
            )

        runtime_config = dict(instance.connection_config_masked or {})
        sample_reads = runtime_config.get("sample_reads")
        if not isinstance(sample_reads, list):
            raise AdapterExecutionError(
                "sample_source_not_configured",
                "This provisional polling adapter requires sample_reads in the masked configuration.",
            )

        watermark = _load_adapter_watermark(
            session,
            adapter_instance_id=instance.id,
            record_type=definition.record_type,
        )
        watermark_before = watermark.cursor_value if watermark is not None else None
        watermark_before_dt = None
        if watermark_before is not None:
            watermark_before_dt = _parse_runtime_timestamp(
                watermark_before,
                error_code="invalid_stored_watermark",
                fallback_message="The stored adapter watermark is not a valid ISO timestamp.",
            )

        eligible_rows: list[tuple[datetime, dict[str, Any]]] = []
        for index, row in enumerate(sample_reads):
            if not isinstance(row, dict):
                raise AdapterExecutionError(
                    "invalid_source_row",
                    f"Sample source row at index {index} must be a JSON object.",
                )

            measurement_ts = row.get("measurement_ts", row.get("measured_at"))
            parsed_measurement_ts = _parse_runtime_timestamp(
                measurement_ts,
                error_code="invalid_source_timestamp",
                fallback_message=(
                    f"Sample source row at index {index} must contain an ISO timestamp with timezone."
                ),
            )
            if watermark_before_dt is None or parsed_measurement_ts > watermark_before_dt:
                eligible_rows.append((parsed_measurement_ts, dict(row)))

        eligible_rows.sort(key=lambda row: row[0])
        batch_limit = instance.batch_size or len(eligible_rows)
        selected_rows = eligible_rows[:batch_limit]

        adapter_key = definition.adapter_profile_key or DEFAULT_ADAPTER_KEY
        now = datetime.now(timezone.utc)
        watermark_after = watermark_before
        last_source_timestamp = watermark_before_dt
        if selected_rows:
            last_source_timestamp = selected_rows[-1][0]
            watermark_after = _serialize_datetime(last_source_timestamp)

        return AdapterIngestEnvelope(
            record_type=definition.record_type,
            payload={
                "contract_version": "v1",
                "source_system": instance.source_system,
                "adapter_key": adapter_key,
                "batch_id": f"adapter-{instance.instance_code}-run-{run.id}",
                "received_at": now.isoformat(),
                "reads": [row for _, row in selected_rows],
            },
            source_rows_fetched=len(selected_rows),
            watermark_before=watermark_before,
            watermark_after=watermark_after,
            cursor_type="timestamp",
            last_source_timestamp=last_source_timestamp,
            details={
                "implementation_key": definition.implementation_key,
                "delivery_mode": definition.delivery_mode,
                "record_type": definition.record_type,
                "adapter_key": adapter_key,
                "source_fixture_rows": len(sample_reads),
            },
        )


RUNTIME_ADAPTERS: dict[str, RuntimeAdapter] = {
    "company_hes_poll_v1": CompanyHesPollRuntime(),
}


def list_waiting_adapter_run_ids(
    session: Session,
    *,
    limit: int = 1,
    run_id: int | None = None,
) -> list[int]:
    statement = select(AdapterRun.id).where(AdapterRun.run_status == "waiting")
    if run_id is not None:
        statement = statement.where(AdapterRun.id == run_id)
    statement = statement.order_by(AdapterRun.requested_at.asc(), AdapterRun.id.asc()).limit(limit)
    return list(session.scalars(statement).all())


def _load_adapter_run(session: Session, run_id: int) -> AdapterRun:
    run = session.scalar(
        select(AdapterRun)
        .options(
            joinedload(AdapterRun.adapter_instance).joinedload(AdapterInstance.adapter_definition)
        )
        .where(AdapterRun.id == run_id)
        .limit(1)
    )
    if run is None:
        raise AdapterExecutionError(
            "adapter_run_not_found",
            "The requested adapter run does not exist.",
        )
    return run


def _resolve_runtime(instance: AdapterInstance) -> RuntimeAdapter:
    runtime = RUNTIME_ADAPTERS.get(instance.adapter_definition.implementation_key)
    if runtime is None:
        raise AdapterExecutionError(
            "unsupported_runtime_implementation",
            "No runtime implementation is registered for this adapter definition.",
            details={"implementation_key": instance.adapter_definition.implementation_key},
        )
    return runtime


def _schedule_next_run(instance: AdapterInstance, *, reference_time: datetime) -> datetime | None:
    if instance.adapter_definition.delivery_mode != "poll":
        return instance.next_run_at
    if instance.admin_state != "enabled":
        return None
    if instance.poll_interval_minutes is None:
        return None
    return reference_time.replace(second=0, microsecond=0) + timedelta(
        minutes=instance.poll_interval_minutes
    )


def _claim_adapter_run(session: Session, run: AdapterRun) -> AdapterRun:
    if run.run_status != "waiting":
        raise AdapterExecutionError(
            "adapter_run_not_waiting",
            "Only waiting adapter runs can be executed.",
        )

    active_run = session.scalar(
        select(AdapterRun.id)
        .where(
            AdapterRun.adapter_instance_id == run.adapter_instance_id,
            AdapterRun.id != run.id,
            AdapterRun.run_status == "running",
        )
        .limit(1)
    )
    if active_run is not None:
        raise AdapterExecutionError(
            "adapter_run_already_active",
            "Another adapter run is already active for this instance.",
        )

    started_at = datetime.now(timezone.utc)
    run.run_status = "running"
    run.started_at = started_at
    run.error_code = None
    run.error_summary = None
    run.details = _coerce_details(run.details) | {"claimed_at": started_at.isoformat()}
    run.adapter_instance.last_heartbeat_at = started_at
    session.flush()
    return run


def _upsert_adapter_watermark(
    session: Session,
    *,
    instance: AdapterInstance,
    record_type: str,
    cursor_type: str,
    cursor_value: str | None,
    last_source_timestamp: datetime | None,
    details: dict[str, Any],
    polled_at: datetime,
) -> AdapterWatermark:
    watermark = _load_adapter_watermark(
        session,
        adapter_instance_id=instance.id,
        record_type=record_type,
    )
    if watermark is None:
        watermark = AdapterWatermark(
            adapter_instance_id=instance.id,
            record_type=record_type,
            cursor_type=cursor_type,
            cursor_value=cursor_value,
            last_source_timestamp=last_source_timestamp,
            last_polled_at=polled_at,
            details=details,
        )
        session.add(watermark)
        session.flush()
        return watermark

    watermark.cursor_type = cursor_type
    watermark.cursor_value = cursor_value
    watermark.last_source_timestamp = last_source_timestamp
    watermark.last_polled_at = polled_at
    watermark.details = details
    session.flush()
    return watermark


def _complete_adapter_run(
    session: Session,
    *,
    run: AdapterRun,
    envelope: AdapterIngestEnvelope,
    ingest_batches_created: int,
    ingest_records_created: int,
) -> AdapterRunExecutionResult:
    completed_at = datetime.now(timezone.utc)
    run.run_status = "completed"
    run.completed_at = completed_at
    run.source_rows_fetched = envelope.source_rows_fetched
    run.ingest_batches_created = ingest_batches_created
    run.ingest_records_created = ingest_records_created
    run.watermark_before = envelope.watermark_before
    run.watermark_after = envelope.watermark_after
    run.details = _coerce_details(run.details) | envelope.details | {
        "completed_at": completed_at.isoformat(),
        "source_rows_fetched": envelope.source_rows_fetched,
        "ingest_batches_created": ingest_batches_created,
        "ingest_records_created": ingest_records_created,
    }

    instance = run.adapter_instance
    instance.last_success_at = completed_at
    instance.last_error_message = None
    instance.last_heartbeat_at = completed_at
    instance.next_run_at = _schedule_next_run(instance, reference_time=completed_at)

    _upsert_adapter_watermark(
        session,
        instance=instance,
        record_type=envelope.record_type,
        cursor_type=envelope.cursor_type,
        cursor_value=envelope.watermark_after,
        last_source_timestamp=envelope.last_source_timestamp,
        details={
            "record_type": envelope.record_type,
            "run_id": run.id,
            "source_rows_fetched": envelope.source_rows_fetched,
        },
        polled_at=completed_at,
    )
    session.flush()

    return AdapterRunExecutionResult(
        run_id=run.id,
        run_status=run.run_status,
        source_rows_fetched=envelope.source_rows_fetched,
        ingest_batches_created=ingest_batches_created,
        ingest_records_created=ingest_records_created,
        watermark_before=envelope.watermark_before,
        watermark_after=envelope.watermark_after,
    )


def _fail_adapter_run(
    session: Session,
    *,
    run: AdapterRun,
    error: AdapterExecutionError,
    envelope: AdapterIngestEnvelope | None = None,
) -> AdapterRunExecutionResult:
    completed_at = datetime.now(timezone.utc)
    run.run_status = "failed"
    run.completed_at = completed_at
    run.error_code = error.error_code
    run.error_summary = error.fallback_message
    run.watermark_before = envelope.watermark_before if envelope is not None else run.watermark_before
    run.watermark_after = envelope.watermark_after if envelope is not None else run.watermark_after
    run.details = _coerce_details(run.details) | (error.details or {}) | {
        "failed_at": completed_at.isoformat(),
        "error_code": error.error_code,
    }

    instance = run.adapter_instance
    instance.last_failure_at = completed_at
    instance.last_error_message = error.fallback_message
    instance.last_heartbeat_at = completed_at
    instance.next_run_at = _schedule_next_run(instance, reference_time=completed_at)
    session.flush()

    return AdapterRunExecutionResult(
        run_id=run.id,
        run_status=run.run_status,
        source_rows_fetched=envelope.source_rows_fetched if envelope is not None else 0,
        ingest_batches_created=0,
        ingest_records_created=0,
        watermark_before=envelope.watermark_before if envelope is not None else None,
        watermark_after=envelope.watermark_after if envelope is not None else None,
        error_code=error.error_code,
        error_summary=error.fallback_message,
    )


def execute_adapter_run(session: Session, run_id: int) -> AdapterRunExecutionResult:
    run = _load_adapter_run(session, run_id)
    _claim_adapter_run(session, run)

    envelope: AdapterIngestEnvelope | None = None
    try:
        runtime = _resolve_runtime(run.adapter_instance)
        with session.begin_nested():
            envelope = runtime.build_ingest_envelope(session, run.adapter_instance, run)
            if envelope.record_type == "hes_read_raw":
                ingest_summary = (
                    ingest_reads(
                        session,
                        envelope.payload,
                        adapter_instance_id=run.adapter_instance_id,
                        adapter_run_id=run.id,
                    )
                    if envelope.source_rows_fetched > 0
                    else None
                )
            elif envelope.record_type == "hes_event_raw":
                ingest_summary = (
                    ingest_events(
                        session,
                        envelope.payload,
                        adapter_instance_id=run.adapter_instance_id,
                        adapter_run_id=run.id,
                    )
                    if envelope.source_rows_fetched > 0
                    else None
                )
            else:
                raise AdapterExecutionError(
                    "unsupported_runtime_record_type",
                    "The runtime adapter returned an unsupported record type.",
                    details={"record_type": envelope.record_type},
                )
    except AdapterExecutionError as exc:
        return _fail_adapter_run(session, run=run, error=exc, envelope=envelope)
    except Exception as exc:
        return _fail_adapter_run(
            session,
            run=run,
            error=AdapterExecutionError(
                "runtime_execution_failed",
                "The adapter run failed unexpectedly during execution.",
                details={"exception_type": type(exc).__name__},
            ),
            envelope=envelope,
        )

    ingest_batches_created = 0
    ingest_records_created = 0
    if ingest_summary is not None:
        ingest_batches_created = ingest_summary["batches_created"]
        if envelope.record_type == "hes_read_raw":
            ingest_records_created = ingest_summary["raw_reads_received"]
        else:
            ingest_records_created = ingest_summary["raw_events_received"]

    return _complete_adapter_run(
        session,
        run=run,
        envelope=envelope,
        ingest_batches_created=ingest_batches_created,
        ingest_records_created=ingest_records_created,
    )


def process_waiting_adapter_runs(
    session: Session,
    *,
    limit: int = 1,
    run_id: int | None = None,
) -> AdapterRunProcessingSummary:
    if limit < 1:
        raise ValueError("limit must be at least 1")

    run_ids = list_waiting_adapter_run_ids(session, limit=limit, run_id=run_id)
    results = [execute_adapter_run(session, candidate_run_id) for candidate_run_id in run_ids]
    completed = sum(1 for row in results if row.run_status == "completed")
    failed = sum(1 for row in results if row.run_status == "failed")
    return AdapterRunProcessingSummary(
        processed=len(results),
        completed=completed,
        failed=failed,
        results=results,
    )
