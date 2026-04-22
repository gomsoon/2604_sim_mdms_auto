# Partitioning Precheck

## Purpose

This document captures the design checks that should be completed before turning the main data-layer tables into PostgreSQL partitioned tables.

It exists because partitioning is not only a table-size optimization. It changes what kinds of uniqueness, indexing, lineage, and maintenance patterns remain valid.

The immediate target tables are:

- `hes_read_raw`
- `final_measurement`
- `landing_lp_em_read_block`

## Core precheck conclusion

The current `hes_read_raw` and `final_measurement` models are acceptable as minimal common MDM structures, but partitioning introduces follow-up work that should be treated explicitly rather than assumed away.

In short:

- the current raw/final structures are good enough to keep using as the common model
- the current uniqueness assumptions are not all partition-ready
- partitioning should therefore be implemented only after those assumptions are reviewed table by table

The current project stance is intentionally two-phase:

1. long-term direction
   - move global replay guarantees out of partitioned fact tables and into a dedicated support structure such as a replay registry
2. near-term execution
   - partition `hes_read_raw` first
   - keep the current replay and idempotency behavior in application logic
   - run the existing replay, idempotency, and regression tests again after partitioning
   - use those results to decide when the replay registry becomes mandatory rather than speculative

## Review of `hes_read_raw`

### Why the current structure is acceptable

The current raw-read model is already close to a vendor-neutral common interval-read structure.

It separates:

- source lineage and traceability
- source-specific metadata
- common MDM interval semantics

Important strengths:

- common identifiers
  - `meter_identifier`
  - `channel_identifier`
- common measurement time
  - `measured_at`
  - `interval_end_at`
  - `interval_size_minutes`
- common read value and quality
  - `reading_value`
  - `quality_code`
  - `status_code`
  - `unit_of_measure`
- source lineage
  - `hes_system_id`
  - `adapter_instance_id`
  - `adapter_run_id`
  - `ingest_batch_id`
- source-specific details remain available
  - `payload`
  - `source_table_name`
  - `source_block_key`
  - `source_record_key`
  - `source_slot_code`
  - `source_slot_index`

That means additional HES integrations can still map into the same raw table without changing the core MDM meaning of the row.

### What must be revisited before partitioning

The raw table currently has two different dedupe concerns:

- exact replay
  - `source_system + source_record_key`
- business duplicate
  - `source_system + meter_identifier + channel_identifier + measured_at`

Today this works because:

- the exact replay scope is supported by a partial unique index
- the business duplicate scope is supported by an index plus application logic

Partitioning changes the exact replay side.

PostgreSQL generally expects partitioned-table uniqueness to include the partition key.

If `hes_read_raw` is partitioned by `measured_at`, then:

- `UNIQUE (source_system, source_record_key)` is not automatically a clean fit
- because the uniqueness rule does not include `measured_at`

That does not mean partitioning is blocked. It means the replay rule needs a partition-compatible design.

Recommended options to evaluate:

1. dedicated replay registry table
   - keep `source_system + source_record_key` uniqueness outside the partitioned raw table
2. partition-compatible uniqueness redesign
   - only if replay semantics truly align with the partition key
3. application-plus-registry hybrid
   - application checks backed by a smaller globally unique support table

For long-term scalability, the first option is still the safest direction.

For the immediate next implementation step, however, the project may still partition `hes_read_raw` first and continue using the existing replay and idempotency logic as an interim guarantee, as long as:

- the current replay and idempotency regression tests remain green
- the project treats that result as an interim operating baseline rather than the final partition-safe design
- the replay registry remains visible in backlog and architecture decisions

## Review of `final_measurement`

### Why the current structure is acceptable

The current final model is a reasonable minimal downstream-ready table.

Important strengths:

- clean promotion from canonical to final
- explicit `finalized_at`
- shared identifiers already resolved
  - `measuring_component_id`
  - `device_id`
  - `service_point_id`
- business-ready timestamp and value
  - `measured_at`
  - `value`
  - `unit_of_measure`

That makes it suitable as a minimal final layer even if more advanced billing-related structures arrive later.

### What must be revisited before partitioning

The current final table uses a one-to-one uniqueness rule:

- `canonical_measurement_id` unique

If `final_measurement` becomes partitioned by `measured_at`, that uniqueness rule should be reviewed carefully for the same reason as raw replay:

- the unique key does not include the partition key

Recommended options to evaluate:

1. keep `final_measurement` non-partitioned slightly longer than raw
   - only if growth rate remains manageable
2. introduce a separate finalization registry or promotion ledger
   - one row per canonical measurement promoted
3. redesign uniqueness around a partition-compatible key
   - only if it does not damage the canonical-to-final meaning

The preferred direction is not to weaken the finalization guarantee. If partitioning needs a helper registry to preserve that guarantee, that is acceptable.

## Review of `landing_lp_em_read_block`

The landing block table is easier to partition than the core raw/final tables.

Why:

- its data is source-specific
- it is append-oriented
- replay semantics are already scoped around source block identity
- archive and purge behavior are naturally time-based

Still, one check remains important:

- if uniqueness is defined by `source_system + source_block_key`, confirm whether that uniqueness must remain globally enforced or whether a replay registry/support table is preferable here as well

## Current minimal decisions that should remain valid

The following minimal-stage decisions still look correct and should not be overturned just because partitioning is being introduced.

### Common raw model should remain interval-granular

Do not redesign common raw back into wide source-specific block rows just for partition convenience.

Wide source rows belong in:

- landing
- source-specific adapter processing

Common raw should remain:

- one interval read per row

### Vendor-specific details should remain outside final semantics

Do not push vendor-specific fields into:

- `canonical_measurement`
- `final_measurement`

The current separation is healthy and should remain the baseline.

### Application queries may still use ORM

Partitioning does not require abandoning SQLAlchemy ORM for normal application reads and writes.

The real split should be:

- ORM or SQLAlchemy query layer for application CRUD and query paths
- Alembic plus explicit SQL for partition DDL and operational partition management

## Backlog items implied by this precheck

The following items should be treated as explicit follow-up work before or during partitioning implementation.

### P-CHK-1. Replay uniqueness redesign for partitioned raw

- decide whether `source_record_key` uniqueness moves to a replay registry table
- keep exact replay guarantees without relying on a partition-incompatible global unique assumption
- treat this as a long-term target even if the first `hes_read_raw` partition rollout proceeds before the registry exists

### P-CHK-2. Finalization uniqueness redesign for partitioned final

- preserve the current one-final-per-canonical guarantee
- choose whether that guarantee remains in-table or moves into a small support registry

### P-CHK-3. Numeric precision review

The current `Float` usage is acceptable for minimal-stage implementation speed, but the project should review whether:

- `reading_value`
- `canonical_measurement.value`
- `final_measurement.value`

should become `Numeric/Decimal` before billing-facing stages grow.

### P-CHK-4. Final measurement revision model review

The current one-to-one finalization model is fine for minimal scope, but later stages should review:

- supersession
- re-finalization
- revision lineage
- correction handling

### P-CHK-5. Naming neutrality review

The current names are good enough for now, but the team may later review whether:

- `hes_read_raw`
- `hes_event_raw`

should evolve toward broader upstream-neutral terminology if the integration surface expands beyond classic HES expectations.

## Recommended next step

Before implementing the first partition migration:

1. confirm the target partition key per table
2. review the unique and dedupe assumptions against that partition key
3. decide which guarantees stay in-table and which move into helper registry tables
4. only then write the Alembic migration for partitioned tables

The practical execution order for the current stage is:

1. partition `hes_read_raw` first
2. preserve existing replay and idempotency behavior for the first rollout
3. rerun replay, idempotency, smoke, and regression tests
4. keep replay-registry design visible as the next hardening step rather than forcing it before the first partition experiment
