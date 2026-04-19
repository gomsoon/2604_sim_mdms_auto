from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import (
    AdapterDefinition,
    AdapterInstance,
    AdapterRun,
    AdapterWatermark,
    CanonicalMeasurement,
    IngestBatch,
)
from app.services.adapter_execution import execute_adapter_run, process_waiting_adapter_runs
from app.services.adapters import queue_adapter_run_once
from app.services.seeds import seed_adapter_runtime, seed_master_data


def test_execute_adapter_run_consumes_waiting_run_and_creates_ingest_lineage(session):
    seed_master_data(session)
    seed_adapter_runtime(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    assert instance is not None

    previous_success_at = instance.last_success_at
    queued_run = queue_adapter_run_once(session, instance)

    result = execute_adapter_run(session, queued_run.id)
    session.commit()

    refreshed_run = session.get(AdapterRun, queued_run.id)
    watermark = session.scalar(
        select(AdapterWatermark)
        .where(
            AdapterWatermark.adapter_instance_id == instance.id,
            AdapterWatermark.record_type == "hes_read_raw",
        )
        .limit(1)
    )
    batch = session.scalar(
        select(IngestBatch)
        .where(IngestBatch.adapter_run_id == queued_run.id)
        .order_by(IngestBatch.id.desc())
        .limit(1)
    )
    refreshed_instance = session.get(AdapterInstance, instance.id)

    assert result.run_status == "completed"
    assert result.source_rows_fetched == 2
    assert result.ingest_batches_created == 1
    assert result.ingest_records_created == 2
    assert refreshed_run is not None
    assert refreshed_run.run_status == "completed"
    assert refreshed_run.watermark_before == "2026-04-18T00:15:00+09:00"
    assert refreshed_run.watermark_after == "2026-04-18T01:00:00+09:00"
    assert watermark is not None
    assert watermark.cursor_value == "2026-04-18T01:00:00+09:00"
    assert batch is not None
    assert batch.adapter_instance_id == instance.id
    assert batch.adapter_run_id == queued_run.id
    assert refreshed_instance is not None
    assert refreshed_instance.last_success_at is not None
    assert previous_success_at is not None
    assert refreshed_instance.last_success_at != previous_success_at
    assert refreshed_instance.last_error_message is None
    assert session.scalar(select(func.count()).select_from(CanonicalMeasurement)) == 2


def test_execute_adapter_run_completes_without_new_rows_when_watermark_is_current(session):
    seed_master_data(session)
    seed_adapter_runtime(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    assert instance is not None

    watermark = session.scalar(
        select(AdapterWatermark)
        .where(
            AdapterWatermark.adapter_instance_id == instance.id,
            AdapterWatermark.record_type == "hes_read_raw",
        )
        .limit(1)
    )
    assert watermark is not None
    watermark.cursor_value = "2026-04-18T01:00:00+09:00"
    watermark.last_source_timestamp = datetime(2026, 4, 17, 16, 0, tzinfo=timezone.utc)
    session.flush()

    queued_run = queue_adapter_run_once(session, instance)

    result = execute_adapter_run(session, queued_run.id)
    session.commit()

    refreshed_run = session.get(AdapterRun, queued_run.id)
    refreshed_watermark = session.get(AdapterWatermark, watermark.id)

    assert result.run_status == "completed"
    assert result.source_rows_fetched == 0
    assert result.ingest_batches_created == 0
    assert result.ingest_records_created == 0
    assert refreshed_run is not None
    assert refreshed_run.run_status == "completed"
    assert refreshed_run.watermark_before == "2026-04-18T01:00:00+09:00"
    assert refreshed_run.watermark_after == "2026-04-18T01:00:00+09:00"
    assert refreshed_watermark is not None
    assert refreshed_watermark.cursor_value == "2026-04-18T01:00:00+09:00"
    assert session.scalar(select(func.count()).select_from(IngestBatch)) == 0


def test_execute_adapter_run_marks_failed_for_unknown_implementation(session):
    definition = AdapterDefinition(
        adapter_code="unknown_poll_v1",
        display_name="Unknown Poll",
        delivery_mode="poll",
        source_family="hes",
        record_type="hes_read_raw",
        adapter_profile_key="common_raw_v1",
        implementation_key="unknown_poll_v1",
        status="active",
    )
    session.add(definition)
    session.flush()

    instance = AdapterInstance(
        adapter_definition_id=definition.id,
        instance_code="unknown_poll_primary",
        display_name="Unknown Poll Primary",
        source_system="HES",
        admin_state="enabled",
        poll_interval_minutes=5,
        batch_size=100,
        landing_enabled=False,
        connection_config_masked={},
    )
    session.add(instance)
    session.flush()

    run = AdapterRun(
        adapter_instance_id=instance.id,
        trigger_type="manual",
        run_status="waiting",
        details={"requested_via": "test"},
    )
    session.add(run)
    session.flush()

    result = execute_adapter_run(session, run.id)
    session.commit()

    refreshed_run = session.get(AdapterRun, run.id)
    refreshed_instance = session.get(AdapterInstance, instance.id)

    assert result.run_status == "failed"
    assert result.error_code == "unsupported_runtime_implementation"
    assert refreshed_run is not None
    assert refreshed_run.run_status == "failed"
    assert refreshed_run.error_code == "unsupported_runtime_implementation"
    assert refreshed_instance is not None
    assert refreshed_instance.last_failure_at is not None
    assert refreshed_instance.last_error_message is not None
    assert session.scalar(select(func.count()).select_from(IngestBatch)) == 0


def test_process_adapter_runs_cli_processes_waiting_run(app, session):
    seed_master_data(session)
    seed_adapter_runtime(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    assert instance is not None

    queued_run = queue_adapter_run_once(session, instance)
    session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["process-adapter-runs", "--limit", "1"])

    refreshed_run = session.get(AdapterRun, queued_run.id)

    assert result.exit_code == 0
    assert "processed=1" in result.output
    assert "completed=1" in result.output
    assert refreshed_run is not None
    assert refreshed_run.run_status == "completed"


def test_process_waiting_adapter_runs_returns_empty_summary_when_queue_is_empty(session):
    summary = process_waiting_adapter_runs(session, limit=1)

    assert summary.processed == 0
    assert summary.completed == 0
    assert summary.failed == 0
    assert summary.results == []
