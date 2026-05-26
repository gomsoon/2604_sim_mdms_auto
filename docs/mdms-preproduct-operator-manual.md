# MDMS Preproduct Operator Manual

## Purpose

This manual consolidates the minimum operating procedure for the current
`mdms-preproduct` baseline.

It is written so that an operator or administrator can:

- start the local preproduct system safely
- stop it cleanly
- perform the daily opening and closing routine
- use the major operator-facing features in the intended order
- identify where to look first when something appears blocked or failed

This manual is not a replacement for deeper engineering runbooks.
It is the top-level operator guide that links those runbooks together.

## Intended audience

### `admin`

Use this role when the task requires:

- HES registration or update
- adapter registration, enable, pause, or `Run Once`
- master-data creation or update
- export recovery or cancellation
- sensitive configuration or admin-only mutation

### `operator`

Use this role when the task requires:

- dashboard review
- ingest and lineage inspection
- VEE exception review
- estimation or manual edit
- replay request monitoring
- billing export inspection
- operational-event or audit review

## Current preproduct boundary

The current baseline is suitable for bounded internal use.

The operator should assume:

- the web application is the primary operating surface
- PostgreSQL is the primary data store
- adapter work is queue-backed and worker-driven
- replay and billing export have persisted request and item status
- VEE, estimation, and manual edit are available with audit lineage
- some deeper bulk automation remains intentionally deferred

For accepted limitations, also see
[mvp-known-limitations.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-known-limitations.md).

## Core system components

The current operating baseline is easiest to understand through these parts:

- PostgreSQL
  - persistence for raw, canonical, final, replay, export, event, and audit
    records
- Flask web application
  - the operator-facing UI and API surface
- adapter queue commands
  - enqueue, process, and health-refresh commands for runtime adapters
- major operator objects
  - `hes_system`
  - `adapter_instance`
  - `ingest_batch`
  - `canonical_measurement`
  - `final_measurement`
  - `vee_exception`
  - `estimation_audit`
  - `manual_edit_audit`
  - `vee_replay_request`
  - `billing_export_request`
  - `operational_event`

## Startup procedure

This section describes the recommended normal startup order.

### 1. Confirm prerequisites

Before starting the system, confirm:

- the local PostgreSQL service or cluster is available
- the intended `.env` file or shell environment is active
- the Python virtual environment exists
- the intended `DATABASE_URL` points to the expected environment
- at least one `admin` account and one `operator` account exist if the system
  will be used interactively

### 2. Verify PostgreSQL availability

Recommended checks:

```bash
psql --version
pg_isready
```

If PostgreSQL is not running, start it with one of the documented methods:

```bash
sudo systemctl start postgresql
sudo systemctl status postgresql
```

Or, when cluster-specific control is preferred:

```bash
sudo pg_ctlcluster 16 main start
sudo pg_ctlcluster 16 main status
```

Adjust the cluster version or name when the local machine differs.

### 3. Activate the application environment

```bash
source .venv/bin/activate
```

Confirm that the repository is using the intended environment and database
target before starting the web process.

### 4. First-time-only bootstrap commands

These commands are not part of every startup.
Use them only when the environment is new or intentionally reset.

```bash
make install
make init-db
make seed-demo
```

Optional first-time data progression:

```bash
./.venv/bin/flask --app wsgi:app promote-final
```

### 5. Start the web application

```bash
make run
```

Expected result:

- the Flask application binds to the local development port
- the login screen becomes available
- the API health endpoint responds

Default local access:

- UI: `http://127.0.0.1:5000/`
- health: `http://127.0.0.1:5000/api/v1/health`

### 6. Start worker-backed operational commands when needed

The preproduct system uses explicit commands for queue-backed adapter work.

Use the following in a separate shell when those workflows are needed.

Enqueue due polling runs:

```bash
./.venv/bin/flask --app wsgi:app enqueue-scheduled-adapter-runs --limit 10
```

Process waiting adapter runs:

```bash
./.venv/bin/flask --app wsgi:app process-adapter-runs --limit 10
```

Refresh adapter health alerts:

```bash
./.venv/bin/flask --app wsgi:app refresh-adapter-health-alerts
```

Use these commands when:

- a scheduler is driving due polling work
- manual or scheduled adapter runs need to be consumed
- stale or overdue adapter alert visibility needs refreshing

### 7. Post-start validation

After startup, perform this minimum validation:

1. open the health endpoint
2. log in with an `admin` or `operator` account
3. open the dashboard
4. review:
   - `Integration` summary
   - open alerts
   - recent operational events
5. open one HES detail page and one adapter detail page
6. confirm the environment matches the intended dataset and timezone

The system should not be treated as ready until these checks succeed.

## Shutdown procedure

This section describes the recommended normal shutdown order.

### 1. Check for in-flight work

Before stopping the application, review whether any of the following are still
active:

- `processing` replay requests
- `processing` billing export requests
- adapter runs that are currently `running`
- a manual correction action that just started and has not yet refreshed

If any of these are in progress, prefer waiting for completion unless there is a
specific need to interrupt the local environment.

### 2. Capture important operator state before shutdown

Before stopping the environment, review and record:

- open alerts that still need follow-up
- blocked VEE exceptions
- failed replay or export requests
- recent operational events that explain the current state

This makes restart triage easier when the system is brought back later.

### 3. Stop worker commands

Stop any long-running or manually launched worker shells first.

Typical cases:

- `enqueue-scheduled-adapter-runs`
- `process-adapter-runs`
- `refresh-adapter-health-alerts`

If they are running in the foreground, stop them cleanly with `Ctrl-C`.

### 4. Stop the web application

Stop the Flask process in the shell where `make run` is active.

Expected result:

- the browser can no longer load the local UI
- the health endpoint stops responding

### 5. Stop PostgreSQL only when appropriate

If the machine is a shared development host, do not stop PostgreSQL unless you
know no other local process depends on it.

When the database is dedicated to this local environment and shutdown is
intended, use one of the documented methods:

```bash
sudo systemctl stop postgresql
```

Or:

```bash
sudo pg_ctlcluster 16 main stop
```

### 6. Post-stop verification

Confirm:

- the Flask process is no longer serving the UI
- worker shells have exited
- PostgreSQL is stopped only if that was intended

### 7. Restart after abnormal termination

If the application or local database stopped unexpectedly:

1. bring PostgreSQL back first
2. restart the web application
3. log in and open the dashboard
4. review recent operational events and open alerts
5. inspect any request or adapter that was previously `processing`
6. confirm whether the interruption left stale or failed runtime state

## Daily opening procedure

Use this at the start of a normal operating session.

### 1. Log in

Log in with the least-privileged account that fits the task:

- `operator` for routine monitoring, correction, replay, and export inspection
- `admin` when HES, adapter, or master-data mutations are needed

### 2. Start from the dashboard

Review the dashboard in this order:

1. open alerts
2. integration summary
3. recent operational events
4. replay or export items that show processing failure or delay

### 3. Identify immediate operator attention items

Prioritize:

- blocking VEE exceptions
- stale or overdue adapters
- failed replay requests
- failed export requests
- new master-data or mapping gaps

### 4. Open the next most relevant detail page

Use the dashboard state to choose the next screen:

- HES detail for source- or adapter-centric problems
- adapter detail for runtime execution or watermark problems
- VEE exception detail for blocked measurement or correction problems
- replay or export request detail for queue-backed processing problems
- operational-event detail for accountability and recent action context

## First-time and change-driven setup

Use these procedures when a new environment or new upstream source is being
prepared.

### 1. Confirm user accounts

Before opening the environment to operators, confirm:

- at least one `admin` account exists
- at least one `operator` account exists
- the intended users can log in successfully

### 2. Register an HES

Use the HES management screens when onboarding or updating an upstream source.

Typical steps:

1. open the HES list
2. create a new HES registration
3. confirm source identity, timezone, delivery mode, and masked connection
   metadata
4. open the HES detail page
5. confirm linked-adapter and recent-activity sections are available

### 3. Register or attach runtime adapters

After HES registration:

1. create or attach the required adapter instance
2. verify masked runtime configuration
3. use `Run Once` for bounded validation
4. process queued runs
5. review recent adapter runs and operational events

Use the adapter procedures in
[adapter-operator-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operator-runbook.md)
for deeper troubleshooting.

### 4. Register minimum master data

Before trusting raw-to-canonical mapping, confirm:

- service points exist
- devices exist
- measuring components exist
- installation history connects devices and service points correctly
- meter and channel identifiers match the upstream source shape

### 5. Confirm lineage before operational use

Before broader use, confirm one end-to-end sample:

1. raw read or event ingest
2. canonical measurement visibility
3. final measurement visibility
4. VEE or correction path visibility if the sample includes an exception

## Major feature procedures

### A. HES and adapter operations

Use these screens first:

- HES list and HES detail
- adapter list
- adapter detail

Use them to answer:

- which upstream HES is affected
- which runtime adapter belongs to that HES
- whether the adapter is `ready`, `running`, `paused`, or `error`
- whether recent runs succeeded or failed

Typical actions:

- `Enable`
- `Pause`
- `Run Once`

Operational meaning:

- `Enable`
  - allow future scheduled or manual execution again
- `Pause`
  - stop future scheduled execution while preserving history
- `Run Once`
  - queue one explicit validation or recovery run

### B. Raw, canonical, and final lineage review

Use these screens when confirming ingest and progression:

- raw reads
- raw events
- canonical measurements
- final measurements

Review them in this order:

1. raw ingest visibility
2. canonical measurements
3. final measurements
4. related usage, determinant, or charge screens if downstream confirmation is
   needed

Use this flow when the question is:

- did the source payload arrive
- did it map successfully
- did it become authoritative final data

### C. VEE exception triage

Use:

- VEE exception queue
- VEE exception detail

Recommended flow:

1. open the queue
2. prioritize blocking exceptions first
3. open the detail view
4. inspect raw, canonical, initial, final, and event context
5. acknowledge when review has started
6. choose whether correction or re-evaluation is the next step

### D. Estimation

Use estimation when a supported correction path is appropriate and policy allows
it.

Recommended operator flow:

1. open the VEE exception detail
2. review blocked guidance and related context
3. apply estimation only for a supported case
4. confirm:
   - the result summary
   - the estimation audit detail
   - VEE resolution or reopening behavior
   - downstream recalculation outcome

### E. Manual edit

Use manual edit when the operator must explicitly enter the corrected value or
status context.

Recommended operator flow:

1. open the VEE exception detail
2. confirm the case is policy-supported
3. enter the manual edit inputs and operator memo
4. confirm:
   - result code
   - blocked reason if any
   - manual-edit audit detail
   - actor lineage
   - downstream recalculation effect

### F. Replay requests

Use replay when a broader re-evaluation or request-oriented processing path is
needed.

Use:

- replay request list
- replay request detail

Recommended flow:

1. create a replay request with the correct scope
2. monitor request status and progress
3. inspect failed items first when present
4. cancel only queued requests when needed
5. confirm action actor and runtime processing identity separately

### G. Billing export requests

Use:

- billing export request list
- billing export request detail

Recommended flow:

1. create the request
2. review request and item status
3. inspect failed items or last error when present
4. cancel queued requests when needed
5. rerun or recreate failed requests only when the upstream issue is understood

### H. Audit and accountability

Use these screens when confirming who changed or requested something:

- operational-event detail
- estimation audit detail
- manual-edit audit detail
- replay request detail
- billing export request detail
- HES detail
- master-data rows

What to confirm first:

- action actor
- actor type such as human account, recorded requester, or runtime worker
- result code or blocked reason
- operator memo
- created actor and updated actor on admin-managed rows

## Incident triage quick guide

### Stale or overdue adapter

Open first:

- dashboard
- HES detail
- adapter detail

Confirm:

- whether the adapter is paused intentionally
- whether the latest run failed
- whether heartbeat or schedule freshness is stale

First action:

- pause if unstable
- correct the cause
- `Enable`
- `Run Once`
- process waiting runs

### Failed replay request

Open first:

- replay request detail

Confirm:

- request status
- last error
- failed items
- representative exception links

First action:

- identify whether the issue is policy, data, or runtime related before retrying

### Failed billing export request

Open first:

- billing export request detail

Confirm:

- last error
- failed items
- queued versus failed state

First action:

- correct the cause before rerun or recreate

### Blocking VEE exception

Open first:

- VEE exception detail

Confirm:

- blocking reason
- event context
- related correction policy
- whether estimation, manual edit, or re-evaluation is the right next step

### Missing master data or mapping failure

Open first:

- ingest or raw visibility
- master-data page
- HES meter reference visibility when relevant

Confirm:

- missing service point, device, component, or installation lineage

First action:

- correct the prerequisite master data before retrying broader processing

## Daily closing procedure

At the end of an operating session, perform this short close-out:

1. review open alerts again
2. check for processing replay or export requests
3. review blocking VEE exceptions that remain unresolved
4. confirm whether any adapter should remain paused overnight
5. record any important memo or handoff note
6. decide whether the local environment remains running or will be shut down

If the environment will be stopped, then follow the shutdown procedure in this
manual.

## Current limitations operators should remember

The preproduct baseline still assumes:

- bounded internal use
- explicit worker commands for adapter queue processing
- synchronous single-object re-evaluation and correction feedback in some flows
- narrower automation than a full production operations platform
- accepted product limitations described in the MVP and preproduct docs

Operators should escalate unusual repeated failures instead of assuming every
recovery path is already fully automated.

## Appendix A. Frequently used commands

Local environment:

```bash
source .venv/bin/activate
make run
```

First-time bootstrap:

```bash
make install
make init-db
make seed-demo
./.venv/bin/flask --app wsgi:app promote-final
```

Adapter queue operations:

```bash
./.venv/bin/flask --app wsgi:app enqueue-scheduled-adapter-runs --limit 10
./.venv/bin/flask --app wsgi:app process-adapter-runs --limit 10
./.venv/bin/flask --app wsgi:app refresh-adapter-health-alerts
```

PostgreSQL checks:

```bash
pg_isready
sudo systemctl status postgresql
sudo pg_ctlcluster 16 main status
```

## Appendix B. Primary operator screens

- `/`
  - dashboard
- `/hes-systems`
  - HES list
- `/adapters`
  - adapter list
- `/master-data`
  - canonical master data
- `/raw-reads`
  - raw read visibility
- `/raw-events`
  - raw event visibility
- `/canonical-measurements`
  - canonical progression visibility
- `/final-measurements`
  - final authoritative measurement visibility
- `/vee-exceptions`
  - VEE queue
- `/vee-replay-requests`
  - replay request list
- `/billing-export-requests`
  - billing export request list
- `/operational-events`
  - timeline and alert history

## Appendix C. Related documents

- [postgresql-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/postgresql-runbook.md)
- [adapter-operator-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operator-runbook.md)
- [operator-workflows.md](/home/tprover/2604_sim_mdms_auto/docs/operator-workflows.md)
- [mvp-smoke-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/mvp-smoke-runbook.md)
- [hes-system-management.md](/home/tprover/2604_sim_mdms_auto/docs/hes-system-management.md)
- [re-vee-baseline-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/re-vee-baseline-runbook.md)
- [mdms-preproduct-plan.md](/home/tprover/2604_sim_mdms_auto/docs/mdms-preproduct-plan.md)
