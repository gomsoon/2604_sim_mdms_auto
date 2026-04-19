# Implementation Roadmap

## Purpose

This document turns the current backlog and planning documents into an implementation sequence for the near-term development of the minimal stage.

## Guiding principles

- Structural alignment comes before feature expansion
- PostgreSQL is the runtime baseline
- Backlog-aligned persistent naming is the target vocabulary
- Tests and regression checks accompany each meaningful change
- English and Korean support must remain part of feature design

## Current starting point

The repository already has:

- a runnable Flask scaffold
- minimal raw-to-canonical flow proof
- engineering baseline documents
- staged backlog documents

The repository does not yet have:

- PostgreSQL-first runtime configuration
- migration tooling
- backlog-aligned persistence names in code
- formal test suite implementation

## Recommended implementation sequence

### Stage 0. Documentation baseline stabilization

#### Goal

Treat the current documentation set as the pre-implementation contract.

#### Entry criteria

- Core engineering documents exist
- Backlog baseline exists
- Gap analysis exists

#### Exit criteria

- Team agrees that current docs are sufficient to start structural refactoring

### Stage 1. PostgreSQL baseline alignment

#### Goal

Move the repository from SQLite-oriented defaults to PostgreSQL-oriented defaults.

#### Key tasks

- Add PostgreSQL driver dependency
- Update configuration defaults and environment examples
- Confirm local PostgreSQL startup and connection flow
- Update setup commands and runbook references

#### Test gate

- Application can boot against PostgreSQL
- Health path reflects connectivity state
- Development and test database separation is documented

#### Related documents

- [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
- [gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/gap-analysis.md)

### Stage 2. Migration foundation

#### Goal

Introduce controlled schema evolution before deeper persistence work continues.

#### Key tasks

- Add `Alembic`
- Create migration configuration
- Establish baseline revision strategy
- Reduce reliance on unmanaged schema creation

#### Test gate

- Schema can be initialized through migration commands
- Test environment can apply schema predictably

#### Related documents

- [migration-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/migration-strategy.md)

### Stage 3. Persistence naming alignment

#### Goal

Refactor interim persistent names to the backlog-aligned vocabulary.

#### Key tasks

- Rename ORM classes and table names
- Revisit ingest-stage error semantics
- Update services, blueprints, templates, and docs
- Remove stale references to interim names

#### Test gate

- Raw read ingest still works
- Raw event ingest still works
- Canonical conversion still works
- Ingest error logging still works
- Regression checks cover adjacent flows

#### Related documents

- [persistence-renaming-plan.md](/home/tprover/2604_sim_mdms_auto/docs/persistence-renaming-plan.md)
- [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)

### Stage 4. Minimal ingest contract implementation hardening

#### Goal

Align code behavior with the first documented HES ingest contract.

#### Key tasks

- Normalize envelope validation
- Normalize read and event validation
- Add stable ingest error codes
- Add locale-aware message behavior
- Harden idempotency expectations

#### Test gate

- Contract-positive and contract-negative cases are covered
- Locale fallback is verified
- Error logging semantics are explicit

#### Related documents

- [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)
- [i18n-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/i18n-strategy.md)

### Stage 5. Master data and operator flow completion

#### Goal

Make the minimal stage operationally credible for mapping and verification.

#### Key tasks

- Add master-data CRUD or equivalent management flows
- Make mapping failure visibility explicit
- Improve batch and meter lookup paths
- Ensure operator UI reflects documented workflows

#### Test gate

- Operators can register master data needed for mapping
- Operators can inspect ingest, errors, and canonical outcomes
- Workflow smoke checks pass

#### Related documents

- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [minimal-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-backlog.md)

### Stage 6. Minimal-stage hardening

#### Goal

Close the gap between proof-of-concept and a stable minimal baseline.

#### Key tasks

- Add test suite structure
- Add sample fixtures
- Improve logging and observability
- Add lightweight orchestration status visibility for the dashboard
- Clean up technical debt discovered during earlier stages

#### Test gate

- Core minimal acceptance scenarios are automated or explicitly smoke-tested
- Regression expectations are repeatable

#### Related documents

- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
- [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)

### Stage 7. Integration runtime baseline

#### Goal

Introduce the first production-like runtime adapter control model without overbuilding a full connector platform.

#### Key tasks

- add runtime adapter lifecycle concepts
- add operator-facing adapter operations visibility
- define the first polling adapter baseline
- keep adapter implementations code-backed while making adapter instances operationally manageable

#### Test gate

- operators can inspect adapter runtime state
- operators can enable, pause, and run once against an adapter instance
- first polling adapter execution is visible and auditable

#### Related documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [adapter-gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-gap-analysis.md)
- [adapter-implementation-sequence.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-implementation-sequence.md)

## Recommended immediate next step

The next implementation work should start at `Stage 1` and `Stage 2` together:

1. PostgreSQL driver and runtime baseline
2. Migration tooling introduction

Only after that should the repository proceed into naming refactor and contract hardening.

## Pre-HES-review design work that can proceed now

Before the real HES schema is shared next week, the project can still make progress on the following:

1. provisional raw-table design
2. PostgreSQL baseline and driver selection
3. migration-tool introduction
4. naming-alignment refactor planning
5. test design for ingest validation and error handling
6. orchestration status model planning for dashboard visibility

This work should use the provisional assumptions explicitly and stay ready for adjustment after the HES schema review.

## Minimal-stage completion checkpoint

The minimal stage is considered meaningfully complete only when:

- PostgreSQL is the active baseline
- backlog-aligned persistence names are in place
- raw reads and events can be ingested
- canonical measurements can be created with lineage
- ingest failures are visible and distinguishable
- operators can inspect the flow by batch and meter
- tests and regression checks exist for the core path
