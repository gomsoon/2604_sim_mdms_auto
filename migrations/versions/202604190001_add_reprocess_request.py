"""Add reprocess request audit table.

Revision ID: 202604190001
Revises: 202604180001
Create Date: 2026-04-19 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604190001"
down_revision = "202604180001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reprocess_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ingest_error_log_id", sa.Integer(), nullable=False),
        sa.Column("hes_read_raw_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_code", sa.String(length=80), nullable=True),
        sa.Column("result_message", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["ingest_error_log_id"], ["ingest_error_log.id"]),
        sa.ForeignKeyConstraint(["hes_read_raw_id"], ["hes_read_raw.id"]),
    )
    op.create_index(
        "ix_reprocess_request_ingest_error_log_id",
        "reprocess_request",
        ["ingest_error_log_id"],
    )
    op.create_index(
        "ix_reprocess_request_hes_read_raw_id",
        "reprocess_request",
        ["hes_read_raw_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_reprocess_request_hes_read_raw_id", table_name="reprocess_request")
    op.drop_index("ix_reprocess_request_ingest_error_log_id", table_name="reprocess_request")
    op.drop_table("reprocess_request")
