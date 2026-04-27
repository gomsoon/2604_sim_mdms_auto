# Processing Core Rollout Plan

## Purpose

This document defines the practical rollout sequence for introducing the first true processing/core boundary after the current minimal finalization baseline.

The focus is safe staged adoption, not a disruptive one-shot replacement.

## Current baseline

The repository currently supports:

- `hes_read_raw`
- `canonical_measurement`
- current minimal `final_measurement`
- operator visibility and reprocess support

The repository does not yet support:

- explicit `initial_measurement`
- explicit VEE execution persistence
- explicit VEE exception persistence
- usage persistence

## Rollout principle

Recommended principle:

- introduce persistence first
- dual-run processing lineage next
- switch business gating after tests are stable
- only then add usage persistence

## Phase 1. Schema introduction

### Goal

Add new processing/core persistence without breaking the current finalization path.

### Scope

- add `initial_measurement`
- add `vee_execution_log`
- add `vee_exception`
- do not yet require them for finalization

### Acceptance gate

- migrations apply cleanly
- existing code paths still pass regression
- no change in current finalization outcome for existing happy-path cases

## Phase 2. New-row lineage creation

### Goal

Start creating the new processing/core records for newly mapped data.

### Scope

- create `initial_measurement` when a new `canonical_measurement` is created
- log pass-through or no-op VEE execution for obviously valid rows
- keep current finalization path active

### Acceptance gate

- new canonical rows always create initial rows
- new processing lineage is visible
- current downstream behavior remains stable

## Phase 3. VEE exception activation

### Goal

Begin persisting blocking processing exceptions explicitly.

### Scope

- evaluate first VEE baseline rules
- create `vee_exception` for blocking cases
- expose those exceptions in operator surfaces
- first active rules: `required_field_missing`, `negative_value_detected`, `duplicate_detected`

### Acceptance gate

- accepted path still promotes correctly
- blocking exception path prevents silent finalization
- operator can trace why finalization did not occur

## Phase 4. Finalization gate switch

### Goal

Make `final_measurement` depend on accepted processing state rather than only on minimal structural checks.

### Scope

- require accepted `initial_measurement`
- block finalization on open blocking `vee_exception`
- preserve `canonical_measurement_id` as compatibility lineage
- add `initial_measurement_id` to `final_measurement`
- backfill `initial_measurement_id` from existing `canonical_measurement_id` lineage where possible

### Acceptance gate

- final rows can be traced through initial and VEE lineage
- current minimal finalization semantics are replaced by explicit VEE-aware promotion
- regression remains stable on previously working canonical cases

## Phase 5. Usage persistence introduction

### Goal

Add the first downstream business output layer.

### Scope

- add `usage_transaction`
- support daily usage
- support monthly usage
- keep TOU and billing determinant logic deferred

### Acceptance gate

- usage depends only on `final_measurement`
- daily and monthly boundaries are testable
- timezone-local windowing is explicit

## Historical-data policy

Recommended first policy:

- keep existing data valid
- prioritize forward-correct behavior
- treat historical backfill as optional and bounded

Recommended first backfill if needed:

- create `initial_measurement` from selected historical canonical rows
- do not force synthetic historical VEE exceptions
- avoid expensive all-history reprocessing in the first rollout

## Testing strategy for the rollout

Each phase should carry its own regression gate.

### Phase 1 tests

- migrations
- unchanged finalization regression

### Phase 2 tests

- canonical to initial creation
- no-op VEE log creation

### Phase 3 tests

- blocking exception creation
- operator visibility

### Phase 4 tests

- finalization blocked by open exception
- finalization allowed after accepted or resolved state
- lineage from final back to raw through canonical and initial

### Phase 5 tests

- daily usage aggregation
- monthly usage aggregation
- partial and blocked usage behavior
- timezone-local boundary behavior

## Recommended immediate next implementation step

The next code phase should begin with:

1. `initial_measurement`
2. `vee_execution_log`
3. `vee_exception`

That gives the repository the first real processing/core persistence boundary without forcing immediate usage calculation or billing logic.
