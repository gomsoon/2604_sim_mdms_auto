# Event-Linked Decisioning Baseline Design

## Purpose

This document defines the first event-linked decisioning slice for the
repository.

The goal is to introduce a narrow, auditable path where upstream HES events
start to influence VEE behavior without prematurely creating a full event
policy engine.

## Why this slice is needed now

The repository already has:

- `hes_event_raw`
- `vee_execution_log`
- `vee_exception`
- operator-facing VEE visibility
- re-VEE, estimation, and manual edit downstream recalculation

What is still missing is a first point where event context is not only visible
but actually used in decisioning.

This is the remaining MVP gap behind:

- outage-aware interpretation of missing intervals
- tamper-aware interpretation of suspicious values

## First-slice scope

Included:

- event context lookup from `hes_event_raw`
- narrow context catalog:
  - `outage`
  - `tamper`
- event-context snapshot persistence inside:
  - `vee_execution_log.details`
  - `vee_exception.details`
- first event-aware rule extensions:
  - `vee_missing_interval_detected` with outage overlap
  - `vee_negative_value_detected` with tamper overlap
  - `vee_high_value_detected` with tamper overlap
- operator visibility of matched event context in VEE exception detail

Not included in the first slice:

- new standalone event-policy tables
- master-data-driven event catalog
- duration-aware outage modeling beyond a fixed tolerance window
- zero-value suppression by outage context
- event-aware estimation policy
- event-aware manual edit policy
- bulk event-linked replay controls
- dashboard- or list-level event-linked spotlight expansion

## Key design decision

### First event-linked decisioning should enrich existing VEE rules

The first slice should not create an entirely new VEE branch.

Instead it should:

- keep existing VEE exception codes
- keep existing VEE persistence structures
- enrich rule behavior and rule details with event context

Why:

- the repository already has strong VEE visibility and downstream replay
- preserving existing exception codes keeps the first rollout smaller
- operators can still learn whether a VEE outcome was event-correlated from
  details and summary behavior

This means the first slice is best treated as:

- event-aware enrichment of existing VEE decisions

not:

- a brand-new event-decision framework

## First supported contexts

### 1. `outage`

This context should be matched from raw HES events such as:

- `POWER_FAIL`
- similar outage-style codes from the same source

The first slice uses this context only to enrich:

- `vee_missing_interval_detected`

Expected first behavior:

- keep the exception blocking
- keep the exception code unchanged
- store event context snapshot and correlation decision in exception details

### 2. `tamper`

This context should be matched from raw HES events such as:

- `METER_TAMPER`
- similar tamper-style codes from the same source

The first slice uses this context only to enrich:

- `vee_negative_value_detected`
- `vee_high_value_detected`

Expected first behavior:

- `vee_negative_value_detected`
  - remains blocking
  - severity escalates from `error` to `critical`
- `vee_high_value_detected`
  - escalates from non-blocking warning to blocking error
  - summary becomes a failed high-value outcome

## Event lookup baseline

The first lookup should remain intentionally simple.

Recommended match conditions:

- same `source_system`
- same `meter_identifier`
- same `hes_system_id` when available
- event time within a fixed tolerance window around the target interval

Recommended first tolerance:

- `15 minutes` before or after the target measured timestamp

This is sufficient for:

- outage correlation with nearby missing-interval states
- tamper correlation with suspicious same-interval values

## Persistence direction

The first slice should avoid adding a large new persistence model.

Recommended first persistence:

- `vee_execution_log.details.event_context_snapshot`
- `vee_exception.details.event_context_snapshot`
- `vee_exception.details.event_linked_decision`

This keeps the first rollout small while still preserving:

- matched event ids
- matched event codes
- matched event times
- matched event severities
- correlation reason

## First event-linked decisions

### `vee_missing_interval_detected` + outage overlap

Expected behavior:

- exception code stays `vee_missing_interval_detected`
- severity stays `error`
- blocking stays `true`
- details include outage event context
- details include `event_linked_decision = outage_correlated_missing_interval`

### `vee_negative_value_detected` + tamper overlap

Expected behavior:

- exception code stays `vee_negative_value_detected`
- blocking stays `true`
- severity escalates to `critical`
- details include tamper event context
- details include `event_linked_decision = tamper_correlated_value_anomaly`

### `vee_high_value_detected` + tamper overlap

Expected behavior:

- exception code stays `vee_high_value_detected`
- blocking changes from `false` to `true`
- severity escalates from `warning` to `error`
- summary changes from `vee_completed_with_high_value` to
  `vee_failed_high_value`
- details include tamper event context
- details include `event_linked_decision = tamper_correlated_value_anomaly`

## Operator visibility

The first UI baseline should start in `vee_exception` detail.

Recommended additions:

- `Event Context` card
- primary context type
- correlation reason
- linked decision code
- matched event codes
- matched event times
- matched event severities

This keeps the first operator experience close to the existing VEE drill-down
path.

## Deferred items

The following are intentionally deferred beyond the first slice:

- zero-value suppression or downgrading by outage context
- richer event-duration modeling
- source-specific event-code governance UI
- event-aware estimation strategy selection
- event-aware manual-edit policy
- dedicated event-linked exception tables
- event-linked list spotlight and bulk operations

## Recommended implementation sequence

1. Document the first baseline and its deferred items
2. Add a small `event_context` lookup service
3. Extend selected VEE rule builders with event-aware behavior
4. Store event-context snapshot in execution and exception details
5. Expose the new context in `vee_exception` detail UI
6. Add regression coverage for outage and tamper correlation
