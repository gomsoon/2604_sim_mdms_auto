from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    AdapterInstance,
    AdapterRun,
    AdapterWatermark,
    LandingLpEmReadBlock,
    RawIntervalWindowState,
)
from app.services.nuri_aimir_hes_source import (
    NuriAimirHesLpEmCursor,
    NuriAimirHesPollingConfig,
    fetch_nuri_aimir_hes_lp_em_rows,
    format_nuri_aimir_hes_lp_em_cursor,
    parse_nuri_aimir_hes_lp_em_cursor,
    parse_nuri_aimir_hes_runtime_config,
)
from app.services.ingest_adapters import DEFAULT_ADAPTER_KEY
from app.services.ingest_contract import coerce_numeric, parse_datetime
from app.services.ingestion import ingest_events, ingest_reads
from app.services.adapters import sync_adapter_health_alerts
from app.services.operational_events import close_operational_alerts, record_operational_event


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


def _raise_configuration_error(code: str, message: str) -> None:
    raise AdapterExecutionError(code, message)


def _require_source_timezone(raw_value: Any) -> ZoneInfo:
    timezone_name = str(raw_value or "").strip()
    if not timezone_name:
        raise AdapterExecutionError(
            "missing_source_timezone",
            "The polling adapter requires an explicit source timezone.",
        )
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise AdapterExecutionError(
            "invalid_source_timezone",
            "The configured source timezone is not recognized.",
            details={"source_timezone": timezone_name},
        ) from exc


def _parse_source_local_timestamp(
    value: Any,
    *,
    source_timezone: ZoneInfo,
    source_format: str,
    error_code: str,
    fallback_message: str,
) -> datetime:
    normalized = str(value or "").strip()
    if not normalized:
        raise AdapterExecutionError(error_code, fallback_message)
    try:
        parsed = datetime.strptime(normalized, source_format)
    except ValueError as exc:
        raise AdapterExecutionError(error_code, fallback_message) from exc
    return parsed.replace(tzinfo=source_timezone).astimezone(timezone.utc)


def _parse_optional_positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _extract_lp_em_slot_values(row: dict[str, Any], *, row_index: int) -> dict[str, float]:
    slot_values: dict[str, float] = {}
    for slot_index in range(60):
        slot_code = f"{slot_index:02d}"
        raw_value = row.get(f"VALUE_{slot_code}")
        if raw_value in (None, ""):
            continue
        try:
            slot_values[slot_code] = float(coerce_numeric(raw_value))
        except (TypeError, ValueError) as exc:
            raise AdapterExecutionError(
                "invalid_source_slot_value",
                f"LP_EM sample block at index {row_index} contains a non-numeric slot value.",
                details={"slot_code": slot_code},
            ) from exc
    return slot_values


def _expected_slot_codes(interval_size_minutes: int) -> list[str]:
    if interval_size_minutes <= 0 or 60 % interval_size_minutes != 0:
        raise AdapterExecutionError(
            "invalid_interval_size_minutes",
            "Interval size must be a positive divisor of 60 minutes.",
            details={"interval_size_minutes": interval_size_minutes},
        )
    return [f"{minute:02d}" for minute in range(0, 60, interval_size_minutes)]


def _decode_slot_bitmap(value: str | None) -> set[str]:
    if not value:
        return set()
    return {slot for slot in value.split(",") if slot}


def _encode_slot_bitmap(values: set[str]) -> str | None:
    if not values:
        return None
    return ",".join(sorted(values))


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


class NuriAimirHesLpEmPollRuntime:
    record_type = "hes_read_raw"
    source_table_name = "LP_EM"
    source_business_hour_format = "%Y%m%d%H"
    source_write_format = "%Y%m%d%H%M%S"

    def _parse_cursor_source_write_ts(
        self, cursor: NuriAimirHesLpEmCursor | None, *, source_timezone: ZoneInfo
    ) -> datetime | None:
        if cursor is None:
            return None
        return _parse_source_local_timestamp(
            cursor.write_date,
            source_timezone=source_timezone,
            source_format=self.source_write_format,
            error_code="invalid_stored_watermark",
            fallback_message="The stored Oracle adapter watermark is not valid.",
        )

    def _row_cursor(self, row: dict[str, Any]) -> NuriAimirHesLpEmCursor:
        meter_source_id = str(row.get("METER_ID") or "").strip()
        channel_code = str(row.get("CHANNEL") or "").strip()
        source_business_hour = str(row.get("YYYYMMDDHH") or "").strip()
        source_write_text = str(row.get("WRITEDATE") or "").strip()
        if not all([meter_source_id, channel_code, source_business_hour, source_write_text]):
            raise AdapterExecutionError(
                "invalid_source_row_cursor",
                "LP_EM source block is missing one of WRITEDATE, YYYYMMDDHH, METER_ID, or CHANNEL.",
            )
        return NuriAimirHesLpEmCursor(
            write_date=source_write_text,
            business_hour=source_business_hour,
            meter_id=meter_source_id,
            channel=channel_code,
        )

    def _get_or_create_landing_block(
        self,
        session: Session,
        *,
        instance: AdapterInstance,
        run: AdapterRun,
        row: dict[str, Any],
        row_index: int,
        meter_source_id: str,
        channel_code: str,
        source_business_hour: str,
        source_write_ts: datetime,
        block_value: float | None,
        slot_values: dict[str, float],
    ) -> LandingLpEmReadBlock:
        block_key = "|".join(
            (
                self.source_table_name,
                meter_source_id,
                source_business_hour,
                channel_code,
                str(row.get("WRITEDATE") or ""),
            )
        )
        existing = session.scalar(
            select(LandingLpEmReadBlock)
            .where(
                LandingLpEmReadBlock.source_system == instance.source_system,
                LandingLpEmReadBlock.source_block_key == block_key,
            )
            .limit(1)
        )
        if existing is not None:
            if existing.source_payload != row:
                raise AdapterExecutionError(
                    "source_block_replay_conflict",
                    (
                        f"LP_EM source block at index {row_index} reused an existing source_block_key "
                        "with a different payload."
                    ),
                    details={"source_block_key": block_key},
                )
            return existing

        landing_block = LandingLpEmReadBlock(
            adapter_instance_id=instance.id,
            adapter_run_id=run.id,
            source_system=instance.source_system,
            source_table_name=self.source_table_name,
            source_block_key=block_key,
            meter_source_id=meter_source_id,
            device_source_id=str(row.get("DEVICE_ID") or "").strip() or None,
            mdev_id=str(row.get("MDEV_ID") or "").strip() or None,
            mdev_type=str(row.get("MDEV_TYPE") or "").strip() or None,
            channel_code=channel_code,
            source_business_hour=source_business_hour,
            source_hour_component=str(row.get("HH") or "").strip() or None,
            source_write_text=str(row.get("WRITEDATE") or "").strip() or None,
            source_write_ts=source_write_ts,
            location_source_id=str(row.get("LOCATION_ID") or "").strip() or None,
            supplier_source_id=str(row.get("SUPPLIER_ID") or "").strip() or None,
            enddevice_source_id=str(row.get("ENDDEVICE_ID") or "").strip() or None,
            value_cnt=_parse_optional_positive_int(row.get("VALUE_CNT")),
            block_value=block_value,
            slot_values=slot_values,
            slot_count=len(slot_values),
            parsed_ok=True,
            source_payload=row,
        )
        session.add(landing_block)
        session.flush()
        return landing_block

    def _load_source_blocks(
        self,
        *,
        source_fetch_mode: str,
        sample_blocks: tuple[dict[str, Any], ...],
        polling_config: NuriAimirHesPollingConfig | None,
        watermark_cursor: NuriAimirHesLpEmCursor | None,
    ) -> tuple[list[dict[str, Any]], str, int]:
        if source_fetch_mode == "sample_blocks":
            selected_blocks: list[dict[str, Any]] = []
            for index, raw_row in enumerate(sample_blocks):
                row_cursor = self._row_cursor(raw_row)
                if watermark_cursor is None or (
                    row_cursor.write_date,
                    row_cursor.business_hour,
                    row_cursor.meter_id,
                    row_cursor.channel,
                ) > (
                    watermark_cursor.write_date,
                    watermark_cursor.business_hour,
                    watermark_cursor.meter_id,
                    watermark_cursor.channel,
                ):
                    selected_blocks.append(dict(raw_row))
            selected_blocks.sort(
                key=lambda row: (
                    str(row.get("WRITEDATE") or ""),
                    str(row.get("YYYYMMDDHH") or ""),
                    str(row.get("METER_ID") or ""),
                    str(row.get("CHANNEL") or ""),
                )
            )
            batch_limit = (polling_config.batch_size if polling_config is not None else None) or len(
                selected_blocks
            )
            return selected_blocks[:batch_limit], "sample_blocks", len(sample_blocks)

        try:
            rows = fetch_nuri_aimir_hes_lp_em_rows(polling_config, cursor=watermark_cursor)
        except Exception as exc:
            raise AdapterExecutionError(
                "nuri_aimir_hes_poll_failed",
                "The NURI AIMIR HES LP_EM Oracle polling query failed.",
                details={"exception_type": type(exc).__name__},
            ) from exc
        return rows, "oracle_query", len(rows)

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
        try:
            runtime_settings = parse_nuri_aimir_hes_runtime_config(
                runtime_config,
                secret_ref=instance.secret_ref,
                batch_size=instance.batch_size,
            )
        except ValueError as exc:
            raise AdapterExecutionError(
                "invalid_nuri_aimir_hes_runtime_configuration",
                str(exc),
            ) from exc
        source_timezone = _require_source_timezone(runtime_settings.source_timezone_name)
        default_interval = runtime_settings.default_interval_minutes
        default_unit = runtime_settings.unit_of_measure

        watermark = _load_adapter_watermark(
            session,
            adapter_instance_id=instance.id,
            record_type=definition.record_type,
        )
        watermark_before = watermark.cursor_value if watermark is not None else None
        watermark_cursor = None
        if watermark_before is not None:
            try:
                watermark_cursor = parse_nuri_aimir_hes_lp_em_cursor(watermark_before)
            except ValueError as exc:
                raise AdapterExecutionError(
                    "invalid_stored_watermark",
                    "The stored NURI AIMIR HES adapter watermark is not valid.",
                ) from exc
        watermark_before_dt = self._parse_cursor_source_write_ts(
            watermark_cursor,
            source_timezone=source_timezone,
        )
        selected_blocks, source_fetch_mode, source_block_count = self._load_source_blocks(
            source_fetch_mode=runtime_settings.source_fetch_mode,
            sample_blocks=runtime_settings.sample_blocks,
            polling_config=runtime_settings.polling_config,
            watermark_cursor=watermark_cursor,
        )

        reads: list[dict[str, Any]] = []
        window_updates: list[dict[str, Any]] = []
        last_source_timestamp = watermark_before_dt
        watermark_after = watermark_before
        now = datetime.now(timezone.utc)

        for row_index, row in enumerate(selected_blocks):
            meter_source_id = str(row.get("METER_ID") or "").strip()
            if not meter_source_id:
                raise AdapterExecutionError(
                    "missing_meter_source_id",
                    f"LP_EM source block at index {row_index} is missing METER_ID.",
                )
            channel_code = str(row.get("CHANNEL") or "").strip()
            if not channel_code:
                raise AdapterExecutionError(
                    "missing_channel_code",
                    f"LP_EM source block at index {row_index} is missing CHANNEL.",
                )
            source_business_hour = str(row.get("YYYYMMDDHH") or "").strip()
            source_business_ts = _parse_source_local_timestamp(
                source_business_hour,
                source_timezone=source_timezone,
                source_format=self.source_business_hour_format,
                error_code="invalid_source_business_hour",
                fallback_message=(
                    f"LP_EM source block at index {row_index} must include YYYYMMDDHH in YYYYMMDDHH format."
                ),
            )
            source_write_ts = _parse_source_local_timestamp(
                row.get("WRITEDATE"),
                source_timezone=source_timezone,
                source_format=self.source_write_format,
                error_code="invalid_source_write_timestamp",
                fallback_message=(
                    f"LP_EM source block at index {row_index} must include WRITEDATE in YYYYMMDDHHMMSS format."
                ),
            )
            interval_size_minutes = (
                _parse_optional_positive_int(row.get("LP_INTERVAL")) or default_interval or 60
            )
            expected_slot_codes = _expected_slot_codes(interval_size_minutes)
            slot_values = _extract_lp_em_slot_values(row, row_index=row_index)
            block_value = None
            if row.get("VALUE") not in (None, ""):
                try:
                    block_value = float(coerce_numeric(row.get("VALUE")))
                except (TypeError, ValueError) as exc:
                    raise AdapterExecutionError(
                        "invalid_source_block_value",
                        f"LP_EM source block at index {row_index} contains a non-numeric VALUE column.",
                    ) from exc

            landing_block = self._get_or_create_landing_block(
                session,
                instance=instance,
                run=run,
                row=row,
                row_index=row_index,
                meter_source_id=meter_source_id,
                channel_code=channel_code,
                source_business_hour=source_business_hour,
                source_write_ts=source_write_ts,
                block_value=block_value,
                slot_values=slot_values,
            )
            block_key = landing_block.source_block_key

            for slot_code, reading_value in sorted(slot_values.items()):
                interval_start = source_business_ts + timedelta(minutes=int(slot_code))
                reads.append(
                    {
                        "meter_id": meter_source_id,
                        "channel_id": channel_code,
                        "measurement_ts": interval_start.isoformat(),
                        "value": reading_value,
                        "quality_code": row.get("QUALITY_CODE"),
                        "status_code": row.get("STATUS_CODE"),
                        "unit_of_measure": default_unit,
                        "interval_size_minutes": interval_size_minutes,
                        "source_table_name": self.source_table_name,
                        "source_block_key": block_key,
                        "source_record_key": f"{block_key}|{slot_code}",
                        "device_identifier": landing_block.device_source_id,
                        "source_slot_code": slot_code,
                        "source_slot_index": int(slot_code),
                        "source_business_ts": source_business_ts.isoformat(),
                        "source_write_ts": source_write_ts.isoformat(),
                        "landing_lp_em_read_block_id": landing_block.id,
                    }
                )

            window_updates.append(
                {
                    "source_system": instance.source_system,
                    "meter_identifier": meter_source_id,
                    "channel_identifier": channel_code,
                    "window_start_at": source_business_ts.isoformat(),
                    "window_size_minutes": 60,
                    "interval_size_minutes": interval_size_minutes,
                    "expected_slot_codes": expected_slot_codes,
                    "received_slot_codes": sorted(slot_values),
                    "source_write_ts": source_write_ts.isoformat(),
                    "landing_lp_em_read_block_id": landing_block.id,
                    "source_block_key": block_key,
                }
            )
            last_source_timestamp = source_write_ts
            watermark_after = format_nuri_aimir_hes_lp_em_cursor(self._row_cursor(row))

        return AdapterIngestEnvelope(
            record_type=definition.record_type,
            payload={
                "contract_version": "v1",
                "source_system": instance.source_system,
                "adapter_key": DEFAULT_ADAPTER_KEY,
                "batch_id": f"adapter-{instance.instance_code}-run-{run.id}",
                "received_at": now.isoformat(),
                "reads": reads,
            },
            source_rows_fetched=len(selected_blocks),
            watermark_before=watermark_before,
            watermark_after=watermark_after,
            cursor_type="lp_em_cursor",
            last_source_timestamp=last_source_timestamp,
            details={
                "implementation_key": definition.implementation_key,
                "delivery_mode": definition.delivery_mode,
                "record_type": definition.record_type,
                "adapter_key": DEFAULT_ADAPTER_KEY,
                "source_fetch_mode": source_fetch_mode,
                "source_block_count": source_block_count,
                "landing_block_count": len(selected_blocks),
                "expanded_interval_count": len(reads),
                "window_updates": window_updates,
            },
        )

    def finalize_ingest(
        self,
        session: Session,
        instance: AdapterInstance,
        run: AdapterRun,
        envelope: AdapterIngestEnvelope,
        ingest_summary: dict[str, int] | None,
    ) -> None:
        if ingest_summary is None:
            return

        ingest_batch_id = ingest_summary.get("ingest_batch_id")
        if ingest_batch_id is None:
            return

        raw_updates = envelope.details.get("window_updates")
        if not isinstance(raw_updates, list):
            return

        for raw_update in raw_updates:
            if not isinstance(raw_update, dict):
                continue
            interval_size_minutes = _parse_optional_positive_int(
                raw_update.get("interval_size_minutes")
            )
            if interval_size_minutes is None:
                continue
            expected_slot_codes = raw_update.get("expected_slot_codes")
            if not isinstance(expected_slot_codes, list) or not expected_slot_codes:
                expected_slot_codes = _expected_slot_codes(interval_size_minutes)
            received_slot_codes = raw_update.get("received_slot_codes")
            if not isinstance(received_slot_codes, list):
                received_slot_codes = []
            window_start_at = _parse_runtime_timestamp(
                raw_update.get("window_start_at"),
                error_code="invalid_window_start_at",
                fallback_message="Window state update requires a valid ISO window start timestamp.",
            )
            source_write_ts = _parse_runtime_timestamp(
                raw_update.get("source_write_ts"),
                error_code="invalid_window_source_write_ts",
                fallback_message="Window state update requires a valid ISO source write timestamp.",
            )
            state = session.scalar(
                select(RawIntervalWindowState)
                .where(
                    RawIntervalWindowState.source_system == str(raw_update.get("source_system")),
                    RawIntervalWindowState.meter_identifier
                    == str(raw_update.get("meter_identifier")),
                    RawIntervalWindowState.channel_identifier
                    == str(raw_update.get("channel_identifier")),
                    RawIntervalWindowState.window_start_at == window_start_at,
                    RawIntervalWindowState.window_size_minutes
                    == int(raw_update.get("window_size_minutes") or 60),
                )
                .limit(1)
            )

            merged_slots = set(received_slot_codes)
            late_update_count = 0
            first_source_write_ts = source_write_ts
            last_source_write_ts = source_write_ts
            if state is not None:
                merged_slots |= _decode_slot_bitmap(state.received_slot_bitmap)
                first_source_write_ts = min(
                    [value for value in (state.first_source_write_ts, source_write_ts) if value]
                )
                last_source_write_ts = max(
                    [value for value in (state.last_source_write_ts, source_write_ts) if value]
                )
                late_update_count = state.late_update_count

            expected_slot_count = len(expected_slot_codes)
            completion_status = "open"
            if merged_slots:
                completion_status = (
                    "complete" if len(merged_slots) >= expected_slot_count else "partial"
                )
            if (
                state is not None
                and state.completion_status in {"complete", "late_update"}
                and source_write_ts > (state.last_source_write_ts or source_write_ts)
            ):
                completion_status = "late_update"
                late_update_count += 1

            state_details = {
                "expected_slot_codes": expected_slot_codes,
                "last_received_slot_codes": sorted(received_slot_codes),
                "landing_lp_em_read_block_id": raw_update.get("landing_lp_em_read_block_id"),
                "source_block_key": raw_update.get("source_block_key"),
            }

            if state is None:
                state = RawIntervalWindowState(
                    source_system=str(raw_update.get("source_system")),
                    meter_identifier=str(raw_update.get("meter_identifier")),
                    channel_identifier=str(raw_update.get("channel_identifier")),
                    window_start_at=window_start_at,
                    window_size_minutes=int(raw_update.get("window_size_minutes") or 60),
                    interval_size_minutes=interval_size_minutes,
                    expected_slot_count=expected_slot_count,
                    received_slot_count=len(merged_slots),
                    received_slot_bitmap=_encode_slot_bitmap(merged_slots),
                    first_source_write_ts=first_source_write_ts,
                    last_source_write_ts=last_source_write_ts,
                    completion_status=completion_status,
                    late_update_count=late_update_count,
                    last_adapter_run_id=run.id,
                    last_ingest_batch_id=ingest_batch_id,
                    details=state_details,
                )
                session.add(state)
            else:
                state.interval_size_minutes = interval_size_minutes
                state.expected_slot_count = max(state.expected_slot_count, expected_slot_count)
                state.received_slot_count = len(merged_slots)
                state.received_slot_bitmap = _encode_slot_bitmap(merged_slots)
                state.first_source_write_ts = first_source_write_ts
                state.last_source_write_ts = last_source_write_ts
                state.completion_status = completion_status
                state.late_update_count = late_update_count
                state.last_adapter_run_id = run.id
                state.last_ingest_batch_id = ingest_batch_id
                state.details = state_details
            session.flush()


RUNTIME_ADAPTERS: dict[str, RuntimeAdapter] = {
    "company_hes_poll_v1": CompanyHesPollRuntime(),
    "nuri_aimir_hes_lp_em_poll_v1": NuriAimirHesLpEmPollRuntime(),
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
    record_operational_event(
        session,
        "adapter_run_started",
        occurred_at=started_at,
        adapter_instance=run.adapter_instance,
        adapter_run=run,
        details={"trigger_type": run.trigger_type, **run.details},
        instance_code=run.adapter_instance.instance_code,
    )
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
    record_operational_event(
        session,
        "adapter_run_completed",
        occurred_at=completed_at,
        adapter_instance=instance,
        adapter_run=run,
        details={
            "trigger_type": run.trigger_type,
            "source_rows_fetched": envelope.source_rows_fetched,
            "ingest_batches_created": ingest_batches_created,
            "ingest_records_created": ingest_records_created,
            "watermark_before": envelope.watermark_before,
            "watermark_after": envelope.watermark_after,
        },
        instance_code=instance.instance_code,
        source_rows_fetched=envelope.source_rows_fetched,
        ingest_batches_created=ingest_batches_created,
        ingest_records_created=ingest_records_created,
    )
    close_operational_alerts(
        session,
        event_code="adapter_run_failed",
        adapter_instance_id=instance.id,
        operator_memo="Closed automatically after a successful adapter run.",
        closed_at=completed_at,
    )
    sync_adapter_health_alerts(session, adapter_instance_ids=[instance.id], as_of=completed_at)

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
    record_operational_event(
        session,
        "adapter_run_failed",
        occurred_at=completed_at,
        adapter_instance=instance,
        adapter_run=run,
        details={
            "trigger_type": run.trigger_type,
            "error_code": error.error_code,
            **(error.details or {}),
        },
        instance_code=instance.instance_code,
        error_summary=error.fallback_message,
    )
    sync_adapter_health_alerts(session, adapter_instance_ids=[instance.id], as_of=completed_at)

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
            finalize_ingest = getattr(runtime, "finalize_ingest", None)
            if callable(finalize_ingest):
                finalize_ingest(
                    session,
                    run.adapter_instance,
                    run,
                    envelope,
                    ingest_summary,
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
