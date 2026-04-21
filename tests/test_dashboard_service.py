from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AdapterInstance, AdapterRun, IngestErrorLog
from app.services.dashboard import build_dashboard_snapshot
from app.services.exception_queue import reprocess_exception
from app.services.finalization import finalize_canonical_measurements
from app.services.seeds import seed_demo_environment


def test_dashboard_snapshot_returns_zero_stage_counts_without_data(session):
    snapshot = build_dashboard_snapshot(session)

    assert snapshot.stats["raw_reads"] == 0
    assert snapshot.stats["raw_events"] == 0
    assert snapshot.stats["exceptions"] == 0
    assert [(card.waiting, card.processing, card.completed, card.failed) for card in snapshot.stage_cards] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
    ]


def test_dashboard_snapshot_derives_stage_counts_from_seeded_data(session):
    seed_demo_environment(session)
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    cards = {card.title_key: card for card in snapshot.stage_cards}

    assert cards["dashboard.stage.integration"].waiting == 1
    assert cards["dashboard.stage.integration"].processing == 0
    assert cards["dashboard.stage.integration"].completed == 0
    assert cards["dashboard.stage.integration"].failed == 0
    assert cards["dashboard.stage.integration"].detail_endpoint == "web.adapters"
    assert cards["dashboard.stage.integration"].summary_rows[0].is_datetime is True
    assert cards["dashboard.stage.integration"].summary_rows[1].value == 0

    assert cards["dashboard.stage.raw_ingest"].waiting == 0
    assert cards["dashboard.stage.raw_ingest"].processing == 0
    assert cards["dashboard.stage.raw_ingest"].completed == 2
    assert cards["dashboard.stage.raw_ingest"].failed == 0

    assert cards["dashboard.stage.canonical"].waiting == 0
    assert cards["dashboard.stage.canonical"].processing == 0
    assert cards["dashboard.stage.canonical"].completed == 0
    assert cards["dashboard.stage.canonical"].failed == 1

    assert cards["dashboard.stage.errors"].waiting == 2
    assert cards["dashboard.stage.errors"].processing == 0
    assert cards["dashboard.stage.errors"].completed == 0
    assert cards["dashboard.stage.errors"].failed == 0

    assert cards["dashboard.stage.final"].waiting == 1
    assert cards["dashboard.stage.final"].processing == 0
    assert cards["dashboard.stage.final"].completed == 0
    assert cards["dashboard.stage.final"].failed == 0


def test_dashboard_snapshot_reflects_failed_reprocess_pipeline_runs(session):
    seed_demo_environment(session)
    session.commit()

    mapping_error = session.scalar(
        select(IngestErrorLog)
        .where(IngestErrorLog.exception_code == "measuring_component_not_found")
        .limit(1)
    )
    assert mapping_error is not None

    reprocess_exception(session, mapping_error)
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    cards = {card.title_key: card for card in snapshot.stage_cards}

    assert cards["dashboard.stage.errors"].waiting == 1
    assert cards["dashboard.stage.errors"].processing == 0
    assert cards["dashboard.stage.errors"].completed == 0
    assert cards["dashboard.stage.errors"].failed == 1


def test_dashboard_snapshot_reflects_finalization_pipeline_runs(session):
    seed_demo_environment(session)
    session.commit()

    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    cards = {card.title_key: card for card in snapshot.stage_cards}

    assert cards["dashboard.stage.final"].waiting == 0
    assert cards["dashboard.stage.final"].processing == 0
    assert cards["dashboard.stage.final"].completed == 1
    assert cards["dashboard.stage.final"].failed == 0


def test_dashboard_snapshot_derives_integration_card_from_adapter_runtime_states(session):
    seed_demo_environment(session)
    session.commit()

    ready_instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    assert ready_instance is not None

    paused_instance = AdapterInstance(
        adapter_definition_id=ready_instance.adapter_definition_id,
        instance_code="demo_hes_poll_paused",
        display_name="Demo HES Poll Paused",
        source_system="HES",
        admin_state="paused",
        poll_interval_minutes=5,
        landing_enabled=False,
    )
    running_instance = AdapterInstance(
        adapter_definition_id=ready_instance.adapter_definition_id,
        instance_code="demo_hes_poll_running",
        display_name="Demo HES Poll Running",
        source_system="HES",
        admin_state="enabled",
        poll_interval_minutes=5,
        landing_enabled=False,
    )
    error_instance = AdapterInstance(
        adapter_definition_id=ready_instance.adapter_definition_id,
        instance_code="demo_hes_poll_error",
        display_name="Demo HES Poll Error",
        source_system="HES",
        admin_state="enabled",
        poll_interval_minutes=5,
        landing_enabled=False,
        last_success_at=datetime.now(timezone.utc) - timedelta(hours=2),
        last_failure_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    session.add_all([paused_instance, running_instance, error_instance])
    session.flush()

    session.add(
        AdapterRun(
            adapter_instance_id=running_instance.id,
            trigger_type="manual",
            run_status="running",
            requested_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            details={"requested_via": "test"},
        )
    )
    session.add(
        AdapterRun(
            adapter_instance_id=paused_instance.id,
            trigger_type="manual",
            run_status="waiting",
            requested_at=datetime.now(timezone.utc),
            details={"requested_via": "test"},
        )
    )
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    card = {row.title_key: row for row in snapshot.stage_cards}["dashboard.stage.integration"]

    assert card.waiting == 1
    assert card.processing == 1
    assert card.completed == 1
    assert card.failed == 1
    assert card.summary_rows[1].value == 1
