"""Partition hes_read_raw by measured_at.

Revision ID: 202604220005
Revises: 202604220004
Create Date: 2026-04-22 15:30:00
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision = "202604220005"
down_revision = "202604220004"
branch_labels = None
depends_on = None


def _month_floor(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_month(value: datetime) -> datetime:
    if value.month == 12:
        return value.replace(year=value.year + 1, month=1)
    return value.replace(month=value.month + 1)


def _partition_name(value: datetime) -> str:
    return f"hes_read_raw_{value.year:04d}{value.month:02d}"


def _create_month_partition(start_at: datetime) -> None:
    end_at = _add_month(start_at)
    partition_name = _partition_name(start_at)
    op.execute(
        f"""
        CREATE TABLE {partition_name}
        PARTITION OF hes_read_raw
        FOR VALUES FROM ('{start_at.isoformat()}'::timestamptz) TO ('{end_at.isoformat()}'::timestamptz)
        """
    )


def upgrade() -> None:
    bind = op.get_bind()

    op.add_column(
        "hes_read_raw",
        sa.Column("duplicate_of_measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "canonical_measurement",
        sa.Column("hes_read_raw_measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ingest_error_log",
        sa.Column("hes_read_raw_measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "reprocess_request",
        sa.Column("hes_read_raw_measured_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_ingest_error_log_hes_read_raw_id",
        "ingest_error_log",
        ["hes_read_raw_id"],
    )

    op.execute(
        text(
            """
            UPDATE hes_read_raw AS raw
            SET duplicate_of_measured_at = duplicate_row.measured_at
            FROM hes_read_raw AS duplicate_row
            WHERE duplicate_row.id = raw.duplicate_of_id
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE canonical_measurement AS canonical
            SET hes_read_raw_measured_at = raw.measured_at
            FROM hes_read_raw AS raw
            WHERE raw.id = canonical.hes_read_raw_id
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE ingest_error_log AS error_log
            SET hes_read_raw_measured_at = raw.measured_at
            FROM hes_read_raw AS raw
            WHERE raw.id = error_log.hes_read_raw_id
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE reprocess_request AS request
            SET hes_read_raw_measured_at = raw.measured_at
            FROM hes_read_raw AS raw
            WHERE raw.id = request.hes_read_raw_id
            """
        )
    )

    null_canonical_count = bind.execute(
        text(
            """
            SELECT count(*)
            FROM canonical_measurement
            WHERE hes_read_raw_measured_at IS NULL
            """
        )
    ).scalar_one()
    if null_canonical_count:
        raise RuntimeError(
            "Cannot partition hes_read_raw because some canonical_measurement rows do not have "
            "a non-null hes_read_raw_measured_at value."
        )

    op.alter_column(
        "canonical_measurement",
        "hes_read_raw_measured_at",
        nullable=False,
    )

    op.drop_constraint(
        "canonical_measurement_hes_read_raw_id_fkey",
        "canonical_measurement",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ingest_error_log_hes_read_raw_id_fkey",
        "ingest_error_log",
        type_="foreignkey",
    )
    op.drop_constraint(
        "reprocess_request_hes_read_raw_id_fkey",
        "reprocess_request",
        type_="foreignkey",
    )
    op.drop_constraint(
        "hes_read_raw_duplicate_of_id_fkey",
        "hes_read_raw",
        type_="foreignkey",
    )

    op.rename_table("hes_read_raw", "hes_read_raw_legacy")

    op.create_table(
        "hes_read_raw",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("ingest_batch_id", sa.Integer(), nullable=False),
        sa.Column("hes_system_id", sa.Integer(), nullable=True),
        sa.Column("adapter_instance_id", sa.Integer(), nullable=True),
        sa.Column("adapter_run_id", sa.Integer(), nullable=True),
        sa.Column("landing_lp_em_read_block_id", sa.Integer(), nullable=True),
        sa.Column("source_system", sa.String(length=50), nullable=False),
        sa.Column("source_table_name", sa.String(length=150), nullable=True),
        sa.Column("source_block_key", sa.String(length=255), nullable=True),
        sa.Column("source_record_key", sa.String(length=255), nullable=True),
        sa.Column("meter_identifier", sa.String(length=100), nullable=True),
        sa.Column("device_identifier", sa.String(length=100), nullable=True),
        sa.Column("channel_identifier", sa.String(length=100), nullable=True),
        sa.Column("source_slot_code", sa.String(length=10), nullable=True),
        sa.Column("source_slot_index", sa.Integer(), nullable=True),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interval_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "interval_size_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
        ),
        sa.Column("reading_value", sa.Float(), nullable=True),
        sa.Column("quality_code", sa.String(length=40), nullable=True),
        sa.Column("status_code", sa.String(length=40), nullable=True),
        sa.Column("unit_of_measure", sa.String(length=20), nullable=True),
        sa.Column("source_business_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_write_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_status", sa.String(length=30), nullable=False),
        sa.Column("is_duplicate", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        sa.Column("duplicate_of_measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
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
        sa.ForeignKeyConstraint(["hes_system_id"], ["hes_system.id"], name="fk_hes_read_raw_hes_system_id"),
        sa.ForeignKeyConstraint(
            ["adapter_instance_id"],
            ["adapter_instance.id"],
            name="fk_hes_read_raw_adapter_instance_id",
        ),
        sa.ForeignKeyConstraint(
            ["adapter_run_id"],
            ["adapter_run.id"],
            name="fk_hes_read_raw_adapter_run_id",
        ),
        sa.ForeignKeyConstraint(
            ["landing_lp_em_read_block_id"],
            ["landing_lp_em_read_block.id"],
            name="fk_hes_read_raw_landing_lp_em_read_block_id",
        ),
        sa.UniqueConstraint("id", "measured_at", name="uq_hes_read_raw_id_measured_at"),
        postgresql_partition_by="RANGE (measured_at)",
    )

    op.execute("CREATE TABLE hes_read_raw_default PARTITION OF hes_read_raw DEFAULT")

    month_range = bind.execute(
        text(
            """
            SELECT min(measured_at) AS min_measured_at, max(measured_at) AS max_measured_at
            FROM hes_read_raw_legacy
            WHERE measured_at IS NOT NULL
            """
        )
    ).mappings().one()

    if month_range["min_measured_at"] is None or month_range["max_measured_at"] is None:
        current_month = _month_floor(datetime.now(timezone.utc))
        month_starts = [current_month, _add_month(current_month)]
    else:
        start_at = _month_floor(month_range["min_measured_at"])
        end_at = _month_floor(month_range["max_measured_at"])
        month_starts = []
        current = start_at
        while current <= end_at:
            month_starts.append(current)
            current = _add_month(current)

    for month_start in month_starts:
        _create_month_partition(month_start)

    op.execute(
        text(
            """
            INSERT INTO hes_read_raw (
                id,
                ingest_batch_id,
                hes_system_id,
                adapter_instance_id,
                adapter_run_id,
                landing_lp_em_read_block_id,
                source_system,
                source_table_name,
                source_block_key,
                source_record_key,
                meter_identifier,
                device_identifier,
                channel_identifier,
                source_slot_code,
                source_slot_index,
                measured_at,
                interval_end_at,
                interval_size_minutes,
                reading_value,
                quality_code,
                status_code,
                unit_of_measure,
                source_business_ts,
                source_write_ts,
                received_at,
                canonical_status,
                is_duplicate,
                duplicate_of_id,
                duplicate_of_measured_at,
                payload,
                created_at,
                updated_at
            )
            SELECT
                id,
                ingest_batch_id,
                hes_system_id,
                adapter_instance_id,
                adapter_run_id,
                landing_lp_em_read_block_id,
                source_system,
                source_table_name,
                source_block_key,
                source_record_key,
                meter_identifier,
                device_identifier,
                channel_identifier,
                source_slot_code,
                source_slot_index,
                measured_at,
                interval_end_at,
                interval_size_minutes,
                reading_value,
                quality_code,
                status_code,
                unit_of_measure,
                source_business_ts,
                source_write_ts,
                received_at,
                canonical_status,
                is_duplicate,
                duplicate_of_id,
                duplicate_of_measured_at,
                payload,
                created_at,
                updated_at
            FROM hes_read_raw_legacy
            """
        )
    )

    op.execute(
        text(
            """
            SELECT setval(
                pg_get_serial_sequence('hes_read_raw', 'id'),
                COALESCE((SELECT max(id) FROM hes_read_raw), 1),
                true
            )
            """
        )
    )

    op.drop_table("hes_read_raw_legacy")

    op.create_index("ix_hes_read_raw_id", "hes_read_raw", ["id"])
    op.create_index("ix_hes_read_raw_source_system", "hes_read_raw", ["source_system"])
    op.create_index("ix_hes_read_raw_meter_identifier", "hes_read_raw", ["meter_identifier"])
    op.create_index("ix_hes_read_raw_channel_identifier", "hes_read_raw", ["channel_identifier"])
    op.create_index("ix_hes_read_raw_measured_at", "hes_read_raw", ["measured_at"])
    op.create_index("ix_hes_read_raw_hes_system_id", "hes_read_raw", ["hes_system_id"])
    op.create_index("ix_hes_read_raw_adapter_instance_id", "hes_read_raw", ["adapter_instance_id"])
    op.create_index("ix_hes_read_raw_adapter_run_id", "hes_read_raw", ["adapter_run_id"])
    op.create_index(
        "ix_hes_read_raw_landing_lp_em_read_block_id",
        "hes_read_raw",
        ["landing_lp_em_read_block_id"],
    )
    op.create_index("ix_hes_read_raw_source_write_ts", "hes_read_raw", ["source_write_ts"])
    op.create_index(
        "ix_hes_read_raw_source_record_key_scope",
        "hes_read_raw",
        ["source_system", "source_record_key"],
    )
    op.create_index(
        "ix_hes_read_raw_source_meter_channel_measured_at",
        "hes_read_raw",
        ["source_system", "meter_identifier", "channel_identifier", "measured_at"],
    )

    op.create_foreign_key(
        "fk_hes_read_raw_duplicate_of",
        "hes_read_raw",
        "hes_read_raw",
        ["duplicate_of_id", "duplicate_of_measured_at"],
        ["id", "measured_at"],
    )
    op.create_foreign_key(
        "fk_canonical_measurement_hes_read_raw_identity",
        "canonical_measurement",
        "hes_read_raw",
        ["hes_read_raw_id", "hes_read_raw_measured_at"],
        ["id", "measured_at"],
    )
    op.create_index(
        "ix_canonical_measurement_hes_read_raw_identity",
        "canonical_measurement",
        ["hes_read_raw_id", "hes_read_raw_measured_at"],
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade is not supported for the hes_read_raw partitioning migration."
    )
