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

### Regression testing is mandatory

- Whenever code changes, regression testing must be executed.
- The regression scope should match the impact of the change, but it must include at least the directly affected area plus known adjacent flows.

### Branch coverage is part of the baseline

- The repository should measure branch coverage, not line coverage only.
- The current baseline should enforce a minimum `80%` branch coverage threshold for the application package.
- Thresholds should continue to increase gradually toward higher confidence instead of jumping unrealistically to `100%` all at once.

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
