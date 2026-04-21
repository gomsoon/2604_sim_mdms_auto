# Provisional Raw Schema

## Purpose

This document defines a provisional raw-table design for the minimal stage so development can continue before the real company HES schema is reviewed next week.

For packed interval-read sources and the newer interval-granular raw direction, the more concrete follow-up design now lives in:

- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
- [interval-raw-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/interval-raw-table-design.md)

## Design intent

- Move forward now without pretending unknown details are already confirmed
- Keep the raw design flexible enough to absorb moderate HES column differences later
- Separate stable core columns from source-specific details
- Preserve source fidelity through explicit metadata and JSON payload storage

## What this document is

- a working pre-design
- a structure for early DDL thinking
- a basis for service and migration planning

## What this document is not

- the final HES-to-MDM mapping
- the final production DDL
- a replacement for the real HES schema review

## Baseline assumptions

The provisional design assumes the company HES can provide or allow derivation of the following:

- meter identifier
- channel identifier for reads
- read or event timestamp
- value for raw reads
- quality or status information
- at least one trace context such as batch ID, message ID, job ID, or source record ID

If some of these are missing, the design can still proceed, but raw ingest semantics and deduplication rules may need adjustment.

## Core design principle

The raw tables should contain:

1. stable MDM-facing columns used for ingest, tracing, and first-pass processing
2. source-specific metadata columns that help later investigation
3. a `jsonb` payload column to preserve source detail without blocking progress now

## Provisional table set

### `ingest_batch`

Purpose:

- track each ingest delivery or logical submission
- preserve envelope-level metadata
- support operator tracing and idempotency handling

Suggested columns:

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `source_system` | `varchar(50)` | Yes | example: `HES` |
| `source_interface` | `varchar(100)` | No | API, file loader, scheduler, connector name |
| `batch_id` | `varchar(150)` | Conditional | use when source sends a batch identifier |
| `message_id` | `varchar(150)` | Conditional | use when source sends per-message identifier |
| `source_table_name` | `varchar(150)` | No | useful for DB-origin tracing |
| `source_schema_version` | `varchar(50)` | No | helpful when upstream schema changes |
| `received_at` | `timestamptz` | Yes | source-provided or server ingest time |
| `ingested_at` | `timestamptz` | Yes | server-side ingest timestamp |
| `locale` | `varchar(10)` | No | `en` or `ko` fallback path |
| `record_type` | `varchar(30)` | Yes | `read` or `event` |
| `record_count` | `integer` | No | total records in envelope |
| `source_payload` | `jsonb` | Yes | preserved envelope payload |
| `created_at` | `timestamptz` | Yes | audit convenience |
| `updated_at` | `timestamptz` | Yes | audit convenience |

Notes:

- At least one of `batch_id` or `message_id` should be present where possible
- `source_payload` should preserve the original envelope without destructive rewrite

### `hes_read_raw`

Purpose:

- store raw HES read records before business-level normalization
- preserve source fidelity while exposing a stable query shape for MDM processing

Suggested columns:

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `ingest_batch_id` | `bigint` | Yes | FK to `ingest_batch` |
| `source_system` | `varchar(50)` | Yes | usually `HES` |
| `source_table_name` | `varchar(150)` | No | source DB table when available |
| `source_record_id` | `varchar(150)` | No | original HES PK or business key |
| `meter_id` | `varchar(150)` | Yes | source meter identifier |
| `channel_id` | `varchar(150)` | Yes | source channel identifier |
| `measurement_ts` | `timestamptz` | Yes | measurement timestamp |
| `received_at` | `timestamptz` | No | source or ingest receive time |
| `value` | `numeric(20,6)` | Yes | broad enough for common utility values |
| `unit_of_measure` | `varchar(30)` | No | source UOM |
| `interval_size_minutes` | `integer` | No | useful for interval reads |
| `source_type` | `varchar(30)` | No | `interval`, `scalar`, or similar |
| `quality_code` | `varchar(60)` | No | source quality code |
| `status_code` | `varchar(60)` | No | source status code |
| `multiplier` | `numeric(20,6)` | No | explicit source multiplier if available |
| `is_deleted_at_source` | `boolean` | No | if HES represents logical deletion |
| `raw_row_created_at` | `timestamptz` | No | original source insert timestamp |
| `raw_row_updated_at` | `timestamptz` | No | original source update timestamp |
| `dedupe_key` | `varchar(255)` | No | optional derived key for ingest logic |
| `source_payload` | `jsonb` | Yes | reconstructed or direct source payload |
| `created_at` | `timestamptz` | Yes | MDM insert timestamp |
| `updated_at` | `timestamptz` | Yes | MDM update timestamp |

Notes:

- The exact unique strategy should stay provisional until the HES schema is reviewed
- `source_payload` makes it safe to continue even when some source-specific fields are still unknown

### `hes_event_raw`

Purpose:

- store raw HES events and alarms before broader event-aware logic is added

Suggested columns:

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `ingest_batch_id` | `bigint` | Yes | FK to `ingest_batch` |
| `source_system` | `varchar(50)` | Yes | usually `HES` |
| `source_table_name` | `varchar(150)` | No | source DB table when available |
| `source_record_id` | `varchar(150)` | No | original HES PK or business key |
| `meter_id` | `varchar(150)` | No | strongly preferred for later correlation |
| `event_ts` | `timestamptz` | Yes | event timestamp |
| `received_at` | `timestamptz` | No | source or ingest receive time |
| `event_code` | `varchar(100)` | Yes | source event/alarm code |
| `severity` | `varchar(30)` | No | low, medium, high or source equivalent |
| `event_source` | `varchar(60)` | No | meter, HES, network, etc. |
| `status_code` | `varchar(60)` | No | source event status |
| `raw_row_created_at` | `timestamptz` | No | original source insert timestamp |
| `raw_row_updated_at` | `timestamptz` | No | original source update timestamp |
| `source_payload` | `jsonb` | Yes | preserved source detail |
| `created_at` | `timestamptz` | Yes | MDM insert timestamp |
| `updated_at` | `timestamptz` | Yes | MDM update timestamp |

### `ingest_error_log`

Purpose:

- store ingest-stage validation or persistence issues
- distinguish ingest failures from later VEE exceptions

Suggested columns:

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `ingest_batch_id` | `bigint` | No | nullable if batch creation fails early |
| `source_system` | `varchar(50)` | Yes | source system label |
| `error_code` | `varchar(100)` | Yes | stable machine-readable code |
| `error_scope` | `varchar(30)` | Yes | `envelope`, `read`, `event`, `persistence` |
| `source_table_name` | `varchar(150)` | No | source tracing |
| `source_record_id` | `varchar(150)` | No | source tracing |
| `meter_id` | `varchar(150)` | No | when available |
| `channel_id` | `varchar(150)` | No | read-specific tracing |
| `measurement_ts` | `timestamptz` | No | read-specific tracing |
| `event_ts` | `timestamptz` | No | event-specific tracing |
| `message_en` | `text` | Yes | operator-facing English message |
| `message_ko` | `text` | Yes | operator-facing Korean message |
| `error_details` | `jsonb` | No | diagnostic detail |
| `source_payload` | `jsonb` | No | failed source record or envelope |
| `created_at` | `timestamptz` | Yes | insert timestamp |

## Provisional indexing ideas

These are starting points only and should be verified after real HES review.

### `ingest_batch`

- index on `source_system`
- index on `batch_id`
- index on `message_id`
- index on `received_at`

### `hes_read_raw`

- index on `ingest_batch_id`
- index on `meter_id`
- index on `(meter_id, channel_id, measurement_ts)`
- index on `measurement_ts`
- optional index on `source_record_id`

### `hes_event_raw`

- index on `ingest_batch_id`
- index on `meter_id`
- index on `event_ts`
- optional index on `event_code`

### `ingest_error_log`

- index on `ingest_batch_id`
- index on `error_code`
- index on `meter_id`
- index on `created_at`

## What can safely remain provisional until next week

- exact varchar lengths
- exact numeric precision scale
- final unique constraints
- final dedupe key logic
- exact source-specific auxiliary columns
- exact event severity and status domains

## What should not wait

We can confidently proceed now with:

- raw table responsibilities
- separation of `ingest_batch`, `hes_read_raw`, `hes_event_raw`, and `ingest_error_log`
- PostgreSQL data type direction
- requirement to preserve source payload in `jsonb`
- distinction between stable core columns and source-specific details

## Recommended next step before real HES schema arrives

Use this provisional schema as the basis for:

1. migration planning
2. ORM refactor target shape
3. ingest service refactor planning
4. test-case design for minimal raw ingest behavior

## Next-step adjustment process

When the company HES schema is available next week:

1. fill [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)
2. compare actual HES fields to this provisional schema
3. mark each provisional column as `confirmed`, `adjusted`, or `dropped`
4. generate the first concrete PostgreSQL DDL and migration plan
