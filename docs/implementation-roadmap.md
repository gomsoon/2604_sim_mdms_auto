# Implementation Roadmap

## Purpose

This document turns the current backlog and planning documents into an implementation sequence for the near-term development of the minimal stage.

## Current billing-lite direction

The near-term downstream billing-lite sequence should now be read as:

1. `usage_transaction`
2. `bill_determinant`
3. `service_point_billing_context`
4. `service_point_tariff_assignment`
5. `bill_charge`
6. optional `invoice_summary`
7. later billing export queue and export status

Key rule:

- `bill_determinant` is billing-ready
- `bill_charge` is charge-ready
- `invoice_summary` is a lightweight review and handoff grouping layer
- `billing_export_queue` is the first immutable export-staging layer
- recovery and resend actions should create new export requests instead of
  mutating an old one in place
- invoice and CIS handoff remain later steps

## Current policy-depth direction

After the first VEE closure baseline, the near-term policy-depth sequence
should now be read as:

1. `event-aware correction policy`
2. `estimation` and `manual edit` coverage expansion only where policy remains
   safe
3. broader source-aware VEE refinement when richer upstream context exists

Key rule:

- prefer guidance and guardrails before automation
- do not imply a correction path that current persistence and lineage do not yet
  support

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
- Add a minimal operational event and alert timeline for operator visibility
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

### Stage 8. Source-specific packed-read adapter expansion

#### Goal

Introduce the first source-specific adapter path for packed HES read blocks while preserving an interval-granular MDM common raw model.

#### Key tasks

- define the interval-granular common raw read target
- define the completeness-state table
- implement optional landing for packed source blocks
- implement the overseas Oracle `LP_EM` polling adapter
- expand packed source rows into interval raw rows

#### Test gate

- source block fetch is auditable
- source block replay can regenerate interval rows
- interval raw rows preserve lineage to source blocks
- completeness-state updates are deterministic
- late-write behavior is visible and testable

#### Related documents

- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
- [lp-em-adapter-mapping.md](/home/tprover/2604_sim_mdms_auto/docs/lp-em-adapter-mapping.md)
- [nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)

### Stage 9. HES-centric operator flow completion

#### Goal

Shift integration operations from an adapter-first posture to an HES-first posture without removing the existing runtime adapter model.

#### Key tasks

- complete HES-scoped adapter registration

### Stage 10. Processing replay and usage visibility hardening

#### Goal

Turn the current single-object processing replay flow into a broader operationally manageable replay model while keeping usage visibility operator-friendly.

#### Key tasks

- complete manual `re-VEE` visibility and downstream usage drill-down
- introduce queue-backed replay requests for:
  - `hes_system`
  - `ingest_batch`
  - bounded `date_range`
- link replay requests to `pipeline_run`
- expose replay progress and failure visibility

#### Test gate

- single-object `re-VEE` remains stable
- replay request creation is auditable
- replay item processing is traceable
- usage recalculation visibility remains intact after replay

#### Related documents

- [re-vee-baseline-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/re-vee-baseline-runbook.md)
- [bulk-async-vee-replay-design.md](/home/tprover/2604_sim_mdms_auto/docs/bulk-async-vee-replay-design.md)
- [processing-core-rollout-plan.md](/home/tprover/2604_sim_mdms_auto/docs/processing-core-rollout-plan.md)
- align `source_system` with `hes_system.hes_code`
- make HES detail the main drill-down anchor into adapters and recent ingest activity
- improve HES-level summaries and navigation across the integration layer

#### Test gate

- operators can create an adapter directly from an HES context
- adapter creation keeps parent HES lineage explicit
- HES detail remains a stable entry point into adapter and ingest investigation

#### Related documents

- [hes-system-management.md](/home/tprover/2604_sim_mdms_auto/docs/hes-system-management.md)
- [hes-centric-operations-plan.md](/home/tprover/2604_sim_mdms_auto/docs/hes-centric-operations-plan.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)

### Stage 10. Processing/core foundation beyond the minimal finalization baseline

#### Goal

Introduce the first true MDM processing boundary between canonical mapping results and downstream usage-oriented outputs.

#### Key tasks

- define `initial_measurement`
- define `vee_execution_log`
- define `vee_exception`
- tighten the business meaning of `final_measurement`
- define the first `usage_transaction` grain
- keep billing-ready determinants as a later follow-up layer

#### Test gate

- the repository can distinguish mapping success from VEE acceptance
- finalization rules are explicit and testable
- downstream usage design depends on `final_measurement` rather than directly on canonical rows

#### Related documents

- [usage-and-billing-ready-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/usage-and-billing-ready-architecture.md)
- [vee-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/vee-baseline-design.md)
- [final-measurement-revision-design.md](/home/tprover/2604_sim_mdms_auto/docs/final-measurement-revision-design.md)
- [usage-transaction-design.md](/home/tprover/2604_sim_mdms_auto/docs/usage-transaction-design.md)

### Stage 11. Billing-ready determinant foundation

### Stage 10A. Processing correction and audit baseline

#### Goal

Add the first operator correction layer above VEE without collapsing
estimation, manual edit, and downstream recalculation into undocumented
side-effects.

#### Key tasks

- finish the first operator-triggered estimation path
- define the next synthetic missing-interval estimation boundary
- keep synthetic repair anchored to `RawIntervalWindowState` and `estimation_audit`
- define a narrow manual-edit-and-audit baseline
- keep both correction paths anchored to `initial_measurement`
- regenerate current `final_measurement` through revision rather than overwrite
- recalculate downstream `usage_transaction`, `bill_determinant`, and
  `bill_charge` from the new authoritative final state

#### Test gate

- estimation remains substitution-only and auditable
- manual correction is append-only in audit storage
- final supersession stays explicit
- downstream recalculation remains deterministic after correction

#### Related documents

- [estimation-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/estimation-baseline-design.md)
- [synthetic-missing-interval-estimation-design.md](/home/tprover/2604_sim_mdms_auto/docs/synthetic-missing-interval-estimation-design.md)
- [manual-edit-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/manual-edit-baseline-design.md)
- [final-measurement-revision-design.md](/home/tprover/2604_sim_mdms_auto/docs/final-measurement-revision-design.md)
- [usage-transaction-design.md](/home/tprover/2604_sim_mdms_auto/docs/usage-transaction-design.md)

### Stage 11. Billing-ready determinant foundation

#### Goal

Define the first billing-ready determinant layer that follows `usage_transaction`
without collapsing export, pricing, or invoice logic into the same persistence slice.

#### Key tasks

- define `bill_determinant` grain
- define the source rule from `usage_transaction`
- define billing-window and billing-cycle prerequisites
- define determinant revision and supersession semantics
- keep billing export as a later follow-up layer

#### Test gate

- determinant generation depends on `usage_transaction` rather than directly on final rows
- determinant current-versus-history semantics are explicit
- the first determinant candidate is realistic under current upstream usage shapes

#### Related documents

- [usage-and-billing-ready-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/usage-and-billing-ready-architecture.md)
- [usage-transaction-design.md](/home/tprover/2604_sim_mdms_auto/docs/usage-transaction-design.md)
- [bill-determinant-design.md](/home/tprover/2604_sim_mdms_auto/docs/bill-determinant-design.md)

### Stage 12. Optional billing-lite boundary

#### Goal

Define a minimal downstream billing slice that can operate inside the MDM for
small-scale deployments and end-to-end testing without absorbing full CIS
responsibilities.

#### Key tasks

- define the `billing-lite` boundary relative to `bill_determinant`
- define minimal billing context requirements
- define minimal tariff assignment requirements
- define the first `bill_charge` candidate and revision expectations
- preserve a clean handoff path to later CIS integration

#### Test gate

- `bill_determinant` remains the only billing-ready input to the first billing slice
- missing billing context produces `blocked`, not guessed, downstream outputs
- the repository can exercise a small tariff-based end-to-end path without
  pretending to be a full CIS

#### Related documents

- [bill-determinant-design.md](/home/tprover/2604_sim_mdms_auto/docs/bill-determinant-design.md)
- [billing-lite-boundary-design.md](/home/tprover/2604_sim_mdms_auto/docs/billing-lite-boundary-design.md)
- [usage-and-billing-ready-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/usage-and-billing-ready-architecture.md)

### Stage 13. Billing context baseline

#### Goal

Define the smallest persistent business-context slice needed so that
`bill_determinant` and later `billing-lite` outputs no longer guess billing
windows.

#### Key tasks

- define `service_point_billing_context`
- define billing timezone semantics
- define `calendar_month` and `anchored_month` baseline cycle modes
- define effective-period and current-row rules
- define how missing billing context blocks downstream outputs

#### Test gate

- determinant calculation can distinguish known versus unknown billing context
- missing context produces `blocked`, not guessed, determinant outcomes
- the repository has a stable place to anchor later tariff and charge models

#### Related documents

- [billing-context-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/billing-context-baseline-design.md)
- [bill-determinant-design.md](/home/tprover/2604_sim_mdms_auto/docs/bill-determinant-design.md)
- [billing-lite-boundary-design.md](/home/tprover/2604_sim_mdms_auto/docs/billing-lite-boundary-design.md)

### Stage 14. Tariff assignment baseline

#### Goal

Define the smallest tariff-assignment slice needed so that later
`bill_charge` calculation stops guessing which tariff should apply, while
keeping the first determinant baseline independent from tariff assignment.

#### Key tasks

- define `service_point_tariff_assignment`
- define current-row and effective-period rules
- define the first operator-managed tariff assignment workflow
- define how missing tariff assignment blocks later charge calculation
- preserve a clean separation between determinant generation and charge
  calculation

#### Test gate

- the first `billing_cycle_consumption_total` determinant can still exist
  without tariff assignment when billing context is valid
- missing tariff assignment is surfaced explicitly for later `bill_charge`
  calculation
- the repository has a stable place to anchor later charge and invoice models

#### Related documents

- [tariff-assignment-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/tariff-assignment-baseline-design.md)
- [billing-lite-boundary-design.md](/home/tprover/2604_sim_mdms_auto/docs/billing-lite-boundary-design.md)
- [bill-determinant-design.md](/home/tprover/2604_sim_mdms_auto/docs/bill-determinant-design.md)

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
