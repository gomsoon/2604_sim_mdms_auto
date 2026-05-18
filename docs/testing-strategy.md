# Testing Strategy

## Goal

This document defines the minimum testing expectations for all code changes in the repository.

## Core testing rules

### Tests are mandatory when code changes

- Any code change must add or update corresponding test cases.
- A code change without test impact analysis is incomplete.

### Boundary value analysis is required

- Unit test cases must be designed using boundary value analysis wherever applicable.
- Test authors should explicitly consider minimum, maximum, empty, null, duplicate, malformed, and just-inside or just-outside valid ranges.

### Robustness testing should extend boundary testing

- Boundary value analysis is the floor, not the ceiling.
- Test design should expand into robustness testing when behavior is safety- or
  decision-sensitive.
- Robustness-oriented cases should explicitly include:
  - invalid but near-valid values
  - null or empty variants beyond the normal happy path
  - malformed combinations of otherwise valid fields
  - unexpected state combinations near supported operating boundaries

### Worst-case testing should be selective

- Worst-case combinational testing is valuable for small, decision-heavy logic.
- It should not be applied blindly to the whole repository.
- It should be concentrated where the input space is small enough to stay
  understandable and where the decision outcome is operationally important.

### Regression testing is mandatory

- Whenever code changes, regression testing must be executed.
- The regression scope should match the impact of the change, but it must include at least the directly affected area plus known adjacent flows.

### Branch coverage is part of the baseline

- The repository should measure branch coverage, not line coverage only.
- The current baseline should enforce a minimum `80%` branch coverage threshold for the application package.
- Thresholds should continue to increase gradually toward higher confidence instead of jumping unrealistically to `100%` all at once.
- The repository should prefer a dual policy:
  - gradual global threshold increases
  - stronger local expectations for high-risk decision logic

### MC/DC-style testing is recommended for critical decision logic

- Modified condition or decision coverage is not required for all code.
- It is strongly recommended for logic that can change measurement values,
  correction outcomes, finalization state, or operator-visible blocking
  decisions.
- At the current repository stage, the highest-priority candidates are:
  - `VEE`
  - `estimation`
  - `manual edit`
  - correction-policy and replay or export eligibility checks where the
    decision tree is small and safety-relevant

## Test layers

### Unit testing

- Unit tests must be written with `pytest`.
- Unit tests should target service logic, validation rules, parsing behavior, duplicate detection, mapping logic, and any reusable utility behavior.
- Unit tests should run quickly and be suitable for frequent local execution.

### Integration and API testing

- API-level tests should verify request and response behavior for key ingestion and operator flows.
- Integration-oriented tests should validate the interaction between Flask routes, service logic, and persistence for critical scenarios.

### Functional testing

- Functional end-to-end testing should be evaluated using tools such as `Playwright`.
- Playwright is the preferred candidate when operator UI flows become important enough to automate.
- At the minimal stage, functional testing may start with a small smoke suite focused on critical operator flows such as dashboard access, raw data visibility, and exception visibility.

## Boundary value analysis guidance

When adding or modifying logic, test at least the following classes of values where relevant:

- Empty payload vs single-record payload vs multi-record payload
- Missing required fields vs fully valid fields
- Duplicate timestamp or identifier combinations vs unique combinations
- Lowest acceptable numeric value vs slightly below it
- Highest acceptable numeric value vs slightly above it
- Valid timestamp format vs malformed timestamp
- Known master-data mapping vs unknown mapping
- Supported locale values such as `en` and `ko` vs unsupported locale fallback

## Robustness testing guidance

When behavior is correction-sensitive, workflow-sensitive, or policy-sensitive,
expand beyond classic boundary values to include:

- valid single condition vs multiple simultaneous invalid conditions
- valid status transition vs forbidden status transition
- supported action with required lineage vs missing lineage
- supported actor path vs missing actor or wrong-role path
- supported event context vs unsupported or conflicting event context
- supported revision state vs stale or superseded state

The goal is to verify that the system fails clearly and safely near the
operational boundary, not only at the nominal boundary.

## Worst-case guidance

Use worst-case combinational coverage selectively when:

- the decision space is intentionally small
- the logic changes values or state
- a missed combination could cause silent operator harm or incorrect downstream
  recalculation

Typical examples in this repository:

- VEE rule blocking versus warning conditions
- synthetic missing-interval eligibility
- estimation strategy or blocking choice
- manual-edit allowed versus blocked decisions
- export action eligibility such as cancel, rerun, and recreate

Avoid forcing worst-case combinational coverage for:

- basic CRUD wiring
- broad visibility queries
- simple template rendering
- low-risk serializer formatting

## Regression testing guidance

### Minimum expectation per change

- Run all relevant `pytest` unit and integration tests for the touched behavior.
- Re-run adjacent tests that cover neighboring logic likely to regress.
- If UI behavior changed, perform at least manual smoke verification and evaluate Playwright coverage.

### Regression examples for this project

- Changes to raw read ingestion should re-test duplicate detection, canonical creation, and exception creation.
- Changes to mapping logic should re-test both mapped and unmapped scenarios.
- Changes to user-facing text or locale logic should re-test English and Korean presentation paths.
- Changes to external integration boundaries should re-test adapter behavior and failure handling.
- Changes to replay, idempotency, or adapter watermark behavior should re-test both exact replay and bounded multi-run scenarios.
- Changes to VEE, estimation, or manual edit logic should re-test the full
  decision path, adjacent exception states, and downstream recalculation.
- Changes to actor, audit, or authorization logic should re-test both allowed
  and forbidden paths together with visibility fallback behavior.

## Recommended test organization

As the repository grows, tests should evolve toward a structure like the following:

- `tests/unit/`
- `tests/integration/`
- `tests/functional/`
- `tests/fixtures/`

## Tooling expectations

- `pytest` is the baseline test runner for unit and integration tests.
- `pytest-cov` should be used to collect branch coverage for the application package.
- `pytest-xdist` should be evaluated for the main non-functional regression suite when the fixtures remain process-safe and schema-isolated.
- `Playwright` should be evaluated for functional browser-driven testing.
- Test data should be deterministic and easy to understand.
- For integration adapters, bounded replay and repeated-run verification should remain part of the regression baseline.

## Parallel execution status

- `pytest-xdist` is now part of the development dependency set and remains a valid direction for future acceleration work.
- A validation attempt with `n=4` workers was performed on the current 16-core environment.
- Several fixture and harness variations were explored during the evaluation.
- Even with those experiments, repeated `xdist` validation remains flaky enough that the repository baseline should stay serial for `make test`.
- Browser-driven functional tests should continue to run in a separate serial command and should not be mixed into the main non-functional pytest session unless that path is explicitly hardened.
- Future `xdist` enablement should be retried only after the PostgreSQL fixture path is tuned further for repeated parallel connection churn.

## Test design principles

- Prefer explicit, readable scenarios over overly clever parametrization.
- Name tests by behavior and expected result.
- Keep fixtures small and domain meaningful.
- Ensure each test has a clear reason for existence tied to requirements or regression risk.
- Prefer bounded source windows in adapter tests so replay and idempotency behavior can be reasoned about explicitly.
- For decision-heavy logic, prefer tests that show which condition independently
  changes the outcome.
- Do not chase global `100%` coverage blindly where the resulting tests add
  little signal.
- Do pursue near-complete branch and condition confidence in high-risk service
  logic.

## Coverage direction for the `mdms-preproduct` phase

The current repository should evolve coverage in two tracks:

1. Global branch threshold:
   - raise gradually from the current baseline toward stronger confidence
   - do not require an immediate repository-wide jump to `100%`

2. High-risk service target:
   - aim for near-complete branch coverage on:
     - `VEE`
     - `estimation`
     - `manual edit`
   - strengthen those same areas with robustness and MC/DC-style test design

The point of this phase is stronger confidence where incorrect decisions would
be most damaging, not a vanity metric on low-risk code paths.

## Definition of done for testing

A code change is not complete unless:

- Test cases were added or updated.
- Boundary value analysis was applied where relevant.
- Regression testing was executed.
- The testing evidence matches the scope of the change.

## Related documents

- [acceptance-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/acceptance-test-matrix.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [adapter-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-test-matrix.md)
- [pytest-xdist-evaluation.md](/home/tprover/2604_sim_mdms_auto/docs/pytest-xdist-evaluation.md)
- [mdms-preproduct-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-plan.md)
