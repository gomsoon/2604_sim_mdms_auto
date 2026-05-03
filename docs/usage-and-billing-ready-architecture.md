# Usage and Billing-Ready Architecture

## Purpose

This document defines the next processing/core structure after the current `raw -> canonical -> minimal final` baseline.

The goal is to move toward a true MDM flow in which:

- HES-originated reads become normalized internal measurements
- VEE decides whether those measurements are acceptable, corrected, or exceptional
- finalized measurements become the only trusted input to downstream usage calculation
- billing-oriented outputs are produced from standardized usage structures, not directly from HES-originated rows

## Current baseline

The repository currently has:

- `hes_read_raw`
- `canonical_measurement`
- `final_measurement`
- `pipeline_run`
- `processing_watermark`
- exception and operator visibility structures

This is a good minimal baseline, but it is not yet a full MDM processing core.

Important clarification:

- current `final_measurement` is still close to a `well_formed canonical promotion`
- it should not yet be treated as the long-term billing-authoritative final layer
- the missing boundary is the explicit `initial -> VEE -> final -> usage` structure

## Recommended target flow

Recommended long-term processing flow:

1. `hes_read_raw`
2. `canonical_measurement`
3. `initial_measurement`
4. `vee_execution_log`
5. `vee_exception`
6. `final_measurement`
7. `usage_transaction`
8. later `bill_determinant`

## Layer responsibilities

### `canonical_measurement`

Purpose:

- normalized output of raw-to-master mapping
- internal vendor-neutral measurement representation
- bridge between ingest/mapping and processing

Key rule:

- `canonical_measurement` is not yet the authoritative billing input

### `initial_measurement`

Purpose:

- first processing-stage measurement record prepared for VEE
- explicit handoff point between normalization and business validation

Why it is needed:

- separates mapping success from VEE acceptance
- gives re-VEE, estimation, and edit flows a clear starting point
- avoids overloading `canonical_measurement` with later business decisions

### `vee_execution_log`

Purpose:

- record one VEE processing attempt or rule pass over one scope
- preserve traceability of why a measurement or interval group passed, failed, or was adjusted

### `vee_exception`

Purpose:

- persist operator-visible VEE abnormalities
- separate data-quality/business-processing issues from raw ingest issues

### `final_measurement`

Purpose:

- authoritative finalized measurement used for downstream usage calculation

Key rule:

- a `final_measurement` should represent a VEE-accepted or explicitly resolved business outcome
- downstream usage calculation should depend on `final_measurement`, not directly on `canonical_measurement`

### `usage_transaction`

Purpose:

- persist consumption or usage values derived from finalized measurements
- provide a stable business output layer ahead of later billing determinant generation

## Recommended incremental transition

The repository should not jump directly from the current baseline to TOU and billing export logic.

Recommended transition:

### Phase A. Processing boundary clarification

- document `initial_measurement`
- document minimal VEE persistence
- document `usage_transaction` grain
- keep current `final_measurement` implementation working

### Phase B. Minimal processing persistence

- add `initial_measurement`
- add `vee_execution_log`
- add `vee_exception`
- redefine `final_measurement` promotion conditions

### Phase C. Minimal usage calculation

- introduce `usage_transaction`
- support daily usage
- support monthly usage
- keep TOU and bill determinant logic out of scope

## Recommended business rules for the next stage

### Before VEE

- `canonical_measurement` exists only when raw mapping succeeded
- duplicate raw rows should not produce new initial/final rows

### Before finalization

- `initial_measurement` is the processing entry point
- VEE must determine whether:
  - measurement is accepted as-is
  - measurement needs estimation or manual resolution
  - measurement becomes a VEE exception

### Before usage calculation

- `final_measurement` must be the only measurement source for usage calculation
- `usage_transaction` should never depend directly on vendor-specific raw semantics

## Billing-ready boundary

This project should distinguish:

- `usage-ready`
- `billing-ready`

Recommended interpretation:

- `usage_transaction` is usage-ready business output
- `bill_determinant` is billing-ready output

Examples:

- daily kWh sum: usage-ready
- monthly on-peak kWh by tariff bucket: billing-ready
- demand determinant with billing-cycle logic: billing-ready

This distinction keeps the next phase realistic and avoids overloading the first usage step.

## Optional billing-lite boundary

The project may later host a small optional `billing-lite` slice inside the MDM
without changing the core responsibility split.

Recommended interpretation:

- `MDM core` remains responsible for metering truth
- `bill_determinant` remains the billing-ready handoff output
- optional `billing-lite` may calculate a narrow set of charges for small-scale
  deployment or end-to-end testing
- full customer, contract, and financial workflow depth still belongs in a
  later CIS or enterprise billing platform

Why this is useful:

- it lets the team test the downstream usefulness of `usage_transaction` and
  `bill_determinant`
- it supports smaller deployments that do not yet have a separate CIS
- it still preserves a clear architectural boundary for future separation

Key rule:

the first `billing-lite` scope should stay downstream of `bill_determinant`.
It should not reach back into raw, canonical, or pre-VEE layers.

## Time and timezone rule

The repository should keep:

- canonical `measured_at` as `timestamp with time zone`
- source-local business time as source lineage where needed

Usage calculation must define its business windows using a local timezone rule such as:

- `service_point` timezone when available
- otherwise `hes_system` timezone

This becomes especially important for:

- daily usage
- monthly usage
- DST-aware window calculations

## Recommended next implementation sequence

1. add `initial_measurement` and minimal persistence rules
2. add `vee_execution_log` and `vee_exception`
3. tighten the meaning of `final_measurement`
4. add `usage_transaction`
5. later introduce `bill_determinant`

## Explicit deferrals

The following items should remain out of the first processing/core slice:

- advanced rule groups
- TOU rating
- demand determinant logic
- full billing-cycle logic
- CIS export
- approval workflow depth beyond minimal exception resolution

They may reappear later in a `billing-lite` or CIS-focused slice, but they do
not belong in the first processing/core boundary.

## Summary

The next processing/core milestone is not "billing calculation" yet.

The correct next milestone is:

- make the boundary between `canonical`, `initial`, `VEE`, `final`, and `usage` explicit
- treat `final_measurement` as the authoritative post-VEE layer
- introduce `usage_transaction` as the first downstream business output before billing-ready determinants
