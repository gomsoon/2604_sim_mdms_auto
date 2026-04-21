from __future__ import annotations

import pytest

from app.services.nuri_aimir_hes_source import (
    NuriAimirHesLpEmCursor,
    _build_lp_em_query,
    format_nuri_aimir_hes_lp_em_cursor,
    parse_nuri_aimir_hes_lp_em_cursor,
    parse_nuri_aimir_hes_polling_config,
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


def test_resolve_env_secret_rejects_missing_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("MDMS_MISSING_SECRET", raising=False)

    with pytest.raises(ValueError):
        resolve_env_secret("env://MDMS_MISSING_SECRET")


def test_build_lp_em_query_includes_cursor_and_channel_filters():
    query, binds = _build_lp_em_query(
        batch_size=250,
        allowed_channels=("0", "98"),
        has_cursor=True,
    )

    assert "LP_EM.WRITEDATE > :cursor_writedate" in query
    assert "LP_EM.CHANNEL in (:channel_0, :channel_1)" in query
    assert "fetch first 250 rows only" in query.lower()
    assert binds == {"channel_0": "0", "channel_1": "98"}
