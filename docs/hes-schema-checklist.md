# HES Schema Checklist

## Purpose

This document is a practical checklist for reviewing the company's HES database schema before designing the MDM minimal-stage raw tables.

## Why this checklist matters

- We do not need a broad market survey to start the minimal MDM
- We do need a disciplined review of the actual HES schema that will feed the MDM
- The raw table design should reflect real source structures, not only abstract backlog assumptions

## Intended output of this checklist

After completing this checklist, the team should be able to define:

- the first `hes_read_raw` table shape
- the first `hes_event_raw` table shape
- the first `ingest_batch` metadata requirements
- the minimal mapping requirements for `device`, `service_point`, `measuring_component`, and `installation_history`

## Recommended source artifacts to collect

Collect as many of the following as possible from the HES side:

- table DDL
- column list with data types
- primary keys and unique keys
- foreign key relationships, if they exist
- indexes
- sample rows for reads
- sample rows for events or alarms
- code tables for status, quality, event code, or alarm severity
- data retention policy
- expected daily or monthly volume

If only part of the schema is available at first, begin with the read-related tables and add the rest later.

## Checklist 1. HES table inventory

Identify which tables contain the following information:

- raw meter reads
- raw interval reads
- scalar reads
- events
- alarms
- device master
- meter identifier history
- channel information
- installation or deployment history
- service-point-like business location reference
- batch or collection job metadata

For each candidate table, capture:

| Item | Notes |
| --- | --- |
| Table name |  |
| Business purpose |  |
| Insert/update pattern |  |
| Expected record volume |  |
| Retention expectation |  |
| Relevant to minimal stage | Yes / No |

## Checklist 2. Raw read table review

For the HES read source table, confirm whether the following information exists and how it is represented:

| Source concept | Present | HES table.column | Notes |
| --- | --- | --- | --- |
| source meter identifier |  |  |  |
| source channel identifier |  |  |  |
| measurement timestamp |  |  |  |
| receive timestamp |  |  |  |
| read value |  |  |  |
| unit of measure |  |  |  |
| interval size |  |  |  |
| scalar vs interval flag |  |  |  |
| quality code |  |  |  |
| status code |  |  |  |
| multiplier |  |  |  |
| source file or batch reference |  |  |  |
| created timestamp |  |  |  |
| updated timestamp |  |  |  |
| delete flag or invalid flag |  |  |  |
| raw payload reconstruction possibility |  |  |  |

## Checklist 3. Event or alarm table review

For the HES event source table, confirm whether the following information exists:

| Source concept | Present | HES table.column | Notes |
| --- | --- | --- | --- |
| source meter identifier |  |  |  |
| event timestamp |  |  |  |
| receive timestamp |  |  |  |
| event code |  |  |  |
| event severity |  |  |  |
| event source |  |  |  |
| event status |  |  |  |
| source batch or message reference |  |  |  |
| raw payload reconstruction possibility |  |  |  |

## Checklist 4. Key and uniqueness review

Understand how the HES currently identifies uniqueness.

- What is the primary key of the read table
- Is the primary key business-meaningful or surrogate only
- Can two rows exist for the same `meter + channel + timestamp`
- Is late-arriving correction stored as update or new row
- Is duplicate delivery visible in the source schema
- Is there a batch/job identifier that can serve as ingest trace context

Document answers:

| Question | Answer |
| --- | --- |
| Read table PK |  |
| Event table PK |  |
| Duplicate strategy in HES |  |
| Update vs append behavior |  |
| Batch trace field |  |

## Checklist 5. Time handling review

Time handling is one of the most important areas for AMI/MDM correctness.

Confirm the following:

- timestamp data type
- timezone storage behavior
- whether stored timestamps are UTC or local time
- whether daylight saving time is relevant
- whether interval boundaries are inclusive or exclusive
- whether interval size is explicit or inferred
- whether missing intervals are represented as absent rows or flagged rows

Document findings:

| Time concern | Answer |
| --- | --- |
| Timestamp type |  |
| Stored timezone convention |  |
| Interval size rule |  |
| DST relevance |  |
| Missing interval representation |  |

## Checklist 6. Quality and status semantics

We should not assume that HES quality codes map cleanly into MDM statuses without review.

Confirm:

- all quality codes used by HES
- all status codes used by HES
- whether codes are documented
- whether codes are stable across time
- whether codes differ by meter type or source interface

Capture code mapping notes:

| Code family | HES value | Meaning | Candidate MDM handling |
| --- | --- | --- | --- |
| quality |  |  |  |
| status |  |  |  |
| event |  |  |  |

## Checklist 7. Master-data linkage review

The raw tables alone are not enough. We also need to know how HES identifiers connect to business objects.

Confirm whether the HES schema exposes or can derive:

- meter-to-device identity
- meter-to-channel identity
- device-to-service-point relation
- installation start and end timestamps
- meter replacement history
- multiplier history

Document source linkage:

| Linkage need | Available | HES source | Notes |
| --- | --- | --- | --- |
| meter to device |  |  |  |
| meter to service point |  |  |  |
| meter to channel |  |  |  |
| installation history |  |  |  |
| replacement history |  |  |  |
| multiplier history |  |  |  |

## Checklist 8. Operational ingest behavior

Minimal-stage raw table design should reflect actual operational behavior.

Confirm:

- How often HES data is delivered
- Whether delivery is batch or near-real-time
- Whether re-send is common
- Whether backfill is common
- Whether partial-day arrival is common
- Whether raw source rows are updated after initial insert
- Whether source deletes happen

Document operational facts:

| Operational concern | Answer |
| --- | --- |
| Delivery mode |  |
| Delivery frequency |  |
| Re-send behavior |  |
| Backfill behavior |  |
| Source update behavior |  |
| Source delete behavior |  |

## Checklist 9. Raw table derivation for MDM

After reviewing the HES schema, map HES columns to minimal MDM raw tables.

### Target: `hes_read_raw`

| MDM raw field | HES source | Required | Notes |
| --- | --- | --- | --- |
| source_system |  | Yes |  |
| source_table_name |  | Recommended |  |
| source_record_id |  | Recommended |  |
| batch_id |  | Conditional |  |
| message_id |  | Conditional |  |
| meter_id |  | Yes |  |
| channel_id |  | Yes |  |
| measurement_ts |  | Yes |  |
| received_at |  | Recommended |  |
| value |  | Yes |  |
| unit_of_measure |  | Recommended |  |
| interval_size_minutes |  | Recommended |  |
| quality_code |  | No |  |
| status_code |  | No |  |
| multiplier |  | No |  |
| source_payload |  | Recommended |  |

### Target: `hes_event_raw`

| MDM raw field | HES source | Required | Notes |
| --- | --- | --- | --- |
| source_system |  | Yes |  |
| source_table_name |  | Recommended |  |
| source_record_id |  | Recommended |  |
| batch_id |  | Conditional |  |
| message_id |  | Conditional |  |
| meter_id |  | Recommended |  |
| event_ts |  | Yes |  |
| received_at |  | Recommended |  |
| event_code |  | Yes |  |
| severity |  | No |  |
| event_source |  | No |  |
| status_code |  | No |  |
| source_payload |  | Recommended |  |

## Checklist 10. Questions to resolve before raw table DDL is finalized

- Do we need to preserve the original HES primary key in the raw table
- Do we need one raw table per read type or one unified raw read table
- Should the initial minimal stage store full JSON payload or reconstructed column-level payload only
- Which HES timestamps are authoritative for lineage and deduplication
- Which HES fields are stable enough to use as unique constraints or idempotency keys

## Ready-to-design gate

We are ready to design the first MDM raw tables only when:

- We know which HES tables are the raw read and raw event sources
- We know the key timestamp fields
- We know the source identifiers used for meter and channel
- We understand how duplicates and re-sends appear in HES
- We know how HES quality and status codes behave
- We know the minimum master-data linkage required for mapping

## What to provide next

When you share the company HES schema, the most useful starting formats are:

- `CREATE TABLE` DDL
- column list with data types
- sample `SELECT` results with sensitive values masked
- code tables or code descriptions for quality/status/event fields

Once you provide that, we can turn this checklist into:

1. HES-to-MDM source mapping
2. first `hes_read_raw` and `hes_event_raw` DDL
3. initial `ingest_batch` design
4. gap notes for master-data linkage

