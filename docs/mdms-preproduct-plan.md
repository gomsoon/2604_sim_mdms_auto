# MDMS Preproduct Plan

## Purpose

This document defines the recommended work mode for the `mdms-preproduct`
phase immediately after MVP close-out.

The goal is not new subsystem expansion.

The goal is to make the current baseline easier, safer, and clearer to operate
through bounded internal use.

## Current baseline snapshot

- `MVP close-out` is complete and tagged
- auth baseline and actor-lineage propagation are complete across the current
  sensitive mutation flows
- first-wave decision-test hardening is complete for:
  - `VEE`
  - `estimation`
  - `manual edit`
- an automated bounded smoke-evidence pass has been executed against the
  runbook mapping with no unplanned foundational blocker observed
- the first visibility-polish slices are complete for:
  - export and adapter runtime-versus-human actor clarity
  - `vee_exception` queue and detail wording clarity
  - replay request list and detail readability
  - correction detail consistency across `vee`, `estimation`, and
    `manual edit`
  - stale-warning and blocked-reason wording cleanup across export and
    correction views
  - billing export wording follow-through across request lifecycle, progress,
    and failure wording
  - cross-view wording and i18n consistency across export and correction
    details
  - stale-warning and blocked-reason second-pass cleanup across replay failure
    wording and correction blocked-guidance fallback
  - lower-traffic composite-page empty-state wording polish across
    `hes_system_detail` and `dashboard` subsection empties
- direct live-ingest execution can still be added later if a stricter
  operator-run smoke record is needed
- the next highest-value visibility work is master-data sectioned empty-state
  cleanup, followed by a broader glossary and locale sweep only if repeated
  use still shows terminology drift

## Operating principles

- prefer bug fix, audit clarity, and visibility polish over new feature breadth
- keep each slice small enough to add or update regression coverage in the same
  change set
- use real internal operator feedback to choose priorities
- treat accepted MVP limitations as known constraints, not as hidden bugs

## Immediate workstreams

### 1. Smoke-pass-driven issue triage

Start with one bounded pass using:

- [mvp-smoke-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-smoke-runbook.md)
- [mvp-known-limitations.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-known-limitations.md)

Every issue found during the pass should be classified as one of:

- `blocker`
- `same-slice hardening fix`
- `accepted limitation`
- `later backlog item`

Key rule:

- if a problem can be fixed without opening a new subsystem, prefer the fix now

### 2. High-traffic visibility polish

Prioritize screens that operators are expected to use repeatedly:

- `vee_exception` queue and detail
- `estimation_audit` detail and key list visibility
- `manual_edit_audit` detail and key list visibility
- replay request list and detail
- billing export request list and detail
- adapter detail and recent runs

Typical polish targets:

- clearer actor display
- clearer runtime-versus-human identity display
- more obvious status or blocked reason wording
- easier drill-down to the next relevant object

Use the shared inventory in:

- [mdms-preproduct-visibility-polish-worklist.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-visibility-polish-worklist.md)

### 3. Audit and accountability readability

The auth baseline is already implemented.

The next step is to make sure operators can read and trust it easily.

Focus areas:

- confirm `user_action_audit` is present on critical read and execute flows
- make actor fallback rules consistent where legacy rows still exist
- make action snapshots in `operational_event.details` easy to interpret
- prefer explicit actor wording like `display_name (login_id)` on sensitive
  actions

### 4. Bug-fix loop with regression discipline

For post-close-out fixes:

- add a focused regression for the exact issue
- run the smallest relevant suite first
- run the full suite when the fix touches shared services, models, or auth

Recommended validation discipline:

1. targeted unit or service test
2. targeted web or API regression if user-facing
3. full `pytest --cov-fail-under=80` for cross-cutting fixes

### 5. Testing hardening follow-through

The first hardening wave for the highest-risk correction logic is complete.

Completed first-wave targets:

- `VEE`
- `estimation`
- `manual edit`

The remaining testing-hardening backlog should stay deferred until:

- the bounded smoke pass is executed once
- real operator friction shows where a second hardening wave would add the most
  value

See:

- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
- [mdms-preproduct-testing-hardening.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-testing-hardening.md)

## Recommended first execution slices

### Slice 1. Close-out smoke pass review

Goal:

- execute the smoke runbook once
- turn the results into a short hardening queue

Expected outputs:

- no hidden foundational blockers
- a small ranked list of real issues

### Slice 2. Smoke triage and same-slice fixes

Goal:

- classify smoke findings into:
  - `blocker`
  - `same-slice hardening fix`
  - `accepted limitation`
  - `later backlog item`
- fix only the issues that can be closed without opening a new subsystem

### Slice 3. Visibility polish on one or two high-traffic views

Recommended first candidates:

- broader i18n label consistency review after the current filter/spotlight
  slice settles
- lower-traffic empty-state wording polish only if repeated internal use still
  shows ambiguity outside the current high-traffic lists

Goal:

- improve operator comprehension without changing core business rules

### Slice 4. Audit readability polish

Recommended first candidates:

- actor display consistency on correction and export views
- runtime-versus-human actor clarity on adapter and export screens

Goal:

- make accountability easier to understand during internal use

### Slice 5. Narrow bug-fix cycle

Goal:

- fix the first few real operating issues found during smoke or early use
- keep fixes narrow and regression-backed

## Exit criteria for the `mdms-preproduct` phase

This mode has done its job when:

- the close-out smoke pass has been run once end to end
- no unplanned foundational blocker remains
- the first few operator-facing visibility confusion hotspots are reduced
- the remaining open issues are mostly policy depth, product breadth, or
  accepted limitations

## Explicitly not the goal of this phase

Do not treat this phase as the time to open:

- a new billing subsystem
- broad policy-depth expansion
- new auth-maturity subsystems such as password reset or token auth
- full user-management UI
- advanced worker registry or runtime analytics platforms

Those may still be valuable later, but they should follow repeated internal-use
signals rather than precede them.
