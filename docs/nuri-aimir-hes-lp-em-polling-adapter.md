# NURI AIMIR HES LP_EM Polling Adapter

## Purpose

This document defines the first source-specific runtime adapter baseline for polling interval reads from the NURI AIMIR HES overseas deployment on Oracle.

The target source tables are:

- `LP_EM` for source read blocks
- `METER` for source meter reference data

## Scope

This baseline covers:

- runtime polling
- Oracle connectivity
- source watermarking
- optional landing persistence
- expansion into common raw interval rows
- completeness-state update

This baseline does not yet cover:

- raw event collection
- full master-data synchronization
- automatic semantic channel decoding
- historical backfill strategy across multiple years

## First-source rationale

This adapter is a good first real source adapter because:

- the project already has runtime adapter lifecycle scaffolding
- Oracle connectivity has been verified
- `LP_EM` and `METER` roles are understandable enough to begin
- the source layout is sufficiently different from the generic JSON ingest path to validate the landing-plus-expansion design

## Recommended adapter family

Suggested identifiers:

- `adapter_definition.adapter_code = nuri_aimir_hes_lp_em_poll_v1`
- `adapter_definition.delivery_mode = poll`
- `adapter_definition.record_type = hes_read_raw`
- `adapter_definition.adapter_profile_key = lp_em_block_v1`
- `adapter_definition.implementation_key = nuri_aimir_hes_lp_em_poll_v1`

## Recommended configuration

The adapter instance should support at least:

- Oracle host
- Oracle port
- Oracle SID or service name
- Oracle username
- Oracle password secret reference
- source timezone
- polling batch size
- allowed channels
- optional business-hour lower bound
- optional business-hour upper bound
- default interval minutes
- slot-index mode
- landing enabled flag
- watermark mode

Recommended current baseline:

- source timezone must be explicit
- slot-index mode should default to `minute_offset`
- watermark mode should start with `writedate`
- smoke or controlled live verification may additionally constrain `YYYYMMDDHH` with optional business-hour bounds

## Recommended extraction boundary

### Primary watermark candidate

Recommended first watermark:

- `LP_EM.WRITEDATE`

Reason:

- it appears to represent source write or arrival time
- it is better aligned with polling than `YYYYMMDDHH`, which looks like business time

### Tie-breaker

Because `LP_EM` has no inspected primary key, the runtime watermark should include a deterministic tie-breaker.

Recommended tuple:

- `WRITEDATE`
- `YYYYMMDDHH`
- `METER_ID`
- `CHANNEL`

If later source inspection shows the need, `MDEV_ID` may be added to the tie-breaker.

## Recommended polling query shape

Conceptually:

1. fetch source rows newer than the last committed watermark
2. order deterministically by watermark and tie-breaker
3. cap the fetch by adapter batch size

Pseudo-shape:

```sql
select ...
from LP_EM
where
  WRITEDATE > :last_writedate
  or (
    WRITEDATE = :last_writedate
    and (
      YYYYMMDDHH > :last_yyyymmddhh
      or (
        YYYYMMDDHH = :last_yyyymmddhh
        and (
          METER_ID > :last_meter_id
          or (
            METER_ID = :last_meter_id
            and CHANNEL > :last_channel
          )
        )
      )
    )
  )
order by WRITEDATE, YYYYMMDDHH, METER_ID, CHANNEL
fetch first :batch_size rows only
```

## Important source-side caution

The inspected metadata did not show useful indexes on `LP_EM`.

That means the project should explicitly validate source-side performance before relying on a production polling frequency.

Recommended next checks with the source team:

- whether `WRITEDATE` is indexed
- whether `YYYYMMDDHH` is indexed
- whether the table is partitioned
- whether a source-side view or extraction table should be introduced

## Recommended runtime flow

1. scheduler or operator triggers an `adapter_run`
2. adapter claims the run
3. adapter opens Oracle connection
4. adapter reads a bounded batch of `LP_EM` source rows
5. adapter optionally reads or caches matching `METER` rows
6. adapter persists source blocks to landing when configured
7. adapter expands source blocks into interval-level common raw rows
8. adapter updates completeness-state rows
9. adapter updates run summary and watermark
10. adapter commits success

## Recommended landing behavior

For this source, landing is strongly recommended in the first implementation.

Why:

- `LP_EM` is a block table, not an interval-row table
- replaying block expansion without rereading Oracle is valuable
- late-write handling will be easier to audit

Recommended first landing meaning:

- one landing row equals one `LP_EM` source row

## Recommended common raw behavior

After landing, the adapter should expand each non-null slot into one interval-level common raw row.

The adapter should not persist the packed `VALUE_00` through `VALUE_59` layout directly into the common raw table.

## Recommended completeness-state behavior

For each expanded source block, the adapter should update one completeness window per:

- meter
- channel
- source hour

Recommended window anchor:

- parsed `YYYYMMDDHH`

Recommended state fields:

- expected slot count
- received slot count
- received slot bitmap
- last source write timestamp
- status

## Recommended METER usage

`METER` should be used for:

- existence validation
- `MDS_ID` cross-check
- `LP_INTERVAL` lookup
- source location and supplier cross-check

The adapter should tolerate `METER` enrichment failure as a controlled error path and surface it through adapter-run details or ingest errors.

## Recommended operator visibility

The adapter UI should eventually show:

- source family = Oracle HES
- last Oracle connection success
- last watermark
- rows fetched
- blocks landed
- interval rows expanded
- completeness windows updated
- last error summary

## Recommended first implementation boundaries

Include now:

- one Oracle polling adapter implementation
- `WRITEDATE` watermark
- deterministic ordering
- optional landing
- expansion into common raw interval rows
- completeness-state update

Defer for later:

- adaptive parallel polling
- historical bulk backfill
- automatic source SQL generation from UI
- channel-semantic decoding
- master-data synchronization beyond required lookup fields

## Testing expectations

The first implementation should prove:

- Oracle connection success and failure handling
- deterministic watermark advancement
- replay safety
- landing replay behavior
- slot expansion behavior
- completeness-state updates
- late-write handling for the same logical interval window

## Related documents

- [polling-adapter-baseline.md](/home/tprover/2604_sim_mdms_auto/docs/polling-adapter-baseline.md)
- [common-raw-interval-model.md](/home/tprover/2604_sim_mdms_auto/docs/common-raw-interval-model.md)
- [lp-em-adapter-mapping.md](/home/tprover/2604_sim_mdms_auto/docs/lp-em-adapter-mapping.md)
- [adapter-runtime-lifecycle.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-runtime-lifecycle.md)
- [adapter-live-hardening-plan.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-live-hardening-plan.md)
- [adapter-test-matrix.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-test-matrix.md)
- [adapter-operator-runbook.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-operator-runbook.md)
