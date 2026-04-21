# Adapter Live Hardening Plan

## Purpose

This document defines the next hardening phase for runtime adapters, with the first target focused on the live `nuri_aimir_hes_lp_em_poll_v1` polling path.

It exists to answer:

- what should be hardened before treating the adapter as production-like
- what remains inside the minimal-stage boundary
- what should be tested and observed during live verification

## Why this hardening phase matters

The project already has:

- adapter definitions and instances
- operator controls such as `Enable`, `Pause`, and `Run Once`
- runtime execution and watermarks
- landing persistence and common-raw expansion
- dashboard visibility and operational events

That baseline is strong enough to demonstrate the end-to-end shape, but live polling still needs a more explicit hardening pass so that:

- runtime configuration failures are deterministic
- watermark advancement is auditable
- replay and duplicate behavior is safe
- operators can tell the difference between connectivity, query, parsing, and downstream persistence failures

## Current baseline

The current first-source runtime path is:

1. operator or scheduler enqueues an `adapter_run`
2. the worker claims the run
3. the runtime implementation connects to Oracle
4. the runtime fetches `LP_EM` rows using a composite watermark
5. source blocks can be persisted into landing
6. blocks are expanded into interval-granular common raw rows
7. completeness-state rows are updated
8. watermark and run summary are committed

Related implementation:

- [app/services/nuri_aimir_hes_source.py](/home/tprover/2604_sim_mdms_auto/app/services/nuri_aimir_hes_source.py)
- [app/services/adapter_execution.py](/home/tprover/2604_sim_mdms_auto/app/services/adapter_execution.py)
- [app/models.py](/home/tprover/2604_sim_mdms_auto/app/models.py)

## Hardening goals

The next live hardening phase should make the adapter stronger in five areas:

1. runtime configuration validation
2. watermark semantics
3. landing and common-raw replay safety
4. failure classification and operator visibility
5. controlled live verification path

## Workstream 1. Runtime configuration validation

### Goal

Fail fast and fail clearly when a live adapter instance is not configured well enough to poll Oracle safely.

### Required baseline

- `oracle_host`
- `oracle_port`
- exactly one of `oracle_sid` or `oracle_service_name`
- `oracle_username`
- `secret_ref`
- positive `batch_size`
- valid `allowed_channels` shape when present

### Recommended behavior

- configuration validation should happen before a source query is attempted
- validation errors should become stable adapter-run failures
- operator-facing error codes should distinguish configuration errors from source execution failures

### Boundary

This phase should not introduce a generic secrets-management platform.

## Workstream 2. Watermark semantics

### Goal

Keep incremental polling deterministic, replay-safe, and auditable.

### Current baseline

The current cursor shape is:

- `WRITEDATE`
- `YYYYMMDDHH`
- `METER_ID`
- `CHANNEL`

### Hardening focus

- confirm how `WRITEDATE` behaves for late writes and rewritten source rows
- ensure ordering remains deterministic for the selected tie-breaker
- ensure watermark updates happen only after successful persistence
- ensure restart after failure resumes from the correct boundary

### Recommended posture

- keep the current composite cursor in the minimal stage
- treat watermark changes as an explicit auditable state transition
- use landing rows and operational events to troubleshoot unexpected replay or gaps

## Workstream 3. Landing and common-raw replay safety

### Goal

Make the path from source block to landing to common raw safe for reruns and late arrivals.

### Hardening focus

- landing uniqueness for the same source block
- raw duplicate protection during block expansion
- safe completeness-state updates on replay
- safe behavior when the same logical hour is polled more than once

### Expected outcome

The adapter should support:

- rerunning a recently failed batch
- replaying already-landed source blocks without multiplying common-raw rows
- observing whether a late source write changed completeness status

## Workstream 4. Failure classification and operator visibility

### Goal

Make live failures easier to diagnose from the operator UI and event stream.

### Minimum failure classes

- configuration validation failure
- Oracle connection failure
- Oracle authentication failure
- Oracle query execution failure
- source-row parsing failure
- landing write failure
- common-raw write failure
- completeness-state update failure

### Recommended visibility

- stable `error_code` on `adapter_run`
- stable summary text on `adapter_run`
- emitted `operational_event`
- promotion to `alert` when operator action is likely needed

## Workstream 5. Controlled live verification path

### Goal

Introduce live polling in a way that is safe to inspect and easy to roll back.

### Recommended first live path

1. prepare one dedicated adapter instance
2. use small batch size
3. optionally restrict channels
4. optionally constrain business-hour lower and upper bounds for smoke validation
5. execute `Run Once`
6. verify `adapter_run`
7. verify watermark movement
8. verify landing rows
9. verify common raw rows
10. verify completeness-state updates
11. repeat once to confirm replay safety

### Recommended first live boundary

Include now:

- one bounded live polling adapter instance
- one or a few channels
- one manual run path
- operator verification of run summary and watermark

Defer for later:

- broad historical backfill
- aggressive polling frequency
- parallel source-range polling

## Minimal-stage boundary

This hardening plan still stays inside the minimal stage.

Included:

- stronger validation
- stronger replay safety
- stronger visibility
- stronger testing

Still deferred:

- receive-adapter runtime
- operator-editable alert rule tables
- dynamic SQL editing from the UI
- parallel polling orchestration
- deep master-data synchronization

## Recommended execution order

1. strengthen live runtime configuration validation
2. harden watermark and replay semantics
3. harden landing and completeness-state idempotency
4. classify and surface failure types
5. run a bounded live verification path

## Acceptance criteria for this hardening phase

- one misconfigured live adapter fails with a clear validation error before polling
- one successful run advances watermark deterministically
- one replay run does not multiply landing or common-raw data incorrectly
- one induced source or query failure is visible in `adapter_run`, `operational_event`, and alert surfaces
- one bounded live run can be inspected end to end by an operator

## Related documents

- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)
- [adapter-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-backlog.md)
- [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
