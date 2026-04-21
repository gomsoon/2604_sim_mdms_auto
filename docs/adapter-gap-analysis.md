# Adapter Gap Analysis

## Purpose

This document clarifies the current gap between the adapter-related baseline already implemented in the repository and the next operational target.

It exists to answer two recurring questions clearly:

- what is already implemented today
- what is still missing before runtime adapters can be considered operationally stronger than the current minimal baseline

## Executive summary

The repository has already implemented:

- field-normalization adapter profiles before common raw ingest
- runtime adapter persistence
- operator-facing adapter instance management
- operator-facing `Run Once` queueing
- adapter run history visibility
- adapter watermark persistence as an explicit model
- code-backed runtime execution selected by `implementation_key`
- a worker command that consumes queued `adapter_run` rows
- automatic summary updates such as `last_success_at`, `last_failure_at`, and `last_heartbeat_at`
- automatic linkage from runtime execution into `ingest_batch.adapter_instance_id` and `ingest_batch.adapter_run_id`
- a first source-specific polling path for the company overseas HES on Oracle

The repository has not yet implemented:

- schedule-driven enqueueing for eligible polling adapters
- a receive runtime path that accepts externally delivered records as a managed adapter lifecycle
- stale or overdue adapter detection beyond the current summary view
- hard-stop semantics for active adapter executions
- full OS-service lifecycle control from the operator UI

So the current system should be understood as:

- operationally visible
- minimally controllable
- execution-capable for manual or explicitly queued runs
- not yet scheduler-complete

## Current state by concern

### 1. Adapter profile layer

Status:

- implemented

Current shape:

- [app/services/ingest_adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/ingest_adapters.py) provides lightweight profile-based normalization through `common_raw_v1` and `legacy_hes_v1`
- this layer maps source field aliases into the common raw ingest contract
- this layer does not connect to an external source

Conclusion:

- adapter profiles are real and working
- they are not runtime connectors

### 2. Runtime adapter persistence

Status:

- implemented

Current shape:

- [app/models.py](/home/tprover/2604_sim_mdms_auto/app/models.py) includes:
  - `adapter_definition`
  - `adapter_instance`
  - `adapter_run`
  - `adapter_watermark`
- `ingest_batch` also has optional lineage fields:
  - `adapter_instance_id`
  - `adapter_run_id`

Conclusion:

- the database baseline needed for runtime adapters is already in place
- the schema now matches actual execution behavior more closely than before

### 3. Runtime adapter operations UI

Status:

- implemented at a minimal operator level

Current shape:

- [app/blueprints/web.py](/home/tprover/2604_sim_mdms_auto/app/blueprints/web.py) supports:
  - adapter list
  - adapter detail
  - enable
  - pause
  - run once
  - adapter registration from an approved definition
- templates already exist for:
  - [app/templates/adapters.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapters.html)
  - [app/templates/adapter_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapter_detail.html)
  - [app/templates/adapter_new.html](/home/tprover/2604_sim_mdms_auto/app/templates/adapter_new.html)

Conclusion:

- operators can manage adapter instances
- operators can trigger real upstream data movement through queued runs and worker execution
- the UI is intentionally lifecycle-oriented rather than process-control-oriented

### 4. Runtime execution engine

Status:

- implemented at a lightweight worker level

Current shape:

- `Run Once` queues an `adapter_run` row with `run_status="waiting"`
- [app/services/adapter_execution.py](/home/tprover/2604_sim_mdms_auto/app/services/adapter_execution.py) can:
  - claim that waiting run
  - mark it `running`
  - resolve the runtime by `implementation_key`
  - connect to an upstream source
  - fetch source rows
  - call ingest with runtime lineage
  - mark the run `completed` or `failed`
- [app/__init__.py](/home/tprover/2604_sim_mdms_auto/app/__init__.py) exposes `process-adapter-runs` as the current worker entry point

Conclusion:

- runtime control exists
- runtime execution exists
- scheduling and higher-order control are still intentionally small

### 5. Polling resume and duplicate prevention

Status:

- partially implemented

Implemented now:

- `adapter_watermark` exists and can store cursor state explicitly
- `adapter_run` can record `watermark_before` and `watermark_after`
- raw ingest performs duplicate detection in [app/services/ingestion.py](/home/tprover/2604_sim_mdms_auto/app/services/ingestion.py)
- the first polling runtime reads and advances watermark state during successful execution

Not implemented yet:

- no schedule-driven enqueueing currently creates polling runs automatically
- no broader policy yet exists for multiple source families or mixed cursor strategies

Important distinction:

- current duplicate protection is stronger than before because watermark-driven polling now exists for the first source path
- broader operational scheduling and cross-source standardization are still open work

### 6. Receive adapter runtime

Status:

- not implemented

Current shape:

- the model supports `delivery_mode="receive"`
- the UI can display that mode
- there is no dedicated receive runtime worker, receiver lifecycle manager, or heartbeat model yet

Conclusion:

- receive is modeled conceptually
- receive is not yet implemented operationally

## Gap matrix

| Concern | Current state | Gap level | Notes |
| --- | --- | --- | --- |
| Field-normalization adapter profiles | Implemented | Low | Stable baseline |
| Adapter persistence schema | Implemented | Low | Good foundation |
| Adapter list/detail/admin actions | Implemented | Low | Operator baseline exists |
| Adapter registration from definition | Implemented | Low | Good minimal control scope |
| Waiting run queueing | Implemented | Low | Queue exists and is executable |
| Runtime implementation dispatch | Implemented | Low | Registry and dispatch baseline exist |
| Polling worker | Implemented | Medium | Manual or explicit worker execution exists |
| Receive runtime worker | Missing | High | Deferred after polling |
| Watermark-driven incremental fetch | Implemented | Medium | First source path exists, broader reuse still pending |
| Automatic summary updates on instance | Implemented | Low | Real runtime results now update instance summary |
| Ingest lineage from runtime execution | Implemented | Low | Traceability baseline exists |
| Scheduler / periodic adapter runner | Missing | Medium | Needed beyond manual run queue |
| Heartbeat / health monitoring | Partial | Medium | Basic timestamps exist, stale detection is still small |
| Hard-stop control for active runs | Missing | Medium | Intentionally deferred for safety |

## Most important implementation truth

The biggest remaining gap is no longer basic executable runtime behavior.

The biggest remaining gap is now:

- schedule-aware operational control

That means the next valuable work should not be:

- a larger adapter CRUD surface
- arbitrary adapter code editing from the UI
- force-stop semantics before schedule and visibility are stable
- a receive adapter before scheduled polling is credible

The next valuable work should be:

- schedule-driven enqueueing for eligible polling adapters
- better stale and overdue integration visibility
- shared-path hardening for manual and scheduled execution

## Recommended architectural rule for the next phase

The next implementation phase should keep this boundary:

- runtime adapter fetches upstream data
- ingest service persists into common raw
- processing layer continues from common raw upward

The polling runtime must not:

- bypass the ingest contract
- write directly into canonical or final tables
- hide watermark state inside opaque code-only memory

## Recommended acceptance signal for closing the next main gap

The current scheduling and operations gap can be considered meaningfully closed only when all of the following are true:

1. eligible polling adapter instances can create queued runs without manual UI action
2. scheduled and manual runs use the same worker execution path
3. overlapping runs for one adapter instance are prevented
4. stale or overdue adapter conditions are visible to operators
5. the current `Pause` semantics still prevent future scheduled work safely

## Related documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-implementation-sequence.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-implementation-sequence.md)
