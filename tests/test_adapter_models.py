from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AdapterDefinition,
    AdapterInstance,
    AdapterRun,
    AdapterWatermark,
    HesSystem,
    IngestBatch,
)


def _create_adapter_definition(session) -> AdapterDefinition:
    definition = AdapterDefinition(
        adapter_code="company_hes_poll_v1",
        display_name="Company HES Poll",
        delivery_mode="poll",
        source_family="hes",
        record_type="hes_read_raw",
        adapter_profile_key="common_raw_v1",
        implementation_key="company_hes_poll_v1",
        status="active",
        description="Reads company HES rows and forwards them into common raw ingest.",
    )
    session.add(definition)
    session.flush()
    return definition


def _create_hes_system(session, *, hes_code: str) -> HesSystem:
    hes_system = HesSystem(
        hes_code=hes_code,
        display_name=hes_code,
        source_family="hes",
        status="active",
    )
    session.add(hes_system)
    session.flush()
    return hes_system


def _create_adapter_instance(session, definition: AdapterDefinition, *, instance_code: str) -> AdapterInstance:
    hes_system = _create_hes_system(session, hes_code="HES")
    instance = AdapterInstance(
        hes_system_id=hes_system.id,
        adapter_definition_id=definition.id,
        instance_code=instance_code,
        display_name="Company HES Primary",
        source_system="HES",
        admin_state="enabled",
        poll_interval_minutes=5,
        batch_size=500,
        landing_enabled=False,
        connection_config_masked={"host": "hes-db.internal", "database": "hes"},
        secret_ref="env://MDMS_HES_PRIMARY",
    )
    session.add(instance)
    session.flush()
    return instance


def test_adapter_runtime_models_link_instances_runs_watermarks_and_batches(session):
    definition = _create_adapter_definition(session)
    instance = _create_adapter_instance(session, definition, instance_code="company_hes_primary")
    run = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="manual",
        run_status="completed",
        requested_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        source_rows_fetched=12,
        ingest_batches_created=1,
        ingest_records_created=12,
        watermark_before="2026-04-18T00:00:00+09:00",
        watermark_after="2026-04-18T00:15:00+09:00",
        details={"mode": "poll"},
    )
    session.add(run)
    session.flush()

    watermark = AdapterWatermark(
        adapter_instance_id=instance.id,
        record_type="hes_read_raw",
        cursor_type="timestamp",
        cursor_value="2026-04-18T00:15:00+09:00",
        last_source_timestamp=datetime(2026, 4, 17, 15, 15, tzinfo=timezone.utc),
        last_polled_at=datetime.now(timezone.utc),
        details={"column": "measured_at"},
    )
    batch = IngestBatch(
        hes_system_id=instance.hes_system_id,
        source_system="HES",
        batch_id="adapter-batch-001",
        record_type="hes_read_raw",
        received_at=datetime.now(timezone.utc),
        payload={"reads": []},
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
    )
    session.add_all([watermark, batch])
    session.commit()

    assert instance.adapter_definition.adapter_code == "company_hes_poll_v1"
    assert instance.hes_system is not None
    assert instance.hes_system.hes_code == "HES"
    assert instance.adapter_runs[0].trigger_type == "manual"
    assert instance.adapter_watermarks[0].record_type == "hes_read_raw"
    assert instance.ingest_batches[0].batch_id == "adapter-batch-001"
    assert batch.adapter_run is not None
    assert batch.adapter_run.adapter_instance_id == instance.id
    assert batch.hes_system is not None
    assert batch.hes_system.hes_code == "HES"


def test_adapter_instance_code_must_be_unique(session):
    definition = _create_adapter_definition(session)
    _create_adapter_instance(session, definition, instance_code="company_hes_primary")
    session.commit()

    duplicate = AdapterInstance(
        adapter_definition_id=definition.id,
        instance_code="company_hes_primary",
        display_name="Company HES Duplicate",
        source_system="HES",
        admin_state="paused",
        landing_enabled=False,
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_adapter_watermark_scope_is_unique_per_instance_and_record_type(session):
    definition = _create_adapter_definition(session)
    instance = _create_adapter_instance(session, definition, instance_code="company_hes_primary")
    session.commit()

    first = AdapterWatermark(
        adapter_instance_id=instance.id,
        record_type="hes_read_raw",
        cursor_type="timestamp",
        cursor_value="2026-04-18T00:15:00+09:00",
        details={},
    )
    second = AdapterWatermark(
        adapter_instance_id=instance.id,
        record_type="hes_read_raw",
        cursor_type="timestamp",
        cursor_value="2026-04-18T00:30:00+09:00",
        details={},
    )
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_adapter_run_allows_only_one_running_row_per_instance(session):
    definition = _create_adapter_definition(session)
    instance = _create_adapter_instance(session, definition, instance_code="company_hes_primary")
    session.commit()

    first = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="schedule",
        run_status="running",
        requested_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        details={"ordinal": 1},
    )
    second = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="manual",
        run_status="running",
        requested_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        details={"ordinal": 2},
    )
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
