# Domain Glossary

## Purpose

This glossary establishes consistent terminology for the project so that backlog, code, schema, and documentation use the same domain language.

## Core system terms

### HES

Head-End System. The upstream system that collects raw meter reads, events, alarms, and device communication outcomes.

### MDM

Meter Data Management. The system responsible for ingesting, validating, mapping, normalizing, and later processing metering data for downstream business use.

### Billing

The downstream system that consumes billing determinants or other bill-ready data produced from MDM-managed measurements.

### CIS

Customer Information System. The downstream or adjacent system that manages customer, contract, and service-related information.

## Minimal-stage data terms

### device

A physical or logical metering device identified by a source or enterprise identifier.

### service_point

The business location or service delivery point to which usage and device relationships are anchored.

### measuring_component

The channel or measurement-producing component associated with a device and service point.

### installation_history

The time-bounded record describing how a device is installed, moved, or removed relative to a service point.

### ingest_batch

The envelope-level persistence record for a set of incoming raw messages or records, including source metadata and lineage-supporting context.

### hes_read_raw

The raw read record received from HES before business-level transformation.

### hes_event_raw

The raw event or alarm record received from HES before broader downstream interpretation.

### canonical_measurement

The normalized internal measurement record created from validated and mapped raw reads.

### ingest_error_log

The minimal-stage error record for ingest validation and ingest persistence failures.

### landing layer

An optional source-specific layer used when incoming HES data cannot be mapped safely into the common raw model immediately.

### common raw layer

The earliest vendor-neutral raw layer in the MDM, intended to unify raw reads and events across compatible HES sources.

### adapter_definition

The persistent definition of a runtime adapter type or family, including delivery mode, supported record type, and implementation identity.

### adapter_instance

The persistent operational configuration of one real adapter connection or source endpoint managed by operators.

### adapter_run

The persistent execution record for one runtime adapter attempt, such as a scheduled poll or manual run.

### adapter_watermark

The persistent incremental cursor or resume point used by a runtime adapter to continue polling safely.

## Processing terms

### lineage

The traceable relationship from raw source data to transformed and downstream records.

### duplicate detection

The process of identifying repeated raw read submissions without deleting the original source record.

### mapping

The process of relating source identifiers such as meter or channel IDs to internal entities such as device, service point, and measuring component.

### normalization

The process of converting source-specific raw data into the internal canonical representation.

### well_formed

A semantic checkpoint, not necessarily a separate table, meaning the canonical measurement has the minimum structural integrity required to be promoted into a final business state.

## Later-phase terms

### initial_measurement

The first business-level measurement representation that is ready for VEE processing.

### final_measurement

The finalized business-level measurement record used for downstream usage and billing-oriented processing.

### VEE

Validation, Estimation, and Editing. The rule-driven process used to assess, correct, and finalize measurements.

### usage_transaction

The persisted result of calculating consumption or usage from final measurements.

### bill_determinant

A billing-oriented output value such as on-peak usage, off-peak usage, demand, or power factor.

## Language usage guidance

- Use the backlog-aligned persistent terms in schema and persistence discussions
- Use stable machine-readable codes for technical states and validation outcomes
- Avoid mixing interim scaffold names with target vocabulary in new documentation
- If English and Korean labels diverge for readability, keep the machine-readable concept stable underneath
