"""Add manual_edit_audit persistence baseline.

Revision ID: 202605050003
Revises: 202605050002
Create Date: 2026-05-05 23:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605050003"
down_revision = "202605050002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_edit_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("pipeline_run_id", sa.Integer(), nullable=True),
        sa.Column("service_point_id", sa.Integer(), nullable=False),
        sa.Column("measuring_component_id", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.Integer(), nullable=False),
        sa.Column("target_initial_measurement_id", sa.Integer(), nullable=False),
        sa.Column("related_vee_exception_id", sa.Integer(), nullable=False),
        sa.Column("target_measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason_code", sa.String(length=60), nullable=False),
        sa.Column("edit_status", sa.String(length=30), nullable=False),
        sa.Column("edited_value", sa.Numeric(precision=19, scale=4), nullable=True),
        sa.Column("edited_quality_code", sa.String(length=40), nullable=True),
        sa.Column("edited_status_code", sa.String(length=40), nullable=True),
        sa.Column("edited_by", sa.String(length=120), nullable=False),
        sa.Column("operator_memo", sa.Text(), nullable=True),
        sa.Column("superseded_final_measurement_id", sa.Integer(), nullable=True),
        sa.Column("result_final_measurement_id", sa.Integer(), nullable=True),
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
            "edit_status in ('applied', 'blocked', 'failed')",
            name="ck_manual_edit_audit_edit_status",
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
            ["related_vee_exception_id"],
            ["vee_exception.id"],
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
        "ix_manual_edit_audit_target_initial_measurement_id",
        "manual_edit_audit",
        ["target_initial_measurement_id"],
        unique=False,
    )
    op.create_index(
        "ix_manual_edit_audit_related_vee_exception_id",
        "manual_edit_audit",
        ["related_vee_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_manual_edit_audit_target_measured_at",
        "manual_edit_audit",
        ["target_measured_at"],
        unique=False,
    )
    op.create_index(
        "ix_manual_edit_audit_edit_status",
        "manual_edit_audit",
        ["edit_status"],
        unique=False,
    )
    op.create_index(
        "ix_manual_edit_audit_reason_code",
        "manual_edit_audit",
        ["reason_code"],
        unique=False,
    )
    op.create_index(
        "ix_manual_edit_audit_service_point_target_measured_at",
        "manual_edit_audit",
        ["service_point_id", "target_measured_at"],
        unique=False,
    )
    op.create_index(
        "ix_manual_edit_audit_pipeline_run_id",
        "manual_edit_audit",
        ["pipeline_run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_manual_edit_audit_pipeline_run_id", table_name="manual_edit_audit")
    op.drop_index(
        "ix_manual_edit_audit_service_point_target_measured_at",
        table_name="manual_edit_audit",
    )
    op.drop_index("ix_manual_edit_audit_reason_code", table_name="manual_edit_audit")
    op.drop_index("ix_manual_edit_audit_edit_status", table_name="manual_edit_audit")
    op.drop_index("ix_manual_edit_audit_target_measured_at", table_name="manual_edit_audit")
    op.drop_index(
        "ix_manual_edit_audit_related_vee_exception_id",
        table_name="manual_edit_audit",
    )
    op.drop_index(
        "ix_manual_edit_audit_target_initial_measurement_id",
        table_name="manual_edit_audit",
    )
    op.drop_table("manual_edit_audit")
