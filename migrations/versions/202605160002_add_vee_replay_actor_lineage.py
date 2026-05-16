"""add vee replay actor lineage

Revision ID: 202605160002
Revises: 202605160001
Create Date: 2026-05-16 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605160002"
down_revision = "202605160001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vee_replay_request",
        sa.Column("requested_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vee_replay_request",
        sa.Column("cancelled_by", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "vee_replay_request",
        sa.Column("cancelled_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "vee_replay_request",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_vee_replay_request_requested_by_user_account_id_user_account",
        "vee_replay_request",
        "user_account",
        ["requested_by_user_account_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_vee_replay_request_cancelled_by_user_account_id_user_account",
        "vee_replay_request",
        "user_account",
        ["cancelled_by_user_account_id"],
        ["id"],
    )
    op.create_index(
        "ix_vee_replay_request_requested_by_user_account_id",
        "vee_replay_request",
        ["requested_by_user_account_id"],
    )
    op.create_index(
        "ix_vee_replay_request_cancelled_by_user_account_id",
        "vee_replay_request",
        ["cancelled_by_user_account_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_vee_replay_request_cancelled_by_user_account_id",
        table_name="vee_replay_request",
    )
    op.drop_index(
        "ix_vee_replay_request_requested_by_user_account_id",
        table_name="vee_replay_request",
    )
    op.drop_constraint(
        "fk_vee_replay_request_cancelled_by_user_account_id_user_account",
        "vee_replay_request",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_vee_replay_request_requested_by_user_account_id_user_account",
        "vee_replay_request",
        type_="foreignkey",
    )
    op.drop_column("vee_replay_request", "cancelled_at")
    op.drop_column("vee_replay_request", "cancelled_by_user_account_id")
    op.drop_column("vee_replay_request", "cancelled_by")
    op.drop_column("vee_replay_request", "requested_by_user_account_id")
