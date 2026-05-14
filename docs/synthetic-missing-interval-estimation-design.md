# Synthetic Missing-Interval Estimation Design

## Purpose

This document defines the first practical slice for synthetic
missing-interval estimation.

The goal is to close the biggest remaining MVP estimation gap without turning
the repository into a full gap-fill engine.

The first slice should:

- repair a single missing interval slot that is explicitly identified through
  `RawIntervalWindowState`
- keep synthetic interval creation anchored to existing raw-window lineage
- reuse the current `canonical -> initial -> final -> usage -> determinant ->
  charge` chain
- leave multi-slot repair, outage-driven repair, and automation for later work

## Why this is the highest-leverage remaining MVP estimation gap

The repository already supports:

- substitution-only estimation for selected value anomalies
- explicit `estimation_audit`
- downstream recalculation through usage, determinant, and charge
- event-aware correction guardrails

What it still cannot do is repair a true `vee_missing_interval_detected`
condition.

That means the system can detect and explain missing intervals, but it still
cannot close the simplest recoverable missing-slot case.

## First-slice scope

Included:

- operator-triggered synthetic estimation from an active
  `vee_missing_interval_detected`
- one-hour windows only
- `interval_size_minutes in {15, 30, 60}`
- exactly one missing slot in the target window
- no outage or tamper event context
- two strategies only:
  - `linear_interpolation`
  - `previous_value_based`
- synthetic lineage through `hes_read_raw`, `canonical_measurement`,
  `initial_measurement`, and `final_measurement`
- window-state update and same-window VEE re-evaluation
- downstream recalculation through usage, determinant, and charge

Not included:

- windows with more than one missing slot
- outage-correlated or tamper-correlated missing-interval repair
- synthetic repair for duplicate, required-field, or interval-size exceptions
- bulk gap-fill
- automatic synthetic estimation policy
- approval workflow
- arbitrary interval creation without raw-window anchor

## Key design decision

### Synthetic repair stays inside the existing processing-core chain

The first slice should not introduce a separate synthetic-only measurement
table.

Instead, it should create:

- synthetic `hes_read_raw`
- synthetic `canonical_measurement`
- synthetic `initial_measurement`
- synthetic current `final_measurement`

Why:

- `InitialMeasurement` still requires `canonical_measurement_id`
- `FinalMeasurement` still requires `canonical_measurement_id`
- downstream usage, determinant, and charge logic already depend on the normal
  finalized-measurement chain

This keeps the first slice auditable and reuses the existing processing-core
structure rather than bypassing it.

## Business anchor

The repair anchor for the first slice is not just the open VEE exception.

It is the combination of:

- `anchor_vee_exception_id`
- `raw_interval_window_state_id`
- the one missing slot implied by `received_slot_bitmap` versus the expected
  slot set

This is why `estimation_audit` must carry both the VEE-exception link and the
raw-window-state link explicitly.

## First-slice eligibility

Synthetic missing-interval estimation should only be allowed when:

- the selected VEE exception is active
- `exception_code == vee_missing_interval_detected`
- the target window exists in `RawIntervalWindowState`
- the window has exactly one missing slot
- the missing slot does not already have a raw/canonical/initial/final row
- no outage or tamper correction-policy override blocks synthetic repair
- the strategy-specific supporting finalized rows exist

Recommended blocked result codes:

- `blocked_missing_interval_multi_slot_window`
- `blocked_missing_interval_invalid_window_state`
- `blocked_missing_interval_existing_measurement_present`
- `blocked_missing_interval_unsupported_event_context`
- `blocked_missing_previous_final`
- `blocked_missing_next_final`

## Estimation strategies

### `linear_interpolation`

Use when:

- previous current finalized final exists
- next current finalized final exists
- both belong to the same service-point and component context

Expected behavior:

- estimate the missing slot value between the two finalized values
- quantize to `Numeric(19,4)`

### `previous_value_based`

Use when:

- previous current finalized final exists
- carry-forward is acceptable for the first slice

Expected behavior:

- copy the previous finalized value
- quantize to `Numeric(19,4)` if needed

## `estimation_audit` requirements

Synthetic missing-interval repair should still use the existing
`estimation_audit` table as the single estimation ledger.

The first schema enhancement should add:

- `anchor_vee_exception_id`
- `raw_interval_window_state_id`
- `estimation_mode`

Recommended `estimation_mode` values:

- `substitution`
- `synthetic_missing_interval`

Why this matters:

- substitution and synthetic estimation should remain queryable from one audit
  surface
- operators must be able to tell which VEE exception and which raw window
  triggered the repair
- later visibility and analytics should not have to infer this from unstructured
  JSON alone

Recommended `details` additions for synthetic repair:

- `estimation_mode`
- `anchor_vee_exception_snapshot`
- `window_state_snapshot_before`
- `window_state_snapshot_after`
- `missing_slot_code`
- `synthetic_hes_read_raw_snapshot`
- `synthetic_canonical_measurement_snapshot`
- `synthetic_initial_measurement_snapshot`
- `result_final_measurement_snapshot`
- `re_evaluated_initial_measurement_ids`
- `downstream_recalculation_summary`

## Window-state update

Creating the synthetic interval alone is not enough.

The repair flow must also update `RawIntervalWindowState`:

- add the missing slot to the received bitmap
- increment `received_slot_count`
- move the window to `completion_status = complete`
- record synthetic-completion metadata in `details`

After that, same-window measurements should be re-evaluated so the open
`vee_missing_interval_detected` condition can close with correct lineage.

## First implementation order

1. document the synthetic missing-interval estimation boundary
2. enhance `estimation_audit` with explicit anchor and mode lineage
3. add synthetic repair orchestration in `estimation.py`
4. add targeted tests for single-slot repair
5. connect the operator UI after service and audit behavior are stable

## Explicit deferrals

The following should remain outside the first synthetic slice:

- multi-slot window reconstruction
- outage-correlated missing-interval repair
- tamper-correlated missing-interval repair
- bulk synthetic repair
- approval workflow
- automatic strategy selection
- arbitrary interval creation without raw-window-state anchor
