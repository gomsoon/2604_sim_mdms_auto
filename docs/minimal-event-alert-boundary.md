# Minimal Event and Alert Boundary

## Purpose

This document defines what operational events and alerts should mean in the `Minimal End-to-End` stage.

It exists because alert requirements become ambiguous very quickly unless the project states:

- what the first implementation must include
- what remains intentionally deferred
- how current versus historical alerts should be handled

## Why this boundary matters

The minimal stage should be operationally useful, but it should not accidentally turn into a full incident-management platform.

Without a clear boundary, the project risks:

- overbuilding alert features before the core data flow is stable
- mixing operator history, notification delivery, and incident workflow into one change
- introducing archive or movement logic too early
- making the first event model harder to implement than the underlying MDM flow itself

## Core recommendation

For the minimal stage:

- operational events should be durable and append-oriented
- alerts should be treated as operator-actionable events with a small lifecycle
- alert history should be separated logically first, not physically first

This means the first implementation should support:

- recent event visibility
- open alert visibility
- closed alert history visibility
- lightweight operator acknowledgement and memo behavior

It should not yet support:

- full incident assignment
- escalation workflow
- external alert delivery channels
- immediate physical movement into history tables when an alert closes
- database-backed alert condition tables
- operator-managed alert rule editing UI

## Required minimal event capabilities

The first implementation should include:

- one durable operator-facing event timeline
- event localization in English and Korean
- recent event visibility on the dashboard
- event history lookup with practical filters

## Required minimal alert capabilities

The first implementation should include:

- `open` alert state
- `acknowledged` alert state
- `closed` alert state
- alert open time
- alert acknowledgement time
- alert acknowledgement user
- alert close time
- operator memo

The first implementation should also allow operators to distinguish:

- alert currently active
- alert already seen by an operator
- alert already closed

## Duration guidance

Alert duration is useful, but it should not be stored as the first implementation baseline.

Recommended posture:

- derive duration from timestamps
- use `closed_at - opened_at` for closed alerts
- use `now - opened_at` for still-open alerts

Why:

- it avoids synchronization bugs
- it keeps lifecycle updates simpler
- it still gives operators the duration they need in UI or reporting

If duration queries become expensive later, add a derived view or summary layer then.

## Alert condition configuration boundary

### Minimal-stage recommendation

For the minimal stage, alert conditions should remain code-backed but structurally organized.

Recommended posture:

- keep condition evaluation in application code
- keep event metadata in the operational event specification registry
- keep health-condition evaluation in a table-like in-code rule registry
- avoid scattering condition-specific `if/else` branches across multiple services

This gives the project:

- a clean first implementation that is easy to test
- one obvious place to add another health alert rule
- a future migration path toward a database-backed rule table if operational complexity grows

### What not to do yet

The minimal stage should not require:

- a persistent alert-condition definition table
- operator-managed threshold editing
- rule lifecycle management UI
- dynamic expression parsing in the database

Those concerns belong in backlog and later-stage operational hardening, not in the first event and alert baseline.

## Current versus history recommendation

### Minimal-stage recommendation

Treat current and history as logical views over the same persistence model.

Recommended interpretation:

- current alerts = `alert_status in ('open', 'acknowledged')`
- historical alerts = `alert_status = 'closed'`

This is the recommended starting point because:

- operators still get a clean current/history distinction
- timeline integrity stays simple
- source-object linkage remains in one place
- migration and query logic stay smaller

### What not to do yet

Do not require:

- moving rows to a second history table immediately when an alert closes
- delete-and-insert archive movement inside the same close action
- dual-write current/history logic

Those can be added later when operational volume really justifies them.

## Archive strategy recommendation

History should be planned from the beginning, but physical archive should be a later operational optimization.

Recommended roadmap:

1. start with one operational event table
2. distinguish current versus history by status
3. later archive only older closed alerts
4. if needed, move them by batch job or partition detach strategy

Good later candidates:

- `operational_event_archive`
- time-based partition detach for old closed rows
- summarized history reporting

## Required minimal operator actions

The first implementation should support:

- view recent events
- view open alerts
- view closed alert history
- acknowledge an alert
- close an alert
- add or update one operator memo

The first implementation does not need:

- re-open lifecycle
- multi-user assignment
- threaded memo history
- root-cause workflow states
- SLA breach tracking

## Dashboard expectation

The dashboard should show:

- summary cards at the top
- open-alert emphasis
- recent event timeline below

It should not yet try to become:

- a full real-time NOC console
- a websocket-heavy event bus UI
- an incident queue with complex workflow controls

## Recommended first implementation sequence

1. add the `operational_event` persistence model with alert lifecycle fields
2. emit important events from adapter, ingest, and processing paths
3. show recent events and open alerts on the dashboard
4. add an event and alert history screen
5. later add acknowledgement and close actions in the UI

## Summary

The minimal stage should be strong enough to let operators see what happened, see what needs action now, and mark alerts as seen or closed.

It should not yet try to solve every long-term history, archive, notification, and incident-management concern in the first pass.

## Related documents

- [operational-events-and-alerts.md](/home/tprover/2604_sim_mdms_auto/docs/operational-events-and-alerts.md)
- [operational-event-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/operational-event-table-design.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
