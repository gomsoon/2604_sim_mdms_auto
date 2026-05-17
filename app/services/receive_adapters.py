from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import AdapterInstance, AdapterRun
from app.services.adapters import sync_adapter_health_alerts
from app.services.ingest_contract import IngestContractError, validate_ingest_envelope
from app.services.ingestion import ingest_events, ingest_reads
from app.services.operational_events import record_operational_event


@dataclass(slots=True)
class ReceiveAdapterError(ValueError):
    error_code: str
    fallback_message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.fallback_message


def _resolve_env_secret(secret_ref: str | None) -> str:
    normalized = str(secret_ref or "").strip()
    if not normalized:
        raise ReceiveAdapterError(
            "receive_adapter_secret_invalid",
            "Receive adapter secret_ref is not configured.",
        )
    if not normalized.startswith("env://"):
        raise ReceiveAdapterError(
            "receive_adapter_secret_invalid",
            "Receive adapter secret_ref must use env://VARIABLE_NAME format.",
        )

    env_name = normalized.removeprefix("env://").strip()
    if not env_name:
        raise ReceiveAdapterError(
            "receive_adapter_secret_invalid",
            "Receive adapter secret_ref must include an environment variable name.",
        )

    value = os.getenv(env_name)
    if not value:
        raise ReceiveAdapterError(
            "receive_adapter_secret_invalid",
            "Receive adapter secret_ref points to an environment variable that is not set.",
        )
    return value


def _load_receive_adapter_instance(
    session: Session,
    *,
    instance_code: str,
    record_type: str,
) -> AdapterInstance:
    instance = session.scalar(
        select(AdapterInstance)
        .options(
            joinedload(AdapterInstance.adapter_definition),
            joinedload(AdapterInstance.hes_system),
        )
        .where(AdapterInstance.instance_code == instance_code)
        .limit(1)
    )
    if instance is None:
        raise ReceiveAdapterError(
            "receive_adapter_not_found",
            "The selected receive adapter instance does not exist.",
            status_code=404,
        )
    if instance.adapter_definition.delivery_mode != "receive":
        raise ReceiveAdapterError(
            "receive_delivery_mode_required",
            "The selected adapter instance is not configured for receive mode.",
        )
    if instance.adapter_definition.record_type != record_type:
        raise ReceiveAdapterError(
            "receive_record_type_mismatch",
            "The selected receive adapter does not accept this record type.",
        )
    if instance.admin_state != "enabled":
        raise ReceiveAdapterError(
            "receive_adapter_not_enabled",
            "The selected receive adapter instance is not enabled.",
            status_code=409,
        )
    return instance


def _authorize_receive_adapter(
    instance: AdapterInstance,
    *,
    shared_secret: str | None,
) -> None:
    if not instance.secret_ref:
        return
    expected_secret = _resolve_env_secret(instance.secret_ref)
    if not shared_secret or shared_secret != expected_secret:
        raise ReceiveAdapterError(
            "receive_adapter_unauthorized",
            "The receive adapter secret is missing or invalid.",
            status_code=403,
        )


def _prepare_receive_payload(
    payload: dict[str, Any],
    *,
    source_system: str,
) -> dict[str, Any]:
    effective_payload = dict(payload)
    incoming_source_system = str(effective_payload.get("source_system") or "").strip()
    if incoming_source_system and incoming_source_system != source_system:
        raise ReceiveAdapterError(
            "receive_source_system_mismatch",
            "Receive payload source_system must match the adapter instance source system.",
        )
    effective_payload["source_system"] = source_system
    return effective_payload


def _start_receive_run(
    session: Session,
    *,
    instance: AdapterInstance,
    record_type: str,
    requested_at: datetime,
) -> AdapterRun:
    run = AdapterRun(
        adapter_instance_id=instance.id,
        requested_by="receive_adapter",
        requested_by_user_account_id=None,
        trigger_type="receive",
        run_status="running",
        requested_at=requested_at,
        started_at=requested_at,
        details={
            "record_type": record_type,
            "delivery_mode": instance.adapter_definition.delivery_mode,
            "requested_by": "receive_adapter",
            "requested_by_user_account_id": None,
            "requested_via": "receive_adapter",
        },
    )
    session.add(run)
    session.flush()
    record_operational_event(
        session,
        "adapter_run_started",
        occurred_at=requested_at,
        adapter_instance=instance,
        adapter_run=run,
        details={"record_type": record_type, "trigger_type": "receive"},
        instance_code=instance.instance_code,
    )
    return run


def _complete_receive_run(
    session: Session,
    *,
    instance: AdapterInstance,
    run: AdapterRun,
    record_type: str,
    ingest_summary: dict[str, int],
    completed_at: datetime,
) -> None:
    run.run_status = "completed"
    run.completed_at = completed_at
    run.source_rows_fetched = ingest_summary.get("raw_reads_received") or ingest_summary.get(
        "raw_events_received"
    )
    run.ingest_batches_created = ingest_summary.get("batches_created")
    run.ingest_records_created = run.source_rows_fetched
    run.details = {
        **dict(run.details or {}),
        "record_type": record_type,
        "ingest_summary": dict(ingest_summary),
    }
    instance.last_success_at = completed_at
    instance.last_heartbeat_at = completed_at
    instance.last_error_message = None
    record_operational_event(
        session,
        "adapter_run_completed",
        occurred_at=completed_at,
        adapter_instance=instance,
        adapter_run=run,
        details={"record_type": record_type, "trigger_type": "receive"},
        instance_code=instance.instance_code,
        source_rows_fetched=run.source_rows_fetched or 0,
        ingest_batches_created=run.ingest_batches_created or 0,
        ingest_records_created=run.ingest_records_created or 0,
    )
    sync_adapter_health_alerts(session, adapter_instance_ids=[instance.id], as_of=completed_at)


def _fail_receive_run(
    session: Session,
    *,
    instance: AdapterInstance,
    run: AdapterRun,
    record_type: str,
    error_code: str,
    error_summary: str,
    completed_at: datetime,
) -> None:
    run.run_status = "failed"
    run.completed_at = completed_at
    run.error_code = error_code
    run.error_summary = error_summary
    run.details = {
        **dict(run.details or {}),
        "record_type": record_type,
        "error_code": error_code,
    }
    instance.last_failure_at = completed_at
    instance.last_heartbeat_at = completed_at
    instance.last_error_message = error_summary
    record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=completed_at,
        adapter_instance=instance,
        adapter_run=run,
        details={"record_type": record_type, "trigger_type": "receive"},
        instance_code=instance.instance_code,
        error_summary=error_summary,
    )
    sync_adapter_health_alerts(session, adapter_instance_ids=[instance.id], as_of=completed_at)


def receive_adapter_payload(
    session: Session,
    *,
    instance_code: str,
    record_type: str,
    payload: dict[str, Any],
    shared_secret: str | None = None,
) -> dict[str, Any]:
    instance = _load_receive_adapter_instance(
        session,
        instance_code=instance_code,
        record_type=record_type,
    )
    _authorize_receive_adapter(instance, shared_secret=shared_secret)

    effective_payload = _prepare_receive_payload(payload, source_system=instance.source_system)
    validate_ingest_envelope(session, effective_payload, record_type=record_type)

    requested_at = datetime.now(timezone.utc)
    run = _start_receive_run(
        session,
        instance=instance,
        record_type=record_type,
        requested_at=requested_at,
    )

    try:
        if record_type == "hes_read_raw":
            ingest_summary = ingest_reads(
                session,
                effective_payload,
                hes_system_id=instance.hes_system_id,
                adapter_instance_id=instance.id,
                adapter_run_id=run.id,
            )
        elif record_type == "hes_event_raw":
            ingest_summary = ingest_events(
                session,
                effective_payload,
                hes_system_id=instance.hes_system_id,
                adapter_instance_id=instance.id,
                adapter_run_id=run.id,
            )
        else:
            raise ReceiveAdapterError(
                "receive_record_type_mismatch",
                "The selected receive adapter does not accept this record type.",
            )
    except IngestContractError:
        raise
    except Exception as exc:
        completed_at = datetime.now(timezone.utc)
        _fail_receive_run(
            session,
            instance=instance,
            run=run,
            record_type=record_type,
            error_code="receive_request_failed",
            error_summary=str(exc),
            completed_at=completed_at,
        )
        raise

    completed_at = datetime.now(timezone.utc)
    _complete_receive_run(
        session,
        instance=instance,
        run=run,
        record_type=record_type,
        ingest_summary=ingest_summary,
        completed_at=completed_at,
    )
    return {
        **ingest_summary,
        "adapter_run_id": run.id,
        "adapter_instance_id": instance.id,
        "trigger_type": "receive",
    }
