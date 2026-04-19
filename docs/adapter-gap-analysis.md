# Adapter Gap Analysis

## Purpose

This document clarifies the current gap between the adapter-related baseline already implemented in the repository and the next production-like runtime adapter target.

It exists to answer two recurring questions clearly:

- what is already implemented today
- what is still missing before a real polling or receive adapter can be considered operational

## Executive summary

The repository has already implemented:

- field-normalization adapter profiles before common raw ingest
- runtime adapter persistence
- operator-facing adapter instance management
- operator-facing `Run Once` queueing
- adapter run history visibility
- adapter watermark persistence as an explicit model

The repository has not yet implemented:

- code-backed runtime execution selected by `implementation_key`
- a worker or scheduler that consumes `adapter_run` rows in `waiting` status
- an actual polling path that reads upstream HES rows by watermark
- a receive runtime path that accepts externally delivered records as a managed adapter lifecycle
- automatic summary updates such as `last_success_at`, `last_failure_at`, `last_heartbeat_at`
- automatic linkage from runtime execution into `ingest_batch.adapter_instance_id` and `ingest_batch.adapter_run_id`

So the current system should be understood as:

- operationally visible
- partially controllable
- not yet execution-complete

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
- the schema is ahead of the execution engine

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
- operators cannot yet trigger real upstream data movement

### 4. Runtime execution engine

Status:

- not implemented

Current shape:

- `Run Once` currently queues an `adapter_run` row with `run_status="waiting"`
- no service currently:
  - claims that waiting run
  - marks it `running`
  - connects to an upstream source
  - fetches source rows
  - calls ingest with runtime lineage
  - marks the run `completed` or `failed`

Conclusion:

- runtime control exists
- runtime execution does not yet exist

### 5. Polling resume and duplicate prevention

Status:

- partially implemented

Implemented now:

- `adapter_watermark` exists and can store cursor state explicitly
- `adapter_run` can record `watermark_before` and `watermark_after`
- raw ingest performs duplicate detection in [app/services/ingestion.py](/home/tprover/2604_sim_mdms_auto/app/services/ingestion.py)

Not implemented yet:

- no polling worker actually reads `adapter_watermark`
- no polling query is currently built using `WHERE source_timestamp > last_watermark`
- no automatic watermark advancement happens after successful polling

Important distinction:

- current duplicate protection is mainly a downstream ingest safeguard
- it is not yet a true incremental polling safeguard

Recommended interpretation:

- current duplicate detection is the second line of defense
- adapter watermark-driven incremental fetch must become the first line of defense

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
| Waiting run queueing | Implemented | Medium | Queue exists but not consumed |
| Runtime implementation dispatch | Missing | High | No `implementation_key` execution registry yet |
| Polling worker | Missing | High | Core runtime gap |
| Receive runtime worker | Missing | High | Deferred after polling |
| Watermark-driven incremental fetch | Missing | High | Core duplicate-prevention gap |
| Automatic summary updates on instance | Missing | Medium | Needed for accurate UI |
| Ingest lineage from runtime execution | Missing | Medium | Needed for traceability |
| Scheduler / periodic adapter runner | Missing | Medium | Needed beyond manual run queue |
| Heartbeat / health monitoring | Missing | Medium | More important after execution exists |

## Most important implementation truth

The biggest remaining gap is not UI and not persistence.

The biggest remaining gap is:

- executable runtime behavior

That means the next valuable work should not be:

- a larger adapter CRUD surface
- arbitrary adapter code editing from the UI
- a receive adapter before polling works

The next valuable work should be:

- consuming `adapter_run`
- executing one real polling adapter implementation
- advancing watermark state safely
- linking execution to the existing ingest pipeline

## Recommended architectural rule for the next phase

The next implementation phase should keep this boundary:

- runtime adapter fetches upstream data
- ingest service persists into common raw
- processing layer continues from common raw upward

The polling runtime must not:

- bypass the ingest contract
- write directly into canonical or final tables
- hide watermark state inside opaque code-only memory

## Recommended acceptance signal for closing the main gap

The main runtime gap can be considered meaningfully closed only when all of the following are true:

1. a queued `adapter_run` can be consumed automatically or manually by a worker
2. the worker uses `implementation_key` to select a real runtime adapter implementation
3. the polling adapter reads upstream rows by explicit watermark or cursor
4. the worker calls the existing ingest service rather than bypassing it
5. `adapter_run` is updated to `completed` or `failed`
6. `adapter_watermark` advances only after a successful fetch-and-ingest cycle
7. `ingest_batch` records can be traced back to the adapter instance and adapter run

## Related documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-implementation-sequence.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-implementation-sequence.md)
