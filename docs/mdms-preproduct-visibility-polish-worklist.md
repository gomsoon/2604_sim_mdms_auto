# MDMS Preproduct Visibility Polish Worklist

## Purpose

This document inventories the operator-facing visibility-polish work that
remains in the `mdms-preproduct` phase.

It exists so that visibility work is chosen intentionally from a shared list
instead of being picked ad hoc one view at a time.

It complements:

- [mdms-preproduct-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-plan.md)
- [mdms-preproduct-smoke-review.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-smoke-review.md)
- [backlog.md](/home/tprover/2604_sim_mdms_auto/docs/backlog.md)

## Selection rules

Choose the next slice using these criteria:

- operator frequency:
  prefer screens that are revisited often during daily bounded internal use
- ambiguity risk:
  prefer wording or labeling gaps that can cause wrong interpretation
- accountability clarity:
  prefer places where actor, runtime worker, status, or blocked reason is easy
  to misread
- implementation size:
  prefer a narrow slice that can ship with focused regression in one change set

Do not mix more than one or two views into the same polish slice unless they
share the exact same wording or display rule.

## Current status

### Completed

- `billing export request` list and detail:
  human actor versus runtime worker clarity is now explicit
- stale-warning and blocked-reason wording cleanup:
  export stale guidance and correction blocked-reason wording now use a more
  consistent operator-facing pattern
- export wording follow-through:
  request lifecycle, progress, failure follow-up, and item-section wording are
  now easier to scan during bounded internal use
- `adapter detail` recent runs:
  human actor versus runtime actor clarity is now explicit
- `vee_exception` queue and detail:
  status, blocked meaning, and next operator action wording is now easier to
  scan
- replay request list and detail:
  scope meaning, requester actor, progress wording, and current-versus-failed
  item readability are now clearer
- correction detail consistency:
  `vee`, `estimation`, and `manual edit` now use a more comparable actor,
  memo, result, blocked-reason, and lineage reading pattern across detail
  views
- cross-view wording and i18n consistency:
  shared actor labels and correction summary helper wording now use a more
  consistent pattern across export and correction detail screens
- stale-warning and blocked-reason second-pass sweep:
  replay failure wording, blocked-guidance fallback, and auto-refresh versus
  intervention wording now use a more explicit operator-facing distinction
- empty-state wording polish:
  high-traffic lists now distinguish filter-miss empties from not-yet-recorded
  baseline empties and point operators to the next likely action
- list-level filter and spotlight polish:
  queue views now show active filter summaries and row-level spotlight helpers
  so operators can see which filters narrowed the list and which rows need
  review first
- broader i18n label consistency review:
  lower-frequency detail views now use a more consistent Korean pattern for
  lineage, revision history, mixed-language descriptions, and shared
  no-details fallback wording
- lower-traffic empty-state wording polish:
  standalone lower-traffic lists now distinguish filter-miss empties from
  baseline empties and point operators to the next likely action
- lower-traffic composite-page empty-state wording polish:
  `hes_system_detail` and `dashboard` subsection empties now distinguish setup,
  quiet-state, and not-yet-recorded activity more clearly
- master-data sectioned empty-state wording polish:
  `master_data` now distinguishes missing prerequisites from true section
  baseline empties across service point, billing, tariff, device, component,
  and installation sections
- broader glossary and locale consistency sweep:
  repeated mixed-language nouns such as revision, downstream recalculation,
  usage window, usage row, source-side, and billing-lite now use a more
  consistent Korean operator-facing pattern across lower-frequency views
- request-detail workflow placeholder wording polish:
  export and replay request detail views now explain whether missing pipeline,
  current-item, failed-item, and focus-payload sections mean not-started-yet,
  not-currently-processing, or a healthy no-failure state
- lineage/detail-context `no_*` wording sweep:
  usage, bill-determinant, and bill-charge detail views now explain whether
  missing downstream rows, upstream snapshots, or revision history mean
  not-yet-calculated context or unavailable lineage context

### Next recommended candidates

- remaining event and exception context `no_*` wording sweep
  - revisit lower-frequency placeholders across operational-event, VEE
    exception, and raw exception detail views only if repeated internal use
    still shows ambiguity after the usage/billing lineage placeholders settle

### Later candidates

- empty-state wording polish across lower-traffic views once the current
  high-traffic wording slices settle
- list-level filter and spotlight polish for broader row triage after repeated
  internal use produces stronger signals
- broader glossary or i18n taxonomy redesign after repeated internal use
  produces a stronger terminology signal
- remaining detail-page and subsection `no_*` wording cleanup after repeated
  internal use produces a clearer ambiguity signal

## Candidate inventory

### A. VEE queue and detail

- clarify queue-level status wording for `open`, `acknowledged`, `resolved`,
  and `re-evaluated superseded`
- make blocking versus non-blocking meaning easier to read without opening the
  service code
- make event-linked context and correction guidance easier to locate

### B. Replay request list and detail

- separate requested-by human actor from runtime processing identity
- make cancel state, recovery lineage, and current request status easier to
  scan
- reduce ambiguity around whether the request is queued, claimed, completed, or
  cancelled

### C. Correction detail consistency

- align actor wording across:
  - `vee_exception` detail
  - `estimation_audit` detail
  - `manual_edit_audit` detail
- prefer one display style for sensitive actor fields:
  - `display_name (login_id)` when account lineage exists
  - explicit legacy fallback wording otherwise
- make `operator_memo`, `result_code`, and blocked reason labels easier to
  compare across correction types

### D. Stale-warning and blocked-reason wording cleanup

- make stale or lagging worker warnings easier to compare across replay and
  export views
- make blocked-result and blocked-reason wording easier to compare across
  correction views
- reduce ambiguity around whether a row needs intervention now or is only an
  informational warning

### E. Export wording follow-through

- keep billing export request actor clarity complete after the first
  runtime-versus-human polish slice
- review whether progress, current-item, failed-item, recent-item, payload, and
  cancellation wording still feels too dense in detail view

### F. Cross-view wording consistency

- review repeated labels for:
  - `human actor`
  - `runtime actor`
  - `runtime worker`
  - `blocked reason`
  - `result code`
  - `current status`
- consolidate wording where the same concept currently appears with slightly
  different labels

## Recommended execution order

1. remaining event and exception context `no_*` wording sweep only if repeated
   internal use still shows ambiguity in lower-frequency placeholders
2. broader glossary or i18n taxonomy redesign only if repeated internal use
   still finds a stronger terminology signal beyond the current label set

## Explicitly deferred in this worklist

This document does not reopen:

- new policy-depth behavior
- new auth or worker-registry subsystems
- large workflow redesigns
- broad dashboard redesign
- exhaustive per-view UI acceptance suites

Those should move only if repeated internal use shows a stronger signal than the
current bounded polish queue.
