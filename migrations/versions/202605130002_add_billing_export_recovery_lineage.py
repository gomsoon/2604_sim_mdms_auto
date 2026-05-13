"""Add billing export recovery lineage.

Revision ID: 202605130002
Revises: 202605130001
Create Date: 2026-05-13 16:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605130002"
down_revision = "202605130001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "billing_export_request",
        sa.Column("source_billing_export_request_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "billing_export_request",
        sa.Column("recovery_action_code", sa.String(length=30), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_export_request_source_billing_export_request",
        "billing_export_request",
        "billing_export_request",
        ["source_billing_export_request_id"],
        ["id"],
    )
    op.create_index(
        "ix_billing_export_request_source_billing_export_request_id",
        "billing_export_request",
        ["source_billing_export_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_billing_export_request_recovery_action_code",
        "billing_export_request",
        ["recovery_action_code"],
        unique=False,
    )
    op.create_check_constraint(
        "ck_billing_export_request_recovery_action_code",
        "billing_export_request",
        "recovery_action_code is null or recovery_action_code in ('rerun', 'recreate')",
    )

    op.add_column(
        "billing_export_item",
        sa.Column("source_billing_export_item_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_billing_export_item_source_billing_export_item",
        "billing_export_item",
        "billing_export_item",
        ["source_billing_export_item_id"],
        ["id"],
    )
    op.create_index(
        "ix_billing_export_item_source_billing_export_item_id",
        "billing_export_item",
        ["source_billing_export_item_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_billing_export_item_source_billing_export_item_id",
        table_name="billing_export_item",
    )
    op.drop_constraint(
        "fk_billing_export_item_source_billing_export_item",
        "billing_export_item",
        type_="foreignkey",
    )
    op.drop_column("billing_export_item", "source_billing_export_item_id")

    op.drop_constraint(
        "ck_billing_export_request_recovery_action_code",
        "billing_export_request",
        type_="check",
    )
    op.drop_index(
        "ix_billing_export_request_recovery_action_code",
        table_name="billing_export_request",
    )
    op.drop_index(
        "ix_billing_export_request_source_billing_export_request_id",
        table_name="billing_export_request",
    )
    op.drop_constraint(
        "fk_billing_export_request_source_billing_export_request",
        "billing_export_request",
        type_="foreignkey",
    )
    op.drop_column("billing_export_request", "recovery_action_code")
    op.drop_column("billing_export_request", "source_billing_export_request_id")
