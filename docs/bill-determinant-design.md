# Bill Determinant Design

## Purpose

This document defines the first billing-ready determinant layer that should follow
`usage_transaction`.

The goal is to introduce a downstream structure that is:

- billing-oriented
- recalculable
- traceable back to usage and finalized measurements
- still separated from invoice creation, pricing, and export concerns

## Position in the data flow

Recommended downstream flow:

- `hes_read_raw`
- `canonical_measurement`
- `initial_measurement`
- `vee_execution_log`
- `vee_exception`
- `final_measurement`
- `usage_transaction`
- `bill_determinant`
- later billing export or CIS integration

`bill_determinant` should therefore be treated as:

- downstream of post-VEE usage calculation
- upstream of billing export, invoice generation, and customer-facing billing APIs

It should also be treated as the natural handoff point into any optional
`billing-lite` module that may be hosted inside the MDM for small deployments
or end-to-end testing.

## Why `bill_determinant` is needed

`usage_transaction` is intentionally simpler than billing-ready output.

It captures usage-safe business aggregates such as:

- daily consumption
- monthly consumption
- usage quality and missing-interval visibility

That is necessary, but not sufficient for billing-oriented workflows.

Billing-ready processing typically needs:

- billing-cycle alignment
- tariff or TOU bucket semantics
- demand window semantics
- determinant-specific quality interpretation
- recalculation lineage when upstream final or usage values change

Without a separate determinant layer, those concerns would either:

- leak into `usage_transaction`
- or be repeatedly reimplemented by downstream systems

`bill_determinant` keeps that boundary explicit.

## Boundary from `usage_transaction`

Recommended interpretation:

- `usage_transaction` is usage-ready
- `bill_determinant` is billing-ready

Examples:

- daily kWh total: `usage_transaction`
- monthly kWh total: `usage_transaction`
- billing-cycle consumption total: `bill_determinant`
- on-peak or off-peak billed consumption: `bill_determinant`
- billing-cycle maximum demand: `bill_determinant`
- average power factor for settlement: `bill_determinant`

Key rule:

`bill_determinant` should not collapse `usage_transaction`.

The determinant layer should consume stable usage outputs, not replace them.

It also should not collapse a later optional billing layer.

Recommended interpretation:

- `usage_transaction` is usage-ready
- `bill_determinant` is billing-ready
- optional `billing-lite` is charge-ready
- later CIS or enterprise billing is customer-and-finance ready

This extra boundary lets the repository support limited tariff-based billing
without turning determinant persistence into invoice logic.

## Source rule

`bill_determinant` must be derived from `usage_transaction`.

It should not directly depend on:

- `hes_read_raw`
- source vendor tables
- unresolved `canonical_measurement`
- pre-VEE `initial_measurement`
- direct HES-side tariff semantics

This keeps the determinant layer:

- vendor-neutral
- replayable
- aligned with post-VEE authoritative data

Important clarification:

some future determinant types may require new upstream `usage_transaction`
types before they can be implemented safely.

Examples:

- TOU determinants need TOU-aware usage rows
- demand determinants may need dedicated demand candidate or interval-window usage rows

That means the determinant layer should be implemented in lockstep with
the required usage shapes, not by bypassing usage.

## Recommended first determinant baseline

The first determinant rollout should start with the simplest billing-ready type:

- `billing_cycle_consumption_total`

Why:

- the repository already has `monthly_consumption` usage
- full TOU, demand, and power-factor logic still need more upstream usage and contract context
- this keeps the first determinant implementation realistic

Recommended later determinant types:

- `tou_on_peak_consumption`
- `tou_off_peak_consumption`
- `maximum_demand`
- `average_power_factor`

## Recommended grain

The first determinant grain should be:

- one row per determinant type
- per settlement subject
- per billing-oriented window

Recommended minimum business dimensions:

- `service_point_id`
- optional `measuring_component_id`
- optional `device_id`
- `determinant_type`
- `billing_period_start_at`
- `billing_period_end_at`
- `window_timezone_name`
- optional `tariff_plan_code`
- optional `tou_bucket_code`
- optional `demand_window_code`
- `unit_of_measure`

Recommended minimum business measures:

- `determinant_value`
- `source_usage_count`
- `quality_summary`
- `calculation_status`

## Recommended minimum fields

- `id`
- `pipeline_run_id`
- `service_point_id`
- `measuring_component_id`
- `device_id`
- `determinant_type`
- `billing_period_start_at`
- `billing_period_end_at`
- `window_timezone_name`
- `tariff_plan_code`
- `tou_bucket_code`
- `demand_window_code`
- `unit_of_measure`
- `determinant_value`
- `source_usage_count`
- `quality_summary`
- `calculation_status`
- `revision_number`
- `revision_reason_code`
- `is_current`
- `supersedes_bill_determinant_id`
- `calculated_at`
- `details`
- `created_at`
- `updated_at`

## Determinant type baseline

Recommended initial catalog:

- `billing_cycle_consumption_total`

Deferred catalog:

- `tou_on_peak_consumption`
- `tou_off_peak_consumption`
- `maximum_demand`
- `average_power_factor`

Key rule:

the first determinant implementation should activate only determinant types that
are fully supported by existing upstream usage shapes.

## Billing window rule

`usage_transaction` currently uses:

- `hes_system.timezone_name` as the first operational timezone fallback

`bill_determinant` needs a stronger business window rule because billing periods
are not always identical to calendar months.

Recommended long-term rule:

- billing windows should use service-point or contract billing timezone
- billing windows should be aligned to explicit billing-cycle boundaries

First design constraint:

- the repository does not yet persist a full contract or billing-cycle model
- the first determinant baseline should therefore document billing-cycle context
  as a prerequisite rather than pretending it already exists

Recommended first implementation rule:

- only implement determinant types whose billing window can be derived explicitly
  from current known context
- if billing-cycle alignment is unknown, determinant calculation should be
  `blocked`, not guessed

## Quality and status semantics

Recommended baseline `calculation_status`:

- `complete`
- `partial`
- `blocked`

Recommended interpretation:

- `complete`: all required source usage rows and billing context were present
- `partial`: determinant was calculated, but source usage was partial or warning-bearing
- `blocked`: determinant could not be safely derived because usage, tariff, or billing context was incomplete

Key rule:

supersession should not be represented by `calculation_status`.

Instead:

- `is_current = false` marks superseded determinant history
- `revision_number` and `supersedes_bill_determinant_id` preserve lineage

## Provenance and source linkage

`bill_determinant` should preserve enough provenance to support:

- replay
- audit
- export troubleshooting
- re-billing after upstream change

Recommended provenance in `details`:

- `trigger_type`
- `trigger_source`
- contributing `usage_transaction` identifiers
- contributing current `final_measurement` identifiers when needed for audit explanation
- optional replay context such as:
  - `vee_execution_log_id`
  - `vee_replay_request_id`
  - previous/current usage lineage when determinant was recalculated after replay

Important note:

if source usage cardinality becomes too large for inline provenance, the next
step should be a helper relation such as `bill_determinant_source` rather than
dropping lineage entirely.

## Revision and recalculation rule

`bill_determinant` should be revision-capable from its first persistence design.

Why:

- `final_measurement` already has current-plus-history supersession
- `usage_transaction` can be recalculated after `re-VEE` and re-finalization
- determinants must therefore be able to keep current and historical business outputs

Recommended rule:

- one current determinant row per determinant business key
- later recalculation supersedes the old current row rather than overwriting it

Recommended business key for current-row uniqueness:

- `service_point_id`
- `measuring_component_id`
- `determinant_type`
- `billing_period_start_at`
- `billing_period_end_at`
- `tariff_plan_code`
- `tou_bucket_code`
- `demand_window_code`
- `is_current = true`

The exact PostgreSQL partial unique shape can be refined later, but the business
intent should be fixed now.

Recommended revision reasons:

- `usage_recalculated`
- `vee_re_evaluated`
- `operator_correction`
- `billing_context_changed`
- `re_determined`

## Relationship to billing export

`bill_determinant` is still not the export queue itself.

Recommended sequencing:

1. calculate determinants
2. preserve determinant revision lineage
3. only then generate billing export payloads or API responses

This avoids coupling determinant generation to a particular external billing interface.

## Explicit deferrals

The following should remain out of the first determinant slice:

- invoice line pricing
- tax logic
- customer balance logic
- contract-dispute workflow
- external billing export queue implementation
- CIS-facing customer summary APIs

## Recommended implementation sequence

1. document determinant grain and source rule
2. document prerequisite billing-cycle and tariff context
3. implement minimal determinant persistence
4. activate `billing_cycle_consumption_total`
5. later expand usage shapes needed for TOU and demand determinants
6. only after that introduce billing export contracts

## Summary

`bill_determinant` should be the first true billing-ready persistence layer.

Its job is to:

- consume stable `usage_transaction` outputs
- apply billing-oriented window and determinant semantics
- preserve revision-capable lineage for recalculation
- stay clearly separate from both raw measurement processing and actual invoice/export logic
