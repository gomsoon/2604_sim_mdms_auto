# Pipeline Orchestration

## Purpose

This document defines the orchestration baseline for moving data through the MDM layers after records have entered the data layer.

## Why this is a separate concern

The data layer answers:

- what tables exist
- what each layer stores
- how lineage is preserved

The orchestration layer answers:

- when processing runs
- what unit of work gets picked up
- how layer-to-layer progression is tracked
- how failures, retries, and reprocessing are handled
- how administrators can see current processing status

## Core recommendation

Do not hard-code layer progression directly into scattered application logic.

Instead, use a lightweight orchestration model that is:

- schedule-oriented by default
- run/status aware
- auditable
- reprocess-friendly
- simple enough for the minimal stage

## What we are not recommending right now

For the current phase, a heavy workflow engine is not required.

Not required at this stage:

- full workflow platform
- complex DAG orchestration engine
- highly dynamic rule-driven process routing
- vendor-specific processing flows after the common raw layer

## Recommended minimal orchestration approach

### Execution style

Start with a schedule-first model.

Examples:

- raw to canonical every few minutes
- canonical or initial processing on a recurring batch window
- finalization on a recurring batch window

Later, this can evolve into a hybrid model that combines:

- fixed schedule
- ingest-triggered readiness
- manual reprocess requests

### Processing philosophy

- raw ingest writes data into the data layer
- orchestration selects work that is `waiting` or otherwise ready
- processing runs advance data to the next layer
- each run records status and timing
- failures remain visible and re-runnable

## Recommended status model

At minimum, the orchestration layer should support statuses such as:

- `waiting`
- `processing`
- `completed`
- `failed`

Optional later statuses:

- `retry_pending`
- `skipped`
- `cancelled`

## Recommended processing units

The exact processing unit can vary, but should be explicit.

Useful candidate units:

- ingest batch
- source system plus time window
- meter plus date range
- scenario or reprocess request

For the minimal stage, the simplest starting unit is usually:

- ingest batch for raw intake progression
- time window or batch-based progression for higher layers

## Suggested orchestration metadata concepts

The exact table design can be decided later, but the following concepts are recommended.

### Pipeline definition

Represents the configured processing stage.

Examples:

- raw to canonical
- canonical to initial
- initial through VEE
- finalization

### Pipeline run

Represents one execution of a pipeline stage.

Useful fields:

- stage name
- run status
- started at
- finished at
- trigger type
- records attempted
- records succeeded
- records failed
- error summary

### Work unit or processing target

Represents what the run is acting on.

Useful fields:

- source system
- batch ID
- date range
- meter ID if relevant
- current status

### Watermark

Represents how far a recurring process has advanced.

Useful for:

- incremental polling
- incremental canonicalization
- avoiding repeated full-table scans

### Reprocess request

Represents an explicit request to re-run a failed or corrected processing scope.

Useful fields:

- requested scope
- reason
- requested by
- request status

## Recommended trigger model

### Initial minimal-stage recommendation

- use fixed schedule as the primary trigger
- allow manual reprocess trigger later
- keep event-driven triggering as a later enhancement

Why:

- simpler to operate
- easier to debug
- easier to make visible in the dashboard

### Future-ready direction

Add hybrid triggering only when useful:

- schedule for periodic safety net
- ingest-triggered readiness for faster response
- manual reprocess for operational recovery

## Relationship to the data layers

The orchestration layer moves data upward through the following conceptual path:

- landing, if used
- common raw
- canonical or initial
- VEE and audit
- final
- usage and bill determinant

The orchestration layer does not replace those layers. It coordinates progression between them.

## Relationship to operational events and alerts

The orchestration layer should also act as one of the main producers of operator-facing events and alerts.

Why:

- status rows alone are not a readable operational timeline
- operators need milestone visibility, not only final state counts
- failures and overdue conditions should become prominent alerts, not only hidden run records

Recommended minimal rule:

- meaningful pipeline milestones should emit operational events
- failed or blocked processing milestones should emit alerts
- dashboard stage cards and the event timeline should agree on the same underlying interpretation

## Administrator dashboard recommendation

Your idea of dashboard cards at the top is a strong fit for this project.

Why it is useful:

- administrators can see where data is waiting
- they can see whether processing is currently active
- they can see whether a stage is stuck or failing
- they can see completion trend without drilling into logs first

## Recommended dashboard card model

At the top of the dashboard, show one card per major layer or processing stage.

### Suggested initial cards

- `Raw Ingest`
- `Canonical`
- `Initial/VEE` later when introduced
- `Final` later when introduced
- `Errors`

### Minimum fields per card

- layer or stage name
- count in `waiting`
- count in `processing`
- count in `completed`
- count in `failed`

### Recommended additional fields

- last run time
- last successful completion time
- next scheduled run time
- source system filter or badge when useful

## Example dashboard interpretation

Examples of what an administrator should be able to tell quickly:

- raw ingest is healthy but canonical processing is backlogged
- canonical processing is running now
- a finalization stage has not succeeded recently
- failures are concentrated in one source system
- there is no current backlog and all stages are caught up

## UI behavior recommendation

- use card color or emphasis carefully, not excessively
- make the cards summary-first
- allow click-through from each card into filtered detail screens
- keep labels localizable in English and Korean

## Recommended minimal dashboard status sources

The earliest version does not need a full orchestration platform to provide value.

Status cards can initially be derived from:

- `ingest_batch` status
- counts from `hes_read_raw` awaiting or completing canonicalization
- counts from `ingest_error_log`
- later pipeline run metadata as it becomes available

## Open decisions intentionally left for later

- exact scheduler tool
- exact run-metadata table design
- exact background worker model
- exact reprocess API shape
- exact hybrid trigger rules

These should remain explicit design decisions rather than accidental implementation details.

## Minimal-stage recommendation summary

For the minimal stage:

- use a lightweight orchestration model
- prefer schedule-first execution
- track `waiting`, `processing`, `completed`, and `failed`
- expose stage status through dashboard cards
- avoid hard-coded implicit layer progression
- defer heavy workflow-engine selection

## Related documents

- [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
- [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
