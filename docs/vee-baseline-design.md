# VEE Baseline Design

## Purpose

This document defines the first practical VEE baseline for the repository.

The goal is not to build a full advanced rule framework immediately.

The goal is to introduce:

- a clear VEE execution boundary
- persistent VEE traceability
- minimal operator-visible VEE exceptions
- a stable promotion path from `initial_measurement` to `final_measurement`

## Scope of the baseline

Included in the first VEE baseline:

- explicit VEE input boundary
- execution logging
- rule result persistence
- minimal exception lifecycle
- minimal accepted-versus-exception outcome model

Not included yet:

- advanced rule sequencing
- branching rule framework
- tariff-aware decisioning
- full manual approval workflow
- sophisticated re-VEE orchestration

## Recommended core objects

### `initial_measurement`

Purpose:

- represent the first processing-stage measurement record ready for VEE

Recommended minimum fields:

- `id`
- `canonical_measurement_id`
- `measuring_component_id`
- `device_id`
- `service_point_id`
- `measured_at`
- `value`
- `quality_code`
- `status_code`
- `unit_of_measure`
- `initial_status`
- `ready_for_vee_at`
- `created_at`
- `updated_at`

Recommended `initial_status` values:

- `ready`
- `held`
- `exception`
- `superseded`

### `vee_execution_log`

Purpose:

- record one VEE execution attempt and its result

Recommended minimum fields:

- `id`
- `execution_scope`
- `trigger_type`
- `rule_set_code`
- `service_point_id`
- `device_id`
- `measuring_component_id`
- `period_start_at`
- `period_end_at`
- `execution_status`
- `started_at`
- `completed_at`
- `details`

Recommended `execution_scope` values:

- `measurement`
- `window`
- `batch`

Recommended `execution_status` values:

- `running`
- `passed`
- `failed`
- `completed_with_exception`

### `vee_exception`

Purpose:

- persist operator-visible VEE failures or unresolved data-quality conditions

Recommended minimum fields:

- `id`
- `initial_measurement_id`
- `vee_execution_log_id`
- `exception_code`
- `severity`
- `exception_status`
- `detected_at`
- `resolved_at`
- `resolution_type`
- `details`
- `operator_memo`

Recommended `exception_status` values:

- `open`
- `acknowledged`
- `resolved`

Recommended `resolution_type` values:

- `accepted_as_is`
- `estimated`
- `manually_corrected`
- `ignored`

## Minimal rule set

The first VEE baseline should implement only rules already visible in the backlog.

Recommended minimal rules:

- required-field validation
- UOM validation
- interval size validation
- duplicate check
- negative check
- zero check
- high check
- low check
- missing interval detection

Notes:

- these rules are intentionally small in scope
- the objective is stable persistence and operator flow, not advanced analytical coverage

## VEE result model

The first VEE baseline should reduce outcomes to three business results:

1. accepted
2. accepted_with_adjustment
3. exception

Recommended interpretation:

- accepted: final may be created directly
- accepted_with_adjustment: final may be created, but audit or estimation lineage must remain visible
- exception: final must not be created until resolution

## Promotion rule to `final_measurement`

The repository should change the meaning of finalization from:

- current `well_formed canonical promotion`

to:

- `VEE-accepted business promotion`

Recommended rule:

- a `final_measurement` may be created only when:
  - a corresponding `initial_measurement` exists
  - VEE outcome is accepted or resolved to an accepted state
  - no open blocking `vee_exception` remains

## Operator visibility

The first VEE slice should reuse existing operational visibility patterns.

Recommended visibility:

- `pipeline_run` for processing runs
- `operational_event` for VEE milestones
- `vee_exception` list/detail for operator action

Important distinction:

- `ingest_error_log` is for ingest-stage failures
- `vee_exception` is for processing-stage data-quality or business-rule failures

## Reprocessing expectations

The first VEE baseline does not need full re-VEE orchestration, but it should prepare for it.

Recommended preparation:

- preserve links from `initial_measurement` to `canonical_measurement`
- preserve links from `final_measurement` to `initial_measurement` or equivalent lineage in a later step
- make exception resolution explicit enough that a later re-VEE flow can replay decisions

## Testing expectations

The first VEE baseline should be accompanied by explicit tests for:

- accepted measurement path
- blocking exception path
- accepted-with-adjustment path
- finalization blocked by open exception
- duplicate rule path
- negative or zero value path
- cross-interval missing data path

## Summary

The first VEE baseline should focus on persistence boundaries and operator-visible outcomes, not on advanced rule framework sophistication.

The design target is:

- `initial_measurement` as VEE input
- `vee_execution_log` as trace
- `vee_exception` as operator-facing abnormality
- `final_measurement` as post-VEE authoritative output
