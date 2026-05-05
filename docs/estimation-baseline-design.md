# Estimation Baseline Design

## Purpose

This document defines the first practical estimation slice for the repository.

The goal is to introduce a narrow, auditable estimation path that:

- resolves selected VEE exceptions through explicit operator action
- creates a new current `final_measurement` revision instead of mutating history
- recalculates downstream `usage_transaction`, `bill_determinant`, and `bill_charge`
- avoids prematurely introducing a full estimation engine or approval workflow

## Why estimation is needed now

The repository already has:

- `initial_measurement`
- `vee_execution_log`
- `vee_exception`
- current-plus-history `final_measurement`
- current-plus-history `bill_determinant`
- current-plus-history `bill_charge`

This means the structure is now good enough to support a first estimation path.

At the same time, the MVP backlog still has a clear gap in:

- basic estimation
- estimation audit
- final-measurement update flow after estimation

Estimation therefore becomes the next upstream processing-core priority.

## First-slice scope

The first estimation baseline should remain intentionally narrow.

Included:

- operator-triggered estimation from a `vee_exception` flow
- estimation for an interval that already has:
  - `canonical_measurement`
  - `initial_measurement`
  - current or prior `final_measurement` lineage
- two strategies only:
  - `linear_interpolation`
  - `previous_value_based`
- explicit estimation audit persistence
- downstream recalculation after estimation

Not included in the first slice:

- synthetic creation of a brand-new missing interval row
- automatic estimation policy engine
- bulk estimation
- estimation approval chain
- event-aware estimation policy
- advanced estimation strategy catalog

## Key design decision

### First estimation is substitution-only

The first estimation slice should support only:

- replacing the business outcome for an already-existing measurement interval

It should not yet support:

- creating a synthetic interval that has no existing `canonical_measurement` /
  `initial_measurement` anchor

Why:

- the current repository anchors `initial_measurement` one-to-one to
  `canonical_measurement`
- `final_measurement` still keeps `canonical_measurement_id` as required lineage
- synthetic gap-fill estimation would therefore require a larger structural
  change than a first MVP estimation slice should take on

This means the first estimation slice is best treated as:

- estimation-based replacement of an existing interval outcome

not:

- full missing-interval reconstruction

## Relationship to VEE

The first estimation slice should be modeled as one operator resolution path for
selected VEE exceptions.

Recommended interpretation:

- VEE detects a data-quality or business-quality condition
- operator chooses an estimation strategy
- estimation applies a substitute value
- the active VEE exception is resolved with `resolution_type = estimated`
- downstream business outputs are recalculated from the new current final result

Important policy:

- the repository does not need a new `initial_status` value in the first slice
- `initial_measurement.initial_status` may remain `accepted` after successful
  estimated resolution
- estimation meaning should instead remain visible through:
  - `estimation_audit`
  - `final_measurement.revision_reason_code`
  - `vee_exception.resolution_type`

This keeps the first rollout safer and avoids expanding every VEE status
consumer immediately.

## Recommended first strategies

### 1. `linear_interpolation`

Use when:

- a previous current final exists
- a next current final exists
- both belong to the same business context
- the target measured timestamp lies between them

Expected behavior:

- estimate the target value from the two surrounding finalized values
- quantize to `Numeric(19,4)`

### 2. `previous_value_based`

Use when:

- a previous current final exists
- the next final is not required for the first rule
- business policy allows a carry-forward style substitute

Expected behavior:

- copy the previous finalized value into the target interval
- quantize to `Numeric(19,4)` if needed

## Required compatibility checks

Estimation should be blocked when:

- previous/next supporting rows are missing for the selected strategy
- unit of measure does not match
- measurement context does not match
- the target interval is not estimation-eligible
- the selected VEE exception is already resolved
- the business anchor is missing

Recommended blocked result codes:

- `blocked_missing_previous_final`
- `blocked_missing_next_final`
- `blocked_uom_mismatch`
- `blocked_context_mismatch`
- `blocked_invalid_target_state`
- `blocked_missing_current_exception`

## Recommended persistence

### `estimation_audit`

The first estimation slice should add an append-only audit table.

Recommended minimum columns:

- `id`
- `pipeline_run_id`
- `service_point_id`
- `measuring_component_id`
- `device_id`
- `target_initial_measurement_id`
- `target_measured_at`
- `strategy_code`
- `estimation_status`
- `estimated_value`
- `unit_of_measure`
- `source_previous_final_measurement_id`
- `source_next_final_measurement_id`
- `superseded_final_measurement_id`
- `result_final_measurement_id`
- `operator_memo`
- `details`
- `created_at`
- `updated_at`

Important interpretation:

- this is an audit record of one estimation attempt
- it is not a mutable current-row table
- every estimation application should create a new audit row

### Recommended first values

`strategy_code`

- `linear_interpolation`
- `previous_value_based`

`estimation_status`

- `applied`
- `blocked`
- `failed`

## Relationship to `final_measurement`

Estimation must not overwrite the existing current final row.

Recommended rule:

- estimation always creates a new current `final_measurement` revision
- the previous current final becomes superseded

Recommended first revision behavior:

- old row:
  - `is_current = false`
  - `final_status = superseded`
- new row:
  - `is_current = true`
  - `revision_number = old + 1`
  - `revision_reason_code = estimation_applied`

Recommended first semantics for the new current final:

- keep the same lineage anchor:
  - `initial_measurement_id`
  - `canonical_measurement_id`
  - `measured_at`
- replace only the business output value and estimation-visible quality/status

Recommended first quality signaling:

- prefer `quality_code = ESTIMATED`
- keep this simpler than adding a broad new state framework immediately

## Downstream recalculation rule

Successful estimation must trigger the same kind of closed-loop recalculation
expected from other authoritative business changes.

Recommended downstream sequence:

1. supersede current `final_measurement`
2. create new current final revision
3. recalculate impacted `usage_transaction`
4. recalculate impacted `bill_determinant`
5. recalculate impacted `bill_charge`

This keeps the repository's downstream chain consistent:

- final -> usage -> determinant -> charge

## UI baseline

The first UI slice should remain narrow and operator-centered.

Recommended first entry point:

- `vee_exception_detail`

Recommended first controls:

- strategy selection
  - `linear_interpolation`
  - `previous_value_based`
- optional operator memo
- execute estimation

Recommended first result visibility:

- applied strategy
- source previous/next final ids
- estimated value
- created current final revision id
- recalculated downstream counts:
  - usage
  - determinant
  - charge

This keeps estimation grounded in a concrete exception-resolution flow rather
than creating a separate large operator subsystem too early.

## First orchestration shape

Recommended new service:

- `app/services/estimation.py`

Recommended responsibilities:

- validate estimation target
- select supporting source finals
- calculate estimated value
- create `estimation_audit`
- resolve the active VEE exception with `resolution_type = estimated`
- create a new current final revision
- recalculate impacted downstream rows

The first baseline should keep this orchestration local and explicit rather than
introducing queue-backed bulk estimation immediately.

## Test expectations

The first estimation slice should include explicit regression coverage for:

- linear interpolation applied
- previous-value-based estimation applied
- blocked when supporting source rows are missing
- blocked on UOM mismatch
- superseded current final plus new current final revision
- VEE exception resolved as `estimated`
- usage recalculation after estimation
- determinant recalculation after estimation
- charge recalculation after estimation

## Explicit deferrals

The following should remain outside the first estimation baseline:

- synthetic missing-interval estimation
- estimation preview and approval workflow
- bulk estimation
- event-aware estimation policy
- manual edit and estimation unification
- advanced estimation strategy registry

These belong in later MVP hardening or product-stage expansion.

## Recommended implementation sequence

1. document the estimation boundary and first rules
2. add `estimation_audit` persistence
3. add `estimation.py` orchestration
4. connect estimation to `vee_exception_detail`
5. add downstream recalculation linkage
6. expand only after regression and operator visibility are stable

## Summary

The first estimation slice should be:

- operator-triggered
- substitution-only
- audit-first
- revision-safe
- downstream-consistent

It should solve the MVP need for basic estimation without prematurely turning
the repository into a full estimation engine or approval platform.
