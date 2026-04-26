# Decision Log

## Purpose

This document records current architectural and process decisions so that the team can distinguish locked baseline decisions from open questions.

## How to use this log

- Add stable project decisions here after they are agreed
- Use the open questions section for unresolved items that still need a decision
- When a decision changes, update the old entry instead of silently drifting

## Locked decisions

### D-001. Minimal stage starts with PostgreSQL

- Status: locked
- Summary: PostgreSQL is the primary database baseline even for the minimal stage
- Why: It better matches target operational reality and avoids SQLite-driven shortcuts
- Related docs:
  - [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
  - [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)

### D-002. Persistent vocabulary follows the backlog PDF

- Status: locked
- Summary: Persistence naming should align with `ingest_batch`, `hes_read_raw`, `hes_event_raw`, `canonical_measurement`, and `ingest_error_log`
- Why: Shared vocabulary reduces drift between schema, backlog, implementation, and discussion
- Related docs:
  - [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)
  - [persistence-renaming-plan.md](/home/tprover/2604_sim_mdms_auto/docs/persistence-renaming-plan.md)

### D-003. Structural review precedes feature work

- Status: locked
- Summary: Before adding features, the team must assess structure and refactor first if the current design is not suitable
- Why: This reduces compounding debt and keeps later expansion feasible
- Related docs:
  - [development-guide.md](/home/tprover/2604_sim_mdms_auto/docs/development-guide.md)

### D-004. Tests are mandatory for code changes

- Status: locked
- Summary: Code changes require tests, boundary value analysis, and regression testing
- Why: The project is data-sensitive and regressions in ingest or mapping logic are costly
- Related docs:
  - [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
  - [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)

### D-005. English and Korean are the baseline locales

- Status: locked
- Summary: Operator-facing features must support at least English and Korean
- Why: Locale support is a baseline requirement and should not become a late retrofit
- Related docs:
  - [i18n-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/i18n-strategy.md)

### D-006. UTF-8 is mandatory

- Status: locked
- Summary: All source and documentation files must be maintained in UTF-8, and Korean corruption must be checked before reflecting changes
- Why: Multilingual reliability is part of project quality
- Related docs:
  - [development-guide.md](/home/tprover/2604_sim_mdms_auto/docs/development-guide.md)
  - [requirements.md](/home/tprover/2604_sim_mdms_auto/docs/requirements.md)

### D-007. Provisional raw schema can proceed before the real HES schema review

- Status: locked
- Summary: We may proceed with a provisional raw-table design before receiving the company's actual HES schema, as long as assumptions remain explicit and adjustable
- Why: This keeps project momentum without falsely treating unknown source details as finalized
- Related docs:
  - [provisional-raw-schema.md](/home/tprover/2604_sim_mdms_auto/docs/provisional-raw-schema.md)
  - [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)

### D-008. Lightweight orchestration is preferred over a heavy workflow engine in the minimal stage

- Status: locked
- Summary: The minimal stage should use a simple schedule-first orchestration model with visible processing status, rather than adopting a heavy workflow engine immediately
- Why: It fits the current scope better and still supports operator visibility, retries, and future extension
- Related docs:
  - [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
  - [implementation-roadmap.md](/home/tprover/2604_sim_mdms_auto/docs/implementation-roadmap.md)

### D-009. Well-formed remains a semantic checkpoint in the minimal stage

- Status: locked
- Summary: In the minimal stage, `well_formed` is treated as an explicit semantic validation step before promotion to `final_measurement`, not as its own persistent table
- Why: This keeps stage meaning explicit without introducing an extra table before VEE and later business rules are ready
- Related docs:
  - [core-stability-goals.md](/home/tprover/2604_sim_mdms_auto/docs/core-stability-goals.md)
  - [domain-glossary.md](/home/tprover/2604_sim_mdms_auto/docs/domain-glossary.md)

### D-010. Adapter profiles and runtime adapters are separate concepts

- Status: locked
- Summary: The project must distinguish between lightweight adapter profiles used for field normalization and runtime adapters used for source connectivity, polling, receive handling, and operational control
- Why: This avoids mixing payload mapping concerns with lifecycle and connectivity management, and gives the integration layer a cleaner long-term shape
- Related docs:
  - [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
  - [architecture.md](/home/tprover/2604_sim_mdms_auto/docs/architecture.md)

### D-011. Common raw interval reads remain append-only and interval-granular

- Status: locked
- Summary: The MDM common raw read model should store one interval read per row and should not copy vendor-specific packed block layouts into the common raw layer
- Why: This keeps downstream processing vendor-neutral, reduces hot-row update patterns, and makes completeness and replay behavior easier to audit
- Related docs:
  - [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
  - [data-layer-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/data-layer-architecture.md)

### D-012. Packed HES read blocks belong in landing or adapter expansion, not in common raw

- Status: locked
- Summary: Source-specific packed rows such as `LP_EM` block rows may be preserved in landing or adapter replay storage, but must be expanded before entering the common raw read layer
- Why: This allows the project to support multiple HES layouts without forcing one vendor's block format into the internal MDM core
- Related docs:
  - [lp-em-adapter-mapping.md](/home/tprover/2604_sim_mdms_auto/docs/lp-em-adapter-mapping.md)
  - [nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)

### D-013. Large append-only read tables should start with monthly time-based partitioning

- Status: locked
- Summary: The initial PostgreSQL baseline for large append-only raw and final read tables should use monthly time-based partitioning
- Why: This gives the project a practical balance of pruning effectiveness, retention management, and operational simplicity before scale grows further
- Related docs:
  - [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)
  - [interval-raw-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/interval-raw-table-design.md)

### D-014. `raw_interval_window_state` is a short-horizon operational table

- Status: locked
- Summary: `raw_interval_window_state` should retain only active and recent windows, sized roughly as `window period + operational alpha`, rather than behaving like a long-term archive
- Why: Its purpose is fast completeness and late-arrival state management, not authoritative long-term audit storage
- Related docs:
  - [interval-raw-table-design.md](/home/tprover/2604_sim_mdms_auto/docs/interval-raw-table-design.md)
  - [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)

### D-015. Minimal runtime adapter control is state-driven and worker-backed

- Status: locked
- Summary: In the minimal stage, adapter operations should use UI-driven state changes plus a separate worker execution path, rather than in-process scheduler control or OS-level process control from Flask
- Why: This keeps adapter operations auditable and safe without turning the web application into a long-running orchestration platform too early
- Related docs:
  - [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
  - [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
  - [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)

### D-016. Minimal stage includes an operational event timeline and alert subset

- Status: locked
- Summary: The minimal stage should expose important integration and processing behavior through a unified operational event timeline, with alerts treated as an operator-actionable subset of those events
- Why: Operators need one readable history and one clear set of urgent conditions without having to infer everything from logs, exception rows, and run tables separately
- Related docs:
  - [operational-events-and-alerts.md](/home/tprover/2604_sim_mdms_auto/docs/operational-events-and-alerts.md)
  - [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
  - [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)

### D-017. Minimal-stage alert conditions remain code-backed but registry-driven

- Status: locked
- Summary: In the minimal stage, alert-condition evaluation should remain in application code, but it should be organized through a table-like in-code rule registry rather than scattered condition-specific branches
- Why: This keeps the first implementation simple and testable while preserving a clean migration path toward a database-backed rule-definition table if operator-tunable thresholds or a larger alert catalog become necessary
- Related docs:
  - [minimal-event-alert-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-event-alert-boundary.md)
  - [operational-events-and-alerts.md](/home/tprover/2604_sim_mdms_auto/docs/operational-events-and-alerts.md)
  - [adapter-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-backlog.md)

### D-018. Replay-safe adapter operation remains bounded-window-first in the minimal stage

- Status: locked
- Summary: Replay and idempotency are currently strong enough for bounded polling and repeated incremental runs, but broader recovery and backfill should still be executed as multiple bounded runs rather than one unbounded load
- Why: The current implementation prioritizes correctness and traceability through application-level replay checks, landing reuse, and completeness-state updates, which is appropriate now but can become expensive at larger volume before stronger database-assisted dedupe and concurrency hardening are in place
- Related docs:
  - [replay-idempotency-operations.md](/home/tprover/2604_sim_mdms_auto/docs/replay-idempotency-operations.md)
  - [adapter-live-hardening-plan.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-live-hardening-plan.md)
  - [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)

### D-019. HES systems should be modeled separately from runtime adapters

- Status: locked
- Summary: The project should model an operator-managed `hes_system` as the parent source object above runtime adapters, rather than treating `adapter_instance` as both the HES and the execution unit
- Why: One upstream HES can require multiple runtime adapters over time, and operators need a stable HES registry concept for source management, lineage, and UI grouping
- Related docs:
  - [hes-system-management.md](/home/tprover/2604_sim_mdms_auto/docs/hes-system-management.md)
  - [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
  - [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)

### D-020. `hes_read_raw` partitioning may proceed before replay-registry extraction

- Status: locked
- Summary: The long-term design direction is to move global replay guarantees out of partitioned fact tables and into a dedicated support structure such as a replay registry, but the project may still apply the first `hes_read_raw` partition migration before that extraction is implemented
- Why: This allows the team to move partitioning forward incrementally, preserve the current replay and idempotency behavior temporarily, and use real regression evidence to decide when registry extraction becomes operationally necessary
- Related docs:
  - [partitioning-precheck.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-precheck.md)
  - [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)
  - [replay-idempotency-operations.md](/home/tprover/2604_sim_mdms_auto/docs/replay-idempotency-operations.md)

### D-021. The first partition migration must be verified with rows from different months

- Status: locked
- Summary: The first partition migration is not considered validated unless tests insert and query rows from at least two different calendar months
- Why: A single-month test can pass without proving real partition routing, child-table creation, or cross-partition query behavior
- Related docs:
  - [partitioning-implementation-plan.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-implementation-plan.md)
  - [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)

### D-022. Null-`measured_at` raw rows stay in `hes_read_raw` through a `DEFAULT` partition in the first rollout

- Status: locked
- Summary: The first `hes_read_raw` partition rollout should keep raw validation-error rows inside the same raw table by routing null-`measured_at` rows into a `DEFAULT` partition rather than splitting them into a separate invalid-raw table
- Why: This preserves simple lineage, avoids premature table proliferation, and still leaves room for later hardening if null-timestamp volume or row-movement complexity becomes unacceptable
- Related docs:
  - [partitioning-implementation-plan.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-implementation-plan.md)
  - [partitioning-precheck.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-precheck.md)
  - [partitioning-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/partitioning-strategy.md)

### D-023. Processing core should separate `canonical`, `initial`, `VEE`, `final`, and `usage`

- Status: locked
- Summary: The next processing/core expansion should explicitly separate `canonical_measurement`, `initial_measurement`, `vee_execution_log`, `vee_exception`, `final_measurement`, and `usage_transaction` rather than treating the current minimal finalization path as the finished business-processing architecture
- Why: This keeps mapping, business validation, finalization, and downstream usage calculation distinct, auditable, and easier to extend toward estimation, re-VEE, and billing-oriented outputs later
- Related docs:
  - [usage-and-billing-ready-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/usage-and-billing-ready-architecture.md)
  - [vee-baseline-design.md](/home/tprover/2604_sim_mdms_auto/docs/vee-baseline-design.md)
  - [usage-transaction-design.md](/home/tprover/2604_sim_mdms_auto/docs/usage-transaction-design.md)

### D-024. `usage_transaction` should precede later billing-ready determinant generation

- Status: locked
- Summary: The first downstream business-output layer should be `usage_transaction`, with `bill_determinant` intentionally deferred as a later billing-ready layer
- Why: This creates a stable bridge between finalized measurements and billing-oriented outputs without overloading the first processing/core expansion with tariff, demand, and billing-cycle logic
- Related docs:
  - [usage-and-billing-ready-architecture.md](/home/tprover/2604_sim_mdms_auto/docs/usage-and-billing-ready-architecture.md)
  - [usage-transaction-design.md](/home/tprover/2604_sim_mdms_auto/docs/usage-transaction-design.md)

## Open questions

### O-001. What is the first production-like HES payload shape

- Status: open
- Why it matters: The contract document exists, but real upstream samples may force changes in field naming or optionality
- Current direction: Start with the documented JSON contract and refine when real samples arrive
- Related docs:
  - [hes-ingest-contract.md](/home/tprover/2604_sim_mdms_auto/docs/hes-ingest-contract.md)

### O-002. Should file-based ingest be included in the first minimal delivery

- Status: open
- Why it matters: The backlog allows API or file loader; delivery scope should avoid ambiguity
- Current direction: Prioritize API-first unless a real integration constraint suggests otherwise

### O-003. How strict should idempotency be in the first implementation

- Status: open
- Why it matters: Envelope-level duplicate handling can affect schema constraints and error semantics
- Current direction: Keep it explicit in contract and revisit during PostgreSQL schema design

### O-004. What exact migration baseline should be preserved

- Status: open
- Why it matters: The project can either preserve the interim schema history or create the first durable PostgreSQL migration directly with target names
- Current direction: Prefer the target-name baseline unless keeping interim local data becomes important
- Related docs:
  - [migration-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/migration-strategy.md)

### O-005. Which provisional raw columns will be confirmed by the real HES schema unchanged

- Status: open
- Why it matters: The provisional schema is intentionally flexible, but next week's HES review must convert assumptions into confirmed columns
- Current direction: Keep stable core columns and adjust source-specific details after the HES review
- Related docs:
  - [provisional-raw-schema.md](/home/tprover/2604_sim_mdms_auto/docs/provisional-raw-schema.md)
  - [hes-schema-checklist.md](/home/tprover/2604_sim_mdms_auto/docs/hes-schema-checklist.md)

### O-006. What exact scheduler and run-metadata implementation should be used

- Status: open
- Why it matters: The orchestration principle is agreed, but the specific scheduler, worker model, and metadata-table design still need implementation decisions
- Current direction: Keep the model lightweight and schedule-first, and defer exact tooling until implementation work begins
- Related docs:
  - [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)

### O-007. What is the minimum runtime adapter management model after the current minimal stage

- Status: open
- Why it matters: The project now has adapter profiles, but production-like HES integration will need operational objects such as adapter instances, run history, and lifecycle control
- Current direction: Keep runtime adapter implementations code-backed for now, but move toward operator-managed adapter instances with `admin_state`, adapter run history, and a derived operator-facing status model
- Related docs:
  - [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
  - [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
  - [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)

### O-008. What exact runtime adapter actions should the first operator UI allow

- Status: open
- Why it matters: Too little control makes runtime adapters hard to operate, but too much control too early increases safety and audit risk
- Current direction: Start with `Enable`, `Pause`, `Run Once`, and `View Runs`, and defer more destructive or code-like actions
- Related docs:
  - [adapter-operations-ui.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operations-ui.md)
  - [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)

### O-009. What should the first polling adapter implementation include and exclude

- Status: open
- Why it matters: The project needs a production-like runtime adapter path, but the first polling implementation must remain intentionally narrow
- Current direction: Start with one company-HES polling adapter for raw reads, explicit source watermarking, schedule plus `Run Once`, and operator visibility before broader connector expansion
- Related docs:
  - [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
  - [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)

### O-010. What exact completeness-state shape should accompany interval-granular common raw

- Status: open
- Why it matters: The project now prefers append-only interval rows in common raw, but the exact table shape, bitmap strategy, and late-update semantics for completeness tracking still need implementation choices
- Current direction: Add a dedicated completeness or window-state table rather than using packed raw-row updates as the missing-data mechanism
- Related docs:
  - [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
  - [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)

## Deferred decisions

### X-001. Full localization platform

- Status: deferred
- Why deferred: The minimal stage needs locale readiness, not a full translation management platform

### X-002. Advanced VEE exception model

- Status: deferred
- Why deferred: Minimal stage should focus on ingest error semantics first

### X-003. Billing and CIS payload finalization

- Status: deferred
- Why deferred: Those belong to later phases after minimal flow credibility is established

## Change control guidance

- If a locked decision is challenged, record the proposed replacement explicitly
- Do not let implementation quietly diverge from a locked decision
- When a decision affects contracts, naming, or testing expectations, update the linked docs in the same change
