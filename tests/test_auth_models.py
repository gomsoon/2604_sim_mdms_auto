from __future__ import annotations

from sqlalchemy import inspect

from app.models import AuthSessionAudit, UserAccount, UserActionAudit


def test_user_account_columns_exist():
    mapper = inspect(UserAccount)

    assert "login_id" in mapper.columns
    assert "password_hash" in mapper.columns
    assert "display_name" in mapper.columns
    assert "role_code" in mapper.columns
    assert "is_active" in mapper.columns
    assert "last_login_at" in mapper.columns
    assert "password_changed_at" in mapper.columns
    assert "details" in mapper.columns


def test_auth_session_audit_columns_exist():
    mapper = inspect(AuthSessionAudit)

    assert "user_account_id" in mapper.columns
    assert "login_id_attempted" in mapper.columns
    assert "auth_event_type" in mapper.columns
    assert "session_identifier" in mapper.columns
    assert "auth_channel" in mapper.columns
    assert "ip_address" in mapper.columns
    assert "user_agent" in mapper.columns
    assert "result_code" in mapper.columns
    assert "details" in mapper.columns
    assert "occurred_at" in mapper.columns


def test_user_action_audit_columns_exist():
    mapper = inspect(UserActionAudit)

    assert "user_account_id" in mapper.columns
    assert "auth_session_audit_id" in mapper.columns
    assert "action_type" in mapper.columns
    assert "resource_type" in mapper.columns
    assert "resource_id" in mapper.columns
    assert "request_method" in mapper.columns
    assert "request_path" in mapper.columns
    assert "status_code" in mapper.columns
    assert "outcome_code" in mapper.columns
    assert "ip_address" in mapper.columns
    assert "user_agent" in mapper.columns
    assert "details" in mapper.columns
    assert "occurred_at" in mapper.columns


def test_auth_model_relationships_exist():
    user_mapper = inspect(UserAccount)
    auth_session_mapper = inspect(AuthSessionAudit)

    assert "auth_session_audits" in user_mapper.relationships
    assert "user_action_audits" in user_mapper.relationships
    assert "user_account" in auth_session_mapper.relationships
    assert "user_action_audits" in auth_session_mapper.relationships
