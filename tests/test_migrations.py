from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect
from sqlalchemy import text

from app.migrations import build_alembic_config
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from postgresql_support import (  # noqa: E402
    build_schema_name,
    build_schema_url,
    create_schema,
    drop_schema,
    resolve_test_database_url,
)


def test_build_alembic_config_sets_runtime_values():
    url = "postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_test"
    config = build_alembic_config(url)

    assert config.get_main_option("sqlalchemy.url") == url
    assert config.get_main_option("script_location").endswith("/migrations")


def test_alembic_upgrade_creates_expected_tables():
    test_database_url = resolve_test_database_url()
    schema_name = build_schema_name(prefix="migration")
    schema_url = build_schema_url(test_database_url, schema_name)
    create_schema(test_database_url, schema_name)

    try:
        config = build_alembic_config(schema_url)
        command.upgrade(config, "head")

        engine = create_engine(schema_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names(schema=schema_name))

        assert "ingest_batch" in tables
        assert "hes_read_raw" in tables
        assert "hes_event_raw" in tables
        assert "canonical_measurement" in tables
        assert "initial_measurement" in tables
        assert "final_measurement" in tables
        assert "ingest_error_log" in tables
        assert "reprocess_request" in tables
        assert "pipeline_run" in tables
        assert "processing_watermark" in tables
        assert "vee_execution_log" in tables
        assert "vee_exception" in tables
        assert "usage_transaction" in tables
        assert "adapter_definition" in tables
        assert "hes_system" in tables
        assert "hes_meter_reference" in tables
        assert "adapter_instance" in tables
        assert "adapter_run" in tables
        assert "adapter_watermark" in tables
        assert "landing_lp_em_read_block" in tables
        assert "raw_interval_window_state" in tables
        assert "operational_event" in tables

        ingest_batch_columns = {
            column["name"] for column in inspector.get_columns("ingest_batch", schema=schema_name)
        }
        adapter_instance_columns = {
            column["name"] for column in inspector.get_columns("adapter_instance", schema=schema_name)
        }
        hes_meter_reference_columns = {
            column["name"]
            for column in inspector.get_columns("hes_meter_reference", schema=schema_name)
        }
        hes_read_raw_columns = {
            column["name"] for column in inspector.get_columns("hes_read_raw", schema=schema_name)
        }
        hes_read_raw_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("hes_read_raw", schema=schema_name)
        }
        canonical_columns = {
            column["name"]
            for column in inspector.get_columns("canonical_measurement", schema=schema_name)
        }
        canonical_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("canonical_measurement", schema=schema_name)
        }
        final_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("final_measurement", schema=schema_name)
        }
        initial_measurement_columns = {
            column["name"]
            for column in inspector.get_columns("initial_measurement", schema=schema_name)
        }
        initial_measurement_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("initial_measurement", schema=schema_name)
        }
        vee_execution_log_columns = {
            column["name"]
            for column in inspector.get_columns("vee_execution_log", schema=schema_name)
        }
        vee_exception_columns = {
            column["name"] for column in inspector.get_columns("vee_exception", schema=schema_name)
        }
        usage_transaction_columns = {
            column["name"]
            for column in inspector.get_columns("usage_transaction", schema=schema_name)
        }
        usage_transaction_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("usage_transaction", schema=schema_name)
        }
        ingest_error_log_columns = {
            column["name"] for column in inspector.get_columns("ingest_error_log", schema=schema_name)
        }
        reprocess_request_columns = {
            column["name"] for column in inspector.get_columns("reprocess_request", schema=schema_name)
        }
        hes_event_raw_columns = {
            column["name"] for column in inspector.get_columns("hes_event_raw", schema=schema_name)
        }
        landing_columns = {
            column["name"]
            for column in inspector.get_columns("landing_lp_em_read_block", schema=schema_name)
        }
        operational_event_columns = {
            column["name"] for column in inspector.get_columns("operational_event", schema=schema_name)
        }

        assert "hes_system_id" in ingest_batch_columns
        assert "hes_system_id" in adapter_instance_columns
        assert "hes_system_id" in hes_meter_reference_columns
        assert "source_meter_id" in hes_meter_reference_columns
        assert "source_meter_key" in hes_meter_reference_columns
        assert "lp_interval_minutes" in hes_meter_reference_columns
        assert "source_payload" in hes_meter_reference_columns
        assert "last_synced_at" in hes_meter_reference_columns
        assert "adapter_instance_id" in ingest_batch_columns
        assert "adapter_run_id" in ingest_batch_columns
        assert "hes_system_id" in hes_read_raw_columns
        assert "adapter_instance_id" in hes_read_raw_columns
        assert "adapter_run_id" in hes_read_raw_columns
        assert "landing_lp_em_read_block_id" in hes_read_raw_columns
        assert "interval_size_minutes" in hes_read_raw_columns
        assert "source_write_ts" in hes_read_raw_columns
        assert "duplicate_of_measured_at" in hes_read_raw_columns
        assert "hes_read_raw_measured_at" in canonical_columns
        assert "canonical_measurement_id" in initial_measurement_columns
        assert "initial_status" in initial_measurement_columns
        assert "ready_for_vee_at" in initial_measurement_columns
        assert "initial_measurement_id" in vee_execution_log_columns
        assert "rule_set_code" in vee_execution_log_columns
        assert "execution_status" in vee_execution_log_columns
        assert "initial_measurement_id" in vee_exception_columns
        assert "vee_execution_log_id" in vee_exception_columns
        assert "blocking_finalization" in vee_exception_columns
        assert "pipeline_run_id" in usage_transaction_columns
        assert "usage_type" in usage_transaction_columns
        assert "period_start_at" in usage_transaction_columns
        assert "period_end_at" in usage_transaction_columns
        assert "window_timezone_name" in usage_transaction_columns
        assert "interval_size_minutes" in usage_transaction_columns
        assert "usage_value" in usage_transaction_columns
        assert "source_final_count" in usage_transaction_columns
        assert "missing_interval_count" in usage_transaction_columns
        assert "quality_summary" in usage_transaction_columns
        assert "calculation_status" in usage_transaction_columns
        assert "calculated_at" in usage_transaction_columns
        assert "initial_measurement_id" in final_column_defs
        assert "revision_number" in final_column_defs
        assert "revision_reason_code" in final_column_defs
        assert "is_current" in final_column_defs
        assert "supersedes_final_measurement_id" in final_column_defs
        assert "hes_read_raw_measured_at" in ingest_error_log_columns
        assert "hes_read_raw_measured_at" in reprocess_request_columns
        assert "hes_system_id" in hes_event_raw_columns
        assert "hes_system_id" in landing_columns
        assert "is_alert" in operational_event_columns
        assert "alert_status" in operational_event_columns
        assert "opened_at" in operational_event_columns
        assert "acknowledged_at" in operational_event_columns
        assert "closed_at" in operational_event_columns
        assert "hes_system_id" in operational_event_columns
        assert hes_read_raw_column_defs["reading_value"]["type"].precision == 19
        assert hes_read_raw_column_defs["reading_value"]["type"].scale == 4
        assert canonical_column_defs["value"]["type"].precision == 19
        assert canonical_column_defs["value"]["type"].scale == 4
        assert initial_measurement_column_defs["value"]["type"].precision == 19
        assert initial_measurement_column_defs["value"]["type"].scale == 4
        assert final_column_defs["value"]["type"].precision == 19
        assert final_column_defs["value"]["type"].scale == 4
        assert final_column_defs["revision_number"]["nullable"] is False
        assert final_column_defs["is_current"]["nullable"] is False
        assert usage_transaction_column_defs["usage_value"]["type"].precision == 19
        assert usage_transaction_column_defs["usage_value"]["type"].scale == 4

        engine = create_engine(schema_url)
        with engine.connect() as connection:
            index_rows = connection.execute(
                text(
                    """
                    select indexname, indexdef
                    from pg_indexes
                    where schemaname = :schema_name
                      and tablename in (
                        'hes_read_raw',
                        'final_measurement',
                        'adapter_run',
                        'operational_event',
                        'initial_measurement',
                        'vee_execution_log',
                        'vee_exception',
                        'usage_transaction'
                      )
                    order by tablename, indexname
                    """
                ),
                {"schema_name": schema_name},
            ).fetchall()

        index_defs = {row.indexname: row.indexdef for row in index_rows}

        assert "uq_hes_read_raw_id_measured_at" in index_defs
        assert "UNIQUE INDEX" in index_defs["uq_hes_read_raw_id_measured_at"]
        assert "ix_hes_read_raw_source_record_key_scope" in index_defs
        assert "UNIQUE INDEX" not in index_defs["ix_hes_read_raw_source_record_key_scope"]
        assert "ix_hes_read_raw_source_meter_channel_measured_at" in index_defs
        assert "ix_initial_measurement_measured_at" in index_defs
        assert "ix_initial_measurement_initial_status" in index_defs
        assert "ix_initial_measurement_service_point_id_measured_at" in index_defs
        assert "ix_vee_execution_log_initial_measurement_id" in index_defs
        assert "ix_vee_execution_log_execution_status" in index_defs
        assert "ix_vee_execution_log_started_at" in index_defs
        assert "ix_vee_exception_initial_measurement_id" in index_defs
        assert "ix_vee_exception_exception_status" in index_defs
        assert "ix_vee_exception_exception_code" in index_defs
        assert "ix_vee_exception_detected_at" in index_defs
        assert "ix_vee_exception_blocking_finalization" in index_defs
        assert "uq_usage_transaction_scope" in index_defs
        assert "UNIQUE INDEX" in index_defs["uq_usage_transaction_scope"]
        assert "ix_usage_transaction_usage_type" in index_defs
        assert "ix_usage_transaction_period_start_at" in index_defs
        assert "ix_usage_transaction_calculation_status" in index_defs
        assert "ix_usage_transaction_service_point_period_start_at" in index_defs
        assert "ix_usage_transaction_measuring_component_period_start_at" in index_defs
        assert "ix_final_measurement_is_current" in index_defs
        assert "ix_final_measurement_supersedes_final_measurement_id" in index_defs
        assert "ix_final_measurement_initial_measurement_id" in index_defs
        assert "ix_final_measurement_canonical_measurement_id" in index_defs
        assert "uq_final_measurement_current_initial_measurement_id" in index_defs
        assert "UNIQUE INDEX" in index_defs["uq_final_measurement_current_initial_measurement_id"]
        assert "uq_adapter_run_single_running_per_instance" in index_defs
        assert "run_status" in index_defs[
            "uq_adapter_run_single_running_per_instance"
        ]
        assert "running" in index_defs[
            "uq_adapter_run_single_running_per_instance"
        ]
        assert "ix_operational_event_hes_system_id" in index_defs

        hes_system_indexes = inspector.get_indexes("hes_system", schema=schema_name)
        hes_system_index_names = {row["name"] for row in hes_system_indexes}
        assert "ix_hes_system_source_family" in hes_system_index_names
        assert "ix_hes_system_status" in hes_system_index_names
        hes_meter_reference_indexes = inspector.get_indexes("hes_meter_reference", schema=schema_name)
        hes_meter_reference_index_names = {row["name"] for row in hes_meter_reference_indexes}
        assert "ix_hes_meter_reference_hes_system_id" in hes_meter_reference_index_names
        assert "ix_hes_meter_reference_source_table_name" in hes_meter_reference_index_names
        assert "ix_hes_meter_reference_meter_status_code" in hes_meter_reference_index_names

        with engine.connect() as connection:
            partition_rows = connection.execute(
                text(
                    """
                    select child.relname
                    from pg_inherits
                    join pg_class parent on parent.oid = pg_inherits.inhparent
                    join pg_class child on child.oid = pg_inherits.inhrelid
                    join pg_namespace namespace on namespace.oid = child.relnamespace
                    where namespace.nspname = :schema_name
                      and parent.relname = 'hes_read_raw'
                    order by child.relname
                    """
                ),
                {"schema_name": schema_name},
            ).scalars().all()

        assert "hes_read_raw_default" in partition_rows
        month_partitions = [name for name in partition_rows if name.startswith("hes_read_raw_20")]
        assert len(month_partitions) >= 2
    finally:
        drop_schema(test_database_url, schema_name)
