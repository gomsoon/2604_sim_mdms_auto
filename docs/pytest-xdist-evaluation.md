# Pytest xdist Evaluation

## Purpose

This document captures the current `pytest-xdist` evaluation history so future work can resume without repeating the same discovery steps.

## Environment snapshot

- Repository path: `/home/tprover/2604_sim_mdms_auto`
- Current virtual environment interpreter: `./.venv/bin/python`
- Current virtual environment Python version during evaluation: `3.12.13`
- System Python available as `python3`: `3.10.12`
- Bare `python` command was not available in the evaluation shell
- Main test database baseline: `mdms_test`
- Functional smoke tests continue to use their own temporary schema under the same PostgreSQL instance

## Why this evaluation started

- The repository test suite keeps growing and the serial `pytest` runtime is becoming heavier.
- The current machine has `16` CPU cores, so `xdist` with `n=4` looked like a reasonable first target.
- The goal was to speed up the main non-functional regression path without weakening the branch coverage baseline or destabilizing the PostgreSQL-backed tests.

## What was changed for the evaluation

### Dependency baseline

- `pytest-xdist` was added to the development dependency set in [pyproject.toml](/home/tprover/2604_sim_mdms_auto/pyproject.toml).

### Harness-hardening ideas that were explored

- Test-only database paths were experimentally modified to disable SQLAlchemy connection pooling through `NullPool`.
- That idea showed some promising single-run results but did not become a stable repeated baseline.
- Because repeated validation was still flaky, those harness experiments should be treated as evaluation notes rather than locked baseline behavior.

## Commands that were evaluated

### Stable serial non-functional regression

```bash
./.venv/bin/pytest --ignore=tests/functional --cov-fail-under=80
```

### Candidate parallel non-functional regression

```bash
./.venv/bin/pytest -n 4 --dist loadfile --ignore=tests/functional --cov-fail-under=80
```

### Separate functional smoke path

```bash
./.venv/bin/pytest tests/functional
```

## What was learned

### 1. `tests/functional` should stay separate

- Running browser-backed functional tests in the same pytest session as the main PostgreSQL schema-isolated suite is not part of the stable path.
- The functional suite should continue to run as its own command.

### 2. The non-functional suite is the real `xdist` target

- The main non-functional regression suite is the only practical target for `xdist`.
- That path is already separated with `--ignore=tests/functional`.

### 3. Connection-pool reuse is still a valid investigation topic

- PostgreSQL failures often happened very early during schema creation and test setup.
- Disabling pooling in test-only DB paths looked promising in some runs, but the result was not stable enough to declare it solved.

### 4. `n=4` was promising but still flaky

- After the `NullPool` hardening, both of the following happened:
  - successful serial non-functional regression
  - successful `n=4` parallel non-functional regression
- However, repeated validation still produced flaky PostgreSQL failures under parallel churn, especially:
  - `psycopg.OperationalError: connection is bad: no error details available`
- Because the same command could pass once and fail on a later retry, the repository baseline should not yet switch to `xdist` by default.

### 5. Python-version mismatch was not the root cause

- The successful and failed `pytest` runs observed during this evaluation both used the virtual environment interpreter, `Python 3.12.13`.
- The system `python3` is `3.10.12`, but it did not explain the flaky behavior seen in the evaluated repository commands.

## Current conclusion

- `pytest-xdist` is worth keeping installed.
- The repository should continue to treat the main regression baseline as:
  - serial non-functional regression
  - separate serial functional smoke
- `xdist` should remain an explicit future-hardening topic, not the default execution mode yet.

## Recommended next steps

### Near-term

- Keep `pytest-xdist` installed but non-default.
- Keep the `NullPool`-based test harness hardening.
- Continue to run the main non-functional suite without `xdist` as the stable baseline.

### Next evaluation options

- Re-evaluate `xdist` at `n=2` instead of `n=4`
- Consider mapping workers across multiple test databases only if simpler hardening fails
- Identify and isolate more pure non-DB tests if a small parallel fast path becomes worthwhile
- Continue distinguishing:
  - pure unit tests
  - PostgreSQL integration tests
  - browser functional tests

## Practical restart point for the next session

When this work resumes, the next useful check order is:

1. Confirm the current test harness changes are still present
2. Re-run stable serial non-functional regression
3. Re-run a single `xdist` experiment on the non-functional suite only
4. Decide whether to:
   - try `n=2`
   - try multiple test databases
   - or stop and keep the serial baseline
