# Bill Charge Baseline Design

## Purpose

This document defines the first `bill_charge` baseline that may sit on top of
`bill_determinant` inside the optional `billing-lite` slice.

The goal is to introduce a downstream structure that is:

- charge-oriented
- recalculable
- traceable back to determinant and tariff context
- intentionally narrower than invoice or CIS workflows

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
- `bill_charge`
- later optional `invoice_summary`
- later CIS handoff or enterprise billing integration

Recommended interpretation:

- `usage_transaction` is usage-ready
- `bill_determinant` is billing-ready
- `bill_charge` is charge-ready

## Why `bill_charge` is a separate layer

`bill_determinant` is still not a charge.

It tells downstream systems what billing-ready quantity exists, but it does not
yet answer:

- which tariff applies
- which unit rate should be used
- what charge amount should be persisted
- which determinant revisions forced downstream recalculation

Without a separate `bill_charge` layer, those concerns would either:

- leak back into `bill_determinant`
- or be repeatedly reimplemented in exports and downstream systems

`bill_charge` keeps the boundary explicit.

## Source rule

`bill_charge` must be derived from `bill_determinant`.

It should not directly depend on:

- `usage_transaction`
- `final_measurement`
- raw HES data
- implicit source-side tariff semantics

Required supporting context:

- applicable `service_point_billing_context`
- applicable `service_point_tariff_assignment`

Key rule:

`bill_charge` should use determinant output plus explicit billing and tariff
context. It should not guess either of them.

## First calculation scope

The first `bill_charge` rollout should stay intentionally narrow.

Recommended initial determinant support:

- `billing_cycle_consumption_total`

Recommended initial charge support:

- `flat_energy_charge`

Recommended first formula:

- `charge_amount = quantity_value * unit_rate_value`

Where:

- `quantity_value` comes from `bill_determinant.determinant_value`
- `unit_rate_value` comes from a small code-backed or later persisted tariff
  rate input

## What is intentionally out of scope

The first `bill_charge` baseline should not include:

- TOU bucket pricing
- demand charges
- tax calculation
- discount or subsidy rules
- minimum charge logic
- fuel adjustment logic
- bill cancellation and rebill workflow
- invoice document rendering
- payment, receivable, or settlement handling

These must remain in backlog until the first flat-rate charge path is stable.

## Minimum grain

Recommended first grain:

- one row per service point
- per determinant type
- per billing period
- per charge type

Recommended minimum business dimensions:

- `service_point_id`
- optional `measuring_component_id`
- optional `device_id`
- `bill_determinant_id`
- `charge_type`
- `billing_period_start_at`
- `billing_period_end_at`
- `currency_code`
- `tariff_plan_code`
- optional `tariff_version_code`

Recommended minimum business measures:

- `quantity_value`
- `unit_rate_value`
- `charge_amount`
- `calculation_status`
- `quality_summary`

## Recommended minimum fields

- `id`
- `pipeline_run_id`
- `service_point_id`
- `measuring_component_id`
- `device_id`
- `bill_determinant_id`
- `charge_type`
- `billing_period_start_at`
- `billing_period_end_at`
- `currency_code`
- `tariff_plan_code`
- `tariff_version_code`
- `quantity_value`
- `unit_rate_value`
- `charge_amount`
- `calculation_status`
- `quality_summary`
- `revision_number`
- `revision_reason_code`
- `is_current`
- `supersedes_bill_charge_id`
- `calculated_at`
- `details`
- `created_at`
- `updated_at`

## Status and quality semantics

Recommended baseline `calculation_status`:

- `complete`
- `partial`
- `blocked`

Recommended baseline `quality_summary`:

- `flat_energy_rate_applied`
- `source_partial_determinant`
- `blocked_missing_billing_context`
- `blocked_missing_tariff_assignment`
- `blocked_missing_tariff_rate`
- `blocked_unsupported_charge_type`

Important rules:

- if source determinant is `blocked`, charge must be `blocked`
- if source determinant is `partial`, charge may remain `partial`
- missing tariff assignment must produce `blocked`, not guessed charge output
- missing rate input must produce `blocked`, not `0`

## Billing and tariff context rule

The first charge baseline should use:

- `service_point_billing_context` for timezone and billing-cycle business
  window truth
- `service_point_tariff_assignment` for applicable tariff plan and optional
  version

The first implementation should not yet require:

- full customer contract persistence
- tariff eligibility rules beyond one applicable assignment per service point

Recommended persistence approach:

- lookup context rows at calculation time
- store snapshots in `details`

Snapshot examples:

- `billing_context_snapshot`
- `tariff_assignment_snapshot`

This keeps replay and recalculation deterministic even if current context later
changes.

## Revision model

`bill_charge` should start with the same `current + history` baseline already
used by `final_measurement` and `bill_determinant`.

Recommended behavior:

- if the current charge snapshot is unchanged, reuse it
- if determinant value, tariff assignment, or rate changes, supersede the old
  current row
- keep previous charge history instead of overwriting it

Why:

- re-VEE or re-finalization may change determinant values
- billing context or tariff assignment may change after the first charge
  calculation
- downstream testing needs explicit before/after lineage

## Rate input baseline

The first rate baseline should remain intentionally simple.

Recommended initial approach:

- code-backed flat rate registry keyed by
  - `tariff_plan_code`
  - optional `tariff_version_code`
  - `charge_type`

Why:

- it lets the repository validate charge-ready flow without prematurely
  designing a full tariff engine
- it keeps the first implementation deterministic and testable

Recommended later expansion:

- persisted tariff rate table
- effective-dated rate versions
- TOU bucket rates
- demand charge rates

## First implementation sequence

1. lock the `bill_charge` boundary in documentation
2. add `bill_charge` persistence and revision baseline
3. add minimal charge calculation service
4. support one `flat_energy_charge` path from
   `billing_cycle_consumption_total`
5. add visibility and revision drill-down
6. later add optional `invoice_summary`

## Backlog items intentionally deferred

The following items should be kept visible in backlog rather than pulled into
the first implementation:

- TOU charge rules
- demand charge rules
- tax and surcharge calculation
- invoice summary persistence
- billing export payload and outbound queue
- bill cancellation and rebill workflow
- customer account and receivable integration

## Summary

The first `bill_charge` baseline should not try to become a full tariff engine
or a CIS-owned billing platform.

The recommended direction is:

- derive charges only from `bill_determinant`
- require explicit billing and tariff context
- support one small flat-rate charge path first
- preserve revision and recalculation lineage from determinant to charge
