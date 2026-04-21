# PostgreSQL Runbook

## Purpose

This runbook defines the PostgreSQL baseline for local development in the minimal stage.

## Baseline decision

- PostgreSQL is the primary database from the minimal stage onward.
- SQLite may still exist in the current scaffold, but it is no longer the target baseline.
- Future refactoring should make PostgreSQL the default runtime path.

## Current repository implication

The repository is not fully aligned yet.

- The current application configuration still defaults to SQLite.
- The current Python dependency set does not yet include a PostgreSQL driver such as `psycopg[binary]`.
- The current repository does not yet include a migration tool such as `Alembic`.

These are known structural alignment tasks and should be addressed before broader feature expansion continues.

## Local environment checks

Run these checks before starting development:

```bash
psql --version
pg_lsclusters
pg_isready
```

Interpretation:

- `psql --version` confirms the client tool is installed.
- `pg_lsclusters` shows available PostgreSQL clusters on Ubuntu-based systems.
- `pg_isready` confirms whether the server is currently accepting connections.

## Start and stop commands

Depending on the system configuration, use one of the following:

```bash
sudo systemctl start postgresql
sudo systemctl stop postgresql
sudo systemctl status postgresql
```

Or, if cluster-specific control is preferred:

```bash
sudo pg_ctlcluster 16 main start
sudo pg_ctlcluster 16 main stop
sudo pg_ctlcluster 16 main status
```

If the cluster version or name differs, adjust `16 main` accordingly.

## Recommended local database setup

Create a dedicated role and separate databases for development and testing.

```sql
CREATE ROLE mdms_app LOGIN PASSWORD 'change-me';
CREATE DATABASE mdms_dev OWNER mdms_app;
CREATE DATABASE mdms_test OWNER mdms_app;
```

If the role already exists, reuse it instead of recreating it.

## Recommended environment variables

Development:

```dotenv
DATABASE_URL=postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_dev
```

Testing:

```dotenv
DATABASE_URL=postgresql+psycopg://mdms_app:change-me@127.0.0.1:5432/mdms_test
```

Production shape:

```dotenv
DATABASE_URL=postgresql+psycopg://mdms_app:<strong-password>@db-host:5432/mdms_prod
```

Use `127.0.0.1` instead of `localhost` when explicit TCP behavior is preferred.

## Encoding and locale checks

All repository files must remain UTF-8, and the database baseline should be checked for compatible text handling.

Useful verification queries:

```sql
SHOW server_encoding;
SHOW client_encoding;
SELECT datname, pg_encoding_to_char(encoding) FROM pg_database;
```

The expected baseline is UTF-8-compatible encoding.

## Suggested development checklist

Before switching the application runtime to PostgreSQL, confirm the following:

- PostgreSQL server is running
- Target database exists
- Application role can connect
- `DATABASE_URL` is set correctly
- Python dependency set includes a PostgreSQL driver
- Migration workflow is defined

## Troubleshooting guide

### `pg_isready` shows no response

- Check whether the PostgreSQL service is running
- Check whether the expected cluster is down
- Start the service or the specific cluster

### Authentication failure

- Verify role name and password
- Verify local authentication rules in `pg_hba.conf`
- Verify whether the connection uses TCP or Unix socket behavior

### Database does not exist

- Create the expected database
- Confirm the application role owns it or has sufficient privileges

### Python cannot connect

- Confirm the project has installed a PostgreSQL SQLAlchemy driver such as `psycopg[binary]`
- Confirm `DATABASE_URL` uses the correct SQLAlchemy driver prefix

## Definition of done for PostgreSQL alignment

The repository is considered PostgreSQL-aligned for the minimal stage only when:

- PostgreSQL is the default runtime assumption
- The application can connect using the configured `DATABASE_URL`
- Development and test databases are documented and usable
- A PostgreSQL driver is installed through project dependencies
- Migration workflow is defined and documented

## Large-table operational baseline

For append-only meter-read tables, PostgreSQL alignment should also consider large-table operational behavior.

Recommended baseline:

- use time-based range partitioning
- start with monthly partitions
- ensure large-table queries include explicit time predicates
- manage retention and archive at the partition level
- keep volatile state tables such as `raw_interval_window_state` on a short rolling horizon rather than long-term retention

The detailed operational strategy is documented in:

- [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)
