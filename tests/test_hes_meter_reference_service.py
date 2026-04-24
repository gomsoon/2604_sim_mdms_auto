from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import HesMeterReference, HesSystem
from app.services.hes_meter_references import (
    HesMeterReferenceValidationError,
    list_hes_meter_references,
    upsert_hes_meter_reference,
)


def _create_hes_system(session, *, hes_code: str) -> HesSystem:
    hes_system = HesSystem(
        hes_code=hes_code,
        display_name=f"{hes_code} Display",
        source_family="hes",
        status="active",
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def test_upsert_hes_meter_reference_creates_minimal_row(session):
    hes_system = _create_hes_system(session, hes_code="AIMIR")

    reference = upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system.id,
        source_table_name="METER",
        source_meter_id="796",
        source_meter_key="32418",
        meter_name="EnergyMeter",
        meter_status_code="140",
        lp_interval_minutes=60,
        meter_type_code="7",
        device_model_code="11",
        location_source_id="1",
        supplier_source_id="10",
        source_payload={"ID": "796", "MDS_ID": "32418"},
        last_synced_at=datetime(2026, 4, 24, 4, 0, tzinfo=timezone.utc),
    )
    session.commit()

    stored = session.scalar(select(HesMeterReference).where(HesMeterReference.id == reference.id))

    assert stored is not None
    assert stored.hes_system_id == hes_system.id
    assert stored.source_table_name == "METER"
    assert stored.source_meter_id == "796"
    assert stored.source_meter_key == "32418"
    assert stored.lp_interval_minutes == 60
    assert stored.source_payload["MDS_ID"] == "32418"


def test_upsert_hes_meter_reference_updates_existing_row_by_source_meter_id(session):
    hes_system = _create_hes_system(session, hes_code="AIMIR")
    first = upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system.id,
        source_table_name="METER",
        source_meter_id="796",
        source_meter_key="32418",
        meter_name="EnergyMeter",
        meter_status_code="140",
        lp_interval_minutes=60,
        source_payload={"ID": "796", "MDS_ID": "32418", "LP_INTERVAL": 60},
    )
    session.commit()

    updated = upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system.id,
        source_table_name="METER",
        source_meter_id="796",
        source_meter_key="32418",
        meter_name="EnergyMeter Updated",
        meter_status_code="151",
        lp_interval_minutes=30,
        source_payload={"ID": "796", "MDS_ID": "32418", "LP_INTERVAL": 30},
    )
    session.commit()

    rows = session.scalars(select(HesMeterReference).order_by(HesMeterReference.id.asc())).all()

    assert first.id == updated.id
    assert len(rows) == 1
    assert rows[0].meter_name == "EnergyMeter Updated"
    assert rows[0].meter_status_code == "151"
    assert rows[0].lp_interval_minutes == 30


def test_upsert_hes_meter_reference_rejects_duplicate_source_meter_key_within_same_hes(session):
    hes_system = _create_hes_system(session, hes_code="AIMIR")
    upsert_hes_meter_reference(
        session,
        hes_system_id=hes_system.id,
        source_table_name="METER",
        source_meter_id="796",
        source_meter_key="32418",
        source_payload={"ID": "796", "MDS_ID": "32418"},
    )
    session.commit()

    with pytest.raises(HesMeterReferenceValidationError) as exc_info:
        upsert_hes_meter_reference(
            session,
            hes_system_id=hes_system.id,
            source_table_name="METER",
            source_meter_id="797",
            source_meter_key="32418",
            source_payload={"ID": "797", "MDS_ID": "32418"},
        )

    assert exc_info.value.error_code == "duplicate_source_meter_key"


def test_hes_meter_reference_allows_same_source_meter_key_across_different_hes(session):
    first_hes = _create_hes_system(session, hes_code="AIMIR")
    second_hes = _create_hes_system(session, hes_code="AIMIR_POLAND")

    upsert_hes_meter_reference(
        session,
        hes_system_id=first_hes.id,
        source_table_name="METER",
        source_meter_id="796",
        source_meter_key="32418",
        source_payload={"ID": "796", "MDS_ID": "32418"},
    )
    upsert_hes_meter_reference(
        session,
        hes_system_id=second_hes.id,
        source_table_name="METER",
        source_meter_id="900",
        source_meter_key="32418",
        source_payload={"ID": "900", "MDS_ID": "32418"},
    )
    session.commit()

    first_rows = session.scalars(
        select(HesMeterReference).where(HesMeterReference.hes_system_id == first_hes.id)
    ).all()
    second_rows = session.scalars(
        select(HesMeterReference).where(HesMeterReference.hes_system_id == second_hes.id)
    ).all()

    assert len(first_rows) == 1
    assert len(second_rows) == 1


def test_hes_meter_reference_unique_constraints_allow_multiple_null_source_meter_keys(session):
    hes_system = _create_hes_system(session, hes_code="AIMIR")
    session.add_all(
        [
            HesMeterReference(
                hes_system_id=hes_system.id,
                source_table_name="METER",
                source_meter_id="796",
                source_meter_key=None,
                source_payload={"ID": "796"},
                last_synced_at=datetime.now(timezone.utc),
            ),
            HesMeterReference(
                hes_system_id=hes_system.id,
                source_table_name="METER",
                source_meter_id="797",
                source_meter_key=None,
                source_payload={"ID": "797"},
                last_synced_at=datetime.now(timezone.utc),
            ),
        ]
    )

    session.commit()


def test_hes_meter_reference_unique_constraint_rejects_duplicate_source_meter_id(session):
    hes_system = _create_hes_system(session, hes_code="AIMIR")
    session.add_all(
        [
            HesMeterReference(
                hes_system_id=hes_system.id,
                source_table_name="METER",
                source_meter_id="796",
                source_payload={"ID": "796"},
                last_synced_at=datetime.now(timezone.utc),
            ),
            HesMeterReference(
                hes_system_id=hes_system.id,
                source_table_name="METER",
                source_meter_id="796",
                source_payload={"ID": "796-second"},
                last_synced_at=datetime.now(timezone.utc),
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_list_hes_meter_references_returns_only_requested_hes(session):
    first_hes = _create_hes_system(session, hes_code="AIMIR")
    second_hes = _create_hes_system(session, hes_code="AIMIR_POLAND")
    upsert_hes_meter_reference(
        session,
        hes_system_id=first_hes.id,
        source_table_name="METER",
        source_meter_id="796",
        source_meter_key="32418",
        source_payload={"ID": "796", "MDS_ID": "32418"},
    )
    upsert_hes_meter_reference(
        session,
        hes_system_id=second_hes.id,
        source_table_name="METER",
        source_meter_id="900",
        source_meter_key="90001",
        source_payload={"ID": "900", "MDS_ID": "90001"},
    )
    session.commit()

    rows = list_hes_meter_references(session, hes_system_id=first_hes.id)

    assert len(rows) == 1
    assert rows[0].hes_system_id == first_hes.id
    assert rows[0].source_meter_id == "796"
