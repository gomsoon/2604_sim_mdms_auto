# Billing Context Baseline Design

## Purpose

This document defines the first minimal billing-context slice needed before the
repository can safely move from `bill_determinant` into optional `billing-lite`
charge calculation.

The goal is to introduce only the minimum business context required to answer:

- what timezone defines the billing window
- how billing-cycle boundaries are aligned
- when one billing context stops and another begins

This is intentionally not a full contract or CIS model.

## Why this is needed

The repository already has:

- `usage_transaction`
- `bill_determinant`
- determinant revision and visibility

However, the current determinant baseline still relies on an operationally
useful but business-light assumption:

- `monthly_consumption` can stand in for the first
  `billing_cycle_consumption_total`

That is acceptable as a first bridge, but it is not enough for a stable
billing-oriented path.

The system needs a small explicit billing-context model so that:

- billing windows are no longer implied or guessed
- determinant calculation can explain why a period exists
- missing business context becomes `blocked` rather than silently incorrect

## Recommended boundary

This model should remain:

- downstream of master data
- upstream of charge calculation
- independent from customer-account and receivables workflows

Recommended relationship:

- `service_point` owns billing context
- `bill_determinant` consumes billing context
- later optional `bill_charge` consumes determinant plus tariff context

## Recommended first table

Recommended first table name:

- `service_point_billing_context`

This is intentionally narrower than:

- full contract master
- billing account master
- CIS customer profile

## Recommended minimum fields

- `id`
- `service_point_id`
- `timezone_name`
- `billing_cycle_mode`
- `billing_cycle_anchor_day`
- `currency_code`
- `effective_from`
- `effective_to`
- `is_current`
- `source_system`
- `source_reference`
- `details`
- `created_at`
- `updated_at`

## Field meaning

### `service_point_id`

The first billing context should attach to the service point because:

- `usage_transaction` and `bill_determinant` are already anchored there
- it is a stable business subject before a fuller contract model exists

### `timezone_name`

Defines the business timezone for billing windows.

This should eventually become stronger than the current operational fallback:

- `hes_system.timezone_name`

### `billing_cycle_mode`

Recommended first catalog:

- `calendar_month`
- `anchored_month`

Why:

- `calendar_month` is enough to stabilize the current determinant baseline
- `anchored_month` gives the project a path toward non-calendar cycles without
  introducing full contract complexity yet

### `billing_cycle_anchor_day`

Required only when `billing_cycle_mode = anchored_month`.

Recommended first constraint:

- allow only `1..28`

Why:

- this avoids complicated month-end rollover rules in the first implementation
- it is enough to prove the architecture before handling 29/30/31 edge cases

### `currency_code`

This is not strictly needed for determinant generation, but it becomes useful
very quickly for downstream `billing-lite` charge calculation.

Recommended first rule:

- optional in persistence
- required before the first real charge calculation is considered `complete`

### `effective_from` and `effective_to`

These fields let the project retain history when billing context changes over
time.

Recommended interpretation:

- one service point may have many historical rows
- only one row should be `is_current = true`

### `source_system` and `source_reference`

These fields preserve where the billing context came from, such as:

- manual operator setup
- later CIS sync
- migration import

## Recommended first business rules

### Current-row rule

Per `service_point_id`, only one row should be `is_current = true`.

### Overlap rule

The first implementation should prevent obviously overlapping active effective
periods for the same `service_point_id`.

The minimal baseline does not need a sophisticated temporal engine, but it
should avoid contradictory current context.

### Mode rule

- `calendar_month`
  - `billing_cycle_anchor_day` should be null
- `anchored_month`
  - `billing_cycle_anchor_day` is required

### Missing-context rule

If a valid current billing context cannot be found for a determinant candidate,
the downstream result should be:

- `blocked`

not guessed.

This is the most important safety rule in the whole baseline.

## Recommended first integration with `bill_determinant`

The first integration should stay lightweight.

Recommended rule:

- do not add a hard FK from `bill_determinant` to
  `service_point_billing_context` yet

Instead:

- look up the current billing context during determinant calculation
- copy a billing-context snapshot into `bill_determinant.details`
- set `calculation_status = blocked` when context is missing or incompatible

Why this is recommended:

- avoids premature schema coupling
- keeps determinant revisions replayable from source usage and context snapshot
- allows later migration to a stronger FK if needed

## Recommended billing-context snapshot

The first `bill_determinant.details` snapshot should include:

- `billing_context_id`
- `billing_cycle_mode`
- `billing_cycle_anchor_day`
- `timezone_name`
- `currency_code`
- `effective_from`
- `effective_to`

This makes downstream tracing much easier even before a full charge layer exists.

## What this model should not try to do yet

The first billing-context baseline should not include:

- customer account
- contract terms
- tariff versioning
- tax policy
- discount programs
- invoice recipient
- receivable ownership

Those belong to a later `billing-lite` or CIS-focused expansion.

## Recommended next steps after this baseline

1. persist `service_point_billing_context`
2. teach `bill_determinant` calculation to require or snapshot it
3. define minimal tariff assignment
4. add first `bill_charge` design

## Summary

The first billing-context baseline should be a small, auditable,
service-point-scoped current-plus-history model.

Its primary job is not to replace CIS.

Its primary job is to stop the repository from guessing billing windows and to
give `bill_determinant` and later `billing-lite` flows a trustworthy business
context.
