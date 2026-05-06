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

Status: substantially implemented

Current state:

- `vee_execution_log` and `vee_exception` persistence exist
- operator visibility and replay flows exist
- active rules already include:
  - required-field checks
  - unit-of-measure validation
  - multiplier unity-only guardrail validation
  - duplicate detection
  - negative value detection
  - zero value warning
  - low-value micro warning
  - interval size validation
  - missing interval detection
  - high-value validation
  - first outage/tamper event-linked behavior

Remaining MVP gap:

- high/low logic remains intentionally shallow and code-backed
- multiplier handling remains intentionally guardrail-first rather than
  source-aware
- duplicate severity policy may still need later review

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
- a first read-only `service_point` usage API slice now exists

Remaining notes:

- the repository now has both operator visibility and a first service-facing
  usage API slice
- later work here is refinement, not baseline existence

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

1. deeper policy layers around estimation, manual edit, and event context
2. richer source-aware VEE policy beyond the first closure baseline
3. later service-facing refinement beyond the first usage API slice

That means the next MVP work should probably focus on closure and refinement in
the core processing loop rather than going deeper into billing first.

## Recommended next priorities

### Priority 1. Policy-depth review for correction flows

Recommended first next step:

- choose the next deeper slice intentionally:
  - broader estimation coverage
  - broader manual edit coverage
  - event-aware correction policy

Why first:

- first baselines now exist for VEE, estimation, manual edit, event-linked
  decisioning, and service-facing usage access
- the next increment should be chosen deliberately instead of widening all
  policy areas at once

### Priority 2. Richer source-aware VEE policy later

Recommended second next step:

- revisit VEE only when new source-aware or business-aware context exists
- examples:
  - source multiplier lineage
  - richer low-value policy basis
  - duplicate severity policy review

Why second:

- the first VEE closure sprint is now complete enough for MVP baseline
- the remaining VEE work is more about policy depth than first-class rule
  presence

### Priority 3. Usage API refinement only if consumers need more

Recommended third next step:

- keep the new `service_point` usage API thin unless a real caller needs more
- examples:
  - summary endpoint
  - determinant or charge linkage in API shape
  - business-facing export contract

Why third:

- a first read-only usage API slice already exists
- the next step should respond to actual caller needs, not speculative surface
  growth

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
