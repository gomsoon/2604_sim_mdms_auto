# Invoice Summary Baseline Design

## Purpose

`invoice_summary` is the first lightweight billing-lite layer above
`bill_charge`.

The first slice is not a legal invoice, receivables artifact, or customer
document. It is an operator-facing and service-facing summary that groups
current bill charges into a reviewable billing-period bundle.

## First-slice scope

The first rollout should:

- remain a calculated read model with no dedicated persistence
- use only current `bill_charge` rows as the source of truth
- group by `service_point + billing period + currency + tariff plan`
- expose a small service-facing API surface for downstream consumers
- compute export eligibility without yet implementing the export queue itself

The first rollout should not yet include:

- invoice number allocation
- invoice persistence or immutable invoice snapshots
- PDF or print rendering
- tax, surcharge, discount, or subsidy calculation
- customer-facing invoice documents
- external-target-specific export payload contracts

## Grouping key

The baseline grouping key is:

1. `service_point_id`
2. `billing_period_start_at`
3. `billing_period_end_at`
4. `currency_code`
5. `tariff_plan_code`

This keeps the first summary aligned with the current `bill_charge` grain while
still being usable for operator review and later export preparation.

## Source rule

The source of truth is current `bill_charge` only.

- use `is_current = true`
- ignore superseded charge revisions by default
- do not read `bill_determinant` or `usage_transaction` directly from the
  summary layer

## Summary fields

The first summary row should expose at least:

- `service_point_id`
- `service_point_external_id`
- `billing_period_start_at`
- `billing_period_end_at`
- `currency_code`
- `tariff_plan_code`
- `charge_count`
- `complete_count`
- `partial_count`
- `blocked_count`
- `subtotal_amount`
- `summary_status`
- `export_eligible`
- `latest_calculated_at`

`subtotal_amount` is the sum of non-null `charge_amount` rows inside the group.

## Summary status rule

The first summary status rule should remain simple:

- all source charges `complete` -> summary `complete`
- any source charge `blocked` -> summary `blocked`
- otherwise, any source charge `partial` -> summary `partial`

This keeps the summary honest and aligned with current `bill_charge`
calculation status.

## Export eligibility

The first export-eligibility rule should be:

- `summary_status = complete` -> `export_eligible = true`
- `summary_status in {partial, blocked}` -> `export_eligible = false`

This intentionally prevents partial or blocked billing bundles from being
treated as export-ready in the first billing-lite rollout.

## Service-facing API

The first API slice should expose:

- `GET /api/v1/service-points/<service_point_id>/invoice-summary`

Recommended first filters:

- `date_from`
- `date_to`
- `tariff_plan_code`
- `summary_status`
- `external_channel_id`
- `charge_type`
- `calculation_status`
- `limit`

The response should be summary-oriented and should not imply full invoice
document semantics.

## Relationship to export queue

`invoice_summary` should come before the later billing export queue.

The expected progression is:

1. `bill_charge`
2. calculated `invoice_summary`
3. export queue payload snapshot
4. export status tracking
5. later external delivery integration

## Deferred follow-up

The following are intentionally deferred:

- invoice summary persistence
- invoice detail UI beyond the first summary list or API
- export queue and payload snapshot persistence
- export retry, cancel, and status lifecycle
- invoice-specific adjustments or reversals
