# Core Stability Goals

## Purpose

This document defines what the project should try to keep stable in the long run, especially in the data layer and processing layer.

It is not a claim that everything is already solved.

It is a statement of what should remain central and what implementation choices should move us toward that goal.

## Why the data and processing layers are the core

The frontend can change.

The HES integration method can change.

Even specific connectors or operator screens can change.

What is much harder to change safely is:

- the meaning of each persisted data state
- the rules that move data from one state to another
- the lineage and audit model that explains how a record became bill-ready

For that reason, the project should treat:

- data layer contracts
- processing layer contracts

as the primary architecture center.

## Stability goal 1. The meaning of each data stage must be explicit

Each major data state should have a defined purpose.

At minimum, the system should clearly distinguish between:

- landing, when used
- common raw
- canonical or initial
- later well-formed or VEE-reviewed state
- final
- downstream billing-ready state

If a stage exists, its role must be clear.

If a stage is not yet implemented physically, its intended semantic meaning should still be defined.

## Stability goal 2. Raw data should remain a trustworthy source-of-truth layer

The common raw layer should not be treated as disposable temporary storage.

It should preserve:

- source trace
- source identifiers
- original payload
- receive timing
- linkage to errors and later stages

The project should prefer append-and-link behavior over destructive overwrite behavior.

## Stability goal 3. Vendor variance should be contained below common raw

The system should be flexible at ingest boundaries but standardized as early as possible.

That means:

- vendor-specific landing is allowed
- vendor-specific parsing is allowed
- vendor-specific common raw and canonical models should be avoided

The goal is that later layers do not care which HES vendor originated the data.

## Stability goal 4. Stage transitions should be explicit, auditable, and re-runnable

Movement between data states should not feel like hidden side effects.

The processing layer should make it possible to answer:

- what moved
- from which state
- to which state
- by which run or trigger
- when it happened
- whether it succeeded or failed
- how it can be reprocessed

Even before a full orchestration framework exists, the implementation should move toward this model.

## Stability goal 5. Processing should be idempotent where practical

The system should aim for safe repeated execution.

This is important for:

- retries
- duplicated upstream delivery
- backfill
- reprocessing after master-data correction

Idempotency may not be perfect in every stage immediately, but it should remain a design target.

## Stability goal 6. Processing units should be explicit

The project should avoid vague, implicit processing scope.

Useful processing units include:

- ingest batch
- source system plus time window
- meter plus date range
- reprocess request

The exact unit can evolve, but the system should always know what work scope a run is acting on.

## Stability goal 7. Data and processing rules should not be defined by the UI

The UI may expose and trigger workflows, but it should not become the source of truth for:

- stage semantics
- business state rules
- orchestration decisions
- lineage interpretation

The UI should present core system meaning, not invent it.

## Stability goal 8. Stable codes should be separate from localized messages

The core system should prefer stable codes and statuses over fragile human text.

Examples:

- ingest error codes
- stage statuses
- exception types
- processing run statuses

Human-facing messages can be localized and improved later, but stable codes should remain consistent.

## Stability goal 9. Schema growth should follow clear contracts, not ad hoc convenience

When new tables or states are added, the reason should be structural.

Good reasons:

- new durable data state
- new lineage boundary
- new audit need
- new processing responsibility

Weak reasons:

- temporary UI shortcut
- vendor-specific special case leaking upward
- one-off experimental logic being made permanent too early

## Stability goal 10. The processing layer should become more declarative over time

The project does not need a heavy workflow engine right now.

But over time, the system should move away from scattered hard-coded transitions and toward explicit processing metadata such as:

- stage names
- run status
- work-unit scope
- retry or reprocess requests
- last-run visibility

The immediate implementation can be simple.

The long-term direction should still be explicit.

## Recommended implementation posture

These goals suggest the following practical posture.

### What to simplify now

- keep orchestration lightweight
- avoid over-generalized frameworks too early
- allow simple route-triggered or schedule-first processing for minimal stage

### What to protect now

- raw immutability
- lineage
- stable stage meanings
- stable codes
- vendor-neutral common raw onward

### What to externalize gradually

- processing metadata
- stage run history
- reprocess requests
- rule configuration where useful

## Good near-term architectural habits

The following habits move the project toward long-term stability:

- add service-layer boundaries before large new features
- keep business transitions out of templates
- treat new statuses and codes as contracts
- prefer additive schema evolution
- make reprocessing a design question, not an afterthought
- keep landing optional and common raw mandatory

## Open design questions that are still acceptable

It is acceptable that some details are not final yet.

Examples:

- whether `well_formed` becomes its own table or a later-stage semantic state
- what the first concrete pipeline metadata tables should be called
- how far manual reprocess should go in the minimal stage
- how much of orchestration should be schedule-based vs trigger-based initially

These are still open.

What should not remain vague is the direction.

## Direction summary

The project should aim for a system where:

- integration is flexible
- data stages are explicit
- processing is auditable
- reprocessing is possible
- vendor-specific behavior is contained low in the stack
- UI evolves on top of a stable core rather than defining that core

## Relationship to other documents

- [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
- [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
