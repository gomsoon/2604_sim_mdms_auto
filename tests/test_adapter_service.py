from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models import AdapterInstance, AdapterRun
from app.services.adapters import (
    AdapterValidationError,
    list_adapter_instances,
    queue_adapter_run_once,
    update_adapter_admin_state,
)
from app.services.seeds import seed_demo_environment


def test_list_adapter_instances_derives_ready_status_from_seeded_runtime(session):
    seed_demo_environment(session)
    session.commit()

    rows = list_adapter_instances(session)

    assert len(rows) == 1
    assert rows[0].instance.instance_code == "demo_hes_poll_primary"
    assert rows[0].effective_status == "ready"
    assert rows[0].latest_run is not None
    assert rows[0].latest_run.run_status == "completed"


def test_queue_adapter_run_once_allows_paused_instance(session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    update_adapter_admin_state(session, instance, "paused")
    run = queue_adapter_run_once(session, instance)
    session.commit()

    assert run.trigger_type == "manual"
    assert run.run_status == "waiting"
    assert session.scalar(select(func.count()).select_from(AdapterRun)) == 2


def test_queue_adapter_run_once_rejects_duplicate_waiting_run(session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(select(AdapterInstance).limit(1))
    assert instance is not None

    queue_adapter_run_once(session, instance)

    with pytest.raises(AdapterValidationError) as exc_info:
        queue_adapter_run_once(session, instance)

    assert exc_info.value.error_code == "run_already_pending"
