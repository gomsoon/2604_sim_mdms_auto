from __future__ import annotations

from sqlalchemy import inspect

from app.models import ServicePoint, ServicePointBillingContext


def test_service_point_billing_context_columns_exist():
    mapper = inspect(ServicePointBillingContext)

    assert "service_point_id" in mapper.columns
    assert "timezone_name" in mapper.columns
    assert "billing_cycle_mode" in mapper.columns
    assert "billing_cycle_anchor_day" in mapper.columns
    assert "currency_code" in mapper.columns
    assert "effective_from" in mapper.columns
    assert "effective_to" in mapper.columns
    assert "is_current" in mapper.columns
    assert "source_system" in mapper.columns
    assert "source_reference" in mapper.columns
    assert "details" in mapper.columns


def test_service_point_has_billing_context_relationship():
    mapper = inspect(ServicePoint)

    assert "billing_context_rows" in mapper.relationships
