"""Add estimation audit missing-interval context support.

Revision ID: 202605140001
Revises: 202605130002
Create Date: 2026-05-14 10:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605140001"
down_revision = "202605130002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estimation_audit",
        sa.Column("anchor_vee_exception_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "estimation_audit",
        sa.Column("raw_interval_window_state_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "estimation_audit",
        sa.Column(
            "estimation_mode",
            sa.String(length=40),
            nullable=False,
            server_default="substitution",
        ),
    )
    op.create_foreign_key(
        "fk_estimation_audit_anchor_vee_exception",
        "estimation_audit",
        "vee_exception",
        ["anchor_vee_exception_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_estimation_audit_raw_interval_window_state",
        "estimation_audit",
        "raw_interval_window_state",
        ["raw_interval_window_state_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_estimation_audit_estimation_mode",
        "estimation_audit",
        "estimation_mode in ('substitution', 'synthetic_missing_interval')",
    )
    op.create_index(
        "ix_estimation_audit_anchor_vee_exception_id",
        "estimation_audit",
        ["anchor_vee_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_raw_interval_window_state_id",
        "estimation_audit",
        ["raw_interval_window_state_id"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_estimation_mode",
        "estimation_audit",
        ["estimation_mode"],
        unique=False,
    )
    op.alter_column("estimation_audit", "estimation_mode", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_estimation_audit_estimation_mode", table_name="estimation_audit")
    op.drop_index(
        "ix_estimation_audit_raw_interval_window_state_id",
        table_name="estimation_audit",
    )
    op.drop_index(
        "ix_estimation_audit_anchor_vee_exception_id",
        table_name="estimation_audit",
    )
    op.drop_constraint(
        "ck_estimation_audit_estimation_mode",
        "estimation_audit",
        type_="check",
    )
    op.drop_constraint(
        "fk_estimation_audit_raw_interval_window_state",
        "estimation_audit",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_estimation_audit_anchor_vee_exception",
        "estimation_audit",
        type_="foreignkey",
    )
    op.drop_column("estimation_audit", "estimation_mode")
    op.drop_column("estimation_audit", "raw_interval_window_state_id")
    op.drop_column("estimation_audit", "anchor_vee_exception_id")
