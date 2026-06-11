# MDMS Preproduct Coverage Uplift Plan

## Purpose

This document defines the recommended next steps for increasing regression
confidence and test coverage beyond the current `mdms-preproduct` baseline.

It intentionally focuses on high-signal work.

It does not recommend blind pursuit of repository-wide `100%`.

## Current starting point

At the latest verified full-regression baseline:

- `590` tests collected
- `590` tests passed in the main regression run
- combined total coverage: `86.28%`
- repository statement coverage: `88.98%`
- repository branch coverage: `75.30%`

See:

- [mdms-preproduct-regression-baseline-review.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-regression-baseline-review.md)

## Completed baseline slices

### Completed 1. Coverage gate semantics cleanup

Goal:

- remove ambiguity about what the repository is actually enforcing

Resolved baseline:

- combined total coverage: `80%` minimum
- repository statement coverage: `88.5%` minimum
- repository branch coverage: `75.0%` minimum

Implementation points:

- [Makefile](/home/tprover/2604_sim_mdms_auto/Makefile)
- [tools/check_coverage_thresholds.py](/home/tprover/2604_sim_mdms_auto/tools/check_coverage_thresholds.py)
- [README.md](/home/tprover/2604_sim_mdms_auto/README.md)
- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
- [mdms-preproduct-testing-hardening.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-testing-hardening.md)

Why this still comes first:

- an explicit branch floor is better than an implied branch promise
- later threshold raises can now happen without policy ambiguity

### Completed 2. Expand browser smoke on the highest-value operator flows

Goal:

- raise confidence in the operator-facing surface without building a huge UI
  test suite

Completed additions:

- dashboard already covered
- VEE exception queue
- VEE exception detail
- replay request list
- replay request detail
- billing export request list
- billing export request detail
- HES detail
- master-data visibility

Primary target file:

- [tests/functional/test_smoke.py](/home/tprover/2604_sim_mdms_auto/tests/functional/test_smoke.py)

This remains a bounded smoke suite, not a full browser regression stack.

## Next priority order

### Priority 1. Strengthen API parity only on critical flows

Goal:

- close the main mismatch between service coverage and public boundary coverage

Recommended first API targets:

- replay request create/cancel/read
- billing export request create/cancel/read
- alert acknowledge/close
- selected admin mutation paths where auth and audit are sensitive

The point is not to duplicate all web assertions.

The point is to protect the public boundary where a regression would matter.

### Priority 2. Add targeted regression around structurally large files

Goal:

- improve confidence where broad route or startup wiring still carries risk

Good candidates:

- [app/blueprints/web.py](/home/tprover/2604_sim_mdms_auto/app/blueprints/web.py)
- [app/__init__.py](/home/tprover/2604_sim_mdms_auto/app/__init__.py)
- [app/services/receive_adapters.py](/home/tprover/2604_sim_mdms_auto/app/services/receive_adapters.py)

Recommended approach:

- do not add abstract low-signal coverage filler
- instead add regression for:
  - newly sensitive routes
  - route-to-service integration boundaries
  - startup/config fallback paths
  - error-handling branches that can affect bounded internal use

### Priority 3. Raise the global threshold only after the next two waves land

Goal:

- move the repository baseline upward in controlled steps

Recommended approach:

1. keep the policy/gate alignment stable
2. land the next API uplift slice
3. land the large-file targeted hardening slice
4. observe the new steady-state coverage
5. raise the global threshold in small increments

Avoid:

- raising the gate first and then scrambling to add low-value tests

## Explicitly deferred work

These are not the recommended first move for the next phase:

- repository-wide pursuit of literal `100%`
- large-scale test-directory reorganization before confidence improves
- converting the whole operator UI into browser-driven coverage
- duplicating every service assertion through both web and API layers
- forcing `xdist` as the default path before the fixture model is ready

## Recommended first implementation slices

### Completed slice 1. Coverage baseline semantics cleanup

Output:

- policy and command alignment
- no ambiguity about what `80%` means

### Completed slice 2. Functional smoke expansion

Output:

- `tests/functional/test_smoke.py` now covers the main operator queues and
  request-detail flows for replay, billing export, HES detail, and
  master-data visibility

### Next slice 3. Replay and export API parity

Output:

- critical request lifecycle boundaries protected beyond service-only coverage

### Next slice 4. Large-file targeted route hardening

Output:

- additional regression around high-value route and startup wiring

## Success condition

The next coverage phase should be considered successful when:

- the gate semantics are explicit and truthful
- browser smoke covers the main operator queues and request-detail flows
- replay and export public boundaries are less dependent on service-only tests
- the global threshold can be raised without filler work
