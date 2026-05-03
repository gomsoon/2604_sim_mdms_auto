# Engineering Docs

This directory captures the working engineering baseline for the `Minimal End-to-End` stage of the MDM system.

## Recommended reading order

1. [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)
2. [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
3. [core-stability-goals.md](/home/tprover/2604_sim_mdms_auto/docs/core-stability-goals.md)
4. [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)
5. [development-guide.md](/home/tprover/2604_sim_mdms_auto/docs/development-guide.md)
6. [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
7. [pytest-xdist-evaluation.md](/home/tprover/2604_sim_mdms_auto/docs/pytest-xdist-evaluation.md)
8. [backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md)
9. [minimal-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-backlog.md)
10. [gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/gap-analysis.md)
11. [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
12. [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)
13. [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)
14. [provisional-raw-schema.md](/home/tprover/2604_sim_mdms_auto/docs/provisional-raw-schema.md)
15. [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)
16. [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
17. [interval-raw-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/interval-raw-table-design.md)
18. [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)
19. [partitioning-precheck.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-precheck.md)
20. [partitioning-implementation-plan.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-implementation-plan.md)
21. [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
22. [hes-system-management.md](/home/tprover/2604_sim_mdms_auto/docs/hes-system-management.md)
23. [hes-meter-reference-design.md](/home/tprover/2604_sim_mdms_auto/docs/hes-meter-reference-design.md)
24. [hes-centric-operations-plan.md](/home/tprover/2604_sim_mdms_auto/docs/hes-centric-operations-plan.md)
25. [usage-and-billing-ready-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/usage-and-billing-ready-architecture.md)
26. [vee-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/vee-baseline-design.md)
27. [re-vee-baseline-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/re-vee-baseline-runbook.md)
28. [bulk-async-vee-replay-design.md](/home/tprover/2604_sim_mdms_auto/docs/bulk-async-vee-replay-design.md)
29. [final-measurement-revision-design.md](/home/tprover/2604_sim_mdms_auto/docs/final-measurement-revision-design.md)
30. [usage-transaction-design.md](/home/tprover/2604_sim_mdms_auto/docs/usage-transaction-design.md)
31. [bill-determinant-design.md](/home/tprover/2604_sim_mdms_auto/docs/bill-determinant-design.md)
32. [billing-lite-boundary-design.md](/home/tprover/2604_sim_mdms_auto/docs/billing-lite-boundary-design.md)
33. [billing-context-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/billing-context-baseline-design.md)
34. [processing-core-persistence-design.md](/home/tprover/2604_sim_mdms_auto/docs/processing-core-persistence-design.md)
35. [processing-core-rollout-plan.md](/home/tprover/2604_sim_mdms_auto/docs/processing-core-rollout-plan.md)
36. [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
37. [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
38. [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
39. [adapter-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-backlog.md)
40. [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
41. [lp-em-adapter-mapping.md](/home/tprover/2604_sim_mdms_auto/docs/lp-em-adapter-mapping.md)
42. [nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)
43. [adapter-live-hardening-plan.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-live-hardening-plan.md)
44. [adapter-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-test-matrix.md)
45. [adapter-operator-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operator-runbook.md)
46. [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
47. [replay-idempotency-operations.md](/home/tprover/2604_sim_mdms_auto/docs/replay-idempotency-operations.md)
48. [adapter-gap-analysis.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-gap-analysis.md)
49. [adapter-implementation-sequence.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-implementation-sequence.md)
50. [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
51. [operational-events-and-alerts.md](/home/tprover/2604_sim_mdms_auto/docs/operational-events-and-alerts.md)
52. [minimal-event-alert-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-event-alert-boundary.md)
53. [operational-event-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/operational-event-table-design.md)
54. [persistence-renaming-plan.md](/home/tprover/2604_sim_mdms_auto/docs/persistence-renaming-plan.md)
55. [i18n-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/i18n-strategy.md)
56. [migration-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/migration-strategy.md)
57. [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)
58. [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
59. [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
60. [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)
61. [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
62. [minimal-e2e-plan.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-e2e-plan.md)

## Intent

These documents are meant to reduce ambiguity before feature work begins.

- `requirements.md` defines what the system must do now.
- `layered-architecture-baseline.md` defines the top-level layered view of the whole system.
- `core-stability-goals.md` defines what should remain stable in the data and processing core.
- `architecture.md` defines how the system should be shaped.
- `development-guide.md` defines how changes must be implemented.
- `testing-strategy.md` defines how changes must be validated.
- `pytest-xdist-evaluation.md` records what was tried with parallel pytest execution, what improved stability, and why the default path remains conservative for now.
- `backlog.md` captures the staged product backlog.
- `minimal-backlog.md` focuses the team on the current delivery wave.
- `gap-analysis.md` explains the difference between the current scaffold and the agreed target baseline.
- `postgresql-runbook.md` defines the local PostgreSQL baseline and checks.
- `hes-ingest-contract.md` defines the minimal raw ingest contract.
- `hes-schema-checklist.md` defines what to inspect in the real HES schema before raw table design starts.
- `provisional-raw-schema.md` defines the pre-HES-review raw schema we can use to keep moving now.
- `data-layer-architecture.md` defines when to use landing tables and how data should converge into the common raw and final layers.
- `common-raw-interval-model.md` defines why the common raw layer should remain interval-granular and append-only, even when source HES tables are block-oriented.
- `interval-raw-table-design.md` defines the concrete baseline table shapes for packed-source landing, interval-granular common raw, and completeness-state tracking.
- `partitioning-strategy.md` defines the PostgreSQL operational baseline for partitioning, pruning, indexing, and retention on large append-only tables.
- `partitioning-precheck.md` captures the table-by-table design checks that should be completed before turning the core raw and final tables into partitioned PostgreSQL tables.
- `partitioning-implementation-plan.md` translates the partitioning direction into an incremental rollout plan, including the first `hes_read_raw` target, the raw identity and FK implications, and the requirement to test with rows from different months.
- `integration-adapter-management.md` defines how to distinguish field-normalization adapter profiles from runtime adapters that connect to external HES systems.
- `hes-system-management.md` defines the operator-facing HES registry concept above runtime adapters and the intended raw and batch lineage anchor for upstream sources.
- `hes-meter-reference-design.md` defines how HES-side meter reference should remain distinct from the MDM canonical master model while still supporting mapping and operations.
- `hes-centric-operations-plan.md` defines the next HES-first operating slice after the registry baseline, including HES-scoped adapter registration and stronger top-down drill-down.
- `usage-and-billing-ready-architecture.md` defines the next processing/core shape after the current minimal finalization baseline, including the intended `initial -> VEE -> final -> usage` flow.
- `vee-baseline-design.md` defines the first practical VEE persistence boundary, including `initial_measurement`, `vee_execution_log`, `vee_exception`, and the promotion conditions into final.
- `re-vee-baseline-runbook.md` explains when manual re-VEE should be triggered, what operators see in the UI, how synchronous single-object re-VEE differs from future async replay, and how the backend supersedes old VEE exceptions, re-finalizes current data, and recalculates impacted usage windows.
- `bulk-async-vee-replay-design.md` defines the first queue-backed replay request model for HES, batch, and bounded date-range scopes, including request items, pipeline linkage, worker behavior, and operator progress visibility.
- `final-measurement-revision-design.md` defines how `final_measurement` should grow from a single promotion target into a current-plus-history authoritative layer with explicit supersession and revision lineage.
- `usage-transaction-design.md` defines the first downstream usage layer and the boundary between usage-ready and later billing-ready outputs.
- `bill-determinant-design.md` defines the first billing-ready determinant layer that should sit on top of `usage_transaction`, including determinant grain, billing-window prerequisites, and current-plus-history recalculation lineage.
- `billing-lite-boundary-design.md` defines the optional minimal billing slice that may sit on top of `bill_determinant` for small-scale deployment and end-to-end testing, while still preserving a later CIS boundary.
- `billing-context-baseline-design.md` defines the smallest service-point-scoped business context needed so that determinant and later charge calculation stop guessing billing windows.
- `processing-core-persistence-design.md` translates that processing/core direction into a concrete first persistence slice for `initial_measurement`, `vee_execution_log`, `vee_exception`, and the future change in `final_measurement` promotion rules.
- `processing-core-rollout-plan.md` defines the safe staged rollout order for introducing the new processing/core persistence while keeping the current minimal finalization path stable during transition.
- `adapter-runtime-lifecycle.md` defines the proposed minimal state model for runtime adapters and the operator-facing status view.
- `adapter-operations-ui.md` defines the recommended first operator actions and screen scope for runtime adapters.
- `minimal-adapter-operations-boundary.md` defines what runtime adapter control means in the minimal stage, what libraries are in use now, and what is intentionally deferred.
- `adapter-backlog.md` consolidates adapter work into a practical backlog view across delivered, next, and deferred items.
- `polling-adapter-baseline.md` defines the first practical polling-adapter implementation target and boundaries.
- `lp-em-adapter-mapping.md` defines the current mapping baseline from the overseas HES `LP_EM` and `METER` tables into landing and common raw.
- `nuri-aimir-hes-lp-em-polling-adapter.md` defines the first NURI AIMIR HES runtime polling adapter baseline for the overseas deployment on Oracle.
- `adapter-live-hardening-plan.md` defines the next hardening scope for live polling, watermark safety, replay handling, and operator visibility.
- `adapter-test-matrix.md` turns adapter hardening expectations into concrete test scenarios and verification priorities.
- `adapter-operator-runbook.md` defines the minimal-stage operating procedure for adapter visibility, `Run Once`, pause and resume, worker commands, and troubleshooting.
- `adapter-data-model.md` defines the minimum persistent model for adapter definitions, instances, runs, and watermarks.
- `replay-idempotency-operations.md` explains how replay and idempotency currently work, what limits they imply at larger volume, and why bounded runs remain the preferred operating model in the minimal stage.
- `adapter-gap-analysis.md` explains what is already implemented versus what is still missing before runtime adapters are execution-complete.
- `adapter-implementation-sequence.md` defines the recommended order for closing the remaining runtime adapter gap.
- `pipeline-orchestration.md` defines how data should move upward between layers and how administrators should see status on the dashboard.
- `operational-events-and-alerts.md` defines the minimal operator-facing timeline and alert model for integration and processing behavior.
- `minimal-event-alert-boundary.md` defines what the first event and alert implementation must include, what remains deferred, and how current versus history should be handled.
- `operational-event-table-design.md` defines the first concrete persistence baseline for that event and alert model.
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
