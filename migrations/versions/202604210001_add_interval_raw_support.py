"""Add landing and interval-window support for interval raw reads.

Revision ID: 202604210001
Revises: 202604190004
Create Date: 2026-04-21 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604210001"
down_revision = "202604190004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "landing_lp_em_read_block",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("adapter_instance_id", sa.Integer(), nullable=False),
        sa.Column("adapter_run_id", sa.Integer(), nullable=False),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_table_name", sa.String(length=150), nullable=False),
        sa.Column("source_block_key", sa.String(length=255), nullable=False),
        sa.Column("meter_source_id", sa.String(length=100), nullable=False),
        sa.Column("device_source_id", sa.String(length=100), nullable=True),
        sa.Column("mdev_id", sa.String(length=100), nullable=True),
        sa.Column("mdev_type", sa.String(length=50), nullable=True),
        sa.Column("channel_code", sa.String(length=30), nullable=False),
        sa.Column("source_business_hour", sa.String(length=10), nullable=False),
        sa.Column("source_hour_component", sa.String(length=2), nullable=True),
        sa.Column("source_write_text", sa.String(length=14), nullable=True),
        sa.Column("source_write_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location_source_id", sa.String(length=100), nullable=True),
        sa.Column("supplier_source_id", sa.String(length=100), nullable=True),
        sa.Column("enddevice_source_id", sa.String(length=100), nullable=True),
        sa.Column("value_cnt", sa.Integer(), nullable=True),
        sa.Column("block_value", sa.Float(), nullable=True),
        sa.Column("slot_values", sa.JSON(), nullable=False),
        sa.Column("slot_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "parsed_ok",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("parse_error_code", sa.String(length=100), nullable=True),
        sa.Column("source_payload", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["adapter_instance_id"], ["adapter_instance.id"]),
        sa.ForeignKeyConstraint(["adapter_run_id"], ["adapter_run.id"]),
        sa.UniqueConstraint(
            "source_system",
            "source_block_key",
            name="uq_landing_lp_em_read_block_source_block",
        ),
    )
    op.create_index(
        "ix_landing_lp_em_read_block_adapter_instance_id",
        "landing_lp_em_read_block",
        ["adapter_instance_id"],
    )
    op.create_index(
        "ix_landing_lp_em_read_block_adapter_run_id",
        "landing_lp_em_read_block",
        ["adapter_run_id"],
    )
    op.create_index(
        "ix_landing_lp_em_read_block_meter_source_id",
        "landing_lp_em_read_block",
        ["meter_source_id"],
    )
    op.create_index(
        "ix_landing_lp_em_read_block_source_business_hour",
        "landing_lp_em_read_block",
        ["source_business_hour"],
    )
    op.create_index(
        "ix_landing_lp_em_read_block_source_system",
        "landing_lp_em_read_block",
        ["source_system"],
    )
    op.create_index(
        "ix_landing_lp_em_read_block_source_write_ts",
        "landing_lp_em_read_block",
        ["source_write_ts"],
    )
    op.create_index(
        "ix_landing_lp_em_read_block_meter_hour_channel",
        "landing_lp_em_read_block",
        ["meter_source_id", "source_business_hour", "channel_code"],
    )

    op.create_table(
        "raw_interval_window_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("meter_identifier", sa.String(length=100), nullable=False),
        sa.Column("channel_identifier", sa.String(length=30), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_size_minutes", sa.Integer(), nullable=False),
        sa.Column("interval_size_minutes", sa.Integer(), nullable=False),
        sa.Column("expected_slot_count", sa.Integer(), nullable=False),
        sa.Column(
            "received_slot_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("received_slot_bitmap", sa.String(length=256), nullable=True),
        sa.Column("first_source_write_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_source_write_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completion_status", sa.String(length=30), nullable=False),
        sa.Column(
            "late_update_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_adapter_run_id", sa.Integer(), nullable=True),
        sa.Column("last_ingest_batch_id", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["last_adapter_run_id"], ["adapter_run.id"]),
        sa.ForeignKeyConstraint(["last_ingest_batch_id"], ["ingest_batch.id"]),
        sa.UniqueConstraint(
            "source_system",
            "meter_identifier",
            "channel_identifier",
            "window_start_at",
            "window_size_minutes",
            name="uq_raw_interval_window_state_scope",
        ),
    )
    op.create_index(
        "ix_raw_interval_window_state_completion_status",
        "raw_interval_window_state",
        ["completion_status"],
    )
    op.create_index(
        "ix_raw_interval_window_state_window_start_at",
        "raw_interval_window_state",
        ["window_start_at"],
    )
    op.create_index(
        "ix_raw_interval_window_state_meter_channel_window",
        "raw_interval_window_state",
        ["meter_identifier", "channel_identifier", "window_start_at"],
    )
    op.create_index(
        "ix_raw_interval_window_state_last_source_write_ts",
        "raw_interval_window_state",
        ["last_source_write_ts"],
    )
    op.create_index(
        "ix_raw_interval_window_state_source_system",
        "raw_interval_window_state",
        ["source_system"],
    )
    op.create_index(
        "ix_raw_interval_window_state_meter_identifier",
        "raw_interval_window_state",
        ["meter_identifier"],
    )
    op.create_index(
        "ix_raw_interval_window_state_channel_identifier",
        "raw_interval_window_state",
        ["channel_identifier"],
    )

    with op.batch_alter_table("hes_read_raw") as batch_op:
        batch_op.add_column(sa.Column("adapter_instance_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("adapter_run_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("landing_lp_em_read_block_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("source_table_name", sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column("source_block_key", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("source_record_key", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("device_identifier", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("source_slot_code", sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column("source_slot_index", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("interval_end_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column(
                "interval_size_minutes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("60"),
            )
        )
        batch_op.add_column(
            sa.Column("source_business_ts", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("source_write_ts", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_foreign_key(
            "fk_hes_read_raw_adapter_instance_id",
            "adapter_instance",
            ["adapter_instance_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_hes_read_raw_adapter_run_id",
            "adapter_run",
            ["adapter_run_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_hes_read_raw_landing_lp_em_read_block_id",
            "landing_lp_em_read_block",
            ["landing_lp_em_read_block_id"],
            ["id"],
        )
        batch_op.create_index("ix_hes_read_raw_adapter_instance_id", ["adapter_instance_id"])
        batch_op.create_index("ix_hes_read_raw_adapter_run_id", ["adapter_run_id"])
        batch_op.create_index(
            "ix_hes_read_raw_landing_lp_em_read_block_id",
            ["landing_lp_em_read_block_id"],
        )
        batch_op.create_index("ix_hes_read_raw_source_write_ts", ["source_write_ts"])


def downgrade() -> None:
    with op.batch_alter_table("hes_read_raw") as batch_op:
        batch_op.drop_index("ix_hes_read_raw_source_write_ts")
        batch_op.drop_index("ix_hes_read_raw_landing_lp_em_read_block_id")
        batch_op.drop_index("ix_hes_read_raw_adapter_run_id")
        batch_op.drop_index("ix_hes_read_raw_adapter_instance_id")
        batch_op.drop_constraint(
            "fk_hes_read_raw_landing_lp_em_read_block_id", type_="foreignkey"
        )
        batch_op.drop_constraint("fk_hes_read_raw_adapter_run_id", type_="foreignkey")
        batch_op.drop_constraint("fk_hes_read_raw_adapter_instance_id", type_="foreignkey")
        batch_op.drop_column("source_write_ts")
        batch_op.drop_column("source_business_ts")
        batch_op.drop_column("interval_size_minutes")
        batch_op.drop_column("interval_end_at")
        batch_op.drop_column("source_slot_index")
        batch_op.drop_column("source_slot_code")
        batch_op.drop_column("device_identifier")
        batch_op.drop_column("source_record_key")
        batch_op.drop_column("source_block_key")
        batch_op.drop_column("source_table_name")
        batch_op.drop_column("landing_lp_em_read_block_id")
        batch_op.drop_column("adapter_run_id")
        batch_op.drop_column("adapter_instance_id")

    op.drop_index(
        "ix_raw_interval_window_state_channel_identifier",
        table_name="raw_interval_window_state",
    )
    op.drop_index(
        "ix_raw_interval_window_state_meter_identifier",
        table_name="raw_interval_window_state",
    )
    op.drop_index(
        "ix_raw_interval_window_state_source_system",
        table_name="raw_interval_window_state",
    )
    op.drop_index(
        "ix_raw_interval_window_state_last_source_write_ts",
        table_name="raw_interval_window_state",
    )
    op.drop_index(
        "ix_raw_interval_window_state_meter_channel_window",
        table_name="raw_interval_window_state",
    )
    op.drop_index(
        "ix_raw_interval_window_state_window_start_at",
        table_name="raw_interval_window_state",
    )
    op.drop_index(
        "ix_raw_interval_window_state_completion_status",
        table_name="raw_interval_window_state",
    )
    op.drop_table("raw_interval_window_state")

    op.drop_index(
        "ix_landing_lp_em_read_block_meter_hour_channel",
        table_name="landing_lp_em_read_block",
    )
    op.drop_index(
        "ix_landing_lp_em_read_block_source_write_ts",
        table_name="landing_lp_em_read_block",
    )
    op.drop_index(
        "ix_landing_lp_em_read_block_source_system",
        table_name="landing_lp_em_read_block",
    )
    op.drop_index(
        "ix_landing_lp_em_read_block_source_business_hour",
        table_name="landing_lp_em_read_block",
    )
    op.drop_index(
        "ix_landing_lp_em_read_block_meter_source_id",
        table_name="landing_lp_em_read_block",
    )
    op.drop_index(
        "ix_landing_lp_em_read_block_adapter_run_id",
        table_name="landing_lp_em_read_block",
    )
    op.drop_index(
        "ix_landing_lp_em_read_block_adapter_instance_id",
        table_name="landing_lp_em_read_block",
    )
    op.drop_table("landing_lp_em_read_block")
