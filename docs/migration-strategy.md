# Migration Strategy

## Purpose

This document defines the schema migration baseline for the repository as it moves toward a PostgreSQL-first minimal stage.

## Why this matters now

- The current scaffold still uses direct table creation without a formal migration tool
- PostgreSQL is now the agreed baseline database
- Persistent naming alignment requires controlled schema change
- Feature work on unstable schema management would increase later risk

For these reasons, migration strategy should be documented before further persistence-heavy implementation continues.

## Baseline decision

- Schema evolution should be handled by a migration tool
- `Alembic` is the recommended migration tool for this SQLAlchemy-based project
- Migration history should become the source of truth for schema change
- Direct unmanaged schema drift should be avoided

## Migration goals for the minimal stage

- Move from ad hoc `create_all()` behavior toward tracked schema revision history
- Support PostgreSQL as the primary migration target
- Enable repeatable setup for development and testing
- Allow controlled renaming from interim names to backlog-aligned names

## Current gap

The repository currently lacks:

- `Alembic` dependency
- migration configuration
- revision history
- naming-refactor migration plan

## Recommended adoption sequence

### Step 1. Freeze the current behavior

- Add tests around existing minimal persistence behavior
- Capture current raw ingest and canonicalization expectations

### Step 2. Add migration tooling

- Add `Alembic` to project dependencies
- Initialize migration directory structure
- Configure migration environment for SQLAlchemy metadata

### Step 3. Establish baseline revision

- Create an initial revision representing the agreed PostgreSQL-oriented minimal schema
- Prefer the target backlog-aligned names rather than preserving interim names in long-term migration history

### Step 4. Refactor application bootstrap

- Reduce reliance on unmanaged `create_all()`
- Route setup and deployment guidance through migration commands instead

### Step 5. Apply future schema changes only through migrations

- Table additions
- column changes
- indexes
- constraints
- renames

## Naming alignment implications

The migration strategy should support the agreed persistence vocabulary:

- `ingest_batch`
- `hes_read_raw`
- `hes_event_raw`
- `canonical_measurement`
- `ingest_error_log`

Where feasible, it is cleaner to make the first durable PostgreSQL migration use the target names directly rather than introducing extra rename steps in long-term history.

## Development workflow expectations

Suggested workflow after migration tooling is introduced:

```bash
alembic upgrade head
pytest
```

For schema changes:

```bash
alembic revision -m "describe change"
alembic upgrade head
pytest
```

## Environment expectations

- Development and test databases should be separate
- Test execution should not depend on the development database
- Migration commands should run against the intended environment explicitly

## Rename-specific strategy

The transition from interim names to target names should follow one of two controlled approaches.

### Preferred approach

- Introduce migration tooling
- Build the initial durable PostgreSQL schema directly with target names
- Move application code to match those target names

### Alternative approach

- Preserve interim names temporarily
- Add explicit rename migrations later

The preferred approach is cleaner if broad feature expansion has not yet started and existing local data is disposable.

## Data safety rules

- Raw-source fidelity must not be lost during migration work
- Migration plans must preserve lineage relationships
- Destructive changes should be explicit and justified
- If development data must be reset during early alignment, document that clearly before execution

## Testing expectations for migrations

- Migration changes require regression testing
- At minimum, verify schema creation, ingest persistence, canonical persistence, and error persistence
- If migration work changes locale-visible text or contracts, include English and Korean checks where relevant

## Definition of done

Migration strategy is considered operationally ready when:

- A migration tool is selected and documented
- The repository can initialize schema through migration commands
- PostgreSQL is the primary migration target
- Persistent naming aligns with the agreed backlog baseline
- Schema changes no longer rely on unmanaged drift

