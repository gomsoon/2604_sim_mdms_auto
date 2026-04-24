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
    IngestBatch,
    IngestErrorLog,
    OperationalEvent,
    PipelineRun,
    ReprocessRequest,
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
class OperationalEventDetailContext:
    event: OperationalEvent
    adapter_instance: AdapterInstance | None = None
    adapter_run: AdapterRun | None = None
    pipeline_run: PipelineRun | None = None
    ingest_batch: IngestBatch | None = None
    ingest_error_log: IngestErrorLog | None = None
    reprocess_request: ReprocessRequest | None = None
    raw_rows: list[HesReadRaw] = ()
    canonical_rows: list[CanonicalMeasurement] = ()
    final_rows: list[FinalMeasurement] = ()


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

    raw_rows = _list_related_raw_rows(
        session,
        event,
        ingest_error_log=ingest_error_log,
        reprocess_request=reprocess_request,
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
        raw_rows=raw_rows,
        canonical_rows=canonical_rows,
        final_rows=final_rows,
    )


def _list_related_raw_rows(
    session: Session,
    event: OperationalEvent,
    *,
    ingest_error_log: IngestErrorLog | None,
    reprocess_request: ReprocessRequest | None,
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
