"""Add billing export queue persistence baseline.

Revision ID: 202605130001
Revises: 202605050003
Create Date: 2026-05-13 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605130001"
down_revision = "202605050003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_export_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_scope", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=True),
        sa.Column("billing_period_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("billing_period_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_system_code", sa.String(length=60), nullable=False),
        sa.Column("payload_format", sa.String(length=40), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("operator_memo", sa.Text(), nullable=True),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("claimed_by", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status in ('queued', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_billing_export_request_status",
        ),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_billing_export_request_status",
        "billing_export_request",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_request_scope",
        "billing_export_request",
        ["request_scope"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_service_point_id",
        "billing_export_request",
        ["service_point_id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_target_system_code",
        "billing_export_request",
        ["target_system_code"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_payload_format",
        "billing_export_request",
        ["payload_format"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_requested_by",
        "billing_export_request",
        ["requested_by"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_created_at",
        "billing_export_request",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "billing_export_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("billing_export_request_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("billing_period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("tariff_plan_code", sa.String(length=60), nullable=True),
        sa.Column("summary_status", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_code", sa.String(length=80), nullable=True),
        sa.Column("payload_snapshot", sa.JSON(), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "summary_status in ('complete', 'partial', 'blocked')",
            name="ck_billing_export_item_summary_status",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'processing', 'completed', 'failed', 'skipped')",
            name="ck_billing_export_item_status",
        ),
        sa.ForeignKeyConstraint(
            ["billing_export_request_id"],
            ["billing_export_request.id"],
        ),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_billing_export_item_billing_export_request_id",
        "billing_export_item",
        ["billing_export_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_item_status",
        "billing_export_item",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_item_service_point_id",
        "billing_export_item",
        ["service_point_id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_item_request_period_start_at",
        "billing_export_item",
        ["billing_export_request_id", "billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_item_service_point_period_start_at",
        "billing_export_item",
        ["service_point_id", "billing_period_start_at"],
        unique=False,
    )

    op.add_column(
        "pipeline_run",
        sa.Column("billing_export_request_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_pipeline_run_billing_export_request_id",
        "pipeline_run",
        ["billing_export_request_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_pipeline_run_billing_export_request",
        "pipeline_run",
        "billing_export_request",
        ["billing_export_request_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_pipeline_run_billing_export_request",
        "pipeline_run",
        type_="foreignkey",
    )
    op.drop_index("ix_pipeline_run_billing_export_request_id", table_name="pipeline_run")
    op.drop_column("pipeline_run", "billing_export_request_id")

    op.drop_index("ix_billing_export_item_service_point_period_start_at", table_name="billing_export_item")
    op.drop_index("ix_billing_export_item_request_period_start_at", table_name="billing_export_item")
    op.drop_index("ix_billing_export_item_service_point_id", table_name="billing_export_item")
    op.drop_index("ix_billing_export_item_status", table_name="billing_export_item")
    op.drop_index("ix_billing_export_item_billing_export_request_id", table_name="billing_export_item")
    op.drop_table("billing_export_item")

    op.drop_index("ix_billing_export_request_created_at", table_name="billing_export_request")
    op.drop_index("ix_billing_export_request_requested_by", table_name="billing_export_request")
    op.drop_index("ix_billing_export_request_payload_format", table_name="billing_export_request")
    op.drop_index("ix_billing_export_request_target_system_code", table_name="billing_export_request")
    op.drop_index("ix_billing_export_request_service_point_id", table_name="billing_export_request")
    op.drop_index("ix_billing_export_request_request_scope", table_name="billing_export_request")
    op.drop_index("ix_billing_export_request_status", table_name="billing_export_request")
    op.drop_table("billing_export_request")
