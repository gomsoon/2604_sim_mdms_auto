# Re-VEE Baseline Runbook

## Purpose

This document explains the current manual `re-VEE` baseline from three angles:

- when operators should trigger it
- what the user interface does
- what the backend persists and changes

The current baseline is intentionally narrow. It supports targeted re-evaluation of one `vee_exception` and its linked `initial_measurement`. It does not yet provide bulk replay, scheduled re-VEE, or rule-version-based automatic reprocessing.

## UX principles

Manual `re-VEE` starts from a single operator button, but the backend may now touch more than one processing stage:

- VEE re-evaluation
- VEE exception supersession or reopening
- re-finalization when the initial measurement becomes acceptable again
- targeted usage recalculation when the authoritative final changes

Because of that, one generic success flash is not enough as the only operator feedback.

The current UX baseline follows these rules:

- one `vee_exception` detail action may remain synchronous for now
- the detail page should show a structured outcome summary after the request completes
- the summary should distinguish `VEE cleared` vs `VEE reopened`
- the summary should distinguish `final unchanged` vs `final created` vs `final superseded`
- the summary should show whether daily or monthly usage windows were recalculated or deleted

## Sync vs async boundary

The current baseline intentionally keeps only the narrowest scope synchronous:

- one `vee_exception`
- one linked `initial_measurement`
- any directly impacted final revision
- any directly impacted daily/monthly usage windows

The following cases should be treated as future asynchronous work rather than current synchronous UI actions:

- HES-wide re-VEE
- batch-wide re-VEE
- date-range replay across many measurements
- scheduled automatic re-evaluation after bulk master-data correction
- mass usage recalculation after large final supersession events

## When re-VEE happens

The current baseline assumes re-VEE is an operator action taken after some corrective work has already happened.

Typical triggers are:

- source-data correction changed the raw or canonical context
- master-data correction fixed device, service point, measuring component, or installation lineage
- a previously missing or invalid field was corrected
- the operator wants to confirm whether the current VEE exception is still valid

The current baseline does not automatically re-run VEE when these corrections happen. The operator must explicitly trigger re-evaluation from the VEE exception detail view.

## Operational procedure

### Goal

Give operators a safe way to confirm whether a blocking or warning VEE exception is still valid after corrective action.

### Steps

1. Open the `VEE exception` detail screen.
2. Review the linked `HES`, `raw`, `canonical`, `initial`, and `final` lineage.
3. Fix the root cause first.
4. Trigger `Re-evaluate`.
5. Review the new VEE result and finalization eligibility.

### Expected operator outcomes

- the previous active exception is preserved for audit
- the system records a fresh VEE execution snapshot
- the issue either reappears as a new active exception or the measurement returns to `accepted`
- finalization eligibility is restored only when no open blocking VEE exception remains

## State transitions

### Before re-VEE

- `initial_measurement.initial_status` is usually `exception` when an open blocking `vee_exception` exists
- the linked `vee_exception` is normally `open` or `acknowledged`
- finalization is blocked for blocking exceptions

### During re-VEE

- active exceptions for the same `initial_measurement` are resolved as `re_evaluated_superseded`
- the related operational alerts are closed
- a fresh `vee_execution_log` row is created with `trigger_type = manual_re_evaluate`
- the baseline rules are evaluated again
- if the new result is `accepted`, finalization may run again immediately
- if current final data changes, directly impacted daily and monthly usage windows may be recalculated immediately

### After re-VEE

If problems remain:

- a new `vee_exception` snapshot is created
- the same `exception_code` may appear again in the new snapshot
- `initial_measurement.initial_status` remains `exception`
- finalization stays blocked when the new exception is blocking

If problems are cleared:

- no new blocking `vee_exception` is created
- `initial_measurement.initial_status` becomes `accepted`
- finalization becomes eligible again

## User interface behavior

### Entry point

The current manual baseline is exposed from:

- `VEE exception detail`

The detail view provides the operator enough context to decide whether re-evaluation is meaningful after a correction.

### Current UI behavior

- a `Re-evaluate` button is shown on the VEE exception detail page
- the action posts back to the application server
- success feedback is shown after the request completes
- the refreshed page reflects the new execution and exception state
- the refreshed page also shows a result card summarizing:
  - the new `vee_execution_log`
  - whether the exception cleared or reopened
  - whether finalization created or superseded a current final
  - whether daily or monthly usage windows were recalculated or deleted
  - per-window usage recalculation results that keep before/after outcome context for later drill-down

### What the operator should see after re-VEE

- the original VEE exception is no longer active
- the exception status becomes `re_evaluated_superseded`
- if the issue persists, a new active exception row exists
- if the issue is fixed, the linked initial measurement is accepted and finalization is no longer blocked by that exception

## Backend behavior

### Main entry points

The current baseline is implemented around these service and web paths:

- `POST /vee-exceptions/<id>/re-evaluate`
- `reevaluate_vee_exception(...)`
- `reevaluate_initial_measurement(...)`
- `evaluate_or_get_vee_baseline(..., force=True)`

### Persistence behavior

The current backend flow is:

1. Load the target `vee_exception`.
2. Resolve all active exceptions for the same `initial_measurement` as `re_evaluated_superseded`.
3. Close any related operational alerts.
4. Create a fresh `vee_execution_log` for the same `initial_measurement`.
5. Re-run the baseline VEE rules.
6. Create new `vee_exception` rows only for the currently detected issues.
7. If the result is acceptable again, attempt re-finalization.
8. If the authoritative final changes, recalculate only the directly impacted usage windows.
9. Record `vee_re_evaluated` and any downstream processing events as `operational_event`.

The usage recalculation payload should preserve per-window result detail, not only aggregate counts.
This allows later screens to show:

- which day or month window changed
- whether the usage row was updated, deleted, or effectively unchanged
- the previous and current usage values
- the previous and current calculation status

The recalculated `usage_transaction` row should also preserve replay provenance in its own `details`.
That provenance should make it possible to trace:

- which `vee_execution_log` triggered the replay
- which `initial_measurement` was re-evaluated
- which previous/current `final_measurement` pair caused the recalculation

### Important implementation rule

The baseline does not mutate the previous exception into the new result. It always keeps the previous active exception as an auditable historical row and creates a new snapshot when the issue still exists.

This means:

- history is preserved
- repeated re-evaluation is traceable
- the same `exception_code` can appear multiple times across different VEE executions

## Operational-event behavior

The current baseline uses `operational_event` so re-VEE is visible outside the VEE screens.

Important event and alert behaviors are:

- opening a VEE exception creates or syncs VEE-related operational alerts
- re-evaluation closes the old active alert when the old exception is superseded
- successful re-evaluation records `vee_re_evaluated`
- if a new issue remains, a fresh VEE alert opens again from the new snapshot
- if re-finalization creates a new current final revision, `final_measurement_superseded` is recorded
- if impacted usage windows are recalculated, `usage_recalculated_after_vee` is recorded

## Finalization impact

The finalization gate remains conservative.

- open blocking `vee_exception` prevents finalization
- acknowledged blocking `vee_exception` still prevents finalization
- resolved or superseded exceptions do not block by themselves
- re-VEE only restores finalization eligibility when the new evaluation has no open blocking exception

## Current limitations

The current manual baseline does not yet include:

- bulk re-VEE by HES, batch, or time range
- scheduled automatic re-VEE after master-data correction
- rule-set versioning and mass replay
- operator notes specific to re-VEE decisions
- explicit side-by-side comparison UI between old and new VEE snapshots

These remain follow-up work after the manual baseline proves stable in operation.

Additional limitations that still remain:

- the operator still waits synchronously for the single-object action to finish
- there is no live sub-step progress bar inside the same request
- bulk or long-running replays are not yet promoted to queue-backed pipeline UI

## Future bulk and async replay direction

The current synchronous baseline is intentionally limited to one `vee_exception`.

The next replay step should introduce:

- `vee_replay_request` as operator-facing request truth
- `vee_replay_request_item` as per-target progress truth
- `pipeline_run` linkage for execution attempts
- queue-backed replay for `hes_system`, `ingest_batch`, and `date_range` scopes

That future design should keep:

- single-object replay synchronous
- bulk replay asynchronous
- the existing `reevaluate_vee_exception_and_replay(...)` logic as the per-item replay engine

See [bulk-async-vee-replay-design.md](/home/tprover/2604_sim_mdms_auto/docs/bulk-async-vee-replay-design.md) for the recommended first persistence model and worker behavior.
