# Minimal E2E Plan

This document is the stage-specific implementation plan for the minimal delivery. Broader engineering rules are defined in the following companion documents:

- [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)
- [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
- [development-guide.md](/home/tprover/2604_sim_mdms_auto/docs/development-guide.md)
- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)

## Why start here

The first delivery target is not a full MDM product. It is the smallest believable operator flow that proves the following:

1. HES raw data can be accepted without loss.
2. Raw payloads can be mapped to internal master data.
3. Canonical measurements can be created from the mapped records.
4. Failures are visible in an exception queue instead of disappearing inside the pipeline.

That sequencing matches the earlier analysis: first build a trusted data pipeline, then add VEE and usage, then productize.

## Stack decision

### Chosen stack

- Python
- Flask
- SQLAlchemy
- Bootstrap

### Why this fits the minimal stage

- Flask keeps the application shape simple while the domain model is still moving.
- Jinja plus Bootstrap is enough for internal operator screens without frontend overhead.
- SQLAlchemy lets us move quickly while still targeting PostgreSQL as the agreed primary database.
- The team can get to a working raw-to-canonical flow quickly before introducing task queues, partitioning, and advanced rule engines.

## Phase boundary

This scaffold is intentionally limited to the `Minimal End-to-End Version`.

### In scope now

- Raw read ingest API
- Raw event ingest API
- Source metadata capture: `source_system`, `batch_id`, `received_at`, raw payload
- Minimal master data: `Device`, `ServicePoint`, `MeasuringComponent`, `InstallationHistory`
- Raw storage
- Canonical measurement creation
- Duplicate detection
- Mapping failure handling
- Exception queue visibility
- Operator dashboard and basic list screens

### Explicitly out of scope for this phase

- VEE rule engine
- Initial vs Final Measurement separation
- Estimation and editing
- Usage calculation
- Bill determinants
- Billing or CIS export
- Advanced audit and role model
- Batch orchestration and worker scaling

## Data flow

```mermaid
flowchart LR
    A["HES Payload"] --> B["Raw Ingest API"]
    B --> C["Raw Read / Raw Event Storage"]
    C --> D["Duplicate Check"]
    D --> E["Master Data Mapping"]
    E -->|success| F["Canonical Measurement"]
    E -->|failure| G["Exception Queue"]
    D -->|duplicate| G
```

## Current data model

- `ingest_batch`: stores source metadata and original request payload.
- `hes_read_raw`: immutable incoming read record with canonical processing status.
- `hes_event_raw`: immutable event and alarm record.
- `service_point`: minimal business location anchor.
- `device`: external meter identity from source systems.
- `measuring_component`: channel-level mapping target for canonicalization.
- `installation_history`: placeholder for device movement and replacement history.
- `canonical_measurement`: mapped output for downstream business logic.
- `ingest_error_log`: queue for validation and ingest-stage failures.

## Target persistent model names

The minimal stage should align with the agreed backlog naming baseline.

- `device`
- `service_point`
- `measuring_component`
- `installation_history`
- `ingest_batch`
- `hes_read_raw`
- `hes_event_raw`
- `canonical_measurement`
- `ingest_error_log`

## Near-term implementation order

1. Lock the raw ingest contract with real HES sample payloads.
2. Refactor the existing scaffold from SQLite-oriented defaults to PostgreSQL-oriented defaults.
3. Refactor current persistent naming to align with the agreed backlog model names.
4. Expand the master-data UI so operators can load and correct mappings.
5. Introduce background workers for non-trivial ingest volume.
6. Add `Initial Measurement` and VEE status model.

## Architectural notes

- Raw records must be preserved even when invalid.
- Canonical records are created only after duplicate and mapping checks.
- Exceptions are treated as first-class operational data.
- The codebase already separates web, API, and service logic so background processing can be introduced without rewriting the Flask surface.
- The current scaffold still contains interim naming and SQLite-oriented defaults, so structural alignment to PostgreSQL and backlog naming is a planned prerequisite before broader feature growth.
