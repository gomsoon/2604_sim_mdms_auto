"""Add final_measurement lineage to initial_measurement.

Revision ID: 202604270002
Revises: 202604270001
Create Date: 2026-04-27 12:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604270002"
down_revision = "202604270001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "final_measurement",
        sa.Column("initial_measurement_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_final_measurement_initial_measurement_id",
        "final_measurement",
        "initial_measurement",
        ["initial_measurement_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_final_measurement_initial_measurement_id",
        "final_measurement",
        ["initial_measurement_id"],
    )

    op.execute(
        """
        UPDATE final_measurement AS fm
        SET initial_measurement_id = im.id
        FROM initial_measurement AS im
        WHERE fm.canonical_measurement_id = im.canonical_measurement_id
          AND fm.initial_measurement_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_final_measurement_initial_measurement_id",
        "final_measurement",
        type_="unique",
    )
    op.drop_constraint(
        "fk_final_measurement_initial_measurement_id",
        "final_measurement",
        type_="foreignkey",
    )
    op.drop_column("final_measurement", "initial_measurement_id")
