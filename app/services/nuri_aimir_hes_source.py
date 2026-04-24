from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True, slots=True)
class NuriAimirHesLpEmCursor:
    write_date: str
    business_hour: str
    meter_id: str
    channel: str


@dataclass(frozen=True, slots=True)
class NuriAimirHesPollingConfig:
    host: str
    port: int
    username: str
    password: str
    sid: str | None
    service_name: str | None
    batch_size: int
    allowed_channels: tuple[str, ...]
    business_hour_from: str | None
    business_hour_to: str | None


@dataclass(frozen=True, slots=True)
class NuriAimirHesMeterReferenceConfig:
    host: str
    port: int
    username: str
    password: str
    sid: str | None
    service_name: str | None


@dataclass(frozen=True, slots=True)
class NuriAimirHesRuntimeConfig:
    source_timezone_name: str
    default_interval_minutes: int | None
    unit_of_measure: str
    source_fetch_mode: str
    sample_blocks: tuple[dict[str, Any], ...]
    polling_config: NuriAimirHesPollingConfig | None


@dataclass(frozen=True, slots=True)
class NuriAimirHesSourceError(RuntimeError):
    error_code: str
    fallback_message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.fallback_message


SELECT_COLUMNS = [
    "LP_EM.METER_ID",
    "LP_EM.DEVICE_ID",
    "LP_EM.MDEV_ID",
    "LP_EM.MDEV_TYPE",
    "LP_EM.YYYYMMDDHH",
    "LP_EM.HH",
    "LP_EM.WRITEDATE",
    "LP_EM.CHANNEL",
    "LP_EM.VALUE_CNT",
    "LP_EM.VALUE",
    "LP_EM.LOCATION_ID",
    "LP_EM.SUPPLIER_ID",
    "LP_EM.ENDDEVICE_ID",
    "METER.LP_INTERVAL",
    *[f"LP_EM.VALUE_{slot_index:02d}" for slot_index in range(60)],
]

METER_REFERENCE_SELECT_COLUMNS = [
    "METER.ID",
    "METER.MDS_ID",
    "METER.METER",
    "METER.METER_STATUS",
    "METER.LP_INTERVAL",
    "METER.METERTYPE_ID",
    "METER.DEVICEMODEL_ID",
    "METER.MODEM_ID",
    "METER.LOCATION_ID",
    "METER.SUPPLIER_ID",
    "METER.LAST_READ_DATE",
    "METER.WRITE_DATE",
]


def resolve_env_secret(secret_ref: str | None) -> str:
    normalized = str(secret_ref or "").strip()
    if not normalized:
        raise ValueError("Oracle polling requires a secret_ref for the source password.")
    if not normalized.startswith("env://"):
        raise ValueError("Oracle polling currently supports only env:// secret references.")

    env_name = normalized.removeprefix("env://").strip()
    if not env_name:
        raise ValueError("Oracle polling secret_ref must include an environment variable name.")

    value = os.getenv(env_name)
    if not value:
        raise ValueError(
            f"Oracle polling secret_ref points to environment variable '{env_name}', but it is not set."
        )
    return value


def _parse_optional_positive_int(value: Any, *, field_name: str) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a positive integer when provided.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be a positive integer when provided.")
    return parsed


def _parse_optional_business_hour(value: Any, *, field_name: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if not re.fullmatch(r"\d{10}", normalized):
        raise ValueError(f"{field_name} must use YYYYMMDDHH format when provided.")
    return normalized


def parse_nuri_aimir_hes_lp_em_cursor(value: str | None) -> NuriAimirHesLpEmCursor | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None

    parts = normalized.split("|")
    if len(parts) != 4 or any(not part for part in parts):
        raise ValueError("LP_EM cursor must use WRITEDATE|YYYYMMDDHH|METER_ID|CHANNEL format.")
    return NuriAimirHesLpEmCursor(
        write_date=parts[0],
        business_hour=parts[1],
        meter_id=parts[2],
        channel=parts[3],
    )


def format_nuri_aimir_hes_lp_em_cursor(cursor: NuriAimirHesLpEmCursor | None) -> str | None:
    if cursor is None:
        return None
    return "|".join((cursor.write_date, cursor.business_hour, cursor.meter_id, cursor.channel))


def parse_nuri_aimir_hes_polling_config(
    runtime_config: dict[str, Any],
    *,
    secret_ref: str | None,
    batch_size: int | None,
) -> NuriAimirHesPollingConfig:
    host = str(runtime_config.get("oracle_host") or "").strip()
    if not host:
        raise ValueError("Oracle polling requires oracle_host in the masked configuration.")

    try:
        port = int(runtime_config.get("oracle_port") or 1521)
    except (TypeError, ValueError) as exc:
        raise ValueError("Oracle polling requires oracle_port to be a valid integer.") from exc
    if port <= 0:
        raise ValueError("Oracle polling requires oracle_port to be a positive integer.")

    username = str(runtime_config.get("oracle_username") or "").strip()
    if not username:
        raise ValueError("Oracle polling requires oracle_username in the masked configuration.")

    sid = str(runtime_config.get("oracle_sid") or "").strip() or None
    service_name = str(runtime_config.get("oracle_service_name") or "").strip() or None
    if bool(sid) == bool(service_name):
        raise ValueError(
            "Oracle polling requires exactly one of oracle_sid or oracle_service_name."
        )

    effective_batch_size = batch_size or int(runtime_config.get("oracle_batch_size") or 0)
    if effective_batch_size <= 0:
        raise ValueError("Oracle polling requires a positive batch size.")

    raw_allowed_channels = runtime_config.get("allowed_channels") or []
    if isinstance(raw_allowed_channels, str):
        raw_allowed_channels = [raw_allowed_channels]
    if not isinstance(raw_allowed_channels, list):
        raise ValueError("Oracle polling allowed_channels must be a list when provided.")

    allowed_channels = tuple(str(value).strip() for value in raw_allowed_channels if str(value).strip())
    business_hour_from = _parse_optional_business_hour(
        runtime_config.get("oracle_business_hour_from"),
        field_name="oracle_business_hour_from",
    )
    business_hour_to = _parse_optional_business_hour(
        runtime_config.get("oracle_business_hour_to"),
        field_name="oracle_business_hour_to",
    )
    if (
        business_hour_from is not None
        and business_hour_to is not None
        and business_hour_from > business_hour_to
    ):
        raise ValueError(
            "oracle_business_hour_from must be less than or equal to oracle_business_hour_to."
        )

    return NuriAimirHesPollingConfig(
        host=host,
        port=port,
        username=username,
        password=resolve_env_secret(secret_ref),
        sid=sid,
        service_name=service_name,
        batch_size=effective_batch_size,
        allowed_channels=allowed_channels,
        business_hour_from=business_hour_from,
        business_hour_to=business_hour_to,
    )


def parse_nuri_aimir_hes_meter_reference_config(
    runtime_config: dict[str, Any],
    *,
    secret_ref: str | None,
) -> NuriAimirHesMeterReferenceConfig:
    host = str(runtime_config.get("oracle_host") or "").strip()
    if not host:
        raise ValueError("Oracle meter reference sync requires oracle_host in the masked configuration.")

    try:
        port = int(runtime_config.get("oracle_port") or 1521)
    except (TypeError, ValueError) as exc:
        raise ValueError("Oracle meter reference sync requires oracle_port to be a valid integer.") from exc
    if port <= 0:
        raise ValueError("Oracle meter reference sync requires oracle_port to be a positive integer.")

    username = str(runtime_config.get("oracle_username") or "").strip()
    if not username:
        raise ValueError("Oracle meter reference sync requires oracle_username in the masked configuration.")

    sid = str(runtime_config.get("oracle_sid") or "").strip() or None
    service_name = str(runtime_config.get("oracle_service_name") or "").strip() or None
    if bool(sid) == bool(service_name):
        raise ValueError(
            "Oracle meter reference sync requires exactly one of oracle_sid or oracle_service_name."
        )

    return NuriAimirHesMeterReferenceConfig(
        host=host,
        port=port,
        username=username,
        password=resolve_env_secret(secret_ref),
        sid=sid,
        service_name=service_name,
    )


def parse_nuri_aimir_hes_runtime_config(
    runtime_config: dict[str, Any],
    *,
    secret_ref: str | None,
    batch_size: int | None,
) -> NuriAimirHesRuntimeConfig:
    source_timezone_name = str(runtime_config.get("source_timezone") or "").strip()
    if not source_timezone_name:
        raise ValueError("The polling adapter requires an explicit source timezone.")
    try:
        ZoneInfo(source_timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("The configured source timezone is not recognized.") from exc

    default_interval_minutes = _parse_optional_positive_int(
        runtime_config.get("default_interval_minutes"),
        field_name="default_interval_minutes",
    )
    unit_of_measure = str(runtime_config.get("unit_of_measure") or "kWh").strip() or "kWh"

    raw_sample_blocks = runtime_config.get("sample_blocks")
    has_sample_blocks = raw_sample_blocks is not None
    if has_sample_blocks and not isinstance(raw_sample_blocks, list):
        raise ValueError("sample_blocks must be a JSON array when provided.")
    sample_blocks = tuple(raw_sample_blocks or [])
    if any(not isinstance(row, dict) for row in sample_blocks):
        raise ValueError("Every sample_blocks entry must be a JSON object.")

    has_oracle_settings = any(
        [
            str(runtime_config.get("oracle_host") or "").strip(),
            str(runtime_config.get("oracle_username") or "").strip(),
            str(runtime_config.get("oracle_sid") or "").strip(),
            str(runtime_config.get("oracle_service_name") or "").strip(),
            str(secret_ref or "").strip(),
        ]
    )

    if has_sample_blocks and has_oracle_settings:
        raise ValueError(
            "Choose exactly one NURI AIMIR HES source fetch mode: sample_blocks or Oracle polling."
        )

    if has_sample_blocks:
        source_fetch_mode = "sample_blocks"
        polling_config = None
    else:
        source_fetch_mode = "oracle_query"
        polling_config = parse_nuri_aimir_hes_polling_config(
            runtime_config,
            secret_ref=secret_ref,
            batch_size=batch_size,
        )

    return NuriAimirHesRuntimeConfig(
        source_timezone_name=source_timezone_name,
        default_interval_minutes=default_interval_minutes,
        unit_of_measure=unit_of_measure,
        source_fetch_mode=source_fetch_mode,
        sample_blocks=sample_blocks,
        polling_config=polling_config,
    )


def _build_allowed_channel_clause(allowed_channels: tuple[str, ...]) -> tuple[str, dict[str, Any]]:
    if not allowed_channels:
        return "", {}

    bind_names = []
    binds: dict[str, Any] = {}
    for index, channel in enumerate(allowed_channels):
        name = f"channel_{index}"
        bind_names.append(f":{name}")
        binds[name] = channel
    return f" and LP_EM.CHANNEL in ({', '.join(bind_names)})", binds


def _build_lp_em_query(
    *,
    batch_size: int,
    allowed_channels: tuple[str, ...],
    business_hour_from: str | None,
    business_hour_to: str | None,
    has_cursor: bool,
) -> tuple[str, dict[str, Any]]:
    allowed_channel_sql, allowed_channel_binds = _build_allowed_channel_clause(allowed_channels)
    where_sql = "1 = 1"
    bind_values: dict[str, Any] = dict(allowed_channel_binds)

    if business_hour_from is not None:
        where_sql += "\n            and LP_EM.YYYYMMDDHH >= :business_hour_from"
        bind_values["business_hour_from"] = business_hour_from
    if business_hour_to is not None:
        where_sql += "\n            and LP_EM.YYYYMMDDHH <= :business_hour_to"
        bind_values["business_hour_to"] = business_hour_to

    if has_cursor:
        cursor_where_sql = """
            (
                LP_EM.WRITEDATE > :cursor_writedate
                or (
                    LP_EM.WRITEDATE = :cursor_writedate
                    and (
                        LP_EM.YYYYMMDDHH > :cursor_business_hour
                        or (
                            LP_EM.YYYYMMDDHH = :cursor_business_hour
                            and (
                                LP_EM.METER_ID > :cursor_meter_id
                                or (
                                    LP_EM.METER_ID = :cursor_meter_id
                                    and LP_EM.CHANNEL > :cursor_channel
                                )
                            )
                        )
                    )
                )
            )
        """.strip()
        where_sql += f"\n            and {cursor_where_sql}"

    query = f"""
        select {", ".join(SELECT_COLUMNS)}
        from LP_EM
        left join METER on LP_EM.METER_ID = METER.ID
        where {where_sql}
        {allowed_channel_sql}
        order by LP_EM.WRITEDATE, LP_EM.YYYYMMDDHH, LP_EM.METER_ID, LP_EM.CHANNEL
        fetch first {int(batch_size)} rows only
    """.strip()
    return query, bind_values


def _build_meter_reference_query() -> str:
    return f"""
        select {", ".join(METER_REFERENCE_SELECT_COLUMNS)}
        from METER
        order by METER.ID
    """.strip()


def _classify_connect_error(exc: Exception) -> NuriAimirHesSourceError:
    rendered = str(exc)
    if "ORA-01017" in rendered or "ORA-28000" in rendered or "ORA-28001" in rendered:
        return NuriAimirHesSourceError(
            "nuri_aimir_hes_authentication_failed",
            "The NURI AIMIR HES Oracle authentication failed.",
            details={"exception_type": type(exc).__name__},
        )
    return NuriAimirHesSourceError(
        "nuri_aimir_hes_connection_failed",
        "The NURI AIMIR HES Oracle connection could not be established.",
        details={"exception_type": type(exc).__name__},
    )


def fetch_nuri_aimir_hes_lp_em_rows(
    config: NuriAimirHesPollingConfig,
    *,
    cursor: NuriAimirHesLpEmCursor | None,
) -> list[dict[str, Any]]:
    try:
        import oracledb
    except ImportError as exc:
        raise NuriAimirHesSourceError(
            "oracle_driver_unavailable",
            "The Python Oracle driver is not available in the current runtime.",
            details={"exception_type": type(exc).__name__},
        ) from exc

    if config.sid:
        dsn = oracledb.makedsn(config.host, config.port, sid=config.sid)
    else:
        dsn = oracledb.makedsn(config.host, config.port, service_name=config.service_name)

    query, bind_values = _build_lp_em_query(
        batch_size=config.batch_size,
        allowed_channels=config.allowed_channels,
        business_hour_from=config.business_hour_from,
        business_hour_to=config.business_hour_to,
        has_cursor=cursor is not None,
    )
    if cursor is not None:
        bind_values.update(
            {
                "cursor_writedate": cursor.write_date,
                "cursor_business_hour": cursor.business_hour,
                "cursor_meter_id": cursor.meter_id,
                "cursor_channel": cursor.channel,
            }
        )

    try:
        connection = oracledb.connect(user=config.username, password=config.password, dsn=dsn)
    except Exception as exc:
        raise _classify_connect_error(exc) from exc
    try:
        cursor_obj = connection.cursor()
        try:
            try:
                cursor_obj.execute(query, bind_values)
            except Exception as exc:
                raise NuriAimirHesSourceError(
                    "nuri_aimir_hes_query_failed",
                    "The NURI AIMIR HES Oracle polling query failed.",
                    details={"exception_type": type(exc).__name__},
                ) from exc
            column_names = [column[0] for column in cursor_obj.description or []]
            return [dict(zip(column_names, row, strict=False)) for row in cursor_obj.fetchall()]
        finally:
            cursor_obj.close()
    finally:
        connection.close()


def fetch_nuri_aimir_hes_meter_rows(
    config: NuriAimirHesMeterReferenceConfig,
) -> list[dict[str, Any]]:
    try:
        import oracledb
    except ImportError as exc:
        raise NuriAimirHesSourceError(
            "oracle_driver_unavailable",
            "The Python Oracle driver is not available in the current runtime.",
            details={"exception_type": type(exc).__name__},
        ) from exc

    if config.sid:
        dsn = oracledb.makedsn(config.host, config.port, sid=config.sid)
    else:
        dsn = oracledb.makedsn(config.host, config.port, service_name=config.service_name)

    try:
        connection = oracledb.connect(user=config.username, password=config.password, dsn=dsn)
    except Exception as exc:
        raise _classify_connect_error(exc) from exc
    try:
        cursor_obj = connection.cursor()
        try:
            try:
                cursor_obj.execute(_build_meter_reference_query())
            except Exception as exc:
                raise NuriAimirHesSourceError(
                    "nuri_aimir_hes_query_failed",
                    "The NURI AIMIR HES Oracle polling query failed.",
                    details={"exception_type": type(exc).__name__},
                ) from exc
            column_names = [column[0] for column in cursor_obj.description or []]
            return [dict(zip(column_names, row, strict=False)) for row in cursor_obj.fetchall()]
        finally:
            cursor_obj.close()
    finally:
        connection.close()
