"""Add HES lineage to operational events.

Revision ID: 202604220004
Revises: 202604220003
Create Date: 2026-04-22 15:05:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604220004"
down_revision = "202604220003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("operational_event") as batch_op:
        batch_op.add_column(sa.Column("hes_system_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_operational_event_hes_system_id",
            "hes_system",
            ["hes_system_id"],
            ["id"],
        )
        batch_op.create_index("ix_operational_event_hes_system_id", ["hes_system_id"])

    op.execute(
        """
        UPDATE operational_event AS event
        SET hes_system_id = instance.hes_system_id
        FROM adapter_instance AS instance
        WHERE event.hes_system_id IS NULL
          AND event.adapter_instance_id = instance.id
          AND instance.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE operational_event AS event
        SET hes_system_id = batch.hes_system_id
        FROM ingest_batch AS batch
        WHERE event.hes_system_id IS NULL
          AND event.ingest_batch_id = batch.id
          AND batch.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE operational_event AS event
        SET hes_system_id = instance.hes_system_id
        FROM adapter_run AS run
        JOIN adapter_instance AS instance ON instance.id = run.adapter_instance_id
        WHERE event.hes_system_id IS NULL
          AND event.adapter_run_id = run.id
          AND instance.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE operational_event AS event
        SET hes_system_id = batch.hes_system_id
        FROM pipeline_run AS pipeline
        JOIN ingest_batch AS batch ON batch.id = pipeline.ingest_batch_id
        WHERE event.hes_system_id IS NULL
          AND event.pipeline_run_id = pipeline.id
          AND batch.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE operational_event AS event
        SET hes_system_id = raw.hes_system_id
        FROM reprocess_request AS request
        JOIN hes_read_raw AS raw ON raw.id = request.hes_read_raw_id
        WHERE event.hes_system_id IS NULL
          AND event.reprocess_request_id = request.id
          AND raw.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE operational_event AS event
        SET hes_system_id = COALESCE(read_raw.hes_system_id, event_raw.hes_system_id)
        FROM ingest_error_log AS error_log
        LEFT JOIN hes_read_raw AS read_raw ON read_raw.id = error_log.hes_read_raw_id
        LEFT JOIN hes_event_raw AS event_raw ON event_raw.id = error_log.hes_event_raw_id
        WHERE event.hes_system_id IS NULL
          AND event.ingest_error_log_id = error_log.id
          AND COALESCE(read_raw.hes_system_id, event_raw.hes_system_id) IS NOT NULL
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("operational_event") as batch_op:
        batch_op.drop_index("ix_operational_event_hes_system_id")
        batch_op.drop_constraint("fk_operational_event_hes_system_id", type_="foreignkey")
        batch_op.drop_column("hes_system_id")
