from __future__ import annotations

from pathlib import Path

import pytest

from app import create_app


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    database_path = tmp_path / "test_app.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(app):
    return app.test_client()

