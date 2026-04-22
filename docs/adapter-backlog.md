# Adapter Backlog

## Purpose

This document consolidates adapter-related work into a backlog-oriented view.

The repository already has several adapter design and implementation documents, but they are spread across:

- lifecycle and UI scope
- execution gap analysis
- implementation sequence
- source-specific polling design

This document exists to show adapter work in one practical backlog shape.

## Why this backlog matters

The integration layer is now large enough that adapter work can drift unless it is grouped into:

- already delivered baseline
- next required minimal features
- intentionally deferred work

That distinction helps the team avoid mixing:

- core minimal-stage obligations
- near-term operational improvements
- later-stage platform features

## Current backlog state

The adapter backlog should be interpreted in three groups:

- `Done`
- `Next`
- `Deferred`

## Done

### A1. Runtime adapter persistence baseline

#### Scope

- `adapter_definition`
- `adapter_instance`
- `adapter_run`
- `adapter_watermark`
- runtime lineage from adapter execution into `ingest_batch`

#### Current status

- done

#### Evidence

- [app/models.py](/home/tprover/2604_sim_mdms_auto/app/models.py)
- [migrations/versions/202604190004_add_adapter_runtime_tables.py](/home/tprover/2604_sim_mdms_auto/migrations/versions/202604190004_add_adapter_runtime_tables.py)

### A2. Minimal operator control UI

#### Scope

- adapter list
- adapter detail
- adapter registration from approved definition
- `Enable`
- `Pause`
- `Run Once`
- recent runs
- watermark visibility

#### Current status

- done

#### Evidence

- [app/blueprints/web.py](/home/tprover/2604_sim_mdms_auto/app/blueprints/web.py)
- [app/templates/adapters.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapters.html)
- [app/templates/adapter_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapter_detail.html)
- [app/templates/adapter_new.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapter_new.html)

### A3. Lightweight adapter execution worker

#### Scope

- queued run claim
- `waiting -> running -> completed|failed`
- runtime dispatch by `implementation_key`
- execution summary and watermark update
- CLI worker entry point

#### Current status

- done

#### Evidence

- [app/services/adapter_execution.py](/home/tprover/2604_sim_mdms_auto/app/services/adapter_execution.py)
- [app/__init__.py](/home/tprover/2604_sim_mdms_auto/app/__init__.py)

### A4. First source-specific polling baseline

#### Scope

- NURI AIMIR HES overseas Oracle source
- `LP_EM` polling
- landing expansion into interval-granular common raw
- completeness-state update

#### Current status

- done as first-source baseline

#### Evidence

- [app/services/nuri_aimir_hes_source.py](/home/tprover/2604_sim_mdms_auto/app/services/nuri_aimir_hes_source.py)
- [docs/nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)

### A5. Integration dashboard baseline

#### Scope

- first dashboard card for adapter/integration health
- `ready`
- `running`
- `paused`
- `error`
- last success and pending-run summary

#### Current status

- done as initial dashboard baseline

#### Evidence

- [app/services/dashboard.py](/home/tprover/2604_sim_mdms_auto/app/services/dashboard.py)
- [app/templates/dashboard.html](/home/tprover/2604_sim_mdms_auto/app/templates/dashboard.html)

### A6. Schedule-driven enqueue for polling adapters

#### Why it mattered

The current adapter model needed a way to queue due polling work without relying on repeated manual `Run Once` actions.

#### Scope

- periodic command to enqueue eligible polling adapter runs
- selection by:
  - `admin_state = enabled`
  - `delivery_mode = poll`
  - `next_run_at <= now`
- overlap prevention per adapter instance
- reuse of current worker execution path

#### Current status

- done

#### Evidence

- [app/services/adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/adapters.py)
- [app/__init__.py](/home/tprover/2604_sim_mdms_auto/app/__init__.py)

#### Acceptance criteria

- polling adapters can queue work without manual UI action
- paused adapters do not receive scheduled runs
- one instance does not receive overlapping scheduled runs

### A7. Stale and overdue adapter visibility

#### Why it mattered

Operators needed to distinguish a paused adapter from one that is enabled but falling behind or losing freshness.

#### Scope

- overdue interpretation from `next_run_at`
- stale interpretation from `last_heartbeat_at` and recent runs
- clearer adapter-detail summaries
- stronger `Integration` card semantics

#### Current status

- done

#### Evidence

- [app/services/adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/adapters.py)
- [app/services/dashboard.py](/home/tprover/2604_sim_mdms_auto/app/services/dashboard.py)
- [app/templates/adapters.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapters.html)
- [app/templates/adapter_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapter_detail.html)

#### Acceptance criteria

- operators can distinguish paused adapters from unhealthy or overdue adapters
- dashboard and adapter detail agree on health interpretation

### A8. Adapter health alert promotion baseline

#### Scope

- `adapter_overdue_detected` alert emission
- `adapter_stale_detected` alert emission
- automatic close when the condition clears or the instance pauses
- health-sync entry points from CLI and runtime execution

#### Current status

- done as minimal operator-alert baseline

#### Evidence

- [app/services/adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/adapters.py)
- [app/services/adapter_execution.py](/home/tprover/2604_sim_mdms_auto/app/services/adapter_execution.py)
- [app/services/operational_events.py](/home/tprover/2604_sim_mdms_auto/app/services/operational_events.py)

## Next

### A9. HES system registry baseline

#### Why it matters

The current runtime adapter model lacks a parent operator-managed HES object. As soon as one HES needs multiple runtime adapters, the source identity and the technical execution unit should no longer be treated as the same thing.

#### Scope

- `hes_system` persistence baseline
- `adapter_instance.hes_system_id`
- `hes_system_id` lineage in `ingest_batch`, `hes_read_raw`, and `hes_event_raw`
- first HES list and detail screens
- adapter screens updated to show the parent HES clearly

#### Acceptance criteria

- operators can register one upstream HES explicitly
- one HES can own multiple runtime adapters
- batch and raw records can be traced by HES as well as adapter

#### Current status

- delivered as registry baseline

#### Evidence

- [app/models.py](/home/tprover/2604_sim_mdms_auto/app/models.py)
- [app/services/hes_systems.py](/home/tprover/2604_sim_mdms_auto/app/services/hes_systems.py)
- [app/templates/hes_systems.html](/home/tprover/2604_sim_mdms_auto/app/templates/hes_systems.html)
- [app/templates/hes_system_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/hes_system_detail.html)

### A10. HES-centric operator flow completion

#### Why it matters

The registry baseline exists now, but operators still need a stronger HES-first operating flow so that adapter creation and troubleshooting begin from the HES rather than from a detached runtime screen.

#### Scope

- HES detail should be the parent navigation surface
- adapter registration should work directly from an HES context
- `source_system` and `hes_system.hes_code` alignment should be enforced
- HES detail should remain the main drill-down page into linked adapters and recent batches

#### Acceptance criteria

- operators can create an adapter under one HES without re-entering a conflicting source identity
- adapter instances created from an HES context keep explicit parent lineage
- HES remains the natural entry point for operator investigation

### A11. Scheduled-run test baseline

#### Why it matters

Once schedule-driven enqueueing exists, manual-only tests are no longer enough.

#### Scope

- schedule enqueue unit tests
- overlap prevention tests
- scheduled + manual shared-path regression tests
- PostgreSQL-backed integration tests for scheduler-related state transitions

#### Acceptance criteria

- scheduled runs and manual runs share the same execution guarantees
- state transitions remain auditable and deterministic

## Deferred

### A11. Receive adapter runtime baseline

#### Why deferred

The lifecycle model supports `receive`, but polling should be stabilized first.

#### Intended scope later

- receive-oriented runtime implementation contract
- heartbeat and delivery visibility
- failure handling aligned with the existing adapter model

### A12. Hard stop or cancel for active adapter runs

#### Why deferred

This increases safety and transaction-boundary complexity too early.

#### Current policy

- `Pause` prevents future work
- active runs are usually allowed to finish

### A13. In-process scheduler or heavy task framework

#### Why deferred

The minimal stage intentionally prefers a lightweight worker and external scheduling approach.

#### Deferred tools

- `Celery`
- `RQ`
- `Dramatiq`
- embedded `APScheduler` as primary orchestration engine

### A14. UI-driven adapter code creation

#### Why deferred

The project should manage adapter instances operationally, while adapter implementations remain code-backed.

#### Examples of deferred scope

- raw SQL editing from the UI
- dynamic adapter code generation
- code-free connector authoring

### A15. Database-backed adapter alert condition table

#### Why deferred

The current alert set is still intentionally small, and the first operational need is structural clarity rather than a fully persistent rule-management model.

#### Current direction

- keep emitted alert rows in `operational_event`
- keep health-condition logic in a table-like in-code rule registry
- move to a database-backed condition-definition table only when operator-tunable thresholds or a larger alert catalog makes it worth the added persistence and governance complexity

#### Examples of deferred scope

- `adapter_alert_condition` persistence
- operator-managed threshold editing
- dynamic rule activation without deployment
- database-resident expression evaluation

## Recommended immediate execution order

The recommended next adapter backlog order is:

1. `A9. HES system registry baseline`
2. `A10. Scheduled-run test baseline`
3. `A11. Receive adapter runtime baseline`
4. `A15. Database-backed adapter alert condition table`

## Related documents

- [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
- [adapter-gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-gap-analysis.md)
- [adapter-implementation-sequence.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-implementation-sequence.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
