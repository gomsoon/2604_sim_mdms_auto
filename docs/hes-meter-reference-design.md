# HES Meter Reference Design

## Purpose

This document defines the minimal design direction for HES-side meter reference data.

The immediate goal is not to mirror a vendor `METER` table directly into the MDM core.

The goal is to:

- understand what useful source-side meter reference exists
- preserve a minimal useful subset when needed
- keep the MDM canonical master model independent from vendor-specific HES schemas

## Why this document matters

The MDM already depends on canonical meter-related master context:

- `service_point`
- `device`
- `measuring_component`
- `installation_history`

That internal context is required for:

- raw-to-canonical mapping
- exception handling
- reprocessing
- downstream usage and billing-oriented processing

At the same time, real HES platforms often hold source-side meter metadata that is operationally useful.

Examples:

- source meter identifiers
- LP interval settings
- meter status
- device model and meter type
- modem and location relationships

So the system needs both:

- canonical meter-related master in MDM
- and a clear place for HES-side source reference when it helps operations and mapping

## AIMIR `METER` table analysis summary

The current AIMIR HES `METER` table behaves like a source-side reference master, not like a direct canonical MDM model.

Observed characteristics:

- row count: about `324`
- PK: `ID`
- unique key: `MDS_ID`
- indexes confirmed:
  - unique on `ID`
  - unique on `MDS_ID`
  - non-unique on `MODEM_ID`
  - non-unique on `GS1`
- many foreign-key relationships to source-side reference tables such as:
  - `DEVICEMODEL_ID`
  - `ENDDEVICE_ID`
  - `LOCATION_ID`
  - `MODEM_ID`
  - `SUPPLIER_ID`
  - `METERTYPE_ID`
  - `METER_STATUS`
  - `DTS_ID`

It is also much wider than the MDM canonical master model and includes mixed concerns:

- source identity
- communication status
- physical and logical relationships
- interval and metering settings
- utility-specific extensions

Examples of useful columns seen in the AIMIR table:

- `ID`
- `MDS_ID`
- `METER`
- `METER_STATUS`
- `LP_INTERVAL`
- `METERTYPE_ID`
- `DEVICEMODEL_ID`
- `MODEM_ID`
- `LOCATION_ID`
- `SUPPLIER_ID`
- `LAST_READ_DATE`
- `WRITE_DATE`

The recent `LP_EM` smoke window also showed:

- `LP_EM.METER_ID -> METER.ID` matched all sampled rows
- `LP_EM.MDEV_ID -> METER.MDS_ID` matched all sampled rows

That makes `METER` operationally valuable for source tracing and mapping bootstrap even though it should not become the MDM canonical master model.

## Core design rule

Recommended rule:

- treat HES `METER` or equivalent tables as source-side meter reference
- do not treat them as the canonical master model of the MDM
- normalize only the needed subset into the internal canonical master context

This preserves long-term vendor neutrality while still allowing useful source-side comparison and synchronization.

## Recommended minimal split

### 1. Source-side meter reference

Purpose:

- preserve useful HES-side meter attributes
- support operator comparison and troubleshooting
- support mapping bootstrap
- support future sync and drift detection

### 2. Canonical MDM meter-related master

Purpose:

- remain the stable internal mapping target
- remain vendor-neutral
- support canonicalization and later business processing

Current canonical master tables:

- `service_point`
- `device`
- `measuring_component`
- `installation_history`

## Recommended minimal persistence baseline

### `hes_meter_reference`

Recommended purpose:

- persist one normalized source-side meter reference row per HES meter identity

Recommended columns:

- `id`
- `hes_system_id`
- `source_table_name`
- `source_meter_id`
- `source_meter_key`
- `meter_name`
- `meter_status_code`
- `lp_interval_minutes`
- `meter_type_code`
- `device_model_code`
- `modem_source_id`
- `location_source_id`
- `supplier_source_id`
- `last_read_at_text`
- `source_write_at_text`
- `source_payload`
- `last_synced_at`
- `created_at`
- `updated_at`

Recommended minimal rules:

- unique on `hes_system_id + source_meter_id`
- unique on `hes_system_id + source_meter_key` when `source_meter_key` is present
- keep the original source payload for traceability

### Column interpretation for AIMIR

Recommended first AIMIR mapping:

- `source_meter_id` <- `METER.ID`
- `source_meter_key` <- `METER.MDS_ID`
- `meter_name` <- `METER.METER`
- `meter_status_code` <- `METER.METER_STATUS`
- `lp_interval_minutes` <- `METER.LP_INTERVAL`
- `meter_type_code` <- `METER.METERTYPE_ID`
- `device_model_code` <- `METER.DEVICEMODEL_ID`
- `modem_source_id` <- `METER.MODEM_ID`
- `location_source_id` <- `METER.LOCATION_ID`
- `supplier_source_id` <- `METER.SUPPLIER_ID`
- `last_read_at_text` <- `METER.LAST_READ_DATE`
- `source_write_at_text` <- `METER.WRITE_DATE`
- `source_payload` <- selected raw snapshot or full source payload

## Relationship to current MDM master

`hes_meter_reference` should not replace:

- `device.external_meter_id`
- `service_point`
- `measuring_component`
- `installation_history`

Instead it should support them.

Useful first relationship patterns:

- compare `hes_meter_reference.source_meter_id` or `source_meter_key` with `device.external_meter_id`
- use `lp_interval_minutes` to validate source assumptions during ingest
- use status and model metadata for operator inspection

## What the minimal stage should not do yet

The minimal stage should not:

- mirror all `METER` columns into the MDM core model
- force a one-to-one semantic equivalence between HES `METER` and MDM `device`
- block current ingest or canonical mapping work on full meter-reference sync
- try to model every utility-specific extension in AIMIR now

## Recommended first implementation slice

1. persist a minimal `hes_meter_reference` table
2. load a minimal AIMIR subset into it
3. expose HES-side meter reference in HES detail or admin screens
4. use it for operator comparison and mapping bootstrap
5. later review whether deeper synchronization is needed

## Relationship to other documents

- [hes-system-management.md](/home/tprover/2604_sim_mdms_auto/docs/hes-system-management.md)
- [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
- [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
- [lp-em-adapter-mapping.md](/home/tprover/2604_sim_mdms_auto/docs/lp-em-adapter-mapping.md)
- [backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md)
