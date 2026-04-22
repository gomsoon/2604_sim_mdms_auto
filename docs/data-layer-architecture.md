# Data Layer Architecture

## Purpose

This document defines the intended data-layer structure for the MDM system, with emphasis on how HES-originated data moves from source-specific formats to bill-ready standardized outputs.

## Core principle

Input may vary by HES vendor, but the MDM internal model should converge to a common structure as early as possible.

In short:

- receive input flexibly
- standardize early
- preserve lineage throughout
- keep final business data vendor-neutral

## Recommended layer model

### 1. Landing layer

Purpose:

- accept source-specific payloads that cannot be mapped safely into the common raw shape immediately
- preserve vendor-specific details without forcing premature normalization

Characteristics:

- optional layer, not mandatory for every source
- used only when source data cannot go directly into the common raw model
- may be vendor-specific
- should preserve the original payload or source row structure as closely as practical

Examples:

- `landing_vendor_a_read`
- `landing_vendor_b_event`

When to use:

- external HES structure differs significantly from the common raw contract
- source meaning is not fully clear at ingest time
- raw payload must be preserved before transformation
- source-specific parsing or reconstruction is required

When not to use:

- source data already fits the common raw model well enough
- our own HES can provide the needed core fields directly

### 2. Common raw layer

Purpose:

- create a unified raw layer for all HES sources
- establish a stable source-of-truth shape for downstream MDM processing

Characteristics:

- mandatory layer
- should be common across vendors
- should preserve traceability back to source system, source table, source record, and payload
- should support direct ingest from our own HES and compatible external HES sources

Core tables:

- `ingest_batch`
- `hes_read_raw`
- `hes_event_raw`
- `ingest_error_log`

Common master context that the raw layer depends on:

- `service_point`
- `device`
- `measuring_component`
- `installation_history`

Key rule:

Even if there are multiple HES vendors, the MDM should avoid vendor-specific branching after the common raw layer unless absolutely necessary.

Additional rule:

- the common raw read model should converge to interval-granular append-only rows, not packed vendor-specific block rows

Related document:

- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)

### 3. Canonical or initial business layer

Purpose:

- normalize common raw records into the internal measurement structure that business logic can use

Characteristics:

- vendor-neutral
- focused on internal consistency
- serves as the bridge between raw ingest and VEE/business processing

Examples:

- `canonical_measurement`
- later `initial_measurement`

Key rule:

By this point, downstream logic should not need to care which HES vendor originated the data.

### 4. VEE, exception, and audit layer

Purpose:

- support validation, estimation, editing, operator review, and traceability

Characteristics:

- business-processing-oriented staging area
- preserves data-quality decisions and intervention history
- must be auditable

Examples:

- `vee_execution_log`
- `vee_exception`
- `estimation_audit`
- `manual_edit_audit`

Key rule:

This layer is where abnormal data is evaluated, adjusted, or flagged before becoming final.

### 5. Final layer

Purpose:

- store the finalized standardized measurements suitable for downstream business use

Characteristics:

- vendor-neutral
- versioned if necessary
- operationally authoritative for downstream usage calculation

Examples:

- `final_measurement`

Key rule:

No vendor-specific raw semantics should leak into the final layer.

### 6. Billing-ready and downstream layer

Purpose:

- convert finalized measurements into outputs needed by billing, CIS, analytics, and reporting

Examples:

- `usage_transaction`
- `bill_determinant`

Key rule:

Downstream systems should consume standardized business outputs, not source-specific raw records.

## HES meter reference vs canonical MDM master

The project should distinguish between two kinds of meter-related data:

### HES-side meter reference

Examples:

- vendor `METER` tables
- interval settings
- source meter status
- source device model or meter type
- source channel definitions

These are source-oriented reference structures.

They may need to be ingested or synchronized because they help:

- adapter configuration
- source-side troubleshooting
- mapping bootstrap
- operator comparison between HES and MDM

### Canonical MDM meter-related master

Examples:

- `service_point`
- `device`
- `measuring_component`
- `installation_history`

These are the internal normalized master structures that MDM processing should depend on.

Recommended rule:

- do not treat an HES vendor `METER` table as the canonical master model of the MDM
- ingest HES meter reference only as source reference data
- normalize the needed subset into MDM canonical master structures

This distinction matters because more HES sources are expected over time, while the internal mapping and processing core should stay vendor-neutral.

## Recommended source handling policy

### Case 1. Our own HES

Recommended path:

- integration adapter normalizes field aliases if needed
- direct ingest into the common raw layer

Why:

- we can shape the integration more predictably
- unnecessary landing complexity should be avoided

### Case 2. External HES with compatible structure

Recommended path:

- integration adapter normalizes field aliases if needed
- direct ingest into the common raw layer

Why:

- if the source can be mapped cleanly into the common raw contract, a separate landing table adds needless operational cost

### Case 3. External HES with incompatible or unclear structure

Recommended path:

- vendor-specific landing layer first
- then transformation into the common raw layer

Why:

- this preserves source fidelity and allows controlled normalization before business logic depends on the data
- it allows packed source blocks such as hourly rows with multiple slot columns to remain source-specific while the MDM common raw model stays stable

## Integration adapter note

Before data reaches the common raw layer, the integration layer may apply a lightweight ingest adapter profile.

Purpose:

- map source-specific field names to the common raw contract
- preserve the original payload while normalizing only the fields needed for raw persistence
- avoid polluting downstream raw, canonical, and processing logic with source-specific branching

Recommended rule:

- use an adapter profile when the source can still go directly to common raw after field normalization
- use a landing layer when field normalization alone is not enough to make the source safe for common raw ingest

## Architectural rule for vendor variance

- vendor-specific variation is allowed before the common raw layer
- vendor-specific variation should be minimized after the common raw layer
- final business tables must remain common and standardized

This rule is critical for long-term maintainability.

## Why not create vendor-specific raw and staging layers everywhere

If vendor-specific tables continue upward through the pipeline, the system will eventually suffer from:

- duplicated logic
- inconsistent VEE behavior
- harder auditing
- more difficult reporting
- more expensive onboarding of each new source

For that reason, the design should normalize into common raw as early as practical.

## Experimental and validation needs

The project may still need temporary or experimental processing areas during development or validation.

Recommended approach:

- use `run_id`, `scenario_id`, or similar processing identifiers
- use separate schema or sandbox structures for experiments when needed
- avoid uncontrolled growth of permanent vendor-specific staging tables in operational paths

This makes experimentation possible without destabilizing the core model.

## Relationship to staging

The word `staging` can mean two different things, and they should not be confused.

### Technical staging

- source-specific or ingest-oriented holding area
- usually landing-related
- focused on safe intake and transformation

### Business staging

- post-raw processing area used for VEE, estimation, correction, and approval
- focused on data-quality and business readiness

The design should treat these as distinct concerns.

## Minimal-stage recommendation

For the current phase, the recommended model is:

- our HES goes directly to the common raw layer
- compatible external HES sources also go directly to the common raw layer
- packed or block-oriented external HES sources should use landing first and then expand into interval-granular common raw rows
- incompatible external HES sources use a landing layer first
- common raw then flows into canonical measurement
- later phases add `initial_measurement`, VEE, final, usage, and bill determinant layers

## Related documents

- [provisional-raw-schema.md](/home/tprover/2604_sim_mdms_auto/docs/provisional-raw-schema.md)
- [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)
- [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)
- [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
