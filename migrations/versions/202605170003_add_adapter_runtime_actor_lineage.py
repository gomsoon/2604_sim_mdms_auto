"""add adapter runtime actor lineage

Revision ID: 202605170003
Revises: 202605170002
Create Date: 2026-05-17 16:20:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202605170003"
down_revision = "202605170002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "adapter_run",
        sa.Column("requested_by", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "adapter_run",
        sa.Column("requested_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_adapter_run_requested_by_user_account",
        "adapter_run",
        "user_account",
        ["requested_by_user_account_id"],
        ["id"],
    )
    op.create_index(
        "ix_adapter_run_requested_by",
        "adapter_run",
        ["requested_by"],
    )
    op.create_index(
        "ix_adapter_run_requested_by_user_account_id",
        "adapter_run",
        ["requested_by_user_account_id"],
    )
    op.execute("update adapter_run set requested_by = 'scheduler' where requested_by is null")
    op.alter_column("adapter_run", "requested_by", existing_type=sa.String(length=120), nullable=False)


def downgrade() -> None:
    op.drop_index("ix_adapter_run_requested_by_user_account_id", table_name="adapter_run")
    op.drop_index("ix_adapter_run_requested_by", table_name="adapter_run")
    op.drop_constraint(
        "fk_adapter_run_requested_by_user_account",
        "adapter_run",
        type_="foreignkey",
    )
    op.drop_column("adapter_run", "requested_by_user_account_id")
    op.drop_column("adapter_run", "requested_by")
