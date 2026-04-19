# Polling Adapter Baseline

## Purpose

This document defines the proposed first implementation baseline for a polling runtime adapter.

It answers:

- what the first polling adapter should do
- what should be included in the first implementation
- what should be deferred until later

## Why start with polling

For this project, polling is a practical early runtime adapter target because:

- the company HES is expected to expose database structures that can be reviewed
- polling fits the schedule-first orchestration stance already documented
- polling can be tested safely with `Run Once`
- polling gives the team a production-like integration shape without needing a full event platform first

## Core recommendation

The first polling adapter should be:

- code-backed
- operator-managed as an adapter instance
- schedule-first
- watermark-aware
- limited in scope

The first version should not try to solve every future connector pattern.

## Recommended first target

The first polling baseline should prioritize:

- one polling runtime adapter family
- company HES as the first target source
- raw read collection first

Raw events can follow the same runtime pattern later, but the first implementation should focus on reads because the strongest current end-to-end path already depends on them.

## Recommended architectural shape

The first polling adapter should follow this conceptual path:

1. scheduler selects an eligible adapter instance
2. an `adapter_run` is created
3. the adapter connects to the upstream HES source
4. the adapter fetches source rows by window or watermark
5. the adapter converts source rows into the documented ingest payload shape
6. the existing ingest service persists into common raw
7. runtime metadata such as run result and source cursor are updated

This preserves the current system boundary:

- runtime adapter fetches data
- ingest service owns persistence into the MDM data layer

## Recommended first delivery mode

The first polling adapter should use:

- `poll`

It should not try to support both `poll` and `receive` behavior in the same implementation module immediately.

The lifecycle model can support both modes, but the first concrete implementation should stay narrow.

## Recommended first processing scope

The first polling adapter should support:

- source system selection
- polling schedule
- batch size limit
- source watermark or cursor
- `Run Once`
- recent run history

The first version does not need:

- multi-source fan-out inside one run
- advanced partition parallelism
- dynamic routing by source schema version
- multi-step landing and normalization orchestration inside one runtime adapter

## Recommended persistence concepts

The exact schema can still be decided later, but the first polling baseline likely needs:

The fuller baseline persistence proposal is defined in [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md).

### Adapter definition

Represents the polling adapter type.

Useful first fields:

- adapter code
- mode = `poll`
- supported record type
- adapter profile key
- implementation code

### Adapter instance

Represents one configured company HES polling connection.

Useful first fields:

- adapter definition reference
- display name
- source system
- admin state
- poll interval minutes
- batch size
- next run at
- masked connection configuration
- source cursor or watermark summary

### Adapter run

Represents one polling cycle.

Useful first fields:

- adapter instance reference
- trigger type
- run status
- started at
- completed at
- source rows fetched
- ingest batches created
- ingest records created
- error summary

### Source cursor or watermark

Represents how the adapter knows where to resume.

The first version can implement this as:

- dedicated adapter watermark persistence
- or adapter-instance state if the design stays small

The key requirement is that it must be explicit and auditable.

## Recommended first trigger model

The first polling baseline should support two trigger types:

- `schedule`
- `manual`

Recommended meaning:

- `schedule`: normal recurring collection
- `manual`: operator-triggered `Run Once`

This is enough for the first production-like polling path.

## Recommended scheduler shape

The first implementation should stay lightweight.

Recommended baseline:

- a simple recurring scheduler or periodic command
- one execution path shared by scheduled and manual runs
- one active run per adapter instance at a time

Not required initially:

- distributed work coordination
- DAG workflow orchestration
- dynamic priority queues
- highly parallel shard control

## Recommended fetch model

The first polling adapter should fetch data by an explicit incremental boundary.

Recommended choices:

- source timestamp watermark
- source sequence or numeric key

Avoid a first version that repeatedly full-scans the upstream source.

## Recommended safety rules

The first polling adapter should follow these rules:

- do not write directly into downstream tables beyond the ingest boundary
- do not bypass the ingest contract or ingest service
- keep source fetch scope explicit
- keep source cursor updates explicit
- keep original source rows auditable through payload preservation
- do not allow overlapping active runs for the same adapter instance
- keep connection settings masked in the UI

## Recommended relationship to landing and common raw

If the polled source can be mapped safely through a field-normalization adapter profile, it should proceed into common raw directly.

If source rows cannot be normalized safely by field mapping alone, the design should allow:

- polling into a landing area first
- then controlled movement into common raw

The first polling adapter does not need to implement both paths at once, but it must not block the landing option later.

## Recommended first UI expectations

For the first polling adapter baseline, the UI should support:

- adapter list view
- adapter detail view
- `Enable`
- `Pause`
- `Run Once`
- recent run visibility
- last success and last failure visibility
- next run time visibility

This should align with [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md).

## Recommended first operational metrics

At minimum, the polling baseline should expose:

- last run status
- last success time
- last failure time
- source rows fetched
- ingest batches created
- records loaded into common raw

These metrics help operators understand whether the runtime adapter is functioning before they need deeper processing-layer investigation.

## Recommended first implementation boundaries

Include now:

- one polling adapter implementation family
- one adapter instance model
- one adapter run model
- `Run Once`
- schedule-based execution
- explicit source watermark
- operator visibility

Defer for later:

- multiple polling adapter families at once
- arbitrary SQL editing from the UI
- advanced credential management platform
- distributed scheduler cluster
- automatic retry backoff policy matrix
- event streaming integration

## Recommended implementation sequence

The most stable first sequence is:

1. finalize runtime adapter lifecycle and UI action scope
2. add adapter definition, adapter instance, and adapter run persistence
3. add read-only adapter list and detail visibility
4. add `Enable`, `Pause`, and `Run Once`
5. implement one company-HES polling path for raw reads
6. connect scheduler and dashboard integration status

## Recommended immediate baseline

If the team wants the smallest credible first polling answer now, the recommendation is:

- one company-HES polling adapter for raw reads
- one adapter instance at a time
- shared execution path for schedule and `Run Once`
- explicit source watermark
- operator visibility before broader automation

This is enough to prove runtime adapter management without overbuilding.

## Relationship to other documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
