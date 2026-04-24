"""Add HES meter reference baseline.

Revision ID: 202604240002
Revises: 202604240001
Create Date: 2026-04-24 13:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604240002"
down_revision = "202604240001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hes_meter_reference",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hes_system_id", sa.Integer(), nullable=False),
        sa.Column("source_table_name", sa.String(length=150), nullable=False),
        sa.Column("source_meter_id", sa.String(length=100), nullable=False),
        sa.Column("source_meter_key", sa.String(length=100), nullable=True),
        sa.Column("meter_name", sa.String(length=150), nullable=True),
        sa.Column("meter_status_code", sa.String(length=60), nullable=True),
        sa.Column("lp_interval_minutes", sa.Integer(), nullable=True),
        sa.Column("meter_type_code", sa.String(length=100), nullable=True),
        sa.Column("device_model_code", sa.String(length=100), nullable=True),
        sa.Column("modem_source_id", sa.String(length=100), nullable=True),
        sa.Column("location_source_id", sa.String(length=100), nullable=True),
        sa.Column("supplier_source_id", sa.String(length=100), nullable=True),
        sa.Column("last_read_at_text", sa.String(length=50), nullable=True),
        sa.Column("source_write_at_text", sa.String(length=50), nullable=True),
        sa.Column("source_payload", sa.JSON(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["hes_system_id"],
            ["hes_system.id"],
            name="fk_hes_meter_reference_hes_system_id",
        ),
        sa.UniqueConstraint(
            "hes_system_id",
            "source_meter_id",
            name="uq_hes_meter_reference_source_meter_id",
        ),
        sa.UniqueConstraint(
            "hes_system_id",
            "source_meter_key",
            name="uq_hes_meter_reference_source_meter_key",
        ),
    )
    op.create_index("ix_hes_meter_reference_hes_system_id", "hes_meter_reference", ["hes_system_id"])
    op.create_index(
        "ix_hes_meter_reference_source_table_name",
        "hes_meter_reference",
        ["source_table_name"],
    )
    op.create_index(
        "ix_hes_meter_reference_meter_status_code",
        "hes_meter_reference",
        ["meter_status_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_hes_meter_reference_meter_status_code", table_name="hes_meter_reference")
    op.drop_index("ix_hes_meter_reference_source_table_name", table_name="hes_meter_reference")
    op.drop_index("ix_hes_meter_reference_hes_system_id", table_name="hes_meter_reference")
    op.drop_table("hes_meter_reference")
