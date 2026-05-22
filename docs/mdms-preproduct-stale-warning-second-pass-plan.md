# MDMS Preproduct Stale-Warning And Blocked-Reason Second-Pass Plan

## Purpose

This document defines the next narrow visibility-polish slice after the first
stale-warning cleanup, export wording follow-through, and cross-view wording
consistency pass.

The goal is not to redesign replay or correction screens.

The goal is to remove the remaining small wording ambiguities around:

- whether a warning requires operator intervention now
- whether a message is only informational
- why a correction action is blocked

## Scope

Keep this slice to wording, helper text, and focused web regression only.

Do not open:

- new worker heartbeat models
- new blocked-reason fields
- replay or correction layout redesign
- broader i18n taxonomy refactors

Primary targets:

- `vee_replay_request_detail`
- `vee_exception_detail`
- `estimation_audit_detail`
- `manual_edit_audit_detail`

Supporting files:

- `app/i18n/__init__.py`
- focused web regressions in `tests/test_vee_replay_web.py`,
  `tests/test_vee_exception_web.py`, and `tests/test_visibility_web.py`

## Desired operator outcome

After this slice, an operator should be able to tell more quickly:

- whether a replay request is still progressing or needs intervention
- whether a failed item is the next thing to inspect
- whether a correction action is blocked by policy, unsupported scope, or
  invalid input
- where to drill down next when the screen shows a warning or blocked result

## Narrow execution areas

### 1. Replay failure wording

Focus on `vee_replay_request_detail`.

Clean up wording around:

- `last_error`
- failed-item summaries
- auto-refresh versus failed-state messaging
- “current item” versus “recent item” emphasis when the request is not
  processing anymore

The key distinction should be explicit:

- `processing`: the request is still moving
- `failed`: a human should inspect failed rows or the last error
- `completed`: no current intervention is implied

### 2. Correction blocked-guidance fallback

Focus on:

- `vee_exception_detail`
- `estimation_audit_detail`
- `manual_edit_audit_detail`

Use one shared reading pattern:

1. current correction outcome
2. blocked reason
3. next operator cue

Keep the implementation shallow:

- improve wording and helper text only
- prefer translated blocked-reason text when it exists
- keep raw-code fallback readable when no dedicated wording exists

### 3. Auto-refresh versus intervention wording

Focus on replay detail first.

Clarify that auto-refresh explains screen behavior, not business outcome.

That means:

- a refresh notice should not sound like a failure
- a failure or blocked notice should not sound like a transient refresh state

## Explicit deferrals

Keep the following deferred:

- replay-specific runtime heartbeat or stale semantics beyond current metadata
- export/replay layout redesign
- blocked-reason taxonomy redesign across all correction paths
- exhaustive locale wording sweeps
- new summary widgets or spotlight panels

## Validation discipline

1. `git diff --check`
2. `ruff` on touched i18n and web-test files
3. targeted web regression for replay and correction views
4. full `pytest --cov-fail-under=80`

## Exit criteria

This slice is done when:

- replay warning versus failure wording is easier to distinguish
- correction blocked guidance uses a more consistent read order
- auto-refresh language no longer competes with intervention language
- targeted web regression and full regression both pass
