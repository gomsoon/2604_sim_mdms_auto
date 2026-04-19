from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app import create_app
from app.db import get_session
from app.migrations import upgrade_db
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
def client(app):
    return app.test_client()


@pytest.fixture
def session(app):
    scoped_session = get_session()
    try:
        yield scoped_session
    finally:
        scoped_session.remove()
