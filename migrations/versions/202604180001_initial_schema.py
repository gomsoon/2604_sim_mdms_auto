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
        "ingestion_batch",
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
    op.create_index("ix_ingestion_batch_source_system", "ingestion_batch", ["source_system"])
    op.create_index("ix_ingestion_batch_batch_id", "ingestion_batch", ["batch_id"])

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
        "raw_read",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingestion_batch_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["raw_read.id"]),
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["ingestion_batch.id"]),
    )
    op.create_index("ix_raw_read_source_system", "raw_read", ["source_system"])
    op.create_index("ix_raw_read_meter_identifier", "raw_read", ["meter_identifier"])
    op.create_index("ix_raw_read_channel_identifier", "raw_read", ["channel_identifier"])
    op.create_index("ix_raw_read_measured_at", "raw_read", ["measured_at"])

    op.create_table(
        "raw_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingestion_batch_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["ingestion_batch_id"], ["ingestion_batch.id"]),
    )
    op.create_index("ix_raw_event_source_system", "raw_event", ["source_system"])
    op.create_index("ix_raw_event_meter_identifier", "raw_event", ["meter_identifier"])
    op.create_index("ix_raw_event_event_time", "raw_event", ["event_time"])

    op.create_table(
        "canonical_measurement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raw_read_id", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["raw_read_id"], ["raw_read.id"]),
        sa.ForeignKeyConstraint(["measuring_component_id"], ["measuring_component.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.UniqueConstraint("raw_read_id", name="uq_canonical_measurement_raw_read_id"),
    )
    op.create_index("ix_canonical_measurement_measured_at", "canonical_measurement", ["measured_at"])

    op.create_table(
        "processing_exception",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("exception_type", sa.String(length=40), nullable=False),
        sa.Column("exception_code", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("raw_read_id", sa.Integer(), nullable=True),
        sa.Column("raw_event_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["raw_read_id"], ["raw_read.id"]),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_event.id"]),
    )
    op.create_index("ix_processing_exception_exception_type", "processing_exception", ["exception_type"])
    op.create_index("ix_processing_exception_exception_code", "processing_exception", ["exception_code"])


def downgrade() -> None:
    op.drop_index("ix_processing_exception_exception_code", table_name="processing_exception")
    op.drop_index("ix_processing_exception_exception_type", table_name="processing_exception")
    op.drop_table("processing_exception")

    op.drop_index("ix_canonical_measurement_measured_at", table_name="canonical_measurement")
    op.drop_table("canonical_measurement")

    op.drop_index("ix_raw_event_event_time", table_name="raw_event")
    op.drop_index("ix_raw_event_meter_identifier", table_name="raw_event")
    op.drop_index("ix_raw_event_source_system", table_name="raw_event")
    op.drop_table("raw_event")

    op.drop_index("ix_raw_read_measured_at", table_name="raw_read")
    op.drop_index("ix_raw_read_channel_identifier", table_name="raw_read")
    op.drop_index("ix_raw_read_meter_identifier", table_name="raw_read")
    op.drop_index("ix_raw_read_source_system", table_name="raw_read")
    op.drop_table("raw_read")

    op.drop_table("installation_history")

    op.drop_index("ix_measuring_component_source_system", table_name="measuring_component")
    op.drop_table("measuring_component")

    op.drop_index("ix_device_source_system", table_name="device")
    op.drop_table("device")

    op.drop_index("ix_service_point_source_system", table_name="service_point")
    op.drop_table("service_point")

    op.drop_index("ix_ingestion_batch_batch_id", table_name="ingestion_batch")
    op.drop_index("ix_ingestion_batch_source_system", table_name="ingestion_batch")
    op.drop_table("ingestion_batch")

