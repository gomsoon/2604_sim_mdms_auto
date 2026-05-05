"""Add estimation_audit persistence baseline.

Revision ID: 202605050002
Revises: 202605050001
Create Date: 2026-05-05 16:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605050002"
down_revision = "202605050001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "estimation_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("target_initial_measurement_id", sa.Integer(), nullable=False),
        sa.Column("target_measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy_code", sa.String(length=40), nullable=False),
        sa.Column("estimation_status", sa.String(length=30), nullable=False),
        sa.Column("estimated_value", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=True),
        sa.Column("source_previous_final_measurement_id", sa.Integer(), nullable=True),
        sa.Column("source_next_final_measurement_id", sa.Integer(), nullable=True),
        sa.Column("superseded_final_measurement_id", sa.Integer(), nullable=True),
        sa.Column("result_final_measurement_id", sa.Integer(), nullable=True),
        sa.Column("operator_memo", sa.Text(), nullable=True),
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
            "strategy_code in ('linear_interpolation', 'previous_value_based')",
            name="ck_estimation_audit_strategy_code",
        ),
        sa.CheckConstraint(
            "estimation_status in ('applied', 'blocked', 'failed')",
            name="ck_estimation_audit_estimation_status",
        ),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_run.id"]),
        sa.ForeignKeyConstraint(["service_point_id"], ["service_point.id"]),
        sa.ForeignKeyConstraint(["measuring_component_id"], ["measuring_component.id"]),
        sa.ForeignKeyConstraint(["device_id"], ["device.id"]),
        sa.ForeignKeyConstraint(
            ["target_initial_measurement_id"],
            ["initial_measurement.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_previous_final_measurement_id"],
            ["final_measurement.id"],
        ),
        sa.ForeignKeyConstraint(
            ["source_next_final_measurement_id"],
            ["final_measurement.id"],
        ),
        sa.ForeignKeyConstraint(
            ["superseded_final_measurement_id"],
            ["final_measurement.id"],
        ),
        sa.ForeignKeyConstraint(
            ["result_final_measurement_id"],
            ["final_measurement.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_estimation_audit_target_initial_measurement_id",
        "estimation_audit",
        ["target_initial_measurement_id"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_target_measured_at",
        "estimation_audit",
        ["target_measured_at"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_estimation_status",
        "estimation_audit",
        ["estimation_status"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_strategy_code",
        "estimation_audit",
        ["strategy_code"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_service_point_target_measured_at",
        "estimation_audit",
        ["service_point_id", "target_measured_at"],
        unique=False,
    )
    op.create_index(
        "ix_estimation_audit_pipeline_run_id",
        "estimation_audit",
        ["pipeline_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_estimation_audit_pipeline_run_id", table_name="estimation_audit")
    op.drop_index(
        "ix_estimation_audit_service_point_target_measured_at",
        table_name="estimation_audit",
    )
    op.drop_index("ix_estimation_audit_strategy_code", table_name="estimation_audit")
    op.drop_index("ix_estimation_audit_estimation_status", table_name="estimation_audit")
    op.drop_index("ix_estimation_audit_target_measured_at", table_name="estimation_audit")
    op.drop_index(
        "ix_estimation_audit_target_initial_measurement_id",
        table_name="estimation_audit",
    )
    op.drop_table("estimation_audit")
