"""Add adapter runtime management tables.

Revision ID: 202604190004
Revises: 202604190003
Create Date: 2026-04-19 23:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604190004"
down_revision = "202604190003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "adapter_definition",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("adapter_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("delivery_mode", sa.String(length=20), nullable=False),
        sa.Column("source_family", sa.String(length=50), nullable=False),
        sa.Column("record_type", sa.String(length=30), nullable=False),
        sa.Column("adapter_profile_key", sa.String(length=100), nullable=True),
        sa.Column("implementation_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("adapter_code"),
    )
    op.create_index("ix_adapter_definition_delivery_mode", "adapter_definition", ["delivery_mode"])
    op.create_index("ix_adapter_definition_record_type", "adapter_definition", ["record_type"])
    op.create_index("ix_adapter_definition_source_family", "adapter_definition", ["source_family"])
    op.create_index("ix_adapter_definition_status", "adapter_definition", ["status"])

    op.create_table(
        "adapter_instance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("adapter_definition_id", sa.Integer(), nullable=False),
        sa.Column("instance_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("admin_state", sa.String(length=30), nullable=False),
        sa.Column("status_reason", sa.String(length=200), nullable=True),
        sa.Column("poll_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("landing_enabled", sa.Boolean(), nullable=False),
        sa.Column("connection_config_masked", sa.JSON(), nullable=True),
        sa.Column("secret_ref", sa.String(length=200), nullable=True),
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
        sa.ForeignKeyConstraint(["adapter_definition_id"], ["adapter_definition.id"]),
        sa.UniqueConstraint("instance_code"),
    )
    op.create_index("ix_adapter_instance_adapter_definition_id", "adapter_instance", ["adapter_definition_id"])
    op.create_index("ix_adapter_instance_admin_state", "adapter_instance", ["admin_state"])
    op.create_index("ix_adapter_instance_next_run_at", "adapter_instance", ["next_run_at"])
    op.create_index("ix_adapter_instance_source_system", "adapter_instance", ["source_system"])
    op.create_index(
        "ix_adapter_instance_admin_state_next_run_at",
        "adapter_instance",
        ["admin_state", "next_run_at"],
    )

    op.create_table(
        "adapter_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("adapter_instance_id", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("run_status", sa.String(length=30), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_rows_fetched", sa.Integer(), nullable=True),
        sa.Column("ingest_batches_created", sa.Integer(), nullable=True),
        sa.Column("ingest_records_created", sa.Integer(), nullable=True),
        sa.Column("watermark_before", sa.String(length=200), nullable=True),
        sa.Column("watermark_after", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["adapter_instance_id"], ["adapter_instance.id"]),
    )
    op.create_index("ix_adapter_run_adapter_instance_id", "adapter_run", ["adapter_instance_id"])
    op.create_index(
        "ix_adapter_run_adapter_instance_created_at",
        "adapter_run",
        ["adapter_instance_id", "created_at"],
    )
    op.create_index("ix_adapter_run_run_status", "adapter_run", ["run_status"])

    op.create_table(
        "adapter_watermark",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("adapter_instance_id", sa.Integer(), nullable=False),
        sa.Column("record_type", sa.String(length=30), nullable=False),
        sa.Column("cursor_type", sa.String(length=30), nullable=False),
        sa.Column("cursor_value", sa.String(length=200), nullable=True),
        sa.Column("last_source_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["adapter_instance_id"], ["adapter_instance.id"]),
        sa.UniqueConstraint(
            "adapter_instance_id",
            "record_type",
            name="uq_adapter_watermark_scope",
        ),
    )
    op.create_index("ix_adapter_watermark_adapter_instance_id", "adapter_watermark", ["adapter_instance_id"])

    with op.batch_alter_table("ingest_batch") as batch_op:
        batch_op.add_column(sa.Column("adapter_instance_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("adapter_run_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ingest_batch_adapter_instance_id",
            "adapter_instance",
            ["adapter_instance_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_ingest_batch_adapter_run_id",
            "adapter_run",
            ["adapter_run_id"],
            ["id"],
        )
        batch_op.create_index("ix_ingest_batch_adapter_instance_id", ["adapter_instance_id"])
        batch_op.create_index("ix_ingest_batch_adapter_run_id", ["adapter_run_id"])


def downgrade() -> None:
    with op.batch_alter_table("ingest_batch") as batch_op:
        batch_op.drop_index("ix_ingest_batch_adapter_run_id")
        batch_op.drop_index("ix_ingest_batch_adapter_instance_id")
        batch_op.drop_constraint("fk_ingest_batch_adapter_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_ingest_batch_adapter_instance_id", type_="foreignkey")
        batch_op.drop_column("adapter_run_id")
        batch_op.drop_column("adapter_instance_id")

    op.drop_index("ix_adapter_watermark_adapter_instance_id", table_name="adapter_watermark")
    op.drop_table("adapter_watermark")

    op.drop_index("ix_adapter_run_run_status", table_name="adapter_run")
    op.drop_index("ix_adapter_run_adapter_instance_created_at", table_name="adapter_run")
    op.drop_index("ix_adapter_run_adapter_instance_id", table_name="adapter_run")
    op.drop_table("adapter_run")

    op.drop_index(
        "ix_adapter_instance_admin_state_next_run_at", table_name="adapter_instance"
    )
    op.drop_index("ix_adapter_instance_source_system", table_name="adapter_instance")
    op.drop_index("ix_adapter_instance_next_run_at", table_name="adapter_instance")
    op.drop_index("ix_adapter_instance_admin_state", table_name="adapter_instance")
    op.drop_index("ix_adapter_instance_adapter_definition_id", table_name="adapter_instance")
    op.drop_table("adapter_instance")

    op.drop_index("ix_adapter_definition_status", table_name="adapter_definition")
    op.drop_index("ix_adapter_definition_source_family", table_name="adapter_definition")
    op.drop_index("ix_adapter_definition_record_type", table_name="adapter_definition")
    op.drop_index("ix_adapter_definition_delivery_mode", table_name="adapter_definition")
    op.drop_table("adapter_definition")
