"""Add pipeline processing metadata tables.

Revision ID: 202604190002
Revises: 202604190001
Create Date: 2026-04-19 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604190002"
down_revision = "202604190001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_run",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_name", sa.String(length=50), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("ingest_batch_id", sa.Integer(), nullable=True),
        sa.Column("reprocess_request_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_code", sa.String(length=80), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["ingest_batch_id"], ["ingest_batch.id"]),
        sa.ForeignKeyConstraint(["reprocess_request_id"], ["reprocess_request.id"]),
    )
    op.create_index("ix_pipeline_run_pipeline_name", "pipeline_run", ["pipeline_name"])

    op.create_table(
        "processing_watermark",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pipeline_name", sa.String(length=50), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=True),
        sa.Column("record_type", sa.String(length=30), nullable=True),
        sa.Column("last_processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
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
        sa.UniqueConstraint(
            "pipeline_name",
            "source_system",
            "record_type",
            name="uq_processing_watermark_scope",
        ),
    )
    op.create_index(
        "ix_processing_watermark_pipeline_name", "processing_watermark", ["pipeline_name"]
    )
    op.create_index(
        "ix_processing_watermark_source_system", "processing_watermark", ["source_system"]
    )
    op.create_index(
        "ix_processing_watermark_record_type", "processing_watermark", ["record_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_processing_watermark_record_type", table_name="processing_watermark")
    op.drop_index("ix_processing_watermark_source_system", table_name="processing_watermark")
    op.drop_index("ix_processing_watermark_pipeline_name", table_name="processing_watermark")
    op.drop_table("processing_watermark")
    op.drop_index("ix_pipeline_run_pipeline_name", table_name="pipeline_run")
    op.drop_table("pipeline_run")
