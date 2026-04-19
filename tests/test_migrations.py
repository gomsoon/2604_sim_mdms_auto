from __future__ import annotations

from pathlib import Path

from alembic import command
from sqlalchemy import create_engine, inspect

from app.migrations import build_alembic_config


def test_build_alembic_config_sets_runtime_values():
    config = build_alembic_config("sqlite:///tmp/mdms.db")

    assert config.get_main_option("sqlalchemy.url") == "sqlite:///tmp/mdms.db"
    assert config.get_main_option("script_location").endswith("/migrations")


def test_alembic_upgrade_creates_expected_tables(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    config = build_alembic_config(f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

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

    ingest_batch_columns = {column["name"] for column in inspector.get_columns("ingest_batch")}

    assert "adapter_instance_id" in ingest_batch_columns
    assert "adapter_run_id" in ingest_batch_columns
