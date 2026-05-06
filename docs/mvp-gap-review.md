# MVP Gap Review

## Purpose

This document reviews the current repository baseline against the MVP backlog in
[backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md).

It is not a replacement for the backlog.

Its job is simpler:

- show which MVP capabilities are already substantially present
- show which MVP capabilities are only partially present
- show which MVP capabilities are still largely untouched
- recommend the next few development priorities

## Review baseline

Current repository baseline now includes:

- `initial_measurement`
- `vee_execution_log`
- `vee_exception`
- current-plus-history `final_measurement`
- `usage_transaction`
- `bill_determinant`
- `service_point_billing_context`
- `service_point_tariff_assignment`
- `bill_charge`
- synchronous single-object `re-VEE`
- async bulk `re-VEE` request and worker baseline
- operator-triggered estimation
- operator-triggered manual edit
- event-linked VEE baseline for outage and tamper context
- broad operator visibility across dashboard, HES detail, usage, determinant,
  charge, and replay flows

This means the repository has already moved beyond a narrow MVP reading in some
downstream areas, especially around billing-lite.

At the same time, some core MVP backlog items are still only lightly addressed
or not addressed at all.

## MVP backlog review

### V1. Initial and final measurement structure

Status: substantially implemented

Current state:

- `canonical_measurement`, `initial_measurement`, and `final_measurement` are
  explicitly separated
- `final_measurement` now supports current-plus-history revision lineage
- finalization is gated by VEE outcome and open blocking exceptions

Remaining notes:

- later estimation and manual-edit flows will still need to interact with this
  structure
- the structure itself is no longer the main MVP gap

### V2. Basic VEE engine

Status: partially implemented, but still incomplete against backlog

Current state:

- `vee_execution_log` and `vee_exception` persistence exist
- operator visibility and replay flows exist
- active rules already include:
  - required-field checks
  - duplicate detection
  - negative value detection
  - zero value warning
  - interval size validation
  - missing interval detection
  - high-value validation
  - first outage/tamper event-linked behavior

Remaining MVP gap:

- `UOM validation` is not yet a real first-class rule path
- `multiplier validation` is not yet present as a real rule path
- `low value` is not yet a real first-class rule path
- high/low logic remains intentionally shallow and code-backed

### V3. Basic estimation

Status: partially implemented

Current state:

- substitution-only estimation exists
- `linear_interpolation` exists
- `previous_value_based` exists
- explicit `estimation_audit` persistence exists
- operator-visible estimation handling exists
- update flow into current `final_measurement` exists

What is still missing:

- synthetic missing-interval estimation
- bulk estimation
- preview and approval workflow
- broader exception-code coverage
- event-aware estimation policy

This is no longer untouched, but it is still intentionally narrow.

### V4. Exception management

Status: substantially implemented

Current state:

- `vee_exception` persistence exists
- query/list/detail visibility exists
- status transitions exist
- acknowledge, resolve, and re-evaluate flows exist
- async bulk replay visibility exists

Remaining notes:

- this area is already in a good MVP state
- future work is more about hardening and policy depth than basic existence

### V5. Manual edits and audit

Status: partially implemented

Current state:

- substitution-only manual edit exists
- explicit `manual_edit_audit` persistence exists
- operator-visible manual edit handling exists
- final regeneration and downstream recalculation exist

What is still missing:

- approval workflow
- bulk manual edit
- broader correction coverage
- event-aware correction policy
- preview-and-compare correction workspace

This is no longer untouched, but it is still intentionally narrow.

### V6. Usage calculation

Status: substantially implemented

Current state:

- `usage_transaction` persistence exists
- daily and monthly usage exist
- timezone-aware local windowing exists
- quality summary and missing-interval visibility exist
- usage list/detail and replay-driven recalculation visibility exist

Remaining notes:

- the MVP backlog says `Service-point usage API`
- the repository already has strong operator visibility, but the usage layer can
  still be made more explicitly service-oriented in API shape if needed

### V7. Event-linked decisioning

Status: partially implemented

Current state:

- `operational_event` and alert visibility are strong
- outage and tamper context matching now exist
- event-aware VEE behavior now exists for:
  - `missing_interval`
  - `negative_value`
  - `high_value`
- `vee_exception` detail now shows matched event context

What is still missing:

- richer event-duration modeling
- zero-value event-linked policy
- event-aware estimation policy
- event-aware manual edit policy
- broader event-linked operational spotlight

Important distinction:

- the repository now both *shows* and *uses* events in selected VEE decisions
- it still does not yet use event context broadly across all correction and
  estimation policies

## Cross-cutting MVP observations

### The repository is ahead in downstream billing-lite

Compared with the original MVP backlog wording, the repository is now ahead in
some downstream areas:

- `bill_determinant`
- `service_point_billing_context`
- `service_point_tariff_assignment`
- `bill_charge`

These are useful and coherent additions, especially for end-to-end testing and
small-scale billing-lite validation.

They do not remove the remaining MVP gaps above.

### The main unfinished MVP areas are not billing-first

The repository already has strong downstream visibility and billing-lite
structure.

The more important remaining MVP gaps are now concentrated in:

1. remaining first-class VEE rule completeness
2. service-point-facing usage API boundary clarity
3. deeper policy layers around estimation, manual edit, and event context

That means the next MVP work should probably focus on closure and refinement in
the core processing loop rather than going deeper into billing first.

## Recommended next priorities

### Priority 1. Basic VEE closure

Recommended first next step:

- close the remaining first-class rule gaps:
  - `UOM validation`
  - `multiplier validation`
  - `low value`

Why first:

- this is now the shortest path to closing V2 cleanly
- it increases confidence in every downstream layer already built on top of VEE

### Priority 2. Usage API boundary review

Recommended second next step:

- review whether current `usage_transaction` visibility already satisfies the
  MVP `service-point usage API` expectation
- if not, add a thin service-facing usage API slice

Why second:

- V6 is mostly complete already
- boundary review is cheaper than another new subsystem

### Priority 3. Policy-depth review for correction flows

Recommended third next step:

- choose the next deeper slice intentionally:
  - broader estimation coverage
  - broader manual edit coverage
  - event-aware correction policy

Why third:

- the first baseline now exists for all three areas
- the next increment should be chosen deliberately instead of growing all three
  at once

## Explicit non-priorities for the next MVP pass

The following can remain deferred while the MVP gap is being closed:

- TOU determinants
- demand determinants
- advanced tariff engine
- invoice rendering
- CIS export hardening
- broader billing-lite expansion

These are valid later targets, but they are not the main missing MVP pieces
right now.

## Summary

The repository is no longer missing "basic downstream billing-shaped outputs."

Instead, the most important remaining MVP gaps are now:

1. `Basic VEE engine closure`
2. `Usage API and service-boundary polish`
3. `Policy-depth expansion for estimation, manual edit, and event-linked correction`

The recommended next direction is therefore:

- return to the processing core
- close the remaining VEE baseline rule gaps first
- then review whether usage needs a thinner service-facing API closure
- then choose the next deeper correction-policy slice intentionally
