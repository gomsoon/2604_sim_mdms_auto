"""Add operational event timeline support.

Revision ID: 202604210002
Revises: 202604210001
Create Date: 2026-04-21 22:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604210002"
down_revision = "202604210001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_layer", sa.String(length=30), nullable=False),
        sa.Column("event_category", sa.String(length=40), nullable=False),
        sa.Column("event_code", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column(
            "is_alert",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("alert_status", sa.String(length=20), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=100), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("operator_memo", sa.Text(), nullable=True),
        sa.Column("title_en", sa.String(length=200), nullable=False),
        sa.Column("title_ko", sa.String(length=200), nullable=False),
        sa.Column("message_en", sa.Text(), nullable=False),
        sa.Column("message_ko", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("adapter_instance_id", sa.Integer(), nullable=True),
        sa.Column("adapter_run_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("ingest_batch_id", sa.Integer(), nullable=True),
        sa.Column("ingest_error_log_id", sa.Integer(), nullable=True),
        sa.Column("reprocess_request_id", sa.Integer(), nullable=True),
        sa.Column("meter_identifier", sa.String(length=100), nullable=True),
        sa.Column("batch_id", sa.String(length=100), nullable=True),
        sa.Column(
            "details",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(["adapter_instance_id"], ["adapter_instance.id"]),
        sa.ForeignKeyConstraint(["adapter_run_id"], ["adapter_run.id"]),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_run.id"]),
        sa.ForeignKeyConstraint(["ingest_batch_id"], ["ingest_batch.id"]),
        sa.ForeignKeyConstraint(["ingest_error_log_id"], ["ingest_error_log.id"]),
        sa.ForeignKeyConstraint(["reprocess_request_id"], ["reprocess_request.id"]),
        sa.CheckConstraint(
            "(is_alert = false AND alert_status IS NULL) OR "
            "(is_alert = true AND alert_status IN ('open', 'acknowledged', 'closed'))",
            name="ck_operational_event_alert_status_scope",
        ),
        sa.CheckConstraint(
            "(is_alert = true) OR "
            "(opened_at IS NULL AND acknowledged_at IS NULL AND acknowledged_by IS NULL "
            "AND closed_at IS NULL AND operator_memo IS NULL)",
            name="ck_operational_event_alert_fields_scope",
        ),
        sa.CheckConstraint(
            "(alert_status <> 'acknowledged') OR acknowledged_at IS NOT NULL",
            name="ck_operational_event_acknowledged_requires_time",
        ),
        sa.CheckConstraint(
            "(alert_status <> 'closed') OR closed_at IS NOT NULL",
            name="ck_operational_event_closed_requires_time",
        ),
    )

    op.create_index("ix_operational_event_occurred_at", "operational_event", ["occurred_at"])
    op.create_index("ix_operational_event_source_layer", "operational_event", ["source_layer"])
    op.create_index(
        "ix_operational_event_event_category", "operational_event", ["event_category"]
    )
    op.create_index("ix_operational_event_event_code", "operational_event", ["event_code"])
    op.create_index("ix_operational_event_severity", "operational_event", ["severity"])
    op.create_index("ix_operational_event_is_alert", "operational_event", ["is_alert"])
    op.create_index("ix_operational_event_alert_status", "operational_event", ["alert_status"])
    op.create_index(
        "ix_operational_event_alert_status_occurred_at",
        "operational_event",
        ["is_alert", "alert_status", "occurred_at"],
    )
    op.create_index(
        "ix_operational_event_severity_occurred_at",
        "operational_event",
        ["severity", "occurred_at"],
    )
    op.create_index(
        "ix_operational_event_event_code_occurred_at",
        "operational_event",
        ["event_code", "occurred_at"],
    )
    op.create_index(
        "ix_operational_event_adapter_instance_id", "operational_event", ["adapter_instance_id"]
    )
    op.create_index("ix_operational_event_adapter_run_id", "operational_event", ["adapter_run_id"])
    op.create_index(
        "ix_operational_event_pipeline_run_id", "operational_event", ["pipeline_run_id"]
    )
    op.create_index(
        "ix_operational_event_ingest_batch_id", "operational_event", ["ingest_batch_id"]
    )
    op.create_index(
        "ix_operational_event_ingest_error_log_id",
        "operational_event",
        ["ingest_error_log_id"],
    )
    op.create_index(
        "ix_operational_event_reprocess_request_id",
        "operational_event",
        ["reprocess_request_id"],
    )
    op.create_index(
        "ix_operational_event_meter_identifier", "operational_event", ["meter_identifier"]
    )
    op.create_index("ix_operational_event_batch_id", "operational_event", ["batch_id"])


def downgrade() -> None:
    op.drop_index("ix_operational_event_batch_id", table_name="operational_event")
    op.drop_index("ix_operational_event_meter_identifier", table_name="operational_event")
    op.drop_index("ix_operational_event_reprocess_request_id", table_name="operational_event")
    op.drop_index("ix_operational_event_ingest_error_log_id", table_name="operational_event")
    op.drop_index("ix_operational_event_ingest_batch_id", table_name="operational_event")
    op.drop_index("ix_operational_event_pipeline_run_id", table_name="operational_event")
    op.drop_index("ix_operational_event_adapter_run_id", table_name="operational_event")
    op.drop_index("ix_operational_event_adapter_instance_id", table_name="operational_event")
    op.drop_index(
        "ix_operational_event_event_code_occurred_at", table_name="operational_event"
    )
    op.drop_index(
        "ix_operational_event_severity_occurred_at", table_name="operational_event"
    )
    op.drop_index(
        "ix_operational_event_alert_status_occurred_at", table_name="operational_event"
    )
    op.drop_index("ix_operational_event_alert_status", table_name="operational_event")
    op.drop_index("ix_operational_event_is_alert", table_name="operational_event")
    op.drop_index("ix_operational_event_severity", table_name="operational_event")
    op.drop_index("ix_operational_event_event_code", table_name="operational_event")
    op.drop_index("ix_operational_event_event_category", table_name="operational_event")
    op.drop_index("ix_operational_event_source_layer", table_name="operational_event")
    op.drop_index("ix_operational_event_occurred_at", table_name="operational_event")
    op.drop_table("operational_event")

