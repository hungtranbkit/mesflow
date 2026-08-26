# MESFlow Release Rollback — Tested Procedure

Status: every claim in this document was verified live on 2026-08-26
(Reliability Validation Round 2, Gate 12) using the actual local deployment
tooling's mechanism (`docker pull`/`alembic upgrade|downgrade`/container
swap, the same primitives `scripts/deploy.sh`/`scripts/deploy-rollback.sh`
use), against a disposable Postgres with a representative dataset. It does
not describe untested theory.

## The question this answers

**Can the previous release's application image run against the current
release's schema, unmodified?**

**No.** Tested concretely with release 71.0.0.67 (migration head
`0039_kiosk_v2_protocol`) → 71.0.0.68 (migration head
`0041_job_health_last_success`, two purely-additive migrations: new
nullable/defaulted columns on `work_sessions`, one new index, one new
`scheduled_job_health` seed row, a new `last_success_at` column).

Starting the 71.0.0.67 app image against a database already migrated to
`0041_job_health_last_success` produces an immediate, hard failure at
container boot:

```
[DB] PostgreSQL ready
FAILED: Can't locate revision identified by '0041_job_health_last_success'
```

`mesflow-entrypoint` runs `alembic upgrade head` unconditionally on every
boot (see `scripts/docker-entrypoint.sh`); the older image's own
`app/migrations/versions/` directory has no knowledge of revisions added
after it was built, so Alembic refuses to proceed and the container never
reaches `verify-schema`/`seed-admin`/serving. This is the safe failure
mode — a fast, unambiguous crash-loop, not a silent partial start or data
corruption — but it means **an app-only rollback does not restore
service** once the schema has moved forward, even by a purely additive
migration.

This was true even though both 0040 and 0041 are additive-only migrations
with real, working `downgrade()` implementations — "additive migration"
does **not** imply "old app tolerates the new schema." Assume
incompatible by default; the only way to know otherwise is to test it the
same way this document did, for the specific version pair in question.

## The tested, working rollback sequence

Rolling back **always** requires downgrading the schema first, using an
image that still has the target revision in its migration history (in
practice: the *current*, about-to-be-replaced image — its
`app/migrations/versions/` still contains every older revision file).

```
# 1. Determine the target migration revision for the release you are
#    rolling back TO (check that release's own migration head, e.g. via
#    its VERSION.txt / `alembic current` at that commit, or the
#    deploy-history.jsonl entry recorded when it was deployed).

# 2. Downgrade the schema using the CURRENT (still-running) image's
#    alembic environment -- do this BEFORE swapping the app container:
docker run --rm --network <net> \
  -e DATABASE_URL="$DATABASE_URL" -e MESFLOW_ENV=production \
  --entrypoint sh <current-image> \
  -c "cd /app && alembic downgrade <target-revision>"

# 3. Swap the running app container back to the previous image
#    (this is exactly what scripts/deploy-rollback.sh already does):
sed -i "s#^MESFLOW_IMAGE=.*#MESFLOW_IMAGE=<previous-image>#" .env
docker compose --env-file .env up -d --no-deps <app-service>

# 4. Health-check as usual (docker inspect --format='{{.State.Health.Status}}',
#    curl /api/system/ready).
```

Verified end to end: after downgrading to `0039_kiosk_v2_protocol` and
starting 71.0.0.67 against it, the app booted cleanly
(`/api/system/ready` → `"status":"ready"`), logged in, read back
pre-existing employee/PO/session data unchanged, and correctly performed a
real write (`POST /work-sessions/<id>/finish`) — full read/write
functionality confirmed, not just a health-check pass.

Business data survives the round trip. Concretely checked: an employee
row, a production order, and an OPEN work session (with non-zero
`good_qty`/`defect_qty`) all round-tripped through upgrade-then-downgrade
with identical values, and the additive columns
(`close_reason`/`closed_by_system`/`shift_boundary_used_at`/
`started_at_trusted`/`ended_at_trusted`/`last_success_at`) were cleanly
dropped by `downgrade()` with no error.

## FIXED (2026-08-26): automatic rollback is now migration-aware

The gap this drill originally found — `scripts/deploy.sh`'s automatic
rollback-on-failed-health-check swapped the app image back but never ran a
schema downgrade, so it would fail to actually restore service whenever
the failed deploy had advanced the schema — has been fixed in
`scripts/deploy.sh`. The automatic rollback now:

1. Captures the **live** migration head of the currently-running app
   (`/api/system/ready`'s `migration_head`, read straight from
   `alembic_version` at request time — never string-parsed from a
   manifest) *before* this deploy's own migration step runs.
2. After migrating and swapping to the new image, if health fails,
   computes `migration_changed` by comparing that captured "before" head
   against the new image's "after" head. This is the one predicate the
   whole branch hangs on — it is never assumed either way.
3. **If unchanged:** takes the fast, safe image-only rollback path (as
   before) — the schema is already compatible with the old image.
4. **If changed:** runs `alembic downgrade <before-head>` using the
   NEW image (which still has every old revision in its own migration
   history — no hardcoded revision pair anywhere in the generic deploy
   logic), *verifies* the downgrade landed exactly on the expected
   revision (never trusts alembic's exit code alone), and only then swaps
   the image back and re-checks health.
5. **If the downgrade itself fails or can't be verified:** the image is
   **never** swapped back. The deploy is recorded as
   `ROLLBACK_REQUIRES_HUMAN` in `deploy-history.jsonl`, the exact manual
   recovery command is printed, and the script exits non-zero. The
   new (already-migrated) app/schema combination is left in place — the
   one combination whose actual state is known — rather than guessing
   further or risking a worse crash-loop.
6. **If the image swap itself then fails to become healthy** (a problem
   in the old image unrelated to schema): recorded as
   `IMAGE_ROLLBACK_FAILED`, still exits non-zero. A rollback is **never**
   reported as passing while the app is not actually healthy.

Release manifests (`release/mesflow-<version>.json`, written by
`scripts/release-build.sh`) now also carry `app_version`,
`migration_revision`, `previous_version`, and `previous_migration_revision`
explicitly, validated at packaging time — a documentation/audit trail of
what each release supersedes, alongside (not instead of) the live
migration-head comparison `deploy.sh` actually keys its safety decision
on.

Regression coverage: `tests/integration/test_deploy_rollback_migration_aware.py`
(marked `slow` — builds two real Docker images from git history against a
disposable tmpfs Postgres; run explicitly with
`pytest -m slow tests/integration/test_deploy_rollback_migration_aware.py`).
It exercises the same sequence of primitives `deploy.sh`'s rollback block
performs (SSH orchestration itself is not invoked, per this task's
constraint against deploying to TEST/PRODUCTION) for: no-migration-change,
migration-changed end-to-end (downgrade → old image → healthy → old app
performs a real write), downgrade-failure (`ROLLBACK_REQUIRES_HUMAN`, no
image swap), and image-rollback-failure (reported, never masked as a
pass).

`scripts/deploy-rollback.sh` (the manual rollback path) is unchanged — it
still requires an explicit human confirmation ("This does NOT revert the
DB schema. Confirm previous image is DB-compatible with the current
schema."), which remains the right behavior for an operator-initiated
rollback disconnected from any specific just-failed deploy; this document
is what that confirmation should be checked against.

## What was NOT tested (scope of this drill)

- Only one version hop was tested (71.0.0.67 → 71.0.0.68, two migrations).
  A rollback spanning many releases/migrations was not exercised end to
  end; downgrade to a specific non-adjacent revision should work the same
  way (`alembic downgrade` accepts any target revision, not just one
  step), but was not empirically run here.
- Rollback under live production traffic/concurrent writes during the
  container swap was not tested — this drill stopped the app before
  downgrading, matching `deploy-rollback.sh`'s own sequence (image swap
  only, no traffic draining), not a zero-downtime cutover.
- The remote SSH-based path in `scripts/deploy.sh`/`deploy-rollback.sh`
  itself was not exercised (this drill used the same underlying
  `docker run --entrypoint sh ... alembic ...` / container-swap primitives
  directly, against a disposable local Postgres, per this task's
  constraint against deploying to TEST/PRODUCTION).
