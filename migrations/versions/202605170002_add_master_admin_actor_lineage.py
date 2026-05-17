"""add master/admin actor lineage

Revision ID: 202605170002
Revises: 202605170001
Create Date: 2026-05-17 13:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "202605170002"
down_revision = "202605170001"
branch_labels = None
depends_on = None


def _add_actor_columns(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column("created_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("updated_by_user_account_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        f"fk_{table_name}_created_by_user_account",
        table_name,
        "user_account",
        ["created_by_user_account_id"],
        ["id"],
    )
    op.create_foreign_key(
        f"fk_{table_name}_updated_by_user_account",
        table_name,
        "user_account",
        ["updated_by_user_account_id"],
        ["id"],
    )
    op.create_index(
        f"ix_{table_name}_created_by_user_account_id",
        table_name,
        ["created_by_user_account_id"],
    )
    op.create_index(
        f"ix_{table_name}_updated_by_user_account_id",
        table_name,
        ["updated_by_user_account_id"],
    )


def _drop_actor_columns(table_name: str) -> None:
    op.drop_index(
        f"ix_{table_name}_updated_by_user_account_id",
        table_name=table_name,
    )
    op.drop_index(
        f"ix_{table_name}_created_by_user_account_id",
        table_name=table_name,
    )
    op.drop_constraint(
        f"fk_{table_name}_updated_by_user_account",
        table_name,
        type_="foreignkey",
    )
    op.drop_constraint(
        f"fk_{table_name}_created_by_user_account",
        table_name,
        type_="foreignkey",
    )
    op.drop_column(table_name, "updated_by_user_account_id")
    op.drop_column(table_name, "created_by_user_account_id")


def upgrade() -> None:
    for table_name in (
        "hes_system",
        "adapter_instance",
        "service_point",
        "service_point_billing_context",
        "service_point_tariff_assignment",
        "device",
        "measuring_component",
        "installation_history",
    ):
        _add_actor_columns(table_name)


def downgrade() -> None:
    for table_name in reversed(
        (
            "hes_system",
            "adapter_instance",
            "service_point",
            "service_point_billing_context",
            "service_point_tariff_assignment",
            "device",
            "measuring_component",
            "installation_history",
        )
    ):
        _drop_actor_columns(table_name)
