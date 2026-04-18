# Persistence Renaming Plan

## Purpose

This document defines the structural renaming plan that aligns the current scaffold with the agreed backlog vocabulary.

## Why this refactor comes before more features

- The current scaffold already proves a useful minimal flow
- The agreed backlog vocabulary is now stable enough to serve as the naming baseline
- Continuing feature work on interim names would increase later migration cost

For that reason, persistence naming alignment should be treated as a prerequisite refactor.

## Naming principles

- Database tables use `snake_case`
- ORM class names use `PascalCase`
- Persistent names should match the backlog terminology
- User-facing labels do not need to mirror physical table names exactly
- Ingest-stage error naming should be separated from later VEE and operational exception naming

## Target renaming map

| Current ORM class | Current table | Target ORM class | Target table |
| --- | --- | --- | --- |
| `IngestionBatch` | `ingestion_batch` | `IngestBatch` | `ingest_batch` |
| `RawRead` | `raw_read` | `HesReadRaw` | `hes_read_raw` |
| `RawEvent` | `raw_event` | `HesEventRaw` | `hes_event_raw` |
| `ProcessingException` | `processing_exception` | `IngestErrorLog` | `ingest_error_log` |
| `CanonicalMeasurement` | `canonical_measurement` | `CanonicalMeasurement` | `canonical_measurement` |
| `Device` | `device` | `Device` | `device` |
| `ServicePoint` | `service_point` | `ServicePoint` | `service_point` |
| `MeasuringComponent` | `measuring_component` | `MeasuringComponent` | `measuring_component` |
| `InstallationHistory` | `installation_history` | `InstallationHistory` | `installation_history` |

## Functional interpretation of the error-model rename

The most sensitive rename is the current general exception model.

### Current behavior

- A single `ProcessingException` concept is handling multiple minimal-stage failure types

### Target behavior

- Ingest validation and ingest persistence failures move into `IngestErrorLog`
- Later business-phase exceptions such as VEE exceptions should be modeled separately when Phase 2 work begins

This keeps minimal-stage semantics clearer and avoids premature overloading of a generic exception table.

## Refactor sequence

### Step 1. Prepare infrastructure

- Add PostgreSQL driver dependency
- Define migration workflow
- Freeze current behavior with tests before renaming

### Step 2. Rename ORM classes and tables

- Rename ORM classes
- Update `__tablename__`
- Update foreign keys and relationship names

### Step 3. Align service and API vocabulary

- Update ingestion services
- Update blueprint imports and query code
- Update template references and dashboard labels where needed

### Step 4. Align documentation and test assets

- Update README and docs references
- Update test names, fixtures, and assertions
- Update any sample payload references that mention old names indirectly

### Step 5. Re-run regression coverage

- Run unit tests
- Run integration and API tests
- Re-check ingest and canonicalization flows
- Re-check English and Korean user-facing text where touched

## File impact expectations

The rename is expected to affect at least:

- `app/models.py`
- `app/services/ingestion.py`
- `app/services/seeds.py`
- `app/blueprints/api.py`
- `app/blueprints/web.py`
- templates and dashboard wording
- setup and migration-related files
- tests and fixtures
- project documentation

## Risk notes

- Renaming without a migration strategy may orphan existing local data
- Renaming without tests may break relationships silently
- Mixing naming refactor and new features in one change would increase regression risk

## Acceptance criteria

The renaming refactor is complete only when:

- Persistent names match the agreed backlog baseline
- Ingest-stage error semantics are clarified
- Documentation reflects the new names
- Regression testing passes
- No stale references to interim names remain in active code paths

