"""Add usage_transaction persistence baseline.

Revision ID: 202604280001
Revises: 202604270002
Create Date: 2026-04-28 09:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604280001"
down_revision = "202604270002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_transaction",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("usage_type", sa.String(length=40), nullable=False),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_timezone_name", sa.String(length=50), nullable=False),
        sa.Column("interval_size_minutes", sa.Integer(), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=True),
        sa.Column("usage_value", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("source_final_count", sa.Integer(), nullable=False),
        sa.Column("missing_interval_count", sa.Integer(), nullable=False),
        sa.Column("quality_summary", sa.String(length=80), nullable=False),
        sa.Column("calculation_status", sa.String(length=30), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["measuring_component_id"], ["measuring_component.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_run.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "service_point_id",
            "measuring_component_id",
            "usage_type",
            "period_start_at",
            "period_end_at",
            name="uq_usage_transaction_scope",
        ),
    )
    op.create_index(
        "ix_usage_transaction_usage_type",
        "usage_transaction",
        ["usage_type"],
        unique=False,
    )
    op.create_index(
        "ix_usage_transaction_period_start_at",
        "usage_transaction",
        ["period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_transaction_calculation_status",
        "usage_transaction",
        ["calculation_status"],
        unique=False,
    )
    op.create_index(
        "ix_usage_transaction_service_point_period_start_at",
        "usage_transaction",
        ["service_point_id", "period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_usage_transaction_measuring_component_period_start_at",
        "usage_transaction",
        ["measuring_component_id", "period_start_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_usage_transaction_measuring_component_period_start_at",
        table_name="usage_transaction",
    )
    op.drop_index(
        "ix_usage_transaction_service_point_period_start_at",
        table_name="usage_transaction",
    )
    op.drop_index("ix_usage_transaction_calculation_status", table_name="usage_transaction")
    op.drop_index("ix_usage_transaction_period_start_at", table_name="usage_transaction")
    op.drop_index("ix_usage_transaction_usage_type", table_name="usage_transaction")
    op.drop_table("usage_transaction")
