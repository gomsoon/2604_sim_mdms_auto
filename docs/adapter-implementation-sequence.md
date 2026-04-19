# Adapter Implementation Sequence

## Purpose

This document turns the current adapter baseline into a practical near-term implementation order.

The goal is to make adapter work progress in a way that is:

- layered
- auditable
- testable
- low-risk

## Guiding rule

The next adapter work should prioritize execution correctness over UI expansion.

That means the preferred order is:

1. make queued adapter runs executable
2. make polling incremental and traceable
3. make runtime status accurate
4. then expand receive mode and richer controls

## Recommended sequence

### Phase 1. Runtime execution contract

#### Goal

Introduce the service boundary that turns an `adapter_run` from a queued row into an executable unit of work.

#### Why first

The project already has:

- adapter instance management
- adapter run persistence
- run queueing from the UI

Without an execution contract, those pieces stop one step too early.

#### Key tasks

- define a runtime execution registry keyed by `adapter_definition.implementation_key`
- introduce a shared execution result object such as:
  - fetched row count
  - created ingest batch count
  - created ingest record count
  - watermark before
  - watermark after
  - error code
  - error summary
- add service functions to:
  - claim a waiting run
  - mark it `running`
  - complete it
  - fail it

#### Exit criteria

- one worker entry point can consume a queued run safely
- one run cannot be claimed twice
- `waiting -> running -> completed|failed` state transition is explicit

### Phase 2. First company HES polling adapter

#### Goal

Implement the first real code-backed polling runtime for company HES raw reads.

#### Why second

The project should prove one complete production-like polling path before adding receive mode or multiple adapter families.

#### Key tasks

- implement one runtime adapter module for `company_hes_poll_v1`
- keep it focused on:
  - raw reads
  - one source family
  - one incremental boundary
- fetch upstream rows by timestamp watermark or other explicit cursor
- convert upstream rows into the existing ingest payload contract
- call the existing ingest service

#### Important rule

The polling adapter should not persist directly into:

- `hes_read_raw`
- `canonical_measurement`
- `final_measurement`

It should only cross the boundary through the ingest service.

#### Exit criteria

- one manual `Run Once` can read upstream data and ingest it
- one successful execution can produce real `ingest_batch` and raw rows
- one failed execution leaves a clear adapter run failure record

### Phase 3. Watermark advancement and duplicate prevention

#### Goal

Make polling incremental, resumable, and safe against repeat collection.

#### Why third

A real polling adapter is not operationally credible if it full-scans repeatedly.

#### Key tasks

- read the current `adapter_watermark` before polling
- record `watermark_before` on the run
- query upstream rows using the explicit cursor boundary
- update `adapter_watermark` only after successful ingest
- record `watermark_after` on the run

#### Interaction with existing duplicate protection

The ingest duplicate check should remain as a safety net.

Recommended role split:

- watermark: primary prevention of re-fetch
- duplicate raw detection: secondary prevention of bad re-load

#### Exit criteria

- repeated runs without new upstream data do not recreate the same raw records
- the resume point is visible and auditable
- watermark changes can be traced through run history

### Phase 4. Runtime summary and lineage updates

#### Goal

Make adapter status and lineage reflect real execution outcomes.

#### Why fourth

Once execution exists, the UI must stop relying on mostly seeded or manually managed summary values.

#### Key tasks

- update `adapter_instance.last_success_at` on successful completion
- update `adapter_instance.last_failure_at` and `last_error_message` on failure
- update `adapter_instance.next_run_at` for polling instances
- populate `ingest_batch.adapter_instance_id`
- populate `ingest_batch.adapter_run_id`

#### Exit criteria

- adapter detail and list screens reflect real runtime history
- ingest batches can be traced back to adapter instance and run

### Phase 5. Lightweight adapter runner

#### Goal

Support schedule-driven execution in addition to operator-triggered manual runs.

#### Why fifth

The minimal stage favors a lightweight scheduler over a full workflow platform.

#### Key tasks

- add a periodic command or lightweight scheduler entry point
- select eligible adapter instances by:
  - `admin_state = enabled`
  - `delivery_mode = poll`
  - `next_run_at <= now`
- enqueue or directly execute one run at a time per adapter instance

#### Exit criteria

- polling adapter instances can run on schedule
- overlapping runs for one instance are prevented

### Phase 6. Dashboard integration visibility

#### Goal

Expose adapter runtime health in the main operator dashboard.

#### Why sixth

This becomes high-value after the execution path is real.

#### Key tasks

- add an `Integration` or `Adapters` stage card
- summarize:
  - ready
  - running
  - paused
  - error
- expose recent adapter failures and last success timestamps

#### Exit criteria

- operators can see integration health without opening adapter detail first

### Phase 7. Receive adapter baseline

#### Goal

Add the first runtime-managed receive path after polling is stable.

#### Why seventh

The lifecycle model already supports `receive`, but a receive runtime should reuse the proven execution and visibility model.

#### Key tasks

- define one receive-oriented implementation contract
- add lifecycle handling for:
  - receive heartbeat
  - receive failures
  - last delivery visibility
- keep the same ingest-boundary rule as polling

#### Exit criteria

- one receive adapter can be managed through the same instance/run model
- receive health is operationally visible

## Explicit deferrals

The following should not come before the polling execution baseline:

- arbitrary SQL editing from the UI
- dynamic runtime adapter code generation
- multiple polling families at once
- distributed scheduler coordination
- complex retry graphs
- advanced secret-management platform integration

## Recommended immediate next step

The most valuable next implementation step is:

- Phase 1 and Phase 2 together

Concretely:

1. add a runtime execution registry
2. add one worker entry point that consumes `waiting` runs
3. implement `company_hes_poll_v1`
4. run it through the existing ingest path

## Recommended first acceptance flow

The first end-to-end runtime adapter acceptance scenario should be:

1. operator registers a polling adapter instance
2. operator clicks `Run Once`
3. a queued `adapter_run` is created
4. worker claims the run and marks it `running`
5. worker fetches new company HES read rows using the stored watermark
6. worker calls ingest and creates `ingest_batch`
7. worker updates watermark and marks the run `completed`
8. operator sees the resulting batch, raw rows, and updated adapter status in the UI

## Related documents

- [adapter-gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-gap-analysis.md)
- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
