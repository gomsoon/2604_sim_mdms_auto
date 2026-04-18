from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app
from app.db import get_session
from app.migrations import upgrade_db


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    database_path = tmp_path / "test_app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    app = create_app()
    app.config.update(TESTING=True)
    upgrade_db(app.config["DATABASE_URL"])
    return app


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
