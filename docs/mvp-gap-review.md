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
  - basic high-value warning

Remaining MVP gap:

- `UOM validation` is not yet a real first-class rule path
- `multiplier validation` is not yet present as a real rule path
- high/low logic remains intentionally shallow and code-backed
- event-aware rule effects are not yet part of the baseline

### V3. Basic estimation

Status: largely not started

Current state:

- documents repeatedly preserve room for estimation
- revision-capable `final_measurement` now makes later estimated outcomes
  structurally possible

What is still missing:

- linear interpolation flow
- previous-value-based estimation flow
- explicit estimation audit persistence
- operator-visible estimated outcome handling
- update flow from estimated result into current `final_measurement`

This is the clearest unimplemented MVP feature area.

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

Status: largely not started

Current state:

- there is strong revision lineage for `final_measurement`,
  `bill_determinant`, and `bill_charge`
- operator actions are auditable through events and pipeline runs

What is still missing:

- manual edit API or UI
- reason-code-driven manual correction flow
- approver/editor identity model
- explicit manual edit audit table or equivalent persistent record
- manual-edit-triggered final regeneration flow

This is the second major untouched MVP area after estimation.

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

Status: lightly addressed, but not implemented as a real MVP capability

Current state:

- `operational_event` and alert visibility are strong
- VEE exceptions, replay, finalization, and usage recalculation all emit and
  consume operational visibility

What is still missing:

- outage and tamper context matching
- event-aware VEE rule behavior
- event-linked exception generation beyond general event visibility

Important distinction:

- the repository already *shows* events well
- it does not yet *use* events deeply in VEE or estimation decisions

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

The more important remaining MVP gaps are now:

1. estimation
2. manual edit and audit
3. event-linked decisioning

That means the next MVP work should probably move back upstream into the core
processing loop rather than going deeper into billing first.

## Recommended next priorities

### Priority 1. Estimation baseline

Recommended first next step:

- define a minimal estimation boundary
- pick one or two strategies only
  - linear interpolation
  - previous-value-based estimation
- persist explicit estimation audit
- update `final_measurement` through revision rather than overwrite

Why first:

- it closes the largest untouched MVP gap
- it fits the current revision-capable processing structure well
- it improves end-to-end MDM realism more than another billing-lite extension

### Priority 2. Manual edit and audit baseline

Recommended second next step:

- manual edit request model or direct operator action baseline
- reason codes
- operator identity capture
- audit persistence
- final regeneration through current-plus-history revision

Why second:

- it is a natural companion to estimation
- it gives operators a practical resolution path beyond VEE acknowledge/resolve

### Priority 3. Event-linked decisioning baseline

Recommended third next step:

- define one or two event-aware rules only
- start with outage or tamper context matching
- keep the first integration narrow and auditable

Why third:

- event visibility is already strong
- the next improvement is to make that event context affect actual decisions

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

1. `Basic estimation`
2. `Manual edits and audit`
3. `Event-linked decisioning`

The recommended next direction is therefore:

- return to the processing core
- close estimation first
- then add manual correction and audit
- then connect operational events more directly into business decisioning
