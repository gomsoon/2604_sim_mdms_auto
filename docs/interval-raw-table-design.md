# Interval Raw Table Design

## Purpose

This document turns the current interval-raw and Oracle `LP_EM` adapter decisions into a concrete table-design baseline.

It focuses on three tables:

- `landing_lp_em_read_block`
- `hes_read_raw`
- `raw_interval_window_state`

## Design scope

This is a design baseline for the next implementation step.

It is:

- specific enough to drive migrations and ORM work
- still adjustable where real source behavior requires refinement

It is not yet:

- a final production DDL
- a complete partitioning and retention plan

## Core design principle

The packed source shape and the common raw shape must stay separate.

- packed source block rows belong in landing
- one interval read belongs in `hes_read_raw`
- missing-slot and completion status belong in `raw_interval_window_state`

## Table 1. `landing_lp_em_read_block`

### Purpose

Persist one overseas Oracle `LP_EM` source row as one replayable landing block.

### Recommended row meaning

One row equals:

- one `LP_EM` source row
- one source meter
- one source hour
- one source channel
- zero to many source slot values

### Recommended columns

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `adapter_instance_id` | `bigint` | Yes | FK to `adapter_instance` |
| `adapter_run_id` | `bigint` | Yes | FK to `adapter_run` |
| `source_system` | `varchar(50)` | Yes | example: `HES_OVERSEAS` |
| `source_table_name` | `varchar(150)` | Yes | fixed as `LP_EM` for this adapter family |
| `source_block_key` | `varchar(255)` | Yes | deterministic replay key |
| `meter_source_id` | `varchar(100)` | Yes | from `LP_EM.METER_ID` |
| `device_source_id` | `varchar(100)` | No | from `LP_EM.DEVICE_ID` |
| `mdev_id` | `varchar(100)` | No | from `LP_EM.MDEV_ID` |
| `mdev_type` | `varchar(50)` | No | from `LP_EM.MDEV_TYPE` |
| `channel_code` | `varchar(30)` | Yes | source-native channel |
| `source_business_hour` | `varchar(10)` | Yes | from `YYYYMMDDHH` |
| `source_hour_component` | `varchar(2)` | No | from `HH` |
| `source_write_text` | `varchar(14)` | No | from `WRITEDATE` before parse |
| `source_write_ts` | `timestamptz` | No | parsed source write timestamp |
| `location_source_id` | `varchar(100)` | No | from `LOCATION_ID` |
| `supplier_source_id` | `varchar(100)` | No | from `SUPPLIER_ID` |
| `enddevice_source_id` | `varchar(100)` | No | from `ENDDEVICE_ID` |
| `value_cnt` | `integer` | No | from `VALUE_CNT` |
| `block_value` | `numeric(20,6)` | No | from `VALUE` |
| `slot_values` | `jsonb` | Yes | compact map such as `{\"00\": 14.2}` |
| `slot_count` | `integer` | Yes | number of non-null slot values |
| `parsed_ok` | `boolean` | Yes | parse success flag |
| `parse_error_code` | `varchar(100)` | No | set when source row parse fails |
| `source_payload` | `jsonb` | Yes | preserved original row |
| `created_at` | `timestamptz` | Yes | insert timestamp |
| `updated_at` | `timestamptz` | Yes | update timestamp |

### Recommended constraints

- unique on `source_system, source_block_key`
- FK to `adapter_instance`
- FK to `adapter_run`

### Recommended indexes

- index on `adapter_run_id`
- index on `meter_source_id`
- index on `source_business_hour`
- index on `source_write_ts`
- index on `(meter_source_id, source_business_hour, channel_code)`

### Why `slot_values` should be `jsonb`

The source has `VALUE_00` through `VALUE_59`, but copying sixty physical columns into PostgreSQL is not necessary for the landing baseline.

Recommended approach:

- preserve the exact source row in `source_payload`
- also preserve a compact parsed slot map in `slot_values`

This keeps replay simple without forcing the MDM schema to inherit Oracle's packed column layout.

## Table 2. `hes_read_raw`

### Purpose

Persist one logical interval read per row in the common raw layer.

### Recommended row meaning

One row equals:

- one source meter
- one source channel
- one interval start timestamp
- one interval value

### Recommended columns

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `ingest_batch_id` | `bigint` | Yes | FK to `ingest_batch` |
| `adapter_instance_id` | `bigint` | No | lineage from integration runtime |
| `adapter_run_id` | `bigint` | No | lineage from integration runtime |
| `landing_lp_em_read_block_id` | `bigint` | No | nullable lineage for Oracle landing path |
| `source_system` | `varchar(50)` | Yes | source label |
| `source_table_name` | `varchar(150)` | No | source origin, example `LP_EM` |
| `source_block_key` | `varchar(255)` | No | block lineage |
| `source_record_key` | `varchar(255)` | No | source interval-level replay key |
| `meter_identifier` | `varchar(100)` | Yes | common raw meter identifier |
| `device_identifier` | `varchar(100)` | No | optional device trace |
| `channel_identifier` | `varchar(30)` | Yes | source-native or mapped channel code |
| `source_slot_code` | `varchar(10)` | No | example `00`, `15`, `30`, `45` |
| `source_slot_index` | `integer` | No | numeric slot position |
| `measured_at` | `timestamptz` | Yes | interval start in UTC |
| `interval_end_at` | `timestamptz` | No | optional interval end |
| `interval_size_minutes` | `integer` | Yes | interval length |
| `reading_value` | `numeric(20,6)` | Yes | interval value |
| `unit_of_measure` | `varchar(30)` | No | source or adapter-derived UOM |
| `quality_code` | `varchar(60)` | No | source quality |
| `status_code` | `varchar(60)` | No | source status |
| `source_business_ts` | `timestamptz` | No | parsed source business hour anchor |
| `source_write_ts` | `timestamptz` | No | parsed source write timestamp |
| `canonical_status` | `varchar(30)` | Yes | existing raw-to-canonical status |
| `is_duplicate` | `boolean` | Yes | duplicate marker |
| `duplicate_of_id` | `bigint` | No | self-reference when duplicate |
| `source_payload` | `jsonb` | Yes | source interval payload or expansion evidence |
| `created_at` | `timestamptz` | Yes | insert timestamp |
| `updated_at` | `timestamptz` | Yes | update timestamp |

### Recommended constraints

- FK to `ingest_batch`
- FK to `adapter_instance`
- FK to `adapter_run`
- FK to `landing_lp_em_read_block` when landing path is used
- self FK on `duplicate_of_id`

### Recommended indexes

- index on `ingest_batch_id`
- index on `adapter_run_id`
- index on `meter_identifier`
- index on `(meter_identifier, channel_identifier, measured_at)`
- index on `measured_at`
- index on `source_write_ts`
- optional index on `source_record_key`

### Recommended raw dedupe baseline

The dedupe baseline should remain source-aware.

For packed-row expansions such as `LP_EM`, a good first candidate is:

- `source_system`
- `meter_identifier`
- `channel_identifier`
- `measured_at`
- `source_write_ts`

This allows a later source write for the same logical interval to remain visible as newer evidence instead of silently replacing the earlier row.

## Table 3. `raw_interval_window_state`

### Purpose

Track collection completeness for one meter, one channel, and one logical window.

### Recommended row meaning

One row equals:

- one source system
- one meter
- one channel
- one completeness window

For the first Oracle `LP_EM` adapter:

- one row will usually represent one source hour window

### Recommended columns

| Column | PostgreSQL type | Required | Notes |
| --- | --- | --- | --- |
| `id` | `bigserial` | Yes | surrogate key |
| `source_system` | `varchar(50)` | Yes | source label |
| `meter_identifier` | `varchar(100)` | Yes | source meter identifier |
| `channel_identifier` | `varchar(30)` | Yes | source-native or mapped channel |
| `window_start_at` | `timestamptz` | Yes | anchor in UTC |
| `window_size_minutes` | `integer` | Yes | example `60` |
| `interval_size_minutes` | `integer` | Yes | example `15` or `60` |
| `expected_slot_count` | `integer` | Yes | expected rows in the window |
| `received_slot_count` | `integer` | Yes | observed rows in the window |
| `received_slot_bitmap` | `varchar(256)` | No | simple bitmap or slot string |
| `first_source_write_ts` | `timestamptz` | No | first arrival in the window |
| `last_source_write_ts` | `timestamptz` | No | latest source write in the window |
| `completion_status` | `varchar(30)` | Yes | `open`, `partial`, `complete`, `late_update` |
| `late_update_count` | `integer` | Yes | count of late-arriving updates |
| `last_adapter_run_id` | `bigint` | No | last runtime touchpoint |
| `last_ingest_batch_id` | `bigint` | No | last ingest touchpoint |
| `details` | `jsonb` | No | adapter- or source-specific state |
| `created_at` | `timestamptz` | Yes | insert timestamp |
| `updated_at` | `timestamptz` | Yes | update timestamp |

### Recommended constraints

- unique on `source_system, meter_identifier, channel_identifier, window_start_at, window_size_minutes`
- FK to `adapter_run` on `last_adapter_run_id`
- FK to `ingest_batch` on `last_ingest_batch_id`

### Recommended indexes

- index on `completion_status`
- index on `window_start_at`
- index on `(meter_identifier, channel_identifier, window_start_at)`
- index on `last_source_write_ts`

### Recommended status semantics

- `open`
  - window created but not enough evidence yet
- `partial`
  - some intervals received but expected count not reached
- `complete`
  - expected slots received
- `late_update`
  - window was already complete, but newer source evidence arrived
- `superseded`
  - optional future state for replay or correction workflows

## Partitioning recommendation

For the first production-like baseline:

- partition `hes_read_raw` by month on `measured_at`
- consider partitioning `landing_lp_em_read_block` by month on `source_write_ts` or `created_at`
- keep `raw_interval_window_state` unpartitioned initially unless its volume proves otherwise

The fuller operational rationale now lives in:

- [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)

## Retention recommendation

Recommended baseline:

- keep `hes_read_raw` as the authoritative raw layer
- keep landing longer than a short transient queue because replay value is high
- keep completeness-state rows only for active and recent windows

For `raw_interval_window_state`, the intended posture is:

- do not treat it as a long-term audit table
- retain roughly `window period + operational alpha`
- use the `alpha` margin to absorb late arrivals, reprocess work, and operator review time
- purge, compact, or roll up older rows once they no longer help current completeness decisions

The exact retention periods should remain an operational decision.

## Relationship to current codebase

The current code already contains:

- `ingest_batch`
- `hes_read_raw`
- adapter lineage on `ingest_batch`

The next design step should extend rather than replace those concepts.

Most likely implementation order:

1. extend `hes_read_raw` toward interval-granular source lineage
2. add `landing_lp_em_read_block`
3. add `raw_interval_window_state`

## Recommended next implementation step

Translate this document into:

1. migration draft
2. ORM model draft
3. adapter service contracts
4. boundary-value test cases for expansion and completeness updates

## Related documents

- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
- [lp-em-adapter-mapping.md](/home/tprover/2604_sim_mdms_auto/docs/lp-em-adapter-mapping.md)
- [nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)
