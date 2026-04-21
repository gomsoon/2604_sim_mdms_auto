from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    AdapterDefinition,
    AdapterInstance,
    AdapterRun,
    HesReadRaw,
    IngestBatch,
    LandingLpEmReadBlock,
    RawIntervalWindowState,
)


def _create_adapter_runtime(session) -> tuple[AdapterInstance, AdapterRun]:
    definition = AdapterDefinition(
        adapter_code="oracle_lp_em_poll_v1",
        display_name="Oracle LP_EM Poll",
        delivery_mode="poll",
        source_family="hes_overseas",
        record_type="hes_read_raw",
        adapter_profile_key="common_raw_v1",
        implementation_key="oracle_lp_em_poll_v1",
        status="active",
    )
    session.add(definition)
    session.flush()

    instance = AdapterInstance(
        adapter_definition_id=definition.id,
        instance_code="oracle_lp_em_primary",
        display_name="Oracle LP_EM Primary",
        source_system="HES_OVERSEAS",
        admin_state="enabled",
        poll_interval_minutes=5,
        batch_size=500,
        landing_enabled=True,
    )
    session.add(instance)
    session.flush()

    run = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="manual",
        run_status="completed",
        requested_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        details={"mode": "poll"},
    )
    session.add(run)
    session.flush()
    return instance, run


def test_landing_block_links_to_runtime_and_raw_interval(session):
    instance, run = _create_adapter_runtime(session)
    batch = IngestBatch(
        source_system="HES_OVERSEAS",
        batch_id="batch-001",
        record_type="hes_read_raw",
        received_at=datetime.now(timezone.utc),
        payload={"reads": []},
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
    )
    session.add(batch)
    session.flush()

    landing_block = LandingLpEmReadBlock(
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
        source_system="HES_OVERSEAS",
        source_table_name="LP_EM",
        source_block_key="LP_EM|32418|2024080603|0|20240806030100",
        meter_source_id="32418",
        device_source_id="795",
        mdev_id="32418",
        channel_code="0",
        source_business_hour="2024080603",
        source_write_text="20240806030100",
        source_write_ts=datetime(2024, 8, 5, 18, 1, tzinfo=timezone.utc),
        slot_values={"00": 14.2},
        slot_count=1,
        parsed_ok=True,
        source_payload={"VALUE_00": 14.2},
    )
    session.add(landing_block)
    session.flush()

    raw_row = HesReadRaw(
        ingest_batch_id=batch.id,
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
        landing_lp_em_read_block_id=landing_block.id,
        source_system="HES_OVERSEAS",
        source_table_name="LP_EM",
        source_block_key=landing_block.source_block_key,
        source_record_key="LP_EM|32418|2024080603|0|00|20240806030100",
        meter_identifier="32418",
        device_identifier="795",
        channel_identifier="0",
        source_slot_code="00",
        source_slot_index=0,
        measured_at=datetime(2024, 8, 5, 18, 0, tzinfo=timezone.utc),
        interval_size_minutes=60,
        reading_value=14.2,
        source_business_ts=datetime(2024, 8, 5, 18, 0, tzinfo=timezone.utc),
        source_write_ts=datetime(2024, 8, 5, 18, 1, tzinfo=timezone.utc),
        received_at=datetime.now(timezone.utc),
        canonical_status="pending",
        is_duplicate=False,
        payload={"VALUE_00": 14.2},
    )
    session.add(raw_row)
    session.commit()

    assert landing_block.adapter_instance.instance_code == "oracle_lp_em_primary"
    assert landing_block.adapter_run.trigger_type == "manual"
    assert landing_block.hes_read_rows[0].source_record_key.endswith("|00|20240806030100")
    assert raw_row.landing_lp_em_read_block is not None
    assert raw_row.interval_size_minutes == 60


def test_landing_block_key_must_be_unique_per_source_system(session):
    instance, run = _create_adapter_runtime(session)
    first = LandingLpEmReadBlock(
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
        source_system="HES_OVERSEAS",
        source_table_name="LP_EM",
        source_block_key="LP_EM|32418|2024080603|0|20240806030100",
        meter_source_id="32418",
        channel_code="0",
        source_business_hour="2024080603",
        slot_values={"00": 14.2},
        slot_count=1,
        parsed_ok=True,
        source_payload={},
    )
    second = LandingLpEmReadBlock(
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
        source_system="HES_OVERSEAS",
        source_table_name="LP_EM",
        source_block_key="LP_EM|32418|2024080603|0|20240806030100",
        meter_source_id="32418",
        channel_code="0",
        source_business_hour="2024080603",
        slot_values={"00": 15.0},
        slot_count=1,
        parsed_ok=True,
        source_payload={},
    )
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()


def test_raw_interval_window_state_scope_is_unique(session):
    instance, run = _create_adapter_runtime(session)
    batch = IngestBatch(
        source_system="HES_OVERSEAS",
        batch_id="batch-001",
        record_type="hes_read_raw",
        received_at=datetime.now(timezone.utc),
        payload={"reads": []},
        adapter_instance_id=instance.id,
        adapter_run_id=run.id,
    )
    session.add(batch)
    session.commit()

    first = RawIntervalWindowState(
        source_system="HES_OVERSEAS",
        meter_identifier="32418",
        channel_identifier="0",
        window_start_at=datetime(2024, 8, 5, 18, 0, tzinfo=timezone.utc),
        window_size_minutes=60,
        interval_size_minutes=15,
        expected_slot_count=4,
        received_slot_count=1,
        received_slot_bitmap="1000",
        completion_status="partial",
        late_update_count=0,
        last_adapter_run_id=run.id,
        last_ingest_batch_id=batch.id,
        details={"slots": ["00"]},
    )
    second = RawIntervalWindowState(
        source_system="HES_OVERSEAS",
        meter_identifier="32418",
        channel_identifier="0",
        window_start_at=datetime(2024, 8, 5, 18, 0, tzinfo=timezone.utc),
        window_size_minutes=60,
        interval_size_minutes=15,
        expected_slot_count=4,
        received_slot_count=4,
        received_slot_bitmap="1111",
        completion_status="complete",
        late_update_count=0,
        last_adapter_run_id=run.id,
        last_ingest_batch_id=batch.id,
        details={"slots": ["00", "15", "30", "45"]},
    )
    session.add_all([first, second])

    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
