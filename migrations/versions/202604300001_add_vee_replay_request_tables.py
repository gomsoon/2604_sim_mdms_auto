"""add vee replay request tables

Revision ID: 202604300001
Revises: 202604280003
Create Date: 2026-04-30 11:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604300001"
down_revision = "202604280003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vee_replay_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_scope", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("operator_memo", sa.Text(), nullable=True),
        sa.Column("hes_system_id", sa.Integer(), nullable=True),
        sa.Column("ingest_batch_id", sa.Integer(), nullable=True),
        sa.Column("measured_at_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("measured_at_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("window_timezone_name", sa.String(length=50), nullable=True),
        sa.Column("target_initial_count", sa.Integer(), nullable=False),
        sa.Column("processed_count", sa.Integer(), nullable=False),
        sa.Column("succeeded_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("reopened_exception_count", sa.Integer(), nullable=False),
        sa.Column("cleared_exception_count", sa.Integer(), nullable=False),
        sa.Column("final_superseded_count", sa.Integer(), nullable=False),
        sa.Column("usage_recalculated_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["hes_system_id"], ["hes_system.id"]),
        sa.ForeignKeyConstraint(["ingest_batch_id"], ["ingest_batch.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_vee_replay_request_status",
        "vee_replay_request",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_request_scope",
        "vee_replay_request",
        ["request_scope"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_hes_system_id",
        "vee_replay_request",
        ["hes_system_id"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_ingest_batch_id",
        "vee_replay_request",
        ["ingest_batch_id"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_requested_by",
        "vee_replay_request",
        ["requested_by"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_created_at",
        "vee_replay_request",
        ["created_at"],
        unique=False,
    )

    op.create_table(
        "vee_replay_request_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vee_replay_request_id", sa.Integer(), nullable=False),
        sa.Column("initial_measurement_id", sa.Integer(), nullable=False),
        sa.Column("representative_vee_exception_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result_code", sa.String(length=80), nullable=True),
        sa.Column("vee_execution_log_id", sa.Integer(), nullable=True),
        sa.Column("previous_final_measurement_id", sa.Integer(), nullable=True),
        sa.Column("current_final_measurement_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["current_final_measurement_id"], ["final_measurement.id"]),
        sa.ForeignKeyConstraint(["initial_measurement_id"], ["initial_measurement.id"]),
        sa.ForeignKeyConstraint(["previous_final_measurement_id"], ["final_measurement.id"]),
        sa.ForeignKeyConstraint(["representative_vee_exception_id"], ["vee_exception.id"]),
        sa.ForeignKeyConstraint(["vee_execution_log_id"], ["vee_execution_log.id"]),
        sa.ForeignKeyConstraint(["vee_replay_request_id"], ["vee_replay_request.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "vee_replay_request_id",
            "initial_measurement_id",
            name="uq_vee_replay_request_item_scope",
        ),
    )
    op.create_index(
        "ix_vee_replay_request_item_vee_replay_request_id",
        "vee_replay_request_item",
        ["vee_replay_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_item_status",
        "vee_replay_request_item",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_item_initial_measurement_id",
        "vee_replay_request_item",
        ["initial_measurement_id"],
        unique=False,
    )
    op.create_index(
        "ix_vee_replay_request_item_representative_vee_exception_id",
        "vee_replay_request_item",
        ["representative_vee_exception_id"],
        unique=False,
    )

    op.add_column(
        "pipeline_run",
        sa.Column("vee_replay_request_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_pipeline_run_vee_replay_request_id",
        "pipeline_run",
        "vee_replay_request",
        ["vee_replay_request_id"],
        ["id"],
    )
    op.create_index(
        "ix_pipeline_run_vee_replay_request_id",
        "pipeline_run",
        ["vee_replay_request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_run_vee_replay_request_id", table_name="pipeline_run")
    op.drop_constraint(
        "fk_pipeline_run_vee_replay_request_id",
        "pipeline_run",
        type_="foreignkey",
    )
    op.drop_column("pipeline_run", "vee_replay_request_id")

    op.drop_index(
        "ix_vee_replay_request_item_representative_vee_exception_id",
        table_name="vee_replay_request_item",
    )
    op.drop_index("ix_vee_replay_request_item_initial_measurement_id", table_name="vee_replay_request_item")
    op.drop_index("ix_vee_replay_request_item_status", table_name="vee_replay_request_item")
    op.drop_index(
        "ix_vee_replay_request_item_vee_replay_request_id",
        table_name="vee_replay_request_item",
    )
    op.drop_table("vee_replay_request_item")

    op.drop_index("ix_vee_replay_request_created_at", table_name="vee_replay_request")
    op.drop_index("ix_vee_replay_request_requested_by", table_name="vee_replay_request")
    op.drop_index("ix_vee_replay_request_ingest_batch_id", table_name="vee_replay_request")
    op.drop_index("ix_vee_replay_request_hes_system_id", table_name="vee_replay_request")
    op.drop_index("ix_vee_replay_request_request_scope", table_name="vee_replay_request")
    op.drop_index("ix_vee_replay_request_status", table_name="vee_replay_request")
    op.drop_table("vee_replay_request")
