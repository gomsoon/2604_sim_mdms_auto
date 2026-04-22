# Operator Workflows

## Purpose

This document describes the expected minimal-stage operator workflows so that UI design, API shape, error handling, and acceptance testing all reflect realistic usage.

## Primary operator roles in the minimal stage

### Data operations operator

Responsible for monitoring ingest results, reviewing raw data, and confirming that source-to-canonical flow is functioning.

### Master data operator

Responsible for maintaining device, service point, measuring component, and installation relationships needed for correct mapping.

### Technical support operator

Responsible for diagnosing ingest failures, unresolved mappings, and environment or connectivity issues.

## Workflow 1. Bring the system online

### Goal

Confirm that the service and PostgreSQL environment are available before ingest begins.

### Typical steps

1. Start or verify PostgreSQL availability
2. Confirm application configuration is pointed at the intended environment
3. Start the application
4. Call the health endpoint
5. Confirm logs show expected connectivity state

### Expected operator outcome

- The operator knows whether the environment is ready for ingest
- Basic environment failures can be diagnosed before data is loaded

## Workflow 1A. Monitor or control runtime adapters

### Goal

Confirm that each runtime adapter is in an expected operational state before relying on upstream collection.

### Typical steps

1. Open the adapter operations screen
2. Confirm whether each adapter is `ready`, `running`, `paused`, or `error`
3. Review the latest success or failure summary
4. Pause an unstable adapter when needed
5. Run an adapter once manually when validation is needed
6. Review recent adapter runs when troubleshooting is required

### Expected operator outcome

- The operator can distinguish configuration intent from runtime behavior
- The operator can stop scheduled collection safely without deleting the adapter instance
- The operator can validate one adapter without changing the whole system state

## Workflow 1A-1. Register and manage HES systems

### Goal

Treat the upstream HES itself as the stable operating object above runtime adapters.

### Typical steps

1. Open the HES management screen
2. Register a new HES or open an existing HES
3. Review HES metadata, timezone, delivery mode, and masked connection context
4. Attach one or more runtime adapters under that HES
5. Use the HES detail page to inspect linked adapters, recent batches, and open alerts

### Expected operator outcome

- The operator can distinguish the upstream HES identity from the runtime adapter identity
- One HES can own more than one adapter without confusion
- Source lineage can be traced by HES as well as by adapter

## Workflow 1B. Review operational events and alerts

### Goal

Understand recent system behavior quickly and identify conditions that need operator action now.

### Typical steps

1. Open the dashboard
2. Review open alerts first
3. Review the recent event timeline below the summary cards
4. Filter the event or alert history by severity, adapter, batch, meter, or date range
5. Drill into the related adapter, batch, exception, or pipeline detail when needed

### Expected operator outcome

- The operator can distinguish routine lifecycle activity from actionable failures
- The operator can identify where the current issue sits in the end-to-end flow
- The operator can react before needing direct log access

## Workflow 2. Register or confirm master data

### Goal

Ensure the system can map incoming HES identifiers to internal records.

### Typical steps

1. Create or review `device`
2. Create or review `service_point`
3. Create or review `measuring_component`
4. Create or review `installation_history`
5. Confirm that meter and channel identifiers match expected HES payloads

### Expected operator outcome

- Known HES identifiers can be mapped successfully
- Missing or inconsistent master data is visible before large ingest runs

## Workflow 3. Ingest raw HES reads

### Goal

Load raw HES read payloads and verify that ingest succeeds without losing source fidelity.

### Typical steps

1. Submit read ingest payload or batch file
2. Confirm `ingest_batch` was created
3. Review `hes_read_raw` records
4. Review any `ingest_error_log` entries
5. Confirm original payload preservation

### Expected operator outcome

- Valid raw reads are stored
- Invalid raw reads are visible through ingest errors rather than silently lost

## Workflow 4. Ingest raw HES events

### Goal

Load raw HES event payloads so future logic can use event context.

### Typical steps

1. Submit event ingest payload
2. Confirm `ingest_batch` was created
3. Review `hes_event_raw` records
4. Review `ingest_error_log` for invalid event records

### Expected operator outcome

- Valid events are stored for future use
- Invalid events are visible without affecting valid records unnecessarily

## Workflow 5. Review unresolved mappings or ingest failures

### Goal

Identify why some raw records did not proceed successfully into the intended flow.

### Typical steps

1. Open ingest or error visibility screens
2. Filter by batch, meter, or time range
3. Inspect missing-field or invalid-format failures
4. Inspect unresolved meter or channel mapping failures
5. Determine whether master data correction or payload correction is needed

### Expected operator outcome

- The operator can distinguish ingest failure from mapping failure
- The operator can identify the next corrective action

## Workflow 6. Confirm canonical conversion

### Goal

Verify that valid, mapped raw reads have become canonical measurements with lineage.

### Typical steps

1. Query recent `hes_read_raw` records
2. Query corresponding `canonical_measurement` records
3. Confirm device, measuring component, and timestamp were carried through
4. Confirm raw-to-canonical lineage exists

### Expected operator outcome

- The operator can confirm the minimal end-to-end flow is actually working
- The operator can prove the system is producing downstream-ready normalized data

## Workflow 7. Inspect by batch or meter

### Goal

Use operational filters to trace ingest behavior for a specific delivery or source identifier.

### Typical steps

1. Filter by `batch_id`
2. Filter by meter identifier
3. Filter by date range
4. Compare raw, event, canonical, and error results

### Expected operator outcome

- Operators can troubleshoot a single ingest delivery without scanning all data
- Lineage can be verified within a bounded operational context

## Master data maintenance expectations

The minimal stage should support at least the following operator questions:

- Which device does this HES meter ID belong to
- Which service point is this device installed at
- Which channel does this raw read belong to
- Was the device actively installed at the measurement timestamp

If the system cannot answer these clearly, mapping quality will remain weak.

## Operator-facing UI expectations

Minimal-stage screens should help operators complete the workflows above with as little ambiguity as possible.

- Dashboard for current ingest and canonical status
- Future adapter operations view for runtime integration control
- Dashboard cards at the top showing `ready`, `running`, `paused`, and `error` counts for integration plus `waiting`, `processing`, `completed`, and `failed` counts by major processing stage
- Recent operational event and alert timeline on the dashboard
- Raw read visibility
- Raw event visibility
- Error visibility
- Master-data visibility
- Batch and meter filters
- English and Korean support for visible labels and notices

## Error-handling expectations from the operator perspective

- Ingest failures must be explicit and reviewable
- Missing master data must be distinguishable from malformed payload issues
- Duplicate conditions must not erase the original record
- Operators should be able to tell whether the next action is data correction, master-data correction, or environment correction

## Logging and observability expectations

Operators and support staff should be able to answer these questions quickly:

- Did the batch arrive
- Did the server accept it
- Were records written to raw tables
- Were invalid records logged
- Did canonical conversion happen
- If not, where did the flow stop

The dashboard should answer these questions first through summary cards before the operator needs to inspect detailed tables.

The recent event and alert timeline should then explain what happened recently and which condition now requires operator attention.

## Relationship to acceptance testing

Each workflow in this document should map to at least one integration or functional verification path in [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md).

## Minimal-stage definition of success

The operator workflow is minimally acceptable only when:

- Operators can bring the system online
- Operators can maintain enough master data to enable mapping
- Operators can ingest raw reads and events
- Operators can review failures clearly
- Operators can verify canonical conversion and lineage
- Operators can see recent important events and current alerts without log inspection
- Operators can do the above in English and Korean without structural redesign
