# Shift Auto-Close Rollout Runbook

Fix Plan Phase 15 (Migration/Rollout Safety). This is the required sequence
for turning on shift-end session auto-close (Fix Plan Phases 2/3/5) in any
environment (dev, prod-test, or production), and the safety flags that back
it. Read this before flipping `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1` anywhere.

## Principle

Migrations only change **schema**. They never auto-close a single historical
stale session inline (migrations `0040_shift_lifecycle_scheduler_health` and
`0041_job_health_last_success` add columns/tables/seed rows only — check
their `upgrade()` bodies if you want to confirm this yourself). All actual
session auto-closing happens through `reconcile-shift-sessions`, which you
control explicitly, in `--dry-run` first, per this runbook.

## Config flags

| Flag | Default | Meaning |
|---|---|---|
| `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED` | `0` | Master switch. `0` = `reconcile-shift-sessions` finds candidates but performs no writes. |
| `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN` | `1` | Independent of the above — even with `ENABLED=1`, `DRY_RUN=1` logs what *would* close without closing it. Belt-and-suspenders: a first production deploy should have `ENABLED=1, DRY_RUN=1` before ever setting `DRY_RUN=0`. |
| `MESFLOW_SHIFT_AUTO_CLOSE_GRACE_MINUTES` | `15` | How long past a shift's end boundary a session must sit before it's a candidate. |
| `MESFLOW_SESSION_PAST_SHIFT_END_GRACE_MINUTES` | `10` | Separate grace window used only by the `SESSION_PAST_SHIFT_END` exception condition (Phase 5) — deliberately shorter than the auto-close grace, so the exception can surface to a human before auto-close would act. |
| `MESFLOW_ALLOW_LEGACY_KIOSK_AUTOBIND` | `0` | Unrelated to shift auto-close directly, but same rollout discipline (Phase 10) — OFF by default in every real environment; only ever `1` in `compose.test.yml`'s test-server environment. |

A command-line `--dry-run`/`--live` flag on `reconcile-shift-sessions`
always overrides the environment defaults above, so you can force a
one-off dry run (or a one-off live run) from a terminal without touching
`.env`.

## Rollout sequence (every environment, every time this is turned on)

1. **Migrate.** `alembic upgrade head` (or however this environment already
   applies migrations). Confirms schema only — no session is touched.

2. **Audit first — before touching any flag.**
   ```
   docker compose exec mesflow python -m mesflow.cli audit-sessions --json > pre-rollout-audit.json
   docker compose exec mesflow python -m mesflow.cli audit-sessions
   ```
   Read the `OPEN`, `PAST_SHIFT_END`, and `OPEN_OVER_12H` counts. This is
   your baseline: how much real stale data exists *right now*, before any
   code in this Fix Plan has acted on it. Keep `pre-rollout-audit.json`.

3. **Install the cron jobs** (`scripts/install-reconcile-cron.sh`,
   `scripts/install-log-retention-cron.sh` if not already installed). At
   this point `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED` is still `0` — the cron
   fires, `reconcile-shift-sessions` runs, `scheduled_job_health` starts
   reporting real `last_started_at`/`last_success_at` (see
   `SESSION_LIFECYCLE`/`JOBS` components on `/api/system-health`, Phase 13),
   but nothing closes yet.

4. **Dry run.** Set `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1`,
   `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=1`. Let at least one full cron cycle
   run (default schedule is every minute). Inspect
   `runtime/shift-reconcile.log` — every candidate session is logged with
   the action it *would* take (`WOULD_CLOSE`), including the exact shift
   boundary it resolved. Cross-check a handful of these by hand against
   `working_calendar`'s shift config for that session's employee/date.

5. **Verify a sample.** Pick 3–5 `WOULD_CLOSE` candidates from the dry-run
   log. For each: confirm independently (from `work_sessions`,
   `working_calendar`/`work_shifts`, and the employee's actual clock-out
   behavior if known) that the resolved shift boundary is correct and that
   auto-closing it would **not** fabricate any quantity — the dry-run log
   shows `good_qty`/`defect_qty`/`rework_qty` it would carry forward
   unchanged from whatever the session already had (Phase 2's own hard
   rule: auto-close never invents quantity).

6. **Enable.** Set `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=0`. Leave `ENABLED=1`.
   From here, real auto-closes happen, each one:
   - dedicated lifecycle (`auto_close_for_shift_end`, never a disguised
     `finish(good_qty=0)` — Phase 2's core constraint),
   - tagged `close_reason='AUTO_SHIFT_END'`, `closed_by_system=TRUE`,
     `shift_boundary_used_at` set (queryable, reversible-in-spirit —
     nothing is guessed or deleted),
   - audited (`SESSION_AUTO_CLOSED` audit row + domain event),
   - idempotent under concurrent/restarted reconciliation runs (advisory
     lock keyed per session — see `0040`'s migration docstring).

7. **Re-audit after 24h.** Run `audit-sessions` again, compare against the
   Step 2 baseline. `PAST_SHIFT_END`/`OPEN_OVER_12H` counts should trend
   down (new stale sessions get closed within the grace window instead of
   accumulating); `OPEN` should reflect only sessions genuinely still
   in-progress. Check `/api/system-health`'s `SESSION_LIFECYCLE` component
   (`auto_closed_sessions_last_24h`) matches what the reconcile log shows.

8. **Roll back safely if something looks wrong.** Setting
   `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=0` (or `_DRY_RUN=1`) at any time stops
   further auto-closes immediately — already-closed sessions are not
   reopened (Phase 2's "không mất dữ liệu cũ" — nothing is undone
   automatically, by design; a wrongly-closed session is a manual data-fix
   decision, not something rollout tooling should reverse on its own).

## What to watch afterward

- `/api/system-health` → `SESSION_LIFECYCLE` component: `open_sessions`,
  `past_shift_end_sessions`, `auto_closed_sessions_last_24h`,
  `oldest_open_session_age_hours`, `exception_reconcile_last_success`,
  `shift_reconcile_last_success` (Phase 13).
- `/api/system-health` → `JOBS` component: both `exception_reconciliation`
  and `shift_session_reconciliation` should read `HEALTHY`, never
  `NEVER_RUN`/`MISSED`/`FAILED` for more than one missed cycle.
- Exception Center: `SESSION_PAST_SHIFT_END` exceptions should
  auto-resolve (`resolution_source=SYSTEM`, reason mentioning
  `AUTO_SHIFT_CLOSE`) shortly after the corresponding session auto-closes,
  with no human interaction required (Phase 5).
- `mesflow audit-sessions` — run periodically (weekly is reasonable) as a
  standing data-integrity check, independent of any specific rollout.
