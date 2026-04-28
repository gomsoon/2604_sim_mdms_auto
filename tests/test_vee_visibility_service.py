from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import HesSystem, InitialMeasurement, VeeException
from app.services.seeds import seed_demo_environment
from app.services.vee import evaluate_or_get_vee_baseline
from app.services.visibility import (
    VisibilityFilterError,
    build_vee_exception_filters,
    get_vee_exception_detail_context,
    list_vee_exceptions,
)


def _create_open_vee_exception(session) -> VeeException:
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None

    for row in list(initial.vee_exceptions):
        session.delete(row)
    for row in list(initial.vee_execution_logs):
        session.delete(row)
    initial.initial_status = "ready"
    initial.unit_of_measure = ""
    session.flush()

    evaluate_or_get_vee_baseline(session, initial)
    session.commit()

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert vee_exception is not None
    return vee_exception


def test_build_vee_exception_filters_rejects_invalid_status():
    with pytest.raises(VisibilityFilterError) as exc_info:
        build_vee_exception_filters({"exception_status": "closed"})

    assert exc_info.value.error_code == "invalid_vee_exception_status"


def test_list_vee_exceptions_filters_by_hes_and_status(session):
    vee_exception = _create_open_vee_exception(session)
    demo_hes = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    assert demo_hes is not None

    rows = list_vee_exceptions(
        session,
        build_vee_exception_filters(
            {
                "hes_system_id": str(demo_hes.id),
                "exception_status": "open",
                "meter_id": "MTR-1001",
            }
        ),
    )

    assert len(rows) == 1
    assert rows[0].id == vee_exception.id
    assert rows[0].initial_measurement.canonical_measurement.hes_read_raw.hes_system_id == demo_hes.id


def test_get_vee_exception_detail_context_returns_lineage(session):
    vee_exception = _create_open_vee_exception(session)

    detail = get_vee_exception_detail_context(session, vee_exception.id)

    assert detail is not None
    assert detail.vee_exception.id == vee_exception.id
    assert detail.raw_row is not None
    assert detail.raw_row.meter_identifier == "MTR-1001"
    assert detail.ingest_batch is not None
    assert detail.ingest_batch.batch_id == "demo-read-batch"
    assert detail.vee_execution_log is not None
