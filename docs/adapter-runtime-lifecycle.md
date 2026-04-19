# Adapter Runtime Lifecycle

## Purpose

This document defines the proposed minimal lifecycle model for runtime adapters.

It answers a narrower question than the broader adapter-management document:

- what states a runtime adapter should have
- what state transitions are allowed
- what the operator should see in the frontend
- what should be persisted now vs added later

## Why this document matters

If the runtime adapter model starts with one overloaded `status` field, the system will quickly become ambiguous.

Common problems with a single mixed status field:

- operator intent and runtime condition get mixed together
- `paused` and `failed` become hard to distinguish
- `poll` and `receive` adapters do not fit the same meaning cleanly
- UI actions become unclear
- future scheduling and heartbeat logic become harder to implement

For that reason, the minimal model should separate:

- administrator intent
- execution history
- derived operator-facing state

## Core recommendation

Do not model runtime adapters with only one status field.

Instead, use a small split model:

- `admin_state` on the adapter instance
- `run_status` on adapter executions
- derived `effective_status` for the frontend

This is still small enough for the minimal stage, but much more stable than a single status field.

## Recommended minimal model

### 1. Adapter instance admin state

This expresses what the administrator wants the adapter to do.

Recommended values:

- `enabled`
- `paused`
- `retired`

Recommended meaning:

- `enabled`: the adapter may receive or poll data according to its mode and schedule
- `paused`: automatic collection is stopped, but the adapter definition remains available
- `retired`: the adapter is no longer used operationally and should not be scheduled

Why this should stay small:

- these are long-lived operational states
- they are understandable to operators
- they do not depend on one transient run

## 2. Adapter run status

This expresses the state of one execution attempt.

Recommended values:

- `waiting`
- `running`
- `completed`
- `failed`

Recommended meaning:

- `waiting`: a scheduled or manual run has been requested but has not started yet
- `running`: the adapter is currently polling, receiving, or transforming source data
- `completed`: the run finished successfully
- `failed`: the run finished with an operational or connectivity error

This aligns well with the processing-layer status model already used elsewhere in the project.

## 3. Derived effective adapter status

This is the status that should be shown in the frontend as the main badge.

Recommended values:

- `ready`
- `running`
- `paused`
- `error`
- `retired`

Recommended derivation logic:

- `retired` if `admin_state = retired`
- `paused` if `admin_state = paused`
- `running` if there is an active run with `run_status = running`
- `error` if the latest relevant run failed and there is no newer success
- `ready` otherwise when the adapter is enabled and not actively failing

This keeps the operator view simple while preserving a cleaner internal model.

## Why `ready` is useful

`ready` is better than reusing `enabled` as the screen status.

Why:

- `enabled` is an operator intent
- `ready` is an operational interpretation

An adapter can be enabled but still currently be:

- running
- in error
- paused later by policy

Using `ready` in the UI avoids that confusion.

## Recommended minimal persisted fields

The exact schema can still be decided later, but the following fields are recommended for `adapter_instance`.

The fuller persistence proposal is defined in [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md).

Useful baseline fields:

- adapter definition reference
- source system
- display name
- delivery mode such as `poll` or `receive`
- adapter profile key
- `admin_state`
- `last_success_at`
- `last_failure_at`
- `last_error_message`
- `last_heartbeat_at`
- `next_run_at` for polling adapters

Useful baseline fields for `adapter_run`:

- adapter instance reference
- `run_status`
- trigger type such as `schedule`, `manual`, or `receive`
- started at
- completed at
- records fetched or received
- batches created
- error summary

## Recommended operator actions

The minimal operator actions should map cleanly to the state model.

Recommended first actions:

- `Enable`
- `Pause`
- `Run Once`
- `Retire` later if needed

Recommended behavior:

- `Enable` moves `admin_state` to `enabled`
- `Pause` moves `admin_state` to `paused`
- `Run Once` creates an `adapter_run` even when the adapter is paused, if manual testing is allowed
- scheduled polling must ignore paused or retired adapters

Allowing `Run Once` while paused is useful because:

- operators can validate connectivity without fully re-enabling a schedule
- issue diagnosis is easier
- onboarding a new source is safer

## Recommended state transitions

### Adapter instance transitions

- `enabled -> paused`
- `paused -> enabled`
- `enabled -> retired`
- `paused -> retired`

The minimal stage should avoid frequent backwards transitions from `retired`.

If revival is ever needed, it should be an explicit administrative action later.

### Adapter run transitions

- `waiting -> running`
- `running -> completed`
- `running -> failed`

The minimal stage does not need more than this.

Later options can include:

- `cancelled`
- `retry_pending`
- `skipped`

## Poll vs receive interpretation

The same model should support both modes.

### Poll adapters

Typical interpretation:

- `enabled` means scheduler may create `waiting` runs
- `running` means a poll cycle is active
- `ready` means no current run and no active error
- `error` means the latest poll run failed

### Receive adapters

Typical interpretation:

- `enabled` means the system accepts or processes incoming deliveries for that adapter instance
- `running` may represent active receive processing or a currently open handler cycle
- `ready` means the adapter is available and healthy
- `error` means recent delivery handling failed or heartbeat expectations were missed

## Dashboard recommendation

The main operator dashboard should later include an `Integration` card based on this lifecycle model.

The card should summarize:

- adapters in `ready`
- adapters in `running`
- adapters in `paused`
- adapters in `error`

This should complement, not replace, the existing data and processing stage cards.

## Why this model fits the minimal stage

This model is intentionally small.

It is good enough for:

- first polling adapter support
- operator lifecycle control
- manual testing through the UI
- simple integration monitoring

It avoids early over-design such as:

- fully dynamic connector plugins
- deep workflow states
- complex health taxonomies
- source-specific status models leaking into the core

## What can be added later

The following are reasonable later extensions, but they are not required now:

- `draft` for incomplete adapter configuration
- `stale` when heartbeat is overdue
- `degraded` when success is partial
- `cancelled` for interrupted runs
- `retry_pending` for retry scheduling

These should be added only when real operational need appears.

## Proposed immediate baseline

If the team wants a concrete minimal baseline now, the recommended answer is:

- use `admin_state = enabled | paused | retired`
- use `adapter_run.status = waiting | running | completed | failed`
- derive frontend `effective_status = ready | running | paused | error | retired`

This is the smallest model that still supports:

- operator control
- runtime visibility
- future polling
- future receive handling

## Relationship to other documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-data-model.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-data-model.md)
- [layered-architecture-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/layered-architecture-baseline.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
