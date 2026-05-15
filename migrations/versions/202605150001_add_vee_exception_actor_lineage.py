"""Add VEE exception actor lineage.

Revision ID: 202605150001
Revises: 202605140002
Create Date: 2026-05-15 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605150001"
down_revision = "202605140002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vee_exception",
        sa.Column("acknowledged_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vee_exception",
        sa.Column("resolved_by", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "vee_exception",
        sa.Column("resolved_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_vee_exception_acknowledged_by_user_account_id_user_account",
        "vee_exception",
        "user_account",
        ["acknowledged_by_user_account_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_vee_exception_resolved_by_user_account_id_user_account",
        "vee_exception",
        "user_account",
        ["resolved_by_user_account_id"],
        ["id"],
    )
    op.create_index(
        "ix_vee_exception_acknowledged_by_user_account_id",
        "vee_exception",
        ["acknowledged_by_user_account_id"],
    )
    op.create_index(
        "ix_vee_exception_resolved_by_user_account_id",
        "vee_exception",
        ["resolved_by_user_account_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vee_exception_resolved_by_user_account_id",
        table_name="vee_exception",
    )
    op.drop_index(
        "ix_vee_exception_acknowledged_by_user_account_id",
        table_name="vee_exception",
    )
    op.drop_constraint(
        "fk_vee_exception_resolved_by_user_account_id_user_account",
        "vee_exception",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_vee_exception_acknowledged_by_user_account_id_user_account",
        "vee_exception",
        type_="foreignkey",
    )
    op.drop_column("vee_exception", "resolved_by_user_account_id")
    op.drop_column("vee_exception", "resolved_by")
    op.drop_column("vee_exception", "acknowledged_by_user_account_id")
