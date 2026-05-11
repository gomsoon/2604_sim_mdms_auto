from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.models import InitialMeasurement, VeeException
from app.services.event_context import has_event_context_type, lookup_event_context_snapshot

CORRECTION_POLICY_ALLOWED = "allowed"
CORRECTION_POLICY_DISCOURAGED = "discouraged"
CORRECTION_POLICY_BLOCKED = "blocked"

CORRECTION_POLICY_ACTION_OPERATOR_INVESTIGATION_THEN_MANUAL_EDIT = (
    "operator_investigation_then_manual_edit"
)
CORRECTION_POLICY_ACTION_DEFER_OR_REPLAY_AFTER_SOURCE_RECOVERY = (
    "defer_or_replay_after_source_recovery"
)
CORRECTION_POLICY_ACTION_FOLLOW_EXISTING_BASELINE = "follow_existing_baseline"

CORRECTION_POLICY_REASON_TAMPER_CORRELATED_VALUE_ANOMALY = (
    "tamper_correlated_value_anomaly"
)
CORRECTION_POLICY_REASON_OUTAGE_CORRELATED_MISSING_INTERVAL = (
    "outage_correlated_missing_interval"
)
CORRECTION_POLICY_REASON_NO_EVENT_SPECIFIC_OVERRIDE = "no_event_specific_override"
CORRECTION_POLICY_EVENT_CONTEXT_TYPE_NONE = "none"
SUPPORTED_CORRECTION_POLICY_REASON_CODES = (
    CORRECTION_POLICY_REASON_NO_EVENT_SPECIFIC_OVERRIDE,
    CORRECTION_POLICY_REASON_TAMPER_CORRELATED_VALUE_ANOMALY,
    CORRECTION_POLICY_REASON_OUTAGE_CORRELATED_MISSING_INTERVAL,
)
SUPPORTED_CORRECTION_POLICY_EVENT_CONTEXT_TYPES = (
    CORRECTION_POLICY_EVENT_CONTEXT_TYPE_NONE,
    "outage",
    "tamper",
)
CORRECTION_POLICY_VERSION = "v1"


@dataclass(frozen=True, slots=True)
class CorrectionPolicyDecision:
    policy_version: str
    recommended_action: str
    estimation_policy: str
    manual_edit_policy: str
    re_evaluate_policy: str
    policy_reason_code: str
    event_context_type: str | None
    details: dict[str, object]

    def to_snapshot(self) -> dict[str, object]:
        return asdict(self)


def _get_exception_event_context_snapshot(
    vee_exception: VeeException,
) -> dict[str, object] | None:
    details = vee_exception.details if isinstance(vee_exception.details, dict) else {}
    snapshot = details.get("event_context_snapshot")
    return snapshot if isinstance(snapshot, dict) else None


def build_correction_policy_decision(
    session: Session,
    vee_exception: VeeException,
    *,
    initial_row: InitialMeasurement | None = None,
    event_context_snapshot: dict[str, object] | None = None,
) -> CorrectionPolicyDecision:
    resolved_initial = initial_row or vee_exception.initial_measurement
    resolved_snapshot = (
        event_context_snapshot
        or _get_exception_event_context_snapshot(vee_exception)
        or lookup_event_context_snapshot(session, resolved_initial)
    )
    primary_context_type = None
    if isinstance(resolved_snapshot, dict):
        primary_context_type = resolved_snapshot.get("primary_context_type")
        if not isinstance(primary_context_type, str):
            primary_context_type = None

    if (
        vee_exception.exception_code == "vee_missing_interval_detected"
        and has_event_context_type(resolved_snapshot, "outage")
    ):
        return CorrectionPolicyDecision(
            policy_version=CORRECTION_POLICY_VERSION,
            recommended_action=CORRECTION_POLICY_ACTION_DEFER_OR_REPLAY_AFTER_SOURCE_RECOVERY,
            estimation_policy=CORRECTION_POLICY_BLOCKED,
            manual_edit_policy=CORRECTION_POLICY_BLOCKED,
            re_evaluate_policy=CORRECTION_POLICY_ALLOWED,
            policy_reason_code=CORRECTION_POLICY_REASON_OUTAGE_CORRELATED_MISSING_INTERVAL,
            event_context_type=primary_context_type,
            details={
                "exception_code": vee_exception.exception_code,
                "event_context_snapshot": resolved_snapshot,
            },
        )

    if vee_exception.exception_code in {
        "vee_negative_value_detected",
        "vee_high_value_detected",
    } and has_event_context_type(resolved_snapshot, "tamper"):
        return CorrectionPolicyDecision(
            policy_version=CORRECTION_POLICY_VERSION,
            recommended_action=(
                CORRECTION_POLICY_ACTION_OPERATOR_INVESTIGATION_THEN_MANUAL_EDIT
            ),
            estimation_policy=CORRECTION_POLICY_BLOCKED,
            manual_edit_policy=CORRECTION_POLICY_ALLOWED,
            re_evaluate_policy=CORRECTION_POLICY_ALLOWED,
            policy_reason_code=CORRECTION_POLICY_REASON_TAMPER_CORRELATED_VALUE_ANOMALY,
            event_context_type=primary_context_type,
            details={
                "exception_code": vee_exception.exception_code,
                "event_context_snapshot": resolved_snapshot,
            },
        )

    return CorrectionPolicyDecision(
        policy_version=CORRECTION_POLICY_VERSION,
        recommended_action=CORRECTION_POLICY_ACTION_FOLLOW_EXISTING_BASELINE,
        estimation_policy=CORRECTION_POLICY_ALLOWED,
        manual_edit_policy=CORRECTION_POLICY_ALLOWED,
        re_evaluate_policy=CORRECTION_POLICY_ALLOWED,
        policy_reason_code=CORRECTION_POLICY_REASON_NO_EVENT_SPECIFIC_OVERRIDE,
        event_context_type=primary_context_type,
        details={
            "exception_code": vee_exception.exception_code,
            "event_context_snapshot": resolved_snapshot,
        },
    )
