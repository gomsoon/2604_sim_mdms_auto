from __future__ import annotations

from sqlalchemy import inspect

from app.models import BillDeterminant


def test_bill_determinant_revision_columns_exist():
    mapper = inspect(BillDeterminant)

    assert "determinant_type" in mapper.columns
    assert "revision_number" in mapper.columns
    assert "revision_reason_code" in mapper.columns
    assert "is_current" in mapper.columns
    assert "supersedes_bill_determinant_id" in mapper.columns
