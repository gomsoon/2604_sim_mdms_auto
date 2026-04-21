# MDMS Minimal E2E

This repository contains the first development scaffold for a minimal end-to-end Meter Data Management System. The goal of this phase is to prove the raw-to-canonical flow before building VEE, usage, and billing-oriented features.

## What is included

- Flask application factory and blueprints
- SQLAlchemy-based core data model
- Bootstrap-backed operator dashboard
- Raw read and raw event ingest APIs
- Basic duplicate detection, mapping, and exception queue
- Demo seed command for local walkthroughs

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
cp .env.example .env
make install
make init-db
make seed-demo
# optional: operator UI can also trigger finalization from /canonical-measurements
./.venv/bin/flask --app wsgi:app promote-final
# optional: enqueue polling adapters that are due for scheduled execution
./.venv/bin/flask --app wsgi:app enqueue-scheduled-adapter-runs --limit 10
# optional: queued adapter runs can be consumed by the lightweight worker command
./.venv/bin/flask --app wsgi:app process-adapter-runs --limit 1
make run
```

Before `make init-db`, make sure local PostgreSQL is running and the application role/database already exist. The current `.env.example` expects:

- role: `mdms_app`
- database: `mdms_dev`
- test database: `mdms_test`
- app timezone: `Asia/Seoul`
- host: `127.0.0.1`
- port: `5432`

Then open `http://127.0.0.1:5000/`.

## Test commands

```bash
make test
make test-functional
```

`make test` now runs `pytest` with branch coverage enabled for the `app` package and enforces a minimum `80%` branch coverage baseline. The test fixtures use PostgreSQL and isolate each test in its own schema under `TEST_DATABASE_URL`.

Date-only operator filters use `APP_TIMEZONE` to interpret local business days before converting them to UTC for storage/query comparisons.

`make test-functional` runs a small Playwright smoke suite against a temporary local Flask server. The suite prefers the system Chrome executable and can also use `PLAYWRIGHT_CHROME_PATH` when Chrome is installed in a non-default path.
If the current environment blocks browser launch, the functional suite is skipped instead of failing the whole regression run.

## Key routes

- `/` dashboard
- `/raw-reads` raw read list
- `/raw-events` raw event list
- `/canonical-measurements` canonical measurement list
- `/final-measurements` final measurement list
- `/adapters` runtime adapter list
- `/exceptions` open exception queue
- `/master-data` minimal master data view
- `/api/v1/health` health check
- `/api/v1/ingest/reads` POST raw meter reads
- `/api/v1/ingest/events` POST raw events
- `/api/v1/canonical-measurements` canonical measurement list
- `/api/v1/final-measurements` final measurement list

## Sample read ingest payload

```json
{
  "contract_version": "v1",
  "source_system": "HES",
  "adapter_key": "common_raw_v1",
  "batch_id": "batch-20260418-001",
  "received_at": "2026-04-18T09:00:00+09:00",
  "reads": [
    {
      "meter_id": "MTR-1001",
      "channel_id": "CH-01",
      "measured_at": "2026-04-18T00:15:00+09:00",
      "value": 14.2,
      "quality_code": "OK",
      "status_code": "ACTUAL",
      "unit": "kWh"
    }
  ]
}
```

## Design notes

- The runtime baseline now targets PostgreSQL and expects a valid `DATABASE_URL`.
- Migration setup is now aligned around Alembic instead of unmanaged schema creation.
- Persistent naming is aligned with the backlog baseline such as `ingest_batch`, `hes_read_raw`, `hes_event_raw`, and `ingest_error_log`.
- Ingest now uses adapter profiles such as `common_raw_v1` and `legacy_hes_v1` to normalize source-specific field names before common raw persistence.
- This stage now includes explicit `canonical -> final_measurement` promotion as a separate processing step, available from both CLI and the canonical measurement operator view.

Additional context lives in [docs/minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md).

Known structural alignment work is tracked in [docs/gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/gap-analysis.md).
