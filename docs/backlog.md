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
- HES meter reference review and minimal sync strategy
- canonical meter-related master governance in MDM
- minimal `hes_meter_reference` persistence baseline
- AIMIR `METER` subset mapping for source reference
- operator comparison between HES meter reference and MDM canonical master

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
- explicit separation between `canonical_measurement`, `initial_measurement`, and post-VEE `final_measurement`
- review whether current minimal finalization should be treated as temporary until the VEE boundary is introduced

### V2. Basic VEE engine

- Rule baseline
- Execution logging
- `vee_execution_log`
- `vee_exception`
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
- usage-local timezone windowing
- usage quality summary and missing-interval visibility
- explicit distinction between `usage_transaction` and later billing-ready determinant outputs

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
- `bill_determinant` persistence baseline
- `billing_cycle_consumption_total` as the first determinant candidate
- On-peak and off-peak usage
- Maximum demand
- Average power factor
- Billing cycle alignment
- determinant revision and supersession lineage

### P3. Billing integration

- billing-lite boundary definition for small-scale deployment and end-to-end testing
- minimal billing context baseline
- tariff assignment baseline
- simple bill charge persistence and calculation
- optional invoice summary baseline
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
- preserve a clean replacement path between optional `billing-lite` and later CIS-owned flows

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
- queue-backed bulk `re-VEE` by `hes_system`, `ingest_batch`, and bounded `date_range`
- replay request progress and item-level failure visibility
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
- Near-term policy: do not block the first `hes_read_raw` partition rollout on this item, but keep it visible as the next hardening step if replay and idempotency remain application-managed at first

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

- Define the first `current + history` model for `final_measurement`
- Review whether the final layer needs:
  - supersession
  - revision lineage
  - re-finalization support
  - correction handling
- Prefer `initial_measurement_id` as the business lineage anchor
- Keep `usage_transaction` dependent only on the current authoritative final rows
- Align later partitioning work with the revision model rather than designing it in isolation

### X5. Common raw naming neutrality review

- Revisit whether `hes_read_raw` and `hes_event_raw` should eventually evolve toward broader upstream-neutral naming
- Do not block current progress on this review

### X6. Partition-compatible raw identity and downstream FK review

- Continue reviewing how partitioned `hes_read_raw` identity should interact with:
  - `canonical_measurement`
  - exception lineage
  - reprocessing lineage

### X7. Processing-core boundary clarification

- Introduce a clear structural boundary between:
  - `canonical_measurement`
  - `initial_measurement`
  - `vee_execution_log`
  - `vee_exception`
  - `final_measurement`
  - `usage_transaction`
- Keep the first usage layer intentionally simpler than later billing-ready determinant generation

- Review how `hes_read_raw` row identity should remain referenceable once the table is partitioned by `measured_at`
- Review downstream references such as canonical, error, reprocess, and duplicate lineage so the first raw partition rollout is structurally safe
- Include `DEFAULT` partition behavior for null `measured_at` rows and the later row-movement path when `measured_at` becomes known

### X7. HES meter reference and canonical master split

- Review which HES-side meter attributes should be synchronized as source reference data
- Keep vendor `METER` tables or equivalents distinct from MDM canonical master structures
- Define how HES meter reference supports mapping bootstrap, operator comparison, and troubleshooting without turning HES vendor schema into the MDM core model
- Revisit which source-side attributes should stay as raw source reference only versus which should influence canonical master governance

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
