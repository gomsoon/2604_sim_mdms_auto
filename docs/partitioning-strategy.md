# Partitioning Strategy

## Purpose

This document defines the initial PostgreSQL partitioning strategy for large append-only meter-read tables in the MDM system.

It exists because table shape alone is not enough. The raw and final read tables will eventually be large enough that operational behavior must be part of the design baseline.

For the table-by-table readiness review that should happen before the first partition migration, see [partitioning-precheck.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-precheck.md).

## Core recommendation

The initial production-like baseline should use time-based range partitioning.

Recommended first choice:

- monthly partitions

This is the best default balance between:

- query pruning effectiveness
- partition count
- operational complexity
- retention and archive management

## Why time-based partitioning is the primary baseline

The main large tables in this project are append-only and naturally time-oriented.

Typical access patterns are expected to include:

- meter plus date range
- source system plus date range
- batch plus recent time window
- canonical and final processing by time window

Because of that, partitioning by time aligns naturally with:

- operator queries
- backfill
- replay
- retention
- archive
- reindex and maintenance

## Why monthly partitions are the recommended starting point

Monthly partitions are usually the right starting point because they avoid both extremes.

If partitions are too coarse:

- pruning is less effective
- maintenance affects too much data at once

If partitions are too fine:

- partition count becomes expensive to manage
- planning overhead increases
- operational scripts become more complex

Monthly partitions are usually a good baseline until actual production volume proves otherwise.

## Recommended table-by-table policy

### `hes_read_raw`

Recommended partition key:

- `measured_at`

Recommended partition model:

- monthly range partitioning

Why:

- this is expected to become the largest MDM table
- most important queries will naturally include time predicates
- retention and archive are time-oriented

### `final_measurement`

Recommended partition key:

- `measured_at`

Recommended partition model:

- monthly range partitioning

Why:

- final measurement volume also grows continuously
- downstream usage and billing windows are time-based

### `landing_lp_em_read_block`

Recommended partition key:

- `source_write_ts` when reliably populated
- otherwise `created_at`

Recommended partition model:

- monthly range partitioning

Why:

- landing is append-heavy
- replay and purge are easier when organized by source-write or arrival time

### `raw_interval_window_state`

Recommended partition model:

- do not partition initially

Why:

- this table is state-oriented, not raw-event-heavy
- it is usually much smaller than the append-only raw and final tables
- keep it simpler until real volume proves otherwise

## Recommended indexing baseline

Partitioning alone is not enough.

Each large partitioned table should still have focused local indexes.

### `hes_read_raw`

Recommended per-partition indexes:

- `(meter_identifier, channel_identifier, measured_at)`
- `(source_system, measured_at)`
- `adapter_run_id`
- `ingest_batch_id`
- optional `source_write_ts`

### `final_measurement`

Recommended per-partition indexes:

- `(measuring_component_id, measured_at)`
- `(device_id, measured_at)`
- `(service_point_id, measured_at)`

### `landing_lp_em_read_block`

Recommended per-partition indexes:

- `adapter_run_id`
- `(meter_source_id, source_business_hour, channel_code)`
- `source_write_ts`
- `source_block_key`

## Query discipline requirement

Partition pruning only helps when queries use the partition key effectively.

The project should treat this as a design rule:

- large raw and final table queries should include explicit time predicates whenever practical

Examples:

- `measured_at >= :from and measured_at < :to`
- `source_write_ts >= :from and source_write_ts < :to`

Avoid broad queries that omit time windows when hitting large append-only tables.

## Unique and primary key caution

PostgreSQL partitioned tables require careful design for uniqueness.

Recommended posture:

- use surrogate IDs for row identity
- avoid early global uniqueness assumptions unless the partition key is included
- keep source dedupe logic explicit in application or partition-compatible indexes

This is especially important for:

- `hes_read_raw`
- `landing_lp_em_read_block`

It is also important for:

- `final_measurement`

because the current one-to-one finalization guarantee may need a partition-compatible support design.

because source-side late updates and replay semantics may not fit a simple global unique key.

The current project posture is:

- long-term
  - move truly global replay guarantees toward a separate support structure such as a replay registry
- short-term
  - allow the first `hes_read_raw` partition rollout to proceed before that registry exists
  - keep replay and idempotency under explicit application control
  - confirm behavior again through replay, idempotency, smoke, and regression tests after the first partition migration

## Maintenance baseline

Partitioning should support easier maintenance, not just query speed.

Recommended operational expectations:

- create next month's partitions ahead of time
- keep a small rolling window of future partitions pre-created
- document archive and drop rules by table
- reindex individual partitions when needed instead of large whole-table operations
- monitor autovacuum and bloat at the partition level

## Retention baseline

Retention should be defined per table, not globally.

Recommended baseline:

- `landing_lp_em_read_block`
  - keep long enough to support replay and audit
- `hes_read_raw`
  - keep as authoritative raw source-of-truth
- `final_measurement`
  - keep as authoritative business output
- `raw_interval_window_state`
  - keep active and recent windows only
  - treat it as an operational state table, not a long-term raw archive
  - size retention around `window period + operational alpha`
  - use the `alpha` margin for late arrivals, reprocess, and operator review
  - purge, compact, or summarize older rows as policy matures

Exact periods should remain operational decisions, but partitioning should make those decisions easy to apply.

## Why append-only still benefits even when transaction speed declines

As volume grows, transaction cost will still rise.

Partitioning does not remove all write overhead.

What it does help with is:

- keeping index scopes smaller
- keeping vacuum more localized
- making old data less disruptive to current reads
- keeping date-range queries predictable

This is why partitioning is a necessary baseline, even though it is not the only scaling tool.

## What partitioning does not solve by itself

Partitioning alone will not solve:

- bad query shapes
- missing time predicates
- overly broad indexes
- excessive updates on hot rows
- poor source-watermark design

The project must therefore combine:

- append-only modeling
- explicit completeness-state tables
- time-based partitioning
- disciplined indexes
- query design that respects pruning

## Recommended first implementation baseline

The first implementation baseline should be:

- monthly partitions for `hes_read_raw`
- monthly partitions for `final_measurement`
- monthly partitions for `landing_lp_em_read_block`
- no partitioning yet for `raw_interval_window_state`

This is the recommended point to start from before production measurements justify refinement.

## Related documents

- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
- [interval-raw-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/interval-raw-table-design.md)
- [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
