"""Add service_point_billing_context baseline.

Revision ID: 202605030001
Revises: 202605020001
Create Date: 2026-05-03 14:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605030001"
down_revision = "202605020001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_point_billing_context",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("timezone_name", sa.String(length=50), nullable=False),
        sa.Column("billing_cycle_mode", sa.String(length=30), nullable=False),
        sa.Column("billing_cycle_anchor_day", sa.Integer(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "source_system",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("source_reference", sa.String(length=200), nullable=True),
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
            "effective_to is null or effective_from < effective_to",
            name="ck_service_point_billing_context_effective_window",
        ),
        sa.CheckConstraint(
            "(billing_cycle_mode = 'calendar_month' and billing_cycle_anchor_day is null) "
            "or "
            "(billing_cycle_mode = 'anchored_month' and billing_cycle_anchor_day between 1 and 28)",
            name="ck_service_point_billing_context_cycle_mode",
        ),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_point_billing_context_billing_cycle_mode",
        "service_point_billing_context",
        ["billing_cycle_mode"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_billing_context_effective_from",
        "service_point_billing_context",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_billing_context_effective_to",
        "service_point_billing_context",
        ["effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_billing_context_is_current",
        "service_point_billing_context",
        ["is_current"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_billing_context_service_point_effective_from",
        "service_point_billing_context",
        ["service_point_id", "effective_from"],
        unique=False,
    )
    op.create_index(
        "uq_service_point_billing_context_current_service_point",
        "service_point_billing_context",
        ["service_point_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_service_point_billing_context_current_service_point",
        table_name="service_point_billing_context",
    )
    op.drop_index(
        "ix_service_point_billing_context_service_point_effective_from",
        table_name="service_point_billing_context",
    )
    op.drop_index(
        "ix_service_point_billing_context_is_current",
        table_name="service_point_billing_context",
    )
    op.drop_index(
        "ix_service_point_billing_context_effective_to",
        table_name="service_point_billing_context",
    )
    op.drop_index(
        "ix_service_point_billing_context_effective_from",
        table_name="service_point_billing_context",
    )
    op.drop_index(
        "ix_service_point_billing_context_billing_cycle_mode",
        table_name="service_point_billing_context",
    )
    op.drop_table("service_point_billing_context")
