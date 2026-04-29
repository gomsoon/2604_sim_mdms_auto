# Processing Core Persistence Design

## Purpose

This document turns the processing/core baseline into a persistence-level design that can be implemented through ORM models and Alembic migrations.

The immediate target is not a full billing engine.

The immediate target is to introduce the first explicit persistence boundary between:

- normalized mapping output
- VEE processing input
- VEE execution trace
- VEE exception state
- finalized measurement output

Implementation note:

- the current repository persistence baseline uses integer surrogate keys widely
- the first ORM and Alembic implementation of this design should stay aligned with that existing convention
- later widening to larger integer identity types can be reviewed separately if scale pressure makes it necessary

## Design scope

This document covers:

- `initial_measurement`
- `vee_execution_log`
- `vee_exception`
- the relationship to `final_measurement`

This document does not yet define the full `usage_transaction` table implementation.

That remains the next persistence slice after the first VEE boundary is established.

First follow-up implementation note:

- the first `usage_transaction` rollout should read only from `final_measurement`
- it may derive operational window timezone from `hes_system.timezone_name` until a dedicated service-point timezone field exists
- it may derive `interval_size_minutes` through final-to-raw lineage until final rows carry that value directly

## Current starting point

The repository currently persists:

- `hes_read_raw`
- `canonical_measurement`
- `final_measurement`
- `pipeline_run`
- `processing_watermark`
- `operational_event`

Current limitation:

- `final_measurement` is still populated from a minimal `well_formed canonical` rule
- there is no explicit persistent VEE-stage boundary yet

## Recommended processing-chain identity

Recommended first identity chain:

- `hes_read_raw.id`
- `canonical_measurement.id`
- `initial_measurement.id`
- `vee_execution_log.id`
- `vee_exception.id`
- `final_measurement.id`

Key lineage rule:

- one `canonical_measurement` may produce at most one current `initial_measurement` in the first baseline
- one `initial_measurement` may participate in multiple `vee_execution_log` rows over time
- one `initial_measurement` may produce zero or more `vee_exception` rows over time
- one accepted or resolved `initial_measurement` may produce one `final_measurement` in the first baseline

## Table 1. `initial_measurement`

### Role

`initial_measurement` is the first business-processing row that is ready for VEE.

It should exist after:

- raw mapping succeeded
- canonical normalization succeeded

It should exist before:

- VEE acceptance
- estimation
- manual correction
- finalization

### Minimum fields

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | `integer` | No | PK in the first implementation |
| `canonical_measurement_id` | `integer` | No | FK, unique in first baseline |
| `measuring_component_id` | `integer` | No | FK |
| `device_id` | `integer` | No | FK |
| `service_point_id` | `integer` | No | FK |
| `measured_at` | `timestamptz` | No | copied from canonical |
| `value` | `numeric(19,4)` | No | copied from canonical |
| `quality_code` | `varchar(40)` | Yes | |
| `status_code` | `varchar(40)` | Yes | |
| `unit_of_measure` | `varchar(20)` | No | |
| `initial_status` | `varchar(30)` | No | processing-entry state |
| `ready_for_vee_at` | `timestamptz` | No | first VEE-ready timestamp |
| `details` | `jsonb` | No | compact processing metadata |
| `created_at` | `timestamptz` | No | |
| `updated_at` | `timestamptz` | No | |

### Minimum constraints

- PK on `id`
- FK to `canonical_measurement`
- unique on `canonical_measurement_id` in the first baseline
- index on `measured_at`
- index on `initial_status`
- composite index on `service_point_id, measured_at`

### Recommended first `initial_status` values

- `ready`
- `held`
- `exception`
- `accepted`
- `superseded`

Recommended interpretation:

- `ready`: available for VEE
- `held`: intentionally not processed yet
- `exception`: open blocking issue exists
- `accepted`: VEE accepted and ready for final promotion
- `superseded`: later revision path placeholder

### Recommended first state transitions

Recommended first transition path:

- `ready -> accepted`
- `ready -> exception`
- `ready -> held`
- `held -> ready`
- `exception -> accepted`
- `accepted -> superseded`

Important first-baseline rule:

- `accepted` should mean "eligible for final promotion"
- `exception` should mean "at least one open blocking processing issue exists"

## Table 2. `vee_execution_log`

### Role

`vee_execution_log` records one VEE processing attempt and its outcome.

It is not only an audit table.

It is also the first stable execution truth for later re-VEE and operator traceability.

### Minimum fields

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | `integer` | No | PK in the first implementation |
| `initial_measurement_id` | `integer` | Yes | for single-measurement execution scope |
| `pipeline_run_id` | `integer` | Yes | link to the broader processing run |
| `execution_scope` | `varchar(30)` | No | `measurement`, `window`, `batch` |
| `trigger_type` | `varchar(30)` | No | `scheduled`, `manual`, `reprocess`, `system` |
| `rule_set_code` | `varchar(60)` | No | baseline rule-set identity |
| `period_start_at` | `timestamptz` | Yes | |
| `period_end_at` | `timestamptz` | Yes | |
| `execution_status` | `varchar(30)` | No | |
| `started_at` | `timestamptz` | No | |
| `completed_at` | `timestamptz` | Yes | |
| `summary_code` | `varchar(60)` | Yes | short result |
| `details` | `jsonb` | No | counts, rule hits, metadata |
| `created_at` | `timestamptz` | No | |
| `updated_at` | `timestamptz` | No | |

### Minimum constraints

- PK on `id`
- FK to `initial_measurement`
- FK to `pipeline_run`
- index on `execution_status`
- index on `started_at`
- index on `initial_measurement_id`

### Recommended first `execution_status` values

- `running`
- `passed`
- `failed`
- `completed_with_exception`

### Recommended first `summary_code` examples

- `vee_passed`
- `vee_failed_required_field`
- `vee_failed_uom`
- `vee_failed_interval_size`
- `vee_failed_missing_interval`
- `vee_completed_with_duplicate`

### Recommended first rule-code baseline

The first rule catalog should stay small and explicit.

Recommended first `rule_set_code`:

- `vee_baseline_v1`

Recommended first machine-readable rule or summary codes:

- `required_field_missing`
- `uom_invalid`
- `interval_size_invalid`
- `duplicate_detected`
- `negative_value_detected`
- `zero_value_detected`
- `high_value_detected`
- `low_value_detected`
- `missing_interval_detected`

## Table 3. `vee_exception`

### Role

`vee_exception` is the operator-facing persistent abnormality record for processing-stage issues.

It should be distinct from:

- `ingest_error_log`
- generic `operational_event`

### Minimum fields

| Column | Type | Null | Notes |
| --- | --- | --- | --- |
| `id` | `integer` | No | PK in the first implementation |
| `initial_measurement_id` | `integer` | No | FK |
| `vee_execution_log_id` | `integer` | Yes | FK |
| `exception_code` | `varchar(80)` | No | stable machine code |
| `severity` | `varchar(20)` | No | |
| `exception_status` | `varchar(30)` | No | |
| `blocking_finalization` | `boolean` | No | default `true` |
| `detected_at` | `timestamptz` | No | |
| `acknowledged_at` | `timestamptz` | Yes | |
| `acknowledged_by` | `varchar(120)` | Yes | |
| `resolved_at` | `timestamptz` | Yes | |
| `resolution_type` | `varchar(40)` | Yes | |
| `operator_memo` | `text` | Yes | |
| `details` | `jsonb` | No | |
| `created_at` | `timestamptz` | No | |
| `updated_at` | `timestamptz` | No | |

### Minimum constraints

- PK on `id`
- FK to `initial_measurement`
- FK to `vee_execution_log`
- index on `exception_status`
- index on `exception_code`
- index on `detected_at`
- index on `blocking_finalization`

### Recommended first `exception_status` values

- `open`
- `acknowledged`
- `resolved`

### Recommended first `resolution_type` values

- `accepted_as_is`
- `estimated`
- `manually_corrected`
- `ignored`

### Recommended first `exception_code` baseline

- `vee_required_field_missing`
- `vee_uom_invalid`
- `vee_interval_size_invalid`
- `vee_duplicate_detected`
- `vee_negative_value_detected`
- `vee_zero_value_detected`
- `vee_high_value_detected`
- `vee_low_value_detected`
- `vee_missing_interval_detected`

## Relationship to `final_measurement`

### Recommended first baseline rule

`final_measurement` should remain the first authoritative downstream measurement layer, but its creation rule should change.

The next follow-up design for revision and supersession is described in [final-measurement-revision-design.md](/home/tprover/2604_sim_mdms_auto/docs/final-measurement-revision-design.md).

Current direction:

- final is created from `well_formed canonical`

Recommended next direction:

- final is created from `accepted initial_measurement`

### Recommended minimum changes to `final_measurement`

In the next code phase, consider:

- add `initial_measurement_id`
- preserve `canonical_measurement_id` for backward lineage continuity
- treat `canonical_measurement_id` as legacy-support lineage, not the only business gate

Recommended minimum new fields:

- `initial_measurement_id` FK
- `final_status`
- `finalized_at`

The existing table already has:

- `final_status`
- `finalized_at`

So the main follow-up is the `initial_measurement_id` lineage and new promotion rule.

### Recommended backward-compatibility rule

During the first transition slice, the repository may temporarily keep:

- `canonical_measurement_id`
- current finalization service entry points

while adding:

- `initial_measurement_id`
- VEE-derived acceptance semantics

Recommended compatibility policy:

- do not remove `canonical_measurement_id` in the first VEE rollout
- backfill `initial_measurement_id` from `canonical_measurement_id` where a matching initial row already exists
- treat missing backfill as a temporary compatibility state, not as the long-term target
- use it as legacy-support lineage while the business gate moves to `initial_measurement`

## First promotion rule

A `final_measurement` may be created only when:

- `initial_measurement.initial_status = 'accepted'`
- no open blocking `vee_exception` exists

Recommended first `final_status` values after the VEE boundary appears:

- `finalized`
- `finalized_with_adjustment`
- `superseded`
- latest relevant `vee_execution_log` outcome is compatible with finalization

## Operator visibility integration

The first persistence slice should fit the existing operator surfaces.

Recommended integration points:

- `pipeline_run` for process execution
- `operational_event` for VEE milestones
- dedicated VEE exception list/detail later
- existing event detail drill-down should eventually include:
  - `initial_measurement`
  - latest `vee_execution_log`
  - open `vee_exception`

Recommended first operational event codes:

- `initial_measurement_created`
- `vee_execution_started`
- `vee_execution_passed`
- `vee_execution_failed`
- `vee_exception_opened`
- `vee_exception_resolved`
- `final_measurement_promoted`

## Recommended implementation order

### Step 1. Persistence only

- add `initial_measurement`
- add `vee_execution_log`
- add `vee_exception`
- do not immediately replace current finalization behavior

Recommended migration note:

- adding these tables should be backward-compatible with the current canonical/final baseline
- the first schema rollout should avoid forcing immediate reprocessing of all historical canonical rows

### Step 2. Dual-running transition

- keep current finalization path available
- begin creating `initial_measurement`
- begin logging VEE no-op or pass-through execution rows

Recommended first compatibility behavior:

- newly created canonical rows should create `initial_measurement`
- VEE may initially run as pass-through for clearly valid rows
- current finalization may continue temporarily while the new processing lineage is recorded

### Step 3. Finalization rule switch

- require accepted `initial_measurement`
- block finalization on open blocking VEE exceptions

Recommended implementation note:

- switch business gating first
- cleanup of legacy assumptions can happen after successful regression coverage

### Step 4. Usage persistence

- add `usage_transaction`
- calculate usage only from post-VEE final rows

## Historical data and backfill strategy

The first rollout should avoid a risky all-history rewrite.

Recommended policy:

### Existing historical data

- keep existing `canonical_measurement` and `final_measurement` rows valid
- do not require immediate backfill of complete VEE history

### Optional first backfill

If a backfill is desired, keep it intentionally limited:

- create `initial_measurement` from existing canonical rows
- mark them with `details.backfill_source = "canonical_backfill"`
- do not invent synthetic `vee_exception` rows unless the rule truly detects one
- avoid synthetic historical `vee_execution_log` rows unless needed for a specific audit requirement

### Forward-only safety

The first implementation may be:

- forward-correct for new measurements
- backward-compatible for existing finalized rows

This is a safer rollout than forcing all historical measurements through newly introduced persistence immediately.

## Minimum test gate

The first implementation should not be considered complete unless these cases are tested:

1. `canonical_measurement -> initial_measurement` creation
2. pass-through VEE execution log creation
3. blocking VEE exception creation
4. finalization blocked by open VEE exception
5. finalization allowed after accepted or resolved state
6. traceability from final back to canonical through initial and VEE structures

## Explicit deferrals

This first persistence slice should not yet include:

- advanced VEE rule grouping
- estimation audit detail tables
- manual edit audit tables
- TOU usage structures
- billing export structures
- final revision or supersession logic beyond placeholders

## Summary

The next code-facing processing/core persistence slice should add:

- `initial_measurement`
- `vee_execution_log`
- `vee_exception`

and then use those objects to redefine when a `final_measurement` becomes authoritative.
