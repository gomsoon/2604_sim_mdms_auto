# Layered Architecture Baseline

## Purpose

This document provides the top-level architectural view of the MDM system so that future design and implementation decisions stay aligned around a stable layered model.

This document is intentionally broader and more central than the other architecture notes.

## Why this document matters

The system is easier to evolve safely when the team agrees on:

- what the major layers are
- what responsibility belongs to each layer
- which layers are expected to change more often
- which layers should remain stable and central over time

For this project, the most important long-term center of gravity is:

- the data layer
- the processing layer

The integration and frontend layers are also important, but they should be able to evolve without forcing repeated redesign of the core data and processing model.

## Top-level layer model

The MDM system should be understood as four major layers.

### 1. Integration layer

Purpose:

- connect with HES and other external systems
- receive source data through push, poll, file, API, or database integration
- absorb source-specific differences before they destabilize the internal model

Typical responsibilities:

- HES registry and source identity management
- HES connectors
- adapter runtime lifecycle control
- adapter health and heartbeat tracking
- source-specific parsing
- adapter profile normalization before common raw entry
- optional landing-table loading
- source authentication and connectivity handling
- upstream delivery trace capture

Key rule:

This layer should be flexible, source-aware, and replaceable.

Vendor-specific behavior belongs here, or at the boundary between this layer and the data layer.

### 2. Data layer

Purpose:

- preserve data at each meaningful state
- maintain lineage across those states
- provide a stable persistent contract for the rest of the system

Typical responsibilities:

- landing tables when needed
- common raw tables
- canonical or initial structures
- later well-formed, final, usage, and billing-ready structures
- audit and trace persistence

Key rule:

This is one of the two central layers of the system and should change slowly and deliberately.

### 3. Processing layer

Purpose:

- move data safely from one state to the next
- apply mapping, validation, duplicate handling, VEE, estimation, correction, and reprocessing logic
- record what happened, when, and why

Typical responsibilities:

- batch or work-unit selection
- state transition control
- orchestration status tracking
- exception registration
- reprocess requests
- audit-friendly execution history

Key rule:

This is the other central layer of the system and should be treated as part of the long-term system core.

### 4. Presentation layer

Purpose:

- expose the system to operators, administrators, and supporting tools
- provide inspection, maintenance, filtering, and workflow support

Typical responsibilities:

- web UI
- operator dashboards
- admin screens
- external-facing query APIs
- localized messages and labels

Key rule:

This layer should depend on the data and processing model, not define it.

## Relationship between the layers

The intended directional flow is:

- integration receives or fetches source data
- data layer preserves source and normalized states
- processing layer advances records between those states
- presentation layer shows current state and allows controlled operator actions

The layers should not collapse into each other.

Examples of what to avoid:

- UI handlers embedding business-stage transitions directly
- vendor-specific parsing leaking into canonical logic
- processing rules depending on template wording
- presentation concerns redefining data semantics

## Recommended dependency direction

Preferred dependency direction:

- presentation depends on processing and data
- processing depends on data and integration boundaries
- integration depends on source contracts and data entry contracts
- data depends only on stable persistence and domain semantics

The data layer should not depend on the frontend.

The processing layer should not depend on specific UI pages.

## What should change slowly vs quickly

### Layers expected to change more frequently

- integration layer
- presentation layer

Why:

- HES connections can vary by vendor and environment
- UI requirements evolve as operators learn what they need
- localization and workflow ergonomics will continue improving

### Layers expected to change carefully and less often

- data layer
- processing layer

Why:

- these layers define the real system meaning
- repeated redesign here causes expensive ripple effects
- downstream billing, audit, and reprocessing all depend on their stability

## Core architectural stance for this project

The system should be designed so that:

- new HES vendors can be added without redesigning canonical and later layers
- UI screens can evolve without redefining data semantics
- new processing steps can be added without breaking lineage
- reprocessing can happen without destructive rewrites of source truth

## Layer-by-layer design goals

### Integration layer goals

- flexible source intake
- clear parent HES registration above technical runtime adapters
- isolated vendor-specific logic
- strong traceability to upstream deliveries
- optional landing layer support when needed

### Data layer goals

- immutable source preservation where appropriate
- explicit state boundaries between raw, canonical, and later stages
- clear lineage from source to downstream business state
- minimal vendor-specific branching after common raw

### Processing layer goals

- explicit work units
- idempotent execution where possible
- visible statuses such as `waiting`, `processing`, `completed`, and `failed`
- audit-friendly stage progression
- reprocess support as a first-class concept

### Presentation layer goals

- operator clarity
- batch and meter traceability
- bilingual support
- minimal direct coupling to business rules

## Recommended current interpretation for this project

At the present stage, the current system can be read like this:

- integration layer: ingest APIs and lightweight adapter profiles now, with future HES registry management and runtime HES adapters later
- data layer: `ingest_batch`, `hes_read_raw`, `hes_event_raw`, `canonical_measurement`, `ingest_error_log`, and master data tables
- processing layer: raw ingest validation, duplicate detection, mapping, canonical conversion, and dashboard status derivation
- presentation layer: Flask blueprints, Jinja screens, localized UI, and query endpoints

This is already a layered system in shape, even if some layers are still minimal.

## Main long-term risk to avoid

The main architectural risk is not that the system lacks features.

The main risk is that feature work gradually mixes the layers until:

- data semantics become tied to one UI flow
- processing logic becomes hard-coded in ad hoc routes
- source-specific assumptions leak upward
- reprocessing and audit become difficult later

That is why the layered view should be treated as a control document, not just a description.

## Relationship to other documents

- [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
- [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [core-stability-goals.md](/home/tprover/2604_sim_mdms_auto/docs/core-stability-goals.md)
