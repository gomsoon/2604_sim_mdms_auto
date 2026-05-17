# MVP Smoke Runbook

## Purpose

This runbook turns the MVP close-out checklist into one bounded operator smoke
pass.

It is intended for first internal-use validation, not for exhaustive QA.

## Preconditions

- the database is migrated to current head
- at least one `admin` account and one `operator` account exist
- at least one HES, adapter, service point, device, and measuring component are
  available
- sample ingest data and at least one replayable correction case exist

## Smoke sequence

### 1. Authentication and role split

Actions:

- log in as `admin`
- log out
- log in as `operator`

Expected result:

- both accounts can log in successfully
- logout returns to the login screen
- protected screens require authentication

### 2. Raw ingest baseline

Actions:

- ingest raw reads
- ingest raw events
- open dashboard and HES detail

Expected result:

- ingest batches complete without unexpected fatal failure
- ingest visibility shows recent batches and raw counts

### 3. Measurement lineage baseline

Actions:

- open a recent service point and inspect raw, canonical, initial, and final
  lineage

Expected result:

- canonical and final lineage is visible
- current final rows are consistent with the latest accepted correction path

### 4. VEE exception handling

Actions:

- open a supported VEE exception
- acknowledge it
- re-evaluate it

Expected result:

- acknowledge and re-evaluate succeed
- actor lineage is visible on the exception

### 5. Supported correction path

Actions:

- choose one supported case and apply either:
  - substitution estimation
  - substitution manual edit

Expected result:

- correction succeeds
- VEE resolution is visible
- estimation or manual-edit audit records the logged-in actor

### 6. Synthetic missing-interval repair

Actions:

- open a supported single-slot missing-interval exception
- run synthetic missing-interval estimation

Expected result:

- repair succeeds on a supported single-slot case
- estimation audit shows anchor VEE, window context, and synthetic lineage

### 7. Downstream recalculation

Actions:

- inspect usage, determinant, and charge after the correction

Expected result:

- downstream recalculation completes
- current rows reflect the new correction result

### 8. Billing-lite summary

Actions:

- open invoice summary for an affected service point and period

Expected result:

- summary status and subtotal are visible
- blocked or partial cases are clearly distinguishable

### 9. Billing export flow

Actions:

- create an export request
- inspect detail visibility
- cancel a queued request or rerun/recreate a failed one

Expected result:

- export request actor lineage is visible
- recovery request lineage is visible
- runtime worker identity remains distinguishable from human actor identity

### 10. Admin mutation lineage

Actions:

- as `admin`, change a master-data row
- pause, enable, and run-once an adapter

Expected result:

- master-data rows store `created_by` or `updated_by` user lineage
- adapter admin actions record actor lineage
- manual run-once records requester lineage

## Close-out decision rule

Proceed with MVP close-out when:

- all smoke steps above pass without an unplanned blocker
- known limitations remain within the accepted MVP boundary
- no missing foundational subsystem is discovered during the pass

If a failure occurs, prefer a narrow bug fix or visibility clarification before
opening new product scope.
