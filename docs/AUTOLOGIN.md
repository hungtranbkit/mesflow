# Auto-login for fast internal testing

A server-side, dev/demo/test-only session bootstrap so a tester or a
Playwright spec can skip typing username/password to check a feature or
an RBAC permission quickly. Off by default everywhere. This document
covers the mechanism as it stands after the 2026-09-04 AUTOLOGIN task,
which extended an existing, already-tested feature rather than building
a new one — see "Why this reuses an existing mechanism" below before
assuming a `MESFLOW_AUTOLOGIN_*` name exists; it doesn't.

## Enable/disable

| Env var | Default | Meaning |
|---|---|---|
| `MESFLOW_TEST_AUTO_LOGIN` | `0` (off) | Master switch. `1`/`true` turns it on. |
| `MESFLOW_TEST_AUTO_LOGIN_USERNAME` | `admin` | Which account the *default* (persona-less) auto-login uses. |
| `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION` | `0` (off) | Required *in addition* to the flag above whenever `MESFLOW_ENV=production` — see "Production guard" below. Real production should never set this. |

Setting `MESFLOW_TEST_AUTO_LOGIN=1` alone is enough on any tier where
`MESFLOW_ENV` is **not** `production` (local DEV sandbox, the
`compose.test.yml` isolated stack, `compose.sandbox.yml`) — nothing else
to configure.

## Production guard

`compose.yml` — the compose file `prodtest` and the demo container's
deployment both derive from — hardcodes `MESFLOW_ENV: production` on
every tier that uses it, prodtest and demo included (see
`docs/DEPLOY_ARCHITECTURE_A.md`). That means the plain "environment !=
production" check alone would never let auto-login run on prodtest or
demo either, and conversely a bare `MESFLOW_TEST_AUTO_LOGIN=1` can never
be a mistake serious enough to expose real production, because the
`MESFLOW_ENV` check alone already refuses it there.

To actually allow it on prodtest/demo, both flags are required:

```
MESFLOW_TEST_AUTO_LOGIN=1
MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1
```

This mirrors `tutorial_data.py`'s existing `MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION`
pattern exactly: a feature-scoped, default-off second opt-in, required
only when `MESFLOW_ENV=production`. It is **never** inferred from
`SERVER_ROLE` — `core/config.py`'s own docstring on `server_role`
explains why security-gated behavior must never key off that field (a
human/operator-facing label with no validation, distinct from
`MESFLOW_ENV`).

If `MESFLOW_TEST_AUTO_LOGIN=1` is set on a `MESFLOW_ENV=production`
deployment **without** the override:
- `POST /api/auth/test-auto-login` returns `403 AUTO_LOGIN_DISABLED_PRODUCTION` and logs a warning on every attempt.
- At process startup, `create_app()` also logs a boot-time warning either way (which combination is present), so this is visible in server logs immediately, not just on a request that happens to hit it.
- `scripts/production-preflight.sh` (the real-production release gate) fails the release if `MESFLOW_TEST_AUTO_LOGIN` **or** `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION` is anything but `0`/`false` — defense-in-depth independent of the app-level guard.

## Personas (RBAC quick-switch)

`POST /api/auth/test-auto-login` accepts an optional `persona`, either as
JSON body (`{"persona":"operator"}`, what `login.js` sends) or a query
param (`?persona=operator`, handy for `curl`/manual testing). Allowed
values are exactly the 5 real non-`super_admin` roles:

```
admin | manager | supervisor | operator | viewer
```

Anything else returns `400 AUTO_LOGIN_INVALID_PERSONA`. A persona
resolves to the user account with that exact username — every real
MESFlow deployment already seeds one account per role named after the
role itself (`admin`, `manager`, `supervisor`, `operator`, `viewer`;
checked directly against local DEV and demo's databases). No new
per-persona env vars, no separate table — reuses that existing
convention. Omitting `persona` falls back to the single configured
`MESFLOW_TEST_AUTO_LOGIN_USERNAME` exactly as before this task (pure
regression for the dozens of e2e specs already calling this endpoint).

Persona switching is gated by the exact same guard as the base flag —
non-production, or production with the explicit override. There is no
separate flag for it.

### Quick manual RBAC check

```
open http://127.0.0.1:8080/login?persona=operator
```

If auto-login is on, this logs straight in as the `operator` account.

## Avoiding the logout → autologin loop

If auto-login is on, visiting `/login` for any reason — including right
after a deliberate logout — would otherwise instantly re-authenticate,
making the logged-out state or a manual/different-persona login
impossible to actually reach.

- The logout button (`app.js`) now redirects to `/login?noauto=1` instead of plain `/login`.
- `/login?noauto=1` renders the real form and does **not** auto-trigger, regardless of the flag — an explicit, visible override, usable any time a tester wants the manual form while auto-login is on.

## Playwright / e2e integration

This already existed before this task and is unchanged: dozens of specs
under `tests/e2e/` call `page.request.post('/api/auth/test-auto-login')`
instead of filling the login form, e.g.:

```js
await page.request.post('/api/auth/test-auto-login');
await page.goto('/app');
```

`compose.test.yml` sets `MESFLOW_TEST_AUTO_LOGIN: "1"` for exactly this.
A real-login test group is deliberately kept separate and untouched:
`tests/e2e/tutorial-video.spec.js` uses `/api/auth/login` with a real
password (`test_tutorial_uses_password_login` in
`tests/test_v6584431_production_hardening.py` asserts this stays true) —
so real credential-based login coverage is never fully replaced by
auto-login across the suite.

## Security notes (why this is not a backdoor)

- **No secret in the frontend.** `login.js` never sends or stores a
  password/token for auto-login; it POSTs to a server route that looks
  the account up itself and calls the exact same
  `session_policy.start_session()` a real password login uses.
- **No new public route.** `/api/auth/test-auto-login` already existed.
- **No global backend bypass.** This codebase already tried and removed
  a broader "auto-login" style request bypass once before (see
  `tests/test_internal_qa_login_contract.py`'s
  `test_internal_qa_uses_real_password_auth_not_a_silent_bypass` —
  `MESFLOW_INTERNAL_QA_AUTO_LOGIN` is kept only as a vestigial
  preflight-guard name, wired to nothing). This task does not reintroduce
  that shape: one explicit route, one explicit session bootstrap, a fixed
  persona allowlist, fail-closed on production.
- **Fail-closed, not fail-open.** Every new check defaults to refusing;
  the override that would allow it in a `MESFLOW_ENV=production`
  deployment must be set explicitly and is itself checked by the
  production-preflight gate.

## Why this reuses an existing mechanism

The original ask named `MESFLOW_AUTOLOGIN_ENABLED` as an example. A
mechanism already existed under `MESFLOW_TEST_AUTO_LOGIN` — a real,
already-tested, already-e2e-integrated server-side session bootstrap
covering most of the requirements out of the box. Introducing a second,
differently-named flag that does the same thing would have meant every
place that currently enumerates "the auto-login flags that must be 0 in
production" (`scripts/production-preflight.sh`,
`tests/test_v6584431_production_hardening.py`) needed updating too, or
silently gains a gap. Extending the existing flag was the simpler, safer
option (per this task's own instruction to prefer that when found) —
functionally, `MESFLOW_TEST_AUTO_LOGIN=1` *is* "autologin enabled."

## Example: local DEV sandbox

```
MESFLOW_ENV=local                          # already true for the local sandbox
MESFLOW_TEST_AUTO_LOGIN=1
MESFLOW_TEST_AUTO_LOGIN_USERNAME=admin      # default persona
```

## Example: demo/prodtest (MESFLOW_ENV=production)

```
MESFLOW_ENV=production                      # already hardcoded by compose.yml
MESFLOW_TEST_AUTO_LOGIN=1
MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1   # required in addition, on this tier only
MESFLOW_TEST_AUTO_LOGIN_USERNAME=admin
```

Real production must never set `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION`.
