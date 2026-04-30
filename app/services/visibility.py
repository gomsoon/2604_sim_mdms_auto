from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import get_app_timezone_name
from app.models import (
    AdapterInstance,
    AdapterRun,
    CanonicalMeasurement,
    FinalMeasurement,
    HesReadRaw,
    InitialMeasurement,
    IngestBatch,
    IngestErrorLog,
    MeasuringComponent,
    OperationalEvent,
    PipelineRun,
    ReprocessRequest,
    ServicePoint,
    UsageTransaction,
    VeeException,
    VeeExecutionLog,
)


@dataclass(slots=True)
class VisibilityFilterError(ValueError):
    error_code: str
    fallback_message: str

    def __str__(self) -> str:
        return self.fallback_message


@dataclass(frozen=True, slots=True)
class IngestBatchFilters:
    batch_id: str | None = None
    source_system: str | None = None
    record_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class CanonicalMeasurementFilters:
    batch_id: str | None = None
    meter_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class FinalMeasurementFilters:
    batch_id: str | None = None
    meter_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class OperationalEventFilters:
    stream_type: str | None = None
    hes_system_id: int | None = None
    source_layer: str | None = None
    severity: str | None = None
    event_code: str | None = None
    alert_status: str | None = None
    batch_id: str | None = None
    meter_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class UsageTransactionFilters:
    usage_transaction_id: int | None = None
    service_point_id: int | None = None
    measuring_component_id: int | None = None
    service_point: str | None = None
    external_channel_id: str | None = None
    usage_type: str | None = None
    calculation_status: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class VeeExceptionFilters:
    hes_system_id: int | None = None
    exception_status: str | None = None
    exception_code: str | None = None
    severity: str | None = None
    meter_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class OperationalEventDetailContext:
    event: OperationalEvent
    adapter_instance: AdapterInstance | None = None
    adapter_run: AdapterRun | None = None
    pipeline_run: PipelineRun | None = None
    ingest_batch: IngestBatch | None = None
    ingest_error_log: IngestErrorLog | None = None
    reprocess_request: ReprocessRequest | None = None
    initial_measurement: InitialMeasurement | None = None
    vee_execution_log: VeeExecutionLog | None = None
    vee_exception: VeeException | None = None
    raw_rows: list[HesReadRaw] = ()
    canonical_rows: list[CanonicalMeasurement] = ()
    final_rows: list[FinalMeasurement] = ()


@dataclass(frozen=True, slots=True)
class VeeExceptionDetailContext:
    vee_exception: VeeException
    initial_measurement: InitialMeasurement
    canonical_measurement: CanonicalMeasurement
    raw_row: HesReadRaw | None = None
    ingest_batch: IngestBatch | None = None
    vee_execution_log: VeeExecutionLog | None = None
    final_measurement: FinalMeasurement | None = None


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = str(value).strip()
    return stripped or None


def _parse_optional_int(value: str | None, *, error_code: str, fallback_message: str) -> int | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        parsed = int(normalized)
    except ValueError as exc:
        raise VisibilityFilterError(error_code, fallback_message) from exc
    if parsed <= 0:
        raise VisibilityFilterError(error_code, fallback_message)
    return parsed


def _parse_filter_datetime(value: str | None, *, end_of_day: bool = False) -> datetime | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None

    try:
        if len(normalized) == 10:
            date_value = datetime.fromisoformat(normalized).date()
            boundary_time = time.max if end_of_day else time.min
            local_tz = _get_filter_timezone()
            return datetime.combine(date_value, boundary_time, tzinfo=local_tz).astimezone(
                timezone.utc
            )

        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise VisibilityFilterError(
            "invalid_date_filter", "Date filters must use ISO date or datetime format."
        ) from exc


def _get_filter_timezone():
    try:
        return ZoneInfo(get_app_timezone_name())
    except ZoneInfoNotFoundError:
        return timezone.utc


def build_ingest_batch_filters(args) -> IngestBatchFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    return IngestBatchFilters(
        batch_id=_normalize_text(args.get("batch_id")),
        source_system=_normalize_text(args.get("source_system")),
        record_type=_normalize_text(args.get("record_type")),
        date_from=date_from,
        date_to=date_to,
    )


def build_canonical_filters(args) -> CanonicalMeasurementFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    return CanonicalMeasurementFilters(
        batch_id=_normalize_text(args.get("batch_id")),
        meter_id=_normalize_text(args.get("meter_id")),
        date_from=date_from,
        date_to=date_to,
    )


def build_final_filters(args) -> FinalMeasurementFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    return FinalMeasurementFilters(
        batch_id=_normalize_text(args.get("batch_id")),
        meter_id=_normalize_text(args.get("meter_id")),
        date_from=date_from,
        date_to=date_to,
    )


def build_usage_transaction_filters(args) -> UsageTransactionFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    usage_type = _normalize_text(args.get("usage_type"))
    if usage_type not in {None, "daily_consumption", "monthly_consumption"}:
        raise VisibilityFilterError(
            "invalid_usage_type_filter",
            "Usage type must be daily_consumption or monthly_consumption when provided.",
        )

    calculation_status = _normalize_text(args.get("calculation_status"))
    if calculation_status not in {None, "complete", "partial", "blocked"}:
        raise VisibilityFilterError(
            "invalid_usage_calculation_status_filter",
            "Calculation status must be complete, partial, or blocked when provided.",
        )

    return UsageTransactionFilters(
        usage_transaction_id=_parse_optional_int(
            args.get("usage_transaction_id"),
            error_code="invalid_usage_transaction_filter",
            fallback_message="Usage transaction filter must be a positive integer.",
        ),
        service_point_id=_parse_optional_int(
            args.get("service_point_id"),
            error_code="invalid_service_point_filter",
            fallback_message="Service point filter must be a positive integer.",
        ),
        measuring_component_id=_parse_optional_int(
            args.get("measuring_component_id"),
            error_code="invalid_measuring_component_filter",
            fallback_message="Measuring component filter must be a positive integer.",
        ),
        service_point=_normalize_text(args.get("service_point")),
        external_channel_id=_normalize_text(args.get("external_channel_id")),
        usage_type=usage_type,
        calculation_status=calculation_status,
        date_from=date_from,
        date_to=date_to,
    )


def build_operational_event_filters(args) -> OperationalEventFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    stream_type = _normalize_text(args.get("stream_type"))
    if stream_type not in {None, "event", "alert"}:
        raise VisibilityFilterError(
            "invalid_stream_type", "Stream type must be event or alert when provided."
        )

    return OperationalEventFilters(
        stream_type=stream_type,
        hes_system_id=_parse_optional_int(
            args.get("hes_system_id"),
            error_code="invalid_hes_system_filter",
            fallback_message="HES system filter must be a positive integer.",
        ),
        source_layer=_normalize_text(args.get("source_layer")),
        severity=_normalize_text(args.get("severity")),
        event_code=_normalize_text(args.get("event_code")),
        alert_status=_normalize_text(args.get("alert_status")),
        batch_id=_normalize_text(args.get("batch_id")),
        meter_id=_normalize_text(args.get("meter_id")),
        date_from=date_from,
        date_to=date_to,
    )


def build_vee_exception_filters(args) -> VeeExceptionFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    exception_status = _normalize_text(args.get("exception_status"))
    if exception_status not in {None, "open", "acknowledged", "resolved"}:
        raise VisibilityFilterError(
            "invalid_vee_exception_status",
            "VEE exception status must be open, acknowledged, or resolved when provided.",
        )

    severity = _normalize_text(args.get("severity"))
    if severity not in {None, "info", "warning", "error", "critical"}:
        raise VisibilityFilterError(
            "invalid_vee_exception_severity",
            "VEE exception severity must be info, warning, error, or critical when provided.",
        )

    return VeeExceptionFilters(
        hes_system_id=_parse_optional_int(
            args.get("hes_system_id"),
            error_code="invalid_hes_system_filter",
            fallback_message="HES system filter must be a positive integer.",
        ),
        exception_status=exception_status,
        exception_code=_normalize_text(args.get("exception_code")),
        severity=severity,
        meter_id=_normalize_text(args.get("meter_id")),
        date_from=date_from,
        date_to=date_to,
    )


def list_ingest_batches(
    session: Session, filters: IngestBatchFilters, *, limit: int = 100
) -> list[IngestBatch]:
    statement: Select[tuple[IngestBatch]] = (
        select(IngestBatch)
        .options(
            selectinload(IngestBatch.hes_read_rows),
            selectinload(IngestBatch.hes_event_rows),
        )
    )

    if filters.batch_id:
        statement = statement.where(IngestBatch.batch_id == filters.batch_id)
    if filters.source_system:
        statement = statement.where(IngestBatch.source_system == filters.source_system)
    if filters.record_type:
        statement = statement.where(IngestBatch.record_type == filters.record_type)
    if filters.date_from:
        statement = statement.where(IngestBatch.received_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(IngestBatch.received_at <= filters.date_to)

    statement = statement.order_by(IngestBatch.id.desc()).limit(limit)
    return session.scalars(statement).all()


def list_canonical_measurements(
    session: Session, filters: CanonicalMeasurementFilters, *, limit: int = 100
) -> list[CanonicalMeasurement]:
    statement: Select[tuple[CanonicalMeasurement]] = (
        select(CanonicalMeasurement)
        .join(CanonicalMeasurement.hes_read_raw)
        .join(HesReadRaw.ingest_batch)
        .options(
            selectinload(CanonicalMeasurement.hes_read_raw).selectinload(HesReadRaw.ingest_batch),
            selectinload(CanonicalMeasurement.measuring_component),
        )
    )

    if filters.batch_id:
        statement = statement.where(IngestBatch.batch_id == filters.batch_id)
    if filters.meter_id:
        statement = statement.where(HesReadRaw.meter_identifier == filters.meter_id)
    if filters.date_from:
        statement = statement.where(CanonicalMeasurement.measured_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(CanonicalMeasurement.measured_at <= filters.date_to)

    statement = statement.order_by(CanonicalMeasurement.id.desc()).limit(limit)
    return session.execute(statement).scalars().unique().all()


def list_final_measurements(
    session: Session, filters: FinalMeasurementFilters, *, limit: int = 100
) -> list[FinalMeasurement]:
    statement: Select[tuple[FinalMeasurement]] = (
        select(FinalMeasurement)
        .join(FinalMeasurement.canonical_measurement)
        .join(CanonicalMeasurement.hes_read_raw)
        .join(HesReadRaw.ingest_batch)
        .options(
            selectinload(FinalMeasurement.canonical_measurement)
            .selectinload(CanonicalMeasurement.hes_read_raw)
            .selectinload(HesReadRaw.ingest_batch)
        )
    )

    if filters.batch_id:
        statement = statement.where(IngestBatch.batch_id == filters.batch_id)
    if filters.meter_id:
        statement = statement.where(HesReadRaw.meter_identifier == filters.meter_id)
    if filters.date_from:
        statement = statement.where(FinalMeasurement.measured_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(FinalMeasurement.measured_at <= filters.date_to)

    statement = statement.order_by(FinalMeasurement.id.desc()).limit(limit)
    return session.execute(statement).scalars().unique().all()


def list_usage_transactions(
    session: Session, filters: UsageTransactionFilters, *, limit: int = 200
) -> list[UsageTransaction]:
    statement: Select[tuple[UsageTransaction]] = (
        select(UsageTransaction)
        .join(UsageTransaction.service_point)
        .join(UsageTransaction.measuring_component)
        .join(UsageTransaction.device)
        .options(
            selectinload(UsageTransaction.service_point),
            selectinload(UsageTransaction.measuring_component),
            selectinload(UsageTransaction.device),
            selectinload(UsageTransaction.pipeline_run),
        )
    )

    if filters.usage_transaction_id is not None:
        statement = statement.where(UsageTransaction.id == filters.usage_transaction_id)
    if filters.service_point_id is not None:
        statement = statement.where(UsageTransaction.service_point_id == filters.service_point_id)
    if filters.measuring_component_id is not None:
        statement = statement.where(
            UsageTransaction.measuring_component_id == filters.measuring_component_id
        )
    if filters.service_point:
        statement = statement.where(ServicePoint.external_id == filters.service_point)
    if filters.external_channel_id:
        statement = statement.where(
            MeasuringComponent.external_channel_id == filters.external_channel_id
        )
    if filters.usage_type:
        statement = statement.where(UsageTransaction.usage_type == filters.usage_type)
    if filters.calculation_status:
        statement = statement.where(
            UsageTransaction.calculation_status == filters.calculation_status
        )
    if filters.date_from:
        statement = statement.where(UsageTransaction.period_start_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(UsageTransaction.period_start_at <= filters.date_to)

    statement = statement.order_by(
        UsageTransaction.period_start_at.desc(),
        UsageTransaction.id.desc(),
    ).limit(limit)
    return session.execute(statement).scalars().unique().all()


def list_operational_events(
    session: Session, filters: OperationalEventFilters, *, limit: int = 200
) -> list[OperationalEvent]:
    statement: Select[tuple[OperationalEvent]] = select(OperationalEvent).options(
        selectinload(OperationalEvent.hes_system)
    )

    if filters.stream_type == "alert":
        statement = statement.where(OperationalEvent.is_alert.is_(True))
    elif filters.stream_type == "event":
        statement = statement.where(OperationalEvent.is_alert.is_(False))
    if filters.hes_system_id is not None:
        statement = statement.where(OperationalEvent.hes_system_id == filters.hes_system_id)
    if filters.source_layer:
        statement = statement.where(OperationalEvent.source_layer == filters.source_layer)
    if filters.severity:
        statement = statement.where(OperationalEvent.severity == filters.severity)
    if filters.event_code:
        statement = statement.where(OperationalEvent.event_code == filters.event_code)
    if filters.alert_status:
        statement = statement.where(OperationalEvent.alert_status == filters.alert_status)
    if filters.batch_id:
        statement = statement.where(OperationalEvent.batch_id == filters.batch_id)
    if filters.meter_id:
        statement = statement.where(OperationalEvent.meter_identifier == filters.meter_id)
    if filters.date_from:
        statement = statement.where(OperationalEvent.occurred_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(OperationalEvent.occurred_at <= filters.date_to)

    statement = statement.order_by(OperationalEvent.occurred_at.desc(), OperationalEvent.id.desc()).limit(
        limit
    )
    return session.scalars(statement).all()


def list_vee_exceptions(
    session: Session,
    filters: VeeExceptionFilters,
    *,
    limit: int = 200,
) -> list[VeeException]:
    statement: Select[tuple[VeeException]] = (
        select(VeeException)
        .join(VeeException.initial_measurement)
        .join(InitialMeasurement.canonical_measurement)
        .join(CanonicalMeasurement.hes_read_raw)
        .options(
            selectinload(VeeException.initial_measurement)
            .selectinload(InitialMeasurement.canonical_measurement)
            .selectinload(CanonicalMeasurement.hes_read_raw)
            .selectinload(HesReadRaw.ingest_batch),
            selectinload(VeeException.initial_measurement)
            .selectinload(InitialMeasurement.canonical_measurement)
            .selectinload(CanonicalMeasurement.hes_read_raw)
            .selectinload(HesReadRaw.hes_system),
            selectinload(VeeException.initial_measurement).selectinload(
                InitialMeasurement.final_measurement
            ),
            selectinload(VeeException.vee_execution_log),
        )
    )

    if filters.hes_system_id is not None:
        statement = statement.where(HesReadRaw.hes_system_id == filters.hes_system_id)
    if filters.exception_status:
        statement = statement.where(VeeException.exception_status == filters.exception_status)
    if filters.exception_code:
        statement = statement.where(VeeException.exception_code == filters.exception_code)
    if filters.severity:
        statement = statement.where(VeeException.severity == filters.severity)
    if filters.meter_id:
        statement = statement.where(HesReadRaw.meter_identifier == filters.meter_id)
    if filters.date_from:
        statement = statement.where(VeeException.detected_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(VeeException.detected_at <= filters.date_to)

    statement = statement.order_by(VeeException.detected_at.desc(), VeeException.id.desc()).limit(limit)
    return session.execute(statement).scalars().unique().all()


def get_operational_event_detail_context(
    session: Session,
    event_id: int,
    *,
    raw_limit: int = 20,
) -> OperationalEventDetailContext | None:
    event = session.scalar(
        select(OperationalEvent)
        .where(OperationalEvent.id == event_id)
        .options(selectinload(OperationalEvent.hes_system))
        .limit(1)
    )
    if event is None:
        return None

    adapter_instance = (
        session.get(AdapterInstance, event.adapter_instance_id)
        if event.adapter_instance_id is not None
        else None
    )
    adapter_run = session.get(AdapterRun, event.adapter_run_id) if event.adapter_run_id is not None else None
    pipeline_run = (
        session.get(PipelineRun, event.pipeline_run_id) if event.pipeline_run_id is not None else None
    )
    ingest_batch = (
        session.get(IngestBatch, event.ingest_batch_id) if event.ingest_batch_id is not None else None
    )
    ingest_error_log = (
        session.scalar(
            select(IngestErrorLog)
            .where(IngestErrorLog.id == event.ingest_error_log_id)
            .options(joinedload(IngestErrorLog.hes_read_raw).joinedload(HesReadRaw.ingest_batch))
            .limit(1)
        )
        if event.ingest_error_log_id is not None
        else None
    )
    reprocess_request = (
        session.scalar(
            select(ReprocessRequest)
            .where(ReprocessRequest.id == event.reprocess_request_id)
            .options(joinedload(ReprocessRequest.hes_read_raw).joinedload(HesReadRaw.ingest_batch))
            .limit(1)
        )
        if event.reprocess_request_id is not None
        else None
    )
    vee_exception = None
    initial_measurement = None
    vee_execution_log = None
    if event.entity_type == "vee_exception" and event.entity_id is not None:
        vee_exception = session.scalar(
            select(VeeException)
            .where(VeeException.id == event.entity_id)
            .options(
                joinedload(VeeException.initial_measurement)
                .joinedload(InitialMeasurement.canonical_measurement)
                .joinedload(CanonicalMeasurement.hes_read_raw)
                .joinedload(HesReadRaw.ingest_batch),
                joinedload(VeeException.vee_execution_log),
                joinedload(VeeException.initial_measurement).joinedload(
                    InitialMeasurement.final_measurement
                ),
            )
            .limit(1)
        )
        if vee_exception is not None:
            initial_measurement = vee_exception.initial_measurement
            vee_execution_log = vee_exception.vee_execution_log

    raw_rows = _list_related_raw_rows(
        session,
        event,
        ingest_error_log=ingest_error_log,
        reprocess_request=reprocess_request,
        vee_exception=vee_exception,
        limit=raw_limit,
    )
    canonical_rows = [
        row.canonical_measurement
        for row in raw_rows
        if row.canonical_measurement is not None
    ]
    canonical_ids = [row.id for row in canonical_rows]
    final_rows: list[FinalMeasurement] = []
    if canonical_ids:
        final_rows = session.scalars(
            select(FinalMeasurement)
            .where(FinalMeasurement.canonical_measurement_id.in_(canonical_ids))
            .order_by(FinalMeasurement.measured_at.desc(), FinalMeasurement.id.desc())
        ).all()

    return OperationalEventDetailContext(
        event=event,
        adapter_instance=adapter_instance,
        adapter_run=adapter_run,
        pipeline_run=pipeline_run,
        ingest_batch=ingest_batch,
        ingest_error_log=ingest_error_log,
        reprocess_request=reprocess_request,
        initial_measurement=initial_measurement,
        vee_execution_log=vee_execution_log,
        vee_exception=vee_exception,
        raw_rows=raw_rows,
        canonical_rows=canonical_rows,
        final_rows=final_rows,
    )


def get_vee_exception_detail_context(
    session: Session,
    vee_exception_id: int,
) -> VeeExceptionDetailContext | None:
    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.id == vee_exception_id)
        .options(
            joinedload(VeeException.initial_measurement)
            .joinedload(InitialMeasurement.canonical_measurement)
            .joinedload(CanonicalMeasurement.hes_read_raw)
            .joinedload(HesReadRaw.ingest_batch),
            joinedload(VeeException.initial_measurement)
            .joinedload(InitialMeasurement.canonical_measurement)
            .joinedload(CanonicalMeasurement.hes_read_raw)
            .joinedload(HesReadRaw.hes_system),
            joinedload(VeeException.initial_measurement).joinedload(
                InitialMeasurement.final_measurement
            ),
            joinedload(VeeException.vee_execution_log),
            joinedload(VeeException.initial_measurement).joinedload(
                InitialMeasurement.device
            ),
            joinedload(VeeException.initial_measurement).joinedload(
                InitialMeasurement.service_point
            ),
            joinedload(VeeException.initial_measurement).joinedload(
                InitialMeasurement.measuring_component
            ),
        )
        .limit(1)
    )
    if vee_exception is None:
        return None

    initial_measurement = vee_exception.initial_measurement
    canonical_measurement = initial_measurement.canonical_measurement
    raw_row = canonical_measurement.hes_read_raw if canonical_measurement is not None else None
    ingest_batch = raw_row.ingest_batch if raw_row is not None else None

    return VeeExceptionDetailContext(
        vee_exception=vee_exception,
        initial_measurement=initial_measurement,
        canonical_measurement=canonical_measurement,
        raw_row=raw_row,
        ingest_batch=ingest_batch,
        vee_execution_log=vee_exception.vee_execution_log,
        final_measurement=initial_measurement.final_measurement,
    )


def _list_related_raw_rows(
    session: Session,
    event: OperationalEvent,
    *,
    ingest_error_log: IngestErrorLog | None,
    reprocess_request: ReprocessRequest | None,
    vee_exception: VeeException | None,
    limit: int,
) -> list[HesReadRaw]:
    statement: Select[tuple[HesReadRaw]] = (
        select(HesReadRaw)
        .options(
            joinedload(HesReadRaw.ingest_batch),
            joinedload(HesReadRaw.canonical_measurement),
        )
        .order_by(HesReadRaw.measured_at.desc().nullslast(), HesReadRaw.id.desc())
    )

    if ingest_error_log is not None and ingest_error_log.hes_read_raw_id is not None:
        statement = statement.where(HesReadRaw.id == ingest_error_log.hes_read_raw_id)
    elif reprocess_request is not None:
        statement = statement.where(HesReadRaw.id == reprocess_request.hes_read_raw_id)
    elif (
        vee_exception is not None
        and vee_exception.initial_measurement is not None
        and vee_exception.initial_measurement.canonical_measurement is not None
        and vee_exception.initial_measurement.canonical_measurement.hes_read_raw is not None
    ):
        statement = statement.where(
            HesReadRaw.id
            == vee_exception.initial_measurement.canonical_measurement.hes_read_raw.id
        )
    elif event.ingest_batch_id is not None and event.meter_identifier:
        statement = statement.where(
            HesReadRaw.ingest_batch_id == event.ingest_batch_id,
            HesReadRaw.meter_identifier == event.meter_identifier,
        )
    elif event.ingest_batch_id is not None:
        statement = statement.where(HesReadRaw.ingest_batch_id == event.ingest_batch_id)
    elif event.meter_identifier:
        statement = statement.where(HesReadRaw.meter_identifier == event.meter_identifier)
    else:
        return []

    return session.scalars(statement.limit(limit)).all()
