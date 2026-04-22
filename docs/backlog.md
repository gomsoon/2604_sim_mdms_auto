# Product Backlog

## Purpose

This document captures the staged backlog derived from the reference PDF backlog input. It is the working product backlog baseline for the repository.

## Phase 1. Minimal End-to-End Version

### M1. Project skeleton

- Repository structure
- Backend application skeleton
- Environment separation for `dev`, `test`, and `prod`
- PostgreSQL connectivity
- Common logging
- Health check API

### M2. Core MDM data model

- DDL for minimal core entities
- `device`
- `service_point`
- `measuring_component`
- `installation_history`
- `ingest_batch`
- `hes_read_raw`
- `hes_event_raw`
- `canonical_measurement`
- `ingest_error_log`
- Baseline indexes
- Shared column conventions such as `created_at`, `updated_at`, and `source_system`

### M3. HES raw read and event ingestion

- HES raw read input contract
- Batch ingest API or file loader
- `ingest_batch` persistence
- `hes_read_raw` persistence
- Required-field validation
- Ingest-stage error persistence
- HES raw event contract
- `hes_event_raw` persistence
- Event and receive timestamp separation
- Event code and severity rules

### M4. Minimal master data management

- `device` API
- `service_point` API
- `measuring_component` API
- `installation_history` API
- Meter identifier mapping rules
- HES meter ID to device mapping

### M5. Canonical measurement conversion

- `canonical_measurement` conversion logic
- Raw-to-canonical field mapping
- Timestamp normalization
- UOM, interval size, and source metadata
- Raw lineage persistence
- Conversion failure handling

### M6. Raw and canonical data visibility

- `ingest_batch` query API
- Raw read query API
- Raw event query API
- Canonical measurement query API
- Operational event and alert timeline
- Filters such as `batch_id`, `meter_id`, and date range

## Phase 2. MVP Version

### V1. Initial and final measurement structure

- `initial_measurement`
- `final_measurement`
- Versioning
- Validation and finalization statuses

### V2. Basic VEE engine

- Rule baseline
- Execution logging
- Required-field validation
- UOM validation
- Multiplier validation
- Interval size validation
- Duplicate check
- Negative check
- Zero check
- High and low check
- Missing interval detection

### V3. Basic estimation

- Linear interpolation
- Previous-value-based estimation
- Estimation audit
- Final measurement update flow

### V4. Exception management

- VEE exception persistence
- Exception query API
- Exception status transitions

### V5. Manual edits and audit

- Manual edit API
- Reason codes
- Approver and editor identity tracking
- Manual edit audit
- Final measurement regeneration

### V6. Usage calculation

- `usage_transaction`
- Daily usage
- Monthly usage
- Service-point usage API

### V7. Event-linked decisioning

- Event lookup service
- Outage and tamper context matching
- Event-aware VEE extension
- Event-linked exceptions

## Phase 3. Product Version

### P1. Advanced VEE rule framework

- Rule groups
- Sequencing
- Branching
- Effectivity
- Rule targeting by service type, region, or device type

### P2. TOU and bill determinant generation

- TOU model
- `bill_determinant`
- On-peak and off-peak usage
- Maximum demand
- Average power factor
- Billing cycle alignment

### P3. Billing integration

- Billing export queue
- Export payload contract
- Batch or API export
- Re-send and recalculation handling
- Export status management

### P4. CIS integration

- Customer and contract master extension
- CIS sync interface
- Usage and event query APIs
- Customer-facing summary APIs

### P5. Aggregation and reporting

- Aggregation grouping
- Regional and tariff-based aggregation
- Daily and monthly reporting
- CSV export

### P6. Security and authorization

- User, role, and permission models
- RBAC middleware
- Audit expansion
- Sensitive-action isolation

### P7. Operability and reprocessing

- Re-ingest
- Re-map
- Re-VEE
- Re-finalize
- Reprocessing selection UI and API

### P8. Performance and partitioning

- Monthly partitioning for high-volume tables
- Index tuning
- Performance testing
- Vacuum and analyze operational guidance

## Common technical backlog

### C1. Test system

- Unit test framework
- Integration test environment
- Sample HES fixtures
- VEE rule test cases
- Usage golden datasets

### C2. DevOps and deployment

- Dockerfile
- Docker Compose
- Migration tool
- CI pipeline
- Environment variable templates

### C3. Observability

- Structured logging
- Batch metrics
- Ingest, VEE, and export monitoring endpoints
- Alerting criteria

## Cross-cutting follow-up backlog

These items are not blockers for the current minimal baseline, but they should remain visible because they affect long-term scalability and downstream correctness.

### X1. Replay uniqueness redesign for partitioned raw

- Review how `source_system + source_record_key` exact replay guarantees should be preserved once `hes_read_raw` is partitioned
- Likely direction: small replay registry table or equivalent support structure

### X2. Finalization uniqueness redesign for partitioned final

- Review how the one-final-per-canonical guarantee should be preserved once `final_measurement` is partitioned
- Keep the canonical-to-final business guarantee explicit

### X3. Numeric precision hardening

- Review replacement of `Float` with `Numeric/Decimal` for:
  - `hes_read_raw.reading_value`
  - `canonical_measurement.value`
  - `final_measurement.value`
- Prioritize before billing-facing logic grows

### X4. Final measurement revision model

- Review whether the final layer needs:
  - supersession
  - revision lineage
  - re-finalization support
  - correction handling

### X5. Common raw naming neutrality review

- Revisit whether `hes_read_raw` and `hes_event_raw` should eventually evolve toward broader upstream-neutral naming
- Do not block current progress on this review

## Recommended execution waves

### Wave 1

- M1
- M2
- M3
- M4
- M5
- M6

### Wave 2

- V1
- V2
- V3
- V4
- V5

### Wave 3

- V6
- V7
- Basic `bill_determinant`

### Wave 4

- P1
- P3
- P4
- P5

### Wave 5

- P6
- P7
- P8
- C1
- C2
- C3
