# Usage Transaction Design

## Purpose

This document defines the first structure for `usage_transaction`, the layer between finalized measurements and later billing-ready determinants.

The intent is to make downstream business output explicit without jumping immediately to TOU, demand, or billing-cycle logic.

## Position in the data flow

Recommended processing flow:

- `hes_read_raw`
- `canonical_measurement`
- `initial_measurement`
- `vee_execution_log`
- `vee_exception`
- `final_measurement`
- `usage_transaction`
- later `bill_determinant`

`usage_transaction` should therefore be treated as:

- downstream of VEE and finalization
- upstream of billing-ready determinant generation

## Why `usage_transaction` is needed

Without an explicit usage layer, downstream systems would either:

- query `final_measurement` directly and reimplement usage logic repeatedly
- or force `final_measurement` itself to carry aggregation semantics it should not own

`usage_transaction` avoids both problems by making usage calculation a first-class persistent result.

## Recommended first grain

The first grain should be intentionally simple.

Recommended baseline grain:

- one row per usage scope and time window

Recommended minimum dimensions:

- `service_point_id`
- `measuring_component_id`
- optional `device_id`
- `usage_type`
- `period_start_at`
- `period_end_at`
- `interval_size_minutes`
- `unit_of_measure`

Recommended minimum measures:

- `usage_value`
- `source_final_count`
- `missing_interval_count`
- `quality_summary`
- `calculation_status`

## Recommended minimum fields

- `id`
- `service_point_id`
- `measuring_component_id`
- `device_id`
- `usage_type`
- `period_start_at`
- `period_end_at`
- `interval_size_minutes`
- `unit_of_measure`
- `usage_value`
- `source_final_count`
- `missing_interval_count`
- `quality_summary`
- `calculation_status`
- `calculated_at`
- `details`
- `created_at`
- `updated_at`

## Recommended `usage_type` baseline

The first stage should keep `usage_type` small.

Recommended initial values:

- `daily_consumption`
- `monthly_consumption`

Later values may include:

- `on_peak_consumption`
- `off_peak_consumption`
- `maximum_demand`
- `power_factor`

## Recommended `calculation_status` baseline

- `complete`
- `partial`
- `blocked`

Recommended interpretation:

- `complete`: all required finalized measurements were present
- `partial`: usage was calculated but some intervals were missing or flagged
- `blocked`: usage was not safely calculable

## Source rule

`usage_transaction` must be derived only from `final_measurement`.

It should not directly depend on:

- `hes_read_raw`
- vendor-specific source tables
- unresolved `canonical_measurement`

This keeps downstream business outputs stable and vendor-neutral.

## Windowing and timezone rule

The first usage layer must define time windows carefully.

Recommended rule:

- local business windows should use the service-point timezone when available
- otherwise use the parent `hes_system` timezone

This matters for:

- daily usage
- monthly usage
- DST-aware day boundaries
- cross-country deployments

## First calculation modes

The first implementation should support only simple aggregation modes.

Recommended baseline:

- interval sum into daily usage
- interval sum into monthly usage

Deferred:

- TOU bucket splitting
- billing cycle alignment
- demand windows
- contract-aware determinants

## Quality semantics

The first usage layer should preserve enough quality context to remain operationally useful.

Recommended fields or details:

- `source_final_count`
- `missing_interval_count`
- `quality_summary`
- optional quality flags in `details`

This allows downstream consumers and operators to distinguish:

- trustworthy usage
- partial usage
- blocked usage

## Relationship to billing-ready outputs

Recommended interpretation:

- `usage_transaction` is usage-ready
- `bill_determinant` is billing-ready

Examples:

- daily kWh total: usage-ready
- monthly kWh total: usage-ready
- on-peak/off-peak split by tariff: billing-ready
- maximum demand aligned to billing cycle: billing-ready

## Testing expectations

The first usage design should later be validated with:

- same-day aggregation
- cross-day boundary aggregation
- cross-month aggregation
- timezone-local day boundary behavior
- partial final set behavior
- blocked usage behavior

## Summary

The first `usage_transaction` layer should be simple, explicit, and downstream-safe.

Its job is to:

- persist business usage outputs from finalized measurements
- provide a stable bridge toward later billing-ready determinants
- avoid mixing raw, VEE, and billing semantics into one table
