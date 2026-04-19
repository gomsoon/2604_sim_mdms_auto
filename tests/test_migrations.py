from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

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
        assert "final_measurement" in tables
        assert "ingest_error_log" in tables
        assert "reprocess_request" in tables
        assert "pipeline_run" in tables
        assert "processing_watermark" in tables
        assert "adapter_definition" in tables
        assert "adapter_instance" in tables
        assert "adapter_run" in tables
        assert "adapter_watermark" in tables

        ingest_batch_columns = {
            column["name"] for column in inspector.get_columns("ingest_batch", schema=schema_name)
        }

        assert "adapter_instance_id" in ingest_batch_columns
        assert "adapter_run_id" in ingest_batch_columns
    finally:
        drop_schema(test_database_url, schema_name)
