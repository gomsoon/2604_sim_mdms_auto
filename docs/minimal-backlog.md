# Minimal Backlog

## Purpose

This document narrows the broader backlog to the agreed `Minimal End-to-End` delivery target.

## Delivery objective

The minimal stage should prove the full path from HES-originated raw data to internal canonical measurement visibility on a PostgreSQL-backed service.

## Minimal epics

### M1. Project skeleton

#### Intent

Provide the base service structure required for all later MDM features.

#### Tasks

- Build the repository and backend skeleton
- Separate runtime configuration for `dev`, `test`, and `prod`
- Establish PostgreSQL connectivity
- Add common logging
- Add health check API

#### Acceptance criteria

- The application runs successfully
- `/health` returns a healthy response
- PostgreSQL connectivity can be confirmed through application logs

### M2. Core MDM data model

#### Intent

Define the minimum persistent shape required to ingest and trace HES data.

#### Tasks

- Create DDL for the minimal schema
- Create `device`
- Create `service_point`
- Create `measuring_component`
- Create `installation_history`
- Create `ingest_batch`
- Create `hes_read_raw`
- Create `hes_event_raw`
- Create `canonical_measurement`
- Create `ingest_error_log`
- Add baseline indexes

#### Acceptance criteria

- The minimum schema exists in PostgreSQL
- Raw data and canonical data are stored separately
- Source-to-canonical lineage can be traced

### M3. HES raw ingestion

#### Intent

Accept raw HES reads and events into the MDM system without losing source fidelity.

#### Tasks

- Define a first HES raw input contract
- Implement ingest API or file loader
- Persist `ingest_batch`
- Persist `hes_read_raw`
- Persist `hes_event_raw`
- Validate required fields
- Persist ingest failures to `ingest_error_log`

#### Acceptance criteria

- Sample HES raw reads can be ingested
- Sample HES events can be ingested
- `batch_id` or `message_id` is captured
- Missing required fields are recorded in `ingest_error_log`
- Original payload is preserved

### M4. Minimal master data management

#### Intent

Map incoming HES data to the correct device, service point, and channel context.

#### Tasks

- Add APIs or services for `device`
- Add APIs or services for `service_point`
- Add APIs or services for `measuring_component`
- Add APIs or services for `installation_history`
- Define meter identifier mapping rules
- Implement unresolved mapping handling

#### Acceptance criteria

- Sample meters can be mapped to device and service point records
- Installation context can be determined for a point in time
- Mapping failures are retained in unresolved form

### M5. Canonical measurement conversion

#### Intent

Convert raw HES measurements into the standard internal measurement representation.

#### Tasks

- Build raw-to-canonical conversion logic
- Normalize timestamps
- Persist UOM, interval size, and source metadata
- Store lineage back to `hes_read_raw`
- Record conversion failures

#### Acceptance criteria

- At least one raw measurement can be converted into `canonical_measurement`
- Canonical records include device, measuring component, and measurement timestamp
- Conversion failures are visible through logs or persistent error records

### M6. Visibility and query APIs

#### Intent

Allow operators to inspect ingest and conversion outcomes.

#### Tasks

- Query `ingest_batch`
- Query raw reads
- Query raw events
- Query canonical measurements
- Query operational events and open alerts
- Add batch, meter, and date filters

#### Acceptance criteria

- Operators can inspect ingest counts and failures by batch
- Operators can query raw and canonical data by meter
- Lineage can be verified through API responses or UI
- Recent important events and open alerts are visible without log inspection

## Minimal-stage structural prerequisites

Before feature development continues, the current scaffold should be structurally aligned to this backlog baseline.

- Switch the primary runtime database expectation from SQLite-oriented defaults to PostgreSQL
- Align persistent naming with `ingest_batch`, `hes_read_raw`, `hes_event_raw`, and `ingest_error_log`
- Separate ingest-stage error handling from broader exception management where needed

## Suggested next documentation focus

- [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)
- [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
- [persistence-renaming-plan.md](/home/tprover/2604_sim_mdms_auto/docs/persistence-renaming-plan.md)
- i18n strategy for English and Korean operator surfaces
