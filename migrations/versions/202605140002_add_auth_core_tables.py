"""Add auth core persistence tables.

Revision ID: 202605140002
Revises: 202605140001
Create Date: 2026-05-14 18:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605140002"
down_revision = "202605140001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login_id", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=150), nullable=False),
        sa.Column("role_code", sa.String(length=30), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
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
            "role_code in ('admin', 'operator')",
            name="ck_user_account_role_code",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_id"),
    )
    op.create_index("ix_user_account_role_code", "user_account", ["role_code"], unique=False)
    op.create_index("ix_user_account_is_active", "user_account", ["is_active"], unique=False)

    op.create_table(
        "auth_session_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_account_id", sa.Integer(), nullable=True),
        sa.Column("login_id_attempted", sa.String(length=120), nullable=True),
        sa.Column("auth_event_type", sa.String(length=40), nullable=False),
        sa.Column("session_identifier", sa.String(length=120), nullable=True),
        sa.Column("auth_channel", sa.String(length=30), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("result_code", sa.String(length=80), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "auth_event_type in ('login_succeeded', 'login_failed', 'logout', 'session_expired')",
            name="ck_auth_session_audit_auth_event_type",
        ),
        sa.CheckConstraint(
            "auth_channel in ('web_session', 'api_session', 'api_token')",
            name="ck_auth_session_audit_auth_channel",
        ),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_session_audit_user_account_id",
        "auth_session_audit",
        ["user_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_session_audit_login_id_attempted",
        "auth_session_audit",
        ["login_id_attempted"],
        unique=False,
    )
    op.create_index(
        "ix_auth_session_audit_auth_event_type",
        "auth_session_audit",
        ["auth_event_type"],
        unique=False,
    )
    op.create_index(
        "ix_auth_session_audit_session_identifier",
        "auth_session_audit",
        ["session_identifier"],
        unique=False,
    )
    op.create_index(
        "ix_auth_session_audit_occurred_at",
        "auth_session_audit",
        ["occurred_at"],
        unique=False,
    )

    op.create_table(
        "user_action_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_account_id", sa.Integer(), nullable=False),
        sa.Column("auth_session_audit_id", sa.Integer(), nullable=True),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("resource_type", sa.String(length=60), nullable=False),
        sa.Column("resource_id", sa.String(length=120), nullable=True),
        sa.Column("request_method", sa.String(length=16), nullable=True),
        sa.Column("request_path", sa.String(length=255), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("outcome_code", sa.String(length=60), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action_type in ('read', 'create', 'update', 'delete', 'execute', 'login', 'logout')",
            name="ck_user_action_audit_action_type",
        ),
        sa.ForeignKeyConstraint(["auth_session_audit_id"], ["auth_session_audit.id"]),
        sa.ForeignKeyConstraint(["user_account_id"], ["user_account.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_action_audit_user_account_id",
        "user_action_audit",
        ["user_account_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_action_audit_auth_session_audit_id",
        "user_action_audit",
        ["auth_session_audit_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_action_audit_action_type",
        "user_action_audit",
        ["action_type"],
        unique=False,
    )
    op.create_index(
        "ix_user_action_audit_resource_type",
        "user_action_audit",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        "ix_user_action_audit_request_path",
        "user_action_audit",
        ["request_path"],
        unique=False,
    )
    op.create_index(
        "ix_user_action_audit_outcome_code",
        "user_action_audit",
        ["outcome_code"],
        unique=False,
    )
    op.create_index(
        "ix_user_action_audit_occurred_at",
        "user_action_audit",
        ["occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_action_audit_occurred_at", table_name="user_action_audit")
    op.drop_index("ix_user_action_audit_outcome_code", table_name="user_action_audit")
    op.drop_index("ix_user_action_audit_request_path", table_name="user_action_audit")
    op.drop_index("ix_user_action_audit_resource_type", table_name="user_action_audit")
    op.drop_index("ix_user_action_audit_action_type", table_name="user_action_audit")
    op.drop_index(
        "ix_user_action_audit_auth_session_audit_id",
        table_name="user_action_audit",
    )
    op.drop_index("ix_user_action_audit_user_account_id", table_name="user_action_audit")
    op.drop_table("user_action_audit")

    op.drop_index("ix_auth_session_audit_occurred_at", table_name="auth_session_audit")
    op.drop_index(
        "ix_auth_session_audit_session_identifier",
        table_name="auth_session_audit",
    )
    op.drop_index(
        "ix_auth_session_audit_auth_event_type",
        table_name="auth_session_audit",
    )
    op.drop_index(
        "ix_auth_session_audit_login_id_attempted",
        table_name="auth_session_audit",
    )
    op.drop_index("ix_auth_session_audit_user_account_id", table_name="auth_session_audit")
    op.drop_table("auth_session_audit")

    op.drop_index("ix_user_account_is_active", table_name="user_account")
    op.drop_index("ix_user_account_role_code", table_name="user_account")
    op.drop_table("user_account")
