# Partitioning Implementation Plan

## Purpose

This document turns the partitioning strategy into an implementation-oriented plan.

It is intentionally more concrete than the strategy and precheck documents.

Its goal is to answer:

- what should be partitioned first
- what structural changes are required before native PostgreSQL partitioning is safe
- what tests must pass before the first partition rollout is accepted

## Current implementation stance

The project will proceed incrementally.

The current near-term target is:

- partition `hes_read_raw` first

The project will not block that first step on full replay-registry extraction, but it will also not pretend that the current schema is already fully partition-ready.

The first partition rollout should therefore be treated as:

- a controlled structural migration
- followed immediately by replay, idempotency, smoke, and regression verification

## Why `hes_read_raw` is the first target

`hes_read_raw` is the strongest first candidate because:

- it is expected to become the largest table
- its most important queries are naturally time-scoped
- the current AIMIR HES path already gives the team realistic live smoke scenarios
- replay and idempotency behavior are already testable in the current implementation

## Structural issue that must be handled explicitly

There is an additional issue beyond replay uniqueness.

The current `hes_read_raw` model uses:

- single-column `id` identity
- downstream foreign keys that point to `hes_read_raw.id`

Examples include:

- `canonical_measurement.hes_read_raw_id`
- `ingest_error_log.hes_read_raw_id`
- `reprocess_request.hes_read_raw_id`
- `hes_read_raw.duplicate_of_id`

For native PostgreSQL partitioned tables, unique and primary-key guarantees generally need to include the partition key.

If `hes_read_raw` is partitioned by `measured_at`, this means the project must review how downstream references will remain valid.

This is separate from replay uniqueness.

## Recommended implementation phases

### Phase 1. Prepare `hes_read_raw` for partitioning

Goals:

- keep the current application behavior
- expose the partition-compatible identity shape needed by PostgreSQL
- avoid introducing a replay registry too early

Recommended direction:

1. keep `measured_at` as the partition key
2. treat `id + measured_at` as the partition-compatible row identity at the database level
3. review and extend downstream references so they can follow that identity where needed
4. relax or redesign only the guarantees that native partitioning cannot preserve directly in the first rollout

This phase may require:

- composite uniqueness or composite foreign-key support
- additional lineage columns in downstream tables
- migration-time backfill for those lineage columns

### Phase 2. Partition `hes_read_raw`

Goals:

- create a native PostgreSQL monthly range-partitioned `hes_read_raw`
- preserve current query and ingest behavior as much as possible

Recommended baseline:

- parent table partitioned by `measured_at`
- monthly child partitions
- local per-partition indexes for:
  - `(source_system, meter_identifier, channel_identifier, measured_at)`
  - `adapter_run_id`
  - `ingest_batch_id`
  - optional `source_write_ts`

### Phase 3. Validate replay and idempotency on the partitioned raw table

Goals:

- prove that the first rollout has not broken existing behavior
- collect evidence before deciding whether replay-registry extraction becomes mandatory

Required verification:

- exact replay behavior still works
- business duplicate detection still works
- AIMIR bounded smoke still works
- canonical conversion still works
- event and alert flows still work

### Phase 4. Replay-registry hardening

Goals:

- remove long-term dependence on partition-hostile global replay uniqueness assumptions inside the raw fact table

This phase remains a strong long-term direction, but it is not the first blocking step.

### Phase 5. `final_measurement` partition review

The final table should be revisited only after:

- `hes_read_raw` partition behavior is proven
- replay and idempotency behavior are stable
- the finalization uniqueness strategy is clearer

## Recommended design posture for the first rollout

### What should remain unchanged if possible

- the common raw interval-granular shape
- current adapter-to-raw lineage
- current canonical conversion semantics
- current replay and idempotency tests

### What may change in the first rollout

- how `hes_read_raw` identity is represented for FK-safe partitioning
- how uniqueness is enforced at the raw table level
- which indexes remain on the parent versus the child partitions

### What should not be forced yet

- replay registry extraction
- `final_measurement` partitioning
- a large renaming of raw or final tables

## Test requirements for the first partition migration

This is a required rule for partition testing:

- tests must insert and query rows from at least two different calendar months

Do not accept a partition migration test that only exercises one month of data.

Why:

- a single-month test can still pass without proving real partition routing
- partition pruning and cross-partition behavior are only meaningfully exercised when more than one child partition exists

Recommended first test scenarios:

1. raw insert routing
   - insert one row in month A
   - insert one row in month B
   - confirm both are visible through the parent
2. replay and idempotency regression
   - run the same source records again across those months
   - confirm replay behavior is unchanged
3. duplicate detection regression
   - confirm business duplicate detection still works across the partitioned parent
4. AIMIR bounded smoke regression
   - use a bounded live window and confirm landing, raw, canonical, and event flow remain correct

## Backlog implications

The first `hes_read_raw` partition rollout does not close the full partitioning topic.

It leaves these follow-up items visible:

- replay-registry extraction
- partition-compatible raw identity and downstream FK review
- finalization uniqueness redesign
- `final_measurement` partition review

## Immediate next design step

Before writing the first migration:

1. decide the exact partition-compatible identity strategy for `hes_read_raw`
2. identify every downstream table that needs to carry the partition key or an equivalent lineage column
3. define the first monthly partition DDL shape
4. define the minimum cross-month regression tests
