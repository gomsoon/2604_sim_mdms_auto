from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import HesMeterReference, HesSystem
from app.services.hes_meter_reference_sync import (
    HesMeterReferenceSyncError,
    sync_hes_meter_references,
)


def _create_hes_system(session, *, hes_code: str, source_family: str, connection_config_masked: dict) -> HesSystem:
    hes_system = HesSystem(
        hes_code=hes_code,
        display_name=f"{hes_code} Display",
        source_family=source_family,
        status="active",
        connection_config_masked=connection_config_masked,
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def test_sync_hes_meter_references_creates_aimir_subset_rows(session, monkeypatch):
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    hes_system = _create_hes_system(
        session,
        hes_code="AIMIR",
        source_family="nuri_aimir_hes",
        connection_config_masked={
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
            "oracle_secret_ref": "env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
        },
    )

    def fake_fetch(config):
        assert config.host == "172.16.10.111"
        assert config.username == "aimir"
        return [
            {
                "ID": "796",
                "MDS_ID": "32418",
                "METER": "EnergyMeter",
                "METER_STATUS": "140",
                "LP_INTERVAL": 60,
                "METERTYPE_ID": "7",
                "DEVICEMODEL_ID": "11",
                "MODEM_ID": "22",
                "LOCATION_ID": "1",
                "SUPPLIER_ID": "10",
                "LAST_READ_DATE": "20240315150102",
                "WRITE_DATE": "20240315150505",
            },
            {
                "ID": "797",
                "MDS_ID": "32419",
                "METER": "EnergyMeter",
                "METER_STATUS": "151",
                "LP_INTERVAL": 30,
                "METERTYPE_ID": "7",
                "DEVICEMODEL_ID": "12",
                "MODEM_ID": "23",
                "LOCATION_ID": "2",
                "SUPPLIER_ID": "10",
                "LAST_READ_DATE": "20240316150102",
                "WRITE_DATE": "20240316150505",
            },
        ]

    monkeypatch.setattr(
        "app.services.hes_meter_reference_sync.fetch_nuri_aimir_hes_meter_rows",
        fake_fetch,
    )

    summary = sync_hes_meter_references(session, hes_code=hes_system.hes_code)
    session.commit()

    rows = session.scalars(
        select(HesMeterReference)
        .where(HesMeterReference.hes_system_id == hes_system.id)
        .order_by(HesMeterReference.source_meter_id.asc())
    ).all()

    assert summary.rows_fetched == 2
    assert summary.created == 2
    assert summary.updated == 0
    assert len(rows) == 2
    assert rows[0].source_meter_key == "32418"
    assert rows[0].lp_interval_minutes == 60
    assert rows[1].meter_status_code == "151"


def test_sync_hes_meter_references_updates_existing_rows_idempotently(session, monkeypatch):
    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    hes_system = _create_hes_system(
        session,
        hes_code="AIMIR",
        source_family="nuri_aimir_hes",
        connection_config_masked={
            "oracle_host": "172.16.10.111",
            "oracle_port": 1521,
            "oracle_sid": "HESDB",
            "oracle_username": "aimir",
            "oracle_secret_ref": "env://MDMS_NURI_AIMIR_HES_DB_PASSWORD",
        },
    )

    first_payload = [
        {
            "ID": "796",
            "MDS_ID": "32418",
            "METER": "EnergyMeter",
            "METER_STATUS": "140",
            "LP_INTERVAL": 60,
            "METERTYPE_ID": "7",
            "DEVICEMODEL_ID": "11",
            "MODEM_ID": "22",
            "LOCATION_ID": "1",
            "SUPPLIER_ID": "10",
            "LAST_READ_DATE": "20240315150102",
            "WRITE_DATE": "20240315150505",
        }
    ]
    second_payload = [
        {
            "ID": "796",
            "MDS_ID": "32418",
            "METER": "EnergyMeter Updated",
            "METER_STATUS": "151",
            "LP_INTERVAL": 30,
            "METERTYPE_ID": "7",
            "DEVICEMODEL_ID": "11",
            "MODEM_ID": "22",
            "LOCATION_ID": "1",
            "SUPPLIER_ID": "10",
            "LAST_READ_DATE": "20240317150102",
            "WRITE_DATE": "20240317150505",
        }
    ]
    payloads = [first_payload, second_payload]

    monkeypatch.setattr(
        "app.services.hes_meter_reference_sync.fetch_nuri_aimir_hes_meter_rows",
        lambda config: payloads.pop(0),
    )

    first_summary = sync_hes_meter_references(session, hes_code=hes_system.hes_code)
    session.commit()
    second_summary = sync_hes_meter_references(session, hes_code=hes_system.hes_code)
    session.commit()

    row = session.scalar(
        select(HesMeterReference).where(HesMeterReference.hes_system_id == hes_system.id).limit(1)
    )

    assert first_summary.created == 1
    assert first_summary.updated == 0
    assert second_summary.created == 0
    assert second_summary.updated == 1
    assert row is not None
    assert row.meter_name == "EnergyMeter Updated"
    assert row.meter_status_code == "151"
    assert row.lp_interval_minutes == 30


def test_sync_hes_meter_references_rejects_unsupported_source_family(session):
    hes_system = _create_hes_system(
        session,
        hes_code="HES",
        source_family="hes",
        connection_config_masked={},
    )

    with pytest.raises(HesMeterReferenceSyncError) as exc_info:
        sync_hes_meter_references(session, hes_code=hes_system.hes_code)

    assert exc_info.value.error_code == "unsupported_hes_meter_reference_source_family"
