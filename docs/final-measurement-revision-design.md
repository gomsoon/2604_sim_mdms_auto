# Final Measurement Revision Design

## Purpose

This document defines the next design step for turning `final_measurement` from a single-promotion target into an authoritative measurement layer that can support later correction, re-finalization, and historical traceability.

The current repository already treats `final_measurement` as the only valid input to `usage_transaction`. Because of that, later correction flows must not overwrite history in an opaque way.

## Why a revision model is needed

The current baseline works for the first processing slice:

- one accepted `initial_measurement`
- one promoted `final_measurement`
- one downstream usage path

That is still too simple for the longer MDM direction.

Later stages will need to handle:

- VEE re-evaluation that changes the authoritative outcome
- operator correction after a business review
- estimation or substitute value flows
- re-finalization after source-side late correction
- partitioning of `final_measurement` without losing business meaning

Without an explicit revision model, the repository risks:

- overwriting the current final row without clear lineage
- recalculating usage from a moving target without audit clarity
- making downstream billing-oriented outputs hard to explain

## Current baseline

The current `final_measurement` model has:

- `initial_measurement_id`
- `canonical_measurement_id`
- `final_status`
- `finalized_at`

The current business meaning is:

- final is created only from `accepted initial_measurement`
- open blocking `vee_exception` prevents promotion

This is a good first authoritative baseline, but it is still effectively `one active final per initial measurement` with no explicit revision history.

## Design goals

The next revision model should satisfy all of the following:

- keep one clearly active authoritative final for each measurement scope
- preserve older final outcomes as auditable history
- make correction reason and replacement reason explicit
- allow downstream usage recalculation to identify which final rows changed
- remain compatible with future partitioning by `measured_at`

## Recommended first revision model

### Principle

Treat `final_measurement` as an append-friendly history table with one active row and zero or more superseded rows for the same business measurement lineage.

### Recommended new concepts

- `revision_number`
- `revision_reason_code`
- `supersedes_final_measurement_id`
- `superseded_by_final_measurement_id`
- `is_current`
- optional `effective_from_at`
- optional `effective_to_at`

### Meaning

- `revision_number`
  - starts at `1`
  - increments whenever a later authoritative final replaces the current one
- `revision_reason_code`
  - explains why a later revision exists
  - examples:
    - `vee_re_evaluated`
    - `operator_correction`
    - `source_late_update`
    - `estimation_applied`
- `supersedes_final_measurement_id`
  - points backward to the previous authoritative final
- `superseded_by_final_measurement_id`
  - points forward to the replacement final
- `is_current`
  - exactly one current final should exist for one business measurement lineage

## Recommended business lineage anchor

The current repository already has `initial_measurement` as the processing entry point.

The first revision model should keep that as the main business anchor:

- one `initial_measurement`
- one or more `final_measurement` revisions over time

Recommended rule:

- only one `current final_measurement` may exist per `initial_measurement_id`

This keeps the processing meaning simple:

- `initial_measurement` identifies the business measurement being decided
- `final_measurement` history identifies how that decision changed over time

## Recommended status model

The current `final_status` should evolve into a slightly richer set.

Recommended first values:

- `finalized`
- `finalized_with_adjustment`
- `superseded`
- later `estimated`

Recommended rule:

- the replacing row should be `finalized` or `finalized_with_adjustment`
- the older row should become `superseded`

## Current-row guarantee

The first revision-aware guarantee should be:

- unique current row per `initial_measurement_id`

The design target is:

- many historical rows allowed
- exactly one `is_current = true` row for the same `initial_measurement_id`

This also fits later `usage_transaction` recalculation better than keeping a hard `unique(initial_measurement_id)` forever.

## Recommended downstream effect on usage

`usage_transaction` should continue to read only from current authoritative `final_measurement` rows.

When a new final revision is created:

- the previous final becomes historical
- affected usage windows should be marked for recalculation
- the usage layer should not need to interpret why the final changed, only that the current authoritative input changed

This separation keeps `usage_transaction` simpler.

## Relation to re-VEE

The current manual `re-VEE` baseline re-evaluates `initial_measurement` and may reopen or clear `vee_exception`.

The next revision step should connect to that flow like this:

- if re-VEE changes the finalization outcome before promotion, no final revision is needed yet
- if re-VEE occurs after a final already exists and changes the accepted result, create a new final revision instead of mutating the old final in place

This is the key handoff between:

- `re-VEE`
- `final revision`
- `usage recalculation`

## Partitioning implications

This design should also stay compatible with later partition review.

Recommended direction:

- partition key remains `measured_at`
- revision lineage stays row-to-row through explicit self-reference
- the `current row` guarantee may need a partition-compatible supporting strategy later

This means the revision model should be designed first, and only then should `final_measurement` partitioning be implemented.

## Recommended implementation sequence

### Phase 1. Design and compatibility review

- lock the revision concepts
- keep current runtime behavior unchanged

### Phase 2. Add revision columns

- add revision and supersession columns to `final_measurement`
- backfill existing rows as:
  - `revision_number = 1`
  - `is_current = true`
  - no supersession links

### Phase 3. Switch promotion behavior

- if no final exists for the `initial_measurement`, create revision `1`
- if a current final exists and a new authoritative result is required:
  - create a new final row
  - mark the previous row `superseded`
  - update supersession links

### Phase 4. Connect to usage recalculation

- identify affected usage windows
- re-run usage aggregation for impacted periods only

## Explicit deferrals

The first revision design does not yet require:

- versioned rule sets for all VEE rules
- full estimation workflow
- approval chains
- billing export correction handling
- bulk supersession UI

Those should come after the baseline revision model is proven stable.

## Summary

The next durable meaning of `final_measurement` should be:

- one business measurement lineage anchored by `initial_measurement`
- one current authoritative final
- optional historical superseded finals

That is the safest bridge between the current post-VEE baseline and later recalculable usage and billing-ready outputs.
