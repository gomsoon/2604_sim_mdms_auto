from __future__ import annotations

from app.services.dashboard import build_dashboard_snapshot
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
    ]


def test_dashboard_snapshot_derives_stage_counts_from_seeded_data(session):
    seed_demo_environment(session)
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    cards = {card.title_key: card for card in snapshot.stage_cards}

    assert cards["dashboard.stage.raw_ingest"].waiting == 0
    assert cards["dashboard.stage.raw_ingest"].processing == 0
    assert cards["dashboard.stage.raw_ingest"].completed == 4
    assert cards["dashboard.stage.raw_ingest"].failed == 0

    assert cards["dashboard.stage.canonical"].waiting == 0
    assert cards["dashboard.stage.canonical"].processing == 0
    assert cards["dashboard.stage.canonical"].completed == 1
    assert cards["dashboard.stage.canonical"].failed == 2

    assert cards["dashboard.stage.errors"].waiting == 2
    assert cards["dashboard.stage.errors"].processing == 0
    assert cards["dashboard.stage.errors"].completed == 0
    assert cards["dashboard.stage.errors"].failed == 0
