"""Add HES system registry baseline.

Revision ID: 202604220003
Revises: 202604220002
Create Date: 2026-04-22 10:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604220003"
down_revision = "202604220002"
branch_labels = None
depends_on = None


def _backfill_hes_system_rows() -> None:
    op.execute(
        """
        INSERT INTO hes_system (
            hes_code,
            display_name,
            vendor_name,
            source_family,
            default_delivery_mode,
            status,
            timezone_name,
            description,
            connection_config_masked,
            created_at,
            updated_at
        )
        SELECT
            source_rows.source_system,
            source_rows.source_system,
            NULL,
            'hes',
            NULL,
            'active',
            NULL,
            'Auto-created during HES registry baseline migration.',
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM (
            SELECT source_system FROM adapter_instance
            UNION
            SELECT source_system FROM ingest_batch
            UNION
            SELECT source_system FROM hes_read_raw
            UNION
            SELECT source_system FROM hes_event_raw
            UNION
            SELECT source_system FROM landing_lp_em_read_block
        ) AS source_rows
        WHERE source_rows.source_system IS NOT NULL
          AND btrim(source_rows.source_system) <> ''
        """
    )


def upgrade() -> None:
    op.create_table(
        "hes_system",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hes_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("vendor_name", sa.String(length=100), nullable=True),
        sa.Column("source_family", sa.String(length=50), nullable=False),
        sa.Column("default_delivery_mode", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("timezone_name", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("connection_config_masked", sa.JSON(), nullable=True),
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
        sa.UniqueConstraint("hes_code", name="uq_hes_system_hes_code"),
    )
    op.create_index("ix_hes_system_source_family", "hes_system", ["source_family"])
    op.create_index("ix_hes_system_status", "hes_system", ["status"])

    _backfill_hes_system_rows()

    with op.batch_alter_table("adapter_instance") as batch_op:
        batch_op.add_column(sa.Column("hes_system_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_adapter_instance_hes_system_id",
            "hes_system",
            ["hes_system_id"],
            ["id"],
        )
        batch_op.create_index("ix_adapter_instance_hes_system_id", ["hes_system_id"])

    op.execute(
        """
        UPDATE adapter_instance AS instance
        SET hes_system_id = hes.id
        FROM hes_system AS hes
        WHERE instance.hes_system_id IS NULL
          AND hes.hes_code = instance.source_system
        """
    )

    with op.batch_alter_table("ingest_batch") as batch_op:
        batch_op.add_column(sa.Column("hes_system_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_ingest_batch_hes_system_id",
            "hes_system",
            ["hes_system_id"],
            ["id"],
        )
        batch_op.create_index("ix_ingest_batch_hes_system_id", ["hes_system_id"])

    op.execute(
        """
        UPDATE ingest_batch AS batch
        SET hes_system_id = instance.hes_system_id
        FROM adapter_instance AS instance
        WHERE batch.hes_system_id IS NULL
          AND batch.adapter_instance_id = instance.id
          AND instance.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE ingest_batch AS batch
        SET hes_system_id = hes.id
        FROM hes_system AS hes
        WHERE batch.hes_system_id IS NULL
          AND hes.hes_code = batch.source_system
        """
    )

    with op.batch_alter_table("landing_lp_em_read_block") as batch_op:
        batch_op.add_column(sa.Column("hes_system_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_landing_lp_em_read_block_hes_system_id",
            "hes_system",
            ["hes_system_id"],
            ["id"],
        )
        batch_op.create_index("ix_landing_lp_em_read_block_hes_system_id", ["hes_system_id"])

    op.execute(
        """
        UPDATE landing_lp_em_read_block AS block
        SET hes_system_id = instance.hes_system_id
        FROM adapter_instance AS instance
        WHERE block.hes_system_id IS NULL
          AND block.adapter_instance_id = instance.id
          AND instance.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE landing_lp_em_read_block AS block
        SET hes_system_id = hes.id
        FROM hes_system AS hes
        WHERE block.hes_system_id IS NULL
          AND hes.hes_code = block.source_system
        """
    )

    with op.batch_alter_table("hes_read_raw") as batch_op:
        batch_op.add_column(sa.Column("hes_system_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_hes_read_raw_hes_system_id",
            "hes_system",
            ["hes_system_id"],
            ["id"],
        )
        batch_op.create_index("ix_hes_read_raw_hes_system_id", ["hes_system_id"])

    op.execute(
        """
        UPDATE hes_read_raw AS raw
        SET hes_system_id = instance.hes_system_id
        FROM adapter_instance AS instance
        WHERE raw.hes_system_id IS NULL
          AND raw.adapter_instance_id = instance.id
          AND instance.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE hes_read_raw AS raw
        SET hes_system_id = batch.hes_system_id
        FROM ingest_batch AS batch
        WHERE raw.hes_system_id IS NULL
          AND raw.ingest_batch_id = batch.id
          AND batch.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE hes_read_raw AS raw
        SET hes_system_id = hes.id
        FROM hes_system AS hes
        WHERE raw.hes_system_id IS NULL
          AND hes.hes_code = raw.source_system
        """
    )

    with op.batch_alter_table("hes_event_raw") as batch_op:
        batch_op.add_column(sa.Column("hes_system_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_hes_event_raw_hes_system_id",
            "hes_system",
            ["hes_system_id"],
            ["id"],
        )
        batch_op.create_index("ix_hes_event_raw_hes_system_id", ["hes_system_id"])

    op.execute(
        """
        UPDATE hes_event_raw AS event
        SET hes_system_id = batch.hes_system_id
        FROM ingest_batch AS batch
        WHERE event.hes_system_id IS NULL
          AND event.ingest_batch_id = batch.id
          AND batch.hes_system_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE hes_event_raw AS event
        SET hes_system_id = hes.id
        FROM hes_system AS hes
        WHERE event.hes_system_id IS NULL
          AND hes.hes_code = event.source_system
        """
    )


def downgrade() -> None:
    with op.batch_alter_table("hes_event_raw") as batch_op:
        batch_op.drop_index("ix_hes_event_raw_hes_system_id")
        batch_op.drop_constraint("fk_hes_event_raw_hes_system_id", type_="foreignkey")
        batch_op.drop_column("hes_system_id")

    with op.batch_alter_table("hes_read_raw") as batch_op:
        batch_op.drop_index("ix_hes_read_raw_hes_system_id")
        batch_op.drop_constraint("fk_hes_read_raw_hes_system_id", type_="foreignkey")
        batch_op.drop_column("hes_system_id")

    with op.batch_alter_table("landing_lp_em_read_block") as batch_op:
        batch_op.drop_index("ix_landing_lp_em_read_block_hes_system_id")
        batch_op.drop_constraint("fk_landing_lp_em_read_block_hes_system_id", type_="foreignkey")
        batch_op.drop_column("hes_system_id")

    with op.batch_alter_table("ingest_batch") as batch_op:
        batch_op.drop_index("ix_ingest_batch_hes_system_id")
        batch_op.drop_constraint("fk_ingest_batch_hes_system_id", type_="foreignkey")
        batch_op.drop_column("hes_system_id")

    with op.batch_alter_table("adapter_instance") as batch_op:
        batch_op.drop_index("ix_adapter_instance_hes_system_id")
        batch_op.drop_constraint("fk_adapter_instance_hes_system_id", type_="foreignkey")
        batch_op.drop_column("hes_system_id")

    op.drop_index("ix_hes_system_status", table_name="hes_system")
    op.drop_index("ix_hes_system_source_family", table_name="hes_system")
    op.drop_table("hes_system")
