# Common Raw Interval Model

## Purpose

This document defines how the MDM common raw layer should represent interval reads when multiple HES products with different source-table layouts must converge into one stable internal model.

## Core decision

The MDM common raw layer should store one interval read per row.

Source-specific wide rows such as:

- one row per hour
- one row per channel per hour
- one row containing `VALUE_00` through `VALUE_59`

may exist in source systems or landing tables, but they should not define the MDM common raw shape.

## Why this matters

The project is expected to onboard additional HES systems over time. If the MDM common raw layer copies one source vendor's block layout, every later vendor integration will need special-case branching in downstream processing.

That would increase:

- mapping complexity
- exception logic complexity
- VEE complexity
- completeness checks
- downstream reporting and billing coupling

The common raw layer should instead converge on the smallest business-meaningful unit that downstream processing can use consistently.

That does not mean source-local business time should be discarded.

The project should preserve both:

- a canonical interval timestamp suitable for cross-source processing and partitioning
- the original source-local business-time representation used by the upstream HES

## Recommended raw unit

For interval reads, the recommended common raw unit is:

- one meter
- one channel
- one interval start timestamp
- one interval value

This unit should be stored even when the upstream HES delivers the data in a larger block.

## Recommended persistence roles

### 1. Optional source block landing

Use a source-specific landing table when the upstream system emits a block row that contains multiple logical interval values.

Examples:

- `landing_lp_em_read_block`
- `landing_vendor_x_interval_block`

Purpose:

- preserve the original source row
- preserve source-specific layout
- support replay and re-expansion without polling the source again

### 2. Common raw interval table

Use the common raw layer to store one logical interval per row.

The existing project vocabulary can keep `hes_read_raw` as the common raw interval table as long as its contents remain vendor-neutral and interval-granular.

Recommended meaning:

- one row in `hes_read_raw` equals one interval read
- not one source block
- not one hour-wide packed row

Recommended time posture:

- `measured_at` should remain a canonical timestamp field
- source-local business time should remain preserved separately as source lineage

### 3. Completeness or window-state table

Use a separate table for missing-slot detection and collection completeness.

Recommended example:

- `raw_interval_window_state`

Purpose:

- track whether a meter or channel window is complete
- avoid using sparse source rows as the primary completeness mechanism
- support late-arrival and retry logic without mutating old raw rows excessively

## Why append-only interval rows are preferred

### Wide-row update model

If the source layout is copied directly into common raw, a 15-minute LP process usually behaves like:

1. insert the top-of-hour row at minute `00`
2. update the same row at minute `15`
3. update the same row at minute `30`
4. update the same row at minute `45`

At large scale this creates:

- repeated updates to the same logical row
- more write amplification
- more MVCC churn in PostgreSQL
- harder reasoning about late correction versus normal completion
- more complicated replay behavior

### Append-only interval model

If the common raw layer stores one interval per row, the same process becomes:

1. insert one row when the `00` interval is received
2. insert one row when the `15` interval is received
3. insert one row when the `30` interval is received
4. insert one row when the `45` interval is received

This is usually better for:

- auditability
- replay and idempotency design
- partitioning
- bulk ingest
- downstream processing simplicity

The row count is higher, but the write pattern is simpler and more stable.

## Recommended common raw columns

The exact schema may still evolve, but the common raw interval table should preserve at least:

- `ingest_batch_id`
- `adapter_instance_id`
- `adapter_run_id`
- `source_system`
- `source_table_name`
- `source_block_key`
- `source_record_key`
- `meter_source_id`
- `device_source_id`
- `channel_code`
- `interval_start_utc`
- `interval_minutes`
- `reading_value`
- `unit_of_measure`
- `quality_code`
- `status_code`
- `source_write_ts`
- `source_business_ts`
- `source_business_key`
- `source_timezone`
- `source_payload`
- `created_at`

Optional but useful:

- `source_row_version`
- `supersedes_raw_id`
- `lineage_details`

## Recommended time-model rule

The common raw layer should not replace `measured_at` with a source-local text field such as `YYYYMMDDHH` or `YYYYMMDDHHMM`.

Recommended rule:

- `measured_at`
  - canonical timestamp suitable for range queries, partitioning, and cross-source processing
- `source_business_key`
  - original source-local business-time text such as `YYYYMMDDHH` or `YYYYMMDDHHMM`
- `source_timezone`
  - explicit timezone used to interpret the source-local business-time text

Why:

- different countries may use different local timezones
- some countries may use DST-like local time behavior
- the raw layer still needs one unambiguous timestamp for internal processing
- the source-local business-time text still matters for audit, operator traceability, and source-side reconciliation

## Recommended completeness-state columns

The completeness table should focus on state, not measurement payload.

Recommended fields:

- `source_system`
- `meter_source_id`
- `channel_code`
- `window_start_utc`
- `window_size_minutes`
- `interval_minutes`
- `expected_slot_count`
- `received_slot_count`
- `received_slot_bitmap`
- `first_source_write_ts`
- `last_source_write_ts`
- `completion_status`
- `late_update_count`
- `details`

Recommended status examples:

- `open`
- `partial`
- `complete`
- `late_update`
- `superseded`

## Recommended completeness logic

Missing intervals should be detected by comparing:

- expected slots for a window
- received slots for a window

not by scanning wide source columns directly inside the common raw model.

This keeps completeness logic stable across:

- block-oriented HES sources
- row-oriented HES sources
- file-based delivery
- API-based delivery

## Handling late or corrected data

The common raw layer should prefer preserving late or corrected interval reads as new append-only rows with lineage, rather than mutating historical rows in place.

The completeness-state table can then mark the affected window as:

- still complete
- late-updated
- needing reprocessing

This is generally easier to audit than silently overwriting a previously ingested interval row.

## Implication for high meter counts

For fleets above one million meters, the raw model must optimize for:

- predictable inserts
- partitioning by time
- replay simplicity
- bounded reprocessing

The interval-row model usually supports those goals better than a hot-row update pattern copied from an upstream HES block table.

## Recommended baseline for this project

- keep vendor-specific packed rows in landing when needed
- treat `hes_read_raw` as interval-granular common raw
- add a dedicated completeness or window-state table instead of encoding completeness into raw row shape
- let processing and VEE operate on interval rows, not vendor-specific blocks

## Related documents

- [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
- [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
