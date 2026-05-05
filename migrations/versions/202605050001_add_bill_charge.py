"""Add bill_charge persistence baseline.

Revision ID: 202605050001
Revises: 202605040001
Create Date: 2026-05-05 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605050001"
down_revision = "202605040001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bill_charge",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=True),
        sa.Column("device_id", sa.Integer(), nullable=True),
        sa.Column("bill_determinant_id", sa.Integer(), nullable=False),
        sa.Column("charge_type", sa.String(length=60), nullable=False),
        sa.Column("billing_period_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("billing_period_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("tariff_plan_code", sa.String(length=60), nullable=True),
        sa.Column("tariff_version_code", sa.String(length=60), nullable=True),
        sa.Column("quantity_value", sa.Numeric(precision=19, scale=4), nullable=False),
        sa.Column("unit_rate_value", sa.Numeric(precision=19, scale=8), nullable=True),
        sa.Column("charge_amount", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("calculation_status", sa.String(length=30), nullable=False),
        sa.Column("quality_summary", sa.String(length=80), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("revision_reason_code", sa.String(length=60), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supersedes_bill_charge_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_run.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.ForeignKeyConstraint(["measuring_component_id"], ["measuring_component.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["bill_determinant_id"], ["bill_determinant.id"]),
        sa.ForeignKeyConstraint(["supersedes_bill_charge_id"], ["bill_charge.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_bill_charge_charge_type",
        "bill_charge",
        ["charge_type"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_billing_period_start_at",
        "bill_charge",
        ["billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_calculation_status",
        "bill_charge",
        ["calculation_status"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_bill_determinant_id",
        "bill_charge",
        ["bill_determinant_id"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_service_point_billing_period_start_at",
        "bill_charge",
        ["service_point_id", "billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_measuring_component_billing_period_start_at",
        "bill_charge",
        ["measuring_component_id", "billing_period_start_at"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_is_current",
        "bill_charge",
        ["is_current"],
        unique=False,
    )
    op.create_index(
        "ix_bill_charge_supersedes_bill_charge_id",
        "bill_charge",
        ["supersedes_bill_charge_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_bill_charge_supersedes_bill_charge_id", table_name="bill_charge")
    op.drop_index("ix_bill_charge_is_current", table_name="bill_charge")
    op.drop_index(
        "ix_bill_charge_measuring_component_billing_period_start_at",
        table_name="bill_charge",
    )
    op.drop_index(
        "ix_bill_charge_service_point_billing_period_start_at",
        table_name="bill_charge",
    )
    op.drop_index("ix_bill_charge_bill_determinant_id", table_name="bill_charge")
    op.drop_index("ix_bill_charge_calculation_status", table_name="bill_charge")
    op.drop_index("ix_bill_charge_billing_period_start_at", table_name="bill_charge")
    op.drop_index("ix_bill_charge_charge_type", table_name="bill_charge")
    op.drop_table("bill_charge")
