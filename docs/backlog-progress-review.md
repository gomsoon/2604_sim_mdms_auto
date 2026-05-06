# Backlog Progress Review

## Purpose

This document reviews the repository against the staged
[backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md) at a broader
level than the MVP-only gap review.

Its job is to answer four practical questions:

- how far each backlog area has progressed
- which areas have the highest current product importance
- which areas have the highest near-term implementation impact
- what the next realistic work sequence should be

This document is intentionally operational.

It is meant to help choose the next work slice, not to replace the backlog.

## Reading guide

Status labels in this review use the following meaning:

- `substantially implemented`
- `partially implemented`
- `lightly addressed`
- `not started`

Importance is judged from the product and MVP perspective.

Impact is judged from the engineering and operational leverage perspective.

## Current repository baseline

The repository now has all of the following practical baselines:

- raw read and raw event ingest
- canonical conversion
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
- async bulk `re-VEE`
- operator-triggered estimation
- operator-triggered manual edit
- event-linked VEE baseline for outage and tamper context
- broad operator visibility across batch, HES, VEE, usage, determinant, charge,
  replay, estimation, and manual edit flows

This means the repository is no longer only a minimal ingest-and-canonical
prototype.

It now behaves much more like an early end-to-end MDM plus billing-lite test
platform.

## Phase 1. Minimal End-to-End Version

### M1. Project skeleton

- Status: `substantially implemented`
- Importance: `medium`
- Impact: `low`

Current baseline:

- Flask application baseline exists
- environment separation exists
- PostgreSQL baseline exists
- health path and common runtime structure exist

Remaining notes:

- this area is no longer a major delivery constraint
- remaining work is mostly maintenance, not product expansion

### M2. Core MDM data model

- Status: `substantially implemented`
- Importance: `high`
- Impact: `high`

Current baseline:

- minimal core entities exist
- raw, canonical, initial, final, usage, determinant, charge, and audit layers
  are all present
- migrations are established

Remaining notes:

- future structural work should be incremental, not foundational
- partitioning and long-term scale tuning remain later concerns

### M3. HES raw read and event ingestion

- Status: `substantially implemented`
- Importance: `high`
- Impact: `medium`

Current baseline:

- read ingest exists
- event ingest exists
- ingest error handling exists
- operational ingest visibility exists

Remaining notes:

- this area still has room for source-specific hardening
- but the baseline needed for processing-core work is already present

### M4. Minimal master data management

- Status: `substantially implemented`
- Importance: `high`
- Impact: `medium`

Current baseline:

- service point, device, measuring component, installation management exist
- billing context and tariff assignment are also now present in `master_data`
- HES meter reference baseline exists

Remaining notes:

- source sync and bulk management remain later work
- operator governance and comparison views can still deepen

### M5. Canonical measurement conversion

- Status: `substantially implemented`
- Importance: `high`
- Impact: `medium`

Current baseline:

- raw-to-canonical mapping exists
- timestamp normalization exists
- raw lineage is preserved
- conversion exceptions are visible

Remaining notes:

- future source-specific conversion rules may still grow
- baseline capability is already in place

### M6. Raw and canonical data visibility

- Status: `substantially implemented`
- Importance: `medium`
- Impact: `medium`

Current baseline:

- ingest batch, raw read, raw event, canonical views exist
- operational event visibility exists
- drill-down is already strong

Remaining notes:

- spotlight quality can still improve
- basic visibility baseline is no longer a major gap

## Phase 2. MVP Version

### V1. Initial and final measurement structure

- Status: `substantially implemented`
- Importance: `high`
- Impact: `high`

Current baseline:

- `canonical_measurement`, `initial_measurement`, and `final_measurement` are
  clearly separated
- current-plus-history final revision exists
- finalization is tied to VEE and exception state

Remaining notes:

- this structure now supports estimation and manual edit
- the main work is no longer foundational modeling here

### V2. Basic VEE engine

- Status: `partially implemented`
- Importance: `high`
- Impact: `high`

Current baseline:

- VEE persistence exists
- replay and operator control exist
- event-linked baseline now exists
- active rules include:
  - required-field
  - duplicate
  - negative
  - zero
  - interval size
  - missing interval
  - high value

Main remaining work:

- `UOM validation` as a real first-class rule
- `multiplier validation` as a real first-class rule
- `low value` baseline
- review whether duplicate should remain blocking or warning by policy

Recommendation:

- this is now one of the strongest candidates for a short closure sprint

### V3. Basic estimation

- Status: `partially implemented`
- Importance: `high`
- Impact: `high`

Current baseline:

- substitution-only estimation exists
- `linear_interpolation` exists
- `previous_value_based` exists
- `estimation_audit` exists
- downstream recalculation closes through usage, determinant, and charge
- operator UI exists in `vee_exception` detail

Main remaining work:

- synthetic missing-interval estimation
- bulk estimation
- preview and approval workflow
- broader exception-code coverage
- event-aware estimation policy

Recommendation:

- first MVP slice is in place
- next work here should be deferred until VEE closure is clearer

### V4. Exception management

- Status: `substantially implemented`
- Importance: `high`
- Impact: `medium`

Current baseline:

- VEE exception query/detail exists
- acknowledge, resolve, re-evaluate exist
- async replay request and progress exist

Remaining notes:

- this area is operationally strong already
- future work is mostly policy hardening and convenience

### V5. Manual edits and audit

- Status: `partially implemented`
- Importance: `high`
- Impact: `high`

Current baseline:

- substitution-only manual edit exists
- `manual_edit_audit` exists
- operator UI exists in `vee_exception` detail
- audit list/detail visibility exists
- downstream recalculation closes through usage, determinant, and charge

Main remaining work:

- approval workflow
- bulk manual edit
- broader correction coverage
- event-aware correction policy
- compare-and-preview workspace

Recommendation:

- first MVP slice is now in place
- not the highest-priority next area unless operators need more policy depth

### V6. Usage calculation

- Status: `substantially implemented`
- Importance: `high`
- Impact: `medium`

Current baseline:

- daily and monthly usage exist
- timezone-aware windowing exists
- quality summary exists
- replay-driven recalculation visibility exists

Main remaining work:

- clearer service-point usage API contract
- broader downstream business-facing service boundary

Recommendation:

- baseline is strong enough for now
- next work here should be API-facing refinement, not core algorithm work

### V7. Event-linked decisioning

- Status: `partially implemented`
- Importance: `medium`
- Impact: `medium`

Current baseline:

- outage and tamper context lookup exists
- event-aware missing-interval behavior exists
- event-aware negative/high-value behavior exists
- event context is visible in `vee_exception` detail

Main remaining work:

- zero-value event-linked policy
- duration-aware event windows
- event-aware estimation
- event-aware manual edit
- spotlight/list-level event-linked operations visibility

Recommendation:

- first baseline is now in place
- not the highest-priority next VEE item until first-class VEE rule gaps close

## Phase 3. Product Version

### P1. Advanced VEE rule framework

- Status: `lightly addressed`
- Importance: `medium`
- Impact: `medium`

Current baseline:

- the rule engine is usable, but still code-backed and intentionally simple

Main remaining work:

- rule groups
- sequencing
- effectivity
- targeting by domain context

Recommendation:

- clearly later than MVP rule completion

### P2. TOU and bill determinant generation

- Status: `partially implemented`
- Importance: `medium`
- Impact: `medium`

Current baseline:

- first determinant baseline exists
- revision and visibility exist

Main remaining work:

- TOU
- demand
- power factor
- richer billing-cycle alignment

Recommendation:

- later product-phase work

### P3. Billing integration

- Status: `partially implemented`
- Importance: `medium`
- Impact: `medium`

Current baseline:

- billing-lite boundary exists
- billing context exists
- tariff assignment exists
- `bill_charge` baseline exists

Main remaining work:

- richer tariff engine
- blocked-charge operator spotlight
- invoice summary
- export queue and payload contract

Recommendation:

- repository is already ahead here compared with the original MVP
- avoid expanding this area before VEE closure unless billing-lite testing
  requires it

### P4. CIS integration

- Status: `not started`
- Importance: `low`
- Impact: `low`

Current baseline:

- boundary is documented, but no real CIS integration slice exists yet

Recommendation:

- intentionally later

### P5. Aggregation and reporting

- Status: `lightly addressed`
- Importance: `low`
- Impact: `low`

Current baseline:

- some dashboard and spotlight capabilities exist

Main remaining work:

- broader aggregation and export/report shape

Recommendation:

- later than core MVP closure

### P6. Security and authorization

- Status: `lightly addressed`
- Importance: `medium`
- Impact: `medium`

Current baseline:

- there is not yet a strong product-grade RBAC or sensitive-action isolation
  layer

Recommendation:

- important for productization, but not the best next step in current flow

### P7. Operability and reprocessing

- Status: `partially implemented`
- Importance: `high`
- Impact: `medium`

Current baseline:

- replay, re-VEE, re-finalization-style downstream recalculation, adapter run
  control, and operator visibility are all strong

Main remaining work:

- broader re-map / re-ingest / bulk policy closure
- deeper queue and recovery behavior

Recommendation:

- baseline is already good enough for current MVP work

## Cross-cutting observations

### The repository is ahead downstream and still slightly behind in basic VEE closure

The repository is now ahead of the original MVP wording in:

- billing context
- tariff assignment
- bill determinant
- bill charge
- replay visibility
- operator correction flows

At the same time, the remaining “small but important” upstream processing gaps
are concentrated in:

- first-class VEE rule completeness
- usage API/service boundary polish
- policy depth around operator correction and event context

### The next best work is probably not a brand-new subsystem

At this point, the highest-leverage next step is likely a short
`VEE closure mini-sprint`, not another new downstream module.

Recommended order:

1. `UOM validation`
2. `multiplier validation`
3. `low value` baseline
4. short review of whether `usage_transaction` needs an explicit service-point
   API closure for MVP wording

## Recommended near-term sequence

### Priority 1. Backlog review refresh

- keep this review aligned with actual repository state
- use it as the next-planning reference instead of the older MVP-only view

### Priority 2. VEE closure mini-sprint

- close the remaining first-class VEE baseline rule gaps
- define explicit closure criteria for V2

### Priority 3. Usage API and service boundary review

- confirm whether `usage_transaction` already satisfies the MVP expectation
- if not, add a thin service-point-facing usage API slice

### Priority 4. Billing-lite actionability only if testing pressure requires it

- invoice summary
- charge/export visibility

These should stay secondary unless end-to-end testing specifically needs them
next.

## Summary

The repository is no longer missing broad end-to-end capability.

Instead, it is now in a refinement stage where the biggest value comes from:

1. closing the remaining small but meaningful VEE gaps
2. tightening service-facing boundaries around usage and billing-lite outputs
3. resisting the urge to open too many new product-phase subsystems too early
