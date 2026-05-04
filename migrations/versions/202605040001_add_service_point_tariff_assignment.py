"""Add service_point_tariff_assignment baseline.

Revision ID: 202605040001
Revises: 202605030001
Create Date: 2026-05-04 13:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605040001"
down_revision = "202605030001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "service_point_tariff_assignment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("tariff_plan_code", sa.String(length=60), nullable=False),
        sa.Column("tariff_version_code", sa.String(length=60), nullable=True),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column(
            "source_system",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("source_reference", sa.String(length=200), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "effective_to is null or effective_from < effective_to",
            name="ck_service_point_tariff_assignment_effective_window",
        ),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_service_point_tariff_assignment_effective_from",
        "service_point_tariff_assignment",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_tariff_assignment_effective_to",
        "service_point_tariff_assignment",
        ["effective_to"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_tariff_assignment_is_current",
        "service_point_tariff_assignment",
        ["is_current"],
        unique=False,
    )
    op.create_index(
        "ix_service_point_tariff_assignment_service_point_effective_from",
        "service_point_tariff_assignment",
        ["service_point_id", "effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_spta_service_point_tariff_plan_code",
        "service_point_tariff_assignment",
        ["service_point_id", "tariff_plan_code"],
        unique=False,
    )
    op.create_index(
        "uq_service_point_tariff_assignment_current_service_point",
        "service_point_tariff_assignment",
        ["service_point_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_service_point_tariff_assignment_current_service_point",
        table_name="service_point_tariff_assignment",
    )
    op.drop_index(
        "ix_spta_service_point_tariff_plan_code",
        table_name="service_point_tariff_assignment",
    )
    op.drop_index(
        "ix_service_point_tariff_assignment_service_point_effective_from",
        table_name="service_point_tariff_assignment",
    )
    op.drop_index(
        "ix_service_point_tariff_assignment_is_current",
        table_name="service_point_tariff_assignment",
    )
    op.drop_index(
        "ix_service_point_tariff_assignment_effective_to",
        table_name="service_point_tariff_assignment",
    )
    op.drop_index(
        "ix_service_point_tariff_assignment_effective_from",
        table_name="service_point_tariff_assignment",
    )
    op.drop_table("service_point_tariff_assignment")
