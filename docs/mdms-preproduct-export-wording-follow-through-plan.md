# MDMS Preproduct Export Wording Follow-through Plan

## Purpose

This document defines the next narrow visibility-polish slice for billing export
request screens during the `mdms-preproduct` phase.

The goal is not to add new billing-export behavior.

The goal is to make the existing list and detail views easier to scan during
bounded internal use after:

- actor clarity
- runtime-versus-human identity clarity
- stale-warning wording cleanup

## Current state

The current export views already show:

- requested-by human actor lineage
- runtime worker identity
- heartbeat freshness
- summary, progress, pipeline, current item, failed items, recent items, and
  payload metadata

The main remaining gap is wording density.

Operators can already find the right facts, but the screens still ask them to
parse too much at once before they know:

- what stage the request is in
- whether it needs intervention now
- which item or error to inspect next

## Slice goal

Use wording and presentation only to make the billing export request list and
detail views easier to scan without changing queue behavior, worker behavior,
or recovery semantics.

## In scope

- [billing_export_requests.html](/home/tprover/2604_sim_mdms_auto/app/templates/billing_export_requests.html)
- [billing_export_request_detail.html](/home/tprover/2604_sim_mdms_auto/app/templates/billing_export_request_detail.html)
- [app/i18n/__init__.py](/home/tprover/2604_sim_mdms_auto/app/i18n/__init__.py)
- [tests/test_visibility_web.py](/home/tprover/2604_sim_mdms_auto/tests/test_visibility_web.py)

## Detailed focus

### 1. Request lifecycle wording

Make `queued`, `processing`, `completed`, `failed`, and `cancelled` easier to
interpret as export-request states rather than generic status labels.

Target outcomes:

- operators can distinguish:
  - waiting to start
  - currently being worked
  - completed successfully
  - completed with failed items
  - stopped by operator cancellation
- status wording feels consistent between list and detail

### 2. Progress and item-count readability

Keep the current counts, but make it clearer what they mean.

Target outcomes:

- `processed`, `remaining`, `succeeded`, `failed`, and `skipped` are easier to
  interpret in one scan
- progress sections read as operational summary first, raw counters second
- export detail makes it clearer whether a request is still moving or only
  retaining historical counts

### 3. Error and intervention wording

Follow through on the stale-warning cleanup by making failure and intervention
language more explicit.

Target outcomes:

- `last_error` feels like an operator signal, not a buried metadata field
- `failed items` better communicates what deserves follow-up next
- cancellation and cancelled actor fields feel like lifecycle events rather
  than low-level audit residue

### 4. Current item, recent items, and payload framing

The screen already exposes useful item-level data, but the operator still has
to infer why each block matters.

Target outcomes:

- `current item` reads as “what is being worked now”
- `recent items` reads as “what most recently finished”
- `focus payload snapshot` reads as “the currently relevant staged export
  payload”
- `request metadata` reads as supporting detail, not the first thing to parse

## Explicitly out of scope

This slice does not reopen:

- export queue or worker behavior changes
- auto-reclaim or recovery logic changes
- explicit export-to-export recovery lineage modeling
- large export list/detail layout redesign
- new widgets or summary dashboards
- exhaustive locale assertion sweeps

## Recommended implementation order

1. billing export list wording cleanup
2. billing export detail summary and progress wording cleanup
3. current-item, failed-item, recent-item, and payload framing cleanup
4. focused visibility-web regression
5. full regression

## Validation expectations

Run at least:

1. `git diff --check`
2. targeted:
   - `./.venv/bin/ruff check app/i18n/__init__.py tests/test_visibility_web.py`
   - `./.venv/bin/pytest tests/test_visibility_web.py -q`
3. full:
   - `./.venv/bin/pytest --cov-fail-under=80`

## Deferred notes

If repeated internal use shows the need, later follow-up can expand into:

- export recovery wording after explicit lineage modeling exists
- richer failed-item spotlighting
- cross-view export/replay wording unification
- larger export detail layout redesign
