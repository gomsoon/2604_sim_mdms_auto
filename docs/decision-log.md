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

