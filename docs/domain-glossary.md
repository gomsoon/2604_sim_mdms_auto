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

### HES meter reference

Source-side meter metadata held by an upstream HES, such as source meter identifiers, interval settings, source status, or vendor-specific meter attributes.

This is useful for source operations and mapping bootstrap, but it is not the same thing as the MDM canonical master model.

### hes_meter_reference

The proposed persistent normalized record used by MDM to store a minimal synchronized subset of HES-side meter reference data for operator comparison, tracing, and mapping support.

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

### hes_system

The persistent operator-managed representation of one upstream HES, used as the parent source object above one or more runtime adapters and as a stable lineage anchor for batches and raw records.

### adapter_definition

The persistent definition of a runtime adapter type or family, including delivery mode, supported record type, and implementation identity.

### adapter_instance

The persistent operational configuration of one real adapter connection or source endpoint managed by operators.

### adapter_run

The persistent execution record for one runtime adapter attempt, such as a scheduled poll or manual run.

### adapter_watermark

The persistent incremental cursor or resume point used by a runtime adapter to continue polling safely.

### operational_event

The operator-facing durable timeline record that captures important integration, ingest, processing, and system milestones, with alert state represented as a subset of those events.

## Processing terms

### lineage

The traceable relationship from raw source data to transformed and downstream records.

### duplicate detection

The process of identifying repeated raw read submissions without deleting the original source record.

### mapping

The process of relating source identifiers such as meter or channel IDs to internal entities such as device, service point, and measuring component.

### canonical meter-related master

The normalized internal master context used by the MDM to map and process measurements, represented in the current project by `service_point`, `device`, `measuring_component`, and `installation_history`.

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

### vee_execution_log

The persistent trace of one VEE execution attempt, including scope, timing, and result.

### vee_exception

The persistent operator-facing record of a VEE-stage abnormality that blocks or conditions finalization.

### usage_transaction

The persisted result of calculating consumption or usage from final measurements.

### bill_determinant

A billing-ready output value derived from `usage_transaction`, such as billing-cycle
consumption total, on-peak usage, off-peak usage, demand, or power factor.

### billing-lite

An optional narrow billing slice hosted inside MDM for small-scale deployment or
end-to-end testing. It may calculate charges or invoice summaries from
`bill_determinant`, but it is not intended to replace a full CIS or enterprise
billing platform.

### billing context

The minimal business context needed to align billing-ready or charge-ready
outputs, such as billing timezone, billing-cycle mode, anchor day, and
effective period.

### service_point_billing_context

The proposed current-plus-history business context record attached to a
`service_point`, used to define billing timezone and billing-cycle alignment
before later charge calculation.

### tariff assignment

The minimal business context that states which tariff plan should apply to a
`service_point` during a given effective period.

### service_point_tariff_assignment

The proposed current-plus-history tariff assignment record attached to a
`service_point`, intended to support later `bill_charge` calculation without
forcing the first determinant baseline to depend on tariff lookup.

### bill_charge

A charge-ready output value derived from `bill_determinant`, typically after
applying a minimal tariff or rate rule plus tariff-assignment context.

### charge-ready

The state in which downstream outputs are suitable for tariff-based charge
calculation, typically after `bill_determinant` plus explicit billing and
tariff context have been applied.

### invoice_summary

A lightweight aggregated billing output that groups one or more bill charges for
operator review or simple export, without implying a full receivables or
customer-accounting workflow.

### billing-ready

The state in which downstream outputs are suitable for billing-oriented use, typically after usage calculation and determinant generation rather than immediately after finalization.

## Language usage guidance

- Use the backlog-aligned persistent terms in schema and persistence discussions
- Use stable machine-readable codes for technical states and validation outcomes
- Avoid mixing interim scaffold names with target vocabulary in new documentation
- If English and Korean labels diverge for readability, keep the machine-readable concept stable underneath
