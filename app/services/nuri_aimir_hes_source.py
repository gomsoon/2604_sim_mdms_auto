from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any


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

    return NuriAimirHesPollingConfig(
        host=host,
        port=port,
        username=username,
        password=resolve_env_secret(secret_ref),
        sid=sid,
        service_name=service_name,
        batch_size=effective_batch_size,
        allowed_channels=allowed_channels,
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
    has_cursor: bool,
) -> tuple[str, dict[str, Any]]:
    allowed_channel_sql, allowed_channel_binds = _build_allowed_channel_clause(allowed_channels)
    where_sql = "1 = 1"
    bind_values: dict[str, Any] = dict(allowed_channel_binds)

    if has_cursor:
        where_sql = """
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


def fetch_nuri_aimir_hes_lp_em_rows(
    config: NuriAimirHesPollingConfig,
    *,
    cursor: NuriAimirHesLpEmCursor | None,
) -> list[dict[str, Any]]:
    import oracledb

    if config.sid:
        dsn = oracledb.makedsn(config.host, config.port, sid=config.sid)
    else:
        dsn = oracledb.makedsn(config.host, config.port, service_name=config.service_name)

    query, bind_values = _build_lp_em_query(
        batch_size=config.batch_size,
        allowed_channels=config.allowed_channels,
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

    connection = oracledb.connect(user=config.username, password=config.password, dsn=dsn)
    try:
        cursor_obj = connection.cursor()
        try:
            cursor_obj.execute(query, bind_values)
            column_names = [column[0] for column in cursor_obj.description or []]
            return [dict(zip(column_names, row, strict=False)) for row in cursor_obj.fetchall()]
        finally:
            cursor_obj.close()
    finally:
        connection.close()
