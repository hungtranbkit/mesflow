# Task Scope: Fix MESFlow `main` Baseline Test Failures

Status of this document: **task definition only, nothing in it has been
executed**. Written after the Universal CI/CD Standard V1 Phase 2 pass
discovered these failures as a side effect of fixing 2 unrelated,
originally-targeted tests in `test_shift_dashboard.py` (see
`docs/CI_CD_STANDARD.md` and the workspace's Phase 2 report for that
work, which is NOT part of this scope).

## 0. Origin and evidence (do not re-derive, verify instead)

Running the full test suite (`./scripts/ci/run-project mesflow-app` from
the outer workspace, or equivalently `scripts/test/docker-test.sh` from
inside `mesflow/`) against `mesflow/`'s `main` branch produces:

```
226 passed, 32 failed, 1 skipped, 541 deselected in ~104s
```

The 32 failures were confirmed, on the SAME run, to be:
- present on vanilla `main` with no other changes applied (isolated via
  `git stash` against an unrelated fix, re-run, confirmed identical
  failure set both times)
- unrelated in subject matter to whatever else was being worked on at
  the time (day-boundary shift dashboard logic) -- these 32 sit in three
  completely different subsystems, listed below
- reproducible: two separate full-suite runs on the same commit produced
  the exact same 32 test names

This is real, current, verified data as of this writing (mesflow `main`
at commit `6564d92` plus the two later, unrelated, already-committed
fixes on `feature/workspace-cicd-v1`: `76932f4` PROJECT.yaml `ci:` block,
`da01edf` the shift-dashboard fix -- neither touches any file these 32
failures come from). Re-verify with a fresh run before starting; do not
assume this list is still accurate without checking, since `main` may
have moved.

## 1. Git safety (read before touching anything)

```bash
cd /home/dell/workspace/mesflow/mesflow
git status --short
git branch --show-current
git log --oneline -15
```

- Do NOT assume this repo is on `main` or is clean -- another session
  changed its checked-out branch mid-task once already this week.
- If the working tree is dirty with anything unrelated to this task:
  **PRESERVE, DO NOT TOUCH, REPORT** -- do not stash/commit/clean it
  to "get a clean baseline."
- Create a dedicated branch off `main` for this work, e.g.
  `fix/baseline-test-failures`. Do NOT do this work on
  `feature/session-management-upgrade` or `feature/workspace-cicd-v1` --
  both are unrelated, active branches with their own history; do not
  merge, rebase onto, or cherry-pick from either without being
  explicitly asked.
- Forbidden: `git reset --hard`, `git clean -fd`, `git checkout -- .`,
  `git restore .`, force push, history rewrite -- same rules as every
  other task in this workspace (see `../AGENTS.md`).
- Do not fix a failing test by weakening or deleting the assertion. Do
  not mark a test `xfail`/`skip` to make the suite "green" -- that is a
  fabricated PASS, prohibited by `../AGENTS.md`'s Honesty rule.

## 2. Scope: three independent clusters

These do not share code paths (confirmed by file/subsystem separation)
and can be investigated/fixed independently, in parallel by different
sessions if useful, or sequentially by one. Each cluster gets its own
root-cause classification and its own fix -- do not apply one fix and
assume it resolves another cluster.

### Cluster A -- Employee Productivity (9 tests)

`tests/integration/test_employee_productivity.py`:
- `test_employee_a_two_sessions_50_and_70_average_60`
- `test_task_case_employee_a_50_70_running_120_excluded_entirely`
- `test_task_case_employee_b_only_running_sessions_no_score_not_zero`
- `test_employee_b_100_100_120_average_106_67`
- `test_employee_c_completed_80_plus_running_excluded_from_average`
- `test_employee_d_missing_denominator_not_zero_not_crash`
- `test_date_range_excludes_sessions_outside_window`
- `test_ended_at_not_started_at_decides_the_reporting_date`
- `test_response_never_exposes_running_or_active_worker_fields`

Names suggest this is about a per-employee productivity/scoring
average, with rules around: running (unfinished) sessions excluded from
the average, a denominator-missing edge case, date-range filtering by
`ended_at` not `started_at`, and a "never expose running/active worker
state" contract. Likely implicated: whatever repository method computes
employee productivity averages (grep for `productivity` in
`app/mesflow/db/repositories/`) and its report/API layer.

### Cluster B -- Employee Productivity Wallboard (12 tests)

`tests/integration/test_employee_productivity_wallboard.py`:
- `test_case1_fixed_range_publish_reflected_on_public_wallboard`
- `test_case2_dynamic_month_to_date_resolves_to_today`
- `test_case3_department_filter_propagates_to_wallboard`
- `test_case4_sort_change_propagates_to_wallboard_order`
- `test_case7_wallboard_refetch_keeps_filter_but_updates_data`
- `test_case9_wallboard_returns_full_list_for_client_side_paging`
- `test_wallboard_never_exposes_running_or_active_worker_state`
- `test_wallboard_employee_with_only_running_session_never_appears`
- `test_publish_rejects_fixed_mode_without_dates`
- `test_publish_rejects_from_after_to`
- `test_public_wallboard_data_requires_no_auth`
- `test_public_wallboard_payload_carries_display_settings`

Likely builds on top of Cluster A's productivity calculation (a
"publish this to a public wallboard" layer with its own filter/sort/
pagination/validation contract) -- **investigate whether Cluster A's
root cause is the actual shared root cause for both** before treating
them as two separate fixes. If Cluster A's fix alone resolves some or
all of Cluster B, say so plainly rather than doing duplicate work.

### Cluster C -- Kiosk V2 (11 tests, 3 files)

`tests/integration/test_kiosk_v2_bootstrap_environment.py`:
- `test_health_reports_server_identity`
- `test_bootstrap_reports_server_identity`

`tests/integration/test_kiosk_v2_disabled_identity_rejection.py`:
- `test_bootstrap_rejects_non_active_identity_with_real_403[SUSPENDED]`
- `test_bootstrap_rejects_non_active_identity_with_real_403[DISABLED]`
- `test_bootstrap_rejects_non_active_identity_with_real_403[PENDING]`
- `test_heartbeat_rejects_suspended_identity_with_real_403`

`tests/integration/test_kiosk_v2_heartbeat_liveness.py`:
- `test_v2_heartbeat_actually_updates_kiosk_status_liveness`
- `test_v2_heartbeat_still_rejects_disabled_kiosk`

`tests/integration/test_kiosk_v2_shared_terminal.py`:
- `test_full_shared_terminal_multi_user_scenario`
- `test_employee_b_scan_does_not_get_blocked_by_employee_a_open_session`
- `test_response_never_contains_previous_users_temporary_state`

These are unrelated to A/B -- kiosk device identity/heartbeat/bootstrap
plus the shared-terminal (multi-user handoff on one physical kiosk)
state machine. One sample failure already observed:
`test_employee_b_scan_does_not_get_blocked_by_employee_a_open_session`
asserted `state.name == 'WAIT_EMPLOYEE'` but got `'SESSION_ACTIVE'` --
i.e. scanning employee B's badge while A's session is open did not reset
the terminal to a clean slate as expected. Treat the 4 files as one
cluster (shared kiosk-v2 endpoint/state-machine code) but do not assume
all 11 share one root cause without checking -- bootstrap/heartbeat
identity-rejection and the shared-terminal handoff may be two distinct
bugs that happen to sit in the same subsystem.

## 3. Required process, per cluster

1. Run just that cluster's test file(s) in isolation first, to get a
   clean, minimal reproduction:
   ```bash
   cd /home/dell/workspace/mesflow/mesflow
   docker compose -f compose.test.yml up --build -d postgres-test mesflow-test-api
   docker compose -f compose.test.yml run --rm tests pytest -q \
     tests/integration/<file>.py -m postgres
   ```
2. Read the failing assertion and the test's own docstring/comments
   carefully -- several of these tests (matching the pattern already
   found in `test_shift_dashboard.py`) may have comments describing the
   INTENDED contract, which is the fastest way to tell stale-test from
   regressed-behavior.
3. Classify each failure (per-test, not just per-cluster) as one of:
   - **A. stale test expectation** -- the test asserts an old, no-longer
     -intended contract; the code's current behavior is the one that's
     actually correct now. Fix: update the test, with a comment
     explaining why the old expectation was wrong, matching this
     repo's existing convention (see `test_shift_dashboard.py`'s own
     comments for the style).
   - **B. business behavior regressed** -- the code no longer does what
     it is documented/intended to do. Fix: the smallest correct change
     to the implementation, not the test.
   - **C. fixture/timezone/shift/test-data issue** -- the test's own
     setup is wrong (bad fixture data, wrong assumed timezone, a shift
     window that no longer matches the real seed data), independent of
     both the implementation and the test's own assertions being
     correct in principle.
   - **D. environment/timing/flake** -- non-deterministic, order-
     dependent, or infra-dependent (only plausible if a failure does NOT
     reproduce consistently across repeated runs -- verify by running
     the same file 2-3 times before concluding this).
4. Fix the smallest correct thing for that classification. Do not
   refactor unrelated code "while you're in there."
5. Do not fix a test by making it accept a wrong answer, and do not fix
   code by deleting/loosening a real invariant the test is protecting
   (e.g. "never expose running/active worker state," "reject a
   suspended/disabled kiosk with 403") -- these read as deliberate
   security/data-integrity contracts, not incidental assertions.

## 4. Verification required before claiming a cluster fixed

- The specific failing tests in that cluster now pass, run in isolation.
- No other previously-passing test in the same file regresses.
- Run the FULL suite once more after all three clusters are addressed
  (or after each, if done sequentially) to confirm the count moves from
  `226 passed, 32 failed` toward `passed, 0 failed` and that nothing
  outside the 32 named tests newly breaks:
  ```bash
  cd /home/dell/workspace/mesflow
  ./scripts/ci/run-project mesflow-app
  ```
  (this reuses the exact same contract already wired by the Universal
  CI/CD Standard V1 foundation -- do not invent a parallel test-running
  script).
- If a cluster cannot be fully resolved in scope, report exactly which
  tests remain failing and why, rather than silently leaving them.

## 5. Explicit non-goals

- Do not touch `scripts/ci/*`, `.github/workflows/*`, `PROJECT.yaml`'s
  `ci:` block, or anything else from the Universal CI/CD Standard V1
  work -- that is a separate, already-completed, already-reported task.
- Do not touch `feature/session-management-upgrade`'s content or merge
  it.
- Do not change test markers/`pytest.ini` to exclude these tests instead
  of fixing them.
- Do not attempt to fix all 32 in one giant commit -- commit per cluster
  (or smaller, per root cause) with a message that states the
  classification (A/B/C/D) and the reasoning, matching this repo's
  existing commit style (see `da01edf` for an example of the expected
  level of detail).

## 6. Final report format expected

```
STATUS: PASS / FIX_REQUIRED

CLUSTER A (employee productivity):
- tests fixed / still failing
- root cause classification (A/B/C/D) per test or per shared cause
- fix summary
- regression evidence

CLUSTER B (productivity wallboard):
- same, plus explicit note on shared-root-cause-with-A or not

CLUSTER C (kiosk v2):
- same

FULL SUITE RESULT: <passed>/<total>, <failed> failed, <skipped> skipped

FILES CHANGED:
TESTS:
UNRELATED WIP PRESERVED:
REMAINING RISKS:
```
