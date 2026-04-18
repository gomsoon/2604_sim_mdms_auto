"""Create initial schema for the minimal scaffold.

Revision ID: 202604180001
Revises:
Create Date: 2026-04-18 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604180001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingest_batch",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("batch_id", sa.String(length=100), nullable=False),
        sa.Column("record_type", sa.String(length=30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_ingest_batch_source_system", "ingest_batch", ["source_system"])
    op.create_index("ix_ingest_batch_batch_id", "ingest_batch", ["batch_id"])

    op.create_table(
        "service_point",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_id", sa.String(length=100), nullable=False),
        sa.Column("service_type", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("external_id", name="uq_service_point_external_id"),
    )
    op.create_index("ix_service_point_source_system", "service_point", ["source_system"])

    op.create_table(
        "device",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_meter_id", sa.String(length=100), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.UniqueConstraint("external_meter_id", name="uq_device_external_meter_id"),
    )
    op.create_index("ix_device_source_system", "device", ["source_system"])

    op.create_table(
        "measuring_component",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("external_channel_id", sa.String(length=100), nullable=False),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column("multiplier", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
    )
    op.create_index("ix_measuring_component_source_system", "measuring_component", ["source_system"])

    op.create_table(
        "installation_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
    )

    op.create_table(
        "hes_read_raw",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingest_batch_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("meter_identifier", sa.String(length=100), nullable=True),
        sa.Column("channel_identifier", sa.String(length=100), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reading_value", sa.Float(), nullable=True),
        sa.Column("quality_code", sa.String(length=40), nullable=True),
        sa.Column("status_code", sa.String(length=40), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_status", sa.String(length=30), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["hes_read_raw.id"]),
        sa.ForeignKeyConstraint(["ingest_batch_id"], ["ingest_batch.id"]),
    )
    op.create_index("ix_hes_read_raw_source_system", "hes_read_raw", ["source_system"])
    op.create_index("ix_hes_read_raw_meter_identifier", "hes_read_raw", ["meter_identifier"])
    op.create_index("ix_hes_read_raw_channel_identifier", "hes_read_raw", ["channel_identifier"])
    op.create_index("ix_hes_read_raw_measured_at", "hes_read_raw", ["measured_at"])

    op.create_table(
        "hes_event_raw",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingest_batch_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("meter_identifier", sa.String(length=100), nullable=True),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_code", sa.String(length=60), nullable=True),
        sa.Column("severity", sa.String(length=30), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["ingest_batch_id"], ["ingest_batch.id"]),
    )
    op.create_index("ix_hes_event_raw_source_system", "hes_event_raw", ["source_system"])
    op.create_index("ix_hes_event_raw_meter_identifier", "hes_event_raw", ["meter_identifier"])
    op.create_index("ix_hes_event_raw_event_time", "hes_event_raw", ["event_time"])

    op.create_table(
        "canonical_measurement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hes_read_raw_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("quality_code", sa.String(length=40), nullable=True),
        sa.Column("status_code", sa.String(length=40), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["hes_read_raw_id"], ["hes_read_raw.id"]),
        sa.ForeignKeyConstraint(["measuring_component_id"], ["measuring_component.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.UniqueConstraint("hes_read_raw_id", name="uq_canonical_measurement_hes_read_raw_id"),
    )
    op.create_index("ix_canonical_measurement_measured_at", "canonical_measurement", ["measured_at"])

    op.create_table(
        "ingest_error_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exception_type", sa.String(length=40), nullable=False),
        sa.Column("exception_code", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("hes_read_raw_id", sa.Integer(), nullable=True),
        sa.Column("hes_event_raw_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["hes_read_raw_id"], ["hes_read_raw.id"]),
        sa.ForeignKeyConstraint(["hes_event_raw_id"], ["hes_event_raw.id"]),
    )
    op.create_index("ix_ingest_error_log_exception_type", "ingest_error_log", ["exception_type"])
    op.create_index("ix_ingest_error_log_exception_code", "ingest_error_log", ["exception_code"])


def downgrade() -> None:
    op.drop_index("ix_ingest_error_log_exception_code", table_name="ingest_error_log")
    op.drop_index("ix_ingest_error_log_exception_type", table_name="ingest_error_log")
    op.drop_table("ingest_error_log")

    op.drop_index("ix_canonical_measurement_measured_at", table_name="canonical_measurement")
    op.drop_table("canonical_measurement")

    op.drop_index("ix_hes_event_raw_event_time", table_name="hes_event_raw")
    op.drop_index("ix_hes_event_raw_meter_identifier", table_name="hes_event_raw")
    op.drop_index("ix_hes_event_raw_source_system", table_name="hes_event_raw")
    op.drop_table("hes_event_raw")

    op.drop_index("ix_hes_read_raw_measured_at", table_name="hes_read_raw")
    op.drop_index("ix_hes_read_raw_channel_identifier", table_name="hes_read_raw")
    op.drop_index("ix_hes_read_raw_meter_identifier", table_name="hes_read_raw")
    op.drop_index("ix_hes_read_raw_source_system", table_name="hes_read_raw")
    op.drop_table("hes_read_raw")

    op.drop_table("installation_history")

    op.drop_index("ix_measuring_component_source_system", table_name="measuring_component")
    op.drop_table("measuring_component")

    op.drop_index("ix_device_source_system", table_name="device")
    op.drop_table("device")

    op.drop_index("ix_service_point_source_system", table_name="service_point")
    op.drop_table("service_point")

    op.drop_index("ix_ingest_batch_batch_id", table_name="ingest_batch")
    op.drop_index("ix_ingest_batch_source_system", table_name="ingest_batch")
    op.drop_table("ingest_batch")
