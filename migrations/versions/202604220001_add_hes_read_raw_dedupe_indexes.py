"""Add dedupe indexes for hes_read_raw.

Revision ID: 202604220001
Revises: 202604210002
Create Date: 2026-04-22 09:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604220001"
down_revision = "202604210002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            select source_system, source_record_key, count(*) as duplicate_count
            from hes_read_raw
            where source_record_key is not null
              and btrim(source_record_key) <> ''
            group by source_system, source_record_key
            having count(*) > 1
            order by duplicate_count desc, source_system asc, source_record_key asc
            fetch first 1 row only
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot create uq_hes_read_raw_source_record_key_scope because duplicate "
            f"source replay keys already exist: source_system={duplicate.source_system}, "
            f"source_record_key={duplicate.source_record_key}, count={duplicate.duplicate_count}."
        )

    op.create_index(
        "uq_hes_read_raw_source_record_key_scope",
        "hes_read_raw",
        ["source_system", "source_record_key"],
        unique=True,
        postgresql_where=sa.text("source_record_key IS NOT NULL AND btrim(source_record_key) <> ''"),
    )
    op.create_index(
        "ix_hes_read_raw_source_meter_channel_measured_at",
        "hes_read_raw",
        ["source_system", "meter_identifier", "channel_identifier", "measured_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_hes_read_raw_source_meter_channel_measured_at", table_name="hes_read_raw")
    op.drop_index("uq_hes_read_raw_source_record_key_scope", table_name="hes_read_raw")
