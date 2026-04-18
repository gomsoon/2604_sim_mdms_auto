# HES Ingest Contract

## Purpose

This document defines the first JSON-based HES ingestion contract for the minimal stage.

## Scope

This contract covers:

- Raw meter read ingestion
- Raw event ingestion
- Minimal validation and ingest logging
- Lineage into minimal-stage persistence

This contract does not yet cover:

- VEE execution
- Usage calculation
- Billing or CIS export
- Advanced schema version negotiation

## Contract principles

- JSON is the first supported format for minimal delivery
- API-based ingestion is the primary path
- Original payload must be preserved
- Stable machine-readable error codes must be returned
- English and Korean operator-facing messaging should be supported
- Timestamps must use ISO 8601 with timezone information

## Shared envelope fields

The following fields apply to both read and event ingestion.

| Field | Required | Notes |
| --- | --- | --- |
| `contract_version` | Yes | Start with `v1` |
| `source_system` | Yes | Example: `HES` |
| `batch_id` | Conditional | Required for batch-oriented delivery unless `message_id` is present |
| `message_id` | Conditional | Required for message-oriented delivery unless `batch_id` is present |
| `received_at` | No | Upstream-provided receipt timestamp; if omitted, the API records the server ingest time separately |
| `locale` | No | `en` or `ko`; defaults to `en` if omitted |

At least one of `batch_id` or `message_id` must be present.

## Raw read ingest endpoint

### Proposed endpoint

```http
POST /api/v1/ingest/reads
Content-Type: application/json
```

### Request shape

```json
{
  "contract_version": "v1",
  "source_system": "HES",
  "batch_id": "batch-20260418-001",
  "received_at": "2026-04-18T09:00:00+09:00",
  "locale": "en",
  "reads": [
    {
      "meter_id": "MTR-1001",
      "channel_id": "CH-01",
      "measurement_ts": "2026-04-18T00:15:00+09:00",
      "value": 14.2,
      "quality_code": "OK",
      "status_code": "ACTUAL",
      "unit_of_measure": "kWh",
      "interval_size_minutes": 15,
      "source_type": "interval"
    }
  ]
}
```

### Required read fields

| Field | Required | Notes |
| --- | --- | --- |
| `meter_id` | Yes | Source meter identifier |
| `channel_id` | Yes | Source channel identifier |
| `measurement_ts` | Yes | ISO 8601 timestamp with timezone |
| `value` | Yes | Numeric measurement value |
| `quality_code` | No | Upstream quality indicator |
| `status_code` | No | Upstream status indicator |
| `unit_of_measure` | Recommended | Prefer explicit source UOM |
| `interval_size_minutes` | No | Needed for interval-aware logic |
| `source_type` | No | Example: `interval` or `scalar` |

### Persistence intent

- Envelope metadata persists to `ingest_batch`
- Each record persists to `hes_read_raw`
- Invalid ingest-level records persist to `ingest_error_log`
- Successfully mapped records later feed `canonical_measurement`

## Raw event ingest endpoint

### Proposed endpoint

```http
POST /api/v1/ingest/events
Content-Type: application/json
```

### Request shape

```json
{
  "contract_version": "v1",
  "source_system": "HES",
  "batch_id": "event-batch-20260418-001",
  "received_at": "2026-04-18T09:05:00+09:00",
  "locale": "ko",
  "events": [
    {
      "meter_id": "MTR-1001",
      "event_ts": "2026-04-18T00:00:00+09:00",
      "event_code": "POWER_FAIL",
      "severity": "high",
      "event_source": "meter"
    }
  ]
}
```

### Required event fields

| Field | Required | Notes |
| --- | --- | --- |
| `event_ts` | Yes | ISO 8601 timestamp with timezone |
| `event_code` | Yes | Upstream event code |
| `meter_id` | Recommended | Strongly preferred for later correlation |
| `severity` | No | Example: `low`, `medium`, `high` |
| `event_source` | No | Example: `meter`, `hes`, `network` |

### Persistence intent

- Envelope metadata persists to `ingest_batch`
- Each record persists to `hes_event_raw`
- Invalid ingest-level records persist to `ingest_error_log`

## Validation rules for the minimal stage

### Envelope validation

- `contract_version` must be recognized
- `source_system` must be present
- At least one of `batch_id` or `message_id` must be present
- `locale`, if present, must be `en` or `ko`

### Read validation

- `meter_id`, `channel_id`, `measurement_ts`, and `value` are required
- `measurement_ts` must be parseable and timezone-aware
- `value` must be numeric

### Event validation

- `event_ts` and `event_code` are required
- `event_ts` must be parseable and timezone-aware

## Idempotency and duplicate handling

- `source_system` plus `batch_id` or `message_id` should identify the ingest envelope
- Duplicate ingest requests must be handled idempotently where possible
- Record-level duplicate checks should continue to compare source system, meter, channel, and timestamp for reads
- Duplicate detection should not delete the original raw record

## Error code baseline

The minimal stage should standardize at least the following ingest error codes:

- `unsupported_contract_version`
- `missing_envelope_identifier`
- `missing_required_field`
- `invalid_timestamp`
- `invalid_numeric_value`
- `invalid_locale`
- `duplicate_ingest_request`

Error responses should expose:

- stable machine-readable error code
- human-readable message
- locale-aware message support for `en` and `ko`

## Localization expectations

- The contract itself remains language-neutral
- Error codes remain stable across languages
- User-facing messages derived from ingest validation should be available in English and Korean

## Open decisions for implementation

- Whether the first minimal delivery supports only API ingestion or also CSV file loading
- Whether `unit_of_measure` should be strictly required for raw reads
- Whether `message_id` should become mandatory for non-batch delivery
- How ingest idempotency is enforced at the database level

