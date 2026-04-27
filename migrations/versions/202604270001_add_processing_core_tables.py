"""Add processing core baseline tables.

Revision ID: 202604270001
Revises: 202604240002
Create Date: 2026-04-27 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604270001"
down_revision = "202604240002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "initial_measurement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_measurement_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(19, 4), nullable=False),
        sa.Column("quality_code", sa.String(length=40), nullable=True),
        sa.Column("status_code", sa.String(length=40), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=False),
        sa.Column("initial_status", sa.String(length=30), nullable=False),
        sa.Column("ready_for_vee_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["canonical_measurement_id"],
            ["canonical_measurement.id"],
            name="fk_initial_measurement_canonical_measurement_id",
        ),
        sa.ForeignKeyConstraint(
            ["measuring_component_id"],
            ["measuring_component.id"],
            name="fk_initial_measurement_measuring_component_id",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["device.id"],
            name="fk_initial_measurement_device_id",
        ),
        sa.ForeignKeyConstraint(
            ["service_point_id"],
            ["service_point.id"],
            name="fk_initial_measurement_service_point_id",
        ),
        sa.UniqueConstraint(
            "canonical_measurement_id",
            name="uq_initial_measurement_canonical_measurement_id",
        ),
    )
    op.create_index("ix_initial_measurement_measured_at", "initial_measurement", ["measured_at"])
    op.create_index(
        "ix_initial_measurement_initial_status", "initial_measurement", ["initial_status"]
    )
    op.create_index(
        "ix_initial_measurement_service_point_id_measured_at",
        "initial_measurement",
        ["service_point_id", "measured_at"],
    )

    op.create_table(
        "vee_execution_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initial_measurement_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("execution_scope", sa.String(length=30), nullable=False),
        sa.Column("trigger_type", sa.String(length=30), nullable=False),
        sa.Column("rule_set_code", sa.String(length=60), nullable=False),
        sa.Column("period_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("summary_code", sa.String(length=60), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["initial_measurement_id"],
            ["initial_measurement.id"],
            name="fk_vee_execution_log_initial_measurement_id",
        ),
        sa.ForeignKeyConstraint(
            ["pipeline_run_id"],
            ["pipeline_run.id"],
            name="fk_vee_execution_log_pipeline_run_id",
        ),
    )
    op.create_index(
        "ix_vee_execution_log_initial_measurement_id",
        "vee_execution_log",
        ["initial_measurement_id"],
    )
    op.create_index(
        "ix_vee_execution_log_execution_status",
        "vee_execution_log",
        ["execution_status"],
    )
    op.create_index("ix_vee_execution_log_started_at", "vee_execution_log", ["started_at"])

    op.create_table(
        "vee_exception",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("initial_measurement_id", sa.Integer(), nullable=False),
        sa.Column("vee_execution_log_id", sa.Integer(), nullable=True),
        sa.Column("exception_code", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("exception_status", sa.String(length=30), nullable=False),
        sa.Column("blocking_finalization", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.String(length=120), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_type", sa.String(length=40), nullable=True),
        sa.Column("operator_memo", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["initial_measurement_id"],
            ["initial_measurement.id"],
            name="fk_vee_exception_initial_measurement_id",
        ),
        sa.ForeignKeyConstraint(
            ["vee_execution_log_id"],
            ["vee_execution_log.id"],
            name="fk_vee_exception_vee_execution_log_id",
        ),
    )
    op.create_index(
        "ix_vee_exception_initial_measurement_id",
        "vee_exception",
        ["initial_measurement_id"],
    )
    op.create_index("ix_vee_exception_exception_status", "vee_exception", ["exception_status"])
    op.create_index("ix_vee_exception_exception_code", "vee_exception", ["exception_code"])
    op.create_index("ix_vee_exception_detected_at", "vee_exception", ["detected_at"])
    op.create_index(
        "ix_vee_exception_blocking_finalization",
        "vee_exception",
        ["blocking_finalization"],
    )


def downgrade() -> None:
    op.drop_index("ix_vee_exception_blocking_finalization", table_name="vee_exception")
    op.drop_index("ix_vee_exception_detected_at", table_name="vee_exception")
    op.drop_index("ix_vee_exception_exception_code", table_name="vee_exception")
    op.drop_index("ix_vee_exception_exception_status", table_name="vee_exception")
    op.drop_index("ix_vee_exception_initial_measurement_id", table_name="vee_exception")
    op.drop_table("vee_exception")

    op.drop_index("ix_vee_execution_log_started_at", table_name="vee_execution_log")
    op.drop_index("ix_vee_execution_log_execution_status", table_name="vee_execution_log")
    op.drop_index(
        "ix_vee_execution_log_initial_measurement_id",
        table_name="vee_execution_log",
    )
    op.drop_table("vee_execution_log")

    op.drop_index(
        "ix_initial_measurement_service_point_id_measured_at",
        table_name="initial_measurement",
    )
    op.drop_index("ix_initial_measurement_initial_status", table_name="initial_measurement")
    op.drop_index("ix_initial_measurement_measured_at", table_name="initial_measurement")
    op.drop_table("initial_measurement")
