# Operational Events and Alerts

## Purpose

This document defines the minimal-stage baseline for operational events and alerts in the MDM system.

It exists because raw tables, exception queues, adapter runs, and pipeline runs already capture parts of system behavior, but they do not yet provide one operator-facing event stream or one explicit alert concept.

## Why this matters in the minimal stage

The minimal stage is not only about persisting data.

It must also let operators answer questions such as:

- Is upstream collection healthy right now
- Did a scheduled adapter fall behind
- Did raw ingest fail for a delivery
- Did canonical or final progression stop
- Which issue needs action now, and which one is only historical context

If the system cannot answer those quickly, operators will still need to inspect logs, tables, and multiple screens before they can react.

## Core distinction

### Operational event

An operational event is a durable record of something meaningful that happened in the running system.

Examples:

- adapter run queued
- adapter run started
- adapter run failed
- ingest batch accepted
- canonical progression failed
- finalization completed
- reprocess completed

Operational events are primarily for:

- timeline visibility
- operational history
- troubleshooting context
- audit-friendly traceability

### Operational alert

An operational alert is an operational event that deserves elevated operator attention because action may be needed soon.

Examples:

- polling adapter overdue
- polling adapter stale
- adapter run failed
- raw ingest failed
- canonical stage failed
- finalization failed

An alert is not a different kind of storage universe.

For the minimal stage, an alert should be treated as a flagged subset of operational events.

## Minimal-stage design recommendation

### Recommendation summary

The minimal stage should introduce:

- one append-only operational event timeline
- one alert interpretation model on top of that timeline
- one dashboard view of recent events and open alerts
- one small alert lifecycle that operators can acknowledge and close

This is enough for minimal operator reaction without overbuilding a full notification platform.

### What should be in scope now

- persistent operational events for important adapter, ingest, processing, and exception milestones
- alert tagging for operator-actionable situations
- alert lifecycle fields such as open time, acknowledgement, close time, and memo
- recent event and alert visibility on the dashboard
- historical event and alert lookup with filters
- English and Korean operator-facing messages

### What should stay out of scope for now

- email, SMS, Slack, or paging integration
- websocket-first real-time streaming infrastructure
- complex alert correlation engine
- database-backed alert condition tables
- configurable alert rules UI
- multi-step incident workflow
- full escalation hierarchy
- immediate physical movement of closed alerts into a separate history table

## Minimal alert condition boundary

The minimal stage should keep alert condition evaluation code-backed, but it should not remain ad-hoc.

Recommended posture:

- alert event metadata lives in the operational event specification registry
- recurring health-condition checks should be expressed through a table-like in-code rule registry
- new alert conditions should be added by extending the registry rather than by scattering direct condition branches

This is intentionally not yet:

- a persistent rule-definition table
- a threshold-editing UI
- a database-resident rule engine

That later step should remain backlog work until the number of alert conditions or operator-tunable thresholds justifies the extra persistence and governance complexity.

## Recommended minimal event categories

### Integration events

- adapter enabled
- adapter paused
- adapter run queued
- adapter run started
- adapter run completed
- adapter run failed
- adapter overdue detected
- adapter stale detected

### Ingest events

- ingest batch accepted
- raw read ingest completed
- raw event ingest completed
- ingest validation failure recorded
- duplicate raw read recorded

### Processing events

- canonical progression started
- canonical progression completed
- canonical progression failed
- finalization started
- finalization completed
- finalization failed
- exception reprocess started
- exception reprocess completed
- exception reprocess failed

### System events

- application health degraded
- database connectivity failure observed

For the minimal stage, system events that happen before the database is usable may still remain in logs only.

## Recommended minimal alert categories

The first alert set should stay intentionally small.

- `adapter_overdue`
- `adapter_stale`
- `adapter_run_failed`
- `raw_ingest_failed`
- `canonical_failed`
- `finalization_failed`
- `exception_reprocess_failed`

This keeps the operator signal clear while the platform is still small.

## Severity recommendation

Use a small, explicit severity model:

- `info`
- `warning`
- `error`
- `critical`

Recommended interpretation:

- `info`: normal lifecycle milestone
- `warning`: something unusual that may need review soon
- `error`: a failed run or blocked progression that likely needs operator action
- `critical`: severe platform issue such as repeated integration failure or infrastructure unavailability

## Persistence recommendation

### Minimal preferred shape

For the minimal stage, prefer one primary table such as `operational_event`.

Suggested columns:

- `id`
- `occurred_at`
- `source_layer`
- `event_category`
- `event_code`
- `severity`
- `is_alert`
- `alert_status`
- `title_en`
- `title_ko`
- `message_en`
- `message_ko`
- `entity_type`
- `entity_id`
- `adapter_instance_id`
- `adapter_run_id`
- `pipeline_run_id`
- `ingest_batch_id`
- `ingest_error_log_id`
- `meter_identifier`
- `batch_id`
- `details jsonb`
- `created_at`

### Why one table first

One table keeps the minimal stage simpler:

- one timeline source for the dashboard
- one query path for event history
- one way to localize operator-facing text
- one alert model as a filtered subset

The concrete first-table baseline is described in:

- [operational-event-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/operational-event-table-design.md)

### Recommended minimal alert state

For the first implementation, keep alert state small but operationally useful:

- `open`
- `acknowledged`
- `closed`

Recommended supporting fields:

- `opened_at`
- `acknowledged_at`
- `acknowledged_by`
- `closed_at`
- `operator_memo`

Recommended duration behavior:

- derive it from timestamps instead of storing it as a base column

## Current versus history recommendation

For the minimal stage, current and history should first be separated logically.

Recommended interpretation:

- current alerts are `open` or `acknowledged`
- history alerts are `closed`

The first implementation should not require closed alerts to be moved immediately into a separate history table.

That physical archive step should remain a later operational optimization after volume and retention behavior are better understood.

## Relationship to existing tables

The event and alert layer should not replace existing domain or processing tables.

It should complement them.

- `adapter_run` remains the source of adapter execution truth
- `pipeline_run` remains the source of processing execution truth
- `ingest_error_log` remains the source of ingest and exception truth
- `operational_event` becomes the operator-facing timeline and alert surface

This avoids forcing the dashboard to infer every operator-facing message directly from multiple unrelated tables forever.

## Dashboard recommendation

### Top of dashboard

Keep summary cards for:

- integration
- raw ingest
- canonical
- final
- errors

### Lower dashboard area

Add a recent operational timeline table that looks streaming-like to the operator.

For the minimal stage, this does not require websocket infrastructure.

A refresh-based or poll-based update model is sufficient if the user experience still feels near-real-time enough for operations.

Recommended columns:

- occurred time
- severity
- event or alert type
- source layer
- related adapter or pipeline
- short message
- status if the row is an alert

### Open-alert emphasis

The dashboard should also make open alerts visually prominent.

This can be done with:

- a small summary count near the top
- filtered rows at the top of the recent event table
- color emphasis by severity

## History and lookup recommendation

Operators should be able to query event and alert history by:

- severity
- event code
- alert status
- adapter instance
- pipeline name or run
- batch ID
- meter identifier
- date range

This should support two practical views:

- current open or acknowledged alerts
- closed alert history

This keeps the event stream useful after the dashboard scrolls past the latest items.

## Event production guidance

The first producers should be:

- adapter lifecycle and adapter execution
- schedule enqueue decisions
- ingest completion or failure
- canonical progression completion or failure
- finalization completion or failure
- exception reprocess completion or failure

Do not try to emit an event for every tiny internal branch.

Emit events for meaningful operator-visible milestones.

## Minimal implementation sequence

1. Define the persistent event model and alert subset rules
2. Emit events from adapter, ingest, pipeline, and reprocess paths
3. Show recent events and open alerts on the dashboard
4. Add filtered event history view
5. Add regression coverage for event emission and alert visibility

The broader minimal boundary for this area is defined in:

- [minimal-event-alert-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-event-alert-boundary.md)

## Acceptance baseline

The minimal stage should be considered operationally incomplete unless:

- recent important system behavior is visible as events
- urgent operator-relevant conditions are visible as alerts
- operators can see those signals without reading logs first
- event and alert messages remain available in English and Korean

## Related documents

- [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
- [minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md)
