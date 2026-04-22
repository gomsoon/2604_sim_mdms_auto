# HES-Centric Operations Plan

## Purpose

This document defines the next implementation step after the initial `hes_system` registry baseline.

The project now has:

- `hes_system` persistence
- HES list and detail screens
- parent HES lineage in adapter, batch, landing, and raw tables

What remains is to make the operator workflow feel genuinely HES-centric rather than still adapter-centric.

## Why this document matters

The system now has the right parent source object, but the operator experience is still only partially organized around it.

If the team stops at the registry baseline:

- operators will still create adapters mostly from the adapter screen
- `source_system` and `hes_code` alignment may drift
- HES-level monitoring and drill-down will remain weaker than adapter-level monitoring
- the UI will reflect the technical execution model more strongly than the upstream source model

This document exists to prevent that drift.

## Current baseline already delivered

The following baseline is already in place:

- `hes_system` table and lineage
- `adapter_instance.hes_system_id`
- `ingest_batch.hes_system_id`
- `hes_read_raw.hes_system_id`
- `hes_event_raw.hes_system_id`
- `landing_lp_em_read_block.hes_system_id`
- HES list screen
- HES detail screen
- adapter screens that show the parent HES

That baseline is necessary but not sufficient for a truly HES-centric operator flow.

## Current remaining gap

Today the operator can:

- register an HES
- inspect an HES
- inspect adapter instances

But the operator cannot yet fully treat the HES as the primary control surface for integration work.

The main remaining gaps are:

- adapter registration is still primarily adapter-first
- HES detail does not yet act as the natural starting point for attaching adapters
- `source_system` still needs stronger alignment with `hes_system.hes_code`
- HES-level operational drill-down is still weaker than adapter-level drill-down
- HES-level event and alert summaries are still mostly derived indirectly

## Core design stance

The project should now adopt the following operating stance:

- `hes_system` is the primary operator-facing source object
- `adapter_instance` is the technical execution unit under one HES
- adapter creation should preferably happen from an HES context
- `source_system` should remain aligned with `hes_system.hes_code`
- HES detail should become the main place to move downward into adapters, runs, batches, and raw data

## Recommended operator flow

The intended flow should become:

1. register or open an HES
2. review HES metadata and current health
3. attach one or more adapters under that HES
4. run, pause, or inspect those adapters
5. inspect recent batches, raw records, and alerts from the HES detail context

This gives operators a stable top-down view:

- HES
- adapter
- run
- batch
- raw
- canonical
- final

## Recommended implementation sequence

### Phase 1. HES-scoped adapter registration

Goal:

- let operators create adapters directly from an HES detail context

Expected scope:

- HES detail screen should expose a clear `Register Adapter` action
- adapter registration page should accept a parent `hes_system`
- when a parent HES is selected, `source_system` should be derived from the HES
- mismatched `source_system` and `hes_code` should be rejected

Why this phase comes first:

- it turns HES from a passive registry into an active operating object
- it reduces drift between HES identity and adapter identity

### Phase 2. HES-scoped adapter visibility

Goal:

- make HES detail the best place to inspect integration runtime state for that source

Expected scope:

- HES detail shows linked adapters with runtime status
- HES detail shows recent ingest batches and counts
- HES detail links cleanly into adapter detail and ingest visibility
- HES list shows enough summary to identify which HES needs attention first

### Phase 3. HES-level operational drill-down

Goal:

- make HES a practical troubleshooting anchor

Expected scope:

- HES detail should link into event/alert history filtered by HES context
- HES detail should link into raw/batch visibility by HES
- future event timeline design should prefer a direct `hes_system_id` path where appropriate

### Phase 4. HES-level runtime and alert roll-up

Goal:

- let operators understand HES health without reading each adapter independently

Expected scope:

- HES summary cards or sections for:
  - linked adapter count
  - enabled adapter count
  - open alerts
  - latest successful activity
- future HES health roll-up should remain derived from adapter/run state, not duplicated manually

## Minimal-stage boundary

The minimal stage should include:

- HES-scoped adapter registration
- HES detail as the parent drill-down page
- `hes_code` and `source_system` alignment
- HES-level summary counts that help operators orient quickly

The minimal stage does not need to include:

- full HES-specific authorization
- HES-specific dashboards separate from the main dashboard
- dedicated HES event pipelines
- advanced HES onboarding workflow or wizard

## Recommended immediate implementation target

The most useful next slice is:

1. HES detail -> `Register Adapter`
2. adapter create flow with optional `hes_system_id`
3. validation that keeps `source_system` aligned with the selected HES
4. regression tests for HES-scoped adapter creation

That slice is small enough to implement safely and large enough to make the HES model feel real.

## Relationship to other documents

- [hes-system-management.md](/home/tprover/2604_sim_mdms_auto/docs/hes-system-management.md)
- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-backlog.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)
