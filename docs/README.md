# Engineering Docs

This directory captures the working engineering baseline for the `Minimal End-to-End` stage of the MDM system.

## Recommended reading order

1. [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)
2. [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
3. [core-stability-goals.md](/home/tprover/2604_sim_mdms_auto/docs/core-stability-goals.md)
4. [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
5. [development-guide.md](/home/tprover/2604_sim_mdms_auto/docs/development-guide.md)
6. [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
7. [backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md)
8. [minimal-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-backlog.md)
9. [gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/gap-analysis.md)
10. [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
11. [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)
12. [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)
13. [provisional-raw-schema.md](/home/tprover/2604_sim_mdms_auto/docs/provisional-raw-schema.md)
14. [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
15. [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
16. [persistence-renaming-plan.md](/home/tprover/2604_sim_mdms_auto/docs/persistence-renaming-plan.md)
17. [i18n-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/i18n-strategy.md)
18. [migration-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/migration-strategy.md)
19. [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)
20. [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
21. [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
22. [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)
23. [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
24. [minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md)

## Intent

These documents are meant to reduce ambiguity before feature work begins.

- `requirements.md` defines what the system must do now.
- `layered-architecture-baseline.md` defines the top-level layered view of the whole system.
- `core-stability-goals.md` defines what should remain stable in the data and processing core.
- `architecture.md` defines how the system should be shaped.
- `development-guide.md` defines how changes must be implemented.
- `testing-strategy.md` defines how changes must be validated.
- `backlog.md` captures the staged product backlog.
- `minimal-backlog.md` focuses the team on the current delivery wave.
- `gap-analysis.md` explains the difference between the current scaffold and the agreed target baseline.
- `postgresql-runbook.md` defines the local PostgreSQL baseline and checks.
- `hes-ingest-contract.md` defines the minimal raw ingest contract.
- `hes-schema-checklist.md` defines what to inspect in the real HES schema before raw table design starts.
- `provisional-raw-schema.md` defines the pre-HES-review raw schema we can use to keep moving now.
- `data-layer-architecture.md` defines when to use landing tables and how data should converge into the common raw and final layers.
- `pipeline-orchestration.md` defines how data should move upward between layers and how administrators should see status on the dashboard.
- `persistence-renaming-plan.md` defines the naming-alignment refactor sequence.
- `i18n-strategy.md` defines the English and Korean support baseline.
- `migration-strategy.md` defines the schema evolution baseline.
- `domain-glossary.md` locks core project terminology.
- `acceptance-test-matrix.md` maps backlog items to concrete verification scope.
- `operator-workflows.md` captures the minimal-stage operational flows the UI and APIs must support.
- `implementation-roadmap.md` turns the planning set into an ordered execution sequence.
- `decision-log.md` distinguishes locked decisions from open questions.

## Current decision baseline

- `PostgreSQL` is the agreed primary database even for the minimal stage.
- The target model and table naming should follow the PDF backlog naming, such as `ingest_batch`, `hes_read_raw`, `hes_event_raw`, and `ingest_error_log`.
- The current scaffold is not fully aligned yet, so future implementation should start with structural refactoring toward that baseline.
