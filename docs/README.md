# Engineering Docs

This directory captures the working engineering baseline for the `Minimal End-to-End` stage of the MDM system.

## Recommended reading order

1. [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)
2. [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
3. [development-guide.md](/home/tprover/2604_sim_mdms_auto/docs/development-guide.md)
4. [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
5. [backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md)
6. [minimal-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-backlog.md)
7. [gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/gap-analysis.md)
8. [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
9. [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)
10. [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)
11. [provisional-raw-schema.md](/home/tprover/2604_sim_mdms_auto/docs/provisional-raw-schema.md)
12. [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
13. [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
14. [persistence-renaming-plan.md](/home/tprover/2604_sim_mdms_auto/docs/persistence-renaming-plan.md)
15. [i18n-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/i18n-strategy.md)
16. [migration-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/migration-strategy.md)
17. [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)
18. [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
19. [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
20. [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)
21. [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
22. [minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md)

## Intent

These documents are meant to reduce ambiguity before feature work begins.

- `requirements.md` defines what the system must do now.
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
