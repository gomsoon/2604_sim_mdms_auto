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
        assert "vee_replay_request" in tables
        assert "vee_replay_request_item" in tables
        assert "usage_transaction" in tables
        assert "bill_determinant" in tables
        assert "bill_charge" in tables
        assert "service_point_billing_context" in tables
        assert "service_point_tariff_assignment" in tables
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
        pipeline_run_columns = {
            column["name"] for column in inspector.get_columns("pipeline_run", schema=schema_name)
        }
        vee_execution_log_columns = {
            column["name"]
            for column in inspector.get_columns("vee_execution_log", schema=schema_name)
        }
        vee_exception_columns = {
            column["name"] for column in inspector.get_columns("vee_exception", schema=schema_name)
        }
        vee_replay_request_columns = {
            column["name"]
            for column in inspector.get_columns("vee_replay_request", schema=schema_name)
        }
        vee_replay_request_item_columns = {
            column["name"]
            for column in inspector.get_columns("vee_replay_request_item", schema=schema_name)
        }
        usage_transaction_columns = {
            column["name"]
            for column in inspector.get_columns("usage_transaction", schema=schema_name)
        }
        usage_transaction_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("usage_transaction", schema=schema_name)
        }
        bill_determinant_columns = {
            column["name"] for column in inspector.get_columns("bill_determinant", schema=schema_name)
        }
        bill_determinant_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("bill_determinant", schema=schema_name)
        }
        bill_charge_columns = {
            column["name"] for column in inspector.get_columns("bill_charge", schema=schema_name)
        }
        bill_charge_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("bill_charge", schema=schema_name)
        }
        billing_context_columns = {
            column["name"]
            for column in inspector.get_columns("service_point_billing_context", schema=schema_name)
        }
        billing_context_column_defs = {
            column["name"]: column
            for column in inspector.get_columns("service_point_billing_context", schema=schema_name)
        }
        tariff_assignment_columns = {
            column["name"]
            for column in inspector.get_columns("service_point_tariff_assignment", schema=schema_name)
        }
        tariff_assignment_column_defs = {
            column["name"]: column
            for column in inspector.get_columns(
                "service_point_tariff_assignment", schema=schema_name
            )
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
        assert "vee_replay_request_id" in pipeline_run_columns
        assert "initial_measurement_id" in vee_execution_log_columns
        assert "rule_set_code" in vee_execution_log_columns
        assert "execution_status" in vee_execution_log_columns
        assert "initial_measurement_id" in vee_exception_columns
        assert "vee_execution_log_id" in vee_exception_columns
        assert "blocking_finalization" in vee_exception_columns
        assert "request_scope" in vee_replay_request_columns
        assert "status" in vee_replay_request_columns
        assert "requested_by" in vee_replay_request_columns
        assert "hes_system_id" in vee_replay_request_columns
        assert "ingest_batch_id" in vee_replay_request_columns
        assert "target_initial_count" in vee_replay_request_columns
        assert "processed_count" in vee_replay_request_columns
        assert "usage_recalculated_count" in vee_replay_request_columns
        assert "vee_replay_request_id" in vee_replay_request_item_columns
        assert "initial_measurement_id" in vee_replay_request_item_columns
        assert "representative_vee_exception_id" in vee_replay_request_item_columns
        assert "vee_execution_log_id" in vee_replay_request_item_columns
        assert "previous_final_measurement_id" in vee_replay_request_item_columns
        assert "current_final_measurement_id" in vee_replay_request_item_columns
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
        assert "pipeline_run_id" in bill_determinant_columns
        assert "service_point_id" in bill_determinant_columns
        assert "measuring_component_id" in bill_determinant_columns
        assert "device_id" in bill_determinant_columns
        assert "determinant_type" in bill_determinant_columns
        assert "billing_period_start_at" in bill_determinant_columns
        assert "billing_period_end_at" in bill_determinant_columns
        assert "window_timezone_name" in bill_determinant_columns
        assert "tariff_plan_code" in bill_determinant_columns
        assert "tou_bucket_code" in bill_determinant_columns
        assert "demand_window_code" in bill_determinant_columns
        assert "unit_of_measure" in bill_determinant_columns
        assert "determinant_value" in bill_determinant_columns
        assert "source_usage_count" in bill_determinant_columns
        assert "quality_summary" in bill_determinant_columns
        assert "calculation_status" in bill_determinant_columns
        assert "revision_number" in bill_determinant_columns
        assert "revision_reason_code" in bill_determinant_columns
        assert "is_current" in bill_determinant_columns
        assert "supersedes_bill_determinant_id" in bill_determinant_columns
        assert "calculated_at" in bill_determinant_columns
        assert "pipeline_run_id" in bill_charge_columns
        assert "service_point_id" in bill_charge_columns
        assert "measuring_component_id" in bill_charge_columns
        assert "device_id" in bill_charge_columns
        assert "bill_determinant_id" in bill_charge_columns
        assert "charge_type" in bill_charge_columns
        assert "billing_period_start_at" in bill_charge_columns
        assert "billing_period_end_at" in bill_charge_columns
        assert "currency_code" in bill_charge_columns
        assert "tariff_plan_code" in bill_charge_columns
        assert "tariff_version_code" in bill_charge_columns
        assert "quantity_value" in bill_charge_columns
        assert "unit_rate_value" in bill_charge_columns
        assert "charge_amount" in bill_charge_columns
        assert "calculation_status" in bill_charge_columns
        assert "quality_summary" in bill_charge_columns
        assert "revision_number" in bill_charge_columns
        assert "revision_reason_code" in bill_charge_columns
        assert "is_current" in bill_charge_columns
        assert "supersedes_bill_charge_id" in bill_charge_columns
        assert "calculated_at" in bill_charge_columns
        assert "service_point_id" in billing_context_columns
        assert "timezone_name" in billing_context_columns
        assert "billing_cycle_mode" in billing_context_columns
        assert "billing_cycle_anchor_day" in billing_context_columns
        assert "currency_code" in billing_context_columns
        assert "effective_from" in billing_context_columns
        assert "effective_to" in billing_context_columns
        assert "is_current" in billing_context_columns
        assert "source_system" in billing_context_columns
        assert "source_reference" in billing_context_columns
        assert "details" in billing_context_columns
        assert billing_context_column_defs["timezone_name"]["nullable"] is False
        assert billing_context_column_defs["billing_cycle_mode"]["nullable"] is False
        assert billing_context_column_defs["effective_from"]["nullable"] is False
        assert billing_context_column_defs["is_current"]["nullable"] is False
        assert "service_point_id" in tariff_assignment_columns
        assert "tariff_plan_code" in tariff_assignment_columns
        assert "tariff_version_code" in tariff_assignment_columns
        assert "effective_from" in tariff_assignment_columns
        assert "effective_to" in tariff_assignment_columns
        assert "is_current" in tariff_assignment_columns
        assert "source_system" in tariff_assignment_columns
        assert "source_reference" in tariff_assignment_columns
        assert "details" in tariff_assignment_columns
        assert tariff_assignment_column_defs["tariff_plan_code"]["nullable"] is False
        assert tariff_assignment_column_defs["effective_from"]["nullable"] is False
        assert tariff_assignment_column_defs["is_current"]["nullable"] is False
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
        assert bill_determinant_column_defs["determinant_value"]["type"].precision == 19
        assert bill_determinant_column_defs["determinant_value"]["type"].scale == 4
        assert bill_determinant_column_defs["revision_number"]["nullable"] is False
        assert bill_determinant_column_defs["is_current"]["nullable"] is False
        assert bill_charge_column_defs["quantity_value"]["type"].precision == 19
        assert bill_charge_column_defs["quantity_value"]["type"].scale == 4
        assert bill_charge_column_defs["unit_rate_value"]["type"].precision == 19
        assert bill_charge_column_defs["unit_rate_value"]["type"].scale == 8
        assert bill_charge_column_defs["charge_amount"]["type"].precision == 19
        assert bill_charge_column_defs["charge_amount"]["type"].scale == 4
        assert bill_charge_column_defs["charge_type"]["nullable"] is False
        assert bill_charge_column_defs["quantity_value"]["nullable"] is False
        assert bill_charge_column_defs["revision_number"]["nullable"] is False
        assert bill_charge_column_defs["is_current"]["nullable"] is False

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
                        'pipeline_run',
                        'vee_execution_log',
                        'vee_exception',
                        'vee_replay_request',
                        'vee_replay_request_item',
                        'usage_transaction',
                        'bill_determinant',
                        'bill_charge',
                        'service_point_billing_context',
                        'service_point_tariff_assignment'
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
        assert "ix_vee_replay_request_status" in index_defs
        assert "ix_vee_replay_request_request_scope" in index_defs
        assert "ix_vee_replay_request_hes_system_id" in index_defs
        assert "ix_vee_replay_request_ingest_batch_id" in index_defs
        assert "ix_vee_replay_request_requested_by" in index_defs
        assert "ix_vee_replay_request_created_at" in index_defs
        assert "uq_vee_replay_request_item_scope" in index_defs
        assert "UNIQUE INDEX" in index_defs["uq_vee_replay_request_item_scope"]
        assert "ix_vee_replay_request_item_vee_replay_request_id" in index_defs
        assert "ix_vee_replay_request_item_status" in index_defs
        assert "ix_vee_replay_request_item_initial_measurement_id" in index_defs
        assert "ix_vee_replay_request_item_representative_vee_exception_id" in index_defs
        assert "ix_pipeline_run_vee_replay_request_id" in index_defs
        assert "uq_usage_transaction_scope" in index_defs
        assert "UNIQUE INDEX" in index_defs["uq_usage_transaction_scope"]
        assert "ix_usage_transaction_usage_type" in index_defs
        assert "ix_usage_transaction_period_start_at" in index_defs
        assert "ix_usage_transaction_calculation_status" in index_defs
        assert "ix_usage_transaction_service_point_period_start_at" in index_defs
        assert "ix_usage_transaction_measuring_component_period_start_at" in index_defs
        assert "ix_bill_determinant_determinant_type" in index_defs
        assert "ix_bill_determinant_billing_period_start_at" in index_defs
        assert "ix_bill_determinant_calculation_status" in index_defs
        assert "ix_bill_determinant_service_point_billing_period_start_at" in index_defs
        assert "ix_bill_determinant_measuring_component_billing_period_start_at" in index_defs
        assert "ix_bill_determinant_is_current" in index_defs
        assert "ix_bill_determinant_supersedes_bill_determinant_id" in index_defs
        assert "ix_bill_charge_charge_type" in index_defs
        assert "ix_bill_charge_billing_period_start_at" in index_defs
        assert "ix_bill_charge_calculation_status" in index_defs
        assert "ix_bill_charge_bill_determinant_id" in index_defs
        assert "ix_bill_charge_service_point_billing_period_start_at" in index_defs
        assert "ix_bill_charge_measuring_component_billing_period_start_at" in index_defs
        assert "ix_bill_charge_is_current" in index_defs
        assert "ix_bill_charge_supersedes_bill_charge_id" in index_defs
        assert "ix_service_point_billing_context_billing_cycle_mode" in index_defs
        assert "ix_service_point_billing_context_effective_from" in index_defs
        assert "ix_service_point_billing_context_effective_to" in index_defs
        assert "ix_service_point_billing_context_is_current" in index_defs
        assert "ix_service_point_billing_context_service_point_effective_from" in index_defs
        assert "uq_service_point_billing_context_current_service_point" in index_defs
        assert "UNIQUE INDEX" in index_defs[
            "uq_service_point_billing_context_current_service_point"
        ]
        assert "ix_service_point_tariff_assignment_effective_from" in index_defs
        assert "ix_service_point_tariff_assignment_effective_to" in index_defs
        assert "ix_service_point_tariff_assignment_is_current" in index_defs
        assert "ix_service_point_tariff_assignment_service_point_effective_from" in index_defs
        assert "ix_spta_service_point_tariff_plan_code" in index_defs
        assert "uq_service_point_tariff_assignment_current_service_point" in index_defs
        assert "UNIQUE INDEX" in index_defs[
            "uq_service_point_tariff_assignment_current_service_point"
        ]
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
        billing_context_checks = inspector.get_check_constraints(
            "service_point_billing_context", schema=schema_name
        )
        billing_context_check_names = {row["name"] for row in billing_context_checks}
        assert "ck_service_point_billing_context_effective_window" in billing_context_check_names
        assert "ck_service_point_billing_context_cycle_mode" in billing_context_check_names
        tariff_assignment_checks = inspector.get_check_constraints(
            "service_point_tariff_assignment", schema=schema_name
        )
        tariff_assignment_check_names = {row["name"] for row in tariff_assignment_checks}
        assert (
            "ck_service_point_tariff_assignment_effective_window"
            in tariff_assignment_check_names
        )
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
