from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AdapterInstance,
    AdapterRun,
    HesSystem,
    IngestBatch,
    IngestErrorLog,
    OperationalEvent,
    PipelineRun,
    ReprocessRequest,
)


@dataclass(frozen=True, slots=True)
class OperationalEventSpec:
    source_layer: str
    event_category: str
    severity: str
    is_alert: bool
    title_en: str
    title_ko: str
    message_en: str
    message_ko: str


@dataclass(frozen=True, slots=True)
class OperationalAlertError(Exception):
    error_code: str
    fallback_message: str


EVENT_SPECS: dict[str, OperationalEventSpec] = {
    "adapter_enabled": OperationalEventSpec(
        source_layer="operator_action",
        event_category="adapter_lifecycle",
        severity="info",
        is_alert=False,
        title_en="Adapter enabled",
        title_ko="어댑터 활성화",
        message_en="Adapter {instance_code} was enabled for runtime collection.",
        message_ko="어댑터 {instance_code}가 수집 실행 가능 상태로 활성화되었습니다.",
    ),
    "adapter_paused": OperationalEventSpec(
        source_layer="operator_action",
        event_category="adapter_lifecycle",
        severity="warning",
        is_alert=False,
        title_en="Adapter paused",
        title_ko="어댑터 일시중지",
        message_en="Adapter {instance_code} was paused for future scheduled collection.",
        message_ko="어댑터 {instance_code}가 향후 스케줄 실행 대상에서 일시중지되었습니다.",
    ),
    "adapter_run_queued": OperationalEventSpec(
        source_layer="integration",
        event_category="adapter_run",
        severity="info",
        is_alert=False,
        title_en="Adapter run queued",
        title_ko="어댑터 실행 대기 등록",
        message_en="Adapter {instance_code} was queued for execution.",
        message_ko="어댑터 {instance_code} 실행이 대기열에 등록되었습니다.",
    ),
    "adapter_run_started": OperationalEventSpec(
        source_layer="integration",
        event_category="adapter_run",
        severity="info",
        is_alert=False,
        title_en="Adapter run started",
        title_ko="어댑터 실행 시작",
        message_en="Adapter {instance_code} started runtime execution.",
        message_ko="어댑터 {instance_code}의 런타임 실행이 시작되었습니다.",
    ),
    "adapter_run_completed": OperationalEventSpec(
        source_layer="integration",
        event_category="adapter_run",
        severity="info",
        is_alert=False,
        title_en="Adapter run completed",
        title_ko="어댑터 실행 완료",
        message_en=(
            "Adapter {instance_code} completed successfully. "
            "Source rows: {source_rows_fetched}, ingest batches: {ingest_batches_created}, ingest records: {ingest_records_created}."
        ),
        message_ko=(
            "어댑터 {instance_code} 실행이 완료되었습니다. "
            "원천 행 수: {source_rows_fetched}, 적재 배치 수: {ingest_batches_created}, 적재 레코드 수: {ingest_records_created}."
        ),
    ),
    "adapter_run_failed": OperationalEventSpec(
        source_layer="integration",
        event_category="adapter_run",
        severity="error",
        is_alert=True,
        title_en="Adapter run failed",
        title_ko="어댑터 실행 실패",
        message_en="Adapter {instance_code} failed: {error_summary}.",
        message_ko="어댑터 {instance_code} 실행이 실패했습니다: {error_summary}.",
    ),
    "adapter_overdue_detected": OperationalEventSpec(
        source_layer="integration",
        event_category="adapter_health",
        severity="warning",
        is_alert=True,
        title_en="Adapter overdue",
        title_ko="어댑터 실행 지연",
        message_en="Adapter {instance_code} is overdue. Scheduled run time was {next_run_at}.",
        message_ko="어댑터 {instance_code} 실행이 지연되었습니다. 예정 시각은 {next_run_at}였습니다.",
    ),
    "adapter_stale_detected": OperationalEventSpec(
        source_layer="integration",
        event_category="adapter_health",
        severity="warning",
        is_alert=True,
        title_en="Adapter stale",
        title_ko="어댑터 신선도 저하",
        message_en="Adapter {instance_code} is stale. Last heartbeat was {last_heartbeat_at}.",
        message_ko="어댑터 {instance_code} 신선도가 저하되었습니다. 마지막 heartbeat는 {last_heartbeat_at}였습니다.",
    ),
    "hes_meter_reference_missing_device_detected": OperationalEventSpec(
        source_layer="master_data",
        event_category="meter_reference_mapping",
        severity="warning",
        is_alert=True,
        title_en="HES meter reference missing device",
        title_ko="HES 계량기 참조 장치 누락",
        message_en="HES meter reference {source_meter_id} is missing a canonical device mapping.",
        message_ko="HES 계량기 참조 {source_meter_id}에 연결된 canonical 장치가 없습니다.",
    ),
    "hes_meter_reference_missing_component_detected": OperationalEventSpec(
        source_layer="master_data",
        event_category="meter_reference_mapping",
        severity="warning",
        is_alert=True,
        title_en="HES meter reference missing component",
        title_ko="HES 계량기 참조 컴포넌트 누락",
        message_en="HES meter reference {source_meter_id} is missing an active canonical component.",
        message_ko="HES 계량기 참조 {source_meter_id}에 활성 canonical 컴포넌트가 없습니다.",
    ),
    "hes_meter_reference_missing_installation_detected": OperationalEventSpec(
        source_layer="master_data",
        event_category="meter_reference_mapping",
        severity="warning",
        is_alert=True,
        title_en="HES meter reference missing installation",
        title_ko="HES 계량기 참조 설치 누락",
        message_en="HES meter reference {source_meter_id} is missing an active installation mapping.",
        message_ko="HES 계량기 참조 {source_meter_id}에 활성 설치 매핑이 없습니다.",
    ),
    "ingest_batch_accepted": OperationalEventSpec(
        source_layer="ingest",
        event_category="ingest_batch",
        severity="info",
        is_alert=False,
        title_en="Ingest batch accepted",
        title_ko="적재 배치 수락",
        message_en="Batch {batch_id} was accepted for ingest.",
        message_ko="배치 {batch_id}가 적재 대상으로 수락되었습니다.",
    ),
    "raw_ingest_completed": OperationalEventSpec(
        source_layer="ingest",
        event_category="pipeline_run",
        severity="info",
        is_alert=False,
        title_en="Raw ingest completed",
        title_ko="원시 적재 완료",
        message_en="Raw ingest completed for batch {batch_id}.",
        message_ko="배치 {batch_id}의 원시 적재가 완료되었습니다.",
    ),
    "raw_ingest_failed": OperationalEventSpec(
        source_layer="ingest",
        event_category="pipeline_run",
        severity="error",
        is_alert=True,
        title_en="Raw ingest requires attention",
        title_ko="원시 적재 주의 필요",
        message_en="Raw ingest for batch {batch_id} completed with issues.",
        message_ko="배치 {batch_id}의 원시 적재가 문제를 포함한 상태로 끝났습니다.",
    ),
    "canonical_completed": OperationalEventSpec(
        source_layer="processing",
        event_category="pipeline_run",
        severity="info",
        is_alert=False,
        title_en="Canonical processing completed",
        title_ko="표준화 완료",
        message_en="Canonical processing completed for batch {batch_id}.",
        message_ko="배치 {batch_id}의 표준화가 완료되었습니다.",
    ),
    "canonical_failed": OperationalEventSpec(
        source_layer="processing",
        event_category="pipeline_run",
        severity="error",
        is_alert=True,
        title_en="Canonical processing requires attention",
        title_ko="표준화 주의 필요",
        message_en="Canonical processing for batch {batch_id} completed with issues.",
        message_ko="배치 {batch_id}의 표준화가 문제를 포함한 상태로 끝났습니다.",
    ),
    "vee_exception_opened": OperationalEventSpec(
        source_layer="processing",
        event_category="vee_exception",
        severity="error",
        is_alert=True,
        title_en="VEE exception opened",
        title_ko="VEE 예외 발생",
        message_en="VEE exception {exception_code} opened for initial measurement {initial_measurement_id}.",
        message_ko="초기 계측 {initial_measurement_id}에 대해 VEE 예외 {exception_code}가 발생했습니다.",
    ),
    "vee_exception_resolved": OperationalEventSpec(
        source_layer="operator_action",
        event_category="vee_exception",
        severity="info",
        is_alert=False,
        title_en="VEE exception resolved",
        title_ko="VEE 예외 해결",
        message_en="VEE exception {exception_code} was resolved with {resolution_type}.",
        message_ko="VEE 예외 {exception_code}가 {resolution_type} 방식으로 해결되었습니다.",
    ),
    "finalization_completed": OperationalEventSpec(
        source_layer="processing",
        event_category="finalization",
        severity="info",
        is_alert=False,
        title_en="Finalization completed",
        title_ko="최종화 완료",
        message_en="Finalization completed successfully.",
        message_ko="최종화가 완료되었습니다.",
    ),
    "finalization_failed": OperationalEventSpec(
        source_layer="processing",
        event_category="finalization",
        severity="error",
        is_alert=True,
        title_en="Finalization requires attention",
        title_ko="최종화 주의 필요",
        message_en="Finalization completed with issues.",
        message_ko="최종화가 문제를 포함한 상태로 끝났습니다.",
    ),
    "exception_reprocess_completed": OperationalEventSpec(
        source_layer="processing",
        event_category="exception_reprocess",
        severity="info",
        is_alert=False,
        title_en="Exception reprocess completed",
        title_ko="오류 재처리 완료",
        message_en="Exception reprocess completed successfully.",
        message_ko="오류 재처리가 완료되었습니다.",
    ),
    "exception_reprocess_failed": OperationalEventSpec(
        source_layer="processing",
        event_category="exception_reprocess",
        severity="error",
        is_alert=True,
        title_en="Exception reprocess requires attention",
        title_ko="오류 재처리 주의 필요",
        message_en="Exception reprocess failed or remained unresolved.",
        message_ko="오류 재처리가 실패했거나 아직 해결되지 않았습니다.",
    ),
}


def _format_message(template: str, **kwargs: object) -> str:
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def _infer_hes_system_id(
    *,
    hes_system: HesSystem | None,
    adapter_instance: AdapterInstance | None,
    adapter_run: AdapterRun | None,
    pipeline_run: PipelineRun | None,
    ingest_batch: IngestBatch | None,
    ingest_error_log: IngestErrorLog | None,
    reprocess_request: ReprocessRequest | None,
) -> int | None:
    if hes_system is not None:
        return hes_system.id
    if ingest_batch is not None and ingest_batch.hes_system_id is not None:
        return ingest_batch.hes_system_id
    if adapter_instance is not None and adapter_instance.hes_system_id is not None:
        return adapter_instance.hes_system_id
    if adapter_run is not None:
        if adapter_run.adapter_instance is not None and adapter_run.adapter_instance.hes_system_id is not None:
            return adapter_run.adapter_instance.hes_system_id
    if pipeline_run is not None:
        if pipeline_run.ingest_batch is not None and pipeline_run.ingest_batch.hes_system_id is not None:
            return pipeline_run.ingest_batch.hes_system_id
        if (
            pipeline_run.reprocess_request is not None
            and pipeline_run.reprocess_request.hes_read_raw is not None
            and pipeline_run.reprocess_request.hes_read_raw.hes_system_id is not None
        ):
            return pipeline_run.reprocess_request.hes_read_raw.hes_system_id
    if reprocess_request is not None and reprocess_request.hes_read_raw.hes_system_id is not None:
        return reprocess_request.hes_read_raw.hes_system_id
    if ingest_error_log is not None:
        if ingest_error_log.hes_read_raw is not None and ingest_error_log.hes_read_raw.hes_system_id is not None:
            return ingest_error_log.hes_read_raw.hes_system_id
        if ingest_error_log.hes_event_raw is not None and ingest_error_log.hes_event_raw.hes_system_id is not None:
            return ingest_error_log.hes_event_raw.hes_system_id
    return None


def record_operational_event(
    session: Session,
    event_code: str,
    *,
    occurred_at: datetime | None = None,
    details: dict[str, Any] | None = None,
    source_layer: str | None = None,
    event_category: str | None = None,
    severity: str | None = None,
    is_alert: bool | None = None,
    alert_status: str | None = None,
    opened_at: datetime | None = None,
    acknowledged_at: datetime | None = None,
    acknowledged_by: str | None = None,
    closed_at: datetime | None = None,
    operator_memo: str | None = None,
    title_en: str | None = None,
    title_ko: str | None = None,
    message_en: str | None = None,
    message_ko: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    hes_system: HesSystem | None = None,
    adapter_instance: AdapterInstance | None = None,
    adapter_run: AdapterRun | None = None,
    pipeline_run: PipelineRun | None = None,
    ingest_batch: IngestBatch | None = None,
    ingest_error_log: IngestErrorLog | None = None,
    reprocess_request: ReprocessRequest | None = None,
    meter_identifier: str | None = None,
    batch_id: str | None = None,
    **message_kwargs: object,
) -> OperationalEvent:
    spec = EVENT_SPECS.get(event_code)
    if spec is None:
        raise ValueError(f"Unknown operational event code: {event_code}")

    effective_occurred_at = occurred_at or datetime.now(timezone.utc)
    effective_is_alert = spec.is_alert if is_alert is None else is_alert
    effective_alert_status = alert_status
    effective_opened_at = opened_at
    if effective_is_alert:
        effective_alert_status = effective_alert_status or "open"
        effective_opened_at = effective_opened_at or effective_occurred_at
    else:
        effective_alert_status = None
        effective_opened_at = None
        acknowledged_at = None
        acknowledged_by = None
        closed_at = None
        operator_memo = None

    effective_title_en = title_en or spec.title_en
    effective_title_ko = title_ko or spec.title_ko
    effective_message_en = message_en or _format_message(spec.message_en, **message_kwargs)
    effective_message_ko = message_ko or _format_message(spec.message_ko, **message_kwargs)

    if entity_type is None or entity_id is None:
        if adapter_run is not None:
            entity_type = entity_type or "adapter_run"
            entity_id = entity_id or adapter_run.id
        elif pipeline_run is not None:
            entity_type = entity_type or "pipeline_run"
            entity_id = entity_id or pipeline_run.id
        elif ingest_error_log is not None:
            entity_type = entity_type or "ingest_error_log"
            entity_id = entity_id or ingest_error_log.id
        elif ingest_batch is not None:
            entity_type = entity_type or "ingest_batch"
            entity_id = entity_id or ingest_batch.id
        elif adapter_instance is not None:
            entity_type = entity_type or "adapter_instance"
            entity_id = entity_id or adapter_instance.id
        elif reprocess_request is not None:
            entity_type = entity_type or "reprocess_request"
            entity_id = entity_id or reprocess_request.id

    hes_system_id = _infer_hes_system_id(
        hes_system=hes_system,
        adapter_instance=adapter_instance,
        adapter_run=adapter_run,
        pipeline_run=pipeline_run,
        ingest_batch=ingest_batch,
        ingest_error_log=ingest_error_log,
        reprocess_request=reprocess_request,
    )

    event = OperationalEvent(
        occurred_at=effective_occurred_at,
        source_layer=source_layer or spec.source_layer,
        event_category=event_category or spec.event_category,
        event_code=event_code,
        severity=severity or spec.severity,
        is_alert=effective_is_alert,
        alert_status=effective_alert_status,
        opened_at=effective_opened_at,
        acknowledged_at=acknowledged_at,
        acknowledged_by=acknowledged_by,
        closed_at=closed_at,
        operator_memo=operator_memo,
        title_en=effective_title_en,
        title_ko=effective_title_ko,
        message_en=effective_message_en,
        message_ko=effective_message_ko,
        entity_type=entity_type,
        entity_id=entity_id,
        hes_system_id=hes_system_id,
        adapter_instance_id=adapter_instance.id if adapter_instance is not None else None,
        adapter_run_id=adapter_run.id if adapter_run is not None else None,
        pipeline_run_id=pipeline_run.id if pipeline_run is not None else None,
        ingest_batch_id=ingest_batch.id if ingest_batch is not None else None,
        ingest_error_log_id=ingest_error_log.id if ingest_error_log is not None else None,
        reprocess_request_id=reprocess_request.id if reprocess_request is not None else None,
        meter_identifier=meter_identifier,
        batch_id=batch_id or (ingest_batch.batch_id if ingest_batch is not None else None),
        details=details or {},
    )
    session.add(event)
    session.flush()
    return event


def close_operational_alerts(
    session: Session,
    *,
    event_code: str,
    adapter_instance_id: int | None = None,
    adapter_run_id: int | None = None,
    pipeline_run_id: int | None = None,
    ingest_batch_id: int | None = None,
    ingest_error_log_id: int | None = None,
    reprocess_request_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    closed_at: datetime | None = None,
    operator_memo: str | None = None,
) -> int:
    statement = select(OperationalEvent).where(
        OperationalEvent.is_alert.is_(True),
        OperationalEvent.event_code == event_code,
        OperationalEvent.alert_status.in_(("open", "acknowledged")),
    )
    if adapter_instance_id is not None:
        statement = statement.where(OperationalEvent.adapter_instance_id == adapter_instance_id)
    if adapter_run_id is not None:
        statement = statement.where(OperationalEvent.adapter_run_id == adapter_run_id)
    if pipeline_run_id is not None:
        statement = statement.where(OperationalEvent.pipeline_run_id == pipeline_run_id)
    if ingest_batch_id is not None:
        statement = statement.where(OperationalEvent.ingest_batch_id == ingest_batch_id)
    if ingest_error_log_id is not None:
        statement = statement.where(OperationalEvent.ingest_error_log_id == ingest_error_log_id)
    if reprocess_request_id is not None:
        statement = statement.where(OperationalEvent.reprocess_request_id == reprocess_request_id)
    if entity_type is not None:
        statement = statement.where(OperationalEvent.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(OperationalEvent.entity_id == entity_id)

    rows = session.scalars(statement).all()
    effective_closed_at = closed_at or datetime.now(timezone.utc)
    for row in rows:
        row.alert_status = "closed"
        row.closed_at = effective_closed_at
        if operator_memo:
            row.operator_memo = operator_memo
    session.flush()
    return len(rows)


def acknowledge_operational_alerts(
    session: Session,
    *,
    event_code: str,
    acknowledged_by: str,
    adapter_instance_id: int | None = None,
    adapter_run_id: int | None = None,
    pipeline_run_id: int | None = None,
    ingest_batch_id: int | None = None,
    ingest_error_log_id: int | None = None,
    reprocess_request_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    acknowledged_at: datetime | None = None,
) -> int:
    statement = select(OperationalEvent).where(
        OperationalEvent.is_alert.is_(True),
        OperationalEvent.event_code == event_code,
        OperationalEvent.alert_status == "open",
    )
    if adapter_instance_id is not None:
        statement = statement.where(OperationalEvent.adapter_instance_id == adapter_instance_id)
    if adapter_run_id is not None:
        statement = statement.where(OperationalEvent.adapter_run_id == adapter_run_id)
    if pipeline_run_id is not None:
        statement = statement.where(OperationalEvent.pipeline_run_id == pipeline_run_id)
    if ingest_batch_id is not None:
        statement = statement.where(OperationalEvent.ingest_batch_id == ingest_batch_id)
    if ingest_error_log_id is not None:
        statement = statement.where(OperationalEvent.ingest_error_log_id == ingest_error_log_id)
    if reprocess_request_id is not None:
        statement = statement.where(OperationalEvent.reprocess_request_id == reprocess_request_id)
    if entity_type is not None:
        statement = statement.where(OperationalEvent.entity_type == entity_type)
    if entity_id is not None:
        statement = statement.where(OperationalEvent.entity_id == entity_id)

    rows = session.scalars(statement).all()
    effective_acknowledged_at = acknowledged_at or datetime.now(timezone.utc)
    for row in rows:
        row.alert_status = "acknowledged"
        row.acknowledged_at = effective_acknowledged_at
        row.acknowledged_by = acknowledged_by
    session.flush()
    return len(rows)


def _get_operational_alert(session: Session, event_id: int) -> OperationalEvent:
    event = session.get(OperationalEvent, event_id)
    if event is None:
        raise OperationalAlertError(
            "not_found", "The selected operational alert does not exist."
        )
    if not event.is_alert:
        raise OperationalAlertError("not_alert", "The selected operational event is not an alert.")
    return event


def acknowledge_operational_alert(
    session: Session,
    event_id: int,
    *,
    acknowledged_by: str,
    acknowledged_at: datetime | None = None,
) -> OperationalEvent:
    event = _get_operational_alert(session, event_id)
    if event.alert_status == "closed":
        raise OperationalAlertError("already_closed", "The selected alert is already closed.")
    if event.alert_status == "acknowledged":
        raise OperationalAlertError(
            "already_acknowledged", "The selected alert is already acknowledged."
        )

    event.alert_status = "acknowledged"
    event.acknowledged_at = acknowledged_at or datetime.now(timezone.utc)
    event.acknowledged_by = acknowledged_by
    session.flush()
    return event


def close_operational_alert(
    session: Session,
    event_id: int,
    *,
    closed_at: datetime | None = None,
    operator_memo: str | None = None,
) -> OperationalEvent:
    event = _get_operational_alert(session, event_id)
    if event.alert_status == "closed":
        raise OperationalAlertError("already_closed", "The selected alert is already closed.")

    event.alert_status = "closed"
    event.closed_at = closed_at or datetime.now(timezone.utc)
    normalized_memo = (operator_memo or "").strip()
    if normalized_memo:
        event.operator_memo = normalized_memo
    session.flush()
    return event
