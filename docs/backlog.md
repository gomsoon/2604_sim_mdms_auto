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
- first low-value slice may start as a narrow non-blocking `micro_value_warning`
  for tiny positive `kWh` interval values
- Missing interval detection
- first multiplier-validation slice may start as a unity-only guardrail because
  source-side multiplier lineage is not yet ingested into processing-core tables
- deferred: source multiplier ingest and snapshot persistence
- deferred: multiplier-aware canonical conversion
- deferred: actual-versus-expected multiplier mismatch validation once source
  multiplier lineage exists
- deferred: contract-aware, tariff-aware, and customer-class-aware low-value
  policy beyond the first micro-value warning slice

### V3. Basic estimation

- Linear interpolation
- Previous-value-based estimation
- Estimation audit
- Final measurement update flow
- first estimation slice starts with substitution-only operator flow
- first estimation slice supports only selected VEE exception codes such as
  `vee_negative_value_detected` and `vee_high_value_detected`
- next synthetic missing-interval slice should start with:
  - single-slot repair only
  - explicit `estimation_audit` lineage to `vee_exception` and
    `raw_interval_window_state`
  - synthetic `hes_read_raw -> canonical_measurement -> initial_measurement ->
    final_measurement` creation rather than an isolated gap-fill table
- deferred: multi-slot synthetic missing-interval estimation
- deferred: outage- or tamper-correlated missing-interval repair
- deferred: arbitrary synthetic interval creation without raw-window-state anchor
- deferred: estimation for `duplicate_detected`
- deferred: estimation for `required_field_missing`
- deferred: estimation for `interval_size_invalid`
- deferred: bulk estimation
- deferred: estimation preview or approval workflow
- deferred: broader event-aware estimation policy beyond the first
  event-aware correction guardrail slice
- deferred: synthetic missing-interval bulk repair UI
- deferred: multi-slot repair UI
- deferred: inline missing-slot preview or visualization in `vee_exception` detail

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
- first manual edit slice starts from active `vee_exception`
- first manual edit slice is substitution-only on existing `initial_measurement`
- first manual edit slice supports only selected VEE exception codes such as
  `vee_negative_value_detected`, `vee_high_value_detected`, and
  `vee_zero_value_detected`
- first manual edit slice updates `initial_measurement` as the mutable working
  copy and regenerates current `final_measurement` through revision
- deferred: synthetic missing-interval manual creation
- deferred: measured-at change
- deferred: unit-of-measure change
- deferred: remapping edits across service point, device, or component
- deferred: bulk manual edit
- deferred: approval workflow
- deferred: preview-and-compare correction workspace
- first event-aware correction policy slice should reuse outage and tamper
  context to guide or constrain estimation and manual edit actions
- deferred: broader event-aware correction policy

### V6. Usage calculation

- `usage_transaction`
- Daily usage
- Monthly usage
- Service-point usage API
- usage-local timezone windowing
- usage quality summary and missing-interval visibility
- explicit distinction between `usage_transaction` and later billing-ready determinant outputs
- first service-facing API slice may start with read-only service-point usage list
  and usage-summary endpoints
- first service-facing aggregate slice may expose `service_point` summary across
  current `usage_transaction`, `bill_determinant`, and `bill_charge` layers
- deferred: service-facing export or pagination contract refinement

### V7. Event-linked decisioning

- Event lookup service
- Outage and tamper context matching
- Event-aware VEE extension
- Event-linked exceptions
- first event-linked slice enriches existing VEE rules before adding new
  decision tables
- first event-linked slice starts with outage and tamper context only
- first event-aware correction policy slice should:
  - block estimation for tamper-correlated negative and high-value anomalies
  - surface outage-correlated missing-interval guidance without pretending a
    first-slice correction path exists
- deferred: zero-value suppression by outage context
- deferred: duration-aware event correlation windows
- deferred: master-data-driven event code catalog
- deferred: automatic event-aware correction selection
- deferred: event-aware approval workflow
- deferred: broader event-aware estimation policy
- deferred: broader event-aware manual edit policy

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
- `service_point_billing_context` persistence
- `service_point_billing_context` delete/archive policy
- `service_point_billing_context` bulk import or source sync
- `service_point_billing_context` history diff and operator audit view
- billing context to determinant impact spotlight and audit summary
- billing timezone and billing-cycle anchor governance
- tariff assignment baseline
- `service_point_tariff_assignment` persistence
- `service_point_tariff_assignment` management UI and history
- tariff assignment source sync or bulk import
- tariff assignment to bill charge impact visibility
- simple bill charge persistence and calculation
- `bill_charge` baseline design
- `flat_energy_charge` only in the first bill-charge rollout
- code-backed minimal tariff rate registry before a full tariff engine
- determinant-to-charge revision lineage and supersession
- bill charge blocked visibility for missing tariff assignment
- bill charge blocked visibility for missing tariff rate
- deferred: TOU charge rules
- deferred: demand charge rules
- deferred: tax and surcharge calculation
- deferred: discount or subsidy rules
- optional invoice summary baseline
- first invoice summary slice should stay a calculated read model and
  service-facing API above current `bill_charge`
- deferred: invoice summary persistence
- deferred: invoice number allocation
- deferred: invoice document rendering
- Billing export queue
- first export queue slice should persist immutable payload snapshots from
  calculated `invoice_summary`
- first export queue slice should include request and item progress counters,
  `claimed_by`, and `last_heartbeat_at`
- export recovery lineage should remain explicit through request-level and
  item-level source references
- Export payload contract
- Batch or API export
- Re-send and recalculation handling
- Export status management
- current export status action API slices expose queued-request cancel and
  failed-request rerun or recreate
- deferred: external delivery integration
- deferred: completed export re-send or re-export action API
- deferred: root-request lineage and recovery-depth tracking
- deferred: processing export cancel or safe stop workflow
- deferred: bulk export action API
- deferred: export worker registry
- deferred: stale auto-reclaim or auto-recovery

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
- first auth close-out slice should include:
  - `user_account`
  - `user_action_audit`
  - `admin` and `operator` role baseline
  - session-cookie login and logout for human-facing surfaces
  - append-only login and logout history
  - route protection for web and human-facing API
- authenticated user activity across existing features should become auditable by
  account for:
  - read
  - create
  - update
  - delete
  - execute
- recommended model:
  - `auth_session_audit` for session lifecycle
  - `user_action_audit` for broad feature usage
  - existing domain-specific audit tables for sensitive business mutations
- login and logout history should:
  - use a dedicated append-only auth audit table as the authoritative source
  - optionally mirror key auth events into `operational_event` later for
    timeline visibility
- actor identity propagation should be staged by functional unit rather than in
  one large schema sweep:
  - phase B: VEE, estimation, manual edit, and replay request actor FKs
  - phase C: billing export request and recovery actor FKs
  - phase D: master-data and system-administration `created_by/updated_by`
    fields
  - phase D should be delivered in two slices:
    - row-level lineage on master-data and admin-managed reference tables
    - runtime action lineage for adapter enable/pause and manual run-once flows
- estimation actor-lineage follow-up should be deferred separately from the
  first FK slice:
  - actor column/filter on estimation audit list views
  - legacy estimation audit actor backfill
  - CLI or system-triggered estimation actor injection beyond web-session flows
- manual edit actor-lineage follow-up should be deferred separately from the
  first FK slice:
  - actor column/filter on manual edit audit list views
  - legacy manual edit actor backfill
  - CLI or system-triggered manual edit actor injection beyond web-session flows
- replay request actor-lineage follow-up should be deferred separately from the
  first FK slice:
  - actor column/filter on replay request list views
  - legacy replay request actor backfill
  - item-level replay actor lineage and processor/system-triggered actor injection
- billing export actor-lineage follow-up should be deferred separately from the
  first FK slice:
  - actor column/filter on billing export list views
  - legacy billing export request actor backfill
  - item-level billing export actor lineage
  - worker/runtime actor registry beyond the current `claimed_by` string
  - CLI or system-triggered export actor injection beyond web-session flows
- phase D master-data and system-administration follow-up should be deferred
  separately from the first row-lineage slice:
  - legacy master-data row actor backfill
  - actor column/filter on master-data and HES/admin list views
  - legacy `adapter_run` requester backfill
  - actor column/filter on adapter runtime views beyond the first
    `requested_by` visibility slice
  - richer typed actor columns on `operational_event` beyond the first
    action-snapshot expansion in `details`
  - worker/runtime registry beyond current string-based runtime identity
- every actor-identity propagation slice should update regression tests in the
  same change set so the new user-account lineage is both written and visible
  in the affected feature area
- deferred: MFA
- deferred: password reset
- deferred: API token or PAT baseline
- deferred: richer RBAC beyond `admin` and `operator`
- deferred: auth-event analytics dashboard
- deferred: full user-management UI

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

### X8. `mdms-preproduct` operational hardening and visibility polish

- After MVP close-out, use the `mdms-preproduct` phase for bounded internal use
  and issue-driven hardening before opening new subsystem scope
- current status:
  - first-wave decision-test hardening is complete for `VEE`, `estimation`, and
    `manual edit`
  - the first bounded smoke-evidence pass has been executed with no unplanned
    foundational blocker observed
  - visibility-polish is complete for:
    - billing export and adapter runtime-versus-human actor clarity
    - `vee_exception` queue and detail wording clarity
    - replay request list and detail readability
    - correction detail consistency across `vee`, `estimation`, and
      `manual edit`
    - stale-warning and blocked-reason wording cleanup across export and
      correction views
- Use the shared visibility inventory in:
  - [mdms-preproduct-visibility-polish-worklist.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-visibility-polish-worklist.md)
- Prioritize:
  - bug fixes on supported operator flows
  - actor and audit readability on high-traffic views
  - small visibility polish on `vee_exception`, replay, correction detail, and
    remaining export wording screens
  - known-limitations communication for internal operators
- Keep each hardening slice small enough to update regression coverage in the
  same change set
- Defer broader product expansion until repeated internal-use friction shows a
  clearer priority signal
- During VEE decision-test hardening, defer:
  - exhaustive worst-case rule-combination matrices
  - full event-context combination sweeps
  - web/API-level summary-code assertion duplication
  - exhaustive operational-event detail assertions for every baseline path
  - full acknowledge/resolve/re-evaluate lifecycle permutation matrices across
    repeated actor and memo combinations
- During finalization adjacency hardening, defer:
  - exhaustive meter/date/limit filter combination matrices
  - watermark timestamp exactness assertions beyond branch-level confidence
  - web/API-level duplication of finalization summary assertions
  - large-batch and partition performance characterization
  - concurrency semantics across overlapping finalization runs
- During estimation decision-test hardening, defer:
  - exhaustive strategy-by-exception matrices
  - full event-policy combination sweeps across all supported estimation paths
  - exhaustive synthetic precheck-to-apply contract sweeps across all window variants
  - exhaustive downstream result-code and side-effect matrices across substitution and synthetic paths
  - web/API-level duplication of estimation result assertions
  - synthetic precheck UI duplication assertions
  - synthetic multi-window or bulk estimation contract matrices
  - exhaustive pipeline-run detail assertions for every blocked and applied estimation path
  - performance and concurrency characterization for synthetic/bulk estimation
- During manual-edit decision-test hardening, defer:
  - exhaustive reason-code matrices across all supported manual-edit paths
  - exhaustive downstream result-code and side-effect matrices across applied manual-edit paths
  - exhaustive audit-detail and pipeline-detail key assertions for every blocked and applied path
  - web/API-level duplication of every manual-edit service result assertion
  - exhaustive resolved-exception actor and operator-memo lifecycle assertions across repeated edit cycles
  - multi-edit same-measurement lifecycle matrices across reopen, supersede, and re-finalize paths
  - exhaustive transition-and-audit contract matrices across clean-pass, same-code reopen, and repeated re-VEE paths
  - performance and concurrency characterization for repeated manual-edit and re-VEE cycles
- During the first `vee_exception` visibility-polish slice, defer:
  - queue layout redesign or new summary widgets
  - dedicated policy-explanation UI beyond wording and label clarity
  - correction preview workspace concepts
  - exhaustive wording assertions across every locale permutation
- During the first replay-request visibility-polish slice, defer:
  - explicit replay-to-replay recovery lineage modeling
  - replay queue layout redesign or new progress summary widgets
  - richer runtime or worker tracking for replay execution
  - per-item deep drilldown redesign beyond wording and readability polish
  - exhaustive locale-wording assertion sweeps for replay list and detail views
- During the first correction-detail consistency slice, defer:
  - expanding `vee_exception` correction result cards with direct actor and memo context
  - correction list/detail layout redesign beyond summary and lineage ordering
  - blocked-reason taxonomy cleanup across every correction flow and locale edge case
  - cross-view correction summary widget redesign
  - exhaustive locale-wording assertion sweeps for correction detail pages
- During the first stale-warning and blocked-reason wording cleanup slice, defer:
  - replay-specific stale or heartbeat semantics beyond current auto-refresh and failure wording
  - export and replay layout redesign beyond wording and emphasis cleanup
  - blocked-reason taxonomy redesign across every correction and export path
  - exhaustive locale-wording assertion sweeps for stale and blocked guidance text
- During the export wording follow-through slice, defer:
  - explicit export-to-export recovery lineage wording beyond current queue fields
  - large export list/detail layout redesign or new summary widgets
  - richer failed-item spotlighting beyond wording and emphasis cleanup
  - exhaustive locale-wording assertion sweeps for export list and detail views

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
