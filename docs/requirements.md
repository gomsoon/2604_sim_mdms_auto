# Requirements

## Purpose

This document defines the development requirements for the `Minimal End-to-End` stage of the MDM system. The purpose of this stage is to establish a trusted data pipeline between HES-originated data and internal canonical measurements before introducing VEE, usage, and billing-oriented capabilities.

## Scope

### In scope for the current stage

- Raw read ingestion from HES or equivalent upstream systems
- Raw event and alarm ingestion
- Storage of source metadata such as `source_system`, `batch_id` or `message_id`, `received_at`, and original payload
- Minimal master data management for `Device`, `ServicePoint`, `MeasuringComponent`, and `InstallationHistory`
- Mapping from raw source data to internal master data
- Canonical measurement creation from mapped raw reads
- Basic duplicate detection
- Exception queue handling for validation and mapping failures
- Operator-facing dashboard, list views, and APIs
- External integration readiness for future HES, database, and API connectivity
- Internationalization readiness for English and Korean user-facing content
- PostgreSQL-based persistence as the default runtime database for the minimal stage
- Alignment of target persistent model names with the agreed backlog naming

### Explicitly out of scope for the current stage

- VEE rule engine and rule administration
- Initial Measurement and Final Measurement separation
- Estimation, editing, and manual approval workflows
- Usage calculation
- Bill determinant generation
- Billing or CIS export
- Production-grade batch orchestration
- Full RBAC and advanced audit tooling

## Functional requirements

### Raw data ingestion

- The system must accept raw read payloads through an API or batch-oriented mechanism.
- The system must accept raw event and alarm payloads through an API or batch-oriented mechanism.
- Raw payloads must be preserved without destructive overwrite.
- Raw payloads must retain lineage to downstream canonical records or exceptions.

### Master data and mapping

- The system must maintain minimal master data needed to map incoming HES data to internal business entities.
- Mapping failures must not be dropped silently.
- Mapping failures must be recorded as explicit operational exceptions.

### Canonicalization

- Canonical measurements must only be created after minimum validation and mapping checks pass.
- Canonical measurements must retain a direct reference to the originating raw read.
- Duplicate raw reads must be identified and marked without deleting the duplicate source record.

### Operator visibility

- Operators must be able to view raw reads, raw events, canonicalization status, and exceptions.
- Operators must be able to trace records from raw source payload to canonical output or exception state.

## Cross-cutting requirements

### Structural analysis before feature work

- Before adding a new feature, the team must first analyze the existing source code structure.
- The structural analysis must review module responsibilities, coupling, duplication, layering, naming clarity, and future extensibility.
- If the existing structure is not adequate for the new feature, refactoring must be performed first.
- Feature implementation must not be added directly on top of an unsuitable structure simply for speed.

### External integration readiness

- Even in the minimal stage, the design must assume integration with external systems such as HES, external APIs, and external databases.
- Integration points must be isolated so that source-specific or protocol-specific logic can be adapted without rewriting core business logic.
- PostgreSQL must be treated as the primary database baseline, not a later migration target.
- Local convenience choices must not drive schema or naming decisions away from the PostgreSQL-oriented target architecture.
- API contracts and persistence structures must consider idempotency, delayed delivery, duplicates, and partial upstream data quality.

### Persistent model naming

- The target persistent naming should follow the agreed backlog terminology from the reference PDF.
- Minimal-stage persistence should use names such as `ingest_batch`, `hes_read_raw`, `hes_event_raw`, `canonical_measurement`, and `ingest_error_log`.
- If existing code uses interim names, structural refactoring should align those names before substantial feature expansion continues.

### Internationalization

- Every operator-facing feature must support at least English and Korean.
- User-facing labels, messages, and validation text must be designed for localization rather than hard-coded in one language only.
- Data models and APIs must allow locale-aware rendering where appropriate.

### Encoding and Korean text integrity

- All source code and documentation files must be created and maintained in UTF-8 encoding.
- Before reflecting a change, the team must verify that Korean text is not corrupted, mojibake-affected, or partially broken.
- Encoding-related review must be treated as part of normal quality control, especially for user-facing text, documentation, sample payloads, and localization resources.

## Non-functional requirements

### Traceability

- The system must support lineage from raw source data to canonical output and exception state.

### Maintainability

- The codebase must remain modular enough to support a later transition from Minimal to MVP and Product stages without large-scale rewrite.

### Testability

- Every code change must remain testable at unit and regression levels.
- Requirements should be written in a way that allows associated test cases to be derived clearly.

## Definition of done for requirement compliance

A feature in the minimal stage is only considered complete if the following are true:

- The implemented behavior is within current phase scope.
- The source structure was reviewed before implementation.
- Necessary refactoring was completed before the feature code was introduced.
- Tests were added or updated.
- Regression testing was performed.
- English and Korean support were considered for user-facing behavior.
- UTF-8 encoding and Korean text integrity were reviewed for changed files.
- External integration implications were reviewed.
- PostgreSQL and agreed persistent naming implications were reviewed.
