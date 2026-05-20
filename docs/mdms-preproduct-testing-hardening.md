# MDMS Preproduct Testing Hardening

## Purpose

This document defines how testing should be strengthened during the
`mdms-preproduct` phase.

It focuses on confidence improvement in the highest-risk logic rather than a
blind whole-repository coverage chase.

## Why this phase matters

The repository has already reached MVP close-out.

That changes the testing goal.

The next goal is not only to prove that features exist.

The next goal is to make sure the most sensitive operator actions and
value-changing decisions behave safely near their real operating boundaries.

## Primary testing directions

### 1. Expand from classic BVA to robustness testing

Continue using boundary value analysis as the baseline.

Then strengthen it with:

- invalid-but-near-valid inputs
- conflicting field combinations
- unsupported status combinations
- wrong-role and wrong-actor paths
- stale, superseded, or no-longer-current state

This is especially important for:

- VEE transitions
- estimation eligibility and application
- manual-edit validation and application
- replay and export action eligibility

### 2. Use selective worst-case testing

Worst-case combinational testing should be applied only where:

- the input set is small enough to stay reviewable
- the decision can change state, value, or blocking behavior

Priority candidates:

- VEE rule blocking and warning logic
- synthetic missing-interval eligibility
- event-aware correction-policy decisions
- export cancel and recovery eligibility

### 3. Apply MC/DC-style strengthening to critical decision logic

MC/DC-style testing is especially appropriate for:

- `app/services/vee.py`
- `app/services/estimation.py`
- `app/services/manual_edits.py`

The intent is to demonstrate that:

- each condition can independently affect the outcome
- blocking and non-blocking paths are both proven
- downstream recalculation consequences are still correct

## Coverage policy for this phase

### Global coverage

Keep repository-wide branch coverage as a gradual target.

Recommended approach:

- keep the current gate stable while strengthening tests
- raise the global branch threshold in controlled steps later
- do not hold the whole repository hostage to low-signal coverage work

### Local high-risk coverage

For `VEE`, `estimation`, and `manual edit`:

- target near-complete branch confidence
- prefer explicit condition-driven tests over generic happy-path expansion
- use regression suites that prove both allowed and blocked behavior

## First recommended implementation order

### Slice 1. Testing-strategy baseline update

Goal:

- lock the stronger terminology and expectations in documentation

Status:

- handled by this document set

### Slice 2. VEE decision-test hardening

Goal:

- improve robustness and decision coverage for blocking, warning, and
  re-evaluation paths

Suggested focus:

- blocking versus warning transitions
- duplicate and missing-interval edge combinations
- actor-sensitive or state-sensitive exception transitions
- event-context predicate matrices for tamper, outage, and supplied-versus-looked-up
  context precedence

Recommended execution order:

1. rule-evaluation hardening in `tests/test_vee_rule_evaluation.py`
2. baseline-evaluation and summary-code hardening in `tests/test_vee_service.py`
3. finalization adjacency and transition robustness in
   `tests/test_finalization_service.py`

### Slice 3. Estimation decision-test hardening

Goal:

- strengthen substitution and synthetic estimation tests around eligibility,
  blocking, and downstream effects

Suggested focus:

- supported versus unsupported exception codes
- synthetic single-slot eligibility and blocked reasons
- actor lineage and VEE resolution side effects

### Slice 4. Manual-edit decision-test hardening

Goal:

- strengthen manual-edit validation, blocking, and downstream recalculation

Suggested focus:

- supported versus unsupported exception codes
- correction-policy constrained paths
- audit and actor-lineage persistence

## Test evidence expectations

For each hardening slice:

1. show the decision or risk being strengthened
2. add or update focused regression tests
3. run the smallest relevant suite first
4. run the full suite when shared services or core persistence are touched

## Explicitly not the first goal

This phase should not begin with:

- repository-wide pursuit of literal `100%` branch coverage
- MC/DC-style effort on low-risk CRUD and rendering code
- large-scale test rewrites before risk-based prioritization

The right first move is stronger confidence in the logic that changes values,
state, and operator decisions.
