from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import InitialMeasurement, RawIntervalWindowState
from app.services.seeds import seed_demo_environment
from app.services.vee import (
    _build_duplicate_hit,
    _build_high_value_hit,
    _build_interval_size_hit,
    _build_low_value_hit,
    _build_missing_interval_hit,
    _build_multiplier_hit,
    _build_negative_value_hit,
    _build_required_field_hit,
    _build_zero_value_hit,
    evaluate_initial_measurement_rule_hits,
)


def _seed_initial_measurement(session) -> InitialMeasurement:
    seed_demo_environment(session)
    session.commit()
    initial = session.scalar(select(InitialMeasurement).order_by(InitialMeasurement.id.asc()).limit(1))
    assert initial is not None
    assert initial.canonical_measurement is not None
    assert initial.canonical_measurement.hes_read_raw is not None
    assert initial.measuring_component is not None
    return initial


def test_build_required_field_hit_returns_none_for_well_formed_row(session):
    initial = _seed_initial_measurement(session)

    hit = _build_required_field_hit(initial)

    assert hit is None


def test_build_required_field_hit_collects_all_missing_fields_in_rule_order(session):
    initial = _seed_initial_measurement(session)
    initial.measured_at = None
    initial.value = None
    initial.unit_of_measure = ""
    initial.measuring_component_id = None
    initial.device_id = None
    initial.service_point_id = None

    hit = _build_required_field_hit(initial)

    assert hit is not None
    assert hit.exception_code == "vee_required_field_missing"
    assert hit.severity == "error"
    assert hit.blocking_finalization is True
    assert hit.details["fields"] == [
        "measured_at",
        "value",
        "unit_of_measure",
        "measuring_component_id",
        "device_id",
        "service_point_id",
    ]


@pytest.mark.parametrize(
    ("multiplier", "expected_reason"),
    [
        (None, "missing_component_multiplier"),
        (Decimal("0"), "invalid_component_multiplier"),
        (Decimal("-1"), "invalid_component_multiplier"),
        (Decimal("2"), "unsupported_non_unity_multiplier"),
        (Decimal("1"), None),
    ],
)
def test_build_multiplier_hit_classifies_supported_and_unsupported_values(
    session,
    multiplier,
    expected_reason,
):
    initial = _seed_initial_measurement(session)
    initial.measuring_component.multiplier = multiplier

    hit = _build_multiplier_hit(initial)

    if expected_reason is None:
        assert hit is None
        return

    assert hit is not None
    assert hit.exception_code == "vee_multiplier_invalid_detected"
    assert hit.blocking_finalization is True
    assert hit.details["validation_reason"] == expected_reason


def test_build_negative_value_hit_escalates_when_tamper_context_is_present(session):
    initial = _seed_initial_measurement(session)
    initial.value = Decimal("-1.0000")

    ordinary_hit = _build_negative_value_hit(initial)
    tamper_hit = _build_negative_value_hit(
        initial,
        event_context_snapshot={"matched_context_types": ["tamper"]},
    )

    assert ordinary_hit is not None
    assert ordinary_hit.severity == "error"
    assert ordinary_hit.blocking_finalization is True
    assert "event_linked_decision" not in ordinary_hit.details

    assert tamper_hit is not None
    assert tamper_hit.severity == "critical"
    assert tamper_hit.blocking_finalization is True
    assert tamper_hit.details["event_linked_decision"] == "tamper_correlated_value_anomaly"


def test_build_zero_value_hit_only_matches_exact_zero(session):
    initial = _seed_initial_measurement(session)

    initial.value = Decimal("0.0000")
    zero_hit = _build_zero_value_hit(initial)

    initial.value = Decimal("0.0001")
    positive_hit = _build_zero_value_hit(initial)

    initial.value = Decimal("-0.0001")
    negative_hit = _build_zero_value_hit(initial)

    assert zero_hit is not None
    assert zero_hit.exception_code == "vee_zero_value_detected"
    assert zero_hit.blocking_finalization is False
    assert positive_hit is None
    assert negative_hit is None


@pytest.mark.parametrize(
    ("value", "interval_size_minutes", "expected_hit"),
    [
        (Decimal("0.0019"), 60, True),
        (Decimal("0.0020"), 60, False),
        (Decimal("0.0021"), 60, False),
        (Decimal("0.0004"), 15, True),
        (Decimal("0.0005"), 15, False),
        (Decimal("0.0010"), 5, False),
    ],
)
def test_build_low_value_hit_respects_threshold_boundaries(session, value, interval_size_minutes, expected_hit):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    initial.value = value
    initial.unit_of_measure = "kWh"
    raw_row.interval_size_minutes = interval_size_minutes

    hit = _build_low_value_hit(initial)

    if not expected_hit:
        assert hit is None
        return

    assert hit is not None
    assert hit.exception_code == "vee_low_value_detected"
    assert hit.blocking_finalization is False


@pytest.mark.parametrize(
    ("interval_size_minutes", "expected_hit"),
    [
        (15, False),
        (30, False),
        (60, False),
        (14, True),
        (16, True),
        (59, True),
        (61, True),
        (None, True),
    ],
)
def test_build_interval_size_hit_flags_invalid_near_supported_values(
    session,
    interval_size_minutes,
    expected_hit,
):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    raw_row.interval_size_minutes = interval_size_minutes

    hit = _build_interval_size_hit(initial)

    assert (hit is not None) is expected_hit
    if hit is not None:
        assert hit.exception_code == "vee_interval_size_invalid"
        assert hit.blocking_finalization is True


@pytest.mark.parametrize(
    ("is_duplicate", "canonical_status", "expected_hit"),
    [
        (True, "accepted", True),
        (False, "duplicate", True),
        (False, "accepted", False),
    ],
)
def test_build_duplicate_hit_supports_both_duplicate_signals(
    session,
    is_duplicate,
    canonical_status,
    expected_hit,
):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    raw_row.is_duplicate = is_duplicate
    raw_row.canonical_status = canonical_status

    hit = _build_duplicate_hit(initial)

    assert (hit is not None) is expected_hit
    if hit is not None:
        assert hit.exception_code == "vee_duplicate_detected"
        assert hit.details["hes_read_raw_id"] == raw_row.id


@pytest.mark.parametrize(
    ("completion_status", "received_slot_count", "expected_slot_count", "expected_hit"),
    [
        ("partial", 2, 4, True),
        ("open", 1, 4, True),
        ("complete", 2, 4, False),
        ("partial", 4, 4, False),
    ],
)
def test_build_missing_interval_hit_requires_incomplete_open_or_partial_window(
    session,
    completion_status,
    received_slot_count,
    expected_slot_count,
    expected_hit,
):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    assert raw_row.source_system is not None
    assert raw_row.meter_identifier is not None
    assert raw_row.channel_identifier is not None
    raw_row.source_business_ts = raw_row.measured_at
    assert raw_row.source_business_ts is not None

    session.add(
        RawIntervalWindowState(
            source_system=raw_row.source_system,
            meter_identifier=raw_row.meter_identifier,
            channel_identifier=raw_row.channel_identifier,
            window_start_at=raw_row.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=raw_row.interval_size_minutes,
            expected_slot_count=expected_slot_count,
            received_slot_count=received_slot_count,
            received_slot_bitmap="00,15",
            completion_status=completion_status,
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.flush()

    hit = _build_missing_interval_hit(session, initial)

    assert (hit is not None) is expected_hit
    if hit is not None:
        assert hit.exception_code == "vee_missing_interval_detected"
        assert hit.blocking_finalization is True


def test_build_missing_interval_hit_records_outage_linked_decision(session):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    assert raw_row.source_system is not None
    assert raw_row.meter_identifier is not None
    assert raw_row.channel_identifier is not None
    raw_row.source_business_ts = raw_row.measured_at
    assert raw_row.source_business_ts is not None

    session.add(
        RawIntervalWindowState(
            source_system=raw_row.source_system,
            meter_identifier=raw_row.meter_identifier,
            channel_identifier=raw_row.channel_identifier,
            window_start_at=raw_row.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=raw_row.interval_size_minutes,
            expected_slot_count=4,
            received_slot_count=2,
            received_slot_bitmap="00,15",
            completion_status="partial",
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.flush()

    hit = _build_missing_interval_hit(
        session,
        initial,
        event_context_snapshot={"matched_context_types": ["outage"]},
    )

    assert hit is not None
    assert hit.details["event_linked_decision"] == "outage_correlated_missing_interval"


def test_build_high_value_hit_respects_threshold_and_tamper_context(session):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    raw_row.interval_size_minutes = 60
    initial.unit_of_measure = "kWh"

    initial.value = Decimal("1000.0000")
    at_threshold = _build_high_value_hit(initial)

    initial.value = Decimal("1000.0001")
    warning_hit = _build_high_value_hit(initial)
    tamper_hit = _build_high_value_hit(
        initial,
        event_context_snapshot={"matched_context_types": ["tamper"]},
    )

    assert at_threshold is None
    assert warning_hit is not None
    assert warning_hit.exception_code == "vee_high_value_detected"
    assert warning_hit.severity == "warning"
    assert warning_hit.blocking_finalization is False
    assert tamper_hit is not None
    assert tamper_hit.severity == "error"
    assert tamper_hit.blocking_finalization is True


def test_evaluate_initial_measurement_rule_hits_keeps_documented_rule_order_for_multiple_matches(session):
    initial = _seed_initial_measurement(session)
    raw_row = initial.canonical_measurement.hes_read_raw
    assert raw_row is not None
    assert raw_row.source_system is not None
    assert raw_row.meter_identifier is not None
    assert raw_row.channel_identifier is not None

    initial.unit_of_measure = "MWh"
    initial.measuring_component.multiplier = Decimal("2")
    initial.value = Decimal("-1.0000")
    raw_row.interval_size_minutes = 14
    raw_row.is_duplicate = True
    raw_row.source_business_ts = raw_row.measured_at
    assert raw_row.source_business_ts is not None

    session.add(
        RawIntervalWindowState(
            source_system=raw_row.source_system,
            meter_identifier=raw_row.meter_identifier,
            channel_identifier=raw_row.channel_identifier,
            window_start_at=raw_row.source_business_ts,
            window_size_minutes=60,
            interval_size_minutes=14,
            expected_slot_count=4,
            received_slot_count=2,
            received_slot_bitmap="00,15",
            completion_status="partial",
            late_update_count=0,
            details={"expected_slot_codes": ["00", "15", "30", "45"]},
        )
    )
    session.flush()

    hits = evaluate_initial_measurement_rule_hits(session, initial)

    assert [hit.exception_code for hit in hits] == [
        "vee_uom_mismatch_detected",
        "vee_multiplier_invalid_detected",
        "vee_negative_value_detected",
        "vee_interval_size_invalid",
        "vee_duplicate_detected",
        "vee_missing_interval_detected",
    ]
