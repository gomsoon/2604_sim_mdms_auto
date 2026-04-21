# Replay And Idempotency Operations

## Purpose

This document explains how replay and idempotency are currently implemented in the minimal stage, what operational limits that implies, and how the team should run bounded versus larger-scale ingestion safely.

It exists to answer:

- what currently prevents duplicated source rows from multiplying downstream data
- where the current implementation may become expensive at larger volume
- when the team should process data in one run versus multiple bounded runs
- what should be hardened before broad backfill or higher concurrency is attempted

## Current implementation baseline

Replay and idempotency are currently enforced in multiple layers.

### 1. Source-block replay protection in landing

The AIMIR `LP_EM` adapter builds one `source_block_key` per source block and checks whether that key already exists in landing.

Current meaning:

- same `source_block_key` and same payload: reuse the existing landing row
- same `source_block_key` and different payload: fail with a replay-conflict error

Current implementation:

- [app/services/adapter_execution.py](/home/tprover/2604_sim_mdms_auto/app/services/adapter_execution.py)
- [app/models.py](/home/tprover/2604_sim_mdms_auto/app/models.py)

Current landing uniqueness:

- `landing_lp_em_read_block.source_system`
- `landing_lp_em_read_block.source_block_key`

### 2. Exact replay protection in common raw

After block expansion, each interval read receives a `source_record_key`.

Current meaning:

- if the same `source_system + source_record_key` is seen again, the raw row is treated as an exact replay and skipped
- replayed rows are counted in pipeline details and adapter smoke verification

Current implementation:

- [app/services/ingestion.py](/home/tprover/2604_sim_mdms_auto/app/services/ingestion.py)
- [app/models.py](/home/tprover/2604_sim_mdms_auto/app/models.py)

### 3. Business-duplicate protection

In addition to exact replay, the current raw-ingest path also checks for logical duplicates by:

- `source_system`
- `meter_identifier`
- `channel_identifier`
- `measured_at`

Current meaning:

- exact source replay and business duplicate are not treated as the same thing
- this helps when the same interval appears again under a different source-row identity

### 4. Completeness-state idempotency

`raw_interval_window_state` is updated per:

- `source_system`
- `meter_identifier`
- `channel_identifier`
- `window_start_at`
- `window_size_minutes`

Current meaning:

- the same window can be revisited without creating duplicate state rows
- late-arriving or newer source writes can be tracked as `late_update`

## Strengths of the current approach

The current implementation is strong enough for:

- bounded smoke validation
- small or medium incremental polling batches
- rerunning a failed batch without uncontrolled duplication
- confirming replay behavior in real source data
- auditing how landing, raw, canonical, and completeness state changed

This has already been validated with live AIMIR HES smoke runs in:

- a narrow single-channel window
- a widened single-channel window
- a bounded multi-channel window

## Operational limits of the current approach

The current implementation favors correctness and traceability over maximum throughput.

That is the right tradeoff for the minimal stage, but it also means cost grows as volume grows.

### Current cost drivers

For a large run, the current path may perform:

- one landing existence lookup per source block
- one exact replay lookup per expanded interval row
- one business-duplicate lookup per expanded interval row
- one completeness-state lookup and update per window
- many intermediate `flush()` operations during a single run

### What this means operationally

At larger scale, replay safety is not free.

The main load does not come only from inserts. It also comes from:

- repeated indexed lookups
- ORM object creation
- transaction growth
- update pressure on window-state rows

This is why the current model is safe for bounded runs, but should not yet be treated as a bulk-unbounded backfill engine.

## Recommended operating posture

### 1. Real-time or near-real-time polling

Recommended posture:

- use relatively small `batch_size`
- run more frequently
- let watermark advancement move in small steps
- prefer repeated bounded runs over one very large run

Why:

- this keeps transactions smaller
- it lowers replay-check cost per transaction
- it reduces lock time and rollback impact

### 2. Backfill or recovery runs

Recommended posture:

- do not run broad historical ranges in one shot
- slice by bounded `business_hour` window
- optionally slice further by channel or meter set
- execute multiple runs sequentially

Recommended initial slicing examples:

- 1 hour
- 6 hours
- 1 day

Choose the slice size according to:

- database response time
- ingest latency tolerance
- CPU and memory pressure
- storage I/O characteristics

### 3. Replay-heavy verification

If replay or idempotency itself is the target of the test:

- keep the source window narrow
- rerun the same bounded window
- compare `source_rows_fetched`, `ingest_records_created`, and `replayed_records`

That gives better signal than widening the time range during replay testing.

## When one run is acceptable

A single run is currently reasonable when:

- the source window is deliberately bounded
- expected source rows are small enough to inspect
- the purpose is smoke verification or targeted recovery
- the team can tolerate one transaction covering the whole run

Recent AIMIR smoke validation followed this model successfully.

## When multiple bounded runs are preferable

Multiple bounded runs are preferable when:

- source rows become too large to inspect safely
- replay checks begin to dominate runtime
- the database server shows CPU, memory, or I/O pressure
- the source range spans many days or many channels
- the team is performing backfill rather than smoke verification

This should be the default operating posture for broad data recovery until heavier hardening is complete.

## Current hardening gaps

The current implementation still has important scale-related gaps.

### Gap 1. Replay and duplicate checks are still application-driven

The current path uses application queries to detect replay and duplicate conditions before insert.

That is simple and auditable, but it is more expensive than database-native conflict handling at larger volume.

### Gap 2. `hes_read_raw` does not yet use the full dedupe baseline as a database constraint

The current code checks:

- `source_system + source_record_key`
- `source_system + meter_identifier + channel_identifier + measured_at`

But those checks are not yet fully enforced as the primary dedupe baseline by a database unique strategy.

### Gap 3. Concurrency is not yet hardened for high parallelism

The current adapter-run claim model is still minimal-stage friendly, but not yet optimized for many concurrent workers.

Broad concurrency should wait until claim and dedupe behavior are hardened further.

### Gap 4. Large-table operational strategy is still partly planned rather than fully implemented

Partitioning direction is already documented, but the large append-only tables are not yet fully moved onto the intended operational partition baseline.

## Recommended next hardening steps

### Short-term

1. document and keep using bounded-window operation for backfill
2. strengthen PostgreSQL scheduled-run and concurrency tests
3. design stronger dedupe indexes and constraints for `hes_read_raw`

### Medium-term

1. move hot replay and duplicate paths toward database-assisted conflict handling
2. harden adapter-run claim semantics for concurrent workers
3. implement partitioning on large append-only read tables

### Later

1. consider bulk-loading or batch-upsert patterns for larger backfill scenarios
2. consider dedicated recovery or replay workflows separate from live incremental polling

## Minimal-stage decision

The current minimal-stage decision should be:

- correctness first
- bounded runs by default
- broad backfill only through sliced repeated runs

This keeps operational risk acceptable while preserving a clean path toward later performance hardening.

## Related documents

- [adapter-live-hardening-plan.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-live-hardening-plan.md)
- [adapter-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-test-matrix.md)
- [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)
- [interval-raw-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/interval-raw-table-design.md)
- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
