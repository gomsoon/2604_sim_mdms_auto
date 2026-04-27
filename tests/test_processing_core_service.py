from __future__ import annotations

from sqlalchemy import func, select

from app.models import CanonicalMeasurement, InitialMeasurement, VeeExecutionLog
from app.services.processing_core import ensure_processing_core_lineage
from app.services.seeds import seed_demo_environment


def test_ensure_processing_core_lineage_creates_initial_measurement_and_pass_through_log(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    assert canonical is not None

    initial = ensure_processing_core_lineage(session, canonical)
    session.commit()

    log = session.scalar(
        select(VeeExecutionLog)
        .where(VeeExecutionLog.initial_measurement_id == initial.id)
        .order_by(VeeExecutionLog.id.asc())
        .limit(1)
    )

    assert initial.canonical_measurement_id == canonical.id
    assert initial.initial_status == "accepted"
    assert log is not None
    assert log.execution_status == "passed"
    assert log.summary_code == "vee_passed"


def test_ensure_processing_core_lineage_is_idempotent(session):
    seed_demo_environment(session)
    session.commit()

    canonical = session.scalar(select(CanonicalMeasurement).limit(1))
    assert canonical is not None

    ensure_processing_core_lineage(session, canonical)
    ensure_processing_core_lineage(session, canonical)
    session.commit()

    assert session.scalar(select(func.count()).select_from(InitialMeasurement)) == 1
    assert session.scalar(select(func.count()).select_from(VeeExecutionLog)) == 1
