# MDMS Preproduct Regression Baseline Review

## Purpose

This document reviews the current regression-testing baseline for the
implemented `mdms-preproduct` system.

It is intended to answer three practical questions:

- what regression coverage already exists
- which parts of the current stack are already well protected
- where the next testing-coverage uplift should focus first

## Current baseline summary

### Test inventory

The current repository-level regression suite is already broad.

At the current review point:

- `586` tests are collected by the main `pytest` suite
- the main regression path remains serial
- functional browser smoke remains a separate command

Primary commands:

- `make test`
  - `.venv/bin/python -m pytest --cov-fail-under=80`
- `make test-functional`
  - `.venv/bin/python -m pytest tests/functional`

Reference:

- [README.md](/home/tprover/2604_sim_mdms_auto/README.md)
- [Makefile](/home/tprover/2604_sim_mdms_auto/Makefile)
- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)

### Last verified full-regression baseline

The last verified full non-functional regression baseline for the current
preproduct close-out path was:

- `586 passed`
- combined total coverage: `86.28%`
- repository statement coverage: `88.98%`
- repository branch coverage: `75.30%`

This is the most recent fully verified baseline before this review note.

## Current regression layers

### 1. Service and model regression

The repository already has broad service and persistence coverage across:

- adapter runtime
- auth
- billing context
- usage and billing
- replay and export
- VEE
- estimation
- manual edit
- HES and master-data
- operational events

Representative suites:

- [test_adapter_execution.py](/home/tprover/2604_sim_mdms_auto/tests/test_adapter_execution.py)
- [test_auth_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_auth_web.py)
- [test_estimation_service.py](/home/tprover/2604_sim_mdms_auto/tests/test_estimation_service.py)
- [test_manual_edit_service.py](/home/tprover/2604_sim_mdms_auto/tests/test_manual_edit_service.py)
- [test_vee_rule_evaluation.py](/home/tprover/2604_sim_mdms_auto/tests/test_vee_rule_evaluation.py)
- [test_vee_service.py](/home/tprover/2604_sim_mdms_auto/tests/test_vee_service.py)
- [test_finalization_service.py](/home/tprover/2604_sim_mdms_auto/tests/test_finalization_service.py)
- [test_billing_export_service.py](/home/tprover/2604_sim_mdms_auto/tests/test_billing_export_service.py)
- [test_visibility_service.py](/home/tprover/2604_sim_mdms_auto/tests/test_visibility_service.py)

### 2. Web regression

The operator-facing UI is already protected by strong route and rendering
coverage.

The heaviest web suites are:

- [test_visibility_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_visibility_web.py)
  - `95` tests
- [test_vee_exception_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_vee_exception_web.py)
  - `20` tests
- [test_hes_system_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_hes_system_web.py)
  - `20` tests
- [test_master_data_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_master_data_web.py)
  - `17` tests
- [test_auth_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_auth_web.py)
  - `16` tests
- [test_operational_event_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_operational_event_web.py)
  - `12` tests
- [test_adapter_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_adapter_web.py)
  - `13` tests
- [test_vee_replay_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_vee_replay_web.py)
  - `8` tests

This means operator-facing wording, empty-state behavior, actor visibility,
drill-down entry, and route-level behavior are already under meaningful
regression protection.

### 3. API regression

API regression exists, but it is thinner than service and web regression.

Representative suites:

- [test_ingest_contract_api.py](/home/tprover/2604_sim_mdms_auto/tests/test_ingest_contract_api.py)
- [test_receive_adapter_api.py](/home/tprover/2604_sim_mdms_auto/tests/test_receive_adapter_api.py)

The current repository posture clearly prioritizes:

- service correctness first
- operator web correctness second
- API parity third

### 4. Functional smoke regression

Browser-driven smoke regression exists and is intentionally narrow.

Current suite:

- [tests/functional/test_smoke.py](/home/tprover/2604_sim_mdms_auto/tests/functional/test_smoke.py)

Current smoke intent:

- dashboard reachability
- raw-read visibility
- exception queue and detail reachability

This is useful, but still closer to a bounded smoke baseline than to broad UI
workflow automation.

## High-signal strengths in the current baseline

### Decision-heavy correction logic is already the strongest area

The highest-risk logic is already where the strongest explicit hardening exists.

That includes:

- `VEE`
- `estimation`
- `manual edit`

Reference:

- [mdms-preproduct-testing-hardening.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-testing-hardening.md)

This is the right current shape for the repository.

### Operator-facing accountability is now tested, not only implemented

Recent slices already locked regression evidence for:

- `user_action_audit` on critical read and execute flows
- operational-event action snapshot readability
- admin mutation actor visibility on HES and master-data views

That means the repository is no longer only feature-complete in those areas.
It is also regression-aware.

### Web wording and visibility are unusually well protected for this phase

The visibility-polish work was done with tests instead of ad hoc UI edits.

That matters because:

- operator text changed frequently
- empty-state and placeholder behavior changed frequently
- route counts and detail pages grew quickly

The current baseline has meaningful regression protection for that operator
surface.

## Current gaps and important caveats

### Coverage-policy wording has now been made explicit

The repository no longer relies on an implied `80% branch coverage` meaning.

The default regression command now enforces:

- combined total coverage: `80%` minimum
- repository statement coverage: `88.5%` minimum
- repository branch coverage: `75.0%` minimum

This is intentionally aligned with the latest verified repository baseline:

- statement coverage currently sits near `88.98%`
- branch coverage currently sits near `75.30%`

That gives the repository:

- a stable explicit gate today
- a clear branch floor that cannot silently regress
- room to raise the branch threshold in later high-signal hardening slices

### Functional browser coverage is still intentionally thin

The browser smoke suite is valuable, but still small relative to the operator
surface now implemented.

The current suite does not yet broadly lock:

- replay request list and detail
- billing export list and detail
- VEE queue and detail
- HES and master-data admin flows
- operational-event detail

### API coverage is not yet as strong as web and service coverage

The current stack has strong service tests and strong web tests.

Compared with those layers, API regression is still narrower and more selective.

### Some structurally large files remain more lightly protected than the
highest-risk logic

Examples:

- [app/blueprints/web.py](/home/tprover/2604_sim_mdms_auto/app/blueprints/web.py)
- [app/__init__.py](/home/tprover/2604_sim_mdms_auto/app/__init__.py)
- [app/services/receive_adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/receive_adapters.py)

That does not necessarily mean the current state is unsafe.

It does mean that the next coverage uplift should not be a random global push.
It should focus where structural breadth and real operating risk overlap.

## Recommended interpretation of the current baseline

The repository is already in a good state for bounded internal regression:

- high-risk decision logic is well targeted
- operator web regression is broad
- accountability regression is no longer missing
- PostgreSQL-backed schema-isolated tests provide stable persistence coverage

The next testing move should not be blind repository-wide test inflation.

The next move should be:

1. fix the coverage-policy and gate mismatch
2. expand browser smoke for a few critical flows
3. add API or route parity only where it closes a real regression gap

## Recommended next document

The natural follow-up to this review is:

- [mdms-preproduct-coverage-uplift-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-coverage-uplift-plan.md)
