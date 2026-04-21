# Integration Adapter Management

## Purpose

This document defines how the project should think about HES adapters from an operational and architectural point of view.

The goal is to avoid confusion between:

- a lightweight field-normalization adapter profile
- a runtime adapter that actually connects to an external HES and moves data into the MDM system

Those are related, but they are not the same thing.

## Why this document matters

If the project treats every adapter concern as one vague concept, implementation will drift in the wrong direction.

Typical failure modes are:

- source field mapping logic mixed with connection lifecycle control
- polling code embedded directly in web routes
- no clear place to represent adapter status, last success, or last failure
- no operational screen for pausing or resuming a problematic source

This document separates those concerns so that the integration layer can evolve without destabilizing the data and processing core.

## Core distinction

### 1. Adapter profile

An adapter profile is a normalization rule set applied before common raw persistence.

Typical responsibilities:

- map source-specific field names to the common raw contract
- normalize collection keys such as `reads` or `events`
- preserve the original payload while producing a normalized payload for parsing

Examples:

- `common_raw_v1`
- `legacy_hes_v1`

This kind of adapter is lightweight and declarative.

### 2. Runtime adapter

A runtime adapter is a controllable integration unit that actually connects to an upstream HES or other source.

Typical responsibilities:

- poll or receive upstream data
- manage credentials and connectivity
- track heartbeat and run status
- pause or resume collection
- trigger data movement into the ingest boundary

Examples:

- company HES polling adapter
- vendor A API receiver
- vendor B database polling adapter

This kind of adapter is operational and lifecycle-oriented.

## Current implementation status

At the current minimal stage, the project has implemented adapter profiles and a lightweight runtime execution baseline, but not a full always-on adapter control plane.

Implemented now:

- lightweight ingest adapter registry
- `adapter_key` contract support
- normalization into the common raw ingest shape
- original payload preservation
- source-aware ingest and processing status through `pipeline_run` and dashboard cards
- runtime adapter persistence through definition, instance, run, and watermark tables
- runtime adapter registration from approved definitions
- adapter instance lifecycle control such as `enable` and `pause`
- operator-triggered `Run Once` queueing
- adapter list and detail screens
- adapter-specific recent run and watermark visibility
- code-backed runtime execution selected by `implementation_key`
- a lightweight worker command that consumes queued `adapter_run` rows
- runtime lineage population into `ingest_batch`
- source-specific polling execution baseline for the first company overseas HES source

Not implemented yet:

- upstream receive runtime handling
- polling scheduler for source adapters
- hard-stop or force-cancel control for already-running adapter executions
- in-process scheduler management from the Flask web process
- full OS-service lifecycle control from the operator UI

## Current code interpretation

The existing code should be interpreted like this:

- `app/services/ingest_adapters.py` handles adapter profiles
- `app/services/adapters.py` handles runtime adapter registration, lifecycle transitions, and run queueing
- `app/services/adapter_execution.py` handles code-backed runtime execution and watermark-aware run completion
- `app/services/ingestion.py` handles ingest processing after a payload has already arrived
- the current UI now manages adapter instances as operational objects
- the current system executes runtime adapter work through a separate worker path rather than directly inside web requests

This means the current implementation is suitable for:

- API-first ingest
- manual or externally triggered payload delivery
- source-field normalization before common raw persistence

It is not yet sufficient for:

- production polling from multiple HES instances
- operator control of upstream collection at OS-process level
- long-running adapter health monitoring
- generalized watermark-driven incremental source fetching across multiple source families
- force-stop semantics for active runs

The exact minimal operational boundary is defined in [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md).

## Recommended architectural rule

The integration layer should contain two explicit sub-concepts:

- adapter profile
- adapter runtime

Recommended rule:

- adapter profiles normalize payload shape
- adapter runtimes control source connectivity and collection lifecycle
- neither concept should leak vendor-specific behavior into common raw, canonical, or final business layers

## Recommended minimal target after the current stage

The next stage does not need a full connector platform, but it should introduce a minimal runtime management model.

Recommended minimum:

- register adapter instances
- enable or pause adapter instances
- run an adapter once on demand
- record last success, last failure, and current status
- keep recent adapter execution history

This is enough to make the integration layer operable without overbuilding a plugin framework too early.

The proposed minimal lifecycle model is defined in [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md).
The recommended first operator control scope is defined in [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md).
The recommended first polling implementation scope is defined in [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md).
The recommended minimum persistent shape is defined in [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md).
The current implementation gap is summarized in [adapter-gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-gap-analysis.md).
The recommended next implementation order is defined in [adapter-implementation-sequence.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-implementation-sequence.md).

## Recommended persistence concepts

The exact table names can be decided later, but the following concepts are recommended.

### Adapter definition

Represents the adapter type.

Useful fields:

- adapter code
- mode such as `push` or `poll`
- source family
- supported record types
- adapter profile key
- implementation type

This is closer to a template than a runtime object.

### Adapter instance

Represents one real external connection or configured source.

Useful fields:

- adapter definition reference
- display name
- source system
- enabled flag
- current status
- schedule settings
- masked connection settings
- landing enabled flag when needed

This is the main operational object an administrator would manage.

### Adapter run

Represents one adapter execution attempt.

Useful fields:

- adapter instance reference
- started at
- completed at
- status
- trigger type such as `schedule`, `manual`, or `receive`
- records fetched or received
- batches created
- error summary

### Adapter heartbeat or status snapshot

Represents the current operational state.

Useful fields:

- current status
- last heartbeat
- last success
- last failure
- last error message

This may be its own table or derived from recent runs, depending on implementation.

## Recommended administrator UI baseline

The frontend should eventually expose runtime adapters as operational objects.

Recommended minimal screen capabilities:

- adapter list
- source system and mode display
- current status badge
- last success and last failure timestamps
- last error summary
- `Enable`
- `Pause`
- `Run Once`
- recent run history drill-down

This UI should manage adapter instances, not code-defined adapter profiles.

## Recommended dashboard relationship

The current dashboard already shows data-stage and processing-stage status.

Later, the dashboard should also include an integration visibility concept.

Recommended future card:

- `Integration`

That card should summarize:

- adapters ready
- adapters running
- adapters paused
- adapters in error
- last successful collection activity
- pending adapter runs

This card complements the current `Raw Ingest`, `Canonical`, `Final`, and `Errors` cards.

For the first dashboard implementation, this card should appear before downstream processing cards so operators can confirm upstream collection health first.

## What administrators should and should not do in the UI

### Reasonable UI responsibilities

- enable or disable an adapter instance
- pause or resume collection
- run once manually
- inspect recent failures
- inspect source metadata and target mode

### Not a priority yet

- building arbitrary new runtime adapter code entirely from the UI
- defining full custom polling SQL or API logic in an unrestricted admin screen
- building a full plugin marketplace inside the product

For the near term, runtime adapter implementations should remain code-backed, while instances and operations become admin-managed.

## Recommended phased direction

### Phase A. Current baseline

- adapter profile registry only
- API-first ingest path
- no runtime lifecycle control

### Phase B. Minimal runtime management

- adapter definition and adapter instance concepts
- operator visibility and control
- manual run-once support
- status and run history

### Phase C. Polling baseline

- scheduled polling for selected adapter instances
- heartbeat and failure visibility
- safe pause and resume

### Phase D. Broader integration model

- more than one HES family
- landing-table path when direct common raw ingest is not safe
- richer scheduling and retry controls

## Recommended immediate next step

Before implementing runtime adapter control, the team should agree on:

- the minimal runtime adapter lifecycle
- the first adapter instance model
- the operator actions allowed in the UI

The project does not need to solve every future connector problem now.

It does need a stable distinction between:

- payload normalization
- source runtime management

## Relationship to other documents

- [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
- [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
