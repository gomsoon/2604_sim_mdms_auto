from __future__ import annotations

from sqlalchemy import inspect

from app.models import ServicePoint, ServicePointTariffAssignment


def test_service_point_tariff_assignment_columns_exist():
    mapper = inspect(ServicePointTariffAssignment)

    assert "service_point_id" in mapper.columns
    assert "tariff_plan_code" in mapper.columns
    assert "tariff_version_code" in mapper.columns
    assert "effective_from" in mapper.columns
    assert "effective_to" in mapper.columns
    assert "is_current" in mapper.columns
    assert "source_system" in mapper.columns
    assert "source_reference" in mapper.columns
    assert "details" in mapper.columns


def test_service_point_has_tariff_assignment_relationship():
    mapper = inspect(ServicePoint)

    assert "tariff_assignment_rows" in mapper.relationships
