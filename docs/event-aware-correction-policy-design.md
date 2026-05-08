# Event-Aware Correction Policy Design

## Purpose

This document defines the first `event-aware correction policy` slice for the
repository.

The goal is to connect existing event context into operator correction choices
without prematurely introducing a full policy engine, approval framework, or
automatic repair workflow.

More specifically, the first slice should:

- reuse existing outage and tamper context from event-linked VEE
- guide or constrain estimation and manual-edit actions
- preserve explicit operator accountability
- block unsafe system-derived correction paths where event context makes them
  untrustworthy

## Why this slice is needed now

The repository already has all of the following:

- event-aware VEE for outage and tamper context
- operator-triggered estimation
- operator-triggered manual edit
- downstream recalculation through:
  - `final_measurement`
  - `usage_transaction`
  - `bill_determinant`
  - `bill_charge`

What is still missing is the policy layer between:

- `event-linked exception meaning`
- `allowed or recommended operator correction choices`

Right now the repository can:

- detect outage-correlated missing intervals
- detect tamper-correlated suspicious values

but it still treats correction actions mostly as event-agnostic.

This is the next practical policy-depth step.

## First-slice scope

Included:

- a code-backed event-aware correction policy helper
- reuse of existing `event_context_snapshot`
- policy decisions for:
  - estimation
  - manual edit
  - operator guidance in `vee_exception` detail
- first supported event contexts:
  - `outage`
  - `tamper`
- first supported VEE scenarios:
  - `vee_missing_interval_detected` with outage overlap
  - `vee_negative_value_detected` with tamper overlap
  - `vee_high_value_detected` with tamper overlap

Not included in the first slice:

- automatic correction execution
- synthetic missing-interval creation
- event-aware approval workflow
- event-aware bulk correction
- policy tuning UI
- database-backed policy tables
- broader event catalog beyond outage and tamper

## Key design decision

### First policy slice is guidance plus guardrails, not auto-correction

The first slice should not try to auto-select and auto-apply a correction.

Instead it should:

- tell the operator which correction path is recommended
- block unsafe actions when the current event context makes them unreliable
- preserve explicit operator choice where business judgment is still required

Why:

- the current repository has narrow, auditable correction baselines
- event context is still intentionally small
- over-automating correction choice now would create policy risk faster than
  product value

This means the first slice is best treated as:

- recommendation and guardrail policy

not:

- full correction orchestration or approval automation

## Relationship to current correction baselines

The first policy slice should build on the current constraints rather than
pretend they already do not exist.

Important current limits:

- first estimation remains substitution-only
- estimation currently supports only selected existing-interval exception codes
- first manual edit remains substitution-only
- missing-interval synthetic reconstruction does not yet exist

This means the first event-aware correction policy must be honest about what is
actually possible today.

For example:

- outage-correlated `missing_interval` cannot yet be solved through first-slice
  estimation or manual edit
- tamper-correlated `negative` or `high` value can be corrected, but automated
  estimation may be less trustworthy than explicit operator review

## First supported policy scenarios

### 1. `vee_missing_interval_detected` with outage overlap

Event meaning:

- missing data may be explained by a nearby outage

First policy behavior:

- estimation: `blocked`
- manual edit: `blocked`
- re-evaluate: `allowed`
- recommended action: `defer_or_replay_after_source_recovery`

Why:

- current estimation does not support synthetic missing-interval creation
- current manual edit does not support synthetic interval creation
- pretending there is a first-slice correction path here would mislead the
  operator

Expected UI meaning:

- the exception remains blocking
- the operator sees that the outage correlation explains the situation
- the operator also sees that no first-slice correction path is yet supported

### 2. `vee_negative_value_detected` with tamper overlap

Event meaning:

- suspicious value anomaly is correlated with a tamper-style event

First policy behavior:

- estimation: `blocked`
- manual edit: `allowed`
- re-evaluate: `allowed`
- recommended action: `operator_investigation_then_manual_edit`

Why:

- system-derived substitute values are risky when the source interval may be
  affected by tamper or manipulation
- explicit operator correction remains safer than silent estimation

Expected UI meaning:

- estimation should be disabled or clearly marked unavailable
- manual edit should remain available
- the operator should see a strong policy explanation

### 3. `vee_high_value_detected` with tamper overlap

Event meaning:

- suspicious high-value anomaly is correlated with tamper context

First policy behavior:

- estimation: `blocked`
- manual edit: `allowed`
- re-evaluate: `allowed`
- recommended action: `operator_investigation_then_manual_edit`

Why:

- the same trust boundary applies as the tamper-correlated negative-value case

### 4. Default event-agnostic path

When no supported event-linked policy scenario is matched:

- current correction baselines remain in force
- estimation and manual edit behave exactly as they do today

This keeps the first policy slice additive and safe.

## Policy output model

The first slice should use a small in-code policy result object.

Recommended fields:

- `policy_version`
- `recommended_action`
- `estimation_policy`
- `manual_edit_policy`
- `re_evaluate_policy`
- `policy_reason_code`
- `details`

Recommended first value set:

`recommended_action`

- `operator_investigation_then_manual_edit`
- `defer_or_replay_after_source_recovery`
- `follow_existing_baseline`

`*_policy`

- `allowed`
- `discouraged`
- `blocked`

Recommended first `policy_reason_code` values:

- `tamper_correlated_value_anomaly`
- `outage_correlated_missing_interval`
- `no_event_specific_override`

## Persistence direction

The first slice should avoid adding a new database table.

Recommended persistence behavior:

- compute policy dynamically from:
  - `vee_exception`
  - `event_context_snapshot`
- store policy snapshots only inside audit records when a correction attempt is
  made

Recommended snapshot targets:

- `estimation_audit.details.correction_policy_snapshot`
- `manual_edit_audit.details.correction_policy_snapshot`

Why:

- policy must be reproducible for applied or blocked correction attempts
- the first slice does not need a separate policy-history table

## Service integration

Recommended new service:

- `app/services/correction_policy.py`

Recommended responsibilities:

- interpret event-linked VEE context
- return a small policy decision object
- centralize policy semantics so UI and service enforcement do not drift

Recommended service consumers:

- `app/services/estimation.py`
- `app/services/manual_edits.py`
- `vee_exception` detail UI

## First enforcement behavior

### Estimation

The first policy slice should enforce real blocking where the policy says
estimation is not acceptable.

Recommended first blocked cases:

- `tamper`-correlated `negative` value
- `tamper`-correlated `high` value
- `outage`-correlated `missing_interval`

Recommended blocked result-code style:

- `blocked_event_policy_tamper_correlated_value_anomaly`
- `blocked_event_policy_outage_correlated_missing_interval`

### Manual edit

The first policy slice should remain more permissive than estimation.

Recommended first behavior:

- allow manual edit for tamper-correlated `negative` and `high` value
- block manual edit for outage-correlated `missing_interval`

Why:

- explicit operator-entered correction remains auditable and intentional
- synthetic interval creation is still out of scope

## Operator visibility

The first UI baseline should extend `vee_exception` detail.

Recommended additions:

- `Correction Policy` card
- recommended action
- estimation availability
- manual-edit availability
- policy reason
- short explanation of why a given action is blocked or preferred

Expected first operator experience:

- event context explains what happened
- correction policy explains what the operator should do next
- blocked actions are visible as intentionally unavailable rather than
  mysteriously absent

## Deferred items

The following remain intentionally deferred:

- automatic correction selection
- event-aware approval workflow
- event-aware estimation strategy choice beyond block-or-allow behavior
- event-aware manual-edit reason-code enforcement
- synthetic outage-driven gap-fill estimation
- broader event catalog and policy matrix governance
- policy tuning UI or policy persistence tables

## Recommended implementation sequence

1. Document the first event-aware correction policy baseline
2. Add a small `correction_policy` helper service
3. Enforce the policy in `estimation.py`
4. Enforce the policy in `manual_edits.py`
5. Add `Correction Policy` visibility to `vee_exception` detail
6. Add regression coverage for event-aware correction outcomes
