# Adapter Implementation Sequence

## Purpose

This document turns the current adapter baseline into a practical near-term implementation order.

The goal is to make adapter work progress in a way that is:

- layered
- auditable
- testable
- low-risk

## Guiding rule

The next adapter work should prioritize scheduler-safe operation and boundary clarity over broader UI expansion.

That means the preferred order is:

1. make polling runnable on schedule
2. make integration health clearer to operators
3. keep manual and scheduled execution on one shared path
4. then expand receive mode and richer controls

## Recommended sequence

### Phase 1. Schedule-driven run enqueueing

#### Goal

Introduce the minimal scheduler-side boundary that turns eligible polling adapter instances into queued `adapter_run` rows.

#### Why first

The project already has:

- adapter instance management
- adapter run persistence
- run queueing from the UI
- a worker execution path for queued runs

Without schedule-driven enqueueing, polling remains operationally manual.

#### Key tasks

- add a periodic command or scheduling entry point that:
  - selects `poll` adapter instances
  - requires `admin_state = enabled`
  - requires `next_run_at <= now`
  - skips instances with waiting or running work
- create one `adapter_run` row per eligible instance
- update `next_run_at` consistently for scheduled polling

#### Exit criteria

- polling adapters can move from passive configuration into queued work without manual UI action
- one instance does not receive overlapping scheduled runs
- manual and scheduled runs remain auditable in the same model

### Phase 2. Integration health and stale-state visibility

#### Goal

Make adapter health easier to understand from the operator dashboard and adapter screens.

#### Why second

The execution path now exists, so the next risk is poor operational visibility rather than missing basic runtime capability.

#### Key tasks

- add stale or overdue interpretation for polling adapters
- show whether `next_run_at` is overdue
- summarize pending runs, running runs, and recent failures more explicitly
- keep the `Integration` card aligned with adapter effective status and recent execution outcomes

#### Important rule

This phase should remain visibility-focused and should not introduce hard-stop behavior.

#### Exit criteria

- operators can tell whether adapters are merely paused, actually failing, or simply overdue
- dashboard and adapter detail pages reflect the same execution truth

### Phase 3. Shared execution path hardening

#### Goal

Keep manual and scheduled execution on the same safe runtime path.

#### Why third

Once schedule-driven enqueueing exists, the shared execution path becomes more important than new surface features.

#### Key tasks

- verify that scheduled runs use the same execution path as `Run Once`
- keep watermark advancement and lineage behavior identical across both triggers
- add more concurrency and overlap protection tests for scheduled scenarios

#### Interaction with existing duplicate protection

The ingest duplicate check should remain as a safety net.

#### Exit criteria

- manual and scheduled runs produce the same audit and lineage shape
- repeated runs without new upstream data do not recreate the same raw records
- watermark changes remain visible and auditable

### Phase 4. Receive adapter baseline

#### Goal

Add the first runtime-managed receive path after polling is stable.

#### Why fourth

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

The following should not come before the schedule baseline:

- arbitrary SQL editing from the UI
- dynamic runtime adapter code generation
- multiple polling families at once
- distributed scheduler coordination
- complex retry graphs
- hard-stop semantics for active runs
- advanced secret-management platform integration

## Recommended immediate next step

The most valuable next implementation step is:

- Phase 1 and Phase 2 together

Concretely:

1. add schedule-driven enqueueing for eligible poll adapters
2. keep the existing worker as the shared execution path
3. add overdue and stale adapter visibility
4. preserve the current `Pause` and `Run Once` semantics

## Recommended first acceptance flow

The first end-to-end scheduled adapter acceptance scenario should be:

1. operator registers a polling adapter instance
2. operator leaves the adapter in `enabled`
3. scheduler command creates a queued `adapter_run`
4. worker claims the run and marks it `running`
5. worker fetches new HES read rows using the stored watermark
6. worker calls ingest and creates `ingest_batch`
7. worker updates watermark and marks the run `completed`
8. operator sees the resulting batch, raw rows, updated adapter status, and integration summary

## Related documents

- [adapter-gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-gap-analysis.md)
- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
