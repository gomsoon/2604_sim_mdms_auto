# Minimal Adapter Operations Boundary

## Purpose

This document defines the operational boundary for runtime adapters in the `Minimal End-to-End` stage.

It answers:

- what adapter operations are already part of the minimal baseline
- what `start`, `pause`, and `stop` should mean in this stage
- which libraries and runtime model are currently used
- what is intentionally deferred until a later stage

## Why this document matters

Adapter operations are important for administrators, but the minimal stage should not overpromise a full connector control plane.

Without a clear boundary, the project risks:

- treating `Flask` as a long-running scheduler platform
- mixing UI state changes with OS-level process control
- expecting force-stop behavior that the current execution model does not support safely
- adding orchestration libraries too early before the required lifecycle is stable

## Core recommendation

For the minimal stage, runtime adapter operations should be:

- operator-visible
- state-driven
- auditable
- safe to extend later

They should not yet be:

- in-process scheduler management
- hard process orchestration
- force-cancel control for active external collection work

## Operator meaning of start and stop

The minimal stage should not overload the words `start` and `stop`.

Recommended interpretation:

- `Enable`
  - allow the adapter instance to participate in scheduled or manual execution again
- `Run Once`
  - queue one explicit adapter run for immediate validation or collection
- `Pause`
  - stop future scheduled execution without deleting the adapter instance

What the minimal stage does not mean by `stop`:

- killing an active worker thread
- interrupting an already-running poll mid-transaction
- stopping an OS service from the browser

For the minimal stage, an active run should usually be allowed to finish cleanly.

## Current implementation baseline

The current project already includes these runtime adapter operations:

- adapter definition and instance persistence
- adapter list and detail screens
- adapter status derivation with `ready`, `running`, `paused`, `error`, and `retired`
- `Enable` action
- `Pause` action
- `Run Once` action
- adapter run history
- adapter watermark visibility
- dashboard `Integration` summary card
- queued adapter-run execution through a lightweight worker command

Relevant code:

- `Flask` routes and templates
  - [app/blueprints/web.py](/home/tprover/2604_sim_mdms_auto/app/blueprints/web.py)
  - [app/templates/adapters.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapters.html)
  - [app/templates/adapter_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapter_detail.html)
- runtime adapter lifecycle and queueing
  - [app/services/adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/adapters.py)
  - [app/services/adapter_execution.py](/home/tprover/2604_sim_mdms_auto/app/services/adapter_execution.py)
- CLI worker entry point
  - [app/__init__.py](/home/tprover/2604_sim_mdms_auto/app/__init__.py)
- dashboard visibility
  - [app/services/dashboard.py](/home/tprover/2604_sim_mdms_auto/app/services/dashboard.py)

## Current library and runtime model

The current minimal implementation is based on:

- `Flask`
- `SQLAlchemy`
- `Alembic`
- `Click` through Flask CLI
- `PostgreSQL`

Current execution pattern:

1. operator changes adapter state or queues a run from the web UI
2. runtime metadata is written to PostgreSQL
3. a lightweight worker command consumes `waiting` adapter runs
4. the worker updates run status, watermarks, and ingest lineage

Current worker entry point:

```bash
./.venv/bin/flask --app wsgi:app process-adapter-runs --limit 1
```

This means the current model is:

- `web control + database state + worker command`

It is not:

- `web route directly performs long-running polling`
- `Flask process acts as an always-on scheduler`

## Required minimal operational features

The following features should be treated as mandatory for the minimal adapter baseline.

### 1. Safe operator lifecycle control

Required:

- `Enable`
- `Pause`
- `Run Once`

Why:

- operators need a safe way to allow or suspend collection
- onboarding and troubleshooting require manual execution without waiting for a schedule

### 2. Observable adapter status

Required:

- effective adapter status
- last success time
- last failure time
- last error summary
- pending or recent runs
- watermarks

Why:

- the integration layer is the upstream entry point for all later processing
- operators should be able to tell whether data collection is healthy before troubleshooting downstream layers

### 3. Auditable execution history

Required:

- one persistent `adapter_run` record per execution attempt
- `waiting`, `running`, `completed`, and `failed` states
- summary counts and error codes

Why:

- the team must be able to trace what happened without relying only on live logs

### 4. Explicit separation between UI and execution

Required:

- the web UI must request state changes or run queueing
- execution must happen through a separate worker path

Why:

- this avoids long-running source polling inside a request-response lifecycle
- it keeps future scheduler introduction cleaner

## Intentionally out of scope in minimal stage

The following should remain outside the minimal boundary for now:

- force-cancel or hard-stop of an already-running adapter execution
- browser-driven OS process control
- in-process scheduler embedded in the Flask web process
- `Celery`, `RQ`, `Dramatiq`, or equivalent distributed task queue adoption
- `APScheduler` embedded as the primary runtime orchestration engine
- direct plaintext credential editing from the UI
- code-free creation of new adapter implementations from the UI
- full receive-daemon lifecycle management

## Why hard stop is deferred

Force-stopping an active adapter run sounds operationally attractive, but it adds risk early.

Risks:

- partial source fetch handling becomes more complex
- landing and common raw writes can be interrupted mid-flight
- audit behavior and retry semantics become harder to reason about
- transaction boundaries become more important than the current minimal model needs

For the minimal stage, `Pause + let current run finish` is the safer baseline.

## Recommended deployment shape for minimal stage

The project should treat runtime adapter execution as a lightweight external worker pattern.

Recommended shape:

- run the Flask app for operator UI and APIs
- run the worker command on demand or from a simple scheduler
- keep scheduling external to the Flask request process

Good near-term operational options:

- `cron`
- `systemd timer`
- container-level scheduled command

This keeps the minimal stage simple while leaving room for later expansion.

## Recommended next-step boundary after minimal stage

The next operational step after the current baseline should be:

1. add schedule-driven run enqueueing
2. keep the same worker execution path for both scheduled and manual runs
3. improve dashboard visibility for stale or overdue adapters

The next step should not immediately be:

- full distributed task infrastructure
- hard-stop semantics
- connector plugin marketplace behavior

## Summary

The minimal adapter operations baseline should be understood as:

- enough operator control to manage and observe adapters safely
- enough runtime separation to avoid polling inside web requests
- not yet a full process-control or workflow platform

That boundary is small enough to be stable, but strong enough to support real HES adapter work.

## Related documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)
