from __future__ import annotations

from sqlalchemy import select

from app.models import IngestErrorLog
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
    ]


def test_dashboard_snapshot_derives_stage_counts_from_seeded_data(session):
    seed_demo_environment(session)
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    cards = {card.title_key: card for card in snapshot.stage_cards}

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
