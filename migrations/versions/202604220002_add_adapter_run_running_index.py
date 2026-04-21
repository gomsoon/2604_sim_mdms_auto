"""Add partial unique index for active adapter runs.

Revision ID: 202604220002
Revises: 202604220001
Create Date: 2026-04-22 10:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202604220002"
down_revision = "202604220001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            select adapter_instance_id, count(*) as running_count
            from adapter_run
            where run_status = 'running'
            group by adapter_instance_id
            having count(*) > 1
            order by running_count desc, adapter_instance_id asc
            fetch first 1 row only
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot create uq_adapter_run_single_running_per_instance because multiple "
            f"running rows already exist for adapter_instance_id={duplicate.adapter_instance_id} "
            f"(count={duplicate.running_count})."
        )

    op.create_index(
        "uq_adapter_run_single_running_per_instance",
        "adapter_run",
        ["adapter_instance_id"],
        unique=True,
        postgresql_where=sa.text("run_status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_adapter_run_single_running_per_instance", table_name="adapter_run")
