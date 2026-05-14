from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from app import create_app
from app.db import get_engine, get_session
from app.migrations import upgrade_db
from app.models import AuthSessionAudit
from app.services.auth import (
    AUTH_ROLE_CODE_SESSION_KEY,
    AUTH_SESSION_AUDIT_ID_SESSION_KEY,
    AUTH_SESSION_IDENTIFIER_SESSION_KEY,
    AUTH_USER_ID_SESSION_KEY,
    create_user_account,
)
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from postgresql_support import (  # noqa: E402
    build_schema_name,
    build_schema_url,
    create_schema,
    drop_schema,
    resolve_test_database_url,
)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return resolve_test_database_url()


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, test_database_url: str):
    schema_name = build_schema_name()
    schema_url = build_schema_url(test_database_url, schema_name)
    create_schema(test_database_url, schema_name)

    monkeypatch.setenv("TEST_DATABASE_URL", test_database_url)
    monkeypatch.setenv("DATABASE_URL", schema_url)
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    app = create_app()
    app.config.update(TESTING=True)
    upgrade_db(schema_url)

    try:
        yield app
    finally:
        get_session().remove()
        drop_schema(test_database_url, schema_name)


@pytest.fixture
def anonymous_client(app, session):
    client = app.test_client()
    original_open = client.open

    def open_and_expire(*args, **kwargs):
        response = original_open(*args, **kwargs)
        session.expire_all()
        return response

    client.open = open_and_expire  # type: ignore[method-assign]
    return client


def _create_authenticated_client(app, session, *, login_id: str, display_name: str, role_code: str):
    user_account = create_user_account(
        session,
        login_id=login_id,
        display_name=display_name,
        role_code=role_code,
        password="test-password",
    )
    auth_session_audit = AuthSessionAudit(
        user_account_id=user_account.id,
        login_id_attempted=user_account.login_id,
        auth_event_type="login_succeeded",
        session_identifier=f"test-session-{role_code}-{user_account.id}",
        auth_channel="web_session",
        result_code="login_succeeded",
        details={"seeded_for_test": True},
        occurred_at=datetime.now(timezone.utc),
    )
    session.add(auth_session_audit)
    session.commit()

    client = app.test_client()
    original_open = client.open

    def open_and_expire(*args, **kwargs):
        response = original_open(*args, **kwargs)
        session.expire_all()
        return response

    client.open = open_and_expire  # type: ignore[method-assign]
    with client.session_transaction() as browser_session:
        browser_session[AUTH_USER_ID_SESSION_KEY] = user_account.id
        browser_session[AUTH_ROLE_CODE_SESSION_KEY] = user_account.role_code
        browser_session[AUTH_SESSION_IDENTIFIER_SESSION_KEY] = auth_session_audit.session_identifier
        browser_session[AUTH_SESSION_AUDIT_ID_SESSION_KEY] = auth_session_audit.id
    return client


@pytest.fixture
def client(app, session):
    return _create_authenticated_client(
        app,
        session,
        login_id="admin",
        display_name="Test Admin",
        role_code="admin",
    )


@pytest.fixture
def operator_client(app, session):
    return _create_authenticated_client(
        app,
        session,
        login_id="operator",
        display_name="Test Operator",
        role_code="operator",
    )


@pytest.fixture
def session(app):
    test_session = sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )()
    original_test_cli_runner = app.test_cli_runner

    def wrapped_test_cli_runner(*args, **kwargs):
        runner = original_test_cli_runner(*args, **kwargs)
        original_invoke = runner.invoke

        def invoke_and_expire(*invoke_args, **invoke_kwargs):
            result = original_invoke(*invoke_args, **invoke_kwargs)
            test_session.expire_all()
            return result

        runner.invoke = invoke_and_expire  # type: ignore[method-assign]
        return runner

    app.test_cli_runner = wrapped_test_cli_runner  # type: ignore[method-assign]
    try:
        yield test_session
    finally:
        test_session.close()
