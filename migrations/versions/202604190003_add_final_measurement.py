"""Add final measurement table.

Revision ID: 202604190003
Revises: 202604190002
Create Date: 2026-04-19 18:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604190003"
down_revision = "202604190002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "final_measurement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_measurement_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("quality_code", sa.String(length=40), nullable=True),
        sa.Column("status_code", sa.String(length=40), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column("final_status", sa.String(length=30), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(["canonical_measurement_id"], ["canonical_measurement.id"]),
        sa.ForeignKeyConstraint(["measuring_component_id"], ["measuring_component.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.UniqueConstraint("canonical_measurement_id"),
    )
    op.create_index("ix_final_measurement_measured_at", "final_measurement", ["measured_at"])


def downgrade() -> None:
    op.drop_index("ix_final_measurement_measured_at", table_name="final_measurement")
    op.drop_table("final_measurement")
