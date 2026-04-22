# HES System Management

## Purpose

This document defines the operator-facing `hes_system` concept that sits above runtime adapters.

The project already has runtime adapter definitions, instances, runs, and watermarks. What is still missing is the parent operational object that represents one registered upstream HES from an administrator's point of view.

## Why this document matters

If the project treats `adapter_instance` as both:

- the upstream HES itself
- and the technical execution unit used to connect to that HES

the model will become confusing as soon as one HES requires more than one adapter.

Typical examples are:

- one polling adapter for raw reads
- one receive adapter for events
- one backfill-oriented adapter for controlled replay

Those are different runtime units, but they may still belong to one operator-managed HES registration.

## Core distinction

### HES system

An `hes_system` is the persistent operator-managed representation of one upstream HES.

Typical responsibilities:

- carry a stable unique source identity
- hold operator-facing registration and descriptive information
- define the parent source object above one or more runtime adapters
- provide a stable lineage reference for batches and raw records
- anchor later HES-side reference synchronization such as source meter metadata

### Runtime adapter

A runtime adapter remains the technical execution unit that connects to an HES and moves data into the MDM.

Typical responsibilities:

- polling or receive execution
- watermark handling
- run history
- pause, resume, and run-once control

## Recommended hierarchy

The recommended relationship is:

- one `hes_system`
- many `adapter_instance`

Example:

- `hes_system`: `aimir_overseas_prod`
- adapter instance 1: read polling adapter
- adapter instance 2: event receive adapter
- adapter instance 3: controlled backfill adapter

This keeps the parent source identity stable even if runtime connection methods expand later.

## Recommended persistence baseline

### 1. `hes_system`

Recommended purpose:

- represent one registered upstream HES as an operator-managed source object

Recommended columns:

- `id`
- `hes_code`
- `display_name`
- `vendor_name`
- `source_family`
- `default_delivery_mode`
- `status`
- `timezone_name`
- `description`
- `connection_config_masked`
- `created_at`
- `updated_at`

Recommended rules:

- `hes_code` should be unique
- `hes_code` should be stable and machine-readable
- `status` can start with a minimal vocabulary such as `active` and `inactive`

### 2. Extend `adapter_instance`

Recommended addition:

- `hes_system_id` FK referencing `hes_system.id`

Why:

- it makes the parent HES explicit
- it avoids treating runtime adapters as the primary source identity
- it allows one HES to own multiple runtime adapters cleanly

### 3. Extend batch and raw lineage

Recommended additions:

- `ingest_batch.hes_system_id`
- `hes_read_raw.hes_system_id`
- `hes_event_raw.hes_system_id`
- when source-specific landing is used, `landing_lp_em_read_block.hes_system_id`

Why:

- `adapter_instance_id` gives runtime lineage
- `adapter_run_id` gives execution lineage
- `hes_system_id` gives stable upstream source lineage

All three are useful and should not be treated as duplicates.

## Relationship to HES meter reference data

An upstream HES is usually not only a producer of raw reads and events.

In practice it may also hold source-side meter reference data such as:

- source meter identifiers
- interval configuration
- device model or meter type indicators
- source status flags
- source-to-channel relationships

That means HES registration should be understood as covering:

- raw read and event connectivity
- and, later, HES-side reference-data synchronization where needed

However, the project should avoid treating the vendor `METER` table or its equivalent as the direct canonical master model of the MDM.

Recommended rule:

- preserve or ingest HES-specific meter reference data when it is operationally useful
- but normalize only the needed subset into the MDM canonical master context

## Canonical meter-related master context in MDM

The MDM still needs its own stable meter-related master context even if downstream billing or CIS systems exist.

Why:

- raw reads cannot be mapped to canonical measurements without stable device and channel identity
- installation windows and device movement matter for historical correctness
- reprocessing and audit need a persistent internal mapping target
- downstream billing-ready outputs should not depend on vendor-specific HES tables directly

In the current project, that canonical meter-related master context is represented by:

- `service_point`
- `device`
- `measuring_component`
- `installation_history`

These should continue to be treated as MDM-owned canonical master structures, not as a direct mirror of one HES vendor table.

## Recommended long-term split

The recommended long-term split is:

- `hes_system` and adapter layers manage source connectivity and HES-side reference acquisition
- source-specific HES meter reference can be preserved in a source-reference or landing-oriented layer
- MDM canonical master tables remain the normalized internal source of truth for mapping and processing

This split becomes more important as more HES vendors are added.

## Relationship with `source_system`

The project already uses `source_system` in contracts, persistence, and runtime logic.

Recommended transition rule:

- keep `source_system` for now
- add `hes_system_id`
- keep `source_system` aligned with `hes_system.hes_code`

This avoids a risky all-at-once rename while still moving toward a cleaner model.

## Recommended minimal operator UI

The operator-facing flow should become:

1. register an HES system
2. review or edit HES metadata
3. attach one or more runtime adapters to that HES
4. manage adapter status and runs under the HES
5. inspect raw, batch, event, and alert lineage by HES and adapter

Recommended first screens:

- HES system list
- HES system detail
- adapter list filtered by HES
- recent runs and alerts for one HES

## Current status after the registry baseline

The project now already has:

- `hes_system` persistence
- `hes_system_id` lineage in adapter, batch, landing, and raw tables
- HES list and detail screens
- adapter screens that show the parent HES

That means the original registry baseline is no longer a future-only design target.

What remains is to make the operator workflow itself more strongly HES-centric.

The next focus should therefore shift from:

- "introduce the HES object"

to:

- "make HES the primary operator control surface above adapters"

Recommended next document:

- [hes-centric-operations-plan.md](/home/tprover/2604_sim_mdms_auto/docs/hes-centric-operations-plan.md)

## Current implementation gap

Today the project already has:

- runtime adapter persistence
- runtime adapter UI
- adapter run and watermark lineage

But it does not yet have:

- a parent `hes_system` object
- HES registration or detail screens
- `hes_system_id` lineage in batch or raw persistence

That means current adapter objects are still doing double duty as both:

- operational source identity
- technical runtime execution unit

The recommended next structural step is to separate those concerns.

## Recommended implementation sequence

1. add `hes_system` persistence
2. add `adapter_instance.hes_system_id`
3. add `hes_system_id` to `ingest_batch`, `hes_read_raw`, `hes_event_raw`, and source-specific landing where needed
4. add HES list and detail screens
5. update adapter screens to show the parent HES clearly

## Relationship to other documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
- [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
- [adapter-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-backlog.md)
- [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)
