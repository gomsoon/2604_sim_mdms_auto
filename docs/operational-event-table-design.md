# Operational Event Table Design

## Purpose

This document turns the minimal event and alert baseline into a concrete persistence design.

It defines the first recommended table shape for:

- operator-facing operational events
- alert state as a subset of those events

## Design scope

This document is intended to be:

- specific enough to drive ORM and migration work
- small enough to stay believable in the minimal stage

It is not yet:

- a full notification platform design
- a full incident-management design
- a production-tuned archival policy
- a physically separated current-alert and alert-history storage platform
- a database-backed alert-condition management system

## Core recommendation

Use one primary append-only table named `operational_event`.

Do not create a separate `alert` table in the first implementation unless real operator workflow proves it is necessary.

Instead:

- every important milestone becomes an operational event
- urgent or operator-actionable conditions are marked with alert fields on that same row

This keeps the first implementation simpler and avoids two overlapping history models.

## Row meaning

One row equals one operator-meaningful event that happened in the system.

Examples:

- one adapter run was queued
- one adapter run failed
- one ingest batch was accepted
- one canonical run failed
- one finalization run completed
- one adapter overdue condition was detected

## Recommended table

### `operational_event`

### Recommended columns

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `occurred_at` | `timestamptz` | Yes | when the event happened |
| `source_layer` | `varchar(30)` | Yes | `integration`, `ingest`, `processing`, `system`, `operator_action` |
| `event_category` | `varchar(40)` | Yes | grouped event area such as `adapter_run`, `ingest_batch`, `pipeline_run` |
| `event_code` | `varchar(100)` | Yes | machine-readable event identity |
| `severity` | `varchar(20)` | Yes | `info`, `warning`, `error`, `critical` |
| `is_alert` | `boolean` | Yes | whether the event should be treated as an alert |
| `alert_status` | `varchar(20)` | No | `open`, `acknowledged`, or `closed` when `is_alert = true` |
| `opened_at` | `timestamptz` | No | alert open time, usually same as `occurred_at` |
| `acknowledged_at` | `timestamptz` | No | when an operator acknowledged the alert |
| `acknowledged_by` | `varchar(100)` | No | operator identity or username |
| `closed_at` | `timestamptz` | No | when the alert was closed |
| `operator_memo` | `text` | No | latest operator note or closure comment |
| `title_en` | `varchar(200)` | Yes | short English summary |
| `title_ko` | `varchar(200)` | Yes | short Korean summary |
| `message_en` | `text` | Yes | detailed English message |
| `message_ko` | `text` | Yes | detailed Korean message |
| `entity_type` | `varchar(40)` | No | related object kind such as `adapter_instance`, `adapter_run`, `pipeline_run`, `ingest_batch` |
| `entity_id` | `bigint` | No | related object identity |
| `adapter_instance_id` | `bigint` | No | FK to `adapter_instance` |
| `adapter_run_id` | `bigint` | No | FK to `adapter_run` |
| `pipeline_run_id` | `bigint` | No | FK to `pipeline_run` |
| `ingest_batch_id` | `bigint` | No | FK to `ingest_batch` |
| `ingest_error_log_id` | `bigint` | No | FK to `ingest_error_log` |
| `reprocess_request_id` | `bigint` | No | FK to `reprocess_request` |
| `meter_identifier` | `varchar(100)` | No | operator filter convenience |
| `batch_id` | `varchar(100)` | No | copied batch identifier for operator lookup |
| `details` | `jsonb` | No | structured source-specific or stage-specific context |
| `created_at` | `timestamptz` | Yes | persistence timestamp |

### Recommended constraints

- FK to `adapter_instance`
- FK to `adapter_run`
- FK to `pipeline_run`
- FK to `ingest_batch`
- FK to `ingest_error_log`
- FK to `reprocess_request`
- check constraint: when `is_alert = false`, `alert_status` should be null
- check constraint: when `is_alert = true`, `alert_status` should be one of `open`, `acknowledged`, `closed`
- check constraint: when `is_alert = false`, `opened_at`, `acknowledged_at`, `acknowledged_by`, `closed_at`, and `operator_memo` should be null
- check constraint: when `alert_status = 'acknowledged'`, `acknowledged_at` should not be null
- check constraint: when `alert_status = 'closed'`, `closed_at` should not be null

### Recommended indexes

- index on `occurred_at desc`
- index on `(is_alert, alert_status, occurred_at desc)`
- index on `(severity, occurred_at desc)`
- index on `(event_code, occurred_at desc)`
- index on `adapter_instance_id`
- index on `adapter_run_id`
- index on `pipeline_run_id`
- index on `ingest_batch_id`
- index on `ingest_error_log_id`
- index on `meter_identifier`
- index on `batch_id`
- partial or filtered index for open alerts when needed later

## Alert condition configuration boundary

The minimal stage should treat `operational_event` as the persistence surface for emitted events and alert lifecycle, not as the place where alert conditions are defined.

Recommended first posture:

- keep alert-condition metadata in code
- keep recurring health checks in a table-like in-code rule registry
- persist only the emitted alert rows, not the rule definitions themselves

Deferred posture:

- a dedicated alert-condition definition table
- operator-managed alert thresholds
- dynamic rule activation or deactivation without a deployment

## Why a separate current and history alert table set is not recommended yet

The first implementation does not need two different operator histories.

Reasons:

- operators need one recent timeline first
- alert lifecycle is still intentionally small in the minimal stage
- separate current and history rows would create duplication or synchronization concerns
- later acknowledgement or escalation can still be added when real workflow requires it

Recommended first posture:

- keep one event timeline table
- separate current and history logically by `alert_status`
- archive older closed alerts later as an operational optimization

## Recommended value domains

### `source_layer`

Recommended first values:

- `integration`
- `ingest`
- `processing`
- `system`
- `operator_action`

### `event_category`

Recommended first values:

- `adapter_lifecycle`
- `adapter_run`
- `adapter_schedule`
- `ingest_batch`
- `ingest_validation`
- `pipeline_run`
- `finalization`
- `exception_reprocess`
- `system_health`

### `event_code`

Recommended first event codes:

- `adapter_enabled`
- `adapter_paused`
- `adapter_run_queued`
- `adapter_run_started`
- `adapter_run_completed`
- `adapter_run_failed`
- `adapter_overdue_detected`
- `adapter_stale_detected`
- `ingest_batch_accepted`
- `raw_ingest_completed`
- `raw_ingest_failed`
- `canonical_started`
- `canonical_completed`
- `canonical_failed`
- `finalization_started`
- `finalization_completed`
- `finalization_failed`
- `exception_reprocess_started`
- `exception_reprocess_completed`
- `exception_reprocess_failed`

### `severity`

Recommended interpretation:

- `info`: normal milestone
- `warning`: degraded but not fully failed
- `error`: failed and likely requires operator attention
- `critical`: repeated or severe system condition

### `alert_status`

Recommended first values:

- `open`
- `acknowledged`
- `closed`

## Recommended alert lifecycle interpretation

- `open`
  - alert exists and has not been acknowledged yet
- `acknowledged`
  - operator has seen the alert, but it still remains active
- `closed`
  - the condition has ended or the operator intentionally closed it

Recommended time interpretation:

- `opened_at`
  - start of alert life
- `acknowledged_at`
  - first operator acknowledgement
- `closed_at`
  - end of alert life

Recommended duration interpretation:

- derive in query or UI
- active duration = `now - opened_at`
- closed duration = `closed_at - opened_at`

## Relationship to existing persistence

`operational_event` should complement, not replace, current source tables.

- `adapter_run` remains runtime truth
- `pipeline_run` remains processing truth
- `ingest_error_log` remains error truth
- `operational_event` becomes operator-facing timeline truth

This allows event rows to link back to the real source-of-truth tables instead of duplicating business logic.

## Event emission guidance

### Emit from adapter operations

The first implementation should emit events when:

- an adapter instance is enabled
- an adapter instance is paused
- a run is queued
- a run starts
- a run completes
- a run fails
- an overdue or stale condition is detected

### Emit from ingest

The first implementation should emit events when:

- an ingest batch is accepted
- a read ingest completes
- an event ingest completes
- ingest fails at the batch level

Do not emit one operational event for every raw row in the minimal stage.

### Emit from processing

The first implementation should emit events when:

- canonical processing starts
- canonical processing completes
- canonical processing fails
- finalization starts
- finalization completes
- finalization fails
- reprocess starts
- reprocess completes
- reprocess fails

## Dashboard query recommendation

### Recent timeline

Recommended dashboard query:

- latest 20 to 50 `operational_event` rows ordered by `occurred_at desc`

### Open-alert spotlight

Recommended dashboard query:

- latest current alerts where `alert_status in ('open', 'acknowledged')` ordered by `occurred_at desc`

### Filtered history view

Recommended first filters:

- `severity`
- `is_alert`
- `alert_status`
- `event_code`
- `adapter_instance_id`
- `batch_id`
- `meter_identifier`
- date range

Recommended practical history split:

- current alerts = `open` or `acknowledged`
- closed history = `closed`

## Retention recommendation

`operational_event` is more valuable than short-horizon state tables, but it is still not raw metering data.

Recommended first posture:

- keep at least a moderate operational history window
- prefer archive or summarization later rather than very early purge
- do not move rows at close time in the first implementation
- archive only older closed alerts later when the table volume justifies it

The first implementation does not require partitioning immediately.

If volume grows materially, revisit:

- monthly partitioning on `occurred_at`

This should be a later operational tuning step, not a blocker for the first implementation.

## Why append-only is still preferred here

Event history should remain durable and easy to reason about.

Recommended posture:

- append one event row per meaningful milestone
- only update lifecycle fields when alert state changes

This means:

- event identity remains append-oriented
- alert lifecycle remains lightweight
- current versus history remains queryable from one table first

This preserves readable operator history while keeping alert lifecycle simple.

## Recommended first implementation sequence

1. add `operational_event` ORM and migration
2. emit adapter lifecycle and adapter run events
3. emit ingest and pipeline milestone events
4. add dashboard recent event and open-alert queries
5. add event history screen and API
6. add acknowledgement and close behavior if the first UI needs it immediately

## Acceptance baseline

This schema is minimally successful when:

- events can be emitted from adapter, ingest, and processing paths
- alerts can be filtered as a subset of the same table
- dashboard queries can show recent events and open alerts efficiently
- current alerts and closed history can be separated without moving rows physically
- the linked source object for an event remains traceable

## Related documents

- [operational-events-and-alerts.md](/home/tprover/2604_sim_mdms_auto/docs/operational-events-and-alerts.md)
- [minimal-event-alert-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-event-alert-boundary.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)
