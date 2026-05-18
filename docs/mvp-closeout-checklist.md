# MVP Close-out Checklist

## Purpose

This document defines what "MVP close-out" means for the current repository
baseline.

It is intentionally narrower than the full backlog.

Its job is to answer three practical questions:

- is the system usable now as an internal operator product
- which capabilities are treated as MVP-close-out required
- which limitations are accepted at close-out and deferred to later work

## Current close-out assessment

Current assessment: `close-out candidate`

Reasoning:

- the repository now supports the core ingest -> canonical -> initial -> VEE ->
  final -> usage -> determinant -> charge loop
- operators can inspect, correct, replay, and re-run the most important flows
- human-user authentication and account-level audit baselines now exist
- sensitive correction and export actions now carry `user_account` lineage

This means MVP close-out no longer depends on a missing foundational subsystem.

The remaining work is mostly:

- accepted functional narrowness
- known operating limitations
- later hardening and usability polish

Recommended decision:

- proceed with MVP close-out after one bounded smoke pass
- do not open new subsystems before first internal operator feedback

## Close-out required baseline

The following are treated as required for MVP close-out.

### 1. Core measurement flow

- raw read and raw event ingest
- canonical conversion
- `initial_measurement`
- `vee_exception`
- current-plus-history `final_measurement`

### 2. Correction and replay flow

- VEE exception visibility and status transitions
- synchronous single-object re-VEE
- async bulk re-VEE request and worker baseline
- substitution estimation
- single-slot synthetic missing-interval estimation
- substitution manual edit
- downstream recalculation through usage, determinant, and charge

### 3. Event-aware baseline

- outage and tamper context lookup
- first event-aware VEE behavior for missing interval and selected value
  anomalies
- event context visibility in exception detail

### 4. Billing-lite baseline

- `usage_transaction`
- `bill_determinant`
- `service_point_billing_context`
- `service_point_tariff_assignment`
- `bill_charge`
- `invoice_summary`
- billing export request queue, visibility, cancel, and recovery actions

### 5. Operator visibility baseline

- dashboard
- ingest/raw/canonical visibility
- VEE queue and detail
- estimation audit detail
- manual edit audit detail
- replay visibility
- export visibility
- HES and adapter visibility

### 6. Auth and accountability baseline

- `login_id + password` session login
- `admin` versus `operator`
- `auth_session_audit`
- `user_action_audit`
- actor lineage on:
  - VEE
  - estimation
  - manual edit
  - replay
  - billing export
  - master-data admin mutation
  - adapter runtime admin actions

## Accepted close-out limitations

The following limitations are accepted for MVP close-out and do not block first
internal use.

### Estimation limitations

- estimation is still intentionally narrow
- synthetic missing-interval repair is single-slot only
- bulk estimation does not exist
- approval and preview workflow do not exist

### Manual edit limitations

- manual edit is still substitution-oriented
- bulk manual edit does not exist
- approval workflow does not exist
- compare-and-preview workspace does not exist

### VEE limitations

- multiplier handling is still unity-guardrail-first
- low-value policy is still a narrow micro-warning
- duplicate severity may still need business review

### Event-policy limitations

- zero-value event-aware policy is not yet implemented
- duration-aware event windows are not yet implemented
- event-aware estimation/manual-edit policy is still intentionally narrow

### Auth maturity limitations

- no user-management UI
- no password reset or account recovery flow
- no token or PAT baseline for non-browser clients
- only first-slice `admin` versus `operator` RBAC exists

### Runtime and export limitations

- worker/runtime registry is still string-based
- item-level actor lineage is intentionally deferred in some runtime/export
  areas
- recovery and export are internal staging flows, not full downstream delivery

## Recommended close-out smoke checks

The following operator checks should pass before declaring close-out.

See also:

- [mvp-smoke-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-smoke-runbook.md)
- [mvp-known-limitations.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-known-limitations.md)

1. Login as `admin` and as `operator`.
2. Ingest raw reads and raw events successfully.
3. Confirm canonical and final measurement lineage.
4. Open a VEE exception and perform:
   - acknowledge
   - re-evaluate
   - estimation or manual edit on a supported case
5. Perform a single-slot synthetic missing-interval repair on a supported case.
6. Confirm downstream recalculation through usage, determinant, and charge.
7. Review `invoice_summary`.
8. Create a billing export request and exercise:
   - detail visibility
   - cancel
   - rerun or recreate on a failed request
9. Confirm master-data admin mutation records actor lineage.
10. Confirm adapter pause/enable/run-once records actor lineage.

## Short hardening and operating polish before close-out

The following short items are recommended before close-out.

1. Run the bounded smoke pass once in operator order.
2. Share the accepted limitations with internal operators before first use.
3. Prefer bug fix, policy clarification, and visibility polish over new
   subsystem expansion.

## Post-close-out operating mode

After MVP close-out, the recommended next mode is:

- follow [mdms-preproduct-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-plan.md)
- use the system in a bounded internal setting
- collect real operating friction, missing policy, and bug reports
- prefer targeted hardening and usability work over new subsystem expansion

## Not required for close-out

The following are explicitly not required for MVP close-out:

- TOU determinants
- demand charge
- advanced tariff engine
- invoice rendering
- CIS integration
- MFA
- full account management UI
- broader workflow automation around approvals and bulk correction
