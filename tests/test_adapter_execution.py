from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.models import (
    AdapterDefinition,
    AdapterInstance,
    AdapterRun,
    AdapterWatermark,
    CanonicalMeasurement,
    Device,
    HesReadRaw,
    IngestBatch,
    InstallationHistory,
    LandingLpEmReadBlock,
    MeasuringComponent,
    OperationalEvent,
    RawIntervalWindowState,
    ServicePoint,
)
from app.services.adapter_execution import execute_adapter_run, process_waiting_adapter_runs
from app.services.adapters import queue_adapter_run_once
from app.services.seeds import seed_adapter_runtime, seed_master_data


def _seed_nuri_aimir_hes_runtime_prerequisites(session) -> AdapterInstance:
    service_point = ServicePoint(
        source_system="HES_OVERSEAS",
        external_id="SP-OVERSEAS-32418",
        service_type="electric",
        name="Overseas Site 32418",
        status="active",
    )
    session.add(service_point)
    session.flush()

    device = Device(
        source_system="HES_OVERSEAS",
        external_meter_id="32418",
        serial_number="32418",
        status="active",
        service_point_id=service_point.id,
    )
    session.add(device)
    session.flush()

    component = MeasuringComponent(
        source_system="HES_OVERSEAS",
        external_channel_id="0",
        unit_of_measure="kWh",
        multiplier=1.0,
        status="active",
        device_id=device.id,
        service_point_id=service_point.id,
    )
    installation = InstallationHistory(
        device_id=device.id,
        service_point_id=service_point.id,
        installed_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        status="installed",
    )
    session.add_all([component, installation])
    session.flush()

    definition = AdapterDefinition(
        adapter_code="nuri_aimir_hes_lp_em_poll_v1",
        display_name="NURI AIMIR HES LP_EM Poll",
        delivery_mode="poll",
        source_family="nuri_aimir_hes",
        record_type="hes_read_raw",
        adapter_profile_key="common_raw_v1",
        implementation_key="nuri_aimir_hes_lp_em_poll_v1",
        status="active",
    )
    session.add(definition)
    session.flush()

    instance = AdapterInstance(
        adapter_definition_id=definition.id,
        instance_code="nuri_aimir_hes_lp_em_primary",
        display_name="NURI AIMIR HES LP_EM Primary",
        source_system="HES_OVERSEAS",
        admin_state="enabled",
        poll_interval_minutes=5,
        batch_size=10,
        landing_enabled=True,
        connection_config_masked={
            "source_timezone": "Asia/Seoul",
            "default_interval_minutes": 15,
            "unit_of_measure": "kWh",
            "sample_blocks": [
                {
                    "METER_ID": "32418",
                    "DEVICE_ID": "795",
                    "MDEV_ID": "32418",
                    "MDEV_TYPE": "EM",
                    "YYYYMMDDHH": "2024080603",
                    "HH": "03",
                    "WRITEDATE": "20240806030100",
                    "CHANNEL": "0",
                    "VALUE_CNT": 2,
                    "VALUE_00": 1.25,
                    "VALUE_15": 1.5,
                    "LOCATION_ID": "100",
                    "SUPPLIER_ID": "200",
                    "ENDDEVICE_ID": "300",
                }
            ],
        },
    )
    session.add(instance)
    session.flush()
    return instance


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
    event_codes = set(session.scalars(select(OperationalEvent.event_code)).all())

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
    assert {"adapter_run_started", "adapter_run_completed", "ingest_batch_accepted", "raw_ingest_completed", "canonical_completed"} <= event_codes


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
    latest_event = session.scalar(
        select(OperationalEvent).order_by(OperationalEvent.id.desc()).limit(1)
    )

    assert result.run_status == "failed"
    assert result.error_code == "unsupported_runtime_implementation"
    assert refreshed_run is not None
    assert refreshed_run.run_status == "failed"
    assert refreshed_run.error_code == "unsupported_runtime_implementation"
    assert refreshed_instance is not None
    assert refreshed_instance.last_failure_at is not None
    assert refreshed_instance.last_error_message is not None
    assert session.scalar(select(func.count()).select_from(IngestBatch)) == 0
    assert latest_event is not None
    assert latest_event.event_code == "adapter_run_failed"
    assert latest_event.is_alert is True
    assert latest_event.alert_status == "open"


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


def test_enqueue_scheduled_adapter_runs_cli_creates_waiting_schedule_run(app, session):
    seed_master_data(session)
    seed_adapter_runtime(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    assert instance is not None

    instance.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()

    runner = app.test_cli_runner()
    result = runner.invoke(args=["enqueue-scheduled-adapter-runs", "--limit", "1"])

    refreshed_run = session.scalar(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance.id, AdapterRun.trigger_type == "schedule")
        .order_by(AdapterRun.id.desc())
        .limit(1)
    )

    assert result.exit_code == 0
    assert "eligible=1" in result.output
    assert "enqueued=1" in result.output
    assert refreshed_run is not None
    assert refreshed_run.run_status == "waiting"


def test_process_waiting_adapter_runs_returns_empty_summary_when_queue_is_empty(session):
    summary = process_waiting_adapter_runs(session, limit=1)

    assert summary.processed == 0
    assert summary.completed == 0
    assert summary.failed == 0
    assert summary.results == []


def test_execute_nuri_aimir_hes_lp_em_run_creates_landing_rows_raw_reads_and_partial_window_state(
    session,
):
    instance = _seed_nuri_aimir_hes_runtime_prerequisites(session)
    session.commit()

    queued_run = queue_adapter_run_once(session, instance)

    result = execute_adapter_run(session, queued_run.id)
    session.commit()

    landing_count = session.scalar(select(func.count()).select_from(LandingLpEmReadBlock))
    raw_count = session.scalar(select(func.count()).select_from(HesReadRaw))
    state = session.scalar(select(RawIntervalWindowState).limit(1))
    watermark = session.scalar(
        select(AdapterWatermark)
        .where(
            AdapterWatermark.adapter_instance_id == instance.id,
            AdapterWatermark.record_type == "hes_read_raw",
        )
        .limit(1)
    )

    assert result.run_status == "completed"
    assert result.source_rows_fetched == 1
    assert result.ingest_batches_created == 1
    assert result.ingest_records_created == 2
    assert landing_count == 1
    assert raw_count == 2
    assert state is not None
    assert state.received_slot_count == 2
    assert state.expected_slot_count == 4
    assert state.received_slot_bitmap == "00,15"
    assert state.completion_status == "partial"
    assert state.last_ingest_batch_id is not None
    assert watermark is not None
    assert watermark.cursor_value == "20240806030100|2024080603|32418|0"


def test_execute_nuri_aimir_hes_lp_em_run_marks_complete_window_as_late_update_on_newer_source_write(
    session,
):
    instance = _seed_nuri_aimir_hes_runtime_prerequisites(session)
    session.commit()

    first_run = queue_adapter_run_once(session, instance)
    first_result = execute_adapter_run(session, first_run.id)
    assert first_result.run_status == "completed"

    state = session.scalar(select(RawIntervalWindowState).limit(1))
    assert state is not None
    state.received_slot_count = 4
    state.expected_slot_count = 4
    state.received_slot_bitmap = "00,15,30,45"
    state.completion_status = "complete"
    state.last_source_write_ts = datetime(2024, 8, 5, 18, 1, tzinfo=timezone.utc)

    instance.connection_config_masked = {
        **dict(instance.connection_config_masked or {}),
        "sample_blocks": [
            {
                "METER_ID": "32418",
                "DEVICE_ID": "795",
                "MDEV_ID": "32418",
                "MDEV_TYPE": "EM",
                "YYYYMMDDHH": "2024080603",
                "HH": "03",
                "WRITEDATE": "20240806030200",
                "CHANNEL": "0",
                "VALUE_CNT": 1,
                "VALUE_00": 1.3,
                "LOCATION_ID": "100",
                "SUPPLIER_ID": "200",
                "ENDDEVICE_ID": "300",
            }
        ],
    }
    session.flush()

    second_run = queue_adapter_run_once(session, instance)
    result = execute_adapter_run(session, second_run.id)
    session.commit()

    refreshed_state = session.get(RawIntervalWindowState, state.id)

    assert result.run_status == "completed"
    assert refreshed_state is not None
    assert refreshed_state.completion_status == "late_update"
    assert refreshed_state.late_update_count == 1
    assert refreshed_state.last_source_write_ts == datetime(
        2024, 8, 5, 18, 2, tzinfo=timezone.utc
    )


def test_execute_nuri_aimir_hes_lp_em_run_supports_oracle_query_mode(
    session, monkeypatch
):
    instance = _seed_nuri_aimir_hes_runtime_prerequisites(session)
    instance.connection_config_masked = {
        "source_timezone": "Asia/Seoul",
        "default_interval_minutes": 15,
        "unit_of_measure": "kWh",
        "oracle_host": "172.16.10.111",
        "oracle_port": 1521,
        "oracle_sid": "HESDB",
        "oracle_username": "aimir",
        "allowed_channels": ["0"],
    }
    instance.secret_ref = "env://MDMS_NURI_AIMIR_HES_DB_PASSWORD"
    session.commit()

    monkeypatch.setenv("MDMS_NURI_AIMIR_HES_DB_PASSWORD", "oracle-secret")

    def fake_fetch_nuri_aimir_hes_lp_em_rows(config, *, cursor):
        assert config.host == "172.16.10.111"
        assert config.sid == "HESDB"
        assert config.username == "aimir"
        assert config.password == "oracle-secret"
        assert config.allowed_channels == ("0",)
        assert cursor is None
        return [
            {
                "METER_ID": "32418",
                "DEVICE_ID": "795",
                "MDEV_ID": "32418",
                "MDEV_TYPE": "EM",
                "YYYYMMDDHH": "2024080603",
                "HH": "03",
                "WRITEDATE": "20240806030100",
                "CHANNEL": "0",
                "VALUE_CNT": 1,
                "VALUE_00": 1.25,
                "LOCATION_ID": "100",
                "SUPPLIER_ID": "200",
                "ENDDEVICE_ID": "300",
                "LP_INTERVAL": 15,
            }
        ]

    monkeypatch.setattr(
        "app.services.adapter_execution.fetch_nuri_aimir_hes_lp_em_rows",
        fake_fetch_nuri_aimir_hes_lp_em_rows,
    )

    queued_run = queue_adapter_run_once(session, instance)
    result = execute_adapter_run(session, queued_run.id)
    session.commit()

    refreshed_run = session.get(AdapterRun, queued_run.id)
    state = session.scalar(select(RawIntervalWindowState).limit(1))

    assert result.run_status == "completed"
    assert refreshed_run is not None
    assert refreshed_run.details["source_fetch_mode"] == "oracle_query"
    assert state is not None
    assert state.completion_status == "partial"
