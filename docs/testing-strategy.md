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

## Recommended test organization

As the repository grows, tests should evolve toward a structure like the following:

- `tests/unit/`
- `tests/integration/`
- `tests/functional/`
- `tests/fixtures/`

## Tooling expectations

- `pytest` is the baseline test runner for unit and integration tests.
- `Playwright` should be evaluated for functional browser-driven testing.
- Test data should be deterministic and easy to understand.

## Test design principles

- Prefer explicit, readable scenarios over overly clever parametrization.
- Name tests by behavior and expected result.
- Keep fixtures small and domain meaningful.
- Ensure each test has a clear reason for existence tied to requirements or regression risk.

## Definition of done for testing

A code change is not complete unless:

- Test cases were added or updated.
- Boundary value analysis was applied where relevant.
- Regression testing was executed.
- The testing evidence matches the scope of the change.

