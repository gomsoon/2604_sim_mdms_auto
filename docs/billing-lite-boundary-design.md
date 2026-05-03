# Billing-Lite Boundary Design

## Purpose

This document defines an optional `billing-lite` boundary that may live inside
the MDM system without turning the MDM into a full CIS or enterprise billing
platform.

The goal is to support:

- small-scale tariff-based billing
- end-to-end testing of MDM outputs without waiting for a separate CIS
- practical downstream validation for `usage_transaction` and `bill_determinant`

while still preserving a clear boundary between:

- `MDM core`
- optional `billing-lite`
- later `CIS` or enterprise billing integration

## Why this boundary is useful

The original system direction remains valid:

- `MDM` handles ingest, normalization, VEE, finalization, usage, and
  billing-ready determinants
- `CIS` or a separate billing system handles customer, contract, tariff,
  invoice, receivable, and customer-service workflows

However, as the MDM grows more complete, two practical needs appear:

1. the team needs a realistic way to test whether MDM-produced outputs are
   truly billing-usable
2. smaller deployments may benefit from a minimal billing capability even when a
   full CIS is not yet available

That means the repository should allow a narrow `billing-lite` slice without
blurring the long-term architectural boundary.

## Position in the flow

Recommended downstream flow:

- `hes_read_raw`
- `canonical_measurement`
- `initial_measurement`
- `vee_execution_log`
- `vee_exception`
- `final_measurement`
- `usage_transaction`
- `bill_determinant`
- optional `billing-lite`
- later CIS integration or full billing export

`billing-lite` should therefore be treated as:

- downstream of `bill_determinant`
- optional for minimal or small-scale deployments
- replaceable by a later external CIS or billing platform

## What stays in MDM core

The following responsibilities should remain part of the MDM core:

- source ingest and lineage
- raw-to-canonical normalization
- VEE and re-VEE
- final measurement revision handling
- usage calculation
- bill determinant generation
- operational replay and processing traceability

These are still MDM responsibilities even if `billing-lite` is never built.

## What `billing-lite` may include

The first optional `billing-lite` slice may include:

- billing context lookup for a service point
- tariff assignment lookup
- deterministic bill charge calculation from `bill_determinant`
- small invoice summary generation
- operator-visible recalculation lineage from determinant to charge

This should remain intentionally narrow.

Recommended first outputs:

- `bill_charge`
- optional `invoice_summary`

Recommended first charge types:

- simple volumetric energy charge
- simple fixed charge
- tax or surcharge placeholders only if explicitly modeled

## What should remain outside `billing-lite`

The following should remain outside the first `billing-lite` scope and stay in a
later CIS or enterprise billing platform:

- customer lifecycle management
- rich contract lifecycle management
- complex tariff versioning and eligibility logic
- settlement and receivables
- payment collection
- bill cancellation and reissue workflow depth
- customer service workflow integration
- dispute handling and financial posting

Key rule:

`billing-lite` may calculate charges, but it should not try to become the full
system of record for customer and financial operations.

## Why this helps testing

Minimal billing capability is useful even before a separate CIS exists because
it lets the team verify:

- whether `usage_transaction` and `bill_determinant` are sufficient inputs
- whether determinant lineage survives replay and supersession
- whether tariff-context gaps are surfaced as `blocked` instead of silently
  guessed
- whether recalculation after `re-VEE` produces stable downstream outcomes

That makes `billing-lite` a practical end-to-end validation slice, not only a
product feature.

## Recommended first design boundaries

The first `billing-lite` design should stay narrow and explicit:

1. `bill_determinant` remains the only source input
2. tariff calculation remains code-backed and small in scope
3. billing context is explicit, versioned, and auditable
4. missing billing context should produce `blocked`, not guessed, results
5. export to CIS remains a separate later boundary

## Recommended minimal supporting context

The next required design work should define a small billing context model.

Recommended minimum:

- `service_point_billing_context`
- `timezone_name`
- `billing_cycle_mode`
- `billing_cycle_anchor_day`
- `effective_from`
- `effective_to`
- `is_current`

Recommended next supporting model after that:

- minimal tariff assignment
- deterministic rate input structure

These should be designed before charge calculation is implemented.

## Recommended first implementation sequence

1. lock the `billing-lite` boundary
2. define billing context baseline
3. define minimal tariff assignment baseline
4. add `bill_charge` persistence and revision semantics
5. add one simple volumetric charge calculation path
6. later add optional invoice summary output

## Summary

The recommended direction is not to turn MDM into a full CIS.

The recommended direction is:

- keep MDM core focused on metering truth and billing-ready determinants
- allow an optional `billing-lite` slice for small deployments and end-to-end
  testing
- preserve a clean replacement path for later CIS integration
