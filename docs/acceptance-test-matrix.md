# Acceptance Test Matrix

## Purpose

This document maps minimal-stage backlog items to concrete test intent so that implementation, acceptance criteria, and regression coverage stay aligned.

## How to use this matrix

- Use this document before feature implementation to understand expected verification scope
- Use this document while writing tests to derive unit, integration, and functional coverage
- Use this document during regression review to confirm that adjacent flows were re-tested

## Test legend

- `U`: unit test with `pytest`
- `I`: integration or API test with `pytest`
- `F`: functional or browser-driven test, manual smoke at minimum and `Playwright` when automation is available

## Minimal-stage matrix

| Backlog item | Capability | Acceptance focus | Boundary cases to verify | Recommended test layers |
| --- | --- | --- | --- | --- |
| `M1` | App skeleton and health check | App boots, health endpoint responds, DB connectivity is observable | Missing env vars, invalid `DATABASE_URL`, DB unavailable, health request method mismatch | `I`, `F` |
| `M2` | Core schema creation | Minimal schema exists in PostgreSQL and preserves raw vs canonical separation | Empty database, repeated setup, missing tables, lineage foreign key integrity | `I` |
| `M3` | Raw read ingest | Accept valid HES read payload, preserve raw payload, log ingest errors | Empty payload, single read, multiple reads, missing required fields, malformed timestamp, duplicate read envelope | `U`, `I` |
| `M3` | Raw event ingest | Accept valid HES event payload and persist event-level metadata | Empty event list, missing `event_code`, malformed `event_ts`, unsupported locale, duplicate envelope | `U`, `I` |
| `M4` | Master data mapping | Device, service point, component, and installation data support mapping | Known mapping, unknown meter, unknown channel, overlapping installation window, no active installation | `U`, `I` |
| `M5` | Canonical conversion | Valid raw read becomes canonical measurement with lineage | Valid source, mapping failure, duplicate read, missing UOM, timestamp normalization edge, mixed source types | `U`, `I` |
| `M6` | Visibility APIs and UI | Operators can inspect ingest, canonical, event, and alert outcomes with filters and lineage | Empty result set, large batch filter, unknown meter filter, invalid date range, locale-sensitive messages, no open alerts vs multiple open alerts | `I`, `F` |

## Detailed verification scenarios

### M1. Project skeleton

#### Primary scenarios

- Application starts with a valid PostgreSQL configuration
- `/api/v1/health` returns success
- Startup or health logging surfaces database connectivity state

#### Regression scope

- Health endpoint remains reachable after persistence refactors
- Startup path remains compatible with environment separation

### M2. Core schema

#### Primary scenarios

- Required minimal tables exist in PostgreSQL
- Raw and canonical records remain structurally distinct
- Lineage relationships can be created

#### Regression scope

- Schema changes do not break raw ingest setup
- Naming refactors do not break table discovery or metadata registration

### M3. Raw read and event ingest

#### Primary scenarios

- Valid read payload persists `ingest_batch` and `hes_read_raw`
- Valid event payload persists `ingest_batch` and `hes_event_raw`
- Invalid records persist `ingest_error_log`
- Original payload remains preserved

#### Boundary scenarios

- `reads` or `events` omitted
- Empty list vs one record vs many records
- Missing `batch_id` with missing `message_id`
- Timestamp just valid vs malformed
- Duplicate raw record vs unique raw record
- Supported locale `en` vs supported locale `ko` vs unsupported locale

#### Regression scope

- Duplicate detection still works after schema or naming refactors
- Error logging still distinguishes ingest-level failures from later exceptions

### M4. Master data mapping

#### Primary scenarios

- Known meter and channel map to internal records
- Installation context can be determined for the measurement timestamp
- Unknown mapping remains visible for operator follow-up

#### Boundary scenarios

- Exact installation start timestamp
- Exact removal timestamp
- No active installation history
- Multiple possible installations due to bad data

#### Regression scope

- Mapping logic remains consistent after master-data UI or API changes
- Canonical conversion still depends on the same mapping rules

### M5. Canonical conversion

#### Primary scenarios

- Valid mapped raw read creates `canonical_measurement`
- Canonical record carries device, component, timestamp, and lineage
- Conversion failures remain observable

#### Boundary scenarios

- Minimal valid field set
- Missing optional source fields
- Duplicate read should not create a second canonical record
- Unknown UOM fallback behavior
- Timestamp normalization across timezone offsets

#### Regression scope

- Canonical conversion remains aligned with ingest contract changes
- Lineage remains intact after naming refactors

### M6. Visibility and operator inspection

#### Primary scenarios

- Operator can query by batch
- Operator can query by meter
- Operator can inspect raw, event, canonical, and error outcomes
- Operator can inspect recent operational events and open alerts
- Lineage is visible through API or UI

#### Boundary scenarios

- Empty database
- Filters returning zero rows
- Very narrow date range
- Invalid filter combinations
- English vs Korean visible text
- No alerts vs one alert vs multiple alerts

#### Regression scope

- Query endpoints still work after persistence renaming
- Operator labels remain localizable
- Operator event and alert visibility still matches underlying adapter and pipeline state

## Cross-cutting regression checklist

Whenever a minimal-stage persistence or ingest change occurs, confirm at least the following:

- Health path still works
- PostgreSQL connectivity path still works
- Raw read ingest still persists
- Raw event ingest still persists
- Ingest error logging still persists
- Master-data mapping still distinguishes mapped vs unmapped
- Canonical conversion still creates lineage-linked records
- English and Korean locale-sensitive responses still behave predictably

## Automation priority

Recommended order for automation investment:

1. `pytest` unit coverage for ingest validation and mapping logic
2. `pytest` integration coverage for API and persistence flows
3. `Playwright` smoke coverage for dashboard, raw visibility, and error visibility

## Definition of done

A backlog item is not ready to close unless:

- The relevant rows in this matrix were covered by added or updated tests
- Boundary cases were considered explicitly
- Regression scope was executed for adjacent flows
- English and Korean behavior was checked where user-facing text or locale behavior was touched
