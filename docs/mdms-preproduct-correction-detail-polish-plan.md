# MDMS Preproduct Correction Detail Polish Plan

## Purpose

This document defines the next `mdms-preproduct` visibility-polish slice after
the first `vee_exception` and replay wording work.

The goal is to make the operator-facing correction details read like one
coherent family of screens.

The goal is not to introduce new correction behavior, new audit fields, or new
workflow depth.

## Why this slice is next

The first-wave decision-test hardening for:

- `VEE`
- `estimation`
- `manual edit`

is complete.

The next operator value is to make the resulting detail screens easier to
compare when a user is moving between:

- `vee_exception` detail
- `estimation_audit` detail
- `manual_edit_audit` detail

These screens already contain the right data.

The remaining friction is mostly wording, layout consistency, and explicit
actor and result interpretation.

## Views in scope

- [vee_exception_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/vee_exception_detail.html)
- [estimation_audit_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/estimation_audit_detail.html)
- [manual_edit_audit_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/manual_edit_audit_detail.html)
- [__init__.py](/home/tprover/2604_sim_mdms_auto/app/i18n/__init__.py)

Likely regression touch points:

- [test_visibility_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_visibility_web.py)
- [test_vee_exception_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_vee_exception_web.py)

## Core goals

### 1. Actor and memo consistency

Use one display pattern across correction details:

- when account lineage exists:
  `display_name (login_id)`
- when only legacy string lineage exists:
  raw string plus explicit fallback wording

`operator_memo` should appear in a comparable place across correction detail
screens when it exists.

### 2. Status and result consistency

Operators should be able to find the same concepts in the same area:

- current correction status
- result code
- blocked reason when relevant
- correction strategy or reason

The correction type changes, but the operator reading pattern should not.

### 3. Final and lineage consistency

The lineage section should make it easier to compare:

- target initial measurement
- related VEE exception
- superseded final
- result final

The ordering and wording should feel parallel between estimation and manual
edit.

## Shared display rules

### Actor display

- Prefer the existing formatted display from visibility context
- Add helper wording:
  - `human actor` when a `user_account` relation exists
  - `recorded actor` when the row only has a legacy string actor

### Operator memo display

- Show `operator_memo` in the summary card, not buried only in raw snapshots
- If memo is empty or normalized away, show `-`

### Result-code display

- Keep the localized `result_code` translation
- Place it close to current status so blocked/applied meaning is visible
  without scanning snapshots

### Blocked-reason display

- If blocked reason is present in correction details, expose it explicitly
  rather than expecting operators to infer it from raw JSON
- Prefer localized wording when a direct translation exists
- Otherwise show the raw code as a visible fallback

## View-by-view design

### A. `vee_exception` detail

This view already has the first wording polish.

For this slice, only the correction result cards are in scope.

Polish targets:

- make `estimation result` and `manual edit result` cards use the same reading
  order:
  - outcome
  - result code
  - actor or audit reference
  - finalization outcome
  - downstream impact
- keep wording parallel so operators can compare two correction types quickly
- avoid adding new widgets or new action flows

### B. `estimation_audit` detail

Summary card improvements:

- make `estimated_by` use actor helper wording
- surface `operator_memo`
- add explicit `result_code`
- add explicit blocked-reason line when relevant

Lineage and result improvements:

- keep target initial, related VEE, source finals, superseded final, and result
  final in a more comparable order
- keep `result final snapshot` easy to locate relative to summary and lineage

### C. `manual_edit_audit` detail

Summary card improvements:

- make `edited_by` use actor helper wording
- surface `operator_memo`
- add explicit `result_code`
- add explicit blocked-reason line when relevant

Lineage and result improvements:

- keep target initial, related VEE, superseded final, and result final in the
  same order used by estimation detail where practical
- keep downstream summary and result snapshot easy to compare with estimation

## Explicitly out of scope

This slice does not reopen:

- new audit persistence fields
- new correction workflow behavior
- queue or list redesigns
- preview workspaces
- approval flows
- exhaustive locale-assertion sweeps

## Deferred items

Keep these deferred until a stronger operator signal appears:

- exhaustive per-key audit snapshot assertions across all correction details
- cross-view widget redesign for correction summaries
- broader blocked-reason taxonomy cleanup beyond the current detail pages
- large-scale i18n consistency sweep across every operator-facing view

## Validation plan

Recommended validation order:

1. targeted template and i18n lint checks
2. [test_visibility_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_visibility_web.py)
   focused on estimation and manual-edit audit detail coverage
3. [test_vee_exception_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_vee_exception_web.py)
   for correction result card links and wording
4. full `./.venv/bin/pytest --cov-fail-under=80`

Coverage reporting should continue to be summarized separately as:

- statement coverage
- branch coverage
