"""Add estimation actor lineage.

Revision ID: 202605150002
Revises: 202605150001
Create Date: 2026-05-15 16:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605150002"
down_revision = "202605150001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "estimation_audit",
        sa.Column("estimated_by", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "estimation_audit",
        sa.Column("estimated_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_estimation_audit_estimated_by_user_account_id_user_account",
        "estimation_audit",
        "user_account",
        ["estimated_by_user_account_id"],
        ["id"],
    )
    op.create_index(
        "ix_estimation_audit_estimated_by_user_account_id",
        "estimation_audit",
        ["estimated_by_user_account_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_estimation_audit_estimated_by_user_account_id",
        table_name="estimation_audit",
    )
    op.drop_constraint(
        "fk_estimation_audit_estimated_by_user_account_id_user_account",
        "estimation_audit",
        type_="foreignkey",
    )
    op.drop_column("estimation_audit", "estimated_by_user_account_id")
    op.drop_column("estimation_audit", "estimated_by")
