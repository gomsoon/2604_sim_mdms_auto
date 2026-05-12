# Billing Export Queue Design

## Purpose

`billing_export_queue` is the first persistence-backed staging layer above the
calculated `invoice_summary`.

The first slice should not yet perform real downstream delivery. It should
capture immutable export payload snapshots, track request and item lifecycle,
and expose enough worker-progress metadata for operators to understand whether
processing is advancing or stale.

## First-slice scope

The first rollout should:

- treat `invoice_summary` as the source calculation layer
- snapshot exportable summaries into queue-backed request and item records
- support only a generic target such as `generic_json`
- support worker claim, processing, heartbeat, and completion state
- expose request-level progress and stale-signal metadata

The first rollout should not yet include:

- external target-specific payload mapping
- real downstream delivery
- webhook, callback, or receipt reconciliation
- auto-reclaim or auto-recovery of stale workers
- dedicated worker registry persistence
- export analytics dashboards beyond simple request and item status

## Source rule

The source of truth remains current calculated `invoice_summary`.

The queue should snapshot that calculated state into immutable export payload
records so that later charge revisions do not change what an already-queued
export intended to send.

## Export eligibility rule

The first eligibility rule should remain strict:

- `summary_status = complete` -> queueable
- `summary_status in {partial, blocked}` -> not exportable

The request-creation layer may either reject non-exportable summaries or record
them as skipped items. The first implementation should prefer skipped-item
visibility so operators can see why a request was only partially queueable.

## Persistence

The first persistence model should use:

1. `billing_export_request`
2. `billing_export_item`

`billing_export_request` is the operator and worker lifecycle record.

`billing_export_item` is the immutable per-summary export snapshot record.

## Request fields

`billing_export_request` should include at least:

- `request_scope`
- `status`
- `service_point_id`
- `billing_period_from`
- `billing_period_to`
- `target_system_code`
- `payload_format`
- `requested_by`
- `operator_memo`
- `item_count`
- `processed_count`
- `succeeded_count`
- `failed_count`
- `skipped_count`
- `claimed_by`
- `started_at`
- `completed_at`
- `last_heartbeat_at`
- `last_error`
- `details`

## Item fields

`billing_export_item` should include at least:

- `billing_export_request_id`
- `service_point_id`
- `billing_period_start_at`
- `billing_period_end_at`
- `currency_code`
- `tariff_plan_code`
- `summary_status`
- `status`
- `result_code`
- `payload_snapshot`
- `exported_at`
- `last_error`
- `details`

## Payload snapshot

The first payload snapshot should contain at least:

- `invoice_summary_snapshot`
- `source_bill_charge_rows`
- `request_context_snapshot`

This keeps the first export queue deterministic even if later current
`bill_charge` rows change.

## Status model

Request status:

- `queued`
- `processing`
- `completed`
- `failed`
- `cancelled`

Item status:

- `pending`
- `processing`
- `completed`
- `failed`
- `skipped`

## Worker visibility

The first rollout should expose worker-state visibility at the request level.

Required fields:

- `claimed_by`
- `last_heartbeat_at`
- `processed_count`
- `item_count`
- `succeeded_count`
- `failed_count`
- `skipped_count`
- `last_error`

Recommended `details` keys:

- `progress_percent`
- `remaining_count`
- `current_item_id`
- `current_service_point_id`
- `current_billing_period_start_at`
- `current_billing_period_end_at`
- `last_processed_item_id`
- `last_processed_result_code`

The first rollout should interpret staleness in the visibility layer rather
than introducing a separate worker registry. For example, a request with
`status=processing` and an old `last_heartbeat_at` may be marked stale by a
later read model.

## Worker concurrency

The first rollout should allow multiple workers overall, but only one worker
may claim a specific `billing_export_request` at a time.

Processing inside one request should remain serial in the first slice.

This keeps progress tracking, payload snapshot mutation, and counter updates
simple and consistent with the current replay-worker baseline.

## Request scope

The first request scope should remain small:

- `service_point_period`

This means the request targets one service point and a bounded billing-period
window, from which one or more exportable invoice summaries may be derived.

## Control model

The first control model should remain conservative:

- queued request cancel: supported
- processing request pause: not supported
- processing request hard stop: not supported

## Relationship to later export status

The first queue baseline should stop at:

1. request creation
2. item snapshot persistence
3. worker claim and heartbeat
4. request and item lifecycle state

Later work may add:

- export request list and detail UI
- payload preview and download
- retry or recreate flow
- external-target-specific delivery adapters
- export receipt or ack tracking
