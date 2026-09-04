# MESFlow — QA Master Requirements

**Purpose**: single source of truth for QC/QA test-case generation across the whole MESFlow system. Every requirement below is sourced from the code, migrations, tests, or directly-verified runtime behavior as of `71.0.0.221` (commit `c27fe91`) — not from assumption. Where an older doc (`PRODUCT.md`, a `reports/*.md` audit) conflicts with what the code/runtime actually does today, that conflict is called out explicitly and the verified behavior wins; see [§13 Known Gaps](#13-known-gaps--open-questions) and inline "⚠ doc conflict" notes.

**How to use this document**: each functional requirement has a stable ID (`REQ-<MODULE>-###`). Business rules are `BR-###`. Use §12's test-case format to turn any requirement into concrete test cases; use §11's traceability matrix to see what's already automated versus what still needs a human tester.

**Evidence method**: routes and their permission decorators were enumerated directly from `app/mesflow/web/*.py`; RBAC data from `app/mesflow/db/repositories/rbac.py` (the single canonical seed, itself reconstructed from a live-verified backup — see its own header comment); state machines from the repository methods that actually compute them (`app/mesflow/db/repositories/production_state.py`, `execution.py`) plus their migrations; business rules cross-checked against the integration test file that already exercises them where one exists.

---

## Table of contents

1. [Scope & terminology](#1-scope--terminology)
2. [Roles & RBAC matrix](#2-roles--rbac-matrix)
3. [Functional requirements by module](#3-functional-requirements-by-module)
4. [Business rules](#4-business-rules)
5. [Status / state machines](#5-status--state-machines)
6. [Validation requirements](#6-validation-requirements)
7. [UI/UX acceptance requirements](#7-uiux-acceptance-requirements)
8. [Non-functional requirements](#8-non-functional-requirements)
9. [Environment & test-data contract](#9-environment--test-data-contract)
10. [End-to-end user journeys](#10-end-to-end-user-journeys)
11. [Traceability matrix](#11-traceability-matrix)
12. [QC test-case generation guidance](#12-qc-test-case-generation-guidance)
13. [Known gaps / open questions](#13-known-gaps--open-questions)

---

## 1. Scope & terminology

### 1.1 What MESFlow is

MESFlow is a production-execution and monitoring system for a mechanical workshop (per `PRODUCT.md`: *"hệ thống điều hành sản xuất dành cho xưởng cơ khí"*). It tracks work from a released Production Order down to individual worker sessions on the shop floor, surfaces exceptions and work-in-progress bottlenecks, and reports employee productivity. It is a server-rendered Flask/Jinja + vanilla JS web app over PostgreSQL, deployed via Docker/Nginx (`PRODUCT.md` §Capabilities).

### 1.2 Actors

| Actor | Primary surface | Notes |
|---|---|---|
| Chủ xưởng / giám đốc (owner/director) | Admin web app — Overview, Dashboard | Read-heavy; wants fast status |
| Quản đốc (supervisor) | Admin web app — Session Management, Exception Center, Production Schedule | Runs the floor day-to-day |
| Quản lý (manager) | Admin web app — most of the above, plus PO/Template/Employee edit | Configures business data |
| Quản trị viên (admin) | Admin web app — everything, incl. Users & Roles | Full system control |
| Super Admin / IT | System Console (`/api/system-health/*`) | Technical health/ops only — **not** a superset of admin's business permissions in the other direction; see §2.3 |
| Vận hành (operator) | Kiosk (web `kiosk.html` or ESP32 firmware "kiosk v2") | Scans employee + operation QR, starts/finishes sessions |
| Chỉ xem (viewer) | Admin web app, read-only | See RBAC matrix for exact scope |
| Kiosk device (no human role) | ESP32 firmware or `kiosk.html` | Authenticates via device token/allowlist, not a `users` row — see §3.8 |

There is **no dedicated "QA Inspector" / "Maintenance" / "Kiosk User" role** in the RBAC table — `PRODUCT.md`'s own text ("admin, manager và supervisor") is itself stale; the seed data (`rbac.py`) defines exactly 6: `super_admin, admin, manager, supervisor, operator, viewer`. Some deployments have usernames like `maintenance`, `kiosk01`, `qa` seeded, but their **role** is always one of the 6 (typically `operator` or `viewer`) — a persona name is not a role.

### 1.3 Data hierarchy

```
Sales Order (optional)
  └─ Production Order (PO)          status: DRAFT→PLANNED→RELEASED→IN_PROGRESS→(PAUSED)→COMPLETED / CANCELLED
       └─ Part                       (belongs to one PO; can carry a drawing file)
            └─ Operation             status: computed from session facts — see §5.2
                 └─ Work Session      status: OPEN → CLOSED (or CLOSED via auto-close)
                      ├─ QC Inspection (optional, per session)
                      ├─ Operation Adjustment (audit trail of quantity corrections)
                      └─ Quantity Movement (GOOD / DEFECT / REPAIRABLE ledger rows)

Template (Process template)  →  instantiated into a new PO's Parts+Operations (a PO is never hand-built directly)

Employee  (independent entity, referenced by Work Session)
Station / Kiosk device  (independent entity, referenced by Work Session)
Exception  — TWO separate systems, do not conflate:
  - session_exception_reviews  (older, per-session workflow: NEW/IN_PROGRESS/RESOLVED/IGNORED)
  - exception_records          (V67 "Exception Center": OPEN/ACKNOWLEDGED/RESOLVED/AUTO_IGNORED/MANUAL_IGNORED, severity CRITICAL..LOW)
```

A PO is **always** created by instantiating a Template (`ProductionOrderRepository.create()` literally raises `ValueError` — *"Production Order phải được tạo từ Template để sao chép Part và Operation"*). There is no direct "create blank PO" path anywhere in the API.

### 1.4 Glossary

| Term | Meaning |
|---|---|
| **PO** | Production Order — one manufacturing run of a `product`, for `planned_quantity` units. |
| **Part** | A sub-assembly/component under one PO; carries an optional drawing file. |
| **Operation** | One process step under a Part (e.g. cutting, welding); the unit workers actually scan/work against. |
| **Work Session** | One employee's timed work block on one Operation. The atomic unit of production data. |
| **good_qty / defect_qty / rework_qty** | Session-level counters: units passed, units failed, and (of the failed) units that are repairable. `rework_qty` can never exceed `defect_qty` (enforced server-side, see BR-014). |
| **Quantity Confirmed** | Whether a human has confirmed a session's final good/defect numbers. `TRUE` for any normal manual finish or correction; `FALSE` only immediately after an auto-close, until a supervisor/admin corrects it (BR-009). |
| **Excluded from reports** | A session can be marked "loại khỏi báo cáo" — it is never deleted, but stops counting toward KPI/progress/time aggregates until restored (BR-010). |
| **Reportable session** | The shared predicate (`reportable_session_sql()`) every KPI/report/exception query applies: `status='CLOSED' AND NOT excluded_from_reports`. If a report's numbers look "off," check this predicate first. |
| **Input flow / material flow** | An Operation can be configured to consume GOOD or REWORK output from an upstream "source" Operation as its own raw-material ceiling — see BR-011. |
| **Auto-close** | The scheduled job that force-closes a Work Session still `OPEN` after its shift's end + grace period, via a dedicated code path distinct from a manual finish (BR-008/BR-009). |
| **Kiosk v1** | The browser-based kiosk (`kiosk.html` + `/api/kiosk-web/*`), token/session-light, used for demo/manual browser testing. |
| **Kiosk v2** | The real ESP32 firmware protocol (`/api/kiosk/v2/*`), device-authenticated, event-sourced projection state machine — the one real hardware talks to. |
| **Exception Center (V67)** | `exception_records` — durable, deduplicated-by-fingerprint incident records with a real lifecycle and severity, replacing ad-hoc detection. |
| **Session Exceptions (legacy)** | `session_exception_reviews` — an older, session-scoped review workflow still live in Session Management. |
| **Persona (autologin only)** | A **test-only** concept: `?persona=operator` etc. quick-switches which seeded account `test-auto-login` logs in as. Not a production concept — see §2.4. |

---

## 2. Roles & RBAC matrix

### 2.1 The 6 real roles

Source: `app/mesflow/db/repositories/rbac.py` `SEED_ROLES` (frozen from a live-verified backup, 2026-09-02 — see that file's own header for the forensic incident this guards against: `rbac_role_permissions` was once found completely empty in local DEV, silently giving every user `permissions:[]`).

| code | Vietnamese name | sort_order |
|---|---|---|
| `super_admin` | Super Admin / IT | 5 |
| `admin` | Quản trị viên | 10 |
| `manager` | Quản lý | 20 |
| `supervisor` | Quản đốc | 30 |
| `operator` | Vận hành | 40 |
| `viewer` | Chỉ xem | 50 |

### 2.2 Permission catalog and grant matrix

Full catalog: 40 permission codes across 20 modules (`overview`, `dashboard`, `production-orders`, `templates`, `session-management`, `session-exceptions`, `production-schedule`, `kiosk-management`, `esp-ota`, `system-logs`, `employees`, `qr-print`, `equipment`, `users`, `working-calendar`, `business-audit`, `operations-center`). Full code list is in `rbac.py`'s `SEED_PERMISSIONS`; the grant-per-role table (`SEED_ROLE_PERMISSIONS`, 102 rows) is the actual authoritative source — **read that file directly for the exact current grant set**, do not hand-copy it into a second location that can drift. Summary by role:

| Role | Permission count | Character |
|---|---|---|
| `admin` | 33 | Everything except `business_audit.view`/`operations.view`/`deploy.*`/`diagnostics.run` (those are Deploy-Agent-integration codes, largely unused by the current app; `system_logs.view` also absent for admin specifically) |
| `manager` | 36 | Broadest of the business roles — includes `business_audit.view`, `deploy.view`, `system_logs.view`, `operations.view` that `admin` itself lacks |
| `supervisor` | 17 | Floor operations: sessions, exceptions, kiosk, material flow, calendar (view), business audit (view) — no employees/users/templates edit |
| `operator` | 8 | `dashboard.view, employees.view, kiosk.view, material_flow.view, overview.view, po.view, qr.view, session.view` — **view-only**, no edit permission anywhere |
| `viewer` | 11 | Broadest read-only: adds `calendar.view, equipment.view, exceptions.view, template.view` on top of operator's set |
| `super_admin` | N/A (not a permission-table role) | Bypasses `_has_permission()` the same as `admin` (`role in ('admin','super_admin'): return True` in `web/auth.py`) for **ordinary business permissions**, but System Console routes (`super_admin_required`) check the literal role string and are **never** satisfied by `admin` |

**BR-001 (RBAC)**: `admin` always has every ordinary business permission — `RBACRepository.has_permission()` short-circuits `True` for `role=='admin'` regardless of what rows exist in `rbac_role_permissions`. Editing `admin`'s permission set via `PUT /api/roles/admin/permissions` is accepted but has no effect (`RBACRepository.set_role_permissions()` silently forces it back to "all permissions" for `role_code=='admin'`).

**BR-002 (RBAC)**: `super_admin` gets `admin`'s full business-permission bypass (App Web functionality) **plus** exclusive access to the System Console (`/api/system-health/errors|services|diagnostics|audit` and service-restart/diagnostics-run actions) — a strict superset in one direction (business) and a strict exclusive set in the other (System Console), not a simple "higher rank" hierarchy. An ordinary `admin` session hitting a `super_admin_required` route gets `403 FORBIDDEN`, never a silent pass.

### 2.3 Expected behavior on missing permission

| Layer | Missing-permission behavior |
|---|---|
| **API** (any `@permission_required`/`@roles_required`/`@admin_required`/`@super_admin_required` route) | `403 {"ok": false, "error": "FORBIDDEN", "permission": "<code>", "message": "Bạn không có quyền thực hiện thao tác này"}` — real, testable, never a silent 200 with filtered data |
| **No session at all** | `401 {"error": "AUTH_REQUIRED"}` on any `login_required`-gated route |
| **Expired session** | `401 {"error": "SESSION_EXPIRED", "reason": "<idle\|absolute>"}` |
| **UI (nav sidebar)** | Pages/tabs the current role's `permissions_for_role()` doesn't include are not rendered — a role without `po.view` never sees "Production Order" in the sidebar at all, not a disabled/greyed link. **QC implication**: absence of a nav item for a low-privilege persona is expected behavior, not a bug, unless the requirement below says otherwise. |
| **UI (in-page controls)** | Inconsistent by page — some hide edit controls entirely for a view-only role, some show them and let the resulting API 403 surface as a toast. Treat "does the button exist" as **not** a reliable signal on its own; the API-level 403 (above) is the one every page must get right. Flagged as SPEC-GAP-002 (§13) — a page-by-page UI-affordance audit was not in scope for this pass. |

### 2.4 Authentication, session, login/logout — and autologin's place in it

**This is the real, only-ever-used-in-production login path** (`POST /api/auth/login`, `app.py`): username + password against `users.password_hash` (`werkzeug.security.check_password_hash`), on success `session_policy.start_session(user_id, username, role)`. Every login attempt (success or failure) is logged to the audit trail (`AuditRepository().log(..., 'LOGIN_SUCCESS'/'LOGIN_FAILED', ...)`), **passwords are never logged**.

Session expiry (`core/session_policy.py`, `config.py`): idle window (`MESFLOW_SESSION_IDLE_MINUTES`, default 60) and an absolute ceiling (`MESFLOW_SESSION_ABSOLUTE_HOURS`, default 12) that fires regardless of activity; a separate, shorter idle window for kiosk-mode logins (`MESFLOW_KIOSK_SESSION_IDLE_MINUTES`, default 15).

**Autologin (`MESFLOW_TEST_AUTO_LOGIN`) is explicitly a test facility, not a business requirement of production.** Full spec: `docs/AUTOLOGIN.md`. Summary for QA purposes:
- Default **off** everywhere. Hard-refused whenever `MESFLOW_ENV=production` unless a second, separate opt-in (`MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1`) is also explicitly set — real production must never set the override; the app logs a security warning at boot and on every refused attempt either way.
- When on, `POST /api/auth/test-auto-login` bootstraps a session **the same way** a real login does (`session_policy.start_session`) for a server-configured account (`MESFLOW_TEST_AUTO_LOGIN_USERNAME`, default `admin`), or an explicit `persona` (`admin|manager|supervisor|operator|viewer` only — a fixed allowlist, never an arbitrary username, never `super_admin`) resolved to the like-named seeded account.
- `GET /login?noauto=1` always renders the real password form, regardless of the flag — this is how a deliberate logout avoids bouncing straight back in (`app.js`'s logout button already appends this).
- **QC must keep a real-password login test group** (`tests/e2e/tutorial-video.spec.js` already is one — asserted by `test_tutorial_uses_password_login`) — autologin existing must never be read as "the password login path no longer needs coverage."

---

## 3. Functional requirements by module

Each requirement: `REQ-<MODULE>-###`. "Evidence" cites the exact file(s). "Role" is the minimum role that can perform the action per §2 (view-only roles omitted where obvious).

### 3.1 Authentication / session (`REQ-AUTH-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-AUTH-001 | `POST /api/auth/login` with a correct active-user username+password creates a session and returns the user's `id/username/role/must_change_password/permissions`. | `app.py:login()` |
| REQ-AUTH-002 | Login with a wrong password, unknown username, or an **inactive** user returns `401 INVALID_CREDENTIALS` — the error is identical for all three (does not reveal whether the username exists). | `app.py:login()` |
| REQ-AUTH-003 | Every login attempt (success or failure) writes an audit-trail row (`LOGIN_SUCCESS`/`LOGIN_FAILED`); the failure reason distinguishes `invalid_credentials` vs `inactive` internally but the HTTP response does not. | `app.py:login()` comment "SECURITY_AUDIT (section 3)" |
| REQ-AUTH-004 | `POST /api/auth/logout` clears the session unconditionally (no auth required to call it — clearing an already-empty session is a no-op, not an error). | `app.py:logout()` |
| REQ-AUTH-005 | `GET /api/auth/me` returns `401 AUTH_REQUIRED` (no session) or `401 SESSION_EXPIRED` (idle/absolute timeout) or `200` with the current user's role+permissions. | `app.py:auth_me()` |
| REQ-AUTH-006 | A first-login user with `must_change_password=TRUE` is signaled in the login response; enforcing the actual change is a UI-level responsibility (`POST /api/auth/change-password`, `users.py`). | `users.py:change_own_password()` |
| REQ-AUTH-007 | Visiting `/login` while already authenticated redirects to `/app`, not the form. | `app.py:login_page()` |
| REQ-AUTH-008 | Visiting `/app` (or any page requiring a session) while unauthenticated redirects to `/login`. | `app.py:app_page()` |
| REQ-AUTH-009 | Autologin: see §2.4 in full — `REQ-AUTH-009a` default-off, `009b` production hard-refusal without explicit override, `009c` persona allowlist, `009d` `?noauto=1` override. | `docs/AUTOLOGIN.md`, `app.py` |

### 3.2 Dashboard / Overview (`REQ-DASH-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-DASH-001 | `GET /api/dashboard/overview` and `/api/dashboard/control-tower` require only `login_required` (any authenticated role can view — no role narrows dashboard visibility beyond `dashboard.view`/`overview.view` presence in §2's grant table). | `analytics.py` |
| REQ-DASH-002 | `GET /api/dashboard/summary`, `/production-orders`, `/active-sessions`, `/daily-progress`, `/daily-sessions`, `/shift`, `/recent-activity` are independent, separately-cacheable panels — a failure in one must not 500 the whole dashboard page (each is its own endpoint, called independently by the frontend). | `analytics.py` route list |
| REQ-DASH-003 | The Overview page ("Tổng quan sản xuất") shows PO/planned/done/defect/repairable roll-ups filterable by PO/Part/Operation/status, matching the KPI-card layout seen live (see the autologin screenshot evidence in the outer workspace repo's `reports/AUTOLOGIN_FEATURE_20260904.md` — "PO dang chay / Kế hoạch / Đạt / NG tổng / Phế / Còn lại / CHỜ SỬA"). | live-verified 2026-09-04 |
| REQ-DASH-004 | Filters (PO/status/sort) must be cascading and never silently show stale data from a superseded request (a later, faster response must not be overwritten by an earlier, slower one that resolves after it — see BR-016). | `tests/e2e/session-management-dependent-filters.spec.js` |

### 3.3 Production Order (PO) (`REQ-PO-*`)

| ID | Requirement | Role | Evidence |
|---|---|---|---|
| REQ-PO-001 | A PO can **only** be created by instantiating a Template (`POST /templates/<id>/instantiate`) — direct `POST /api/production-orders` is rejected with a Vietnamese `ValueError`. | manager | `master_data.py: ProductionOrderRepository.create()` |
| REQ-PO-002 | `POST /production-orders/<id>/start` transitions `PLANNED/DRAFT/RELEASED → IN_PROGRESS`, making every child Operation kiosk-workable. Requires ≥1 Operation to exist; refuses if already `COMPLETED`/`CANCELLED`; is idempotent if already `IN_PROGRESS` (`already_started:true`, not an error). | admin/manager/**supervisor** (deliberately widened — see `auth.py`'s Gate-18 carve-out comment) | `master_data.py:start_production_order()` |
| REQ-PO-003 | PATCH/PUT on a PO validates `status` against the fixed enum `{DRAFT,PLANNED,RELEASED,IN_PROGRESS,PAUSED,COMPLETED,CANCELLED}` and `priority` against `{LOW,NORMAL,HIGH,URGENT}` — any other value is a `400`-class `ValueError`. | manager | `master_data.py:ProductionOrderRepository._normalize()` |
| REQ-PO-004 | `planned_start_at`/`planned_end_at`, if both given, must have end strictly after start. | manager | same |
| REQ-PO-005 | `DELETE /production-orders/<id>` is refused with `ConflictError` if the PO has ANY production history (sessions, input-consumption ledger rows, output quantities, kiosk events, adjustments, or QC inspections) — deleting a PO with real history is never allowed via the normal delete path. | admin/manager | same, `delete()` |
| REQ-PO-006 | `DELETE /production-orders/<id>/force` bypasses the history check — **admin-only**, not manager (a real historical bug: manager could force-delete until Gate-18's fix). | **admin only** | `auth.py` Gate-18 comment, `master_data.py` |
| REQ-PO-007 | Trace: `GET /production-orders/<id>/trace` and `/quantity-history` give the full audit lineage for a PO. | login_required | `trace.py` |

### 3.4 Part + drawing (`REQ-PART-*`)

| ID | Requirement | Role | Evidence |
|---|---|---|---|
| REQ-PART-001 | A Part belongs to exactly one PO (`production_order_id` FK, not nullable in practice). | — | `master_data.py: PartRepository` |
| REQ-PART-002 | `DELETE` on a Part is refused (`ConflictError`) if ANY child Operation has production history (session/ledger/output/event/adjustment/QC) — same shape as the PO-delete guard, evaluated per-Operation and aggregated. | admin/manager | `PartRepository.delete()` |
| REQ-PART-003 | `POST /template-parts/upload-drawing` attaches a drawing file to a template Part (propagates into every PO instantiated from that template afterward). | admin/manager | `master_data.py` route list |

### 3.5 Template / routing (`REQ-TPL-*`)

| ID | Requirement | Role | Evidence |
|---|---|---|---|
| REQ-TPL-001 | `GET /templates/<id>/tree` returns the full Part→Operation structure; `PUT .../tree` replaces it. | view: login_required; edit: admin/manager | `master_data.py` |
| REQ-TPL-002 | `PUT .../tree` (Replace) is refused once the template's instantiated Operations have any Session or input-consumption Ledger — must use Merge, or create a new PO, instead. | admin/manager | `excel_io.py` line 264 comment |
| REQ-TPL-003 | `GET /templates/<id>/validate` checks structural integrity (e.g. dependency cycles — see BR-012) before allowing instantiate. | login_required | `master_data.py` |
| REQ-TPL-004 | `POST /templates/<id>/instantiate` copies the template's Parts+Operations into a brand-new PO. | admin/manager | same |
| REQ-TPL-005 | `POST /templates/demo/seed` and `DELETE /templates/demo` are **admin-only** (narrower than the generic `template.edit` a manager also holds) — demo-data seed/wipe is deliberately locked tighter than ordinary template editing. | **admin only** | `auth.py` Gate-18 comment |
| REQ-TPL-006 | Excel import/export: `GET /export.xlsx`, `POST /import`, per-template `export-workbook`/`import` (workbook) — round-trips the Operation sheet; `export-workbook` is readable by `viewer` too (widened, read-only, low-risk per Gate-18's audit). | admin/manager (viewer for export-workbook) | `excel_io.py` |

### 3.6 Employee management (`REQ-EMP-*`)

| ID | Requirement | Role | Evidence |
|---|---|---|---|
| REQ-EMP-001 | `employee_no` is normalized to uppercase on write; `employment_status` defaults to `"Đang làm"` and derives `active` (`active = employment_status != "Đã nghỉ"`) — **`active` is not independently settable**, it is a computed side-effect of the status text. | admin/manager | `master_data.py:EmployeeRepository._normalize()` |
| REQ-EMP-002 | Date fields (`birth_date, identity_issue_date, start_date, end_date`) accept empty string as "clear" (coerced to `NULL`, not rejected). | admin/manager | same |
| REQ-EMP-003 | `WorkSessionRepository.start()` refuses (`RepositoryError`) if the employee is missing or `active=FALSE` — an inactive employee cannot start a session, kiosk or otherwise. | system-enforced | `execution.py:start()` |
| REQ-EMP-004 | QR/label generation: `GET /qr-labels`, `/qr-image` — printable identity for kiosk scanning. | login_required | `master_data.py` |

### 3.7 Work Session lifecycle (`REQ-SESS-*`)

See §5.1 for the full state machine; this table is the requirement-ID index into it.

| ID | Requirement | Evidence |
|---|---|---|
| REQ-SESS-001 | An employee can have **at most one `OPEN` session at any time** — DB-enforced (`uq_open_session_per_employee` partial unique index), not just app-level. A second concurrent `start()` for the same employee raises `ConflictError('employee already has an open session')`. | `0003_execution.py`, `execution.py:start()` |
| REQ-SESS-002 | `start()` requires the target PO to be `IN_PROGRESS` (else `ConflictError` naming the PO code) and the Operation itself to be dispatch-ready (`ConflictError` with the specific `readiness_reason`+current WIP). | `execution.py:start()` |
| REQ-SESS-003 | If the Operation has input-flow enabled, its upstream **source** Operation must have at least one session ever started (not necessarily finished) before this Operation can start — a downstream worker cannot start before the upstream chain has begun. | same, lines 369–387 |
| REQ-SESS-004 | `finish()` requires `rework_qty ≤ defect_qty`; negative quantities are clamped to 0, not rejected as an error. | `execution.py:_finish_within()` |
| REQ-SESS-005 | `finish()` validates upstream input-consumption availability (BR-011) before allowing the close. | same |
| REQ-SESS-006 | Both `start()` and `finish()` reject a time window that overlaps another session for the **same employee** (`_find_employee_session_overlap`), including against a trusted offline-device timestamp. | same |
| REQ-SESS-007 | `finish_many()` (`/session/group/finish`) is a true all-or-nothing atomic batch across multiple sessions — one failure rolls back every item in the batch, never a partial commit. | `execution.py:finish_many()` docstring |
| REQ-SESS-008 | `SupervisorRepository.adjust()` (quantity correction) requires a non-empty `reason`; always flips `quantity_confirmed` back to `TRUE`; writes an immutable `operation_adjustments` audit row (old/new for good/defect/rework) plus a `VALUE_CHANGED` domain event. | admin/manager/supervisor | `execution.py:adjust()` |
| REQ-SESS-009 | `edit_session()` (full PATCH) supports optimistic-concurrency via `expected_updated_at` — a stale edit is refused, not silently overwritten (see BR-013). | admin/manager/supervisor | `execution.py:edit_session()` |
| REQ-SESS-010 | `exclude_session()`/`restore_session()` both require a non-empty `reason`; exclude is refused if already excluded, restore is refused if not currently excluded (idempotency guard, not a silent no-op). | admin/manager/supervisor | `execution.py` |
| REQ-SESS-011 | `transfer_session_operation()` reassigns a session's Operation (the "giao nhầm operation" correction case) — audited, with before/after operation captured. | admin/manager/supervisor | `execution.py` route list |
| REQ-SESS-012 | Every start/finish/adjust/exclude/restore writes a transactionally-consistent audit row (same DB transaction as the state change — a session can never exist/change without a matching audit entry) via `record_audit()`. | `execution.py` throughout |

### 3.8 Kiosk workflow (`REQ-KIOSK-*`)

Two independent implementations — test both, do not assume kiosk-v1 coverage implies kiosk-v2 correctness or vice versa.

**Kiosk v1** (`kiosk.py`, browser-based, `/api/kiosk-web/*`):

| ID | Requirement | Evidence |
|---|---|---|
| REQ-KIOSK-001 | `POST /api/kiosk-web/scan` requires a non-empty `qr`; empty input returns `400 QR_REQUIRED` with a specific `error_code: SCN-001` and an operator-facing recovery hint ("Kiểm tra nguồn và dây máy quét, rồi quét lại"). | `kiosk.py:kiosk_scan()` |
| REQ-KIOSK-002 | `POST /api/kiosk-web/start`, `/finish/<session_id>` drive `WorkSessionRepository.start()/finish()` directly — same server-side rules as §3.7 apply, kiosk is not a separate rule set. | `kiosk.py` |
| REQ-KIOSK-003 | `/kiosk/employee-productivity` (the wallboard page) is public-route-shaped but its **data** endpoint (`/api/wallboard/employee-productivity`) requires no auth by design (a shop-floor TV display) — confirmed intentional, see `test_public_wallboard_data_requires_no_auth`. | `analytics.py`, tests |

**Kiosk v2** (`kiosk_v2.py`, ESP32 protocol, `/api/kiosk/v2/*`, event-sourced per-device projection):

| ID | Requirement | Evidence |
|---|---|---|
| REQ-KIOSK-004 | QR wire format is `WF|EMP|<key>` or `WF|OP|<key>` — anything else parses to `(None, None)` and is rejected. | `kiosk_v2.py:_parse_scan()` |
| REQ-KIOSK-005 | Device states: `WAIT_EMPLOYEE → WAIT_OPERATION → (session starts, resets to) WAIT_EMPLOYEE`, plus `QUANTITY_INPUT` (reachable directly once an EMP scan resolves an *already-open* session) and `DEVICE_DISABLED`/`MAINTENANCE` (hard block on any event). See §5.4 for the full transition table. | `kiosk_v2.py:_apply_event()` |
| REQ-KIOSK-006 | An `EMP` scan is always evaluated fresh against server truth (does *this* employee have an open session right now), independent of what the kiosk was previously displaying — a shared/walk-up kiosk is never "locked" to whichever employee used it last. | `kiosk_v2.py` — "SHARED-TERMINAL FIX (2026-08-26)" comment |
| REQ-KIOSK-007 | An `OP` scan is only valid immediately after a `WAIT_OPERATION`-state EMP scan; the target PO must be `IN_PROGRESS` (`OPERATION_NOT_WORKABLE` otherwise, naming the PO). | same |
| REQ-KIOSK-008 | Session-start via kiosk v2 goes through the exact same `WorkSessionRepository.start()` as everything else — no parallel/lighter validation path. | `kiosk_v2.py:_apply_event()` calls `_sessions.start(...)` |
| REQ-KIOSK-009 | `GET /api/kiosk/v2/state`, `POST /bootstrap`, `/heartbeat`, `/events` are all device-authenticated (`_authorize_kiosk_v2_device`); a disabled/unrecognized device gets a canonical device-not-allowed error, never a silent pass. | `kiosk_v2.py` |
| REQ-KIOSK-010 | Kiosk v2 event ingestion is idempotent per `(device_id, event_id)` — a retried/duplicated event must not double-apply. | `kiosk_v2.py:_store_event`, corroborated by `tests/integration/test_offline_sync_concurrency_blocker6.py`, `test_offline_burst_gate14.py` |

### 3.9 Shift / auto-close / grace period (`REQ-SHIFT-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-SHIFT-001 | Two seeded shifts, `DAY` (08:00–17:00, same-day) and `NIGHT` (18:00–03:00, `cross_midnight=TRUE`) — each shift is a set of `WORK`/`BREAK` intervals in shift-relative minutes, not wall-clock, so cross-midnight arithmetic is a first-class case, not a special-cased hack. | `0017_work_shifts.py` |
| REQ-SHIFT-002 | `auto_close_for_shift_end()` is a **distinct code path** from a manual `finish()` — never a thin `finish(good_qty=0)` wrapper. It keeps whatever quantities the session already had (never fabricates a number), sets `close_reason='AUTO_SHIFT_END'`, `closed_by_system=TRUE`, `quantity_confirmed=FALSE`, and fires `SESSION_AUTO_CLOSED` (never disguised as `SESSION_FINISHED`). | `execution.py:auto_close_for_shift_end()` |
| REQ-SHIFT-003 | Auto-close is idempotent and concurrency-safe: a per-session advisory lock serializes concurrent reconciliation runs; if the session is no longer `OPEN` by the time the lock is acquired, the call is a documented no-op (`None`), not an error. | same |
| REQ-SHIFT-004 | `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED` defaults `0` and `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN` defaults `1` — a fresh deploy's cron installs but never actually closes real sessions until both are explicitly flipped (`mesflow audit-sessions` first, inspect a dry-run cycle, then enable). | `scripts/deploy.sh` output text, `config.py` |
| REQ-SHIFT-005 | An auto-closed session's `quantity_confirmed=FALSE` is what makes it show as `AUTO_CLOSED_UNCONFIRMED` until an admin/supervisor correction (`adjust()`/`edit_session()`) flips it back — this is the direct mechanism for the "quên nhập sản lượng" journey (§10). | `0042_session_review_and_exclusion.py` docstring |

### 3.10 Exceptions — two systems (`REQ-EXC-*`)

**Session Exceptions (legacy, `session_exception_reviews`)**, surfaced in Session Management:

| ID | Requirement | Evidence |
|---|---|---|
| REQ-EXC-001 | Workflow states: `NEW → IN_PROGRESS → RESOLVED` or `→ IGNORED` (fixed 4-state enum, DB CHECK constraint). | `0018_session_exception_workflow.py` |
| REQ-EXC-002 | `PATCH /session-exceptions/workflow` transitions it — admin/manager/supervisor. | `analytics.py` |

**Exception Center (V67, `exception_records`)**, the primary durable incident system:

| ID | Requirement | Evidence |
|---|---|---|
| REQ-EXC-003 | Detected condition types (7): `LONG_OPEN_SESSION` (HIGH, >12h open), `ZERO_QUANTITY_LONG` (MEDIUM, closed >4h with 0 good+defect), `MISSING_STATION` (LOW, no station/kiosk recorded), `INVALID_DURATION` (CRITICAL, `ended_at < started_at`), `OPERATION_COMPLETED_SESSION_OPEN` (HIGH), `EMPLOYEE_SESSION_CONFLICT` (CRITICAL, overlapping sessions for one employee), `SESSION_PAST_SHIFT_END` (MEDIUM, still open past shift end + grace). | `exceptions.py:detected_conditions()` |
| REQ-EXC-004 | Every detected condition **excludes** sessions with `excluded_from_reports=TRUE` (P1 fix, 2026-08-28 — a supervisor's explicit "loại khỏi báo cáo" must silence future exception noise for that session too, not just reporting). | same, `reportable_session_sql()` |
| REQ-EXC-005 | Status lifecycle: `OPEN → ACKNOWLEDGED → RESOLVED`, or `→ AUTO_IGNORED`/`MANUAL_IGNORED`. Only `OPEN`/`ACKNOWLEDGED` count as "active" (`ACTIVE=('OPEN','ACKNOWLEDGED')`) — a unique index enforces at most one **active** record per `fingerprint` (same condition + same session never double-fires while unresolved). | `exceptions.py`, `0031_v67_exception_center.py` |
| REQ-EXC-006 | `POST /exceptions/<id>/acknowledge`, `/resolve`, `/ignore` — admin/manager/supervisor. Each transition is version-checked (`expected_version`) — a stale client action is refused, not silently applied over a newer state. | `exceptions.py`, `web/exceptions.py` |
| REQ-EXC-007 | `POST /session-exceptions/<id>/correct-session` opens the same session-correction flow (edit/adjust) directly from an exception's detail view — "Sửa Session hiện before/after rồi lưu, modal không tự đóng" per the e2e spec name. | `web/exceptions.py`, `tests/e2e/session-exception-detail-drawer.spec.js` |
| REQ-EXC-008 | Every exception record keeps `entity_type/entity_id`, `employee_id`, `production_order_id`, `part_id`, `operation_id`, `session_id` so it's traceable back to exactly the row that triggered it — never just a free-text message. | `0031_v67_exception_center.py` schema |

### 3.11 Quantity handling — good/NG/zero/correction (`REQ-QTY-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-QTY-001 | `good_qty`/`defect_qty`/`rework_qty` are always clamped to ≥0 server-side on every write path (start has no quantity; finish/adjust/auto-close all `max(int(x or 0), 0)`) — a negative input is silently floored to 0, not rejected with an error. | `execution.py` throughout |
| REQ-QTY-002 | `rework_qty > defect_qty` is a hard `ValueError` on both `finish()` and `SupervisorRepository.adjust()` — rework can never exceed the defect count it's drawn from. | same |
| REQ-QTY-003 | A session finished with `good=0, defect=0` after >4h open is not an error but **is** flagged (`ZERO_QUANTITY_LONG`, REQ-EXC-003) for human review — the system records the fact, never blocks the finish. | `exceptions.py` |
| REQ-QTY-004 | Every quantity change (finish/adjust/auto-close) is recorded as one or more `quantity_movements` rows (`GOOD`/`DEFECT`/`REPAIRABLE`) via `record_quantities()` — the ledger, not just the session's current numbers, is the audit source of truth. | `execution.py` calls to `record_quantities` |
| REQ-QTY-005 | A supervisor/admin correction (`adjust()`) is the **only** way to change a session's numbers after finish; it requires a reason, is fully audited (before/after), and always re-confirms the session (`quantity_confirmed=TRUE`). | REQ-SESS-008 |

### 3.12 Employee Productivity / KPI (`REQ-PROD-*`)

Deep-audited earlier this session (the outer workspace repo's `reports/AUTOLOGIN_FEATURE_20260904.md`'s predecessor work, `test_employee_productivity.py`'s own docstring is close to a spec in itself).

| ID | Requirement | Evidence |
|---|---|---|
| REQ-PROD-001 | The report is **completed-session-only**: `status='CLOSED' AND ended_at IS NOT NULL AND reportable_session_sql()`. It never reflects running sessions, "who's working right now," or any realtime state — confirmed by `test_response_never_exposes_running_or_active_worker_fields`. | `analytics.py: ReportRepository.employee_productivity()` |
| REQ-PROD-002 | Date filter is on `ended_at` (business date, `Asia/Ho_Chi_Minh`), **not** `started_at` — a session that starts one day and ends the next files under the day it *ended*. | same, docstring + `test_ended_at_not_started_at_decides_the_reporting_date` |
| REQ-PROD-003 | Per-session `completion_percent = expected_seconds / actual_seconds * 100`, where `expected_seconds = standard_seconds_per_unit * (good_qty+defect_qty)` — `NULL` (not `0`) whenever the standard time isn't configured, rendered as "Không đủ dữ liệu" in the UI, not a misleading `0%`. | `test_employee_d_missing_denominator_not_zero_not_crash` |
| REQ-PROD-004 | An employee's overall productivity is the **average of their own sessions' completion_percent** (equal weight per session for that employee); the summary card's cross-employee average is the average **of employees' own averages**, not a session-weighted global average — an employee with many sessions is not weighted heavier. | `analytics.py` summary-block comment |
| REQ-PROD-005 | No clamp at 100% — a session that finished faster than standard time can show >100% (verified: a session at 120% appears in the detail view's `completion_percent` list and is included in the average). | `test_employee_b_100_100_120_average_106_67` |
| REQ-PROD-006 | An employee whose *only* session(s) in range are still `OPEN` does not appear in the report **at all** — never as a `0%` row. | `test_task_case_employee_b_only_running_sessions_no_score_not_zero` |
| REQ-PROD-007 | `summary.total_good_qty`/`total_defect_qty` are the sum of the per-employee rows already computed — **fixed 2026-09-04** (previously always `0`, a real shipped bug; see the outer workspace repo's `reports/AUTOLOGIN_FEATURE_20260904.md`'s KPI-fix section and the regression test in `test_employee_productivity.py`). | `analytics.py`, this session's own fix |
| REQ-PROD-008 | The Kiosk wallboard (`/api/wallboard/employee-productivity`, no auth) publishes a configurable ranked projection of the same data (fixed-range or dynamic month-to-date, department filter, sort, page size, auto-flip interval) — a "Preview"-style call must never mutate the published config (`test_case5_preview_style_report_call_does_not_mutate_published_config`). | `analytics.py`, `test_employee_productivity_wallboard.py` |
| REQ-PROD-009 | **Not supported** (do not test for it, do not assume it exists): a raw units/hour throughput metric distinct from `productivity_percent`; a per-day/per-shift breakdown inside the ranked table (only whole-range filter + per-session drill-down); a trend chart. | the outer workspace repo's `reports/AUTOLOGIN_FEATURE_20260904.md`'s predecessor report §"Employee productivity feature — what it actually supports" |

### 3.13 Import/Export (Excel) (`REQ-IO-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-IO-001 | `GET /export.xlsx` and per-template `export-workbook` — admin/manager (export-workbook additionally readable by viewer, REQ-TPL-006). | `excel_io.py` |
| REQ-IO-002 | Import requires every Operation row to have `operation_id` OR full context (PO code + Part + Operation name) — missing any is a row-numbered Vietnamese error (`"Dòng N: thiếu ..."`), not a silent skip. | `excel_io.py:_normalize_item()` |
| REQ-IO-003 | `done/defect/status` columns are **production-derived, not importable** — a row that tries to set them directly is rejected: *"done, defect và status là dữ liệu production tự tính; hãy sửa Session nguồn rồi reconcile."* | `excel_io.py` line 247 |
| REQ-IO-004 | A PO whose `planned_quantity` already differs from the file's value is rejected outright (`ConflictError`, naming both numbers) rather than silently overwritten. | `excel_io.py` line 276 |
| REQ-IO-005 | Moving an Operation to a different PO/Part via Excel is refused once that Operation has any input-consumption ledger row. | `excel_io.py` line 301 |
| REQ-IO-006 | Duplicate `operation_id` within one import file is rejected. | `excel_io.py` line 249 |
| REQ-IO-007 | The full-workbook template import (`Parts`+`Operations` sheets) requires every Part referenced by an Operation row to actually exist in the `Parts` sheet — cross-sheet referential validation, not per-sheet in isolation. | `excel_io.py` lines 453–477 |

### 3.14 Search / filter / sort / pagination (`REQ-SEARCH-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-SEARCH-001 | Session Management's PO→Part→Operation filter is a true cascade (choosing a PO narrows the Part options to that PO's own Parts, etc.) — a stale/incompatible combination in the URL is normalized on load, not left inconsistent. | `tests/e2e/session-management-dependent-filters.spec.js` (spec name: "URL hợp lệ được restore; URL không tương thích được normalize") |
| REQ-SEARCH-002 | A slow, superseded filter request must never overwrite the UI with its (now-stale) result after a faster, more recent request has already rendered. | same spec, "request cũ không ghi đè lựa chọn mới" |
| REQ-SEARCH-003 | List endpoints generally default to a bounded page size (e.g. `WorkSessionRepository.list(limit=200)`, `employee_productivity(..., limit=1000)`) — never an unbounded full-table return. | `execution.py`, `analytics.py` signatures |
| REQ-SEARCH-004 | The Employee Productivity wallboard's public data endpoint returns the **full** filtered list for client-side paging (not server-paginated) — deliberate, per `test_case9_wallboard_returns_full_list_for_client_side_paging`. | `analytics.py` |

### 3.15 Tutorial / help / video guidance (`REQ-TUT-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-TUT-001 | `GET /api/tutorials` and `GET /tutorials/<file>` both require a real session (`session_policy.validate_and_touch()`), same as any other page — tutorial videos are not a public asset. | `app.py:tutorial_manifest()`, `tutorial_video()` |
| REQ-TUT-002 | The manifest is read from `MESFLOW_TUTORIAL_DIR` (default `/data/tutorials`) at request time; only `items` whose `file` resolves to a real, existing file **under** that root are ever exposed — path traversal (`..`, absolute paths) is explicitly rejected. | `app.py:tutorial_manifest()` |
| REQ-TUT-003 | 15 chapters as of `71.0.0.221`, covering every major module including Employee Productivity and the full Kiosk flow (added 2026-09-03/04 — see the outer workspace repo's `reports/DEMO_DATASET_AND_TUTORIAL_VIDEO_20260903.md`). | live-verified on `mesflow-demo-app`/`prod.mesflow.net:8299` |
| REQ-TUT-004 | A separate ESP Kiosk tutorial (`/api/esp-kiosk-tutorial`, `MESFLOW_ESP_TUTORIAL_DIR`) exists independently of the main tutorial manifest — same auth/path-safety pattern. | `app.py` |
| REQ-TUT-005 | The tutorial video pipeline itself (`scripts/make-user-guide-video.sh`) is gated by a coverage matrix (`tutorial/coverage-matrix.json`, `tests/e2e/tutorial-coverage.spec.js`) requiring 100% `happy_path`/`critical_exception` coverage and ≥90% overall across 8 dimensions before a release ships — QA-relevant as a **process** requirement (a merged PR touching a covered feature should keep its coverage-matrix entry accurate), not a runtime one. | `tutorial/coverage-matrix.json`, prior session work |

### 3.16 Admin / system settings (`REQ-SYS-*`)

| ID | Requirement | Role | Evidence |
|---|---|---|---|
| REQ-SYS-001 | `GET/PUT /settings/work-shifts`, `GET/PATCH /settings/working-calendar` — view any authenticated role, edit admin/manager. | login/admin+manager | `analytics.py` |
| REQ-SYS-002 | Users & Roles: `GET/POST/PATCH /api/users`, `POST /reset-password`, `GET/PUT /api/roles` — gated by `permission_required('users.view'/'users.manage'/'roles.manage')`, not the coarser `roles_required()` decorator most other routes use. | `permission_required` | `users.py` |
| REQ-SYS-003 | `POST /auth/change-password` — any authenticated user, self-service only (no `user_id` param, always acts on the caller's own session). | login_required | `users.py` |
| REQ-SYS-004 | System Console (`/api/system-health/errors|services|diagnostics|audit`, service restart, diagnostics run) is **exclusively** `super_admin` — see BR-002. | super_admin only | `system_health.py` |
| REQ-SYS-005 | `/api/system-health` (summary), `/kiosks`, alert/notification/prediction endpoints are `login_required` (any role), while `/history` additionally self-checks `ok()==super_admin` inline and 403s otherwise even though the outer decorator is only `login_required` — an inconsistent-looking but deliberate two-tier gate on the same blueprint. | `system_health.py:history()` |

### 3.17 Audit / history / logging (`REQ-AUDIT-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-AUDIT-001 | `GET /action-logs`, `/error-traces`, `/log-retention/*` are **admin-only** (`@admin_required`, i.e. requires `roles.manage`) — narrower than most other admin+manager routes. | `action_logging.py` |
| REQ-AUDIT-002 | `GET /audit-logs` (business audit trail) requires exactly `business_audit.view` — held by `manager`/`supervisor` but **not** `admin` by default (admin's bypass in `_has_permission` still makes it accessible in practice; the grant-table itself doesn't explicitly list it for `admin`, only for `manager`/`supervisor`). | `analytics.py`, `rbac.py` grant table |
| REQ-AUDIT-003 | Every business state change (session start/finish/adjust/exclude/restore/transfer, PO start, Operation cancel, exception ack/resolve/ignore) writes to the audit trail via `record_audit()` in the **same transaction** as the change — an audit row can never be missing for a change that committed, nor exist for one that rolled back. | throughout `execution.py`, `master_data.py`, `exceptions.py` |
| REQ-AUDIT-004 | Log retention (`MESFLOW_LOG_RETENTION_*`) runs on a schedule with distinct day-counts per category (success 30d, slow 90d, resolved-error 180d, unresolved-error 365d, security 365d) — a QA data-retention check should assert these are the boundaries actually enforced, not assume a single blanket TTL. | `compose.yml` env defaults, `config.py` |

### 3.18 API behavior the UI depends on (`REQ-API-*`)

| ID | Requirement | Evidence |
|---|---|---|
| REQ-API-001 | Every mutating endpoint that can be retried (kiosk start/finish, group finish, supervisor adjust) is idempotent via a caller-supplied `request_id`, stored in `kiosk_idempotency` — a retried identical request returns the **original** response (`idempotent_replay: true`), never double-applies. | `execution.py` throughout |
| REQ-API-002 | Every write path takes the production-order row lock **first**, before any other row lock, in a fixed documented order (`lock_production_order_for_operation_first()`) — a real, previously-live deadlock class this prevents; a regression here is a concurrency bug, not a cosmetic one. | `execution.py` comments at every `start`/`finish`/`adjust`/etc. |
| REQ-API-003 | `GET /api/system/ready` reports `version`, `commit`, `migration_head`, `server_role`, `db_ok`, `schema_version` — this is the health contract every deploy script (`deploy.sh`) actually parses to confirm a promotion succeeded; a QA smoke test should hit this exact endpoint, not infer health from the home page loading. | `app.py`, `scripts/deploy_lib.sh` |
| REQ-API-004 | `GET /api/system/version` is intentionally **unauthenticated** (used for external health checks) and returns only code-derived fields (no host/container identity) — do not use it as a "which physical instance is this" signal (a real investigation this session found two different real hosts reporting byte-identical version JSON). | `app.py:version()`, the outer workspace repo's `reports/DEMO_DATASET_AND_TUTORIAL_VIDEO_20260903.md`'s 2026-09-04 addendum |

---

## 4. Business rules

Numbered independently of the module tables above (a `BR-###` may be cited by several `REQ-*` rows).

| ID | Rule | Verified by |
|---|---|---|
| BR-001 | `admin` role bypasses the permission table entirely — always `True`. | `has_permission()` code |
| BR-002 | `super_admin` gets `admin`'s business bypass but System Console access requires the literal role, never satisfied by `admin`. | `super_admin_required()` code |
| BR-003 | An employee may have **at most one `OPEN` work session** at any time (DB-enforced). | `uq_open_session_per_employee` index |
| BR-004 | A downstream Operation with input-flow enabled cannot `start()` until its upstream source Operation has had **at least one session started** (not necessarily finished). | `execution.py:start()` |
| BR-005 | `qty=0` on finish is never rejected; if the session was open >4h, it is flagged `ZERO_QUANTITY_LONG` for review, not blocked. | `exceptions.py` |
| BR-006 | `rework_qty` can never exceed `defect_qty`, enforced on both `finish()` and `adjust()`. | `execution.py` |
| BR-007 | A `CLOSED` session is **never deleted**, even when excluded from reports — history/audit is permanent; "exclude" only stops it counting toward aggregates. | `exclude_session()` docstring |
| BR-008 | Auto-close is a dedicated lifecycle, not a disguised manual finish — `close_reason`/`closed_by_system`/`shift_boundary_used_at` make it distinguishable after the fact, and it fires a different domain event (`SESSION_AUTO_CLOSED` vs `SESSION_FINISHED`). | `0040_shift_lifecycle...py`, `auto_close_for_shift_end()` |
| BR-009 | An auto-closed session is `quantity_confirmed=FALSE` until a human correction confirms it; any `adjust()`/`edit_session()` always sets it back `TRUE`. | `0042_session_review_and_exclusion.py` |
| BR-010 | "Excluded from reports" affects **only** aggregation (KPI/progress/time); the session's own `OPEN`/`CLOSED` status and its presence in history/audit are untouched. | `exclude_session()` |
| BR-011 | Material/input-flow constraint: a target Operation cannot consume more GOOD (or REWORK, per its configured `input_source_kind`) quantity from its source Operation than `source.produced − already_allocated_elsewhere`; violating this is a `ConflictError` naming the exact available quantity. | `_validate_and_upsert_input_consumption()` |
| BR-012 | Operation dependencies distinguish two independent relationships: a pure time/order **predecessor** (must simply exist) and a quantity **input source** (must have a started session) — the same Operation can be both, in which case only the (stricter) input-source rule applies. | `execution.py:start()` comment |
| BR-013 | Full-session edits (`edit_session()`) support optimistic concurrency via `expected_updated_at` — two supervisors racing to correct the same session, one wins and the other is refused, never a silent last-write-wins. | `execution.py:edit_session()` signature |
| BR-014 | PO/Part deletion is refused whenever any descendant Operation has real production history (session, ledger, output, event, adjustment, or QC) — the specific kind(s) of history found are named in the error, not a generic refusal. | `ProductionOrderRepository.delete()`, `PartRepository.delete()` |
| BR-015 | An Exception Center record's `fingerprint` is unique **while active** (`OPEN`/`ACKNOWLEDGED`) — the same condition recurring after a prior instance was resolved/ignored creates a fresh record (a new occurrence), not a silent revival of the old one. | `uq_exception_active_fingerprint` |
| BR-016 | A stale, superseded UI request must never overwrite a more recent one's rendered result — applies to filter/search panels generally (verified concretely for Session Management's dependent filters). | `session-management-dependent-filters.spec.js` |
| BR-017 | Timezone/shift math is always done in shift-relative minutes against the site timezone (`Asia/Ho_Chi_Minh` by default, configurable via `MESFLOW_TIMEZONE`), never naive wall-clock subtraction — e.g. `NIGHT` (18:00–03:00, `cross_midnight=TRUE`) must resolve a session started at 23:00 and a session started at 01:00 the following calendar day as the same shift instance, not two different ones. | `0017_work_shifts.py`, `core/working_calendar.py` (not fully read this pass — see SPEC-GAP-004) |
| BR-018 | KPI/report/exception-detection queries share one predicate (`reportable_session_sql()`: `status='CLOSED' AND NOT excluded_from_reports`) rather than each hand-rolling their own — if a number looks wrong across two different screens simultaneously, check whether both actually call this shared predicate before assuming a data bug. | `db/repositories/base.py`, referenced throughout `analytics.py`/`exceptions.py` |

---

## 5. Status / state machines

### 5.1 Work Session

```
                    start()
                      │
                      ▼
                   [OPEN]  ──────────────┐
                      │                  │
         finish()     │      auto_close_for_shift_end()
     (manual, real     │      (system, past shift end + grace,
      operator action) │       only if still OPEN)
                      ▼                  ▼
                  [CLOSED]           [CLOSED]
              close_reason=''    close_reason='AUTO_SHIFT_END'
              closed_by_system   closed_by_system=TRUE
                =FALSE           quantity_confirmed=FALSE
              quantity_confirmed
                =TRUE
```

Orthogonal flags on a `CLOSED` (or `OPEN`) session, independently settable, not additional states:
- `quantity_confirmed` (bool) — flipped `TRUE` by any `adjust()`/`edit_session()` correction.
- `excluded_from_reports` (bool) — set/cleared by `exclude_session()`/`restore_session()`, each requiring a reason; does not change `status`.

**No transition exists back from `CLOSED` to `OPEN`.** A "reopen" requirement was not found anywhere in the code — if QA is asked to test one, treat it as SPEC-GAP-005 (§13), not an assumed feature.

### 5.2 Operation (computed, not directly settable except by explicit Cancel)

Computed fresh on every `reconcile_operation_and_po()` call (i.e. after every session start/finish/adjust/exclude/restore under it) from `production_state.py`:

| Precondition (checked in this order) | Resulting status |
|---|---|
| `current == 'CANCELLED'` | `CANCELLED` (sticky — never recomputed away) |
| any session currently `OPEN` | `IN_PROGRESS` |
| `current == 'COMPLETED'` and zero reportable sessions | `COMPLETED` (stays completed even with no history left, e.g. after exclusions) |
| `planned_quantity > 0` and `good_qty ≥ planned_quantity` | `COMPLETED` |
| `current == 'PAUSED'` | `PAUSED` (sticky — P1 fix 2026-08-28: an explicit pause must survive ordinary reconcile churn, checked after the two "wins" above but before the generic history fallback) |
| any reportable session exists at all | `IN_PROGRESS` |
| `current in {DRAFT, PLANNED, RELEASED, READY}` | unchanged |
| (fallback) | `PLANNED` |

Explicit transition: `POST /operations/<id>/cancel` → `CANCELLED`, refused if the Operation is already `COMPLETED` (must use the rework workflow instead) or has any `OPEN` session (must close it first).

### 5.3 Production Order

Enum: `DRAFT, PLANNED, RELEASED, IN_PROGRESS, PAUSED, COMPLETED, CANCELLED` (validated on every write, §REQ-PO-003). The one explicit, code-driven transition is `Start` (→`IN_PROGRESS`, REQ-PO-002); every other status change goes through the generic PATCH and is **not further state-machine-validated** by the code beyond "is this a member of the enum" — e.g. nothing in `_normalize()` stops a direct `PLANNED → COMPLETED` PATCH. Treat any stricter PO transition rule as unverified (SPEC-GAP-006) unless a specific test proves otherwise.

### 5.4 Kiosk v2 device projection

| Current state | Event | New state | Notes |
|---|---|---|---|
| `WAIT_EMPLOYEE` | `SCAN` (EMP), employee has no open session | `WAIT_OPERATION` | |
| `WAIT_EMPLOYEE` | `SCAN` (EMP), employee **has** an open session | `QUANTITY_INPUT` | Direct — no intermediate `SESSION_ACTIVE` stop (removed 2026-08-27, see field-report comment) |
| `WAIT_EMPLOYEE` | `SCAN` (OP) | *(rejected)* | `STATE_INVALID_TRANSITION` — "Cần quét thẻ nhân viên" |
| `WAIT_OPERATION` | `SCAN` (OP), PO `IN_PROGRESS` | `WAIT_EMPLOYEE` | Session created server-side; device resets immediately so the *next* employee can use it (shared-terminal fix) |
| `WAIT_OPERATION` | `SCAN` (OP), PO not `IN_PROGRESS` | *(rejected)* | `OPERATION_NOT_WORKABLE` |
| `WAIT_OPERATION` | `SCAN` (EMP) | *(rejected)* | `STATE_INVALID_TRANSITION` — "Cần quét mã công đoạn" |
| `SESSION_ACTIVE` | `SCAN` (EMP), same employee, session still open | `QUANTITY_INPUT` | Legacy-reachable path only; not reachable via the normal flow above (kept, documented as dead code, harmless) |
| any | `FINISH_REQUESTED` | → quantity flow | |
| any | `QUANTITY_SUBMITTED` | session finishes | goes through real `finish()` |
| any | `CANCEL_REQUESTED` | resets | |
| `DEVICE_DISABLED` / `MAINTENANCE` | any event | *(rejected)* | `DEVICE_NOT_ALLOWED` — hard block regardless of event type |

### 5.5 Exception Center record

```
   detected_conditions() finds a NEW fingerprint (no active record for it)
                              │
                              ▼
                          [OPEN]
                    ┌────────┼────────┐
              acknowledge  resolve   ignore
                    │        │         │
                    ▼        ▼         ▼
           [ACKNOWLEDGED] [RESOLVED] [MANUAL_IGNORED]
                    │
                resolve/ignore
                    │
              ┌─────┴─────┐
              ▼           ▼
         [RESOLVED]  [MANUAL_IGNORED]

   (a system-side auto-ignore path exists: AUTO_IGNORED,
    auto_ignore_reason/auto_ignored_at columns — trigger not
    traced this pass, see SPEC-GAP-007)
```

Only `OPEN`/`ACKNOWLEDGED` are "active"; each transition is version-checked (`expected_version`) and history-logged (`exception_history`, append-only).

### 5.6 Session Exception (legacy) review

`NEW → IN_PROGRESS → RESOLVED`, or `→ IGNORED` from any of the first two (simple 4-value CHECK constraint, no further code-enforced ordering found — verify against `session_exception_reviews`-specific code before asserting a stricter sequence).

---

## 6. Validation requirements

Consolidated from the module tables above — this section is the flat "what to fuzz" checklist.

| Field / form | Rule | Error surfaced as |
|---|---|---|
| PO `status` | must be one of 7 enum values | `ValueError` → 400-class |
| PO `priority` | must be one of `LOW/NORMAL/HIGH/URGENT` | same |
| PO `planned_quantity` | integer, `> 0` | `ValueError`, Vietnamese message |
| PO `planned_start_at`/`planned_end_at` | if both set, end > start | `ValueError` |
| PO `code`, `product` | required, non-empty on create | `ValueError` |
| Employee `employee_no` | required; uppercased on write | — |
| Employee `employment_status` | free text, but `"Đã nghỉ"` is the specific sentinel that flips `active=FALSE` — any other value (including empty) leaves `active=TRUE` | — |
| Session `good_qty`/`defect_qty`/`rework_qty` | clamped ≥0; `rework ≤ defect` enforced | `ValueError` |
| `SupervisorRepository.adjust()` `reason` | required, non-empty | `ValueError` |
| `exclude_session()`/`restore_session()` `reason` | required, non-empty | `ValueError` |
| Kiosk `qr` scan payload | required, non-empty; must parse as `WF|EMP|...` or `WF|OP|...` for kiosk v2 | `400 QR_REQUIRED` (v1) / silently unmatched → next check fails (v2) |
| `request_id` (idempotency key, start/finish/adjust) | required, non-empty | `ValueError('request_id required')` |
| Excel import Operation row | needs `operation_id` OR full PO+Part+Operation-name context | row-numbered `ValueError` |
| Excel import `done/defect/status` columns | rejected outright — not a settable import field | `ValueError` |
| Autologin `persona` | must be exactly one of `admin/manager/supervisor/operator/viewer` | `400 AUTO_LOGIN_INVALID_PERSONA` with the allowed list echoed back |
| Role permission update (`PUT /roles/<code>/permissions`) | every submitted code must exist in the permission catalog | `ValueError('Unknown permissions: ...')` |
| Concurrent duplicate write (any idempotency-keyed action) | same `request_id` twice → returns the **original** response, `idempotent_replay:true` | not an error |
| Concurrent conflicting write (two different actions racing the same row) | row-level `FOR UPDATE` lock serializes them; the loser sees the winner's already-applied state | depends on the specific check that then fails, e.g. `'session already closed'` |

---

## 7. UI/UX acceptance requirements

Sourced from this session's own live UI audits (checkbox/radio normalization — see the outer workspace repo's `reports/CHECKBOX_RADIO_UI_NORMALIZATION_20260903.md`) plus direct screenshot verification of the autologin/RBAC work. Kept to **behavior QC can actually verify**, not a pixel-perfect spec.

| ID | Requirement |
|---|---|
| REQ-UI-001 | Every checkbox/radio input on a given form renders at the same rendered width/height (in px, via computed style) as every other checkbox/radio on that same form — this was a real, fixed defect this session (two checkboxes on the PO Operation modal, "Giới hạn đầu vào" vs "NG tiêu hao đầu vào", differed in size before the fix); regression-check any new settings panel by comparing computed box dimensions across all its checkbox/radio inputs, not by eye. |
| REQ-UI-002 | A field whose value is implicitly always-true for the current business rule is not shown as a togglable option at all (e.g. "NG tiêu hao đầu vào" was removed from the PO Operation modal once confirmed the value is always effectively `true`) — don't expose dead configuration surface. |
| REQ-UI-003 | The login page's brand/context panel (left) and the form (right) are a fixed split-screen layout — "Điều hành sản xuất rõ ràng tại xưởng" heading, `Industrial Operations Console · v{version}` footer, KIMEX wordmark — present regardless of autologin state. |
| REQ-UI-004 | A role without a given page's `.view` permission does not show that page's entry in the left sidebar nav at all (confirmed live: the `operator` persona's sidebar has no "Quản trị" section; the `admin` persona's sidebar does). |
| REQ-UI-005 | The primary admin viewport target is **1366×768** (`PRODUCT.md` §Operating Context) — any layout QA should include this exact resolution, not just a generic "desktop" bucket. |
| REQ-UI-006 | Responsive breakpoints exercised by the existing e2e suite: `1920×1080`, `1366×768`, `390×844` (mobile) — treat these three as the minimum required matrix for any new page's "không vỡ tại ..." (doesn't break at) check, matching the pattern already used across `dashboard-employee-timeline.spec.js`, `production-schedule-sticky.spec.js`, `session-exception-detail-drawer.spec.js`, etc. |
| REQ-UI-007 | Modal/drawer interactions for exception resolution explicitly do **not** auto-close on save ("modal không tự đóng") — the operator must see the saved before/after state and close it themselves. |
| REQ-UI-008 | Sticky elements (PO group headers in Production Schedule) must not duplicate on scroll and must layer at the correct z-order ("sticky đúng tầng, không duplicate"). |
| REQ-UI-009 | Filter state and scroll position survive a data refresh — a refresh must not silently reset the user's filter or jump scroll to top. |
| REQ-UI-010 | Empty states are explicit, not a blank panel — e.g. Session Management's table shows "Không có Session hoàn thành trong khoảng ngày đã chọn" rather than an empty `<table>`. |
| REQ-UI-011 | Kiosk auto-login status text (`#autoLoginStatus`) gives the operator explicit feedback during the async auto-login POST ("Chế độ test: đang tự đăng nhập...") rather than a silent spinner-less wait. |
| REQ-UI-012 | Interface language is Vietnamese throughout the admin app (`PRODUCT.md` §Capabilities) — an English string appearing in a user-facing label/error/toast is itself a defect, not a style nit, given this is an explicit, confirmed product decision. |

**Not covered this pass** (do not assume verified): full keyboard-navigation/focus-order accessibility audit, screen-reader labeling, color-contrast ratios. `PRODUCT.md` §Accessibility itself says no formal accessibility standard has been confirmed — treat any accessibility test beyond "labels are distinguishable from values, not color-only" as exploratory, not a pass/fail gate.

---

## 8. Non-functional requirements

| ID | Requirement | Evidence |
|---|---|---|
| REQ-NFR-001 | **Concurrency**: every write path that touches a PO's Operations takes the PO row lock first, in a fixed order, specifically to prevent deadlocks under concurrent kiosk traffic on the same PO — a load test that only checks throughput without checking for lock-wait/deadlock errors under concurrent same-PO start/finish is incomplete. | `execution.py` `lock_production_order_for_operation_first()` comments throughout |
| REQ-NFR-002 | **Idempotency**: kiosk start/finish/adjust and the offline-sync ingestion path are idempotent per request/event id — a QA network-flake simulation (retry the same POST twice) must assert the *same* result, not a duplicated session/movement. | `execution.py`, `tests/integration/test_offline_sync_concurrency_blocker6.py`, `test_offline_burst_gate14.py` |
| REQ-NFR-003 | **Transactional integrity**: state change + its audit row + its domain event are one DB transaction — a forced mid-write failure test (if the harness supports fault injection) should confirm partial-commit is impossible, not just assume it from code reading. | `execution.py` transaction blocks |
| REQ-NFR-004 | **Security — session cookies**: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'` always; `SESSION_COOKIE_SECURE` is context-dependent (`Secure` for public/production traffic, relaxable only for direct-localhost or trusted-internal-network HTTP per `LocalhostAwareSessionInterface` — never relaxed for proxied/public traffic). | `app.py` `create_app()`, `LocalhostAwareSessionInterface` |
| REQ-NFR-005 | **Security — RBAC fail-closed**: `_has_permission()` catches any exception from the RBAC lookup itself and returns `False` (fails closed), never `True`. | `web/auth.py` |
| REQ-NFR-006 | **Security — no CSRF token mechanism was found** in the routes read this pass; session-cookie `SameSite=Lax` is the primary cross-site mitigation in place. Flagged as SPEC-GAP-008 (§13) rather than asserted safe or unsafe — a dedicated CSRF audit was out of scope here. | not verified this pass |
| REQ-NFR-007 | **Deploy/migration/rollback**: `scripts/deploy.sh <target> <version-or-digest>` never builds on the target (pull-by-digest only); every deploy re-verifies the *running image's* digest (not just the container's tag) matches what was requested, and health-checks `/api/system/ready` before declaring success; automatic rollback to the previous digest on any health-check failure. A QA deploy-verification test should assert against this exact endpoint/digest contract, matching what `deploy.sh` itself checks. | `scripts/deploy.sh`, `scripts/deploy_lib.sh`, this session's own real deploys |
| REQ-NFR-008 | **Backup/health-check expectations**: `/api/system/ready` is the canonical liveness+readiness contract (see REQ-API-003); a QA smoke suite should treat "container Docker-healthy" and "`/api/system/ready` returns `ok:true`" as two separate checks — a container can report Docker-healthy on a stale/no healthcheck config (observed directly this session: `mesflow-demo-app` has **no** `HEALTHCHECK` at all, `docker inspect` returns `null` — Docker-level health status is not a reliable signal for that specific container). | live-verified 2026-09-04, the outer workspace repo's `reports/AUTOLOGIN_FEATURE_20260904.md` |
| REQ-NFR-009 | **Browser support**: no explicit supported-browser list was found in the repo (no browserslist config, no README/docs statement). Playwright's e2e suite runs Chromium only. Treat cross-browser (Firefox/Safari) coverage as **not currently verified** — SPEC-GAP-009. | absence confirmed by search this pass |
| REQ-NFR-010 | **Performance/SLA**: no explicit numeric SLA (e.g. "dashboard must load in Xms") was found documented anywhere in the repo. `MESFLOW_ACTION_LOG_SLOW_MS=1500` exists as an internal *slow-request logging threshold*, not a user-facing SLA — do not conflate the two. Treat performance requirements as SPEC-GAP-010 until a real target is set by the product owner. | `config.py`, absence confirmed by search |

---

## 9. Environment & test-data contract

| Tier | `MESFLOW_ENV` | `SERVER_ROLE` | Autologin | Notes |
|---|---|---|---|---|
| **DEV** (isolated QA sandbox, port 18280) | `local` | (unset) | Allowed with just `MESFLOW_TEST_AUTO_LOGIN=1` | `compose.projectflow-local.yml`; ephemeral, torn down/recreated per QA run |
| **DEV** (isolated pytest+Playwright stack) | `test` | (unset) | Already on by default for e2e (`compose.test.yml` sets `MESFLOW_TEST_AUTO_LOGIN=1`) | The stack every `docker-test.sh` run uses; real Postgres, real migrations, thrown away after |
| **DEMO** (`mesflow-demo-app`, 127.0.0.1:8081) | `production` (!) | (unset) | On, with `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` (enabled 2026-09-04) | Standalone `docker run`, **no bind mounts** — anything written to its filesystem (tutorial videos, etc.) is lost on container recreate unless backed up first; separate `mesflow_demo` database, isolated from local DEV's own `mesflow` database |
| **PRODTEST** (`prod.mesflow.net:8299`) | `production` (!) | `PRODUCTION_TEST` | Off by default; would need the same explicit override as DEMO to enable | Compose-managed (`/home/dell/deploy/mesflow-prodtest`), reached via the `deploy.sh prodtest` pipeline |
| **This host's `/opt/mesflow`** (`mesflow-app` container, 127.0.0.1:8080) | `production` | `DEV` (as currently configured — inconsistent with its own compose default, not corrected this pass) | Not evaluated this session | **This is NOT confirmed to be real public `mesflow.net`** — see below |
| **Real production** (`mesflow.net`) | unconfirmed | unconfirmed | must never have the override set | Host is genuinely unreachable from this dev machine as of 2026-09-04 (a documented, deterministic canary test disproved the earlier belief that `/opt/mesflow` on this host *is* it — see `docs/DEPLOY_ARCHITECTURE_A.md`'s "2026-09-04 follow-up" and the outer workspace repo's `reports/DEMO_DATASET_AND_TUTORIAL_VIDEO_20260903.md`'s addendum). **Do not run any QA action against a URL believed to be "production" without first re-confirming via that doc's canary-test method — a stale assumption here has already caused one real incident this workspace's history documents.** |

**⚠ Important, non-obvious fact for QA**: `MESFLOW_ENV=production` does **not** mean "this is the real live business system" in this codebase — it is hardcoded by `compose.yml` on *every* tier that file deploys (DEMO and PRODTEST included), and is really more of a "run in hardened/secure-cookie mode" switch than a host-identity signal. The only tiers with `MESFLOW_ENV` genuinely different are the two throwaway local sandboxes above. Never infer "this is real production" from `MESFLOW_ENV` alone.

### 9.1 Autologin — how to use it for QA (see also §2.4, `docs/AUTOLOGIN.md`)

```
# Any non-production sandbox:
MESFLOW_TEST_AUTO_LOGIN=1
# Open /login (auto-logs in as admin by default) or /login?persona=operator (etc.)

# DEMO/PRODTEST specifically (MESFLOW_ENV=production there):
MESFLOW_TEST_AUTO_LOGIN=1
MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1
```
Never set the override on anything that might be real production.

### 9.2 Demo seed / idempotency

`app/mesflow/tutorial_data.py` (`python -m mesflow.tutorial_data seed|status|cleanup`) — additive-safe, prefix-namespaced (`TUT-%` codes, `TUT39:%` notes), idempotent (cleanup-then-reseed on every `seed` call), guarded against running on a real production DB unless `MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1` is explicitly set. This is the **only** sanctioned way to seed demo/tutorial data — QC should never hand-write `INSERT`s into a shared demo/prodtest database (this session did so once, deliberately, for a handful of throwaway persona-test users on the *isolated local sandbox only* — never on a shared tier).

### 9.3 What QC may reset vs. must not touch

| Data | May QC reset it? |
|---|---|
| The isolated `compose.test.yml`/`compose.projectflow-local.yml` sandbox databases | Yes, freely — torn down and recreated per run by design |
| `mesflow-demo-app`'s `mesflow_demo` database (TUT-prefixed rows) | Yes, via `tutorial_data.py cleanup`/`seed` — never via raw SQL DELETE on non-prefixed rows |
| `mesflow-demo-app`'s non-TUT-prefixed rows (real seeded employees like `manager`/`operator`/`viewer`) | **No** — these are the canonical persona accounts the autologin feature and manual RBAC testing depend on; deleting them breaks `?persona=` for everyone |
| `prod.mesflow.net:8299` (PRODTEST) database | Only via the documented `deploy.sh`/migration pipeline — never ad-hoc | 
| Real production data (whichever host that turns out to be) | **Never**, without separate, explicit, human authorization each time — this is a workspace-wide standing rule, not specific to this document |

### 9.4 Base URLs (stable convention, no secrets)

| Tier | URL |
|---|---|
| Local DEV sandbox | `http://127.0.0.1:18280` |
| Isolated pytest+Playwright stack | `http://mesflow-test-api:8080` (in-network only) |
| Demo | `http://127.0.0.1:8081` |
| Prodtest | `http://127.0.0.1:8299` / `https://prod.mesflow.net` |
| This host's `/opt/mesflow` | `http://127.0.0.1:8080` |

---

## 10. End-to-end user journeys

Each journey: numbered steps + expected result. Written to be turned directly into an E2E test case (§12's format).

### JOURNEY-001 — Admin builds a PO from a Template through to a worked Operation

1. Admin logs in (`REQ-AUTH-001`). **Expect**: lands on `/app`, sidebar shows full nav.
2. Admin opens a Template, adds/edits Parts+Operations (`REQ-TPL-001`). **Expect**: tree saves; `validate` shows no structural errors.
3. Admin instantiates the Template into a new PO (`REQ-TPL-004`/`REQ-PO-001`). **Expect**: new PO exists, status `PLANNED` (or `DRAFT`), with the Template's Parts/Operations copied in.
4. Admin (or supervisor) Starts the PO (`REQ-PO-002`). **Expect**: status → `IN_PROGRESS`; every child Operation becomes kiosk-workable (readiness check no longer blocks `start()`).
5. An Employee is created/exists and is `active` (`REQ-EMP-001`).
6. Operator (kiosk) scans employee, scans the first Operation, session `start()`s (`REQ-SESS-001`/`002`). **Expect**: Operation status → `IN_PROGRESS` (§5.2); PO stays `IN_PROGRESS`.
7. Operator finishes the session with a good quantity (`REQ-SESS-004`). **Expect**: session `CLOSED`, `quantity_confirmed=TRUE`; Operation's `done_qty` reflects it; if `good_qty ≥ planned_quantity`, Operation → `COMPLETED` (§5.2).
8. Dashboard/Overview refreshed. **Expect**: the PO's progress numbers reflect the new closed session (`REQ-DASH-003`).

### JOURNEY-002 — Operator/Kiosk normal start/finish (both kiosk implementations)

1. Kiosk v1 or v2: scan employee QR. **Expect**: if the employee has no open session, kiosk moves to "waiting for operation" state; if they already have one open, kiosk goes straight to quantity input (kiosk v2: `REQ-KIOSK-005`).
2. Scan a valid, workable Operation QR. **Expect**: session created server-side (`REQ-KIOSK-008`), kiosk device resets to wait-for-employee (v2: `REQ-KIOSK-006`) so the next worker can use it immediately.
3. Enter good/defect/rework and submit finish. **Expect**: same validation as the web finish path (`REQ-QTY-001/002`), session closes.
4. Repeat step 1 immediately with a **different** employee's card. **Expect**: works with no interference from the previous employee's session (shared-terminal correctness, `REQ-KIOSK-006`).

### JOURNEY-003 — Forgot to enter quantity → auto-close → admin resolves

1. Operator starts a session and never finishes it (walks away, shift ends).
2. Shift end + grace period passes; `shift_session_reconciliation` job runs (`REQ-SHIFT-002`/`003`). **Expect**: session auto-closes with whatever quantity it already had (likely 0/0), `close_reason='AUTO_SHIFT_END'`, `quantity_confirmed=FALSE`.
3. Exception Center / audit surfaces it (`SESSION_PAST_SHIFT_END` while open, or the resulting `ZERO_QUANTITY_LONG` once closed if applicable, `REQ-EXC-003`).
4. Supervisor opens the session, corrects the real quantity via `adjust()` with a reason (`REQ-SESS-008`). **Expect**: `quantity_confirmed` flips to `TRUE`; an `operation_adjustments` audit row and `VALUE_CHANGED` event are created; Operation/PO progress reconciles to the corrected number.

### JOURNEY-004 — Giao nhầm Operation → sửa/reassign → audit/report đúng

1. A session is mistakenly started against the wrong Operation.
2. Supervisor uses `transfer_session_operation()` to reassign it (`REQ-SESS-011`). **Expect**: session now belongs to the correct Operation; both the old and new Operation's progress reconcile; an audit trail captures the before/after Operation.
3. Reports (dashboard, employee productivity) for both the old and new Operation reflect the correction — the session's contribution moves, it does not duplicate.

### JOURNEY-005 — Session sai → disable (exclude) → không ảnh hưởng báo cáo

1. A session is identified as junk (duplicate scan, test data, etc.).
2. Supervisor calls `exclude_session()` with a reason (`REQ-SESS-010`/BR-010). **Expect**: session stays visible in history, `excluded_from_reports=TRUE`; Operation/PO progress, KPI, and Exception Center detection all stop counting it (`REQ-EXC-004`).
3. `restore_session()` with a reason reverses it. **Expect**: session counts again from the next reconcile onward.

### JOURNEY-006 — Exception zero qty / NG → Exception Center → resolve/confirm

1. A session closes with 0/0 after >4h open. **Expect**: `ZERO_QUANTITY_LONG` (MEDIUM) appears in the Exception Center (`REQ-EXC-003`).
2. Supervisor acknowledges it (`OPEN → ACKNOWLEDGED`, `REQ-EXC-006`).
3. Supervisor uses "correct-session" from the exception's own detail view (`REQ-EXC-007`) to fix the quantity in place.
4. Supervisor resolves the exception (`→ RESOLVED`). **Expect**: no longer counts as "active" (BR-015); a fresh recurrence of the same condition on the same session would open a **new** record, not reopen this one.

### JOURNEY-007 — Employee Productivity: session data → KPI/table/trend must match

1. Seed/verify several `CLOSED` sessions for one employee across a date range, with known `standard_seconds_per_unit` on their Operations.
2. `GET /reports/employee-productivity?from=...&to=...`. **Expect**: `completed_sessions` count matches exactly; `productivity_percent` = the average of each session's own `expected/actual*100` (REQ-PROD-003/004); an `OPEN` session in the same range is invisible to this report entirely (REQ-PROD-001).
3. Drill into the employee's detail (`/reports/employee-productivity/<id>`). **Expect**: every session listed matches the summary's `completed_sessions` count 1:1.
4. Compare the Kiosk wallboard's ranked table for the same range/filters. **Expect**: same underlying numbers (both read the same repository method), differing only in presentation/paging.

### JOURNEY-008 — RBAC theo các persona

1. Using autologin (`?persona=<role>`, non-production sandbox, §9.1), log in as each of `admin/manager/supervisor/operator/viewer` in turn.
2. For each, hit every route in §3's tables relevant to that role's boundary (e.g. `operator` attempting `POST /production-orders/<id>/start` should `403`; `viewer` attempting any `*.edit`/`*.manage` route should `403`).
3. **Expect**: every boundary in §2's grant table holds exactly, both API-level (`403 FORBIDDEN` with the specific `permission` code) and UI-level (nav item absent per §2.3).

---

## 11. Traceability matrix

Legend: **A** = automated (pytest/Playwright), **M** = manual-only observed this session (screenshot/live curl, no committed automated assertion found), **P** = partial (some but not all sub-requirements covered), **—** = no coverage found this pass.

| Requirement group | Existing automated coverage | Status |
|---|---|---|
| REQ-AUTH-001…008 (real login/session/logout) | `tests/e2e/tutorial-video.spec.js` (real password), `test_local_8080_login_contract.py`, `test_internal_qa_login_contract.py` | A |
| REQ-AUTH-009 (autologin) | `tests/test_autologin_guard_unit.py`, `tests/integration/test_autologin_persona.py`, `tests/test_v6584431_production_hardening.py` | A |
| §2 RBAC matrix | `tests/integration/test_permission_matrix.py`, `test_super_admin_system_console.py`/`_unit.py`, `test_rbac_self_heal.py` | A (matrix-level); role×route enumeration in §2/§3 of this doc is broader than what `test_permission_matrix.py` alone checks — treat this doc's tables as the fuller spec, that test file as a strong but partial automated subset |
| REQ-DASH-* | `tests/e2e/overview-and-calendar.spec.js`, `overview-production-summary.spec.js`, `dashboard-employee-timeline.spec.js` | A |
| REQ-PO-*, REQ-PART-*, REQ-TPL-* | `tests/e2e/catalog-crud.spec.js`, `catalog-visual.spec.js`, `template-ui.spec.js`; `test_p1_audit_2026_08_28.py`, `test_production_state_integrity.py`, `test_production_consistency_p1.py` | A (P for the finer PO-transition rules noted as SPEC-GAP-006) |
| REQ-EMP-* | `tests/e2e/catalog-crud.spec.js` (employees are part of "catalog" CRUD) | P — no dedicated employee-lifecycle test file found by name |
| REQ-SESS-* | `test_session_lifecycle_state_machine_property.py`, `test_session_lifecycle_observability_phase13.py`, `test_session_overlap_and_exceptions.py`, `test_shift_session_lifecycle.py`, `test_write_path_po_lock_contention.py`, `tests/e2e/session-management-*.spec.js` (3 files) | A |
| REQ-KIOSK-001…003 (v1) | not found as a dedicated test file — `kiosk.py` routes appear exercised indirectly via `tests/e2e/mesflow.spec.js` | P |
| REQ-KIOSK-004…010 (v2) | `test_kiosk_v2_bootstrap_environment.py`, `test_kiosk_v2_disabled_identity_rejection.py`, `test_kiosk_v2_heartbeat_liveness.py`, `test_kiosk_v2_p0_device_authorization.py`, `test_kiosk_v2_reset_projection_safety.py`, `test_kiosk_v2_shared_terminal.py`, `test_legacy_kiosk_security_phase10.py`, `test_kiosk_offline_sync.py`, `test_offline_sync_concurrency_blocker6.py`, `test_offline_burst_gate14.py`, `test_offline_trusted_timestamp_phase7.py`, `test_kiosk_rebind_security_blocker2.py`, `test_kiosk_lookup_po_status.py` | A — the single most heavily-tested module in the whole system |
| REQ-SHIFT-* | `test_shift_dashboard.py`, `test_shift_session_lifecycle.py`, `test_scheduling_time_p2.py`, `test_daily_progress_day_state_semantics.py` | A |
| REQ-EXC-* (both systems) | `test_v67_exception_center.py`, `test_session_exception_workflow.py`, `test_session_exception_resolution_modal.py`, `test_session_audit_phase14.py`, `tests/e2e/exception-center-v67.spec.js`, `session-exception-detail-drawer.spec.js` | A |
| REQ-QTY-* | covered inline within REQ-SESS-*'s test files (`_finish_within`/`adjust` are exercised together with quantities) | A (P as a standalone concern — no test file solely about "quantity handling" as a topic) |
| REQ-PROD-* | `tests/integration/test_employee_productivity.py` (14 cases), `test_employee_productivity_wallboard.py` (23 cases), `tests/e2e/employee-productivity-wallboard.spec.js` | A — very strong, this session added to it directly |
| REQ-IO-* | not found as a dedicated pytest file for `excel_io.py`'s validation rules specifically | — SPEC-GAP-011 |
| REQ-SEARCH-* | `tests/e2e/session-management-dependent-filters.spec.js`, `production-schedule-sticky.spec.js` | A (for Session Management/Production Schedule specifically; other list screens' search/filter/pagination not separately verified) |
| REQ-TUT-* | `tests/e2e/tutorial-*.spec.js` (3 files), `tests/test_v6584434…438…439…445…437.py` (5 files) | A |
| REQ-SYS-* | `test_v69_system_health.py`, `test_v69d_phase2_notifications.py`, `test_v69g_phase3_predictive.py`, `test_v73_monitoring_cutover.py`, `test_super_admin_system_console.py` | A |
| REQ-AUDIT-* | `test_v66_session_service.py`, `test_v72_audit_operations_separation.py`, `test_v74_audit_presentation.py`, `tests/e2e/audit-operations-v72.spec.js`, `business-audit-v74.spec.js` | A |
| REQ-API-001…002 (idempotency/locking) | `test_write_path_po_lock_contention.py`, offline-sync tests above | A |
| REQ-API-003…004 (system/version contract) | `test_postgres_schema.py`, `test_migration_matrix_blocker7.py`, `test_deploy_rollback_migration_aware.py`, `test_api_contract.py` | A |
| §7 UI/UX | `tests/e2e/*-visual.spec.js` (catalog, system, ops), `mobile-navigation.spec.js`, `back-navigation.spec.js` | P — visual/breakpoint coverage exists for several screens, not exhaustively for every page in §3 |
| §8 NFR | Concurrency/idempotency: A (see REQ-NFR-001/002 rows above). Security/CSRF, browser support, performance SLA: — (SPEC-GAP-008/009/010) |
| §9 Environment contract | `test_local_8080_login_contract.py`, `test_internal_qa_login_contract.py`, `docs/AUTOLOGIN.md` + its own tests | A |

**Reading this table**: "A" means *a* test exists and was verified passing at some point this session/history — it does not mean every requirement row in this document's tables has its own 1:1 automated assertion. Where this document states a requirement more precisely than any single test file checks (common — many of the richest facts here came from repository docstrings, not test assertions), treat the requirement as **code-verified but not yet test-locked**, and a new test closing that gap is exactly the kind of test case §12 asks QC to generate.

---

## 12. QC test-case generation guidance

### 12.1 Standard test-case format

```
TC-ID:              TC-<MODULE>-<###>
Requirement ID:      REQ-... / BR-... (one or more)
Priority:            P0 (blocks release) / P1 / P2
Preconditions:       exact DB/session state needed before Step 1
Test data:           concrete values (PO code, employee_no, qty, etc.) — never "some PO"
Steps:               numbered, one action per step
Expected result:     one expectation per step, or a final combined expectation
API/UI evidence:     the exact endpoint+method, or the exact selector/screen, this test observes
Cleanup:             how to leave the environment as it was found (see §9.3 for what may/may not be reset)
Automation candidate: Y/N — Y if it's a pure API/state assertion; N if it needs a human judgment call (visual polish, wording)
```

### 12.2 What to generate per requirement

For every `REQ-*` row in §3 and every `BR-*` in §4, generate:
1. **Happy path** — the documented normal case succeeds.
2. **Validation negative** — every field/rule in §6 that applies to this requirement, tried with the invalid value.
3. **Permission negative** — for any role-gated action, at least one role just below the required threshold gets `403`, and (where applicable) the role just above still succeeds.
4. **Boundary** — zero, the exact threshold value (e.g. `rework_qty == defect_qty` should pass, `rework_qty == defect_qty+1` should fail; a session exactly at the 12h/4h exception thresholds).
5. **State-transition** — for anything in §5, both the documented valid transition and at least one documented-invalid one (e.g. finishing an already-`CLOSED` session).
6. **Concurrency/idempotency** — only where §8/BR-016/REQ-API-001/002 say it's relevant (retried request, two supervisors racing one session, a filter request superseded by a faster one) — do not generate this category for requirements with no documented concurrency concern.

### 12.3 Priority guidance

- **P0**: anything in §2 (RBAC boundary), §4 BR-003/006/007/011 (data-integrity rules), §5 (state machine transitions), auto-close (§3.9) — these protect real production data correctness.
- **P1**: the rest of §3's functional requirements, §6 validation.
- **P2**: §7 UI/UX, most of §8 (except concurrency/idempotency, which is P0).

---

## 13. Known gaps / open questions

Numbered `SPEC-GAP-###` (behavior genuinely unclear or unverified) vs `OPEN-QUESTION-###` (a decision that needs a human, not more code-reading).

| ID | Gap | Evidence / why it's open |
|---|---|---|
| SPEC-GAP-001 | `PRODUCT.md` §Capabilities states RBAC covers only "admin, manager và supervisor" — **stale**; the real seed data has 6 roles including `operator`/`viewer`/`super_admin`. This doc's §2 is the corrected version; `PRODUCT.md` itself was not edited this pass (out of scope — a product doc, not a QA doc) but should be flagged to whoever owns it. | `rbac.py` vs `PRODUCT.md:36` |
| SPEC-GAP-002 | Whether every low-privilege-role page consistently *hides* (vs. shows-then-403s) edit controls was not audited page-by-page — §2.3 explicitly says not to trust button-presence as the RBAC signal, API 403 is. A UI-affordance consistency sweep across all pages × all 6 roles is real, undone work. | not attempted this pass |
| SPEC-GAP-003 | Whether a real production PO status transition table exists (e.g. can `PAUSED` go directly to `COMPLETED`? is there a UI-level block beyond the raw PATCH the code allows?) is unverified — §5.3 documents only what the *repository* enforces, not what the *UI* additionally restricts. | `master_data.py:_normalize()` has no stricter transition graph than "member of the enum" |
| SPEC-GAP-004 | `core/working_calendar.py`'s exact shift-resolution algorithm (how `resolve_shift_window_for_datetime()` picks which shift/day a given timestamp belongs to, especially near a cross-midnight boundary) was cited but not read line-by-line this pass — BR-017 is a summary, not a full spec. | file not read in full |
| SPEC-GAP-005 | No "reopen a CLOSED session" code path was found. If this is a real, expected feature, it needs its own requirement + owner confirmation; if not, no action needed — just don't assume QA should test for it. | absence confirmed by search, not a full-repo grep of every string |
| SPEC-GAP-006 | See SPEC-GAP-003 — same underlying gap, restated for the traceability table. | |
| SPEC-GAP-007 | `exception_records.status='AUTO_IGNORED'` — the trigger/condition that auto-ignores an exception (vs. requiring a human `ignore`) was not traced to its source this pass. | `0031_v67_exception_center.py` schema only |
| SPEC-GAP-008 | No CSRF-token mechanism was found in the routes read this pass. This may be an intentional design (SameSite=Lax cookies + same-origin-only frontend), or a real gap — needs a security-focused pass, not a QA-doc guess. | absence confirmed, not a full audit |
| SPEC-GAP-009 | No supported-browser statement exists anywhere in the repo; e2e coverage is Chromium-only via Playwright. | absence confirmed |
| SPEC-GAP-010 | No documented performance/SLA numbers exist. `MESFLOW_ACTION_LOG_SLOW_MS` is an internal logging threshold, not a user-facing target. | `config.py` |
| SPEC-GAP-011 | No dedicated automated test file for `excel_io.py`'s validation rules (§REQ-IO-*) was found — these rules are verified by direct code reading, not by an existing pytest asserting them. | `tests/integration/` file listing, no `test_excel*`/`test_import*` match |
| OPEN-QUESTION-001 | Real public `mesflow.net`'s actual host is, as of 2026-09-04, **unconfirmed and unreachable** from this dev environment (see §9's environment table). Any QA plan that assumes access to real production needs this resolved by a human first — it is not something more code-reading can answer. | `docs/DEPLOY_ARCHITECTURE_A.md` 2026-09-04 follow-up |
| OPEN-QUESTION-002 | `PRODUCT.md` §Positioning explicitly says competitive positioning vs. spreadsheets/other MES tools is "chưa được xác nhận" (unconfirmed, open product decision) — not a QA concern directly, but relevant if QC is ever asked to write comparison-style acceptance criteria. | `PRODUCT.md:22` |
| OPEN-QUESTION-003 | Whether `/opt/mesflow`'s `SERVER_ROLE=DEV` (observed live, inconsistent with `deploy_lib.sh`'s own `PRODUCTION` default for that target) is a real drift bug or an intentional leftover from before that tier's role was formalized was not resolved this pass — flagged, not fixed (out of scope for a QA requirements doc). | live `docker exec ... printenv`, 2026-09-04 |
