# Adapter Test Matrix

## Purpose

This document turns adapter hardening expectations into concrete verification scope.

It is focused on runtime adapters, especially the first live `nuri_aimir_hes_lp_em_poll_v1` polling path.

## How to use this matrix

- use it before implementation to understand expected coverage
- use it during implementation to decide which tests must be added
- use it after implementation to confirm that regression scope is complete

## Test categories

The adapter area should be verified through five layers:

1. configuration validation tests
2. source polling and query tests
3. watermark and replay-safety tests
4. persistence and lineage tests
5. operator-visibility and alert tests

## Matrix

| Area | Scenario | Type | Expected result |
| --- | --- | --- | --- |
| Runtime config | missing `oracle_host` | unit | adapter fails with stable validation error |
| Runtime config | both `oracle_sid` and `oracle_service_name` present | unit | adapter fails with stable validation error |
| Runtime config | neither `oracle_sid` nor `oracle_service_name` present | unit | adapter fails with stable validation error |
| Runtime config | invalid `oracle_port` | unit | adapter fails with stable validation error |
| Runtime config | missing `secret_ref` or empty env target | unit | adapter fails before source query |
| Runtime config | invalid `allowed_channels` shape | unit | adapter fails with stable validation error |
| Oracle source | successful bounded query | unit or integration | rows are returned in deterministic order |
| Oracle source | connection failure | unit with mock | adapter run fails with stable source-connect error |
| Oracle source | authentication failure | unit with mock | adapter run fails with stable auth error |
| Oracle source | query execution failure | unit with mock | adapter run fails with stable query error |
| Watermark | no prior watermark | integration | first batch uses empty cursor and persists new watermark |
| Watermark | existing composite watermark | integration | query resumes after the stored cursor |
| Watermark | same source row replay | integration | replay does not create duplicate common-raw rows |
| Watermark | late source write in same logical hour | integration | landing and completeness state update safely |
| Watermark | failure before commit | integration | watermark does not advance incorrectly |
| Landing | landing enabled with one source block | integration | one landing row is persisted with expected lineage |
| Landing | same source block arrives twice | integration | landing uniqueness protects replay behavior |
| Common raw | one packed block expands into interval rows | integration | only non-null slots expand into common raw rows |
| Common raw | invalid slot or malformed value | integration | ingest error or adapter failure is recorded predictably |
| Completeness | first partial block for a window | integration | `raw_interval_window_state` becomes partial |
| Completeness | full expected slots received | integration | completeness becomes complete |
| Completeness | replay of already-complete window | integration | state remains correct and does not regress |
| Lineage | successful run | integration | `adapter_run`, `adapter_watermark`, `ingest_batch`, landing, and common raw are linked |
| Events | successful run | integration | informational event rows are emitted |
| Alerts | overdue condition detected | unit or integration | open alert is created once |
| Alerts | stale condition detected | unit or integration | open alert is created once |
| Alerts | overdue or stale recovers | unit or integration | alert is closed automatically |
| Operator control | `Run Once` on enabled adapter | web or integration | waiting run is queued |
| Operator control | `Pause` on unhealthy adapter | web or integration | future schedule is blocked and health alert closes |
| Scheduler | due polling adapter | integration | scheduled enqueue creates one waiting run |
| Scheduler | paused adapter | integration | no scheduled run is created |
| Scheduler | active waiting or running run exists | integration | no overlapping run is created |
| Dashboard | integration card with overdue or stale adapter | service or web | counts match adapter health interpretation |
| Event history | operator filters adapter events and alerts | web or API | filters return expected rows |

## Boundary-value expectations

Every adapter-related code change should consider at least:

- missing config vs valid config
- smallest positive batch size vs zero or negative
- empty channel list vs one channel vs many channels
- no watermark vs existing watermark
- first source row vs last row in a fetched batch
- no landing rows vs one landing row vs duplicate landing row
- no interval slots vs one non-null slot vs many slots
- paused adapter vs enabled adapter
- no open alert vs one existing open alert

## PostgreSQL integration expectations

The adapter path should continue expanding PostgreSQL-backed tests for:

- scheduler enqueue state transitions
- run claim overlap prevention
- watermark updates
- landing uniqueness
- common-raw duplicate protection
- alert open and close transitions

SQLite is no longer the target baseline for these behaviors.

## Functional smoke recommendations

Playwright or operator-style smoke coverage should eventually include:

- adapter list visibility
- adapter detail visibility
- `Run Once`
- adapter run history
- open alert visibility for adapter health
- event history filtering

## Current highest-priority gaps

The most valuable next tests are:

1. PostgreSQL-backed scheduled-run and overlap tests
2. replay and late-write tests for `nuri_aimir_hes` polling
3. live-config validation regression tests
4. operator event and alert drill-down smoke tests

## Related documents

- [testing-strategy.md](/home/tprover/2604_sim_mdms_auto/docs/testing-strategy.md)
- [adapter-live-hardening-plan.md](/home/tprover/2604_sim_mdms_auto/docs/adapter-live-hardening-plan.md)
- [nuri-aimir-hes-lp-em-polling-adapter.md](/home/tprover/2604_sim_mdms_auto/docs/nuri-aimir-hes-lp-em-polling-adapter.md)
