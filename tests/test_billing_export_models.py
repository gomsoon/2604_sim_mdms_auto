from __future__ import annotations

from sqlalchemy import inspect

from app.models import BillingExportItem, BillingExportRequest


def test_billing_export_request_columns_exist():
    mapper = inspect(BillingExportRequest)

    assert "request_scope" in mapper.columns
    assert "status" in mapper.columns
    assert "source_billing_export_request_id" in mapper.columns
    assert "recovery_action_code" in mapper.columns
    assert "service_point_id" in mapper.columns
    assert "target_system_code" in mapper.columns
    assert "payload_format" in mapper.columns
    assert "item_count" in mapper.columns
    assert "processed_count" in mapper.columns
    assert "succeeded_count" in mapper.columns
    assert "failed_count" in mapper.columns
    assert "skipped_count" in mapper.columns
    assert "claimed_by" in mapper.columns
    assert "last_heartbeat_at" in mapper.columns
    assert "details" in mapper.columns


def test_billing_export_item_columns_exist():
    mapper = inspect(BillingExportItem)

    assert "billing_export_request_id" in mapper.columns
    assert "source_billing_export_item_id" in mapper.columns
    assert "service_point_id" in mapper.columns
    assert "billing_period_start_at" in mapper.columns
    assert "billing_period_end_at" in mapper.columns
    assert "currency_code" in mapper.columns
    assert "tariff_plan_code" in mapper.columns
    assert "summary_status" in mapper.columns
    assert "status" in mapper.columns
    assert "payload_snapshot" in mapper.columns
    assert "exported_at" in mapper.columns
    assert "details" in mapper.columns
