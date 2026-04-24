from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from app.services.nuri_aimir_hes_source import (
    NuriAimirHesSourceError,
    NuriAimirHesLpEmCursor,
    _build_lp_em_query,
    fetch_nuri_aimir_hes_meter_rows,
    fetch_nuri_aimir_hes_lp_em_rows,
    format_nuri_aimir_hes_lp_em_cursor,
    parse_nuri_aimir_hes_lp_em_cursor,
    parse_nuri_aimir_hes_meter_reference_config,
    parse_nuri_aimir_hes_polling_config,
    parse_nuri_aimir_hes_runtime_config,
    resolve_env_secret,
)


def test_parse_and_format_lp_em_cursor_round_trip():
    cursor = NuriAimirHesLpEmCursor(
        write_date="20240806030100",
        business_hour="2024080603",
        meter_id="32418",
        channel="0",
    )

    serialized = format_nuri_aimir_hes_lp_em_cursor(cursor)

    assert serialized == "20240806030100|2024080603|32418|0"
    assert parse_nuri_aimir_hes_lp_em_cursor(serialized) == cursor


def test_parse_nuri_aimir_hes_polling_config_reads_env_secret_and_channels(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    config = parse_nuri_aimir_hes_polling_config(
        {
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
            "allowed_channels": ["0", "98"],
            "oracle_business_hour_from": "2024080600",
            "oracle_business_hour_to": "2024080603",
        },
        secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
        batch_size=500,
    )

    assert config.host == "172.16.10.111"
    assert config.port == 1521
    assert config.sid == "HESDB"
    assert config.service_name is None
    assert config.username == "aimir"
    assert config.password == "oracle-secret"
    assert config.batch_size == 500
    assert config.allowed_channels == ("0", "98")
    assert config.business_hour_from == "2024080600"
    assert config.business_hour_to == "2024080603"


def test_parse_nuri_aimir_hes_meter_reference_config_reads_env_secret(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    config = parse_nuri_aimir_hes_meter_reference_config(
        {
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
        },
        secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
    )

    assert config.host == "172.16.10.111"
    assert config.port == 1521
    assert config.sid == "HESDB"
    assert config.service_name is None
    assert config.username == "aimir"
    assert config.password == "oracle-secret"


def test_parse_nuri_aimir_hes_polling_config_rejects_invalid_business_hour_range(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    with pytest.raises(ValueError):
        parse_nuri_aimir_hes_polling_config(
            {
                "oracle_host": "172.16.10.111",
                "oracle_port": 1521,
                "oracle_sid": "HESDB",
                "oracle_username": "aimir",
                "oracle_business_hour_from": "2024080604",
                "oracle_business_hour_to": "2024080603",
            },
            secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
            batch_size=500,
        )


def test_parse_nuri_aimir_hes_runtime_config_supports_sample_mode():
    runtime_config = parse_nuri_aimir_hes_runtime_config(
        {
            "source_timezone": "Asia/Seoul",
            "default_interval_minutes": 15,
            "unit_of_measure": "kWh",
            "sample_blocks": [{"METER_ID": "32418"}],
        },
        secret_ref=None,
        batch_size=100,
    )

    assert runtime_config.source_fetch_mode == "sample_blocks"
    assert runtime_config.source_timezone_name == "Asia/Seoul"
    assert runtime_config.default_interval_minutes == 15
    assert runtime_config.sample_blocks == ({"METER_ID": "32418"},)
    assert runtime_config.polling_config is None


def test_parse_nuri_aimir_hes_runtime_config_rejects_mixed_sample_and_oracle_modes(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    with pytest.raises(ValueError):
        parse_nuri_aimir_hes_runtime_config(
            {
                "source_timezone": "Asia/Seoul",
                "sample_blocks": [{"METER_ID": "32418"}],
                "oracle_host": "172.16.10.111",
                "oracle_sid": "HESDB",
                "oracle_username": "aimir",
            },
            secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
            batch_size=100,
        )


def test_parse_nuri_aimir_hes_runtime_config_rejects_invalid_default_interval():
    with pytest.raises(ValueError):
        parse_nuri_aimir_hes_runtime_config(
            {
                "source_timezone": "Asia/Seoul",
                "default_interval_minutes": 0,
                "sample_blocks": [{"METER_ID": "32418"}],
            },
            secret_ref=None,
            batch_size=100,
        )


def test_resolve_env_secret_rejects_missing_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MDMS_MISSING_SECRET", raising=False)

    with pytest.raises(ValueError):
        resolve_env_secret("env://MDMS_MISSING_SECRET")


def test_build_lp_em_query_includes_cursor_and_channel_filters():
    query, binds = _build_lp_em_query(
        batch_size=250,
        allowed_channels=("0", "98"),
        business_hour_from="2024080600",
        business_hour_to="2024080603",
        has_cursor=True,
    )

    assert "LP_EM.WRITEDATE > :cursor_writedate" in query
    assert "LP_EM.CHANNEL in (:channel_0, :channel_1)" in query
    assert "LP_EM.YYYYMMDDHH >= :business_hour_from" in query
    assert "LP_EM.YYYYMMDDHH <= :business_hour_to" in query
    assert "fetch first 250 rows only" in query.lower()
    assert binds == {
        "channel_0": "0",
        "channel_1": "98",
        "business_hour_from": "2024080600",
        "business_hour_to": "2024080603",
    }


def test_fetch_nuri_aimir_hes_lp_em_rows_classifies_authentication_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeOracleDatabaseError(Exception):
        pass

    fake_module = SimpleNamespace(
        makedsn=lambda host, port, sid=None, service_name=None: "fake-dsn",
        connect=lambda **kwargs: (_ for _ in ()).throw(FakeOracleDatabaseError("ORA-01017 invalid")),
    )
    monkeypatch.setitem(sys.modules, "oracledb", fake_module)
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    config = parse_nuri_aimir_hes_polling_config(
        {
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
        },
        secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
        batch_size=100,
    )

    with pytest.raises(NuriAimirHesSourceError) as exc_info:
        fetch_nuri_aimir_hes_lp_em_rows(config, cursor=None)

    assert exc_info.value.error_code == "nuri_aimir_hes_authentication_failed"


def test_fetch_nuri_aimir_hes_lp_em_rows_classifies_query_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeCursor:
        description = []

        def execute(self, query, bind_values):
            raise RuntimeError("query failed")

        def close(self):
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    fake_module = SimpleNamespace(
        makedsn=lambda host, port, sid=None, service_name=None: "fake-dsn",
        connect=lambda **kwargs: FakeConnection(),
    )
    monkeypatch.setitem(sys.modules, "oracledb", fake_module)
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    config = parse_nuri_aimir_hes_polling_config(
        {
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
        },
        secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
        batch_size=100,
    )

    with pytest.raises(NuriAimirHesSourceError) as exc_info:
        fetch_nuri_aimir_hes_lp_em_rows(config, cursor=None)

    assert exc_info.value.error_code == "nuri_aimir_hes_query_failed"


def test_fetch_nuri_aimir_hes_meter_rows_classifies_query_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeCursor:
        description = []

        def execute(self, query):
            raise RuntimeError("query failed")

        def close(self):
            return None

    class FakeConnection:
        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    fake_module = SimpleNamespace(
        makedsn=lambda host, port, sid=None, service_name=None: "fake-dsn",
        connect=lambda **kwargs: FakeConnection(),
    )
    monkeypatch.setitem(sys.modules, "oracledb", fake_module)
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    config = parse_nuri_aimir_hes_meter_reference_config(
        {
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
        },
        secret_ref="env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
    )

    with pytest.raises(NuriAimirHesSourceError) as exc_info:
        fetch_nuri_aimir_hes_meter_rows(config)

    assert exc_info.value.error_code == "nuri_aimir_hes_query_failed"
