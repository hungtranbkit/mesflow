# Stable kiosk display numbers implementation plan

> Execution: native implementation in the assigned worktree, followed by independent source review. The user approved this contract and implementation; release build and production changes remain coordinated separately.

**Goal:** Show the same short decimal machine number on MESFlow and supporting ESP firmware without changing UUIDs, credentials, names or station mappings.

**Architecture:** PostgreSQL owns an optional `display_number` integer on each hardware identity. An integer sequence allocates once under the identity row lock. Existing bind and heartbeat responses carry it; Classic UI formats it with a minimum of two decimal digits.

**Tech stack:** PostgreSQL / Alembic, Python / Flask / psycopg, Classic JavaScript, pytest and Playwright.

## Approved contract and constraints

- `display_number` is a JSON integer from 1 through 2147483647, or null. Format 1 as 01, 2 as 02, and 100 as 100; never wrap or derive from a list position, name, UUID substring or modulo.
- Non-WEB identities are hardware/legacy kiosk identities. Case-insensitive `WEB-` identities stay null and consume no display numbers.
- Migration `0057_kiosk_display_number` adds a nullable INTEGER column, unique constraint, range check and `kiosk_display_number_seq` (INTEGER, NO CYCLE). No column default calls nextval.
- Backfill existing hardware once in `(created_at, id)` order, preserving every pre-existing field. New unapproved contacts stay unnumbered; approval, ACTIVE registration/rebind/status and authenticated heartbeat may allocate a missing number.
- Allocate inside the current transaction with an identity row lock. Repeated contact/approval/bind/heartbeat and rename keep the same number and do not advance the sequence again. Ignore device-supplied numbers.
- DISABLED retains its number. The application has no hard-delete route; retaining a number after a database-level hard delete is out of scope. The sequence never cycles or deliberately reuses deleted numbers.
- Enrollment confirmation code remains separate. Full UUID remains available in technical details and is still the action key.
- Exact numeric search prefers the matching display number; if none exists, preserve normal name/station/IP/firmware search, including numeric station codes.
- Production-specific initial mapping is an explicitly reviewed atomic operation after migration and before new app activation. Never embed production UUIDs in application or migration source.
- Preserve shared checkout WIP. No release build/freeze or public mutation during this source task.

## Review focus

1. Concurrent requests for one identity allocate once; different identities receive unique numbers.
2. Unapproved/unauthorized requests and WEB demos cannot consume or override human numbers.
3. Migration preserves identity, token, status, station and metadata while handling empty and historical inventories.
4. Nullable/invalid values and values over 99 render honestly without hex fallbacks or UUID search noise.
5. Old frozen .392 remains ready on the additive schema when started through the existing direct-Waitress override; its stock entrypoint cannot resolve a future revision.

## Task 1 — Persist and expose the number

Files: new `app/migrations/versions/0057_kiosk_display_number.py`; modify `app/mesflow/db/repositories/execution.py` and `app/mesflow/web/execution.py`; add `tests/integration/test_kiosk_display_numbers_pg.py`.

- [x] Add behavioral PostgreSQL/API tests. Observe the pending-registration field assertion fail on the unchanged .392 source.
- [x] Add migration and row-locked allocator; expose `display_number` in overview, approval/enrollment, bind and both hardware heartbeat variants. Return the post-allocation heartbeat value.
- [x] Verify pending and WEB exclusion, supplied-number rejection, idempotence, independent concurrent connections, status/rename stability, deletion non-reuse, constraints and real migration/backfill/downgrade in an isolated test schema.
- [x] Run new tests plus existing names/enrollment coverage with the declared PostgreSQL/API services, isolated project, read-only source mounts and no production data.

## Task 2 — Human display and search

Files: `app/mesflow/web/static/app.js`; existing kiosk names Playwright spec; `tests/e2e/persistent-login.spec.js`.

- [x] Update the real-page browser fixture to supply display numbers and expect 01/02/100, stable identity through rename/order changes, exact numeric search, numeric station fallback, and unnumbered WEB/pending states. Observe a numeric-label assertion fail before implementation.
- [x] Replace UUID suffix labels with validated decimal formatting in cards, dialogs and timeline. Put full UUID in explicit technical details.
- [x] Correct the proven persistent-login fixture bug: alter a significant signature character, assert decoded bytes differ, preserve the cookie payload/timestamp, and require the existing redirect behavior. No authentication logic changes.
- [x] Run focused browser cases at 1920/1366/768/390px plus all five persistent-login cases; inspect render/console/overflow evidence.

## Task 3 — Qualification and handoff

- [ ] Run declared preflight, syntax/diff checks and Alembic head verification.
- [ ] Run the frozen .392 image against the new isolated schema using direct Waitress. Verify readiness and existing authenticated read/rename behavior while numbers and identities remain stable. Record the old legacy health provider's exact-head warning, if observed.
- [ ] Update PROJECT_CONTEXT, commit/push the owned branch and open a reviewable draft PR targeting `integration/pr43-test-preserve-reports`.
- [ ] After source review, prepare version .393 using canonical version tooling, obtain coordinator build authorization and follow the immutable build/promotion contract. These release actions are not part of the current implementation authorization.

## Progress ledger

- 2026-11-27: fresh fetch and own clean worktree from 363cce2d (same tree as frozen .392). No competing 0057 on remote agent/integration refs; .393 artifact absent. Canonical UI WIP preserved. Current production has 8 hardware and 19 WEB identities, all ACTIVE (coordinator evidence).
- Ruling: historical backfill covers all existing non-WEB rows, including any PENDING/DISABLED historical inventory; only newly arriving unapproved contacts remain unnumbered. This follows the approved one-time inventory backfill while preventing ongoing unauthenticated number consumption.

- Verified: unchanged .392 baseline 24 passed; new API/label tests failed for the expected missing field/hex label. After implementation, 38 PostgreSQL/API/migration tests passed in 6.55s, and 11 browser cases passed in 14.3s without retries. Migration fixture cleanup was corrected after its own isolated DROP SCHEMA failure; product assertions already passed. Normal startup upgrade and Alembic heads report 0057. Frozen .392 runtime rollback and operational seed qualification remain pending.
