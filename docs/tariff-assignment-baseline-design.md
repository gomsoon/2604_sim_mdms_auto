# Tariff Assignment Baseline Design

## Purpose

This document defines the first minimal tariff-assignment slice that should sit
between `bill_determinant` and later optional `bill_charge` calculation.

The goal is to introduce only the minimum business context required to answer:

- which tariff plan applies to a service point
- when one tariff assignment starts and another ends
- how later charge calculation can remain deterministic and auditable

This is intentionally not a full tariff engine or CIS contract model.

## Why this is needed

The repository now has:

- `usage_transaction`
- `bill_determinant`
- `service_point_billing_context`
- optional `billing-lite` direction

That is enough to produce billing-ready determinants, but not enough to produce
charge-ready outputs.

The system needs a small explicit tariff-assignment model so that:

- later `bill_charge` calculation stops guessing which tariff should apply
- missing tariff context becomes explicit rather than silently assumed
- end-to-end billing-lite testing can stay deterministic

## Recommended boundary

This model should remain:

- downstream of `service_point` master data
- downstream of `service_point_billing_context`
- downstream of `bill_determinant` generation in the first implementation
- upstream of later `bill_charge` calculation

Recommended relationship:

- `service_point` owns tariff assignment
- `bill_determinant` may preserve a tariff snapshot later when a determinant
  type truly depends on tariff semantics
- the first `bill_charge` consumes `bill_determinant` plus tariff assignment

## Important first-stage rule

The first tariff-assignment baseline should not block the first
`billing_cycle_consumption_total` determinant.

Why:

- the current determinant baseline is meant to remain billing-ready
- tariff choice belongs more naturally to charge calculation than determinant
  calculation for the first simple consumption total
- this keeps the architectural boundary clear:
  - `bill_determinant` is billing-ready
  - `bill_charge` is charge-ready

Recommended first rule:

- missing billing context blocks determinant
- missing tariff assignment blocks later `bill_charge`
- tariff-aware determinant types may later tighten this rule if their business
  meaning genuinely depends on tariff semantics

## Recommended first table

Recommended first table name:

- `service_point_tariff_assignment`

This is intentionally narrower than:

- full tariff master
- contract-account relationship master
- CIS customer or financial account profile

## Recommended minimum fields

- `id`
- `service_point_id`
- `tariff_plan_code`
- `tariff_version_code`
- `effective_from`
- `effective_to`
- `is_current`
- `source_system`
- `source_reference`
- `details`
- `created_at`
- `updated_at`

## Field meaning

### `service_point_id`

The first tariff assignment should attach to the service point because:

- `usage_transaction` and `bill_determinant` are already anchored there
- the project does not yet carry a full contract-account model
- it keeps the first billing-lite scope small and practical

### `tariff_plan_code`

This is the minimum required business identifier for the first baseline.

It answers:

- which tariff family should be used for later charge calculation

Recommended first rule:

- required
- stable code, not a human-readable label

### `tariff_version_code`

This should remain optional in the first baseline.

Why:

- some deployments may only need one active tariff version at a time
- later tariff hardening may require explicit versioning, but the first design
  should not pretend that a full tariff catalog already exists

### `effective_from` and `effective_to`

These fields preserve assignment history over time.

Recommended interpretation:

- one service point may have many historical assignment rows
- only one row should be `is_current = true`
- effective periods should be interpreted as half-open windows:
  `effective_from <= target_ts < effective_to`

### `source_system` and `source_reference`

These preserve where the assignment came from, such as:

- manual operator setup
- later CIS sync
- migration import

## Recommended first business rules

### Current-row rule

Per `service_point_id`, only one row should be `is_current = true`.

### Overlap rule

The first implementation should prevent obviously overlapping active effective
periods for the same `service_point_id`.

### Required-field rule

- `tariff_plan_code` is required
- `effective_to` must be greater than `effective_from`

### Missing-assignment rule

Missing tariff assignment should not block the first determinant baseline.

Instead:

- determinant may still be `complete` or `partial` if billing context and usage
  are valid
- later charge calculation should become `blocked_missing_tariff_assignment`

This keeps the data-flow boundary honest.

## Recommended first integration with `bill_determinant`

The first integration should stay lightweight.

Recommended rule:

- do not add a hard FK from `bill_determinant` to
  `service_point_tariff_assignment` yet

Instead:

- keep determinant calculation independent from tariff assignment for the first
  `billing_cycle_consumption_total`
- later, when tariff-aware determinant types arrive, optionally copy a
  `tariff_assignment_snapshot` into `bill_determinant.details`

Why this is recommended:

- avoids premature coupling
- keeps the first determinant baseline simple and stable
- leaves room for later tariff-aware determinant expansion without forcing it
  too early

## Recommended first integration with `bill_charge`

The first real consumer of tariff assignment should be `bill_charge`.

Recommended rule:

- `bill_charge` looks up the applicable current tariff assignment
- if none exists, charge calculation becomes `blocked`
- charge calculation preserves a tariff-assignment snapshot in `details`

Recommended first snapshot:

- `tariff_assignment_id`
- `tariff_plan_code`
- `tariff_version_code`
- `effective_from`
- `effective_to`

## Recommended first management semantics

The first operator workflow should mirror billing-context management:

- view current tariff assignment
- create a new current assignment
- retain history
- automatically close the old current row when a new current row begins

This keeps the UX and persistence model aligned across billing-supporting
contexts.

## Explicit deferrals

The following should remain outside the first tariff-assignment baseline:

- full tariff rate catalog
- time-of-use period definition engine
- customer-specific contract eligibility logic
- seasonal exception logic
- subsidy or discount qualification
- tax and surcharge policy
- invoice posting semantics

These belong in later `billing-lite` hardening or a fuller CIS/billing platform.

## Recommended implementation sequence

1. document tariff-assignment boundary and first rules
2. add `service_point_tariff_assignment` persistence
3. add current-plus-history management UI in `master_data`
4. keep determinant independent for the first simple determinant type
5. later introduce `bill_charge` with tariff-assignment lookup

## Summary

The first tariff-assignment baseline should be a small service-point-scoped
current-plus-history model.

It should support later `bill_charge` calculation without prematurely turning
`bill_determinant` into a tariff-dependent layer.
