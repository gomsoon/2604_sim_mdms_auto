from __future__ import annotations

from sqlalchemy import inspect

from app.models import FinalMeasurement


def test_final_measurement_revision_columns_exist():
    mapper = inspect(FinalMeasurement)

    assert "revision_number" in mapper.columns
    assert "revision_reason_code" in mapper.columns
    assert "is_current" in mapper.columns
    assert "supersedes_final_measurement_id" in mapper.columns
