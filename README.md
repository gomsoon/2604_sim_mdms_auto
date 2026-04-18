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

Then open `http://127.0.0.1:5000/`.

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

- Local development defaults to SQLite so the team can start fast with no external dependency.
- The app is intentionally structured so `DATABASE_URL` can later point to PostgreSQL without changing the Flask code shape.
- This stage stops at raw ingestion, master-data mapping, canonicalization, and exception visibility.

Additional context lives in [docs/minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md).

