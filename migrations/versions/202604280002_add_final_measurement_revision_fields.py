"""add final measurement revision fields

Revision ID: 202604280002
Revises: 202604280001
Create Date: 2026-04-28 23:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604280002"
down_revision = "202604280001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "final_measurement",
        sa.Column("revision_number", sa.Integer(), nullable=True),
    )
    op.add_column(
        "final_measurement",
        sa.Column("revision_reason_code", sa.String(length=60), nullable=True),
    )
    op.add_column(
        "final_measurement",
        sa.Column("is_current", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "final_measurement",
        sa.Column("supersedes_final_measurement_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_final_measurement_is_current",
        "final_measurement",
        ["is_current"],
        unique=False,
    )
    op.create_index(
        "ix_final_measurement_supersedes_final_measurement_id",
        "final_measurement",
        ["supersedes_final_measurement_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_final_measurement_supersedes_final_measurement_id",
        "final_measurement",
        "final_measurement",
        ["supersedes_final_measurement_id"],
        ["id"],
    )

    op.execute(
        """
        UPDATE final_measurement
        SET revision_number = 1,
            is_current = TRUE
        WHERE revision_number IS NULL
           OR is_current IS NULL
        """
    )

    op.alter_column("final_measurement", "revision_number", nullable=False)
    op.alter_column("final_measurement", "is_current", nullable=False)


def downgrade() -> None:
    op.drop_constraint(
        "fk_final_measurement_supersedes_final_measurement_id",
        "final_measurement",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_final_measurement_supersedes_final_measurement_id",
        table_name="final_measurement",
    )
    op.drop_index("ix_final_measurement_is_current", table_name="final_measurement")
    op.drop_column("final_measurement", "supersedes_final_measurement_id")
    op.drop_column("final_measurement", "is_current")
    op.drop_column("final_measurement", "revision_reason_code")
    op.drop_column("final_measurement", "revision_number")
