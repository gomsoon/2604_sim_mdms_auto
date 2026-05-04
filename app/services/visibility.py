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
    BillDeterminant,
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
    VeeReplayRequest,
    VeeReplayRequestItem,
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
class BillDeterminantFilters:
    bill_determinant_id: int | None = None
    hes_system_id: int | None = None
    service_point_id: int | None = None
    measuring_component_id: int | None = None
    service_point: str | None = None
    external_channel_id: str | None = None
    determinant_type: str | None = None
    calculation_status: str | None = None
    quality_summary: str | None = None
    billing_cycle_mode: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    include_history: bool = False


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
class VeeReplayRequestFilters:
    request_scope: str | None = None
    status: str | None = None
    hes_system_id: int | None = None
    requested_by: str | None = None


@dataclass(frozen=True, slots=True)
class VeeReplayRequestDetailContext:
    request: VeeReplayRequest
    latest_pipeline_run: PipelineRun | None = None
    current_item: VeeReplayRequestItem | None = None
    recent_items: list[VeeReplayRequestItem] = ()
    failed_items: list[VeeReplayRequestItem] = ()


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


@dataclass(frozen=True, slots=True)
class UsageTransactionDetailContext:
    usage_transaction: UsageTransaction
    pipeline_run: PipelineRun | None = None
    final_rows: list[FinalMeasurement] = ()
    bill_determinant_rows: list[BillDeterminant] = ()


@dataclass(frozen=True, slots=True)
class BillDeterminantDetailContext:
    bill_determinant: BillDeterminant
    pipeline_run: PipelineRun | None = None
    source_usage_rows: list[UsageTransaction] = ()
    revision_rows: list[BillDeterminant] = ()


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


def _parse_optional_bool(value: str | None, *, default: bool = False) -> bool:
    normalized = _normalize_text(value)
    if normalized is None:
        return default

    lowered = normalized.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


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


def build_bill_determinant_filters(args) -> BillDeterminantFilters:
    date_from = _parse_filter_datetime(args.get("date_from"))
    date_to = _parse_filter_datetime(args.get("date_to"), end_of_day=True)
    if date_from and date_to and date_from > date_to:
        raise VisibilityFilterError(
            "invalid_date_range", "The start date must be earlier than or equal to the end date."
        )

    determinant_type = _normalize_text(args.get("determinant_type"))
    if determinant_type not in {None, "billing_cycle_consumption_total"}:
        raise VisibilityFilterError(
            "invalid_bill_determinant_type_filter",
            "Bill determinant type must be billing_cycle_consumption_total when provided.",
        )

    calculation_status = _normalize_text(args.get("calculation_status"))
    if calculation_status not in {None, "complete", "partial", "blocked"}:
        raise VisibilityFilterError(
            "invalid_bill_determinant_status_filter",
            "Bill determinant status must be complete, partial, or blocked when provided.",
        )

    billing_cycle_mode = _normalize_text(args.get("billing_cycle_mode"))
    if billing_cycle_mode not in {None, "calendar_month", "anchored_month"}:
        raise VisibilityFilterError(
            "invalid_billing_cycle_mode_filter",
            "Billing cycle mode must be calendar_month or anchored_month when provided.",
        )

    return BillDeterminantFilters(
        bill_determinant_id=_parse_optional_int(
            args.get("bill_determinant_id"),
            error_code="invalid_bill_determinant_filter",
            fallback_message="Bill determinant filter must be a positive integer.",
        ),
        hes_system_id=_parse_optional_int(
            args.get("hes_system_id"),
            error_code="invalid_hes_system_filter",
            fallback_message="HES system filter must be a positive integer.",
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
        determinant_type=determinant_type,
        calculation_status=calculation_status,
        quality_summary=_normalize_text(args.get("quality_summary")),
        billing_cycle_mode=billing_cycle_mode,
        date_from=date_from,
        date_to=date_to,
        include_history=_parse_optional_bool(args.get("include_history"), default=False),
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


def build_vee_replay_request_filters(args) -> VeeReplayRequestFilters:
    request_scope = _normalize_text(args.get("request_scope"))
    if request_scope not in {None, "hes_system", "ingest_batch", "date_range"}:
        raise VisibilityFilterError(
            "invalid_vee_replay_request_scope",
            "Replay request scope must be hes_system, ingest_batch, or date_range when provided.",
        )

    status = _normalize_text(args.get("status"))
    if status not in {None, "queued", "processing", "completed", "failed", "cancelled"}:
        raise VisibilityFilterError(
            "invalid_vee_replay_request_status",
            "Replay request status must be queued, processing, completed, failed, or cancelled when provided.",
        )

    return VeeReplayRequestFilters(
        request_scope=request_scope,
        status=status,
        hes_system_id=_parse_optional_int(
            args.get("hes_system_id"),
            error_code="invalid_hes_system_filter",
            fallback_message="HES system filter must be a positive integer.",
        ),
        requested_by=_normalize_text(args.get("requested_by")),
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


def list_bill_determinants(
    session: Session, filters: BillDeterminantFilters, *, limit: int = 200
) -> list[BillDeterminant]:
    statement: Select[tuple[BillDeterminant]] = (
        select(BillDeterminant)
        .join(BillDeterminant.service_point)
        .outerjoin(BillDeterminant.measuring_component)
        .outerjoin(BillDeterminant.device)
        .options(
            selectinload(BillDeterminant.service_point),
            selectinload(BillDeterminant.measuring_component),
            selectinload(BillDeterminant.device),
            selectinload(BillDeterminant.pipeline_run),
            selectinload(BillDeterminant.supersedes_bill_determinant),
        )
    )

    if filters.hes_system_id is not None:
        statement = statement.where(_bill_determinant_matches_hes_clause(filters.hes_system_id))
    if filters.bill_determinant_id is not None:
        statement = statement.where(BillDeterminant.id == filters.bill_determinant_id)
    if filters.service_point_id is not None:
        statement = statement.where(BillDeterminant.service_point_id == filters.service_point_id)
    if filters.measuring_component_id is not None:
        statement = statement.where(
            BillDeterminant.measuring_component_id == filters.measuring_component_id
        )
    if filters.service_point:
        statement = statement.where(ServicePoint.external_id == filters.service_point)
    if filters.external_channel_id:
        statement = statement.where(
            MeasuringComponent.external_channel_id == filters.external_channel_id
        )
    if filters.determinant_type:
        statement = statement.where(BillDeterminant.determinant_type == filters.determinant_type)
    if filters.calculation_status:
        statement = statement.where(
            BillDeterminant.calculation_status == filters.calculation_status
        )
    if filters.quality_summary:
        statement = statement.where(BillDeterminant.quality_summary == filters.quality_summary)
    if filters.billing_cycle_mode:
        statement = statement.where(
            BillDeterminant.details["billing_context_snapshot"]["billing_cycle_mode"].as_string()
            == filters.billing_cycle_mode
        )
    if filters.date_from:
        statement = statement.where(BillDeterminant.billing_period_start_at >= filters.date_from)
    if filters.date_to:
        statement = statement.where(BillDeterminant.billing_period_start_at <= filters.date_to)
    if filters.bill_determinant_id is None and not filters.include_history:
        statement = statement.where(BillDeterminant.is_current.is_(True))

    statement = statement.order_by(
        BillDeterminant.billing_period_start_at.desc(),
        BillDeterminant.revision_number.desc(),
        BillDeterminant.id.desc(),
    ).limit(limit)
    return session.execute(statement).scalars().unique().all()


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
        .where(
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
        .exists()
    )


def get_usage_transaction_detail_context(
    session: Session,
    usage_transaction_id: int,
    *,
    final_limit: int = 200,
) -> UsageTransactionDetailContext | None:
    usage_transaction = session.scalar(
        select(UsageTransaction)
        .where(UsageTransaction.id == usage_transaction_id)
        .options(
            joinedload(UsageTransaction.pipeline_run),
            joinedload(UsageTransaction.service_point),
            joinedload(UsageTransaction.device),
            joinedload(UsageTransaction.measuring_component),
        )
        .limit(1)
    )
    if usage_transaction is None:
        return None

    final_rows = session.scalars(
        select(FinalMeasurement)
        .where(
            FinalMeasurement.final_status == "finalized",
            FinalMeasurement.is_current.is_(True),
            FinalMeasurement.service_point_id == usage_transaction.service_point_id,
            FinalMeasurement.measuring_component_id == usage_transaction.measuring_component_id,
            FinalMeasurement.measured_at >= usage_transaction.period_start_at,
            FinalMeasurement.measured_at < usage_transaction.period_end_at,
        )
        .options(
            joinedload(FinalMeasurement.canonical_measurement).joinedload(
                CanonicalMeasurement.hes_read_raw
            ),
            joinedload(FinalMeasurement.initial_measurement),
        )
        .order_by(FinalMeasurement.measured_at.asc(), FinalMeasurement.id.asc())
        .limit(final_limit)
    ).all()

    bill_determinant_rows = session.scalars(
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == usage_transaction.service_point_id)
        .where(
            BillDeterminant.measuring_component_id == usage_transaction.measuring_component_id
        )
        .where(BillDeterminant.billing_period_start_at == usage_transaction.period_start_at)
        .where(BillDeterminant.billing_period_end_at == usage_transaction.period_end_at)
        .options(
            joinedload(BillDeterminant.pipeline_run),
            joinedload(BillDeterminant.supersedes_bill_determinant),
        )
        .order_by(BillDeterminant.revision_number.desc(), BillDeterminant.id.desc())
    ).all()

    return UsageTransactionDetailContext(
        usage_transaction=usage_transaction,
        pipeline_run=usage_transaction.pipeline_run,
        final_rows=final_rows,
        bill_determinant_rows=bill_determinant_rows,
    )


def get_bill_determinant_detail_context(
    session: Session,
    bill_determinant_id: int,
    *,
    source_usage_limit: int = 50,
) -> BillDeterminantDetailContext | None:
    bill_determinant = session.scalar(
        select(BillDeterminant)
        .where(BillDeterminant.id == bill_determinant_id)
        .options(
            joinedload(BillDeterminant.pipeline_run),
            joinedload(BillDeterminant.service_point),
            joinedload(BillDeterminant.device),
            joinedload(BillDeterminant.measuring_component),
            joinedload(BillDeterminant.supersedes_bill_determinant),
        )
        .limit(1)
    )
    if bill_determinant is None:
        return None

    provenance = (bill_determinant.details or {}).get("provenance") or {}
    source_usage_ids = [
        usage_id
        for usage_id in provenance.get("source_usage_transaction_ids", [])
        if isinstance(usage_id, int)
    ]
    source_usage_rows: list[UsageTransaction] = []
    if source_usage_ids:
        source_usage_rows = session.scalars(
            select(UsageTransaction)
            .where(UsageTransaction.id.in_(source_usage_ids))
            .options(
                joinedload(UsageTransaction.pipeline_run),
                joinedload(UsageTransaction.service_point),
                joinedload(UsageTransaction.device),
                joinedload(UsageTransaction.measuring_component),
            )
            .order_by(UsageTransaction.period_start_at.asc(), UsageTransaction.id.asc())
            .limit(source_usage_limit)
        ).all()

    revision_statement = (
        select(BillDeterminant)
        .where(BillDeterminant.service_point_id == bill_determinant.service_point_id)
        .where(BillDeterminant.determinant_type == bill_determinant.determinant_type)
        .where(BillDeterminant.billing_period_start_at == bill_determinant.billing_period_start_at)
        .where(BillDeterminant.billing_period_end_at == bill_determinant.billing_period_end_at)
        .order_by(BillDeterminant.revision_number.desc(), BillDeterminant.id.desc())
    )
    if bill_determinant.measuring_component_id is None:
        revision_statement = revision_statement.where(
            BillDeterminant.measuring_component_id.is_(None)
        )
    else:
        revision_statement = revision_statement.where(
            BillDeterminant.measuring_component_id == bill_determinant.measuring_component_id
        )

    revision_rows = session.scalars(revision_statement.limit(50)).all()

    return BillDeterminantDetailContext(
        bill_determinant=bill_determinant,
        pipeline_run=bill_determinant.pipeline_run,
        source_usage_rows=source_usage_rows,
        revision_rows=revision_rows,
    )


def list_vee_replay_requests(
    session: Session,
    filters: VeeReplayRequestFilters,
    *,
    limit: int = 200,
) -> list[VeeReplayRequest]:
    statement: Select[tuple[VeeReplayRequest]] = select(VeeReplayRequest).options(
        selectinload(VeeReplayRequest.hes_system),
        selectinload(VeeReplayRequest.ingest_batch),
        selectinload(VeeReplayRequest.pipeline_runs),
        selectinload(VeeReplayRequest.request_items),
    )

    if filters.request_scope:
        statement = statement.where(VeeReplayRequest.request_scope == filters.request_scope)
    if filters.status:
        statement = statement.where(VeeReplayRequest.status == filters.status)
    if filters.hes_system_id is not None:
        statement = statement.where(VeeReplayRequest.hes_system_id == filters.hes_system_id)
    if filters.requested_by:
        statement = statement.where(VeeReplayRequest.requested_by == filters.requested_by)

    statement = statement.order_by(
        VeeReplayRequest.created_at.desc(),
        VeeReplayRequest.id.desc(),
    ).limit(limit)
    return session.execute(statement).scalars().unique().all()


def get_vee_replay_request_detail_context(
    session: Session,
    request_id: int,
    *,
    recent_item_limit: int = 100,
    failed_item_limit: int = 20,
) -> VeeReplayRequestDetailContext | None:
    request = session.scalar(
        select(VeeReplayRequest)
        .where(VeeReplayRequest.id == request_id)
        .options(
            joinedload(VeeReplayRequest.hes_system),
            joinedload(VeeReplayRequest.ingest_batch),
            selectinload(VeeReplayRequest.pipeline_runs),
            selectinload(VeeReplayRequest.request_items).joinedload(
                VeeReplayRequestItem.representative_vee_exception
            ),
            selectinload(VeeReplayRequest.request_items).joinedload(
                VeeReplayRequestItem.initial_measurement
            ),
            selectinload(VeeReplayRequest.request_items).joinedload(
                VeeReplayRequestItem.current_final_measurement
            ),
            selectinload(VeeReplayRequest.request_items).joinedload(
                VeeReplayRequestItem.previous_final_measurement
            ),
        )
        .limit(1)
    )
    if request is None:
        return None

    latest_pipeline_run = None
    if request.pipeline_runs:
        latest_pipeline_run = max(
            request.pipeline_runs,
            key=lambda row: ((row.started_at or datetime.min.replace(tzinfo=timezone.utc)), row.id),
        )

    current_item_id = (request.details or {}).get("current_item_id")
    current_item = next(
        (
            row
            for row in request.request_items
            if current_item_id is not None and row.id == current_item_id
        ),
        None,
    )
    if current_item is None:
        current_item = next(
            (row for row in request.request_items if row.status == "processing"),
            None,
        )

    recent_items = sorted(
        request.request_items,
        key=lambda row: (row.updated_at, row.id),
        reverse=True,
    )[:recent_item_limit]
    failed_items = [
        row for row in recent_items if row.status == "failed"
    ][:failed_item_limit]

    return VeeReplayRequestDetailContext(
        request=request,
        latest_pipeline_run=latest_pipeline_run,
        current_item=current_item,
        recent_items=recent_items,
        failed_items=failed_items,
    )


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
