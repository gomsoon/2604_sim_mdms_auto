# Manual Edit Baseline Design

## Purpose

This document defines the first manual edit slice for the repository.

The goal is to introduce a narrow, auditable operator correction path that:

- starts from an active `vee_exception`
- updates the mutable `initial_measurement` working copy
- creates a new current `final_measurement` revision instead of mutating history
- recalculates downstream `usage_transaction`, `bill_determinant`, and `bill_charge`
- stays clearly separated from both estimation and future full approval workflows

## Why manual edit is needed

The repository already has:

- current-plus-history `final_measurement`
- current-plus-history `bill_determinant`
- current-plus-history `bill_charge`
- operator-triggered `re-VEE`
- operator-triggered estimation

That means the processing core can already carry authoritative revisions through
to downstream outputs.

What is still missing is an explicit path for:

- operator-entered correction
- reason-code-driven change
- persistent audit of who changed what and why

This is the next practical MVP gap after estimation.

## First-slice scope

Included:

- operator-triggered manual edit from `vee_exception` detail
- edit only for an interval that already has:
  - `canonical_measurement`
  - `initial_measurement`
  - downstream lineage capable of re-finalization
- first editable fields:
  - `value`
  - optional `quality_code`
  - optional `status_code`
- explicit audit persistence
- downstream recalculation after successful edit

Not included in the first slice:

- synthetic creation of a missing interval
- changing `measured_at`
- changing `unit_of_measure`
- changing `service_point`, `device`, or `measuring_component`
- remapping source lineage
- bulk manual edit
- approval chain
- preview-and-compare workflow
- event-aware edit policy
- unification of manual edit and estimation UI

## Relationship to estimation

Manual edit and estimation should remain distinct in the first slice.

Estimation means:

- the system derives a substitute value through a known estimation strategy

Manual edit means:

- the operator explicitly enters the substitute value

The repository should therefore preserve separate audit and reason semantics for:

- estimated outcome
- manually corrected outcome

This keeps later operator reporting and business review clearer.

## Key design decision

### First manual edit is substitution-only

The first manual edit slice should support only:

- replacing the business outcome for an already-existing interval

It should not support:

- creating a brand-new interval with no `initial_measurement` anchor

Why:

- the current repository treats `initial_measurement` as the VEE working copy
- `final_measurement` still carries required canonical lineage
- synthetic interval creation would require a broader structural change than the
  first manual edit slice should take on

This means the first slice is best treated as:

- correction of an existing business interval

not:

- full manual gap-fill reconstruction

## Working-copy decision

The first manual edit slice should treat `initial_measurement` as the mutable
operator-adjusted working copy.

Recommended behavior:

- keep `hes_read_raw` immutable
- keep `canonical_measurement` immutable
- update `initial_measurement`
- keep later `final_measurement` authoritative through revision creation

Why:

- finalization already reads from `initial_measurement`
- changing only `final_measurement` would allow later re-finalization to drift
  back to the pre-edit value
- updating the working copy keeps replay and finalization deterministic

## First allowed edit targets

The first slice should begin with a small allowlist of VEE exception codes that
can reasonably be corrected by operator-entered substitution.

Recommended first allowlist:

- `vee_negative_value_detected`
- `vee_high_value_detected`
- `vee_zero_value_detected`

Recommended first exclusions:

- `vee_missing_interval_detected`
- `vee_duplicate_detected`
- `vee_interval_size_invalid`
- `vee_required_field_missing`

Why:

- the first group can often be addressed by direct correction of the existing
  interval value
- the second group usually needs structural repair, mapping repair, or
  synthetic creation rather than plain substitution

## Required input

The first manual edit slice should require:

- `reason_code`
- `edited_by`
- `operator_memo`

The edited value itself should also be required.

Optional in the first slice:

- `quality_code`
- `status_code`

Recommended first reason codes:

- `operator_meter_correction`
- `operator_source_override`
- `operator_data_entry_fix`
- `operator_business_override`

These codes should remain code-backed in the first rollout.

## Persistence

### `manual_edit_audit`

The first slice should add a dedicated append-only audit table.

Recommended minimum columns:

- `id`
- `pipeline_run_id`
- `service_point_id`
- `measuring_component_id`
- `device_id`
- `target_initial_measurement_id`
- `related_vee_exception_id`
- `target_measured_at`
- `reason_code`
- `edit_status`
- `edited_value`
- `edited_quality_code`
- `edited_status_code`
- `edited_by`
- `operator_memo`
- `superseded_final_measurement_id`
- `result_final_measurement_id`
- `details`
- `created_at`
- `updated_at`

Important interpretation:

- this is an audit record of one manual correction attempt
- it is not a current-row table
- each attempt creates a new row

Recommended first `edit_status` values:

- `applied`
- `blocked`
- `failed`

## Relationship to VEE

Manual edit should be modeled as one operator resolution path for active
`vee_exception`.

Recommended flow:

1. operator opens `vee_exception` detail
2. operator enters corrected value and reason
3. manual edit audit row is created
4. `initial_measurement` is updated
5. target `vee_exception` is resolved with `resolution_type = manually_corrected`
6. baseline VEE is re-evaluated
7. finalization decides whether a new current final revision is needed
8. downstream outputs are recalculated

The first slice does not need a new `initial_status` value.

Meaning should remain visible through:

- `manual_edit_audit`
- `vee_exception.resolution_type = manually_corrected`
- `final_measurement.revision_reason_code = manual_edit_applied`

## Edit validation and blocked conditions

Manual edit should be blocked when:

- the selected `vee_exception` does not exist
- the selected `vee_exception` is not active
- the selected exception code is outside the allowlist
- the target `initial_measurement` does not exist
- the edited value is invalid
- the edited value produces no effective business change
- optional quality or status input is invalid

Recommended blocked result codes:

- `blocked_exception_not_found`
- `blocked_exception_not_active`
- `blocked_unsupported_exception_code`
- `blocked_missing_initial_measurement`
- `blocked_invalid_value`
- `blocked_no_effective_change`
- `blocked_invalid_quality_code`
- `blocked_invalid_status_code`

## Relationship to `final_measurement`

Manual edit must not overwrite current `final_measurement` history.

Recommended rule:

- if the edit leads to an accepted finalizable state, create a new current
  `final_measurement` revision
- supersede the previous current final row

Recommended first revision behavior:

- old row:
  - `is_current = false`
  - `final_status = superseded`
- new row:
  - `is_current = true`
  - `revision_reason_code = manual_edit_applied`

This mirrors the estimation baseline and keeps downstream recalculation simple.

## Downstream recalculation

The first manual edit slice should close the full currently-supported business
loop.

Recommended recalculation order:

1. `usage_transaction`
2. `bill_determinant`
3. `bill_charge`

Why:

- downstream consumers should not need to know whether the upstream correction
  came from estimation or manual edit
- they only need a new current authoritative source row

## UI baseline

The first UI baseline should start only from:

- `vee_exception` detail

Recommended first form inputs:

- edited value
- optional quality code
- optional status code
- reason code
- operator memo

Recommended first result summary:

- audit id
- reason code
- before/after value
- new final revision id
- recalculated usage count
- recalculated determinant count
- recalculated charge count

## Explicit deferrals

The first manual edit baseline should explicitly defer:

- bulk edit
- approval workflow
- synthetic interval creation
- UOM change
- measured-at change
- remapping edit
- event-aware correction policy
- full side-by-side preview UI
- unified correction workspace for estimation and manual edit

## Recommended implementation sequence

1. `manual-edit-baseline-design.md`
2. `manual_edit_audit` ORM + Alembic
3. `manual_edits.py` service
4. `vee_exception` detail manual edit UI baseline
5. downstream recalculation regression coverage

## Summary

The first manual edit slice should be read as:

- operator-entered substitution on an existing interval
- persisted through append-only audit
- applied to `initial_measurement` as the mutable working copy
- finalized through current-plus-history revision
- propagated through usage, determinant, and charge recalculation

This keeps the first implementation narrow, auditable, and compatible with the
current processing-core architecture.
