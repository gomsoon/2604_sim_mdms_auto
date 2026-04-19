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
make run
```

Before `make init-db`, make sure local PostgreSQL is running and the application role/database already exist. The current `.env.example` expects:

- role: `mdms_app`
- database: `mdms_dev`
- host: `127.0.0.1`
- port: `5432`

Then open `http://127.0.0.1:5000/`.

## Test commands

```bash
./.venv/bin/pytest
make test-functional
```

`make test-functional` runs a small Playwright smoke suite against a temporary local Flask server. The suite prefers the system Chrome executable and can also use `PLAYWRIGHT_CHROME_PATH` when Chrome is installed in a non-default path.
If the current environment blocks browser launch, the functional suite is skipped instead of failing the whole regression run.

## Key routes

- `/` dashboard
- `/raw-reads` raw read list
- `/raw-events` raw event list
- `/exceptions` open exception queue
- `/master-data` minimal master data view
- `/api/v1/health` health check
- `/api/v1/ingest/reads` POST raw meter reads
- `/api/v1/ingest/events` POST raw events

## Sample read ingest payload

```json
{
  "source_system": "HES",
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
- This stage stops at raw ingestion, master-data mapping, canonicalization, and exception visibility.

Additional context lives in [docs/minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md).

Known structural alignment work is tracked in [docs/gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/gap-analysis.md).
