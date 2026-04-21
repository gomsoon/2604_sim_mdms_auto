from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import AdapterDefinition, AdapterInstance, AdapterRun
from app.services.adapters import (
    AdapterValidationError,
    create_adapter_instance,
    enqueue_scheduled_adapter_runs,
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


def test_create_adapter_instance_creates_enabled_poll_runtime(session):
    seed_demo_environment(session)
    session.commit()

    definition = session.scalar(select(AdapterDefinition).limit(1))
    assert definition is not None

    instance = create_adapter_instance(
        session,
        adapter_definition_id=str(definition.id),
        instance_code="company_hes_poll_secondary",
        display_name="Company HES Poll Secondary",
        source_system="HES",
        poll_interval_minutes="10",
        batch_size="250",
        landing_enabled=True,
        secret_ref="env://SECONDARY",
        connection_config_masked='{"host": "hes-db-2.internal"}',
    )
    session.commit()

    assert instance.id is not None
    assert instance.admin_state == "enabled"
    assert instance.landing_enabled is True
    assert instance.poll_interval_minutes == 10
    assert instance.batch_size == 250
    assert instance.secret_ref == "env://SECONDARY"
    assert instance.connection_config_masked == {"host": "hes-db-2.internal"}
    assert instance.next_run_at is not None


def test_create_adapter_instance_rejects_zero_poll_interval(session):
    seed_demo_environment(session)
    session.commit()

    definition = session.scalar(select(AdapterDefinition).limit(1))
    assert definition is not None

    with pytest.raises(AdapterValidationError) as exc_info:
        create_adapter_instance(
            session,
            adapter_definition_id=str(definition.id),
            instance_code="company_hes_poll_invalid",
            display_name="Invalid Poll Interval",
            source_system="HES",
            poll_interval_minutes="0",
            batch_size="100",
            landing_enabled=False,
            secret_ref="",
            connection_config_masked="",
        )

    assert exc_info.value.error_code == "invalid_poll_interval_minutes"


def test_create_adapter_instance_rejects_duplicate_instance_code(session):
    seed_demo_environment(session)
    session.commit()

    definition = session.scalar(select(AdapterDefinition).limit(1))
    assert definition is not None

    with pytest.raises(AdapterValidationError) as exc_info:
        create_adapter_instance(
            session,
            adapter_definition_id=str(definition.id),
            instance_code="demo_hes_poll_primary",
            display_name="Duplicate Code",
            source_system="HES",
            poll_interval_minutes="5",
            batch_size="100",
            landing_enabled=False,
            secret_ref="",
            connection_config_masked="",
        )

    assert exc_info.value.error_code == "duplicate_instance_code"


def test_enqueue_scheduled_adapter_runs_creates_waiting_schedule_run_for_due_poll_instance(session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary").limit(1)
    )
    assert instance is not None

    as_of = datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc)
    instance.next_run_at = as_of - timedelta(minutes=1)
    session.flush()

    summary = enqueue_scheduled_adapter_runs(session, as_of=as_of, limit=10)
    session.commit()

    scheduled_run = session.scalar(
        select(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance.id, AdapterRun.trigger_type == "schedule")
        .order_by(AdapterRun.id.desc())
        .limit(1)
    )

    assert summary.eligible == 1
    assert summary.enqueued == 1
    assert summary.skipped_due_to_active_run == 0
    assert len(summary.run_ids) == 1
    assert scheduled_run is not None
    assert scheduled_run.run_status == "waiting"
    assert scheduled_run.details["requested_via"] == "scheduler"


def test_enqueue_scheduled_adapter_runs_skips_instance_with_active_waiting_run(session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance).where(AdapterInstance.instance_code == "demo_hes_poll_primary").limit(1)
    )
    assert instance is not None

    as_of = datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc)
    instance.next_run_at = as_of - timedelta(minutes=1)
    session.flush()
    queue_adapter_run_once(session, instance)
    session.flush()

    summary = enqueue_scheduled_adapter_runs(session, as_of=as_of, limit=10)
    session.commit()

    schedule_run_count = session.scalar(
        select(func.count())
        .select_from(AdapterRun)
        .where(AdapterRun.adapter_instance_id == instance.id, AdapterRun.trigger_type == "schedule")
    )

    assert summary.eligible == 1
    assert summary.enqueued == 0
    assert summary.skipped_due_to_active_run == 1
    assert summary.run_ids == []
    assert schedule_run_count == 1
