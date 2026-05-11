from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import (
    AdapterInstance,
    BillDeterminant,
    AdapterRun,
    EstimationAudit,
    HesSystem,
    IngestBatch,
    IngestErrorLog,
    InitialMeasurement,
    ManualEditAudit,
    OperationalEvent,
    VeeException,
    VeeReplayRequest,
)
from app.services.dashboard import build_dashboard_snapshot
from app.services.bill_determinants import calculate_bill_determinants
from app.services.exception_queue import reprocess_exception
from app.services.finalization import finalize_canonical_measurements
from app.services.processing_replay import reevaluate_vee_exception_and_replay
from app.services.seeds import seed_demo_environment
from app.services.usage import calculate_usage_transactions
from app.services.vee import evaluate_or_get_vee_baseline


def test_dashboard_snapshot_returns_zero_stage_counts_without_data(session):
    snapshot = build_dashboard_snapshot(session)

    assert snapshot.stats["raw_reads"] == 0
    assert snapshot.stats["raw_events"] == 0
    assert snapshot.stats["exceptions"] == 0
    assert snapshot.stats["open_alerts"] == 0
    assert snapshot.open_alerts == []
    assert snapshot.recent_events == []
    assert snapshot.recent_recalculated_usage == []
    assert snapshot.recent_vee_replay_requests == []
    assert snapshot.recent_correction_audits == []
    assert [row.count for row in snapshot.correction_policy_spotlight] == [0, 0, 0]
    assert [(card.waiting, card.processing, card.completed, card.failed) for card in snapshot.stage_cards] == [
        (0, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
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
    assert cards["dashboard.stage.usage"].waiting == 0
    assert cards["dashboard.stage.usage"].processing == 0
    assert cards["dashboard.stage.usage"].completed == 0
    assert cards["dashboard.stage.usage"].failed == 0
    assert cards["dashboard.stage.bill_determinant"].waiting == 0
    assert cards["dashboard.stage.bill_determinant"].processing == 0
    assert cards["dashboard.stage.bill_determinant"].completed == 0
    assert cards["dashboard.stage.bill_determinant"].failed == 0
    assert cards["dashboard.stage.vee_replay"].waiting == 0
    assert cards["dashboard.stage.vee_replay"].processing == 0
    assert cards["dashboard.stage.vee_replay"].completed == 0
    assert cards["dashboard.stage.vee_replay"].failed == 0
    assert snapshot.stats["open_alerts"] == 1
    assert snapshot.open_alerts[0].event_code == "canonical_failed"
    assert len(snapshot.recent_events) >= 5
    assert snapshot.recent_recalculated_usage == []


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
    assert snapshot.stats["open_alerts"] == 2
    assert {row.event_code for row in snapshot.open_alerts} >= {
        "canonical_failed",
        "exception_reprocess_failed",
    }


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
    assert any(row.event_code == "finalization_completed" for row in snapshot.recent_events)


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


def test_dashboard_snapshot_summarizes_overdue_and_stale_adapter_counts(session):
    seed_demo_environment(session)
    session.commit()

    instance = session.scalar(
        select(AdapterInstance)
        .where(AdapterInstance.instance_code == "demo_hes_poll_primary")
        .limit(1)
    )
    assert instance is not None

    reference_time = datetime.now(timezone.utc)
    instance.next_run_at = reference_time - timedelta(minutes=10)
    instance.last_heartbeat_at = reference_time - timedelta(minutes=20)
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    card = {row.title_key: row for row in snapshot.stage_cards}["dashboard.stage.integration"]
    summary = {row.label_key: row.value for row in card.summary_rows}

    assert summary["dashboard.integration.overdue_adapters"] == 1
    assert summary["dashboard.integration.stale_adapters"] == 1


def test_dashboard_snapshot_lists_open_alerts_and_recent_events_in_time_order(session):
    seed_demo_environment(session)
    session.commit()

    later_event = OperationalEvent(
        occurred_at=datetime.now(timezone.utc),
        source_layer="system",
        event_category="system_health",
        event_code="test_event",
        severity="warning",
        is_alert=True,
        alert_status="open",
        opened_at=datetime.now(timezone.utc),
        title_en="Test event",
        title_ko="테스트 이벤트",
        message_en="A test event was recorded.",
        message_ko="테스트 이벤트가 기록되었습니다.",
        details={},
    )
    session.add(later_event)
    session.commit()

    snapshot = build_dashboard_snapshot(session)

    assert snapshot.open_alerts[0].id == later_event.id
    assert snapshot.recent_events[0].id == later_event.id


def test_dashboard_snapshot_includes_usage_spotlight_after_revee(session):
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

    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="daily_consumption")
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()

    vee_exception = session.scalar(
        select(VeeException)
        .where(VeeException.initial_measurement_id == initial.id)
        .order_by(VeeException.id.asc())
        .limit(1)
    )
    assert vee_exception is not None
    initial.unit_of_measure = "kWh"
    session.commit()

    reevaluate_vee_exception_and_replay(
        session,
        vee_exception.id,
        reevaluated_by="operator_ui",
    )
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    card = {row.title_key: row for row in snapshot.stage_cards}["dashboard.stage.usage"]
    summary = {row.label_key: row.value for row in card.summary_rows}

    assert card.total_count == 2
    assert card.processing >= 1
    assert card.failed >= 1
    assert summary["dashboard.usage.last_calculated"] is not None
    assert summary["dashboard.usage.last_recalculated"] is not None
    assert summary["dashboard.usage.partial_or_blocked"] == 2
    assert len(snapshot.recent_recalculated_usage) >= 1
    assert all(
        row.details["provenance"]["trigger_source"] == "re_vee"
        for row in snapshot.recent_recalculated_usage
    )


def test_dashboard_snapshot_includes_bill_determinant_spotlight(session):
    seed_demo_environment(session)
    session.commit()

    finalize_canonical_measurements(session, batch_id="demo-read-batch")
    session.commit()
    calculate_usage_transactions(session, usage_type="monthly_consumption")
    session.commit()
    calculate_bill_determinants(
        session,
        determinant_type="billing_cycle_consumption_total",
    )
    session.commit()

    determinant = session.scalar(select(BillDeterminant).limit(1))
    assert determinant is not None

    snapshot = build_dashboard_snapshot(session)
    card = {row.title_key: row for row in snapshot.stage_cards}["dashboard.stage.bill_determinant"]
    summary = {row.label_key: row.value for row in card.summary_rows}

    assert card.total_count == 1
    assert card.waiting == 0
    assert card.processing >= 1
    assert card.completed == 0
    assert card.failed == 0
    assert summary["dashboard.bill_determinant.last_calculated"] is not None
    assert summary["dashboard.bill_determinant.partial_or_blocked"] >= 1
    assert len(snapshot.recent_bill_determinants) == 1
    assert snapshot.recent_bill_determinants[0].id == determinant.id


def test_dashboard_snapshot_includes_vee_replay_request_spotlight(session):
    seed_demo_environment(session)
    session.commit()

    hes_system = session.scalar(select(HesSystem).where(HesSystem.hes_code == "HES").limit(1))
    ingest_batch = session.scalar(
        select(IngestBatch).where(IngestBatch.batch_id == "demo-read-batch").limit(1)
    )
    assert hes_system is not None
    assert ingest_batch is not None

    session.add_all(
        [
            VeeReplayRequest(
                request_scope="hes_system",
                status="queued",
                requested_by="operator_a",
                hes_system_id=hes_system.id,
                target_initial_count=3,
                details={"progress_percent": 0},
            ),
            VeeReplayRequest(
                request_scope="ingest_batch",
                status="processing",
                requested_by="operator_b",
                ingest_batch_id=ingest_batch.id,
                target_initial_count=4,
                processed_count=2,
                details={"progress_percent": 50},
            ),
            VeeReplayRequest(
                request_scope="date_range",
                status="failed",
                requested_by="operator_c",
                hes_system_id=hes_system.id,
                target_initial_count=2,
                processed_count=2,
                failed_count=1,
                details={"progress_percent": 100},
            ),
            VeeReplayRequest(
                request_scope="hes_system",
                status="cancelled",
                requested_by="operator_d",
                hes_system_id=hes_system.id,
                target_initial_count=1,
                details={"progress_percent": 0},
            ),
        ]
    )
    session.commit()

    snapshot = build_dashboard_snapshot(session)
    replay_card = {row.title_key: row for row in snapshot.stage_cards}["dashboard.stage.vee_replay"]
    summary = {row.label_key: row.value for row in replay_card.summary_rows}

    assert replay_card.waiting == 1
    assert replay_card.processing == 1
    assert replay_card.completed == 0
    assert replay_card.failed == 1
    assert replay_card.detail_endpoint == "web.vee_replay_requests"
    assert summary["dashboard.vee_replay.cancelled"] == 1
    assert len(snapshot.recent_vee_replay_requests) == 4


def test_dashboard_snapshot_includes_correction_policy_spotlight_and_recent_audits(session):
    seed_demo_environment(session)
    session.commit()

    initial = session.scalar(select(InitialMeasurement).limit(1))
    assert initial is not None

    baseline_exception = VeeException(
        initial_measurement_id=initial.id,
        exception_code="vee_zero_value_detected",
        severity="warning",
        exception_status="open",
        blocking_finalization=False,
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        details={},
    )
    tamper_exception = VeeException(
        initial_measurement_id=initial.id,
        exception_code="vee_high_value_detected",
        severity="error",
        exception_status="open",
        blocking_finalization=True,
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        details={
            "event_context_snapshot": {
                "primary_context_type": "tamper",
                "matched_context_types": ["tamper"],
            }
        },
    )
    outage_exception = VeeException(
        initial_measurement_id=initial.id,
        exception_code="vee_missing_interval_detected",
        severity="error",
        exception_status="acknowledged",
        blocking_finalization=True,
        detected_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        details={
            "event_context_snapshot": {
                "primary_context_type": "outage",
                "matched_context_types": ["outage"],
            }
        },
    )
    session.add_all([baseline_exception, tamper_exception, outage_exception])
    session.flush()

    session.add_all(
        [
            EstimationAudit(
                service_point_id=initial.service_point_id,
                measuring_component_id=initial.measuring_component_id,
                device_id=initial.device_id,
                target_initial_measurement_id=initial.id,
                target_measured_at=initial.measured_at,
                strategy_code="previous_value_based",
                estimation_status="blocked",
                estimated_value=None,
                unit_of_measure=initial.unit_of_measure,
                operator_memo="blocked by tamper policy",
                details={
                    "correction_policy_snapshot": {
                        "policy_reason_code": "tamper_correlated_value_anomaly",
                        "recommended_action": "operator_investigation_then_manual_edit",
                    }
                },
            ),
            ManualEditAudit(
                service_point_id=initial.service_point_id,
                measuring_component_id=initial.measuring_component_id,
                device_id=initial.device_id,
                target_initial_measurement_id=initial.id,
                related_vee_exception_id=baseline_exception.id,
                target_measured_at=initial.measured_at,
                reason_code="operator_meter_correction",
                edit_status="applied",
                edited_value=initial.value,
                edited_by="operator_dashboard",
                operator_memo="manual correction confirmed",
                details={
                    "correction_policy_snapshot": {
                        "policy_reason_code": "no_event_specific_override",
                        "recommended_action": "follow_existing_baseline",
                    }
                },
            ),
        ]
    )
    session.commit()

    manual_audit = session.scalar(select(ManualEditAudit).order_by(ManualEditAudit.id.desc()).limit(1))
    assert manual_audit is not None
    estimation_audit = session.scalar(
        select(EstimationAudit).order_by(EstimationAudit.id.desc()).limit(1)
    )
    assert estimation_audit is not None

    snapshot = build_dashboard_snapshot(session)
    spotlight = {
        row.policy_reason_code: row.count for row in snapshot.correction_policy_spotlight
    }

    assert spotlight["no_event_specific_override"] == 1
    assert spotlight["tamper_correlated_value_anomaly"] == 1
    assert spotlight["outage_correlated_missing_interval"] == 1
    assert len(snapshot.recent_correction_audits) == 2
    assert {row.audit_kind for row in snapshot.recent_correction_audits} == {
        "estimation",
        "manual_edit",
    }
    assert {
        (row.audit_kind, row.audit_id) for row in snapshot.recent_correction_audits
    } == {
        ("estimation", estimation_audit.id),
        ("manual_edit", manual_audit.id),
    }
