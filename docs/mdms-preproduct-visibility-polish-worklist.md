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
- `adapter detail` recent runs:
  human actor versus runtime actor clarity is now explicit
- `vee_exception` queue and detail:
  status, blocked meaning, and next operator action wording is now easier to
  scan
- replay request list and detail:
  scope meaning, requester actor, progress wording, and current-versus-failed
  item readability are now clearer

### Next recommended candidates

- correction detail wording consistency
  - align `vee`, `estimation`, and `manual edit` actor and result wording so
    the operator sees the same shape across sensitive mutation flows
  - use the active slice design in:
    [mdms-preproduct-correction-detail-polish-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-correction-detail-polish-plan.md)
- stale-warning and blocked-reason wording cleanup
  - make warning and blocked language easier to compare across replay, export,
    and correction views
- export wording follow-through
  - keep billing export detail wording dense enough for audit value but easier
    to scan during bounded internal use

### Later candidates

- stale-warning, empty-state, and blocked-reason wording polish across
  visibility views
- list-level filter and spotlight polish where actor or status confusion keeps
  appearing in bounded use
- broader i18n label consistency review after the next few targeted polish
  slices settle

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

### D. Export wording follow-through

- keep billing export request actor clarity complete after the first
  runtime-versus-human polish slice
- review whether progress, recovery, and cancellation wording still feels too
  dense in detail view

### E. Cross-view wording consistency

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

1. correction detail wording consistency
2. stale-warning and blocked-reason wording cleanup
3. export wording follow-through
4. wider label and i18n consistency pass

## Explicitly deferred in this worklist

This document does not reopen:

- new policy-depth behavior
- new auth or worker-registry subsystems
- large workflow redesigns
- broad dashboard redesign
- exhaustive per-view UI acceptance suites

Those should move only if repeated internal use shows a stronger signal than the
current bounded polish queue.
