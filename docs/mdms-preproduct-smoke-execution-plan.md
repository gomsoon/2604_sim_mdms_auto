# MDMS Preproduct Smoke Execution Plan

## Purpose

This document defines how to execute the first bounded smoke pass in the
`mdms-preproduct` phase.

It complements:

- [mvp-smoke-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-smoke-runbook.md)
- [mvp-known-limitations.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-known-limitations.md)
- [mdms-preproduct-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-plan.md)

The goal is not exhaustive QA.

The goal is to confirm that the current baseline behaves safely across one real
operator-ordered pass and to convert the findings into a small hardening queue.

## Scope

The first bounded smoke pass should cover:

- human authentication and role split
- raw ingest and measurement lineage visibility
- one supported `VEE` action flow
- one supported correction flow
- one supported synthetic missing-interval repair flow
- downstream recalculation visibility
- one billing export request flow
- one admin mutation lineage flow

The first bounded smoke pass should not try to cover:

- unsupported or deferred product breadth
- exhaustive data-volume or performance characterization
- every correction strategy combination
- every web and API permutation of the same action

## Preconditions

Before running the pass, confirm:

- database schema is migrated to current head
- `admin` and `operator` accounts are available
- at least one HES, adapter, service point, device, and measuring component
  are available
- at least one supported correction case exists for:
  - substitution estimation or substitution manual edit
  - synthetic single-slot missing-interval repair
- current regression baseline is green

## Execution order

Use the existing smoke runbook in strict operator order.

Recommended sequence:

1. authentication and role split
2. raw ingest baseline
3. measurement lineage baseline
4. `VEE` exception handling
5. supported correction path
6. synthetic missing-interval repair
7. downstream recalculation
8. billing-lite summary
9. billing export flow
10. admin mutation lineage

## Evidence to capture during the pass

For each step, record only the minimal evidence needed to support triage:

- step name
- pass or fail
- affected object IDs when relevant
  - `vee_exception_id`
  - `manual_edit_audit_id`
  - `estimation_audit_id`
  - `billing_export_request_id`
  - `adapter_run_id`
- one-sentence observation
- if failed:
  - user-facing symptom
  - suspected layer
  - whether the issue looks like a blocker or a bounded hardening fix

Avoid turning the first pass into a long narrative log.

The goal is a short actionable queue.

## Triage rules

Every issue found during the smoke pass should be classified as exactly one of:

- `blocker`
- `same-slice hardening fix`
- `accepted limitation`
- `later backlog item`

Use these decision rules:

### `blocker`

Use when:

- a required smoke step cannot complete
- actor lineage is missing on a sensitive mutation
- a supported correction path corrupts or loses downstream consistency
- auth or role protection fails

### `same-slice hardening fix`

Use when:

- the supported behavior works but wording, visibility, or audit readability is
  confusing
- the defect is narrow and can be fixed without opening a new subsystem
- the issue can be closed together with a focused regression

### `accepted limitation`

Use when:

- the behavior matches an already-documented MVP or preproduct limitation
- the operator implication is already known and tolerable for bounded internal
  use

### `later backlog item`

Use when:

- the issue implies broader product scope
- the fix would require opening a deferred subsystem
- the symptom is real but not urgent for first bounded internal use

## Stop and continue rules

Continue the pass when:

- the issue is only readability or visibility related
- the issue matches an accepted limitation
- the issue is isolated and does not invalidate later smoke steps

Stop the pass early when:

- authentication or authorization fails
- supported correction mutates data incorrectly
- current final lineage becomes inconsistent
- a required operator path cannot proceed at all

## Expected outputs

At the end of the first pass, produce:

- a short list of blockers, if any
- a short list of same-slice hardening fixes
- a short list of accepted limitations confirmed in practice
- a short list of later backlog items that should remain deferred

## Recommended next step after the pass

If no blocker is found:

- do one narrow hardening slice from the smoke findings
- then move to high-traffic visibility polish

If one or more blockers are found:

- fix the blockers first with focused regression
- rerun only the affected smoke steps
- rerun the full bounded pass only if the blockers touched shared services or
  cross-cutting actor and audit behavior
