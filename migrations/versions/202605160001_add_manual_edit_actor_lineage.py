"""add manual edit actor lineage

Revision ID: 202605160001
Revises: 202605150002
Create Date: 2026-05-16 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605160001"
down_revision = "202605150002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manual_edit_audit",
        sa.Column("edited_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_manual_edit_audit_edited_by_user_account_id_user_account",
        "manual_edit_audit",
        "user_account",
        ["edited_by_user_account_id"],
        ["id"],
    )
    op.create_index(
        "ix_manual_edit_audit_edited_by_user_account_id",
        "manual_edit_audit",
        ["edited_by_user_account_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_manual_edit_audit_edited_by_user_account_id", table_name="manual_edit_audit")
    op.drop_constraint(
        "fk_manual_edit_audit_edited_by_user_account_id_user_account",
        "manual_edit_audit",
        type_="foreignkey",
    )
    op.drop_column("manual_edit_audit", "edited_by_user_account_id")
