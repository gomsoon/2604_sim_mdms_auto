# LP_EM Adapter Mapping

## Purpose

This document defines the current mapping baseline for the overseas HES `LP_EM` table into the MDM landing and common raw layers.

It is intentionally written as an adapter-focused design document rather than as a full HES schema document.

## Source role

Current interpretation:

- `LP_EM` is the source read block table
- `METER` is the source meter reference table

`LP_EM` should be treated as the upstream interval-read source, and `METER` should be treated as a master or reference table used by the adapter to enrich and validate source rows.

## Current observed facts

From the inspected overseas HES environment:

- `LP_EM` is large and operationally significant
- `METER` is small and behaves like a master table
- `LP_EM.METER_ID` joins to `METER.ID`
- `LP_EM.MDEV_ID` matches `METER.MDS_ID`
- `LP_EM.LOCATION_ID` matches `METER.LOCATION_ID` in the inspected sample
- `LP_EM.SUPPLIER_ID` matches `METER.SUPPLIER_ID` in the inspected sample
- `LP_EM.YYYYMMDDHH` and `LP_EM.HH` were consistent in the inspected recent sample

## Current source-row interpretation

The current interpretation of one `LP_EM` row is:

- one source meter
- one source hour identified by `YYYYMMDDHH`
- one source channel identified by `CHANNEL`
- one source block containing up to sixty slot columns

Examples:

- `VALUE_00`
- `VALUE_01`
- ...
- `VALUE_59`

This means one source row may expand into multiple common raw interval rows.

## Recommended adapter stages

### Stage 1. Read source block

Read one `LP_EM` row as a source block.

Preserve at least:

- `METER_ID`
- `DEVICE_ID`
- `MDEV_ID`
- `MDEV_TYPE`
- `YYYYMMDDHH`
- `HH`
- `WRITEDATE`
- `CHANNEL`
- `VALUE_CNT`
- `VALUE`
- `VALUE_00` through `VALUE_59`
- `LOCATION_ID`
- `SUPPLIER_ID`
- `ENDDEVICE_ID`

### Stage 2. Optional landing persistence

If the adapter path uses landing, persist the original source block with a stable source-block key.

Recommended source-block key candidate:

- `LP_EM|METER_ID|YYYYMMDDHH|CHANNEL|WRITEDATE`

This is not guaranteed to be a true source primary key, but it is a practical first replay key.

### Stage 3. Expand block into interval rows

For each non-null `VALUE_nn` column:

- derive one interval row
- preserve lineage back to the source block

## Recommended time mapping

### Base hour

`YYYYMMDDHH` should be parsed as the base source hour.

The adapter configuration should define the source timezone explicitly.

For the current AIMIR HES interpretation:

- `YYYYMMDDHH` is the source-local business hour
- `WRITEDATE` is the source write or arrival time
- `HH` is only the hour component and should not be treated as a full measurement timestamp

### Slot interpretation

Recommended baseline:

- treat `VALUE_00` through `VALUE_59` as minute-offset slots within the source hour

Meaning:

- `VALUE_00` maps to minute offset `0`
- `VALUE_15` maps to minute offset `15`
- `VALUE_30` maps to minute offset `30`
- `VALUE_45` maps to minute offset `45`

This is the most natural interpretation for the current column naming.

### Interval length

The adapter should determine interval length in this order:

1. `METER.LP_INTERVAL` when present and trusted
2. adapter instance default
3. source-family fallback

For the inspected recent sample:

- `METER.LP_INTERVAL = 60`
- `VALUE_CNT = 1`
- only `VALUE_00` was populated

That is consistent with hourly collection for the sampled recent data.

## Recommended common raw mapping

Suggested target semantics per expanded row:

- `source_system` = configured HES source name
- `source_table_name` = `LP_EM`
- `source_block_key` = derived block key
- `meter_source_id` = `LP_EM.METER_ID`
- `device_source_id` = `LP_EM.DEVICE_ID`
- `channel_code` = `LP_EM.CHANNEL`
- `measured_at` = parsed `YYYYMMDDHH` plus slot offset interpreted in the configured source timezone
- `interval_start_utc` = canonical UTC or timestamptz representation derived from `measured_at`
- `interval_minutes` = derived interval length
- `reading_value` = `VALUE_nn`
- `quality_code` = adapter-mapped value or null when unavailable
- `status_code` = adapter-mapped value or null when unavailable
- `source_write_ts` = parsed `WRITEDATE` when available
- `source_business_ts` = parsed `YYYYMMDDHH`
- `source_business_key` = original `YYYYMMDDHH`
- `source_timezone` = configured source timezone
- `source_payload` = original `LP_EM` row payload

Preserve source-block-level fields inside payload even when they do not become top-level raw columns.

Examples:

- `VALUE`
- `VALUE_CNT`
- `MDEV_TYPE`
- `ENDDEVICE_ID`

## Recommended use of METER enrichment

The adapter should use `METER` primarily for:

- validation of `METER_ID`
- enrichment of `MDS_ID`
- interval-length derivation from `LP_INTERVAL`
- source-side location and supplier cross-checks

The adapter should not assume that every future HES source will provide the same exact master table shape.

## Recommended channel handling

The current adapter should preserve `CHANNEL` as a source-native numeric channel code.

Do not over-normalize channel semantics too early.

Recommended baseline:

- keep raw `CHANNEL` value
- add a later source-channel mapping table when business meaning is confirmed

This is safer than inventing a semantic channel model too early.

## Recommended dedupe baseline

For the current `LP_EM` adapter, a practical raw dedupe candidate is:

- `source_system`
- `METER_ID`
- `CHANNEL`
- derived interval start
- `WRITEDATE`

However, the adapter should preserve source lineage even if a later correction arrives for the same logical interval.

That means:

- append-only raw persistence is preferred
- late rows should be tracked as newer source evidence
- downstream processing can decide whether a later source row supersedes an earlier one

## Recommended completeness-state update

When the adapter expands a source block into interval rows, it should also update the completeness window for:

- `METER_ID`
- `CHANNEL`
- source hour window

For `LP_EM`, the natural window anchor is:

- the base hour from `YYYYMMDDHH`

The completeness logic should mark which slot offsets were received.

## Current recent-sample observations

The recent sample already indicates a stable pattern:

- full join success from `LP_EM` to `METER`
- `VALUE_CNT = 1`
- one populated slot per row
- channels repeated consistently per meter-hour
- no duplicate `(METER_ID, YYYYMMDDHH, CHANNEL)` keys in the inspected recent sample

## Current time interpretation decision

For the current AIMIR HES source:

- use `YYYYMMDDHH` as the basis for `measured_at`
- use `WRITEDATE` as the basis for `source_write_ts`
- preserve the original local business-hour string as source lineage rather than replacing `measured_at` with text

These observations are strong enough to support the first adapter baseline, but they should still be treated as source observations, not as global guarantees.

## Open questions

- whether all deployments use the same `CHANNEL` semantics
- whether older or different data periods populate multiple slot columns per row
- whether `WRITEDATE` is the best extraction watermark in every environment
- whether late corrections can produce repeated logical interval keys with newer source write time

## Recommended first implementation boundary

The first `LP_EM` adapter should:

- poll `LP_EM`
- enrich from `METER`
- optionally persist source blocks to landing
- expand non-null `VALUE_nn` slots into interval-level common raw rows
- update completeness state by source hour

It should not initially try to:

- infer business channel meaning automatically
- normalize every possible source column into master data
- solve every historical data-shape variation before a first working path exists

## Related documents

- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
