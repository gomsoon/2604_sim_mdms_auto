# Adapter Operations UI

## Purpose

This document defines the recommended minimal operator-facing UI scope for runtime adapters.

It answers:

- what the first adapter operations screen should show
- what actions operators should be allowed to perform
- what should explicitly stay out of scope in the first version

## Why this document matters

The runtime adapter model is only useful if operators can actually inspect and control it safely.

Without a clear UI scope, the project risks:

- exposing too little operational control
- exposing too much low-level power too early
- mixing runtime lifecycle actions with code-level adapter design
- making troubleshooting harder than it should be

## Core recommendation

The first adapter operations UI should manage adapter instances, not adapter implementations.

That means the first UI is for:

- operational control
- runtime inspection
- basic manual execution

It is not for:

- defining new adapter code
- writing arbitrary polling logic
- editing unrestricted secrets or SQL

## UI design goal

The first operator UI should make these questions easy to answer:

- Is this adapter available right now
- Is it currently running
- Did it fail recently
- When did it last succeed
- Can I pause it safely
- Can I run it once for validation

If the screen cannot answer those clearly, the operator will still need to inspect logs first, which is not the intended workflow.

## Recommended first screen structure

### 1. Adapter list view

The list view should be the main operational landing page.

Recommended columns:

- display name
- source system
- delivery mode such as `poll` or `receive`
- adapter definition or type
- adapter profile key
- effective status
- last success time
- last failure time
- next run time for polling adapters
- last error summary

Recommended row actions:

- `Enable`
- `Pause`
- `Run Once`
- `View Runs`

### 2. Adapter detail view

The detail page should give a more complete operational picture.

Recommended sections:

- identity and source summary
- current lifecycle state
- masked configuration summary
- recent runs
- last success and failure information
- recent error details
- schedule summary for polling adapters

Recommended detail-page actions:

- `Enable`
- `Pause`
- `Run Once`

## Recommended first actions

### Enable

Purpose:

- move an adapter instance back into active operational use

Expected result:

- `admin_state` becomes `enabled`
- the effective status becomes `ready` unless a currently active error or run changes the view

### Pause

Purpose:

- stop automatic collection safely without removing the adapter instance

Expected result:

- `admin_state` becomes `paused`
- future scheduled polling does not start
- existing history remains visible

### Run Once

Purpose:

- validate connectivity or collection behavior without waiting for the schedule

Expected result:

- create a manual `adapter_run`
- use the same runtime path as scheduled execution
- allow validation even when the adapter is paused, if policy permits

### View Runs

Purpose:

- inspect recent execution attempts and their outcomes

Expected result:

- operator can see `waiting`, `running`, `completed`, and `failed` runs
- operator can review timestamps, counts, and error summaries

## Recommended disabled or deferred actions

The first version should not attempt to expose every possible operational action.

Defer for later:

- `Delete`
- `Clone`
- `Edit raw SQL`
- `Edit plaintext credentials`
- `Acknowledge and suppress errors`
- `Retire` as a common operator action
- `Create new adapter code from the UI`

Why defer them:

- they add risk without being required for the first operational baseline
- they blur the boundary between operations and engineering configuration
- they increase audit and safety complexity

## Recommended action rules by state

### When effective status is `ready`

Allow:

- `Pause`
- `Run Once`
- `View Runs`

Do not show:

- `Enable`

### When effective status is `running`

Allow:

- `View Runs`

Defer:

- `Cancel`

For the minimal stage, a running adapter should usually be allowed to finish.

### When effective status is `paused`

Allow:

- `Enable`
- `Run Once`
- `View Runs`

Do not show:

- `Pause`

### When effective status is `error`

Allow:

- `Pause`
- `Run Once`
- `View Runs`

Optional later:

- `Retry`

For the minimal stage, `Run Once` is usually enough and cleaner than a separate retry concept.

### When effective status is `retired`

Show:

- read-only summary
- run history

Do not emphasize routine operational actions.

## Recommended visual model

The main status badge should use the derived effective status:

- `ready`
- `running`
- `paused`
- `error`
- `retired`

Recommended secondary metadata:

- `poll` or `receive`
- source system
- adapter profile key
- last success
- next run

This avoids crowding the list with internal fields that operators do not need every time.

## Recommended confirmation behavior

The first UI should confirm actions that change lifecycle state.

Recommended confirmations:

- pausing an adapter
- enabling an adapter after failure
- running an adapter once when it is paused

The confirmation should be lightweight, not a long wizard.

## Recommended audit expectations

Each lifecycle action should leave an audit trace or operational event.

At minimum, the system should be able to answer:

- who paused the adapter
- who enabled it
- who triggered `Run Once`
- when the action happened

This can begin as simple application logging if a dedicated audit model does not exist yet.

## Recommended localization expectations

The adapter operations UI should follow the project baseline for English and Korean support.

At minimum, the following must be localizable:

- status labels
- action labels
- confirmation prompts
- error summaries
- empty-state messages

## Recommended testing expectations

When the adapter operations UI is implemented, tests should cover:

- allowed actions by effective status
- hidden or disabled actions in invalid states
- `Run Once` action from a paused adapter
- localized labels and feedback
- regression behavior for recent-run visibility

## Recommended immediate baseline

If the team wants the smallest useful UI answer now, the recommended first action set is:

- `Enable`
- `Pause`
- `Run Once`
- `View Runs`

That set is enough to make runtime adapters operationally visible and controllable without overcommitting to a larger control plane.

## Relationship to other documents

- [integration-adapter-management.md](/home/tprover/2604_sim_mdms_auto/docs/integration-adapter-management.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [pipeline-orchestration.md](/home/tprover/2604_sim_mdms_auto/docs/pipeline-orchestration.md)
- [decision-log.md](/home/tprover/2604_sim_mdms_auto/docs/decision-log.md)
