# Gap Analysis

## Purpose

This document compares the current scaffold in the repository with the agreed target baseline for the minimal stage.

## Baseline comparison summary

### Agreed target baseline

- PostgreSQL is the primary database from the minimal stage onward
- Persistent naming follows the backlog PDF vocabulary
- Minimal backlog tracks `M1` through `M6`
- Structural refactoring is allowed before further feature expansion

### Current scaffold state

- The current app still defaults to SQLite in configuration
- The current SQLAlchemy model names use interim application-oriented names
- The current scaffold combines ingest-stage failures and broader processing issues under a general exception concept
- The current scaffold proves the basic raw-to-canonical flow but is not fully vocabulary-aligned with the backlog baseline

## Detailed gaps

### Gap 1. Database baseline

#### Current

- `app/config.py` still defaults `DATABASE_URL` to SQLite
- Existing setup instructions assume a SQLite-first local flow
- Project dependencies do not yet include a PostgreSQL driver
- Migration workflow is not yet defined in the repository

#### Target

- PostgreSQL should be the default runtime assumption for minimal development
- Local setup should explicitly guide PostgreSQL usage

#### Impact

- If left unchanged, future implementation may drift toward SQLite-friendly shortcuts
- This would increase later refactoring cost for partitioning, indexing, and operational realism

#### Required action

- Refactor configuration defaults and setup flow toward PostgreSQL
- Add PostgreSQL driver dependency
- Define migration tooling and workflow
- Add PostgreSQL development run instructions and environment examples

### Gap 2. Persistent model naming

#### Current

- `IngestionBatch`
- `RawRead`
- `RawEvent`
- `ProcessingException`

#### Target

- `ingest_batch`
- `hes_read_raw`
- `hes_event_raw`
- `ingest_error_log`

#### Impact

- Vocabulary drift makes backlog tracking, schema discussion, and implementation planning harder
- Feature work risks building on names that will later need renaming

#### Required action

- Refactor persistence naming to match the agreed backlog terminology
- Update API, services, templates, documentation, and tests consistently

### Gap 3. Ingest-stage error semantics

#### Current

- The current scaffold uses a general exception mechanism for multiple failure types

#### Target

- Minimal ingest failures should map clearly to an ingest-oriented error construct such as `ingest_error_log`
- Broader VEE and operational exception structures should remain available for later phases

#### Impact

- Mixed semantics can blur the difference between ingest validation failures and later operational exceptions

#### Required action

- Revisit the error model while aligning names and minimal-stage responsibilities

### Gap 4. Backlog traceability

#### Current

- The repository has engineering baseline documents and a minimal plan
- The staged product backlog from the PDF was not yet captured as first-class repo documentation

#### Target

- The repository should include a backlog baseline and a minimal-only backlog view

#### Impact

- Without repo-native backlog documents, design discussions and implementation sequence can drift from the agreed roadmap

#### Required action

- Maintain `backlog.md` and `minimal-backlog.md` as working references

## Recommended order of structural alignment

1. Confirm PostgreSQL connection and local development workflow
2. Refactor configuration and setup docs toward PostgreSQL
3. Rename persistent vocabulary to the agreed backlog baseline
4. Revisit error-model boundaries for ingest failures
5. Continue minimal backlog implementation only after the structural alignment is complete

## Notes

- The current scaffold is still useful because it already demonstrates basic layering and a minimal flow
- The next step is not to discard it, but to refactor it into alignment before further feature growth
