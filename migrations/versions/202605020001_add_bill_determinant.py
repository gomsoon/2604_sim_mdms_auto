"""Add bill_determinant persistence baseline.

Revision ID: 202605020001
Revises: 202604300001
Create Date: 2026-05-02 14:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605020001"
down_revision = "202604300001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_determinant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("determinant_type", sa.String(length=60), nullable=False),
        sa.Column("billing_period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_timezone_name", sa.String(length=50), nullable=False),
        sa.Column("tariff_plan_code", sa.String(length=60), nullable=True),
        sa.Column("tou_bucket_code", sa.String(length=60), nullable=True),
        sa.Column("demand_window_code", sa.String(length=60), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column("determinant_value", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("source_usage_count", sa.Integer(), nullable=False),
        sa.Column("quality_summary", sa.String(length=80), nullable=False),
        sa.Column("calculation_status", sa.String(length=30), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("revision_reason_code", sa.String(length=60), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("supersedes_bill_determinant_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["supersedes_bill_determinant_id"],
            ["bill_determinant.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bill_determinant_determinant_type",
        "bill_determinant",
        ["determinant_type"],
        unique=False,
    )
    op.create_index(
        "ix_bill_determinant_billing_period_start_at",
        "bill_determinant",
        ["billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_bill_determinant_calculation_status",
        "bill_determinant",
        ["calculation_status"],
        unique=False,
    )
    op.create_index(
        "ix_bill_determinant_service_point_billing_period_start_at",
        "bill_determinant",
        ["service_point_id", "billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_bill_determinant_measuring_component_billing_period_start_at",
        "bill_determinant",
        ["measuring_component_id", "billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_bill_determinant_is_current",
        "bill_determinant",
        ["is_current"],
        unique=False,
    )
    op.create_index(
        "ix_bill_determinant_supersedes_bill_determinant_id",
        "bill_determinant",
        ["supersedes_bill_determinant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bill_determinant_supersedes_bill_determinant_id",
        table_name="bill_determinant",
    )
    op.drop_index("ix_bill_determinant_is_current", table_name="bill_determinant")
    op.drop_index(
        "ix_bill_determinant_measuring_component_billing_period_start_at",
        table_name="bill_determinant",
    )
    op.drop_index(
        "ix_bill_determinant_service_point_billing_period_start_at",
        table_name="bill_determinant",
    )
    op.drop_index(
        "ix_bill_determinant_calculation_status",
        table_name="bill_determinant",
    )
    op.drop_index(
        "ix_bill_determinant_billing_period_start_at",
        table_name="bill_determinant",
    )
    op.drop_index("ix_bill_determinant_determinant_type", table_name="bill_determinant")
    op.drop_table("bill_determinant")
