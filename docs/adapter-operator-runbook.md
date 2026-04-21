# Adapter Operator Runbook

## Purpose

This document defines the recommended minimal-stage operating procedure for runtime adapters.

It is written for administrators who need to:

- inspect adapter health
- trigger a safe run
- pause future collection
- verify what a completed run actually did

## Minimal-stage operating model

In the minimal stage, adapter operations are:

- state-driven
- worker-backed
- auditable through database-backed run records and events

They are not:

- direct browser control of long-running OS processes
- force-stop orchestration for an already-running poll

## Operator-facing actions

### Enable

Meaning:

- allow the adapter instance to participate in future scheduled or manual execution again

Use when:

- a paused adapter is ready to collect again

### Pause

Meaning:

- prevent future scheduled execution
- keep the adapter definition, configuration, runs, and watermarks intact

Use when:

- source credentials are being updated
- source behavior is unstable
- operator wants to stop future polling safely

### Run Once

Meaning:

- create one explicit `adapter_run` for immediate collection or verification

Use when:

- verifying a new configuration
- validating watermark behavior
- checking recovery after a recent failure

## Core operational screens

### Dashboard

The dashboard should be used first to inspect:

- `Integration` card
- overdue adapter count
- stale adapter count
- open alerts
- recent events

### Adapter list

Use the adapter list to inspect:

- effective status
- overdue or stale markers
- last success
- last failure
- last heartbeat

### Adapter detail

Use adapter detail to inspect:

- current configuration summary
- recent runs
- watermark
- latest error summary

## Worker commands

The minimal-stage runtime path relies on worker commands.

### Enqueue due polling runs

```bash
./.venv/bin/flask --app wsgi:app enqueue-scheduled-adapter-runs --limit 10
```

Use when:

- a simple external scheduler such as `cron` or `systemd timer` is driving scheduled work

### Process waiting adapter runs

```bash
./.venv/bin/flask --app wsgi:app process-adapter-runs --limit 10
```

Use when:

- processing queued manual or scheduled adapter runs

### Refresh adapter health alerts

```bash
./.venv/bin/flask --app wsgi:app refresh-adapter-health-alerts
```

Use when:

- verifying overdue or stale alert synchronization
- checking whether recovered adapters close their health alerts

## Recommended minimal operating procedures

### Procedure 1. Validate a new adapter instance

1. Open adapter detail
2. Verify masked connection settings and poll interval
3. Trigger `Run Once`
4. Process waiting runs
5. Review the latest `adapter_run`
6. Review watermark movement
7. Review landing and common-raw effects if needed

### Procedure 2. Pause an unhealthy adapter

1. Confirm the adapter is showing overdue, stale, or repeated failure
2. Open adapter detail
3. Use `Pause`
4. Confirm future schedule is blocked
5. Confirm related health alert closes or remains historically visible
6. Investigate configuration, source connectivity, or downstream persistence issues

### Procedure 3. Resume after correction

1. Correct the configuration or source issue
2. Use `Enable`
3. Trigger `Run Once`
4. Process waiting runs
5. Verify successful run summary
6. Verify watermark and last-success timestamps

## What to inspect after a run

After a completed or failed run, inspect at least:

- `adapter_run.run_status`
- `adapter_run.error_code`
- `adapter_run.error_summary`
- `adapter_run.source_rows_fetched`
- `adapter_run.ingest_batches_created`
- `adapter_run.ingest_records_created`
- `adapter_watermark.cursor_value`
- recent `operational_event` rows
- any open adapter health or run-failure alerts

## Recommended troubleshooting split

### Configuration problem

Symptoms:

- failure happens before a meaningful source query
- run error is immediate and repeatable

Check:

- masked connection config
- `secret_ref`
- SID or service-name choice
- batch size

### Source connectivity problem

Symptoms:

- connection or authentication failure

Check:

- Oracle reachability
- credentials
- source listener status

### Query or source-shape problem

Symptoms:

- query failure
- unexpected source fields
- parse issues

Check:

- source table shape
- cursor ordering assumptions
- allowed channels

### Replay or duplicate problem

Symptoms:

- repeated polling of the same logical source rows
- duplicate common-raw effects

Check:

- watermark progression
- landing uniqueness
- common-raw duplicate protection

## Minimal-stage limitations

Operators should assume the following limitations still exist:

- `Pause` is safe, but hard-stop is not supported
- long-running scheduler control does not live inside Flask
- adapter code is still deployment-backed, not UI-authored
- alert conditions are still code-backed, not operator-managed through a rule table

## Related documents

- [minimal-adapter-operations-boundary.md](/home/tprover/2604_sim_mdms_auto/docs/minimal-adapter-operations-boundary.md)
- [adapter-live-hardening-plan.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-live-hardening-plan.md)
- [adapter-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-test-matrix.md)
- [adapter-backlog.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-backlog.md)
