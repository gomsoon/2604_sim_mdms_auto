from __future__ import annotations

from sqlalchemy import inspect

from app.models import BillCharge


def test_bill_charge_revision_columns_exist():
    mapper = inspect(BillCharge)

    assert "bill_determinant_id" in mapper.columns
    assert "charge_type" in mapper.columns
    assert "revision_number" in mapper.columns
    assert "revision_reason_code" in mapper.columns
    assert "is_current" in mapper.columns
    assert "supersedes_bill_charge_id" in mapper.columns
