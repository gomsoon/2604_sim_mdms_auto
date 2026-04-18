from __future__ import annotations

from unittest.mock import Mock

import app.blueprints.api as api_blueprint


def test_health_check_reports_database_up(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "database": "up"}


def test_health_check_reports_database_down(client, monkeypatch):
    checker = Mock(side_effect=RuntimeError("database unavailable"))
    monkeypatch.setattr(api_blueprint, "check_database_connection", checker)

    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.get_json()["status"] == "degraded"
    assert response.get_json()["database"] == "down"
    assert "database unavailable" in response.get_json()["error"]

