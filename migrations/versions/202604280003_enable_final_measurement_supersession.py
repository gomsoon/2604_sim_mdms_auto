"""enable final measurement supersession

Revision ID: 202604280003
Revises: 202604280002
Create Date: 2026-04-28 23:45:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604280003"
down_revision = "202604280002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_final_measurement_initial_measurement_id",
        "final_measurement",
        type_="unique",
    )
    op.drop_constraint(
        "final_measurement_canonical_measurement_id_key",
        "final_measurement",
        type_="unique",
    )

    op.create_index(
        "ix_final_measurement_initial_measurement_id",
        "final_measurement",
        ["initial_measurement_id"],
        unique=False,
    )
    op.create_index(
        "ix_final_measurement_canonical_measurement_id",
        "final_measurement",
        ["canonical_measurement_id"],
        unique=False,
    )
    op.create_index(
        "uq_final_measurement_current_initial_measurement_id",
        "final_measurement",
        ["initial_measurement_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_final_measurement_current_initial_measurement_id",
        table_name="final_measurement",
    )
    op.drop_index(
        "ix_final_measurement_canonical_measurement_id",
        table_name="final_measurement",
    )
    op.drop_index(
        "ix_final_measurement_initial_measurement_id",
        table_name="final_measurement",
    )

    op.create_unique_constraint(
        "final_measurement_canonical_measurement_id_key",
        "final_measurement",
        ["canonical_measurement_id"],
    )
    op.create_unique_constraint(
        "uq_final_measurement_initial_measurement_id",
        "final_measurement",
        ["initial_measurement_id"],
    )
