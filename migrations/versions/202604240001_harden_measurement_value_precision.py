"""Harden measurement value precision

Revision ID: 202604240001
Revises: 202604220005
Create Date: 2026-04-24 10:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604240001"
down_revision = "202604220005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE hes_read_raw
        ALTER COLUMN reading_value
        TYPE NUMERIC(19, 4)
        USING reading_value::numeric(19, 4)
        """
    )
    op.alter_column(
        "canonical_measurement",
        "value",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=19, scale=4),
        existing_nullable=False,
    )
    op.alter_column(
        "final_measurement",
        "value",
        existing_type=sa.Float(),
        type_=sa.Numeric(precision=19, scale=4),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "final_measurement",
        "value",
        existing_type=sa.Numeric(precision=19, scale=4),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.alter_column(
        "canonical_measurement",
        "value",
        existing_type=sa.Numeric(precision=19, scale=4),
        type_=sa.Float(),
        existing_nullable=False,
    )
    op.execute(
        """
        ALTER TABLE hes_read_raw
        ALTER COLUMN reading_value
        TYPE DOUBLE PRECISION
        USING reading_value::double precision
        """
    )
