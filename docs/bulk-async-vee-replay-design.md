# Bulk Async Re-VEE Replay Design

## Purpose

This document defines the first queue-backed replay baseline for `re-VEE` beyond the current single-object synchronous operator flow.

The immediate goal is not a full processing scheduler. It is a safe baseline for:

- HES-scoped replay
- batch-scoped replay
- date-range replay

while preserving the existing `single vee_exception -> synchronous replay` path for narrow operator actions.

## Why this is needed

The current manual baseline works well for one `vee_exception`, one `initial_measurement`, and a small amount of directly impacted downstream work.

It is not a good fit for:

- HES-wide correction after master-data changes
- batch-wide replay after source or mapping fixes
- bounded date-range replay across many measurements
- long-running replay work that needs queueing, retries, progress visibility, and result auditing

For those cases, `pipeline_run` alone is not enough.

`pipeline_run` is execution truth, but operators also need a persistent request object that explains:

- what was requested
- which scope was selected
- how many targets were found
- how many were processed successfully
- what failed
- whether usage recalculation happened downstream

## Scope of the first async baseline

The first async replay baseline should stay intentionally narrow.

### Included

- request scopes:
  - `hes_system`
  - `ingest_batch`
  - `date_range`
- target set:
  - only `initial_measurement` rows that currently have active `vee_exception`
- execution model:
  - asynchronous background processing only
- downstream behavior:
  - re-VEE
  - re-finalization when the measurement becomes acceptable again
  - targeted daily/monthly usage recalculation when the authoritative final changes

### Deferred

- rule-version mass replay without an existing active exception
- replay by arbitrary service point list
- replay by arbitrary measuring component list
- scheduled automatic replay after master-data correction
- cancellation and resume semantics beyond a simple `queued/processing/completed/failed/cancelled` lifecycle
- distributed worker execution across multiple processes

## Design principles

### Separate request truth from execution truth

The replay request itself is not the same thing as a processing attempt.

- `vee_replay_request` should capture operator intent and queue state
- `pipeline_run` should capture the actual execution attempt

This mirrors the way adapters and pipelines already distinguish operational objects from runtime executions.

### Reuse single-object replay logic

Bulk replay should not invent a second replay algorithm.

The queue-backed worker should reuse the existing single-object orchestration in:

- `reevaluate_vee_exception_and_replay(...)`

That keeps business rules, final supersession, and usage recalculation in one place.

### Keep narrow requests synchronous, broad requests asynchronous

The user experience boundary should remain:

- single `vee_exception` detail action stays synchronous
- HES / batch / date-range replay becomes asynchronous

### Prefer explicit items over implicit progress counting

The first async baseline should keep request items explicitly.

That makes progress, retries, and failure inspection much easier than trying to infer them from summary counts alone.

## Recommended persistence

### `vee_replay_request`

This is the operator-facing queue record.

Recommended columns:

- `id`
- `request_scope`
  - `hes_system`
  - `ingest_batch`
  - `date_range`
- `status`
  - `queued`
  - `processing`
  - `completed`
  - `failed`
  - `cancelled`
- `requested_by`
- `operator_memo`
- `hes_system_id` nullable
- `ingest_batch_id` nullable
- `measured_at_from` nullable
- `measured_at_to` nullable
- `window_timezone_name` nullable
- `target_initial_count`
- `processed_count`
- `succeeded_count`
- `failed_count`
- `reopened_exception_count`
- `cleared_exception_count`
- `final_superseded_count`
- `usage_recalculated_count`
- `started_at`
- `completed_at`
- `last_error`
- `details`

Recommended indexes:

- `status`
- `request_scope`
- `hes_system_id`
- `ingest_batch_id`
- `requested_by`
- `created_at`

### `vee_replay_request_item`

This is the per-target progress record.

Recommended columns:

- `id`
- `vee_replay_request_id`
- `initial_measurement_id`
- `representative_vee_exception_id`
- `status`
  - `pending`
  - `processing`
  - `completed`
  - `failed`
  - `skipped`
- `result_code`
- `vee_execution_log_id` nullable
- `previous_final_measurement_id` nullable
- `current_final_measurement_id` nullable
- `details`

Recommended unique constraint:

- `unique(vee_replay_request_id, initial_measurement_id)`

Recommended indexes:

- `vee_replay_request_id`
- `status`
- `initial_measurement_id`

### `pipeline_run` linkage

The first async baseline should link execution attempts back to the request.

Recommended column on `pipeline_run`:

- `vee_replay_request_id` nullable FK

This allows:

- one request to have one main pipeline run in the simple case
- future retry attempts to create more than one `pipeline_run` if needed

## Request creation behavior

### Request sources

The first baseline may allow replay requests from:

- HES detail
- ingest batch detail
- future replay request form for date-range replay

### Target discovery

Target discovery should be based on active exceptions, not all measurements.

Recommended steps:

1. Identify active `vee_exception` rows within the selected scope.
2. Convert them to distinct `initial_measurement_id` targets.
3. Choose one active `vee_exception` as the representative replay entry point for each target.
4. Create `vee_replay_request_item` rows from that deduplicated set.

This keeps the first baseline conservative and aligned with the current operator mental model.

## Worker behavior

### High-level flow

1. Claim one `vee_replay_request` with `status = queued`.
2. Mark request `processing`.
3. Start a `pipeline_run` with `pipeline_name = "vee_replay"`.
4. Iterate through `pending` request items.
5. For each item:
   - mark `processing`
   - call `reevaluate_vee_exception_and_replay(...)`
   - capture the returned replay summary
   - persist item result details
   - update aggregate request counters
6. Mark request `completed` or `failed`.
7. Complete or fail the linked `pipeline_run`.

### Error strategy

The first baseline should be item-tolerant.

That means:

- one failed item should not fail the whole request immediately
- the request should finish all items it can
- the request is `completed` when all items are processed and no item failed
- the request is `failed` when one or more items failed

## Aggregate counters

The request should expose simple operator-facing counters, even though item details remain available.

Recommended aggregate counters:

- `target_initial_count`
- `processed_count`
- `succeeded_count`
- `failed_count`
- `reopened_exception_count`
- `cleared_exception_count`
- `final_superseded_count`
- `usage_recalculated_count`

These should be updated incrementally as items complete.

## UI and UX baseline

### Request creation

The first async UI baseline should be intentionally simple.

- operator selects a scope
- operator submits a replay request
- UI redirects to a replay request detail page

### Request detail page

The detail page should show:

- request scope
- current request status
- requested by / requested at
- counts for processed, succeeded, failed
- counts for reopened, cleared, superseded, recalculated
- recent failed items
- related pipeline run
- links to impacted `vee_exception`, `final_measurement`, and `usage_transaction` detail pages where available

### Progress principle

Operators must be able to answer:

- how many targets were found
- how many have already been processed
- how many failed
- whether replay only reopened exceptions or also changed final and usage layers

## Operational-event baseline

The first async replay baseline should add these high-level events:

- `vee_replay_requested`
- `vee_replay_started`
- `vee_replay_completed`
- `vee_replay_failed`

The existing item-level events remain useful and should be reused:

- `vee_re_evaluated`
- `final_measurement_superseded`
- `usage_recalculated_after_vee`

## Testing baseline

The first async replay baseline should be gated by:

### Persistence tests

- request creation
- request item creation and dedupe
- request-to-pipeline linkage

### Service tests

- HES request discovery
- batch request discovery
- date-range request discovery
- worker processes all items
- partial item failure marks request failed but preserves successful items
- aggregate counters match item outcomes

### Web tests

- request creation form or action
- request detail rendering
- queue status visibility

### Full regression

- `./.venv/bin/ruff check app tests docs`
- `git diff --check`
- `./.venv/bin/pytest --cov-fail-under=80`

## Recommended implementation sequence

1. document the async replay boundary and persistence model
2. add `vee_replay_request`
3. add `vee_replay_request_item`
4. link `pipeline_run` to replay requests
5. add request creation service
6. add replay worker service
7. add request detail UI
8. add regression coverage

## Relation to later work

This baseline should make later processing/core work easier, not harder.

It provides the queue and execution structure needed for:

- scheduled replay after master-data correction
- rule-version replay
- bulk re-finalization
- broader usage recalculation jobs
- future billing-ready replay workflows
