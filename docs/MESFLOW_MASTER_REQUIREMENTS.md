# MESFlow — Master Requirements (Self-Contained, Agent-Independent)

Version: `71.0.0.221` · Written: 2026-09-04 · Source of truth for QC test-case generation.

## 0. How to use this document (read this first)

**This document is self-contained.** It is written so that a QC agent or
LLM agent with **zero access to MESFlow's source code, zero access to a
running MESFlow instance, and zero memory of any prior conversation**
can read this file alone and generate a complete, valid set of test
cases for the whole system. Every fact a test case needs — field names,
formulas, error codes, exact state-transition rules, sample data — is
written out in full below, not referenced as "see the code" or
"current behavior." If you find a requirement that still says "see
implementation" or is otherwise not self-sufficient, that is a defect
in this document — flag it, do not guess past it.

**Companion file**: `docs/MESFLOW_QC_AGENT_TESTCASE_INPUT.md` is a short
handoff note for an agent about to generate test cases — read this
document first, that one second.

**Document map**:
- **Part A (§1–§14)**: reference specs — module inventory, RBAC matrix,
  entities, state machines, kiosk workflow, session lifecycle, KPI
  formulas, exception rules, import/export schema, error catalog,
  environment matrix, QC personas/sample data, NFR acceptance criteria,
  known limitations. Read these first — everything else points back to
  them instead of repeating them.
- **Part B (§15)**: functional requirements (`REQ-*`), one block per
  requirement, every field filled in or explicitly marked N/A with a
  one-line reason.
- **Part C (§16)**: business rules (`BR-*`).
- **Part D (§17)**: UI/UX acceptance requirements.
- **Part E (§18)**: end-to-end user journeys.
- **Part F (§19)**: traceability matrix against the existing automated
  test suite.
- **Part G (§20)**: QC test-case generation guidance and the required
  test-case output schema.
- **Part H (§21)**: known gaps / open questions, kept separate from
  normal behavior so they are never mistaken for a spec'd rule.

**Requirement ID stability**: IDs are stable across revisions of this
document — once assigned, an ID is never reused for a different
requirement, even if the requirement is later deprecated (it would be
marked `DEPRECATED` in place, not deleted and reassigned).

---

# PART A — Reference Specs

## 1. Scope & terminology

### 1.1 What MESFlow is

MESFlow is a production-execution and monitoring system for a
mechanical workshop. It tracks work from a released Production Order
down to individual worker sessions on the shop floor, surfaces
exceptions and work-in-progress bottlenecks, and reports employee
productivity. It is a server-rendered web app (Flask/Jinja + vanilla
JS) over PostgreSQL. Primary target viewport: 1366×768 desktop; UI
language is Vietnamese throughout.

### 1.2 Actors and roles

MESFlow has exactly **6 roles** — no others exist. (An earlier product
doc mentions only 3 roles; that doc is stale — this list is the
verified, current one.)

| Role code | Vietnamese name | Typical actor |
|---|---|---|
| `super_admin` | Super Admin / IT | IT/ops staff maintaining the system itself (health, diagnostics, service restarts) |
| `admin` | Quản trị viên | Full business-system administrator |
| `manager` | Quản lý | Production management — configures business data, broadest business-permission role |
| `supervisor` | Quản đốc | Floor supervisor — runs sessions, exceptions, kiosk day-to-day |
| `operator` | Vận hành | Floor worker — view-only in the admin app; the real work happens via Kiosk |
| `viewer` | Chỉ xem | Read-only across most business screens |

There is no "QA Inspector," "Maintenance," or "Kiosk User" role. A
persona named `maintenance` or `kiosk01` in seed data is always one of
the 6 roles above (commonly `operator`) — a username is not a role.

### 1.3 Data hierarchy

```
Sales Order (optional)
  └─ Production Order (PO)
       └─ Part                      (belongs to exactly one PO)
            └─ Operation             (belongs to exactly one Part)
                 └─ Work Session      (one employee's timed work block on one Operation)
                      ├─ QC Inspection (optional)
                      ├─ Operation Adjustment (audit trail of quantity corrections)
                      └─ Quantity Movement rows (GOOD / DEFECT / REPAIRABLE ledger)

Template (Process template) → instantiated into a brand-new PO's Parts+Operations
  (a PO can never be created directly — only by instantiating a Template)

Employee — independent entity, referenced by Work Session
Station / Kiosk device — independent entity, referenced by Work Session
Exception — TWO independent systems, never conflate them:
  - session_exception_reviews  (legacy, Session Management screen)
  - exception_records          ("Exception Center", the primary system)
```

### 1.4 Glossary (every term used elsewhere in this document)

| Term | Definition |
|---|---|
| **PO** | Production Order — one manufacturing run of a `product`, for `planned_quantity` units. |
| **Part** | A sub-assembly/component under one PO; may carry a drawing file (`drawing_path`). |
| **Operation** | One process step under a Part — the unit workers scan/work against at a kiosk. |
| **Work Session** | One employee's timed work block on one Operation. The atomic unit of production data. Has `status` = `OPEN` or `CLOSED` only. |
| **good_qty** | Units produced that passed. Integer, always ≥ 0. |
| **defect_qty** | Units produced that failed. Integer, always ≥ 0. |
| **rework_qty** | Of `defect_qty`, how many are repairable. Integer, always ≥ 0, always ≤ `defect_qty` on the same session. |
| **quantity_confirmed** | Boolean. `TRUE` after any real operator finish or any admin/supervisor correction. `FALSE` only immediately after an auto-close, until a human corrects it. |
| **excluded_from_reports** | Boolean. When `TRUE`, this session's numbers are excluded from every KPI/progress/exception-detection aggregate, but the row itself is never deleted and its `OPEN`/`CLOSED` status is untouched. |
| **Reportable session** | The shared filter every KPI/report/exception query applies: `status = 'CLOSED' AND excluded_from_reports = FALSE`. |
| **Input flow / material flow** | An Operation can be configured to draw its raw-material ceiling from an upstream "source" Operation's own output (GOOD or REWORK kind). See §8 formula and REQ-SESS-004/005. |
| **Auto-close** | The scheduled job that force-closes a Work Session still `OPEN` past its shift's end-time + grace period. Distinct code path from a manual finish — see §6. |
| **Kiosk v1** | Browser-based kiosk UI (`/kiosk`, `/api/kiosk-web/*`). Used for manual/demo browser testing. |
| **Kiosk v2** | The real ESP32 hardware protocol (`/api/kiosk/v2/*`), device-authenticated, event-sourced. What real shop-floor hardware talks to. See §5. |
| **Exception Center** | `exception_records` table — durable, deduplicated-by-fingerprint incident records with severity and a real lifecycle. Primary exception system. |
| **Session Exceptions (legacy)** | `session_exception_reviews` table — an older, simpler per-session review workflow, still live on the Session Management screen. |
| **Persona (test-only)** | `?persona=admin|manager|supervisor|operator|viewer` on the autologin route — a **test facility**, never a production concept. See §11.4. |
| **PII field** | A field holding personal data about a real person (employee identity number, address, phone, etc.) — see §3.6's employee entity for the exact list. |

---

## 2. Module inventory & navigation map

This is the **exact, current sidebar navigation** (source: the app's
own nav-menu definition), with each page's internal `page` id, its
required permission code, and which nav group it sits under. A role
that lacks the listed permission simply does not see that sidebar
entry — it is not shown disabled, it is absent entirely.

| Nav group | Page label (Vietnamese) | `page` id | Required permission | Notes |
|---|---|---|---|---|
| *(top-level)* | Tổng quan sản xuất | `overview` | `overview.view` | Landing page after login |
| *(top-level)* | Dashboard theo ngày | `dashboard` | `dashboard.view` | |
| Kế hoạch | Production Order | `production-orders` | `po.view` | |
| Kế hoạch | Template | `templates` | `template.view` | |
| Điều hành | Quản lý Session | `session-management` | `session.view` | "50 OP gần nhất, xem session, lọc và chỉnh sửa" |
| Điều hành | Trung tâm ngoại lệ | `session-exceptions` | `exceptions.view` | Exception Center |
| Điều hành | Production Trace | `production-trace` | `session.view` | Timeline: PO, Session, quantity, changes |
| Điều hành | Nhật ký nghiệp vụ | `business-audit` | `business_audit.view` | Who changed what/when/why |
| Điều hành | Gantt & Material Flow | `production-schedule` | `material_flow.view` | |
| Điều hành | Trạm kiosk | `kiosk-management` | `kiosk.view` | Device registration/health/logs |
| Điều hành | Báo cáo năng suất nhân viên | `employee-productivity` | `session.view` | KPI: average % completion per employee |
| Điều hành | Nhật ký ứng dụng | `system-logs` | `logs.view` | Action log, API error trace |
| Danh mục | Nhân viên | `employees` | `employees.view` | Employee profiles + QR |
| Danh mục | Danh sách QR Code | `qr-print` | `qr.view` | Filter/select/print QR labels in bulk |
| Danh mục | Thiết bị | `equipment` | `equipment.view` | |
| Quản trị | Người dùng | `users` | `users.view` | Accounts, roles, passwords |
| Quản trị | Lịch làm việc | `working-calendar` | `calendar.view` | Shifts and rest periods |
| Hệ thống *(super_admin only)* | Tổng quan hệ thống | `system-overview` | — (role check only) | App/DB/QA Center/Deploy Agent health |
| Hệ thống *(super_admin only)* | Lỗi hệ thống | `system-errors` | — | HTTP 500s, DB errors, unhealthy services — distinct from session exceptions |
| Hệ thống *(super_admin only)* | Nhật ký | `system-logs-it` | — | MESFlow/DB/QA Center/Deploy Agent logs |
| Hệ thống *(super_admin only)* | Dịch vụ | `system-services` | — | Health + restart, allowlist-gated |
| Hệ thống *(super_admin only)* | Chẩn đoán | `system-diagnostics` | — | DB/migration/QA Center/Deploy Agent checks |
| Hệ thống *(super_admin only)* | Nhật ký quản trị | `system-audit` | — | Who granted Super Admin, restarted services, when |
| *(top-level)* | Hướng dẫn | `tutorials` | — (`login_required` only) | Text guide + video guide, incl. ESP Kiosk sub-tab |

**Access rule (exact, verbatim from the app's own gate function)**:
`canOpenPage(page)` = if `page` is one of the 6 "Hệ thống" pages above,
allowed only when the session role is literally `super_admin`
(**never** satisfied by `admin`); otherwise allowed when the session
has the page's listed permission code, or the page has no permission
requirement at all (`tutorials`).

**Pages that exist but are not in the sidebar** (reached by direct
action, not nav click): PO detail/edit, Template tree editor, Session
detail drawer, Exception detail drawer, User edit modal, Employee
edit/create modal, Working-calendar shift editor. These inherit the
same permission as their parent list page.

**Non-admin-app pages**: `/login` (public), `/kiosk` (Kiosk v1 web UI,
its own auth model — see §5), `/api/kiosk/v2/*` (Kiosk v2, device
token auth, no browser UI of its own).

---

## 3. Role/Permission matrix (detailed)

### 3.1 Full permission catalog

40 permission codes. `module`/`page`/`action` are metadata fields the
Users & Roles screen displays, not separate access checks.

| Code | Module (Vietnamese) | Action | Page id |
|---|---|---|---|
| `overview.view` | Tổng quan | view | overview |
| `dashboard.view` | Dashboard | view | dashboard |
| `po.view` | Production Order | view | production-orders |
| `po.edit` | Production Order | edit | production-orders |
| `template.view` | Template | view | templates |
| `template.edit` | Template | edit | templates |
| `session.view` | Session | view | session-management |
| `session.edit` | Session | edit | session-management |
| `exceptions.view` | Session bất thường | view | session-exceptions |
| `exceptions.resolve` | Session bất thường | edit | session-exceptions |
| `material_flow.view` | Gantt & Material Flow | view | production-schedule |
| `material_flow.edit` | Gantt & Material Flow | edit | production-schedule |
| `kiosk.view` | Trạm kiosk | view | kiosk-management |
| `kiosk.manage` | Trạm kiosk | edit | kiosk-management |
| `ota.view` | ESP Kiosk OTA | view | esp-ota |
| `ota.firmware.manage` | ESP Kiosk OTA | edit | esp-ota |
| `ota.deploy` | ESP Kiosk OTA | deploy | esp-ota |
| `ota.control` | ESP Kiosk OTA | control | esp-ota |
| `ota.approve_stage` | ESP Kiosk OTA | approve | esp-ota |
| `ota.emergency_stop` | ESP Kiosk OTA | emergency | esp-ota |
| `ota.manage_policy` | ESP Kiosk OTA | policy | esp-ota |
| `ota.manage_global_switch` | ESP Kiosk OTA | global | esp-ota |
| `logs.view` | Nhật ký hệ thống | view | system-logs |
| `logs.manage` | Nhật ký hệ thống | edit | system-logs |
| `employees.view` | Nhân viên | view | employees |
| `employees.edit` | Nhân viên | edit | employees |
| `qr.view` | QR Code | view | qr-print |
| `equipment.view` | Thiết bị | view | equipment |
| `equipment.edit` | Thiết bị | edit | equipment |
| `users.view` | Người dùng | view | users |
| `users.manage` | Người dùng | edit | users |
| `roles.manage` | Phân quyền | admin | users |
| `calendar.view` | Lịch làm việc | view | working-calendar |
| `calendar.edit` | Lịch làm việc | edit | working-calendar |
| `business_audit.view` | Nhật ký nghiệp vụ | view | business-audit |
| `operations.view` | Operations Center | view | operations-center |
| `system_logs.view` | Nhật ký hệ thống (kỹ thuật) | view | operations-center |
| `diagnostics.run` | Chẩn đoán | edit | operations-center |
| `deploy.view` | Deploy | view | operations-center |
| `deploy.execute` | Deploy | admin | operations-center |

### 3.2 Grant matrix (role → permissions, exact, current)

`✓` = granted. `admin` and `super_admin` additionally bypass this
table entirely for ordinary business permissions (see §3.3) — the
`admin` column below is what the grant table itself contains, which is
moot because of the bypass, shown here only for completeness/audit
purposes.

| Permission | admin* | manager | supervisor | operator | viewer |
|---|:---:|:---:|:---:|:---:|:---:|
| overview.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| dashboard.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| po.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| po.edit | ✓ | ✓ | | | |
| template.view | ✓ | ✓ | | | ✓ |
| template.edit | ✓ | ✓ | | | |
| session.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| session.edit | ✓ | ✓ | ✓ | | |
| exceptions.view | ✓ | ✓ | ✓ | | ✓ |
| exceptions.resolve | ✓ | ✓ | ✓ | | |
| material_flow.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| material_flow.edit | ✓ | ✓ | ✓ | | |
| kiosk.view | ✓ | ✓ | ✓ | ✓ | |
| kiosk.manage | ✓ | ✓ | ✓ | | |
| ota.view | ✓ | ✓ | ✓ | | |
| ota.firmware.manage | ✓ | ✓ | | | |
| ota.deploy | ✓ | ✓ | | | |
| ota.control | ✓ | ✓ | | | |
| ota.approve_stage | ✓ | ✓ | | | |
| ota.emergency_stop | ✓ | | | | |
| ota.manage_policy | ✓ | ✓ | | | |
| ota.manage_global_switch | ✓ | | | | |
| logs.view | ✓ | ✓ | | | |
| logs.manage | ✓ | | | | |
| employees.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| employees.edit | ✓ | ✓ | | | |
| qr.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| equipment.view | ✓ | ✓ | ✓ | | ✓ |
| equipment.edit | ✓ | ✓ | | | |
| users.view | ✓ | | | | |
| users.manage | ✓ | | | | |
| roles.manage | ✓ | | | | |
| calendar.view | ✓ | ✓ | ✓ | | ✓ |
| calendar.edit | ✓ | ✓ | | | |
| business_audit.view | | ✓ | ✓ | | |
| operations.view | | ✓ | | | |
| system_logs.view | | ✓ | | | |
| deploy.view | | ✓ | | | |

*`admin`'s column above is the raw grant table; §3.3 explains why it's
irrelevant to actual behavior.

### 3.3 Enforcement rules (exact, no ambiguity)

1. **`admin` bypass**: `role == 'admin'` (or `super_admin`, for
   ordinary business permissions) → every permission check returns
   `True` immediately, regardless of what §3.2's table says.
   Consequence: editing `admin`'s row via `PUT /api/roles/admin/permissions`
   is accepted by the API but has **no effect** — the server silently
   re-forces `admin`'s grant set back to "every permission" on that
   same call.
2. **`super_admin` and the System Console**: the 6 "Hệ thống" pages
   (§2) and their APIs (`GET/POST /api/system-health/*`) check the
   **literal session role string** — satisfied only by `super_admin`,
   **never** by `admin`, even though `admin` has the business-permission
   bypass above. An `admin` session hitting a System Console API gets
   `403 FORBIDDEN`.
3. **Fail-closed**: if the permission lookup itself errors (e.g. RBAC
   metadata table unreachable), the check returns `False` (deny), never
   `True`.
4. **Standard missing-permission response** (any role, any gated
   route): `HTTP 403`, body
   `{"ok": false, "error": "FORBIDDEN", "permission": "<code>", "message": "Bạn không có quyền thực hiện thao tác này"}`.
5. **No session at all**: `HTTP 401`, `{"ok": false, "error": "AUTH_REQUIRED"}`.
6. **Expired session**: `HTTP 401`,
   `{"ok": false, "error": "SESSION_EXPIRED", "reason": "<idle|absolute>", "message": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."}`.

### 3.4 Known, deliberate exceptions to the generic per-prefix rule

A handful of specific routes are intentionally **narrower** or
**wider** than the generic permission §3.1's table would suggest for
their URL prefix. These are real, confirmed, current behavior — test
each one explicitly, they are exactly the kind of thing a naive
prefix-based test would get wrong:

| Route | Generic rule would say | Actual rule |
|---|---|---|
| `DELETE /api/production-orders/<id>/force` | `po.edit` (admin+manager) | **admin only** |
| `POST /api/production-orders/<id>/start` | `po.edit` (admin+manager) | **admin + manager + supervisor** |
| `POST /api/templates/demo/seed`, `DELETE /api/templates/demo` | `template.edit` (admin+manager) | **admin only** |
| `GET /api/templates/<id>/export-workbook` | `template.view`-restricted | **admin + manager + viewer** (read-only, widened) |

### 3.5 Session/authentication timing rules

| Rule | Value |
|---|---|
| Idle session timeout | 60 minutes of inactivity (configurable, default 60) |
| Absolute session ceiling | 12 hours from login, regardless of activity (configurable, default 12) |
| Kiosk-mode idle timeout | 15 minutes (shorter than a normal office login, shared-terminal risk) |

---

## 4. Domain entities — field definitions and relationships

Types are PostgreSQL types as actually declared. `NN` = NOT NULL.
`FK→X` = foreign key to table X. `def` = default value if omitted.

### 4.1 `production_orders` (PO)

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| code | text | NN, unique |
| sales_order_id | bigint | FK→sales_orders, nullable, ON DELETE SET NULL |
| product | text | NN |
| planned_quantity | int | NN, def 0, **must be > 0 on create** |
| status | text | NN, def `PLANNED`, enum: `DRAFT, PLANNED, RELEASED, IN_PROGRESS, PAUSED, COMPLETED, CANCELLED` |
| priority | text | NN, def `NORMAL`, enum: `LOW, NORMAL, HIGH, URGENT` |
| due_date | date | nullable |
| planned_start_at / planned_end_at | timestamptz | nullable; if both set, end must be strictly after start |
| notes | text | NN, def `''` |
| created_at / updated_at | timestamptz | NN |

Relationships: has many `parts`, has many `operations` (denormalized
FK, also reachable via part), optionally belongs to one `sales_order`.

### 4.2 `parts`

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| production_order_id | bigint | NN, FK→production_orders, ON DELETE CASCADE |
| code | text | NN, unique **within the same PO** (`UNIQUE(production_order_id, code)`) |
| name | text | NN |
| drawing_path | text | NN, def `''` |
| sort_order | int | NN, def 0 |
| active | bool | NN, def true |
| created_at / updated_at | timestamptz | NN |

### 4.3 `operations`

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| production_order_id | bigint | NN, FK→production_orders, CASCADE |
| part_id | bigint | NN, FK→parts, CASCADE |
| equipment_id | bigint | FK→equipment, nullable, ON DELETE SET NULL |
| code | text | NN, **globally unique** (not just within PO) |
| name | text | NN |
| plan_qty | int | NN, def 0 |
| done_qty | int | NN, def 0 — **computed, not directly writable by users** (see §5.2) |
| defect_qty | int | NN, def 0 — computed |
| rework_qty | int | NN, def 0 — computed (added by migration `0022_rework_flow`) |
| status | text | NN, def `PLANNED` — computed, see state machine §6.2 |
| sort_order | int | NN, def 0 |
| qr | text | NN, unique |
| standard_seconds_per_unit | numeric(12,3) | NN, def 0 — used in the productivity formula, §8 |
| repair_cycle_time_seconds_per_unit | numeric(12,3) | NN, def 0 |
| predecessor_operation_id | bigint | nullable — pure time/order dependency, see §4.9 |
| dependency_type | text | NN, def `FS` (Finish-to-Start) |
| lag_minutes | int | NN, def 0 |
| planned_start_at / planned_end_at | timestamptz | nullable |
| input_flow_enabled | bool | NN, def false |
| input_source_operation_id | bigint | nullable — the upstream Operation this one draws material from |
| input_source_kind | text | NN, def `GOOD`, enum `GOOD, REWORK` — which of the source's outputs is drawn |
| defects_consume_input | bool | NN, def true |
| created_at / updated_at | timestamptz | NN |

### 4.4 `work_sessions`

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| employee_id | bigint | NN, FK→employees, ON DELETE RESTRICT |
| operation_id | bigint | NN, FK→operations, ON DELETE RESTRICT |
| station_id | bigint | FK→stations, nullable, ON DELETE SET NULL |
| device_uuid | text | NN, def `''` |
| status | text | NN, def `OPEN`, enum: `OPEN, CLOSED` only — **no other value ever exists** |
| started_at | timestamptz | NN, def now |
| ended_at | timestamptz | nullable (set on close) |
| good_qty / defect_qty | int | NN, def 0, always clamped ≥ 0 on write |
| rework_qty | int | NN, def 0, always ≤ defect_qty on the same row |
| note | text | NN, def `''` |
| start_request_id | text | NN, **unique** — idempotency key for the start call |
| finish_request_id | text | unique, nullable — idempotency key for the finish call |
| close_reason | text | NN, def `''` — `'AUTO_SHIFT_END'` when auto-closed, empty for a manual finish |
| closed_by_system | bool | NN, def false — `TRUE` only for auto-close |
| shift_boundary_used_at | timestamptz | nullable — the shift-end timestamp used, if auto-closed |
| started_at_trusted / ended_at_trusted | bool | NN, def false — whether the timestamp came from a verified offline-device clock |
| quantity_confirmed | bool | NN, def **true** — see §1.4/§6.4 |
| excluded_from_reports | bool | NN, def false |
| exclusion_reason | text | NN, def `''` |
| excluded_by | text | NN, def `''` |
| excluded_at | timestamptz | nullable |
| created_at / updated_at | timestamptz | NN |

**DB-enforced constraint**: `CREATE UNIQUE INDEX ON work_sessions(employee_id) WHERE status='OPEN'`
— an employee can have **at most one `OPEN` session at any time**,
enforced at the database level, not just application logic.

### 4.5 `employees`

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| employee_no | text | NN, unique, **uppercased on every write** |
| name | text | NN |
| department | text | NN, def `''` |
| position | text | NN, def `''` |
| employment_status | text | NN, def `'Đang làm'` (free text, but the literal string `'Đã nghỉ'` is the one sentinel value that flips `active`) |
| active | bool | NN, def true — **computed**: `active = (employment_status != 'Đã nghỉ')`, not independently settable |
| qr | text | NN, unique |
| birth_date, identity_issue_date, start_date, end_date | date | nullable — empty string on write is coerced to `NULL` |
| hometown, phone, identity_number, current_address, contract_1, contract_2 | text | NN, def `''` — PII fields |
| created_at / updated_at | timestamptz | NN |

### 4.6 `stations`

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| code | text | NN, unique |
| name | text | NN |
| workshop, production_line | text | NN, def `''` |
| active | bool | NN, def true |

### 4.7 `users`

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| username | text | NN, unique |
| display_name | text | NN |
| password_hash | text | NN — never returned by any API |
| role | text | NN — one of the 6 codes in §1.2 |
| active | bool | NN, def true |
| must_change_password | bool | NN, def false |
| created_at / updated_at | timestamptz | NN |

### 4.8 `exception_records` (Exception Center)

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| exception_type | text | NN — one of the 7 types in §9.1 |
| severity | text | NN, enum `CRITICAL, HIGH, MEDIUM, LOW` |
| status | text | NN, def `OPEN`, enum `OPEN, ACKNOWLEDGED, RESOLVED, AUTO_IGNORED, MANUAL_IGNORED` |
| entity_type, entity_id | text/bigint | NN — what triggered it |
| employee_id, production_order_id, part_id, operation_id, session_id | bigint | nullable FKs, `ON DELETE SET NULL` |
| title, message, recommended_action | text | NN |
| fingerprint | text | NN — see BR-015 for uniqueness rule |
| metadata_json | jsonb | NN, def `{}` |
| condition_active | bool | NN, def true |
| occurrence_no | int | NN, def 1, > 0 |
| row_version | int | NN, def 1, > 0 — optimistic-concurrency version |
| detected_at | timestamptz | NN |
| acknowledged_at, resolved_at, ignored_at | timestamptz | nullable |
| acknowledged_by, resolved_by | bigint | FK→users, nullable |
| auto_ignore_reason, auto_ignored_at | text/timestamptz | nullable |

**DB-enforced constraint**: `CREATE UNIQUE INDEX ON exception_records(fingerprint) WHERE status IN ('OPEN','ACKNOWLEDGED')`
— at most one **active** record per fingerprint; a resolved/ignored
condition recurring creates a new record (new occurrence), never
revives the old one.

### 4.9 `session_exception_reviews` (legacy Session Exceptions)

| Field | Type | Constraints |
|---|---|---|
| id | bigint | PK |
| session_id | bigint | NN, FK→work_sessions, CASCADE |
| exception_code | text(40) | NN |
| exception_fingerprint | text(120) | NN |
| workflow_status | text(20) | NN, def `NEW`, enum `NEW, IN_PROGRESS, RESOLVED, IGNORED` |
| resolution | text(40) | NN, def `''` |
| note | text | NN, def `''` |
| assigned_to, started_by, resolved_by | text(120) | NN, def `''` |
| started_at, resolved_at | timestamptz | nullable |

Unique on `(session_id, exception_fingerprint)`.

### 4.10 Other supporting tables (fields only where relevant to test data)

- **`qc_inspections`**: `session_id` (FK), `operation_id` (FK),
  `inspector_user_id` (FK→users), `status` (`OPEN`/`COMPLETED`),
  `good_qty`, `defect_qty`, `defect_reason`.
- **`operation_adjustments`**: `session_id`, `operation_id`,
  `old_good_qty`/`new_good_qty`, `old_defect_qty`/`new_defect_qty`,
  `old_rework_qty`/`new_rework_qty`, `reason` (NN), `adjusted_by` (FK→users).
- **`penalty_tickets`**: `employee_id`, `operation_id` (nullable),
  `session_id` (nullable), `points`, `reason`, `status`, `issued_by`.
- **`templates` / `template_parts` / `template_operations`**: mirror
  `production_orders`/`parts`/`operations` shape minus the runtime
  fields (`done_qty` etc.), plus `templates.version` (text, def `'1.0'`)
  and `templates.source_workbook`.
- **`work_shifts`**: `code` (unique), `name`, `timezone` (def
  `Asia/Ho_Chi_Minh`), `anchor_start`/`anchor_end` (time),
  `cross_midnight` (bool), `target_minutes` (int, def 480),
  `working_weekdays` (smallint array, 0=Monday..6=Sunday, def
  `[0,1,2,3,4,5]`), `active` (bool).
- **`work_shift_intervals`**: `shift_id` (FK), `interval_type`
  (`WORK`/`BREAK`), `start_minute`/`end_minute` (int, shift-relative
  minutes, `end > start` enforced by CHECK constraint), `label`.
- **`kiosk_identities`**: `device_uuid` (unique), `device_name`,
  `station_id` (FK, nullable), `status` (def `PENDING`), `token_hash`,
  `firmware_version`, `last_ip`, `last_seen_at`.

---

## 5. State machines

### 5.1 Work Session

```
                    start()
                      │
                      ▼
                   [OPEN]  ─────────────────┐
                      │                     │
       finish()       │      auto-close (system job,
   (real operator      │      shift end + grace, only
    action)            │      if still OPEN)
                      ▼                     ▼
                  [CLOSED]              [CLOSED]
           close_reason=''         close_reason='AUTO_SHIFT_END'
           closed_by_system=FALSE  closed_by_system=TRUE
           quantity_confirmed=TRUE quantity_confirmed=FALSE
```

There is **no transition back from `CLOSED` to `OPEN`** anywhere in the
system — no "reopen" action exists. If a test plan calls for reopening
a closed session, that is testing a feature that does not exist (flag
as a gap, do not assume it should work).

Two independent boolean flags layered on top of `status`, changed by
separate actions, not additional states:
- `quantity_confirmed`: set `FALSE` only by auto-close; set back `TRUE`
  by any supervisor/admin correction (`adjust()` or `edit_session()`).
- `excluded_from_reports`: set `TRUE`/`FALSE` by explicit
  exclude/restore actions, each requiring a non-empty reason; never
  changes `status`.

### 5.2 Operation status (fully computed — recalculated after every
relevant session change; only `CANCELLED` is set by a direct user action)

Evaluated in this exact order, first match wins:

| # | Condition | Resulting status |
|---|---|---|
| 1 | current status is already `CANCELLED` | `CANCELLED` (sticky forever) |
| 2 | any session on this Operation is currently `OPEN` | `IN_PROGRESS` |
| 3 | current status is `COMPLETED` and there are zero reportable sessions left | `COMPLETED` (stays even if all history got excluded) |
| 4 | `plan_qty > 0` and `good_qty ≥ plan_qty` | `COMPLETED` |
| 5 | current status is `PAUSED` | `PAUSED` (sticky — survives ordinary reconcile churn from unrelated activity elsewhere on the same PO) |
| 6 | at least one reportable session exists | `IN_PROGRESS` |
| 7 | current status is one of `DRAFT, PLANNED, RELEASED, READY` | unchanged |
| 8 | *(fallback, none of the above)* | `PLANNED` |

Explicit user action: `POST /operations/<id>/cancel` → `CANCELLED`.
Refused (`409`) if the Operation is already `COMPLETED` (must use a
separate rework flow instead) or has any `OPEN` session (must close it
first).

### 5.3 Production Order status

Enum: `DRAFT, PLANNED, RELEASED, IN_PROGRESS, PAUSED, COMPLETED, CANCELLED`.

The **only** code-enforced transition is **Start**:
`POST /production-orders/<id>/start`
- Requires the PO to have ≥ 1 Operation (else `409`, "PO chưa có
  Operation. Hãy thêm Operation trước khi Start.").
- Refused if current status is `COMPLETED` or `CANCELLED` ("PO đã
  hoàn thành hoặc đã hủy nên không thể Start").
- **Idempotent**: if already `IN_PROGRESS`, returns success with
  `already_started: true` (not an error).
- On success: status → `IN_PROGRESS`.

Every other status change goes through a generic PATCH with only
enum-membership validated — there is **no** further code-enforced
transition graph (e.g. a direct `PLANNED → COMPLETED` PATCH is not
blocked by the code). Treat any stricter transition rule as
unconfirmed (see §21 gaps) unless testing proves otherwise.

### 5.4 Exception Center record (`exception_records`)

```
   new fingerprint detected (no active record for it) → [OPEN]
                                │
              ┌─────────────────┼─────────────────┐
         acknowledge()      resolve()          ignore()
              │                 │                  │
              ▼                 ▼                  ▼
       [ACKNOWLEDGED]      [RESOLVED]        [MANUAL_IGNORED]
              │
     ┌────────┴────────┐
  resolve()          ignore()
     │                  │
     ▼                  ▼
 [RESOLVED]      [MANUAL_IGNORED]
```

Only `OPEN`/`ACKNOWLEDGED` are "active." `[AUTO_IGNORED]` is a
system-set terminal state (trigger not fully documented — see §21
gap). Every transition requires the caller to pass the record's
current `row_version` (`expected_version`) — a stale/mismatched
version is refused, not silently applied.

### 5.5 Session Exception (legacy, `session_exception_reviews`)

`NEW → IN_PROGRESS → RESOLVED`, or `→ IGNORED` from either `NEW` or
`IN_PROGRESS` (simple 4-value enum via CHECK constraint; no further
code-enforced ordering confirmed beyond the constraint itself).

---

## 6. Session lifecycle — full detail

### 6.1 Start

`POST /work-sessions/start` (web) or the Kiosk v2 `OP` scan event
(§7). Input: `employee_id`, `operation_id`, `station_id` (optional),
`device_uuid` (optional), `request_id` (required, idempotency key),
`occurred_at` (optional, trusted offline timestamp).

Preconditions checked, in order:
1. Employee exists and `active = TRUE` (else `RepositoryError`, "employee inactive or missing").
2. PO of the target Operation is `IN_PROGRESS` (else `409`, "PO {code} chưa Start hoặc đang tạm dừng").
3. If `input_flow_enabled` on the Operation: the upstream source
   Operation must have **at least one session ever started** — not
   necessarily finished (else `409`, "OP nguồn {code} chưa bắt đầu
   session. Phải start session OP nguồn trước khi start {code}.").
4. If a pure time/order predecessor exists (and is not also the input
   source): the predecessor Operation must simply exist (checked, but
   completion is not required by this specific check).
5. Dispatch readiness check (WIP-based) — if not actionable, `409`
   naming the reason and current WIP quantity.
6. The employee must have **no other currently `OPEN` session**
   (DB-enforced unique index) — else `409`, "employee already has an
   open session."
7. No overlapping time window with any other session for the same
   employee.

On success: new `work_sessions` row, `status=OPEN`. Operation status
recomputes per §5.2. An audit row (`SESSION_STARTED`) and a domain
event are written in the same transaction.

Retrying the exact same `request_id` returns the **original** response
unchanged (`idempotent_replay: true`), never creates a second session.

### 6.2 Finish

`POST /work-sessions/<id>/finish`. Input: `request_id` (required),
`good_qty`, `defect_qty`, `rework_qty` (all optional, default 0),
`note` (optional), `occurred_at` (optional).

Validation:
- `good_qty`, `defect_qty`, `rework_qty` are clamped to ≥ 0 (a
  negative input is silently floored to 0, never rejected as an
  error).
- `rework_qty > defect_qty` → `ValueError` ("rework_qty cannot exceed
  defect_qty").
- Session must currently be `OPEN` (else `409`, "session already
  closed").
- Material/input-flow availability check — see §8's formula; violation
  → `409` naming the exact quantity still available.
- No overlapping time window for the same employee (same check as
  start).

On success: `status → CLOSED`, `quantity_confirmed → TRUE`,
`close_reason` stays `''`, `closed_by_system` stays `FALSE`. One or
more `quantity_movements` rows written (`GOOD`/`DEFECT`/`REPAIRABLE`).
Operation status recomputes. Audit row `SESSION_FINISHED` + domain
event(s) written in the same transaction.

A `good=0, defect=0` finish after the session was open > 4 hours is
**not an error** — it is allowed, and separately flagged by the
Exception Center (`ZERO_QUANTITY_LONG`, §9.1).

### 6.3 Batch finish

`POST /session/group/finish` — an array of `(session_id, data)` pairs.
**True atomic batch**: one shared DB transaction across the whole
array — the first item that fails rolls back every item, never a
partial commit with some sessions closed and others not.

### 6.4 Auto-close

Runs on a scheduled job (`shift_session_reconciliation`), only for a
session still `OPEN` past its shift's end time + a configurable grace
period (default: see §11 environment matrix for the exact env vars).

- Rollout-safety defaults: `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=0`,
  `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=1` — a fresh deployment's cron
  installs but does **not** actually close real sessions until both
  are explicitly flipped.
- Keeps whatever `good_qty`/`defect_qty`/`rework_qty` the session
  already had — never fabricates a number.
- Sets `close_reason='AUTO_SHIFT_END'`, `closed_by_system=TRUE`,
  `shift_boundary_used_at`, `quantity_confirmed=FALSE`.
- Fires domain event `SESSION_AUTO_CLOSED` (a **different** event type
  from `SESSION_FINISHED` — never disguised as a manual finish).
- Idempotent + concurrency-safe: a per-session advisory lock
  serializes concurrent runs; if the session is no longer `OPEN` by
  the time the lock is acquired (already manually finished, or already
  auto-closed by a faster concurrent run), the call is a documented
  no-op, not an error.
- Same overlap and input-flow-ledger checks as a manual finish apply.

### 6.5 Correction (supervisor/admin quantity adjust)

`POST /supervisor/sessions/<id>/adjust`. Roles: admin, manager,
supervisor. Requires non-empty `reason` (else `ValueError`, "reason
required"). Works on both `OPEN` and `CLOSED` sessions. Always sets
`quantity_confirmed = TRUE` regardless of its prior value — a human
correction **is** the confirmation. Writes an `operation_adjustments`
audit row (old/new for good/defect/rework) and a `VALUE_CHANGED`
domain event. Same `rework ≤ defect` rule as finish.

### 6.6 Full edit

`PATCH /supervisor/sessions/<id>`. Roles: admin, manager, supervisor.
Supports optimistic concurrency: caller may pass `expected_updated_at`
— a stale value (someone else edited it first) is refused, never
silently overwritten.

### 6.7 Transfer Operation ("giao nhầm Operation")

`POST /supervisor/sessions/<id>/transfer-operation`. Roles: admin,
manager, supervisor. Reassigns a session's `operation_id`. Audited
with the before/after Operation captured. Both the old and new
Operation's status/progress recompute (§5.2).

### 6.8 Exclude / restore ("Loại khỏi báo cáo")

`POST /supervisor/sessions/<id>/exclude` and `.../restore`. Roles:
admin, manager, supervisor. Both require a non-empty `reason`. Exclude
is refused if already excluded (`409`, "Session đã được loại khỏi báo
cáo"); restore is refused if not currently excluded (`409`, "Session
hiện không bị loại khỏi báo cáo"). Neither ever deletes the row or
changes `status`. Each writes its own domain event
(`SESSION_EXCLUDED` / `SESSION_RESTORED`).

---

## 7. Kiosk workflow — end-to-end, every branch

### 7.1 Kiosk v1 (browser-based, `/kiosk`, `/api/kiosk-web/*`)

No device-token auth — a lighter, browser-facing flow intended for
demo/manual testing on any browser that can reach the app.

| Step | Endpoint | Input | Success | Failure |
|---|---|---|---|---|
| 1. Scan | `POST /api/kiosk-web/scan` | `{qr}` | Resolves employee or operation by QR | Empty `qr` → `400 QR_REQUIRED`, `error_code: SCN-001`, message "Chưa nhận được mã quét", `action` hint "Kiểm tra nguồn và dây máy quét, rồi quét lại." |
| 2. Start | `POST /api/kiosk-web/start` | employee+operation resolved | Same rules as §6.1 | Same errors as §6.1 |
| 3. Finish | `POST /api/kiosk-web/finish/<session_id>` | quantities | Same rules as §6.2 | Same errors as §6.2 |

### 7.2 Kiosk v2 (ESP32 hardware protocol, `/api/kiosk/v2/*`)

Device-authenticated (per-device token), event-sourced: each device
has one server-side "projection" row tracking its own short-lived UI
state, entirely separate from the durable `work_sessions` server
state.

**QR wire format**: `WF|EMP|<key>` or `WF|OP|<key>`. Anything else
fails to parse (`kind=None`) and is rejected.

**Device states**: `WAIT_EMPLOYEE`, `WAIT_OPERATION`, `QUANTITY_INPUT`,
`SESSION_ACTIVE` (legacy-reachable only, not part of the normal flow),
`DEVICE_DISABLED`, `MAINTENANCE`.

**Full transition table**:

| Current state | Event | Result | Notes |
|---|---|---|---|
| `WAIT_EMPLOYEE` | `SCAN` (kind=EMP), employee has no open session | → `WAIT_OPERATION` | Employee identity + name stored in the projection |
| `WAIT_EMPLOYEE` | `SCAN` (kind=EMP), employee **has** an open session | → `QUANTITY_INPUT` | Direct — the device goes straight to quantity entry for the already-open session, no intermediate confirmation screen |
| `WAIT_EMPLOYEE` | `SCAN` (kind=OP) | rejected | `STATE_INVALID_TRANSITION`, "Cần quét thẻ nhân viên" |
| `WAIT_EMPLOYEE`/`WAIT_OPERATION`/any | `SCAN`, unparseable QR (kind=None) | rejected | `STATE_INVALID_TRANSITION`, "Không thể quét mã ở trạng thái này" |
| `WAIT_OPERATION` | `SCAN` (kind=OP), PO of that Operation is `IN_PROGRESS` | → `WAIT_EMPLOYEE` | A real Work Session is created server-side (§6.1 rules apply in full); the **device** immediately resets to `WAIT_EMPLOYEE` so the next worker can use it right away — the session itself stays `OPEN` server-side regardless of device state |
| `WAIT_OPERATION` | `SCAN` (kind=OP), PO **not** `IN_PROGRESS` | rejected | `OPERATION_NOT_WORKABLE`, names the PO code |
| `WAIT_OPERATION` | `SCAN` (kind=EMP) | rejected | `STATE_INVALID_TRANSITION`, "Cần quét mã công đoạn" |
| any | `FINISH_REQUESTED` | → quantity-entry flow | |
| any | `QUANTITY_SUBMITTED` | session finishes (§6.2 rules) | |
| any | `CANCEL_REQUESTED` | resets to `WAIT_EMPLOYEE` | |
| `DEVICE_DISABLED` / `MAINTENANCE` | **any** event | rejected | `DEVICE_NOT_ALLOWED`, "Thiết bị chưa được phép" — hard block regardless of event type |

**Idempotency**: every event is keyed by `(device_id, event_id)` — a
retried/duplicated event (e.g. offline device replaying a queued
event) does not double-apply.

**Offline behavior**: a device with `time_quality='synced'` can submit
a trusted `occurred_at`; the server only honors it if it does not
produce an impossible session (e.g. a trusted `ended_at` at or before
`started_at` falls back to server time instead of writing a
negative-duration session).

---

## 8. Productivity/KPI formulas — exact math

**Scope of the report**: `GET /reports/employee-productivity` and its
detail (`/{employee_id}`) and the public Kiosk wallboard
(`/api/wallboard/employee-productivity`) all read the **same**
underlying query — they must never diverge.

**Population filter**: `work_sessions.status = 'CLOSED' AND ended_at IS NOT NULL AND excluded_from_reports = FALSE`.
**Never** includes `OPEN` sessions or any realtime "who's working now"
state — confirmed: the response never contains a running-session
count or active-worker field of any kind.

**Date filter**: on `ended_at` (business date, site timezone —
`Asia/Ho_Chi_Minh` by default), **not** `started_at`. A session that
starts one calendar day and ends the next is filed under the day it
**ended**.

**Per-session completion percent**:
```
expected_seconds = operations.standard_seconds_per_unit × (good_qty + defect_qty)
actual_seconds   = EXTRACT(EPOCH FROM (ended_at − started_at))
completion_percent = expected_seconds / actual_seconds × 100
```
- If `standard_seconds_per_unit = 0` (not configured) or
  `actual_seconds = 0`: `completion_percent = NULL` — **never** `0`.
  The UI renders this as "Không đủ dữ liệu" (not enough data), not a
  0% score.
- **No upper clamp** — a session finished faster than standard time can
  legitimately show > 100% (e.g. 120%), and that value is included as-is
  in every downstream average.

**Per-employee productivity_percent** (shown as their row score):
`AVG(completion_percent)` over that employee's own sessions in range,
where `completion_percent IS NOT NULL` (sessions with `NULL`
completion are counted separately as `completed_invalid_sessions`, not
averaged in, not treated as 0).

**Cross-employee summary average** (`avg_employee_productivity_percent`):
the average **of each employee's own already-computed
productivity_percent** — i.e. every employee counts equally regardless
of how many sessions they had. This is **not** a session-weighted
global average.

**Employee with zero valid sessions in range**: does not appear in the
report **at all** — never shown as a `0%` row. An employee whose only
session(s) in range are still `OPEN` is likewise entirely invisible to
this report (population filter excludes `OPEN` outright).

**Summary totals**: `total_good_qty` and `total_defect_qty` are the
plain sum of `good_qty`/`defect_qty` across every employee row already
computed for the report (fixed 2026-09-04 — previously these two
fields were always `0` due to a real shipped bug; now correct).

**Wallboard-specific**: supports fixed date-range or dynamic
month-to-date, department filter, configurable sort/page
size/auto-flip interval; a "Preview"-style call must never mutate the
already-published wallboard config; returns the **full** filtered list
(client does its own paging, not server-side pagination).

---

## 9. Exception rules

### 9.1 Exception Center — the 7 detection conditions

Each row below is evaluated continuously (on reconciliation), and
**excludes** any session with `excluded_from_reports = TRUE` from
ever triggering (fixed 2026-08-28 — this exclusion did not originally
apply and produced false-positive noise for sessions a supervisor had
already written off).

| exception_type | severity | Trigger condition | Recommended action (shown to user) |
|---|---|---|---|
| `LONG_OPEN_SESSION` | HIGH | Session `status='OPEN'` and `started_at` more than 12 hours ago | "Kiểm tra Session và xác nhận trạng thái." |
| `ZERO_QUANTITY_LONG` | MEDIUM | Session `status='CLOSED'`, duration > 4 hours, and `good_qty + defect_qty = 0` | "Đối chiếu sản lượng và xác nhận hoặc sửa Session." |
| `MISSING_STATION` | LOW | `station_id IS NULL` and `device_uuid = ''` | "Xác nhận nguồn thao tác của Session." |
| `INVALID_DURATION` | CRITICAL | `ended_at IS NOT NULL AND ended_at < started_at` | "Mở Session, kiểm tra bằng chứng và sửa qua quy trình hiện có." |
| `OPERATION_COMPLETED_SESSION_OPEN` | HIGH | Session `status='OPEN'` while its Operation's `status='COMPLETED'` | "Kiểm tra Session trước khi xác nhận trạng thái Operation." |
| `EMPLOYEE_SESSION_CONFLICT` | CRITICAL | Two sessions for the same employee with overlapping time ranges | "Kiểm tra cả hai Session và bằng chứng kiosk." |
| `SESSION_PAST_SHIFT_END` | MEDIUM | Session `status='OPEN'`, its `started_at` resolves to a shift whose end-time + grace period has already passed, and the shift boundary applies (a session starting during a gap with no active shift is skipped here — still covered by `LONG_OPEN_SESSION` if it runs past 12h) | "Kết thúc Session thủ công, hoặc chờ hệ thống tự động đóng ca." |

Each generated record's `fingerprint = "<exception_type>:SESSION:<session_id>"`.

### 9.2 Legacy Session Exceptions (`session_exception_reviews`)

Populated separately for the older Session Management screen. Same
population filter applies (`excluded_from_reports=FALSE`). Lifecycle:
§5.5. Codes/fingerprints are session-scoped, not the same values as
§9.1's `exception_type` list (do not conflate the two systems' codes).

---

## 10. Import/export schema and validation

Excel workbook import/export for Templates and Operations
(`GET /export.xlsx`, `POST /import`, per-template
`export-workbook`/`import`). Roles: admin + manager (export-workbook
additionally readable by viewer).

**Operation row requirements** (row-level, "Sheet Operations"):
- Every row needs either `operation_id`, **or** the full context
  (PO code + Part + Operation name) — missing either → row-numbered
  error: `"Dòng {N}: thiếu ..."` naming exactly which field.
- `done_qty`, `defect_qty`, `status` are **rejected outright** if
  present with a value that would change them — these are
  production-derived, never importable:
  `"Dòng {N}: done, defect và status là dữ liệu production tự tính; hãy sửa Session nguồn rồi reconcile."`
- Duplicate `operation_id` within the same file → rejected:
  `"Dòng {N}: trùng operation_id {code}."`
- If the target PO's `planned_quantity` already differs from the
  file's value → rejected outright (not silently overwritten):
  `"PO {code} có số lượng kế hoạch {current}, nhưng file có {file_value}"`.
- Moving an Operation to a different PO/Part via Excel is refused once
  that Operation has any input-consumption ledger row:
  `"Operation {code} đã có Ledger nên không thể chuyển PO/Part bằng Excel."`

**Full-workbook template import** (`Parts` + `Operations` sheets):
- `Parts` sheet must not be empty (`"Sheet Parts chưa có dữ liệu."`);
  every Part row needs both a code and a name.
- Every Operation row's Part reference must exist in the `Parts`
  sheet — cross-sheet referential validation, not per-sheet in
  isolation (`"Operations dòng {N}: Part {code} không tồn tại."`).
- Every Operation row needs a name (`"Operations dòng {N}: thiếu tên
  Operation."`).

**Template tree replace** (`PUT /templates/<id>/tree`): refused once
that template's instantiated Operations have any Session or
input-consumption Ledger — must use Merge instead, or create a new PO.

---

## 11. Error catalog / standard error behavior

### 11.1 Standard HTTP status → meaning (applies system-wide)

| Status | Meaning | Body shape |
|---|---|---|
| 200 | Success | `{"ok": true, ...}` |
| 400 | Bad request / validation failure | `{"ok": false, "error": "<CODE>", "message": "<Vietnamese message>"}` |
| 401 | No session / expired session | `{"ok": false, "error": "AUTH_REQUIRED"}` or `{"error": "SESSION_EXPIRED", "reason": "idle"|"absolute"}` |
| 403 | Authenticated but not permitted | `{"ok": false, "error": "FORBIDDEN", "permission": "<code>", "message": "..."}` |
| 404 | Entity/route not found | `{"ok": false, "error": "NOT_FOUND", "message": "Đường dẫn không tồn tại."}` |
| 409 | Conflict / business-rule refusal (e.g. already closed, overlap, insufficient input stock) | `{"ok": false, "error": "CONFLICT"}` or a specific error code, `message` names the exact reason |
| 500 | Unexpected server error | Generic error body; captured to Action/Error logs, never exposes a raw stack trace to the client |

### 11.2 Known specific error codes

| Code | Where | Meaning |
|---|---|---|
| `AUTO_LOGIN_DISABLED_PRODUCTION` | `/api/auth/test-auto-login` | Attempted on `MESFLOW_ENV=production` without the explicit override — see §11.4 |
| `AUTO_LOGIN_DISABLED` | same | Feature flag itself is off |
| `AUTO_LOGIN_INVALID_PERSONA` | same | `persona` param not one of the 5 allowed values |
| `AUTO_LOGIN_USER_NOT_FOUND` | same | Configured/persona username has no active account |
| `INVALID_CREDENTIALS` | `/api/auth/login` | Wrong username or password, or account inactive — same message for all 3 cases (never reveals which) |
| `QR_REQUIRED` (`error_code: SCN-001`) | Kiosk v1 scan | Empty QR payload |
| `STATE_INVALID_TRANSITION` | Kiosk v2 | Event doesn't fit the device's current state — see §7.2 table |
| `OPERATION_NOT_WORKABLE` | Kiosk v2 | Target Operation's PO isn't `IN_PROGRESS` |
| `EMPLOYEE_NOT_FOUND` / `OPERATION_NOT_FOUND` | Kiosk v2 | QR resolved but no matching record |
| `DEVICE_NOT_ALLOWED` | Kiosk v2 | Device disabled/in maintenance, or unauthorized |
| `SESSION_NOT_OPEN` | Kiosk v2 | Expected an open session, found none/already closed |

---

## 12. Environment matrix

| | DEV (local sandbox) | DEMO | PRODTEST | Real production |
|---|---|---|---|---|
| `MESFLOW_ENV` | `local` or `test` | `production` | `production` | unconfirmed |
| Autologin allowed with just `MESFLOW_TEST_AUTO_LOGIN=1`? | **Yes** | No — needs override below | No — needs override below | Must never be enabled |
| Extra flag needed | none | `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` | same | — |
| Seed mechanism | `python -m mesflow.tutorial_data seed` | same (prefix-namespaced, idempotent) | same | — |
| Typical URL | `http://127.0.0.1:18280` (isolated QA sandbox) | `http://127.0.0.1:8081` | `https://prod.mesflow.net` / `127.0.0.1:8299` | unconfirmed as of this writing |
| Volume-mounted tutorial videos | yes | no (ephemeral container layer — lost on recreate unless backed up first) | yes (fixed 2026-09-04 — was missing entirely before) | unconfirmed |

**Important, non-obvious fact**: `MESFLOW_ENV=production` does **not**
mean "this is the live business system" — it is the compose default
for every one of the shared tiers (DEMO and PRODTEST included), really
functioning as a "run in hardened/secure-cookie mode" switch rather
than a host-identity signal. Never infer "this is real production"
from `MESFLOW_ENV` alone.

### 12.1 Autologin (`MESFLOW_TEST_AUTO_LOGIN`) — full spec

- Default **off** everywhere.
- Hard-refused whenever `MESFLOW_ENV=production` unless
  `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` is **also** explicitly
  set (a second, independent opt-in — never satisfied by the first
  flag alone). The app logs a security warning at boot and on every
  refused attempt either way.
- When on: `POST /api/auth/test-auto-login` bootstraps a real session
  (the same server-side call a password login uses) for a
  server-configured account (`MESFLOW_TEST_AUTO_LOGIN_USERNAME`,
  default `admin`), or an explicit `persona` — see §12.2.
- `GET /login?noauto=1` always renders the real password form and
  never auto-triggers, regardless of the flag — the app's own logout
  button already appends this to avoid a logout→autologin loop.
- Real-password login coverage is deliberately kept as its own,
  separate test group and must never be treated as replaced by
  autologin coverage.

### 12.2 Persona quick-switch (RBAC testing convenience)

`POST /api/auth/test-auto-login` with body/query `persona=<role>` —
allowed values are **exactly**: `admin`, `manager`, `supervisor`,
`operator`, `viewer` (never `super_admin`, deliberately excluded from
quick-switch). Resolves to the account whose **username literally
equals** the persona name (every real deployment seeds one canonical
account per role named after the role itself — this convention is
depended upon, not incidental). Same guard as §12.1 — never usable in
real production. An unrecognized value → `400 AUTO_LOGIN_INVALID_PERSONA`,
body includes the allowed list; no session is created.

---

## 13. QC test-data personas and sample datasets

Use these exact values when a test case needs concrete data and none
is otherwise specified — this removes any need to invent or ask.

### 13.1 Standard login personas (via autologin persona switch, §12.2)

| Persona | Username | Role | Use for |
|---|---|---|---|
| Admin | `admin` | admin | Full-access baseline; every REQ that says "admin" |
| Manager | `manager` | manager | Broadest business-config testing |
| Supervisor | `supervisor` | supervisor | Floor-operations testing (sessions, exceptions, kiosk) |
| Operator | `operator` | operator | View-only-in-admin-app boundary testing |
| Viewer | `viewer` | viewer | Read-only boundary testing |

Password login fallback (when autologin is off or a real-login test is
required): `MESFLOW_ADMIN_USERNAME`/`MESFLOW_ADMIN_PASSWORD` from the
target environment's own configuration — never hardcode a password
into a test case; reference it as an environment secret.

### 13.2 Sample Production Order dataset

```
Template: TPL-DEMO-01 "Khung kim loại", version 1.0
  Part P-DEMO-01 "Khung chính"
    Operation OP-DEMO-01-CUT   "Cắt phôi"     standard_seconds_per_unit=60
    Operation OP-DEMO-01-BEND  "Uốn"          standard_seconds_per_unit=90, predecessor=OP-DEMO-01-CUT
    Operation OP-DEMO-01-WELD  "Hàn"          standard_seconds_per_unit=120, predecessor=OP-DEMO-01-BEND,
                                                input_flow_enabled=true, input_source=OP-DEMO-01-BEND, input_source_kind=GOOD
    Operation OP-DEMO-01-QC    "Kiểm tra"     standard_seconds_per_unit=30, predecessor=OP-DEMO-01-WELD

Instantiated PO: PO-DEMO-001, product "Khung kim loại", planned_quantity=100, status=PLANNED
```

Use `TPL-DEMO-01` → instantiate → `PO-DEMO-001` for every journey that
needs "a PO"; Start it (`status → IN_PROGRESS`) before any session-level
test case.

### 13.3 Sample employees (also the persona-switch accounts, §13.1 —
same DB rows, dual purpose)

```
EMP-DEMO-01, name "Nguyễn Văn A", department "Sản xuất", employment_status "Đang làm" (active=true)
EMP-DEMO-02, name "Trần Thị B",   department "QC",       employment_status "Đang làm" (active=true)
EMP-DEMO-03, name "Lê Văn C",     department "Sản xuất", employment_status "Đã nghỉ"  (active=false — use for REQ-EMP-003's inactive-employee negative case)
```

### 13.4 Sample session data covering every KPI-formula edge case (§8)

| Session | Operation std sec/unit | good | defect | duration | completion_percent |
|---|---|---|---|---|---|
| A | 60 | 10 | 0 | 20 min (1200s) | `(60×10)/1200×100 = 50%` |
| B | 60 | 14 | 0 | 20 min | `(60×14)/1200×100 = 70%` |
| C | 60 | 10 | 0 | 500s | `600/500×100 = 120%` (no clamp — must appear as-is) |
| D | 0 (unconfigured) | 5 | 0 | 10 min | `NULL` — "Không đủ dữ liệu," not 0 |
| E | 60 | 0 | 0 | 5 hours (>4h) | valid 0%-ish math, but **also** triggers `ZERO_QUANTITY_LONG` (§9.1) |

Employee averaging A+B over one employee in one day → `(50+70)/2 = 60%`
— the textbook case to verify §8's averaging rule.

### 13.5 Exception-triggering sample data (§9.1, one row per condition)

- A session `OPEN`, `started_at` = now − 13 hours → `LONG_OPEN_SESSION`.
- A session `CLOSED`, duration 5 hours, `good=defect=0` → `ZERO_QUANTITY_LONG`.
- A session with `station_id=NULL, device_uuid=''` → `MISSING_STATION`.
- A session with `ended_at` set to 1 minute **before** `started_at`
  (only reachable via direct data manipulation, not a normal API path —
  useful for testing the detector itself) → `INVALID_DURATION`.
- Two sessions for the same `employee_id` with overlapping
  `[started_at, ended_at)` ranges → `EMPLOYEE_SESSION_CONFLICT`.

---

## 14. Non-functional acceptance criteria (testable only)

Every row below is phrased as a concrete, checkable assertion — no
"reasonable," "fast," "user-friendly," or similar unquantified word is
used anywhere in this document; if you find one, it is a defect.

| ID | Criterion |
|---|---|
| NFR-001 | Retrying an identical idempotency-keyed request (same `request_id`) returns the exact original response body with `idempotent_replay: true`, and creates **zero** additional database rows. |
| NFR-002 | Two concurrent `start()`/`finish()`/`adjust()` calls touching Operations under the **same** Production Order never deadlock — the PO row lock is always acquired first, in a fixed order, before any other lock in the same call. |
| NFR-003 | A state change (session start/finish/adjust/exclude/restore, PO start, Operation cancel, exception acknowledge/resolve/ignore) and its corresponding audit-log row are always committed in the same database transaction — after any successful call, exactly one matching audit row exists; after any failed/rolled-back call, zero. |
| NFR-004 | Session cookies: `HttpOnly` and `SameSite=Lax` on every response, always. `Secure` flag is present on every response except direct-localhost or trusted-internal-network HTTP traffic explicitly carved out for QA. |
| NFR-005 | A permission check that cannot complete (RBAC data unavailable) returns "deny" (`403`), never "allow." |
| NFR-006 | `GET /api/system/ready` responds within the deploy pipeline's own health-check window (18 retries × 10s = 180s from container start) with `ok: true` before a deploy is considered successful — this is the exact contract the deploy tooling itself checks. |
| NFR-007 | A Docker container reporting "healthy" at the platform level is **not** by itself sufficient evidence the app is serving correctly — a separate, direct `GET /api/system/ready` check returning `ok:true` is required (a real observed case: a container with no `HEALTHCHECK` configured at all still reports a running status). |
| NFR-008 | No numeric page-load/response-time SLA exists in this system as of this writing — do not assert one; see §21 gap. |
| NFR-009 | Automated browser test coverage in this codebase runs on Chromium only via Playwright — no automated Firefox/Safari coverage exists; do not assume cross-browser parity has been verified. |
| NFR-010 | The primary supported/tested desktop viewport is exactly 1366×768; additional viewports with automated coverage: 1920×1080 and 390×844 (mobile). Any new page's responsive check should cover at minimum these three. |

---

# PART B — Functional Requirements

Field key for every block below: **Module**, **Purpose**, **Actors**,
**Preconditions**, **Input**, **Trigger**, **Main flow**, **Expected
output**, **State transition**, **Validation**, **Errors**,
**Boundary**, **Permission**, **Concurrency**, **Audit**, **Related**,
**Priority**, **Dimensions**. A field marked `N/A` includes a one-line
reason. Formulas/tables cited as "§N" are in Part A above, in this same
file — never external.

## 15.1 Authentication & Session (`REQ-AUTH-*`)

### REQ-AUTH-001 — Real password login

- **Module**: Authentication
- **Purpose**: Let a real account holder establish an authenticated session.
- **Actors**: any account, any of the 6 roles (§1.2), `active=true`.
- **Preconditions**: an account with a known username/password exists and is active.
- **Input**: `{username, password}`, both non-empty strings.
- **Trigger**: `POST /api/auth/login`.
- **Main flow**: 1) server looks up `users` by `username`. 2) verifies `password` against `password_hash`. 3) on match, creates a session carrying `user_id/username/role`. 4) returns the user object with computed `permissions` (§3.2/§3.3).
- **Expected output**: `200 {"ok":true,"user":{"id","username","role","must_change_password","permissions":[...]}}`; a session cookie is set (`HttpOnly`, `SameSite=Lax`, `Secure` per NFR-004).
- **State transition**: no session → active session (idle/absolute timers start, §3.5).
- **Validation**: both fields required; no format constraint beyond non-empty.
- **Errors**: wrong password, unknown username, or `active=false` account → **identical** `401 {"error":"INVALID_CREDENTIALS"}` in all three cases (never reveals which).
- **Boundary**: empty string password vs. correct password of length 1 — both handled by the same hash-compare path, no special-casing.
- **Permission**: N/A — this endpoint has no permission gate, it establishes the identity permissions are later checked against.
- **Concurrency**: N/A — stateless per-request check.
- **Audit**: writes `LOGIN_SUCCESS` or `LOGIN_FAILED` (with `reason: invalid_credentials|inactive`) to the audit trail on every attempt; the submitted password is never logged in any form.
- **Related**: BR-901 (see §16).
- **Priority**: P0.
- **Dimensions**: positive, negative, boundary (empty fields).

### REQ-AUTH-002 — Logout

- **Module**: Authentication
- **Purpose**: End the current session on demand.
- **Actors**: any session state, including none.
- **Preconditions**: none.
- **Input**: none.
- **Trigger**: `POST /api/auth/logout`.
- **Main flow**: 1) server clears the session unconditionally.
- **Expected output**: `200 {"ok":true}` whether or not a session existed.
- **State transition**: active session → no session (or no-op if already none).
- **Validation**: N/A.
- **Errors**: none — this call cannot fail.
- **Boundary**: calling it twice in a row is safe (second call is a no-op).
- **Permission**: N/A — callable with or without a session.
- **Concurrency**: N/A.
- **Audit**: N/A (no explicit audit row for logout confirmed).
- **Related**: REQ-AUTH-001, BR-902 (logout anti-loop, §16).
- **Priority**: P1.
- **Dimensions**: positive.

### REQ-AUTH-003 — Session status check

- **Module**: Authentication
- **Purpose**: Let the frontend determine whether the current session is valid and who it belongs to.
- **Actors**: any.
- **Preconditions**: none.
- **Input**: none (relies on the session cookie).
- **Trigger**: `GET /api/auth/me`.
- **Main flow**: 1) validate session (idle/absolute expiry, §3.5). 2) if valid, look up the user and return role+permissions.
- **Expected output**: `200 {"ok":true,"user":{...}}` when valid.
- **State transition**: N/A (read-only).
- **Validation**: N/A.
- **Errors**: no session → `401 {"error":"AUTH_REQUIRED"}`; expired session → `401 {"error":"SESSION_EXPIRED","reason":"idle"|"absolute"}` (session is also cleared as a side effect of detecting expiry).
- **Boundary**: request arriving exactly at the idle-timeout boundary — implementation resolves this by wall-clock comparison at request time, not a separate scheduled sweep; test both "1 second before" and "1 second after" the idle window.
- **Permission**: N/A.
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: REQ-AUTH-001.
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary.

### REQ-AUTH-004 — Autologin (test facility only)

- **Module**: Authentication (test-only)
- **Purpose**: Let QA/Playwright skip the password form in non-production environments. **Never a production requirement.**
- **Actors**: any of the 5 non-super_admin roles via persona (§12.2), or the single configured default account.
- **Preconditions**: `MESFLOW_TEST_AUTO_LOGIN=1`; if `MESFLOW_ENV=production`, additionally `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` must also be set (§12.1).
- **Input**: optional `{persona}` in JSON body or query string.
- **Trigger**: `POST /api/auth/test-auto-login`.
- **Main flow**: 1) guard check (§12.1). 2) if `persona` given, validate against the 5-value allowlist and resolve to the like-named username. 3) else use `MESFLOW_TEST_AUTO_LOGIN_USERNAME` (default `admin`). 4) look up that active user and start a real session exactly as REQ-AUTH-001 does.
- **Expected output**: same shape as REQ-AUTH-001's success response.
- **State transition**: no session → active session.
- **Validation**: `persona`, if given, must be exactly one of `admin|manager|supervisor|operator|viewer`.
- **Errors**: guard fails → `403 AUTO_LOGIN_DISABLED_PRODUCTION` or `403 AUTO_LOGIN_DISABLED`; invalid persona → `400 AUTO_LOGIN_INVALID_PERSONA` (response includes the allowed list); resolved username has no active account → `503 AUTO_LOGIN_USER_NOT_FOUND`.
- **Boundary**: persona value differing only in case (e.g. `Admin`) — implementation lowercases before matching, so this should succeed, not fail.
- **Permission**: N/A (this route bypasses password, but not the environment guard — see §12.1; `super_admin` is never reachable via persona).
- **Concurrency**: N/A.
- **Audit**: N/A confirmed for this specific route (unlike REQ-AUTH-001); the server does log a boot-time and per-attempt security warning when the guard is engaged on a `production`-flagged environment.
- **Related**: BR-903/904/905 (§16).
- **Priority**: P0 for the guard/negative cases (a failure here is a real security regression), P2 for the happy path itself (test convenience, not business value).
- **Dimensions**: positive, negative, boundary (case sensitivity), RBAC (persona allowlist).

### REQ-AUTH-005 — Logout does not loop back into autologin

- **Module**: Authentication (test-only)
- **Purpose**: Ensure a deliberate logout is reachable/visible even when autologin is on.
- **Actors**: any.
- **Preconditions**: `MESFLOW_TEST_AUTO_LOGIN=1` and guard satisfied (autologin actually active).
- **Input**: none.
- **Trigger**: `GET /login?noauto=1`.
- **Main flow**: 1) server renders the login page with the auto-trigger flag forced off for this render only, regardless of the global flag's value.
- **Expected output**: rendered HTML with `data-test-auto-login="0"`; the client-side script does not fire the autologin POST.
- **State transition**: N/A.
- **Validation**: N/A.
- **Errors**: none.
- **Boundary**: `GET /login` (no query param) on the same environment must still show `data-test-auto-login="1"` and auto-trigger — this is the contrast case that proves the override is real, not a global change.
- **Permission**: N/A.
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: REQ-AUTH-004, BR-902.
- **Priority**: P1.
- **Dimensions**: positive, negative (contrast case).

## 15.2 Dashboard / Overview (`REQ-DASH-*`)

### REQ-DASH-001 — Overview and Dashboard pages load for any authenticated role

- **Module**: Dashboard
- **Purpose**: Give every role a single-screen production status view (PO count/progress, quantity totals) without navigating to a detail screen first.
- **Actors**: any role holding `overview.view`/`dashboard.view` — per §3.2, this is **all 6 roles** for both permissions.
- **Preconditions**: authenticated session.
- **Input**: none for the base view; optional PO/status/sort filters (see REQ-DASH-002).
- **Trigger**: navigate to `overview` or `dashboard` page (§2), or `GET /api/dashboard/overview` / `/api/dashboard/control-tower` directly.
- **Main flow**: 1) client requests the summary panels independently (`/api/dashboard/summary`, `/production-orders`, `/active-sessions`, `/daily-progress`, `/daily-sessions`, `/shift`, `/recent-activity`). 2) each renders its own card/section.
- **Expected output**: KPI cards for PO đang chạy / Kế hoạch / Đạt / NG tổng / Phế / Còn lại / Chờ sửa (live-verified card set); each panel populates independently.
- **State transition**: N/A (read-only).
- **Validation**: N/A.
- **Errors**: a failure in one panel's endpoint must not 500 the whole page — each panel is fetched and rendered independently.
- **Boundary**: zero POs in the system at all → every KPI card shows 0, not an error state.
- **Permission**: `login_required` only at the route level; permission is really enforced by whether the nav entry is shown (§2) — direct API access without the permission does **not** appear to be separately blocked beyond session validity (verify this explicitly as a test case, since it is a real, testable distinction between "hidden in nav" and "blocked at API").
- **Concurrency**: N/A.
- **Audit**: N/A (read-only view).
- **Related**: REQ-DASH-002.
- **Priority**: P0.
- **Dimensions**: positive, empty-state, RBAC (nav visibility per role).

### REQ-DASH-002 — Filter cascading and stale-response protection

- **Module**: Dashboard / Session Management (shared pattern)
- **Purpose**: Selecting a PO/Part filter must narrow the downstream dropdowns to only that parent's own children, and a filter change must never render a response older than the user's latest selection.
- **Actors**: any role with view access to the filtered screen.
- **Preconditions**: at least 2 POs with different Parts/Operations exist, to make cascading observable.
- **Input**: `po`, `part`, `operation`, `status`, `sort` query params (screen-dependent).
- **Trigger**: changing any filter control.
- **Main flow**: 1) selecting a PO narrows the Part dropdown to only that PO's own Parts (and Part narrows Operation similarly). 2) an incompatible combination present in the URL on page load is normalized, not left inconsistent. 3) each filter change issues a new request.
- **Expected output**: filtered list/table reflecting only the current filter combination.
- **State transition**: N/A.
- **Validation**: N/A.
- **Errors**: N/A.
- **Boundary**: rapidly changing the PO filter twice in quick succession (a slow first response must not overwrite the second, faster response once it arrives) — this is a **real, specifically tested** requirement, not a hypothetical.
- **Permission**: inherits the host screen's permission.
- **Concurrency**: request-race protection is required client-side: a response to a superseded request must be discarded, not rendered.
- **Audit**: N/A.
- **Related**: BR-016 (§16).
- **Priority**: P1.
- **Dimensions**: positive, boundary, concurrency (race).

## 15.3 Production Order (`REQ-PO-*`)

### REQ-PO-001 — PO creation is template-instantiation only

- **Module**: Production Order
- **Purpose**: Every PO must originate from a validated Template, never a blank hand-built record.
- **Actors**: admin, manager (`template.edit` — instantiate is a template-edit-permission action).
- **Preconditions**: an active Template with ≥1 Part/Operation exists.
- **Input**: `{template_id}` plus any PO-level overrides the instantiate form allows (e.g. `planned_quantity`).
- **Trigger**: `POST /templates/<template_id>/instantiate`.
- **Main flow**: 1) copy the template's Parts into new `parts` rows tied to a new `production_orders` row. 2) copy the template's Operations into new `operations` rows, preserving dependency/input-flow relationships remapped to the new IDs. 3) new PO gets a fresh `code`, `status=PLANNED` (or `DRAFT`), `planned_quantity` as given.
- **Expected output**: `200` with the new PO id/code; a subsequent `GET` on that PO shows all Parts/Operations copied with matching structure to the source Template.
- **State transition**: (no PO existed) → PO exists, `status=PLANNED`.
- **Validation**: `planned_quantity`, if overridden, must be `> 0`.
- **Errors**: **directly calling** `POST /api/production-orders` (bypassing instantiate) is rejected outright: `ValueError`, "Production Order phải được tạo từ Template để sao chép Part và Operation" — this must be tested explicitly as a negative case, it is not merely undocumented, it is actively refused.
- **Boundary**: instantiating the same Template twice must produce two independent POs, not a conflict — Operation `code` values must be generated distinctly per instantiation (globally unique, §4.3).
- **Permission**: admin, manager (`template.edit`); supervisor/operator/viewer → `403`.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed as a distinct audit action from generic PO create (verify presence, not assumed absent).
- **Related**: REQ-TPL-001..004, REQ-PART-001.
- **Priority**: P0.
- **Dimensions**: positive, negative (direct-create rejection), RBAC.

### REQ-PO-002 — Start a Production Order

- **Module**: Production Order
- **Purpose**: Release a prepared PO to the shop floor, making its Operations kiosk-workable.
- **Actors**: admin, manager, **supervisor** (widened beyond the generic `po.edit` role set — §3.4).
- **Preconditions**: PO exists with `status` not `COMPLETED`/`CANCELLED`, and has ≥1 Operation.
- **Input**: PO id in the URL, no body.
- **Trigger**: `POST /production-orders/<id>/start`.
- **Main flow**: 1) lock the PO row. 2) if already `IN_PROGRESS`, short-circuit to success (idempotent). 3) if `COMPLETED`/`CANCELLED`, refuse. 4) if zero Operations, refuse. 5) else set `status=IN_PROGRESS`, write a `PO_STARTED` domain event.
- **Expected output**: `200 {"ok":true,"item":{...,"status":"IN_PROGRESS"},"operation_count":N,"already_started":false}` (or `true` on the idempotent-repeat case).
- **State transition**: `DRAFT|PLANNED|RELEASED|PAUSED → IN_PROGRESS`.
- **Validation**: N/A beyond the preconditions above.
- **Errors**: `COMPLETED`/`CANCELLED` PO → `409`, "PO đã hoàn thành hoặc đã hủy nên không thể Start"; zero Operations → `409`, "PO chưa có Operation. Hãy thêm Operation trước khi Start."
- **Boundary**: exactly 1 Operation (the minimum non-zero count) must succeed; exactly 0 must fail with the specific message above.
- **Permission**: admin, manager, supervisor succeed; operator, viewer → `403`.
- **Concurrency**: two concurrent Start calls on the same PO — the second observes the already-`IN_PROGRESS` state under the same row lock and returns the idempotent success path, never a race-condition error.
- **Audit**: `PO_STARTED` domain event with `previous_status` and new `status` in its metadata.
- **Related**: REQ-SESS-001 (Operations only become startable once the PO is `IN_PROGRESS`).
- **Priority**: P0.
- **Dimensions**: positive, negative, boundary, RBAC, concurrency, state transition.

### REQ-PO-003 — Edit a Production Order

- **Module**: Production Order
- **Purpose**: Update PO metadata (status, priority, dates, notes) after creation.
- **Actors**: admin, manager.
- **Preconditions**: PO exists.
- **Input**: any subset of `{status, priority, due_date, planned_start_at, planned_end_at, notes, product, code}`.
- **Trigger**: `PATCH /production-orders/<id>`.
- **Main flow**: 1) normalize/validate every submitted field. 2) apply the update.
- **Expected output**: `200` with the updated PO row.
- **State transition**: whatever `status` is submitted, if valid — see §5.3's note that no further transition graph is enforced beyond enum membership.
- **Validation**: `status` ∈ `{DRAFT,PLANNED,RELEASED,IN_PROGRESS,PAUSED,COMPLETED,CANCELLED}`; `priority` ∈ `{LOW,NORMAL,HIGH,URGENT}`; if both `planned_start_at`/`planned_end_at` given, end must be strictly after start; `code`/`product`, if given, must be non-empty.
- **Errors**: any value outside the enums → `400`-class `ValueError` naming the Vietnamese field ("Trạng thái PO không hợp lệ" / "Mức ưu tiên PO không hợp lệ"); `planned_end_at ≤ planned_start_at` → "Thời gian kết thúc dự kiến phải sau thời gian bắt đầu".
- **Boundary**: `planned_end_at` exactly equal to `planned_start_at` must be rejected (strictly after, not "at or after").
- **Permission**: admin, manager only; supervisor/operator/viewer → `403`.
- **Concurrency**: N/A confirmed (no optimistic-lock field observed on this specific PATCH, unlike session edit — treat this absence as a real, testable fact, not an oversight in this document).
- **Audit**: N/A confirmed distinctly (verify presence of a generic entity-update audit row).
- **Related**: REQ-PO-002.
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary, RBAC.

### REQ-PO-004 — Delete a Production Order (history guard)

- **Module**: Production Order
- **Purpose**: Prevent destroying real production history via ordinary delete.
- **Actors**: admin, manager for the guarded delete; **admin only** for the force variant.
- **Preconditions**: PO exists.
- **Input**: PO id.
- **Trigger**: `DELETE /production-orders/<id>` (guarded) or `DELETE /production-orders/<id>/force` (bypasses the guard).
- **Main flow (guarded)**: 1) check for any session, input-consumption ledger row, non-zero output quantity, kiosk event, adjustment, or QC inspection under this PO's Operations. 2) if any exist, refuse naming which kind(s) were found. 3) else delete.
- **Expected output (guarded, no history)**: `200`, PO and its Parts/Operations removed (cascade).
- **State transition**: PO exists → PO does not exist.
- **Validation**: N/A.
- **Errors**: any history present → `409`, "Không thể xóa Production Order vì đã có production history: {found kinds}." — the message names exactly which categories were found (e.g. "Session, sản lượng").
- **Boundary**: a PO with exactly one `CLOSED` session (the minimum non-zero history) must be refused by the guarded path.
- **Permission**: guarded delete: admin, manager. **Force delete: admin only** — manager must get `403` on the force path even though manager can use the guarded path (§3.4's explicitly confirmed narrower rule).
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly for delete/force-delete (verify).
- **Related**: REQ-PART-002 (same guard shape, one level down).
- **Priority**: P0 (force-delete's role boundary is a real, previously-broken security rule — regression-critical).
- **Dimensions**: positive, negative, boundary, RBAC (specifically: manager must fail force-delete).

## 15.4 Part & Drawing (`REQ-PART-*`)

### REQ-PART-001 — Part belongs to exactly one PO

- **Module**: Part
- **Purpose**: Enforce the PO→Part ownership hierarchy.
- **Actors**: admin, manager (create/edit); any viewer role (read).
- **Preconditions**: a PO exists.
- **Input**: `{production_order_id, code, name, drawing_path?, sort_order?, active?}`.
- **Trigger**: `POST /<resource=parts>` (generic resource create) or as part of template instantiation (REQ-PO-001).
- **Main flow**: 1) `production_order_id` required and must reference an existing PO. 2) `code` must be unique **within that PO** (not globally).
- **Expected output**: `200` with the new Part row.
- **State transition**: N/A.
- **Validation**: `code`+`production_order_id` combination unique (`UNIQUE(production_order_id, code)`); `name` required.
- **Errors**: duplicate `(production_order_id, code)` → DB-level unique-violation surfaced as a conflict error.
- **Boundary**: the **same** `code` value used under two **different** POs must both succeed (uniqueness is scoped per-PO, not global — this is the exact opposite behavior from Operation's `code`, which IS globally unique — test this contrast explicitly).
- **Permission**: admin, manager write; any role with `template.view`/PO view reads it as part of the PO detail.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed.
- **Related**: REQ-PO-001, REQ-PART-002, REQ-TPL-003 (drawing upload).
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary (per-PO vs. global uniqueness contrast).

### REQ-PART-002 — Delete a Part (history guard)

- **Module**: Part
- **Purpose**: Prevent destroying production history one level below the PO guard.
- **Actors**: admin, manager.
- **Preconditions**: Part exists.
- **Input**: Part id.
- **Trigger**: `DELETE /<resource=parts>/<id>`.
- **Main flow**: 1) aggregate across every Operation under this Part: session count, ledger rows, non-zero output, kiosk events, adjustments, QC inspections. 2) refuse if any found, naming which kinds; else delete.
- **Expected output**: `200` on success (no history); Part and its Operations removed (cascade).
- **State transition**: Part exists → does not exist.
- **Validation**: N/A.
- **Errors**: any history under any child Operation → `409`, "Không thể xóa Part vì đã có production history: {found kinds}."
- **Boundary**: a Part with 2 Operations, only one of which has history, must still be refused (aggregated across all child Operations, not per-Operation).
- **Permission**: admin, manager; supervisor/operator/viewer → `403`.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed.
- **Related**: REQ-PO-004 (identical guard shape).
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary.

### REQ-PART-003 — Upload a drawing file

- **Module**: Part / Template
- **Purpose**: Attach a technical drawing to a template Part, propagating to every future PO instantiated from it.
- **Actors**: admin, manager.
- **Preconditions**: template Part exists.
- **Input**: multipart file upload + target `template_part_id`.
- **Trigger**: `POST /template-parts/upload-drawing`.
- **Main flow**: 1) accept the file, store it, record its path on the template Part's `drawing_path`.
- **Expected output**: `200` with the stored path/reference.
- **State transition**: N/A.
- **Validation**: file type/size constraints — not confirmed in this pass (see §21 gap; test conservatively with a real image/PDF and flag if the system accepts something unexpected).
- **Errors**: N/A confirmed beyond generic upload failure.
- **Boundary**: N/A confirmed (file-size ceiling exists system-wide, `MESFLOW_MAX_UPLOAD_BYTES`, default ~200MB — test near that boundary if precision matters).
- **Permission**: admin, manager; others → `403`.
- **Concurrency**: N/A.
- **Audit**: N/A confirmed.
- **Related**: REQ-PART-001.
- **Priority**: P2.
- **Dimensions**: positive, negative, boundary (file size).

## 15.5 Template / Routing (`REQ-TPL-*`)

### REQ-TPL-001 — View and edit the Template tree

- **Module**: Template
- **Purpose**: Define the reusable Part→Operation structure a PO is instantiated from.
- **Actors**: view — any authenticated role (`template.view`, held by admin/manager/viewer); edit — admin, manager.
- **Preconditions**: Template exists.
- **Input (edit)**: full tree replacement payload — ordered list of Parts, each with ordered Operations and their fields (§4.3 minus runtime-only fields).
- **Trigger**: `GET /templates/<id>/tree` (view), `PUT /templates/<id>/tree` (replace).
- **Main flow (replace)**: 1) check whether this template has ever been instantiated into a PO whose Operations now carry Session or ledger history. 2) if so, refuse. 3) else replace the whole tree atomically.
- **Expected output**: `200` with the new tree on success.
- **State transition**: N/A.
- **Validation**: structural — see REQ-TPL-003 (separate validate endpoint).
- **Errors**: history exists on an instantiated PO's Operations → `409`, "Không thể Replace cấu trúc Operation khi đã có Session hoặc Ledger dòng vật tư. Hãy dùng Merge hoặc tạo PO mới."
- **Boundary**: a Template that has been instantiated but whose resulting PO has **zero** sessions yet must still allow Replace (the guard is keyed on actual history, not on "has ever been instantiated").
- **Permission**: view: any role with `template.view`; edit: admin, manager only.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed.
- **Related**: REQ-PO-001, REQ-TPL-002/003/004.
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary, RBAC.

### REQ-TPL-002 — Validate a Template

- **Module**: Template
- **Purpose**: Catch structural problems (e.g. dependency cycles) before instantiation.
- **Actors**: any role with `template.view`.
- **Preconditions**: Template exists.
- **Input**: Template id.
- **Trigger**: `GET /templates/<id>/validate`.
- **Main flow**: 1) walk the Operation dependency graph (predecessor + input-source links) for cycles/dangling references. 2) return a pass/fail with details.
- **Expected output**: `200` with a validation result object (errors list, empty if valid).
- **State transition**: N/A (read-only check).
- **Validation**: N/A (this IS the validation).
- **Errors**: N/A — always `200`, the *body* signals validity, not the HTTP status.
- **Boundary**: a template with a 2-node dependency cycle (`A→B→A`) must fail validation; a straight-line chain of any length must pass.
- **Permission**: any role with `template.view`.
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: REQ-TPL-004.
- **Priority**: P1.
- **Dimensions**: positive, negative (cycle case), boundary.

### REQ-TPL-003 — Instantiate a Template into a PO

- Covered fully as REQ-PO-001 (instantiation is the PO-creation path — do not duplicate test cases, cross-reference REQ-PO-001).

### REQ-TPL-004 — Demo template seed/wipe (admin-only)

- **Module**: Template
- **Purpose**: Let an administrator seed or remove demo/tutorial template data.
- **Actors**: **admin only** (§3.4 — narrower than ordinary `template.edit`, which manager also has).
- **Preconditions**: none for seed; demo data must exist for wipe to have an effect.
- **Input**: none.
- **Trigger**: `POST /templates/demo/seed`, `DELETE /templates/demo`.
- **Main flow**: 1) seed inserts a known set of demo Templates/Parts/Operations (prefix-namespaced); wipe removes exactly that namespaced set.
- **Expected output**: `200` on success.
- **State transition**: N/A.
- **Validation**: N/A.
- **Errors**: N/A confirmed beyond the permission boundary below.
- **Boundary**: calling seed twice must not create duplicates (idempotent by design — the same convention `tutorial_data.py` uses elsewhere in the system, §12).
- **Permission**: **admin only** — manager, despite holding `template.edit`, must receive `403` here (a specifically confirmed, previously-broken rule — regression-critical).
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed.
- **Related**: §12 (environment/seed conventions), REQ-TPL-001.
- **Priority**: P0 (RBAC-boundary regression risk).
- **Dimensions**: positive, RBAC (specifically: manager must fail), boundary (idempotency).

### REQ-TPL-005 — Excel import/export for Templates/Operations

- **Module**: Template / Import-Export
- **Purpose**: Round-trip Operation data via Excel workbook.
- **Actors**: export: admin, manager, **viewer** (widened, read-only — §3.4); import: admin, manager only.
- **Preconditions**: for import, a well-formed workbook per §10's schema.
- **Input**: export — none (Template id in URL); import — multipart Excel file.
- **Trigger**: `GET /export.xlsx`, per-template `export-workbook`; `POST /import`, per-template `import`.
- **Main flow**: see §10 in full for every row-level rule.
- **Expected output**: export — a downloadable `.xlsx`; import — `200` with a summary of rows applied, or a `400` naming the first row/column that failed.
- **State transition**: import can move Operations between PO/Part (§10), subject to the ledger guard.
- **Validation**: full rule set in §10 — required fields, done/defect/status rejection, duplicate `operation_id` rejection, planned-quantity-conflict rejection, ledger-guarded PO/Part move.
- **Errors**: every validation rule in §10 has its own exact Vietnamese message — use those verbatim in negative test assertions, not a generic "import failed."
- **Boundary**: a workbook with exactly one invalid row among many valid ones — confirm the whole import is rejected (transactional), not partially applied (verify this is actually transactional; if evidence is inconclusive, flag as open question rather than assert either way).
- **Permission**: export: admin/manager/viewer; import: admin/manager only; export-workbook specifically also viewer.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly.
- **Related**: §10 (full schema appendix).
- **Priority**: P1.
- **Dimensions**: positive, negative (every §10 rule), boundary, RBAC.

## 15.6 Employee (`REQ-EMP-*`)

### REQ-EMP-001 — Create/edit an Employee

- **Module**: Employee
- **Purpose**: Maintain the employee roster kiosk sessions are recorded against.
- **Actors**: admin, manager.
- **Preconditions**: none for create.
- **Input**: `{employee_no, name, department?, position?, employment_status?, qr, birth_date?, hometown?, phone?, identity_number?, identity_issue_date?, current_address?, start_date?, end_date?, contract_1?, contract_2?}` — full field list §4.5.
- **Trigger**: `POST /<resource=employees>` (create), `PATCH /<resource=employees>/<id>` (edit).
- **Main flow**: 1) `employee_no` uppercased automatically. 2) `employment_status` defaults to `"Đang làm"` if omitted. 3) `active` is derived, not accepted as direct input: `active = (employment_status != "Đã nghỉ")`. 4) empty-string date fields coerce to `NULL`.
- **Expected output**: `200` with the stored row, `active` reflecting the derived value.
- **State transition**: N/A (not a stateful entity beyond active/inactive).
- **Validation**: `employee_no` and `qr` unique; other fields free-text.
- **Errors**: duplicate `employee_no`/`qr` → conflict.
- **Boundary**: submitting `active: false` directly while `employment_status` stays `"Đang làm"` — the derived rule must win, i.e. `active` ends up `true` regardless of the direct `active` field submitted (this is a real, specifically testable trap).
- **Permission**: admin, manager write; any role with `employees.view` (all 6 roles, §3.2) reads.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly.
- **Related**: REQ-SESS-001 (inactive employees cannot start sessions).
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary (derived-active trap), RBAC.

### REQ-EMP-002 — Inactive employee cannot start a session

- **Module**: Employee / Session
- **Purpose**: Block work being recorded against a terminated employee.
- **Actors**: system-enforced, triggered by any kiosk/web start action.
- **Preconditions**: an employee with `active=false` (i.e. `employment_status="Đã nghỉ"`).
- **Input**: `employee_id` of the inactive employee, in a session-start call.
- **Trigger**: `POST /work-sessions/start` (or the equivalent Kiosk v2 OP-scan path).
- **Main flow**: 1) employee lookup checks `active` before proceeding. 2) refuses immediately, before any Operation-side checks run.
- **Expected output**: refusal, no session row created.
- **State transition**: none (blocked before any state change).
- **Validation**: N/A.
- **Errors**: `RepositoryError`, "employee inactive or missing" (same message whether the employee is inactive or the id simply doesn't exist — does not reveal which).
- **Boundary**: an employee whose `employment_status` was just changed to `"Đã nghỉ"` mid-session (while they have an existing `OPEN` session) — starting a **new** session is blocked, but the existing open session is untouched by this check (it is not automatically closed).
- **Permission**: N/A (system rule, not a role check).
- **Concurrency**: N/A.
- **Audit**: N/A confirmed for the refusal itself.
- **Related**: REQ-SESS-001, REQ-EMP-001.
- **Priority**: P0.
- **Dimensions**: negative, boundary.

### REQ-EMP-003 — QR label generation/printing

- **Module**: Employee / QR
- **Purpose**: Produce printable QR identity for kiosk scanning.
- **Actors**: any role with `qr.view` (all 6 roles, §3.2).
- **Preconditions**: employees exist.
- **Input**: filter/selection of which employees to print.
- **Trigger**: `GET /qr-labels`, `GET /qr-image`.
- **Main flow**: 1) generate a QR payload per employee in the form `WF|EMP|<key>` (§7.2's wire format — the same format Kiosk v2 parses). 2) render as printable labels.
- **Expected output**: `200` with label/image data.
- **State transition**: N/A.
- **Validation**: N/A.
- **Errors**: N/A confirmed.
- **Boundary**: an employee with no `qr` value set — confirm whether this is possible given `qr` is `NOT NULL unique` at the schema level (§4.5) — likely always populated at creation time; test that the create flow actually enforces this rather than assuming.
- **Permission**: all 6 roles (`qr.view` is universally granted, §3.2).
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: §7.2 (QR wire format).
- **Priority**: P2.
- **Dimensions**: positive, boundary.

## 15.7 Work Session (`REQ-SESS-*`)

Full business-rule detail for all of these lives in §6 (Session
lifecycle) and §5.1 (state machine) — each requirement below is the
test-case-generation entry point into that detail, not a duplicate of
it.

### REQ-SESS-001 — Start a session

- **Module**: Session
- **Purpose**: Begin timed, attributable work by one employee on one Operation.
- **Actors**: system-triggered by Kiosk (v1/v2) or an authenticated web caller holding session-start capability (kiosk calls use device/token auth, not a role — see §7).
- **Preconditions**: full precondition list in §6.1 (employee active, PO `IN_PROGRESS`, input-flow source started if applicable, predecessor exists if applicable, dispatch-ready, employee has no other `OPEN` session, no time overlap).
- **Input**: `{employee_id, operation_id, station_id?, device_uuid?, request_id, occurred_at?}`.
- **Trigger**: `POST /work-sessions/start`, or Kiosk v2 `OP` scan while in `WAIT_OPERATION` state (§7.2).
- **Main flow**: §6.1, steps 1–7 in order — test each precondition's negative case independently, not only the full happy path.
- **Expected output**: new `work_sessions` row, `status=OPEN`; Operation status recomputes per §5.2 (typically → `IN_PROGRESS`).
- **State transition**: (no session) → `OPEN`; Operation status per §5.2 rule #2.
- **Validation**: `request_id` required and non-empty.
- **Errors**: see §6.1's ordered list — each precondition has its own exact message, reproduced there.
- **Boundary**: an employee with **exactly one** existing `OPEN` session attempting to start a second — must fail (§4.4's DB-enforced unique index, not just app logic — verify by attempting to bypass app validation if the test harness allows direct DB access, to confirm the DB constraint itself, not merely the app-level check).
- **Permission**: N/A at this call itself (kiosk uses device auth); the web equivalent route requires an authenticated session.
- **Concurrency**: retried identical `request_id` → same response, `idempotent_replay:true`, zero new rows (NFR-001). Two concurrent starts for the same employee — the DB unique index guarantees only one wins.
- **Audit**: `SESSION_STARTED` audit row + domain event, same transaction as the insert.
- **Related**: §6.1, §5.1, REQ-EMP-002, REQ-PO-002.
- **Priority**: P0.
- **Dimensions**: positive, negative (every precondition), boundary, concurrency, idempotency, state transition.

### REQ-SESS-002 — Finish a session

- **Module**: Session
- **Purpose**: Close out a work block with final good/defect/rework counts.
- **Actors**: same as REQ-SESS-001 (kiosk device or authenticated web caller).
- **Preconditions**: target session exists and is currently `OPEN`.
- **Input**: `{request_id, good_qty?, defect_qty?, rework_qty?, note?, occurred_at?}`.
- **Trigger**: `POST /work-sessions/<id>/finish`, or Kiosk v2 `QUANTITY_SUBMITTED` event.
- **Main flow**: §6.2 in full.
- **Expected output**: `status=CLOSED`, `quantity_confirmed=TRUE`, quantities recorded; Operation status recomputes.
- **State transition**: `OPEN → CLOSED` (manual path, §5.1's left branch).
- **Validation**: quantities clamped ≥0; `rework_qty ≤ defect_qty` (else `ValueError`).
- **Errors**: already-`CLOSED` session → `409`, "session already closed"; input-flow insufficient stock → `409` naming the exact available quantity (§8's material formula in §6.2's cross-reference); time overlap → refused.
- **Boundary**: `rework_qty` exactly equal to `defect_qty` must succeed; `rework_qty = defect_qty + 1` must fail.
- **Permission**: N/A at this call itself (see REQ-SESS-001).
- **Concurrency**: same `request_id` idempotency guarantee as start.
- **Audit**: `SESSION_FINISHED` audit row + one domain event per quantity-movement type recorded, same transaction.
- **Related**: §6.2, BR-005/BR-006 (quantity rules), REQ-EXC-001 (`ZERO_QUANTITY_LONG` if 0/0 after >4h).
- **Priority**: P0.
- **Dimensions**: positive, negative, boundary, concurrency, idempotency, state transition.

### REQ-SESS-003 — Batch finish (atomic)

- **Module**: Session
- **Purpose**: Close multiple sessions as one all-or-nothing operation.
- **Actors**: same callers as finish.
- **Preconditions**: all target sessions currently `OPEN`.
- **Input**: array of `(session_id, data)` pairs, each shaped like REQ-SESS-002's input.
- **Trigger**: `POST /session/group/finish`.
- **Main flow**: §6.3 — single shared transaction across the whole array.
- **Expected output**: array of per-item responses in the same order as input, all succeeded.
- **State transition**: all targeted sessions `OPEN → CLOSED` together, or none.
- **Validation**: same per-item rules as REQ-SESS-002.
- **Errors**: **first item that fails rolls back the entire batch** — a batch of 5 where item 3 fails must leave all 5 sessions still `OPEN`, not 2 closed + 3 pending.
- **Boundary**: a batch of exactly 1 item behaves identically to a single finish call; an empty array — confirm behavior (likely a no-op `200`, verify rather than assume).
- **Permission**: N/A at this call itself.
- **Concurrency**: the whole batch is one transaction — no partial-commit race is possible by construction.
- **Audit**: one `SESSION_FINISHED` (+ movement events) per successfully-closed item within the same transaction.
- **Related**: REQ-SESS-002.
- **Priority**: P1.
- **Dimensions**: positive, negative (rollback proof), boundary.

### REQ-SESS-004 — Supervisor quantity correction (adjust)

- **Module**: Session
- **Purpose**: Let a supervisor/admin fix wrong quantities after the fact, with a mandatory reason and full audit trail.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: session exists (may be `OPEN` or `CLOSED`).
- **Input**: `{good_qty?, defect_qty?, rework_qty?, reason, request_id?}` — `reason` is **required**.
- **Trigger**: `POST /supervisor/sessions/<id>/adjust`.
- **Main flow**: §6.5 in full.
- **Expected output**: `200` with the adjustment record (old/new for each quantity field) and the updated session.
- **State transition**: `quantity_confirmed → TRUE` unconditionally (regardless of its prior value) — this is the primary state effect of this action, distinct from `status` itself.
- **Validation**: `reason` non-empty (else `ValueError`, "reason required"); `rework_qty ≤ defect_qty` (same rule as finish).
- **Errors**: empty reason → `ValueError`; excess rework → `ValueError`.
- **Boundary**: correcting an **auto-closed, unconfirmed** session (`quantity_confirmed=FALSE`) is the primary real-world case this exists for — confirm it flips to `TRUE` afterward (§6.4/§9.1's `AUTO_CLOSED_UNCONFIRMED` case resolution path).
- **Permission**: admin, manager, supervisor; operator, viewer → `403`.
- **Concurrency**: optional `request_id` gives the same idempotent-replay guarantee as start/finish.
- **Audit**: `operation_adjustments` row (old/new for good/defect/rework, `reason`, `adjusted_by`) + `VALUE_CHANGED` domain event, same transaction.
- **Related**: §6.5, §6.4 (the auto-close→correction journey), REQ-SESS-002.
- **Priority**: P0.
- **Dimensions**: positive, negative, boundary, RBAC, state transition (confirmed flag), audit.

### REQ-SESS-005 — Full session edit (optimistic concurrency)

- **Module**: Session
- **Purpose**: Broader edit than a quantity-only adjust, with stale-write protection.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: session exists.
- **Input**: editable session fields + optional `expected_updated_at`.
- **Trigger**: `PATCH /supervisor/sessions/<id>`.
- **Main flow**: §6.6.
- **Expected output**: `200` with the updated session on success.
- **State transition**: whatever fields changed.
- **Validation**: if `expected_updated_at` is supplied and does not match the row's actual current `updated_at`, refuse.
- **Errors**: mismatch → conflict (someone else edited it first) — must **not** silently overwrite.
- **Boundary**: two supervisors loading the same session, one saves first, the second's save (with the now-stale `expected_updated_at`) must be refused, not silently applied over the first save.
- **Permission**: admin, manager, supervisor; operator, viewer → `403`.
- **Concurrency**: this is the primary concurrency mechanism to test — a real two-actor race, not a single-actor retried request.
- **Audit**: N/A confirmed distinctly from `adjust`'s audit shape — verify which audit action name this specific route writes.
- **Related**: §6.6, REQ-SESS-004.
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary, RBAC, concurrency.

### REQ-SESS-006 — Transfer Operation ("giao nhầm Operation")

- **Module**: Session
- **Purpose**: Correct a session mistakenly recorded against the wrong Operation.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: session exists; target Operation exists.
- **Input**: `{new_operation_id, reason?}`.
- **Trigger**: `POST /supervisor/sessions/<id>/transfer-operation`.
- **Main flow**: §6.7 — reassign `operation_id`, recompute both the old and new Operation's status.
- **Expected output**: `200` with the session now pointing at the new Operation.
- **State transition**: session's `operation_id` changes; both old and new Operation's `status` recompute per §5.2.
- **Validation**: N/A confirmed beyond target-Operation existence.
- **Errors**: N/A confirmed distinctly.
- **Boundary**: transferring to the **same** Operation it already belongs to — confirm this is either a harmless no-op or explicitly rejected (verify rather than assume either).
- **Permission**: admin, manager, supervisor; operator, viewer → `403`.
- **Concurrency**: N/A confirmed.
- **Audit**: captures before/after Operation on the audit row.
- **Related**: §6.7, JOURNEY (§18) "giao nhầm Operation."
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary, RBAC, audit.

### REQ-SESS-007 — Exclude / restore a session from reports

- **Module**: Session
- **Purpose**: Let a supervisor mark a session's data as not-to-be-counted (e.g. duplicate/test scan) without deleting it.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: exclude — session not already excluded; restore — session currently excluded.
- **Input**: `{reason}` — required for both.
- **Trigger**: `POST /supervisor/sessions/<id>/exclude`, `.../restore`.
- **Main flow**: §6.8.
- **Expected output**: `200`; `excluded_from_reports` flips; session `status` untouched, row never deleted.
- **State transition**: `excluded_from_reports: FALSE→TRUE` (exclude) or `TRUE→FALSE` (restore); independent of `status`.
- **Validation**: `reason` required for both directions.
- **Errors**: exclude on an already-excluded session → `409`, "Session đã được loại khỏi báo cáo"; restore on a not-excluded session → `409`, "Session hiện không bị loại khỏi báo cáo".
- **Boundary**: exclude → restore → exclude again in sequence must each succeed in turn (no permanent one-way lock).
- **Permission**: admin, manager, supervisor; operator, viewer → `403`.
- **Concurrency**: N/A confirmed.
- **Audit**: `SESSION_EXCLUDED`/`SESSION_RESTORED` domain event with the reason.
- **Related**: §6.8, BR-010 (§16), REQ-PROD-001 (excluded sessions vanish from KPI).
- **Priority**: P1.
- **Dimensions**: positive, negative (double-exclude/restore), boundary, RBAC, audit.

## 15.8 Kiosk (`REQ-KIOSK-*`)

Full end-to-end workflow with every branch is §7 — these requirements
are the test-entry-points into it.

### REQ-KIOSK-001 — Kiosk v1 scan/start/finish (browser)

- **Module**: Kiosk v1
- **Purpose**: Manual/demo-friendly browser-based kiosk flow.
- **Actors**: no role check — browser-facing, unauthenticated device flow (§7.1).
- **Preconditions**: valid employee/Operation QR values exist.
- **Input**: `{qr}` per scan; start/finish inputs identical to REQ-SESS-001/002.
- **Trigger**: `POST /api/kiosk-web/scan`, `/start`, `/finish/<id>`.
- **Main flow**: §7.1's 3-step table.
- **Expected output**: same session-lifecycle outcomes as the web session routes, reached through the kiosk-shaped endpoints.
- **State transition**: identical to REQ-SESS-001/002.
- **Validation**: `qr` required and non-empty for scan.
- **Errors**: empty `qr` → `400 QR_REQUIRED`, `error_code SCN-001`, "Chưa nhận được mã quét", action hint "Kiểm tra nguồn và dây máy quét, rồi quét lại."; all downstream errors identical to REQ-SESS-001/002.
- **Boundary**: same as REQ-SESS-001/002 (this is the same business logic reached through a different door).
- **Permission**: N/A (no role gate on this flow).
- **Concurrency**: same idempotency guarantees as REQ-SESS-001/002.
- **Audit**: same as REQ-SESS-001/002.
- **Related**: §7.1, REQ-SESS-001/002.
- **Priority**: P0.
- **Dimensions**: positive, negative, boundary.

### REQ-KIOSK-002 — Kiosk v2 device state machine (ESP32 protocol)

- **Module**: Kiosk v2
- **Purpose**: Real hardware-facing kiosk protocol, one shared device serving a sequence of employees.
- **Actors**: authenticated device (per-device token), not a user role.
- **Preconditions**: device is registered and not `DEVICE_DISABLED`/`MAINTENANCE`.
- **Input**: events — `SCAN {raw}`, `FINISH_REQUESTED`, `QUANTITY_SUBMITTED {...}`, `CANCEL_REQUESTED`, each carrying a unique `event_id`.
- **Trigger**: `POST /api/kiosk/v2/events`.
- **Main flow**: full transition table §7.2 — every row must be its own test case, both the allowed transition and its explicitly-listed rejection.
- **Expected output**: new device-projection state + (where applicable) a real session created/finished per REQ-SESS-001/002's rules.
- **State transition**: the full table in §7.2.
- **Validation**: QR must parse as `WF|EMP|<key>` or `WF|OP|<key>` (§7.2); anything else → unparseable, rejected.
- **Errors**: `STATE_INVALID_TRANSITION`, `OPERATION_NOT_WORKABLE`, `EMPLOYEE_NOT_FOUND`, `OPERATION_NOT_FOUND`, `DEVICE_NOT_ALLOWED`, `SESSION_NOT_OPEN` — each with its own trigger condition in §7.2/§11.2.
- **Boundary**: an `EMP` scan for an employee who has an open session **on a different device** than the one currently scanning — the fresh-resolve rule (§7.2) means it must still route to `QUANTITY_INPUT` on **this** device, proving device state is per-device, not per-employee-sticky.
- **Permission**: N/A (device-token auth, not role-based).
- **Concurrency**: idempotent per `(device_id, event_id)` — a duplicated/retried event must not double-apply.
- **Audit**: each successful scan/session action writes its own `SCAN_EMPLOYEE`/`SCAN_OPERATION`/etc. kiosk event row.
- **Related**: §7.2 in full, REQ-SESS-001/002.
- **Priority**: P0.
- **Dimensions**: positive, negative (every rejection row), boundary, concurrency, state transition (every table row).

### REQ-KIOSK-003 — Kiosk shared-terminal correctness (sequential multi-employee use)

- **Module**: Kiosk v2
- **Purpose**: Prove one physical kiosk device can serve employee A, then B, then C in sequence, with each employee's later card-scan resolving only to their own open session, never to another employee's session or device state left over from before.
- **Actors**: device (multiple employees using it in turn).
- **Preconditions**: employees A, B, C all exist and are active; at least one workable Operation.
- **Input**: sequential scans: A(EMP)→A(OP, starts a session)→B(EMP)→B(OP, starts a session)→C(EMP)→C(OP, starts a session).
- **Trigger**: sequence of `POST /api/kiosk/v2/events` calls on the **same** `device_id`.
- **Main flow**: after each employee's OP scan, the device resets to `WAIT_EMPLOYEE` (§7.2) — the very next scan is evaluated fresh against whichever employee just scanned, never influenced by the previous employee's still-open session.
- **Expected output**: three independent `OPEN` sessions exist (one per employee), all on the same `device_uuid`/`station_id`; each employee's later `EMP` scan on this same device sets the device's `employee_id`/`work_session_id` to **that employee's own** session id, never another employee's.
- **State transition**: device cycles `WAIT_EMPLOYEE → WAIT_OPERATION → WAIT_EMPLOYEE` three times in a row, once per employee.
- **Validation**: N/A beyond REQ-KIOSK-002.
- **Errors**: N/A (this is the positive, previously-broken case — a regression here would incorrectly surface `SESSION_EMPLOYEE_MISMATCH` or similar, per the historical incident this exact rule was fixed for).
- **Boundary**: B scanning their card while A's session is still open on the same device is the exact previously-broken case — must succeed cleanly.
- **Permission**: N/A.
- **Concurrency**: N/A (sequential by nature of one physical scanner).
- **Audit**: three independent `SCAN_EMPLOYEE`/`SCAN_OPERATION` event sequences.
- **Related**: §7.2, REQ-KIOSK-002. This is the required "chuyển qua nhiều nhân viên" demo scenario for the tutorial video.
- **Priority**: P0.
- **Dimensions**: positive, boundary (the specific historical regression case).

### REQ-KIOSK-004 — Kiosk productivity wallboard

- **Module**: Kiosk / Employee Productivity
- **Purpose**: Shop-floor TV display of ranked employee productivity, refreshed continuously, no login required (public within the trusted network).
- **Actors**: unauthenticated (deliberately — a shop-floor display).
- **Preconditions**: a published wallboard config exists (or defaults apply); reportable sessions exist in range.
- **Input**: none from the viewer; config is set separately by an admin/manager (`POST /reports/employee-productivity/wallboard-config`).
- **Trigger**: `GET /api/wallboard/employee-productivity`, and the `/kiosk/employee-productivity` page.
- **Main flow**: reads the exact same query as §8's formula — ranked employee list, configurable sort/columns/page-size/auto-flip-interval.
- **Expected output**: same numbers as the authenticated Employee Productivity report for the same date range (REQ-PROD-001) — must never diverge.
- **State transition**: N/A (read-only).
- **Validation**: N/A for the read path.
- **Errors**: N/A confirmed.
- **Boundary**: a "Preview" of a not-yet-published config change must **not** mutate what the public wallboard currently shows (confirmed, specifically tested requirement).
- **Permission**: **no auth required** for the data endpoint itself — this is deliberate, not a bug; do not flag it as a security gap without first confirming it is not the intended design (it is, per direct code confirmation).
- **Concurrency**: N/A.
- **Audit**: N/A (read-only).
- **Related**: §8 (KPI formula), REQ-PROD-001, REQ-KIOSK-003 (the sequential multi-employee demo this wallboard should visibly reflect afterward).
- **Priority**: P0 — this is the tutorial's explicitly required "Kiosk năng suất nhân viên" chapter subject.
- **Dimensions**: positive, boundary (preview-does-not-mutate), unauth access (confirm intended).

## 15.9 Shift / Auto-close (`REQ-SHIFT-*`)

Full detail in §6.4 and §4.10's `work_shifts`/`work_shift_intervals`
schema — requirements below are the test-entry-points.

### REQ-SHIFT-001 — Shift definition and interval editing

- **Module**: Working Calendar
- **Purpose**: Define the WORK/BREAK interval structure of each shift, including cross-midnight shifts.
- **Actors**: view — any role with `calendar.view` (admin/manager/supervisor/viewer); edit — admin, manager.
- **Preconditions**: none.
- **Input**: `{code, name, anchor_start, anchor_end, cross_midnight, target_minutes, working_weekdays[], intervals:[{interval_type, start_minute, end_minute, label}]}`.
- **Trigger**: `GET/PUT /settings/work-shifts`.
- **Main flow**: intervals are shift-relative minutes, not wall-clock; `cross_midnight=true` shifts (e.g. the seeded `NIGHT` 18:00–03:00) span past minute 1440.
- **Expected output**: `200` with the stored shift definition.
- **State transition**: N/A.
- **Validation**: each interval's `end_minute > start_minute` (DB CHECK constraint); `interval_type` ∈ `{WORK, BREAK}`.
- **Errors**: an interval violating `end > start` → rejected.
- **Boundary**: two intervals overlapping in time within the same shift, and a gap between two intervals — both are real, distinctly-handled cases the shift editor UI itself validates (warns on gaps, errors on overlaps per the editor's own validation logic) — test both.
- **Permission**: admin, manager write; admin/manager/supervisor/viewer read.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly.
- **Related**: §4.10, REQ-SHIFT-002.
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary (overlap vs. gap), RBAC.

### REQ-SHIFT-002 — Auto-close a session past shift end + grace

- **Module**: Session / Shift
- **Purpose**: Force-close sessions abandoned past their shift's end, without fabricating data or disguising the action as a manual finish.
- **Actors**: system job (`shift_session_reconciliation`), not user-triggered.
- **Preconditions**: `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1` and `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=0` (both required — the rollout-safety defaults leave this off, §6.4); a session is `OPEN` and its resolved shift's end-time + grace period has passed.
- **Input**: none (system-driven; internally computes `shift_end_at` per session from §4.10's shift/interval data).
- **Trigger**: scheduled job run (not an API call a test can invoke directly in the same way — test via the job's own entry point or by fast-forwarding a fixture's clock, per the test harness's own capability).
- **Main flow**: §6.4 in full.
- **Expected output**: session `CLOSED`, quantities unchanged from whatever they were, `close_reason='AUTO_SHIFT_END'`, `closed_by_system=TRUE`, `quantity_confirmed=FALSE`.
- **State transition**: `OPEN → CLOSED` via the auto-close branch of §5.1 (distinct from the manual-finish branch).
- **Validation**: `shift_end_at` must be strictly after the session's `started_at` (else the job raises rather than writing an impossible interval — this is an internal consistency guard, not a user-facing validation).
- **Errors**: overlap with another session for the same employee → refused, same as a manual finish would be.
- **Boundary**: a session that gets manually finished by the operator in the same moment the reconciliation job would have auto-closed it — the job's advisory lock + `status != OPEN` re-check makes this a safe no-op for the job (§6.4), never a double-close or an error.
- **Permission**: N/A (system-only).
- **Concurrency**: per-session advisory lock; concurrent reconciliation runs must never double-close the same session.
- **Audit**: `SESSION_AUTO_CLOSED` domain event (distinct type from `SESSION_FINISHED`) + audit row.
- **Related**: §6.4, REQ-SESS-004 (the correction that follows), REQ-EXC-002 (`SESSION_PAST_SHIFT_END` while still open).
- **Priority**: P0.
- **Dimensions**: positive, boundary, concurrency, state transition, audit. This is a **required tutorial error-scenario**: "quên nhập sản lượng khi kết thúc" / "session vượt giờ kết thúc ca."

## 15.10 Exception Handling (`REQ-EXC-*`)

Full detection-condition table is §9.1; lifecycle is §5.4/§5.5.

### REQ-EXC-001 — Exception Center: detection

- **Module**: Exception Center
- **Purpose**: Automatically surface the 7 known anomaly conditions as durable, deduplicated records.
- **Actors**: system-triggered; viewed by any role with `exceptions.view` (admin/manager/supervisor/viewer).
- **Preconditions**: one of §9.1's 7 trigger conditions is true for a reportable session/Operation.
- **Input**: none (continuous reconciliation).
- **Trigger**: reconciliation cycle (background) or `GET /exceptions` (list, which reflects currently-detected + previously-recorded state).
- **Main flow**: §9.1's condition table, each producing `fingerprint = "<type>:SESSION:<session_id>"`.
- **Expected output**: a new `exception_records` row per newly-detected condition, `status=OPEN`.
- **State transition**: (no record) → `OPEN` (§5.4).
- **Validation**: N/A (detection is a pure derivation).
- **Errors**: N/A (detection cannot itself error out for a valid session; a session already excluded via `excluded_from_reports` never triggers detection at all — §9.1's explicit fix).
- **Boundary**: a session at **exactly** 12h00m00s open — confirm whether `LONG_OPEN_SESSION`'s "more than 12 hours" is a strict `>` (session at exactly 12:00:00 should NOT yet trigger) — test the boundary precisely, do not assume.
- **Permission**: view: admin/manager/supervisor/viewer (`exceptions.view`); operator lacks this permission entirely.
- **Concurrency**: N/A (detection is idempotent by fingerprint — re-running reconciliation never creates a duplicate active record for the same condition).
- **Audit**: `exception_history` gets an append-only row for the detection itself.
- **Related**: §9.1, REQ-EXC-002/003.
- **Priority**: P0.
- **Dimensions**: positive (all 7 conditions), boundary (threshold edges), RBAC.

### REQ-EXC-002 — Exception Center: acknowledge / resolve / ignore

- **Module**: Exception Center
- **Purpose**: Human triage workflow for a detected exception.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: an `OPEN` (or, for resolve/ignore, `ACKNOWLEDGED`) exception record exists.
- **Input**: `{expected_version, reason?}`.
- **Trigger**: `POST /exceptions/<id>/acknowledge`, `/resolve`, `/ignore`.
- **Main flow**: §5.4's transition diagram; version-checked against `row_version`.
- **Expected output**: `200` with the updated record (`status`, incremented `row_version`).
- **State transition**: `OPEN→ACKNOWLEDGED`, `OPEN|ACKNOWLEDGED→RESOLVED`, `OPEN|ACKNOWLEDGED→MANUAL_IGNORED`.
- **Validation**: `expected_version` must match the record's current `row_version`.
- **Errors**: version mismatch → refused (someone else already actioned it) — a real, testable optimistic-concurrency case, not theoretical.
- **Boundary**: attempting to `resolve` an already-`RESOLVED` record — must be refused (not idempotently accepted) since it's a terminal state and the version will already have moved.
- **Permission**: admin, manager, supervisor; operator, viewer → `403`.
- **Concurrency**: two supervisors racing to acknowledge the same exception — version check ensures only the first succeeds.
- **Audit**: `exception_history` row per transition (append-only).
- **Related**: §5.4, REQ-EXC-003 (correct-session from within this flow).
- **Priority**: P0.
- **Dimensions**: positive, negative, boundary, RBAC, concurrency.

### REQ-EXC-003 — Correct a session directly from its exception

- **Module**: Exception Center
- **Purpose**: Let a supervisor fix the underlying session without leaving the exception detail view.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: exception record references a real session.
- **Input**: same shape as REQ-SESS-004/005 (this opens the same correction flow, just contextually from the exception).
- **Trigger**: `POST /session-exceptions/<id>/correct-session`.
- **Main flow**: applies REQ-SESS-004/005's rules; the modal/drawer does **not** auto-close on save (§17 UI requirement) so the user sees the before/after state.
- **Expected output**: session corrected exactly as REQ-SESS-004 describes; the exception itself is not automatically resolved by this action alone (a separate explicit `resolve` call is still required — verify this is true rather than assumed).
- **State transition**: session-side per REQ-SESS-004; exception-side unchanged unless separately resolved.
- **Validation**: same as REQ-SESS-004.
- **Errors**: same as REQ-SESS-004.
- **Boundary**: same as REQ-SESS-004.
- **Permission**: admin, manager, supervisor.
- **Concurrency**: same as REQ-SESS-004.
- **Audit**: same as REQ-SESS-004, plus the exception's own history if it is separately resolved afterward.
- **Related**: REQ-SESS-004, REQ-EXC-002, JOURNEY §18 (zero-qty → exception → resolve).
- **Priority**: P1.
- **Dimensions**: positive, boundary, RBAC.

### REQ-EXC-004 — Legacy Session Exceptions workflow

- **Module**: Session Management (legacy exceptions)
- **Purpose**: Older, simpler per-session review workflow still live on Session Management.
- **Actors**: admin, manager, supervisor.
- **Preconditions**: a `session_exception_reviews` record exists.
- **Input**: `{status}` transition.
- **Trigger**: `PATCH /session-exceptions/workflow`.
- **Main flow**: §5.5 — `NEW→IN_PROGRESS→RESOLVED`, or `→IGNORED` from either.
- **Expected output**: `200` with the updated review row.
- **State transition**: §5.5's 4-value enum.
- **Validation**: `status` must be one of the 4 enum values (DB CHECK constraint).
- **Errors**: invalid status value → rejected.
- **Boundary**: transitioning directly `NEW→RESOLVED` (skipping `IN_PROGRESS`) — confirm whether this is allowed (the CHECK constraint alone does not forbid it; no further code-enforced ordering was confirmed — test and record the actual behavior rather than assuming either way).
- **Permission**: admin, manager, supervisor; operator, viewer → `403`.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly from Exception Center's `exception_history`.
- **Related**: §5.5, §4.9 — this is a **separate system** from REQ-EXC-001..003, do not conflate their codes/fingerprints.
- **Priority**: P2 (legacy, still live but Exception Center is primary).
- **Dimensions**: positive, negative, boundary, RBAC.

## 15.11 Employee Productivity / KPI (`REQ-PROD-*`)

Exact formulas are §8 — requirements below are the test-entry-points.

### REQ-PROD-001 — Employee Productivity report

- **Module**: Employee Productivity
- **Purpose**: Rank/report each employee's average completion percent over a date range.
- **Actors**: any role with `session.view` (all 6 roles hold `session.view` per §3.2 — verify this specific permission mapping since the nav entry itself uses `session.view`, not a dedicated `productivity.view` code).
- **Preconditions**: `CLOSED`, non-excluded sessions exist in the requested range.
- **Input**: `{from, to, employee_id?, department?, team?, limit?}`.
- **Trigger**: `GET /reports/employee-productivity`, `/reports/employee-productivity/<employee_id>` (detail).
- **Main flow**: §8's formula in full.
- **Expected output**: ranked employee list with `completed_sessions`, `completed_valid_sessions`, `completed_invalid_sessions`, `productivity_percent`, `good_qty`/`defect_qty`, plus a `summary` block (`employee_count`, `completed_sessions`, `avg_employee_productivity_percent`, `total_good_qty`, `total_defect_qty`, `top_employee`).
- **State transition**: N/A (read-only).
- **Validation**: `from`/`to` must be valid dates.
- **Errors**: N/A confirmed for the read path itself.
- **Boundary**: an employee whose only sessions in range are `OPEN`, or whose sessions are all `excluded_from_reports=TRUE` — must not appear in the list at all, never as a `0%` row (§8).
- **Permission**: all 6 roles (via `session.view`).
- **Concurrency**: N/A.
- **Audit**: N/A (read-only).
- **Related**: §8 in full, §13.4's sample-data table (ready-to-use test fixtures for every formula edge case), REQ-KIOSK-004.
- **Priority**: P0.
- **Dimensions**: positive, boundary (every §8 edge case), empty-state.

### REQ-PROD-002 — Wallboard publish config

- **Module**: Employee Productivity / Kiosk
- **Purpose**: Let admin/manager configure what the public Kiosk wallboard shows.
- **Actors**: admin, manager (publish); any role with `session.view` (get current config).
- **Preconditions**: none.
- **Input**: `{mode: fixed|dynamic, from?, to?, department?, sort, employees_per_page, auto_page_flip_seconds, columns[]}`.
- **Trigger**: `GET/POST /reports/employee-productivity/wallboard-config`.
- **Main flow**: validated config is stored; the public wallboard (REQ-KIOSK-004) reads it on every refresh.
- **Expected output**: `200` with the stored config.
- **State transition**: N/A (config, not a lifecycle entity).
- **Validation**: `mode=fixed` requires both `from` and `to`; `from` must not be after `to`; `sort` must be a known value; `employees_per_page` and `auto_page_flip_seconds` within valid ranges; `columns` must be known column names.
- **Errors**: each validation failure has its own specific rejection (fixed-mode-without-dates, from-after-to, unknown-sort, out-of-range-page-size, invalid-employees-per-page, invalid-columns, invalid-auto-page-flip-seconds) — 7 distinct negative cases, all independently confirmed to exist.
- **Boundary**: `employees_per_page` at its exact min/max boundary values.
- **Permission**: publish: admin, manager only (supervisor/operator/viewer → `403`, specifically confirmed for viewer); read: broader.
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly.
- **Related**: REQ-KIOSK-004, REQ-PROD-001.
- **Priority**: P1.
- **Dimensions**: positive, negative (all 7 validation cases), boundary, RBAC.

## 15.12 Search / Filter / Pagination (`REQ-SEARCH-*`)

### REQ-SEARCH-001 — Bounded list responses

- **Module**: cross-cutting
- **Purpose**: Prevent unbounded full-table responses.
- **Actors**: any role reading a list endpoint.
- **Preconditions**: more rows exist than the default/max limit.
- **Input**: optional `limit` param, screen-dependent.
- **Trigger**: any list `GET` (e.g. `GET /work-sessions`, default limit 200; `GET /reports/employee-productivity`, default limit 1000).
- **Main flow**: server caps the returned row count at a fixed default unless a smaller `limit` is requested.
- **Expected output**: response row count ≤ the endpoint's documented default/max.
- **State transition**: N/A.
- **Validation**: `limit`, if given, is clamped into a sane range (verify the exact min/max per endpoint rather than assuming a universal constant).
- **Errors**: N/A confirmed.
- **Boundary**: requesting `limit` far above the max — confirm it's clamped down, not honored literally (a potential real gap if not clamped — test explicitly).
- **Permission**: inherits the host endpoint's permission.
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: REQ-PROD-001.
- **Priority**: P2.
- **Dimensions**: positive, boundary.

## 15.13 Tutorial / Help (`REQ-TUT-*`)

### REQ-TUT-001 — Tutorial manifest and video serving

- **Module**: Tutorial
- **Purpose**: Serve the video-guide library to authenticated users only, with path-traversal protection.
- **Actors**: any authenticated role (no specific permission code — `login_required` only).
- **Preconditions**: a `manifest.json` and its referenced video files exist under the configured tutorial directory.
- **Input**: none for the manifest; `filename` path segment for a specific video.
- **Trigger**: `GET /api/tutorials`, `GET /tutorials/<filename>`.
- **Main flow**: 1) require a valid session. 2) read the manifest. 3) filter its `items` to only those whose `file` resolves to a real, existing file **under** the configured root — entries pointing outside the root (`..`, absolute paths) are silently dropped, never served.
- **Expected output**: `200` with the filtered manifest; a valid video file streams with `Content-Type: video/mp4` and correct `Content-Length`.
- **State transition**: N/A.
- **Validation**: path containment check on every `file` value.
- **Errors**: no session → `401`; a `filename` outside the root, or non-existent → `404`.
- **Boundary**: a manifest entry with `file: "../../etc/passwd"` or an absolute path — must be excluded from the returned list, and a direct request for it must `404`, not serve anything.
- **Permission**: `login_required` only, no finer-grained permission — every authenticated role can access every published video.
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: §2 (nav entry), the full chapter list is a **living artifact**, not spec'd by ID here — see §21 for the specific "15 vs 14" historical defect and its regression-test requirement.
- **Priority**: P0 (the path-traversal protection is a real security boundary).
- **Dimensions**: positive, negative (path traversal), boundary, empty-state (zero videos published).

## 15.14 Admin / System (`REQ-SYS-*`)

### REQ-SYS-001 — Users & Roles management

- **Module**: Users & Roles
- **Purpose**: Manage accounts and their role assignment; manage which permissions each role grants.
- **Actors**: view: `users.view` (admin only, per §3.2's grant table — note this is narrower than most view permissions); manage: `users.manage`/`roles.manage` (admin only).
- **Preconditions**: none for list; target user/role exists for edit.
- **Input**: create — `{username, display_name, password, role}`; edit — subset of the same; role-permission update — `{permission_codes[]}`.
- **Trigger**: `GET/POST /users`, `PATCH /users/<id>`, `POST /users/<id>/reset-password`, `GET /roles`, `PUT /roles/<role_code>/permissions`.
- **Main flow**: standard CRUD, plus the special-case in §3.3 rule 1 (editing `admin`'s permissions has no effect).
- **Expected output**: `200` with the affected row(s).
- **State transition**: N/A (not a lifecycle entity).
- **Validation**: `role` must be one of the 6 valid codes; permission-update payload's every code must exist in the catalog (§3.1) — an unknown code → `ValueError`, "Unknown permissions: {codes}".
- **Errors**: unknown role/permission code → rejected; see §11.
- **Boundary**: submitting `role_code=admin` to `PUT /roles/admin/permissions` with an explicitly reduced permission list — must be silently overridden back to the full set (§3.3 rule 1 — a real, specifically testable no-op).
- **Permission**: admin only for every write in this module; `users.view` for list (admin only per the grant table).
- **Concurrency**: N/A confirmed.
- **Audit**: N/A confirmed distinctly (verify presence of a user/role-change audit row).
- **Related**: §3 in full (RBAC matrix).
- **Priority**: P0 (RBAC self-management — a bug here can cascade into every other permission check).
- **Dimensions**: positive, negative, boundary (admin-row no-op), RBAC.

### REQ-SYS-002 — Self-service password change

- **Module**: Users & Roles
- **Purpose**: Let any logged-in user change their own password.
- **Actors**: any authenticated role.
- **Preconditions**: authenticated session.
- **Input**: `{current_password, new_password}`.
- **Trigger**: `POST /auth/change-password`.
- **Main flow**: 1) verify `current_password` against the caller's own hash. 2) if correct, hash and store `new_password`; always acts on the **caller's own** account, never a `user_id` parameter.
- **Expected output**: `200` on success.
- **State transition**: N/A.
- **Validation**: password-strength rule (exact rule not fully confirmed in this pass — see §21 gap; test with an obviously-weak password and record actual behavior rather than assuming a specific policy).
- **Errors**: wrong `current_password` → rejected.
- **Boundary**: N/A confirmed beyond the password-strength gap above.
- **Permission**: any authenticated role — this is self-service, not permission-gated beyond having a session.
- **Concurrency**: N/A.
- **Audit**: N/A confirmed distinctly.
- **Related**: REQ-SYS-001.
- **Priority**: P1.
- **Dimensions**: positive, negative, boundary.

### REQ-SYS-003 — System Console (Super Admin only)

- **Module**: System Console
- **Purpose**: Technical health/diagnostics/service-control area, entirely separate from ordinary business administration.
- **Actors**: **super_admin only** — never `admin`, even though `admin` has the business-permission bypass elsewhere (§3.3 rule 2).
- **Preconditions**: `super_admin` session.
- **Input**: screen-dependent (service id for restart, component name for diagnostics run, etc.).
- **Trigger**: `GET/POST /api/system-health/errors|services|diagnostics|audit`, `POST /api/system-health/services/<id>/restart`, `POST /api/system-health/diagnostics/<component>`.
- **Main flow**: role-string check, not permission-table check (§3.3 rule 2) — literal `session.role == 'super_admin'`.
- **Expected output**: `200` with the requested technical data/action result for `super_admin`.
- **State transition**: service-restart actions change the target service's running state (out of scope for this document's data model — treat as an infrastructure action, not a MESFlow domain-entity transition).
- **Validation**: N/A confirmed beyond the role check.
- **Errors**: any role other than `super_admin`, **including `admin`**, → `403`, "Chỉ Super Admin mới có quyền truy cập khu vực Hệ thống."
- **Boundary**: an `admin` session (not `super_admin`) is the critical boundary case — must be refused despite `admin`'s blanket bypass everywhere else in the system (§3.3's explicit exception).
- **Permission**: literal role string `super_admin` only.
- **Concurrency**: N/A confirmed for this document's scope.
- **Audit**: `system-audit` page/API specifically exists to show who did what here — self-referential audit trail for this module.
- **Related**: §2 (nav entries), §3.3 rule 2.
- **Priority**: P0 (this is the most security-sensitive boundary in the whole system — a leak here means an ordinary admin could restart production services).
- **Dimensions**: positive, negative (admin-must-fail boundary — the single most important RBAC test case in the system), RBAC.

## 15.15 Audit / History (`REQ-AUDIT-*`)

### REQ-AUDIT-001 — Action logs & error traces (admin-only)

- **Module**: System Logs
- **Purpose**: Technical action/error logging distinct from business audit and from System Console.
- **Actors**: **admin only** (`roles.manage`-gated, §3.4's `@admin_required` decorator — narrower than most admin+manager pairs elsewhere).
- **Preconditions**: log entries exist.
- **Input**: filter params (date range, resolved/unresolved, etc.).
- **Trigger**: `GET /action-logs`, `/error-traces`, `/log-retention/*`.
- **Main flow**: standard filtered list/detail/resolve.
- **Expected output**: `200` with the filtered log list.
- **State transition**: a log entry can be marked resolved.
- **Validation**: N/A confirmed beyond filter parsing.
- **Errors**: N/A confirmed distinctly.
- **Boundary**: N/A confirmed.
- **Permission**: **admin only** — manager, despite holding many other admin-equivalent permissions elsewhere, is **not** granted `logs.manage`/access to this specific screen per §3.2's grant table (manager does hold `logs.view` only, which maps to a *different*, narrower nav-visible screen — verify the exact split between `logs.view` and this admin-only action-log/error-trace area during test design, since the grant table shows `manager: logs.view` but this requirement's route decorator is `@admin_required`; this is a nuance worth a dedicated boundary test rather than assuming consistency).
- **Concurrency**: N/A.
- **Audit**: this **is** the audit/log system itself.
- **Related**: §3.2, REQ-SYS-003 (a related but distinct, even-more-restricted system-level log area).
- **Priority**: P1.
- **Dimensions**: positive, RBAC (admin vs. manager boundary — verify precisely).

### REQ-AUDIT-002 — Business audit trail

- **Module**: Business Audit
- **Purpose**: Human-readable "who changed what, when, why" trail across PO/Session/quantity/exception changes.
- **Actors**: `business_audit.view` — held by manager, supervisor (not admin directly in the grant table, though admin's bypass makes it accessible in practice — §3.2/§3.3).
- **Preconditions**: business changes have occurred.
- **Input**: filter params (entity type, date range, actor).
- **Trigger**: `GET /audit-logs`.
- **Main flow**: reads the same underlying audit rows every state-changing action in this document writes (REQ-PO-*, REQ-SESS-*, REQ-EXC-* all reference this).
- **Expected output**: `200` with a filtered, human-readable change list.
- **State transition**: N/A (read-only).
- **Validation**: N/A.
- **Errors**: N/A confirmed.
- **Boundary**: N/A confirmed.
- **Permission**: manager, supervisor (and admin via bypass); operator lacks it, viewer lacks it (per §3.2's grant table — neither is listed for `business_audit.view`).
- **Concurrency**: N/A.
- **Audit**: this IS the audit view.
- **Related**: every `**Audit**` field across Part B's other requirements feeds this screen.
- **Priority**: P1.
- **Dimensions**: positive, RBAC.

## 15.16 Cross-cutting API behavior (`REQ-API-*`)

### REQ-API-001 — Idempotency

- **Module**: cross-cutting
- **Purpose**: Guarantee a retried write (network flake, kiosk retry) never double-applies.
- **Actors**: any caller of an idempotency-keyed endpoint (start, finish, group-finish, adjust).
- **Preconditions**: an identical `request_id` was already successfully processed once.
- **Input**: identical payload including the same `request_id`.
- **Trigger**: any of REQ-SESS-001/002/003/004.
- **Main flow**: server recognizes the `request_id` in `kiosk_idempotency`, returns the stored original response instead of reprocessing.
- **Expected output**: identical response body to the first call, with `idempotent_replay: true` added.
- **State transition**: none on the retry (already applied on the first call).
- **Validation**: N/A.
- **Errors**: N/A — this is itself an error-prevention mechanism.
- **Boundary**: the same `request_id` reused with a **different** payload — confirm the server returns the original stored response (ignoring the new payload) rather than either erroring or applying the new payload (verify exact behavior, this is a meaningful edge case).
- **Permission**: N/A (orthogonal to permission checks).
- **Concurrency**: this is precisely the concurrency-safety mechanism (NFR-001).
- **Audit**: no duplicate audit rows on replay.
- **Related**: NFR-001, REQ-SESS-001/002.
- **Priority**: P0.
- **Dimensions**: positive, boundary (payload-mismatch case), concurrency.

### REQ-API-002 — PO-lock-first ordering (deadlock prevention)

- **Module**: cross-cutting
- **Purpose**: Prevent deadlocks under concurrent writes touching the same PO's Operations.
- **Actors**: any concurrent pair of start/finish/adjust/auto-close calls under the same PO.
- **Preconditions**: two or more concurrent calls target different Operations under the same PO.
- **Input**: N/A (an internal implementation guarantee, tested via concurrency, not a single request's input).
- **Trigger**: concurrent load test issuing simultaneous start/finish calls across multiple Operations of one PO.
- **Main flow**: every write path locks the PO row **first**, before any other row lock, in a fixed order.
- **Expected output**: all calls eventually complete (serialized, not deadlocked); none time out due to a lock-ordering conflict.
- **State transition**: N/A (this is a non-functional guarantee about *how* transitions happen under load).
- **Validation**: N/A.
- **Errors**: a deadlock error surfacing under concurrent load would be a **regression** of this guarantee.
- **Boundary**: the realistic worst case — many kiosks hitting many Operations of the *same* PO simultaneously (a busy shift-start moment) — is exactly the scenario this exists to keep correct.
- **Permission**: N/A.
- **Concurrency**: this **is** the concurrency requirement (NFR-002).
- **Audit**: N/A.
- **Related**: NFR-002.
- **Priority**: P0 (production-stability critical, not merely a nice-to-have).
- **Dimensions**: concurrency (load test).

### REQ-API-003 — Health/readiness contract

- **Module**: cross-cutting / Deploy
- **Purpose**: Give deploy tooling and QA an authoritative, unauthenticated liveness+readiness signal.
- **Actors**: unauthenticated (deploy scripts, monitoring).
- **Preconditions**: app process is running.
- **Input**: none.
- **Trigger**: `GET /api/system/ready`, `GET /api/system/version`.
- **Main flow**: `/ready` checks DB connectivity and reports `version`, `commit`, `migration_head`, `server_role`, `db_ok`, `schema_version`; `/version` returns only code-derived fields.
- **Expected output**: `200 {"ok": true, "status": "ready", ...}` when healthy.
- **State transition**: N/A.
- **Validation**: N/A.
- **Errors**: DB unreachable → `ok:false`/non-ready status (exact shape: verify against the live contract rather than assume).
- **Boundary**: N/A.
- **Permission**: **unauthenticated by design** — do not flag as a security gap.
- **Concurrency**: N/A.
- **Audit**: N/A.
- **Related**: NFR-006/007/008. **Important caution**: `/api/system/version`'s fields never identify *which physical host* answered — do not use it to conclude two endpoints are "the same server" (a real, confirmed investigation in this system's history found two genuinely different hosts reporting byte-identical version JSON).
- **Priority**: P0 (deploy-pipeline-critical).
- **Dimensions**: positive, negative (DB-down case).

---

# PART C — Business Rules

Independently numbered `BR-###`; a `REQ-*` may cite one or more.

| ID | Rule | Testable as |
|---|---|---|
| BR-001 | `admin` role bypasses the permission table entirely for ordinary business permissions — always allowed. | REQ-SYS-001 boundary case |
| BR-002 | `super_admin` gets `admin`'s business bypass but System Console access requires the literal role string, never satisfied by `admin`. | REQ-SYS-003 |
| BR-003 | An employee may have **at most one `OPEN` work session** at any time — DB-enforced, not merely app-level. | REQ-SESS-001 boundary |
| BR-004 | A downstream Operation with input-flow enabled cannot `start()` until its upstream source Operation has had **at least one session started** (not necessarily finished). | REQ-SESS-001 |
| BR-005 | `qty=0` on finish is never rejected; if the session was open > 4h, it is flagged `ZERO_QUANTITY_LONG` for review, not blocked. | REQ-SESS-002, REQ-EXC-001 |
| BR-006 | `rework_qty` can never exceed `defect_qty`, enforced on both finish and adjust. | REQ-SESS-002/004 boundary |
| BR-007 | A `CLOSED` session is **never deleted**, even when excluded from reports — history/audit is permanent; "exclude" only stops it counting toward aggregates. | REQ-SESS-007 |
| BR-008 | Auto-close is a dedicated lifecycle, not a disguised manual finish — distinguishable after the fact via `close_reason`/`closed_by_system`, and fires a different domain event. | REQ-SHIFT-002 |
| BR-009 | An auto-closed session is `quantity_confirmed=FALSE` until a human correction confirms it; any correction always sets it back `TRUE`. | REQ-SHIFT-002, REQ-SESS-004 |
| BR-010 | "Excluded from reports" affects **only** aggregation; the session's own status and its presence in history/audit are untouched. | REQ-SESS-007 |
| BR-011 | Material/input-flow constraint: a target Operation cannot consume more GOOD (or REWORK, per its configured `input_source_kind`) quantity from its source than `source.produced − already_allocated_elsewhere`. | REQ-SESS-002 (finish, material check) |
| BR-012 | Operation dependencies are two independent relationships: a pure time/order **predecessor** (must simply exist) and a quantity **input source** (must have a started session) — the same Operation can be both, in which case only the stricter input-source rule applies. | REQ-SESS-001 |
| BR-013 | Full-session edits support optimistic concurrency via `expected_updated_at` — a stale edit is refused, never silently overwritten. | REQ-SESS-005 |
| BR-014 | PO/Part deletion is refused whenever any descendant Operation has real production history, naming the specific kind(s) found. | REQ-PO-004, REQ-PART-002 |
| BR-015 | An Exception Center record's `fingerprint` is unique **while active**; the same condition recurring after a prior instance was resolved/ignored creates a fresh record, never revives the old one. | REQ-EXC-001 |
| BR-016 | A stale, superseded UI request must never overwrite a more recent one's rendered result. | REQ-DASH-002 |
| BR-017 | Timezone/shift math is always shift-relative-minutes against the site timezone, never naive wall-clock subtraction — required for cross-midnight shifts. | REQ-SHIFT-001 |
| BR-018 | KPI/report/exception-detection queries share one predicate (`status='CLOSED' AND NOT excluded_from_reports`) rather than each hand-rolling their own. | REQ-PROD-001, REQ-EXC-001 |
| BR-901 | Every login attempt (success or failure) writes an audit-trail row (`LOGIN_SUCCESS`/`LOGIN_FAILED`); the submitted password is never logged in any form, regardless of outcome. | REQ-AUTH-001 |
| BR-902 | A deliberate logout must never bounce straight back into an authenticated session even when autologin is on — the app's own logout button always appends `?noauto=1`. | REQ-AUTH-002/005 |
| BR-903 | Autologin requires `MESFLOW_ENV != production`, **or** both that condition failing **and** an explicit second flag (`MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1`) — never satisfied by the base flag alone on a production-flagged environment. | REQ-AUTH-004 |
| BR-904 | Persona quick-switch resolves to a username **literally equal to** the persona name, from a fixed 5-value allowlist — never an arbitrary username, never `super_admin`. | REQ-AUTH-004 |
| BR-905 | A rejected autologin attempt (guard failure) reaches the audit/log stream as a security warning, both at process boot (if the risky combination is configured) and on every individual refused attempt. | REQ-AUTH-004 |

---

# PART D — UI/UX Acceptance Requirements

Kept to **behavior a QC agent can mechanically verify** — no
pixel-perfect subjective judgment.

| ID | Requirement |
|---|---|
| REQ-UI-001 | Every checkbox/radio input on a given form renders at the same computed width/height (px) as every other checkbox/radio on that same form. |
| REQ-UI-002 | A field whose value is implicitly always-true for the current business rule is not shown as a togglable option at all — no dead configuration surface. |
| REQ-UI-003 | The login page always shows a fixed split-screen layout: brand/context panel (left) with the product tagline and version footer, and the login form (right) — present regardless of autologin state. |
| REQ-UI-004 | A role without a given page's `.view` permission does not show that page's sidebar entry at all (§2/§3.3) — absent, not disabled. |
| REQ-UI-005 | The primary supported desktop viewport is exactly 1366×768 — any layout QA must include this exact resolution. |
| REQ-UI-006 | Minimum responsive breakpoint matrix for any page-level "doesn't break" check: 1920×1080, 1366×768, 390×844 (mobile). |
| REQ-UI-007 | Modal/drawer interactions for exception/session correction do not auto-close on save — the user must see the saved before/after state and close it themselves. |
| REQ-UI-008 | Sticky elements (e.g. Production Schedule's PO group headers) must not duplicate on scroll and must layer at the correct stacking order. |
| REQ-UI-009 | Filter state and scroll position survive a data refresh — a refresh must never silently reset the user's filter or jump scroll to top. |
| REQ-UI-010 | Empty states show an explicit Vietnamese message (e.g. "Không có Session hoàn thành trong khoảng ngày đã chọn") rather than a blank container. |
| REQ-UI-011 | Any async auto-action (e.g. autologin's POST) gives the user explicit status text during the wait, not a silent unlabeled delay. |
| REQ-UI-012 | Interface language is Vietnamese throughout the admin app — an English string in a user-facing label/error/toast is a defect. |

**Not covered / not asserted**: keyboard-navigation/focus-order
accessibility audit, screen-reader labeling, color-contrast ratios — no
formal accessibility standard is confirmed for this system (§21 gap);
treat anything beyond "labels are distinguishable from values, not
color-only" as exploratory, not pass/fail.

---

# PART E — End-to-End User Journeys

Each journey is directly convertible into an E2E test case using §20's
schema. Every referenced value can be taken from §13's sample data.

### JOURNEY-001 — Admin builds a PO from a Template through to a worked Operation

1. Admin logs in (REQ-AUTH-001). **Expect**: lands on `overview`, full sidebar (§2).
2. Admin opens `TPL-DEMO-01` (§13.2), confirms its tree (REQ-TPL-001). **Expect**: `GET /templates/<id>/validate` (REQ-TPL-002) shows no errors.
3. Admin instantiates it (REQ-PO-001). **Expect**: new PO `PO-DEMO-001` exists, `status=PLANNED`, Parts/Operations copied.
4. Supervisor Starts the PO (REQ-PO-002). **Expect**: `status→IN_PROGRESS`; every child Operation becomes kiosk-workable.
5. Employee `EMP-DEMO-01` (active) scans in via Kiosk v2, starts `OP-DEMO-01-CUT` (REQ-SESS-001/REQ-KIOSK-002). **Expect**: Operation `→IN_PROGRESS` (§5.2 rule 2).
6. Employee finishes with `good_qty=10` (REQ-SESS-002). **Expect**: session `CLOSED`, `quantity_confirmed=TRUE`; if `good_qty ≥ plan_qty`, Operation `→COMPLETED`.
7. Dashboard refreshed (REQ-DASH-001). **Expect**: PO progress numbers reflect the new closed session.

### JOURNEY-002 — Kiosk sequential multi-employee use (required tutorial scenario)

1. Kiosk v2 device in `WAIT_EMPLOYEE`. Employee A scans → `WAIT_OPERATION` → scans `OP-DEMO-01-CUT` → session starts, device resets to `WAIT_EMPLOYEE` (REQ-KIOSK-002/003).
2. Employee B scans immediately after (A's session still `OPEN`) → resolves fresh, `WAIT_OPERATION` → scans a different Operation → own session starts, device resets again.
3. Employee C repeats the same. **Expect**: 3 independent `OPEN` sessions exist; each employee's own later re-scan on this same device resolves to their own session, never another's (REQ-KIOSK-003's core proof).
4. Each employee finishes their session in turn with distinct good/defect quantities.
5. Open the Employee Productivity report / Kiosk wallboard (REQ-PROD-001/REQ-KIOSK-004). **Expect**: all 3 employees appear with correct, independent numbers.

### JOURNEY-003 — Forgot to enter quantity → auto-close → admin resolves

1. Operator starts a session, never finishes it (shift ends while still `OPEN`).
2. Shift end + grace period passes; reconciliation job runs (REQ-SHIFT-002). **Expect**: session auto-closes, whatever quantity it had, `close_reason='AUTO_SHIFT_END'`, `quantity_confirmed=FALSE`.
3. Exception Center surfaces it (`SESSION_PAST_SHIFT_END` while open, or `ZERO_QUANTITY_LONG` once closed if applicable — REQ-EXC-001).
4. Supervisor opens the session, corrects the real quantity via adjust with a reason (REQ-SESS-004). **Expect**: `quantity_confirmed→TRUE`; audit row + `VALUE_CHANGED` event; Operation/PO progress reconciles.

### JOURNEY-004 — Giao nhầm Operation → sửa/reassign → audit/report đúng

1. A session is mistakenly started against the wrong Operation.
2. Supervisor uses transfer-operation (REQ-SESS-006). **Expect**: session now belongs to the correct Operation; both old and new Operation's progress reconcile (§5.2); audit captures before/after.
3. Reports for both Operations reflect the correction — the session's contribution moves, never duplicates.

### JOURNEY-005 — Session sai → disable (exclude) → không ảnh hưởng báo cáo

1. A session is identified as junk (duplicate scan/test data).
2. Supervisor excludes it with a reason (REQ-SESS-007/BR-010). **Expect**: stays in history, `excluded_from_reports=TRUE`; Operation/PO progress, KPI, and exception detection all stop counting it.
3. Restore with a reason reverses it. **Expect**: counts again from the next reconcile onward.

### JOURNEY-006 — Exception zero-qty/NG → Exception Center → resolve/confirm

1. A session closes 0/0 after >4h open. **Expect**: `ZERO_QUANTITY_LONG` (MEDIUM) appears in the Exception Center (REQ-EXC-001).
2. Supervisor acknowledges it (`OPEN→ACKNOWLEDGED`, REQ-EXC-002).
3. Supervisor corrects the session directly from the exception detail (REQ-EXC-003).
4. Supervisor resolves the exception (`→RESOLVED`). **Expect**: no longer "active" (BR-015); a fresh recurrence opens a new record, never reopens this one.

### JOURNEY-007 — Employee Productivity: session data → KPI/table/wallboard must match

1. Seed §13.4's 5 sample sessions for one employee, spanning the KPI formula's edge cases.
2. `GET /reports/employee-productivity` (REQ-PROD-001). **Expect**: `completed_sessions` count, `productivity_percent` average, exactly per §8's formulas.
3. Drill into the employee's detail. **Expect**: every session listed matches the summary's count 1:1.
4. Compare the Kiosk wallboard (REQ-KIOSK-004) for the same range/filters. **Expect**: identical underlying numbers, differing only in presentation/paging.

### JOURNEY-008 — RBAC theo các persona

1. Using autologin persona switch (§12.2, non-production sandbox only), log in as each of admin/manager/supervisor/operator/viewer in turn.
2. For each, attempt every module's boundary action from Part B (e.g. `operator` attempting PO Start should succeed per §3.4's widened rule; `viewer` attempting any `.edit`/`.manage` route should `403`).
3. **Expect**: every boundary in §3.2's grant table (plus §3.4's exceptions) holds exactly, both at the API (`403` with the specific `permission` code) and in the UI (nav item absent, §3.3).

### JOURNEY-009 — Realistic multi-day production dataset walkthrough (tutorial-grade)

1. Seed a dataset spanning ≥5 working days, ≥10 employees, ≥3 POs, with session durations distributed per §13.4's shape guidance (predominantly 4–8h, a natural productivity spread averaging ~85%, not a uniform value).
2. Walk Dashboard → Session Management → Employee Productivity → Exception Center in sequence. **Expect**: the same underlying numbers are consistent across all four screens for the same date range (no screen shows a PO/employee/quantity total that contradicts another).
3. Demonstrate at least one instance each of: a normal completed session, an `OPEN` (in-progress) session, an auto-closed session, a corrected/adjusted session, and an active Exception Center record. **Expect**: each is visually and numerically distinguishable on the relevant screen.

---

# PART F — Traceability Matrix

Legend: **A** = automated coverage exists (pytest/Playwright) as of
this writing, **P** = partial, **—** = no automated coverage found.

| Requirement group | Existing automated coverage (file names) | Status |
|---|---|---|
| REQ-AUTH-001..003 (real login/session) | `tests/e2e/tutorial-video.spec.js` (real password), `test_local_8080_login_contract.py`, `test_internal_qa_login_contract.py` | A |
| REQ-AUTH-004/005 (autologin) | `tests/test_autologin_guard_unit.py`, `tests/integration/test_autologin_persona.py`, `tests/test_v6584431_production_hardening.py` | A |
| §3 RBAC matrix | `tests/integration/test_permission_matrix.py`, `test_super_admin_system_console.py`/`_unit.py`, `test_rbac_self_heal.py` | A (matrix-level); this document's full per-route table is broader than any single existing test file |
| REQ-DASH-* | `tests/e2e/overview-and-calendar.spec.js`, `overview-production-summary.spec.js`, `dashboard-employee-timeline.spec.js` | A |
| REQ-PO-*, REQ-PART-*, REQ-TPL-* | `tests/e2e/catalog-crud.spec.js`, `catalog-visual.spec.js`, `template-ui.spec.js`; `test_p1_audit_2026_08_28.py`, `test_production_state_integrity.py`, `test_production_consistency_p1.py` | A (P for PO-transition rules beyond the enum, §5.3 gap) |
| REQ-EMP-* | `tests/e2e/catalog-crud.spec.js` | P — no dedicated employee-lifecycle test file |
| REQ-SESS-* | `test_session_lifecycle_state_machine_property.py`, `test_session_lifecycle_observability_phase13.py`, `test_session_overlap_and_exceptions.py`, `test_shift_session_lifecycle.py`, `test_write_path_po_lock_contention.py`, `tests/e2e/session-management-*.spec.js` (3 files) | A |
| REQ-KIOSK-001 (v1) | indirect only, via `tests/e2e/mesflow.spec.js` | P |
| REQ-KIOSK-002/003 (v2) | `test_kiosk_v2_bootstrap_environment.py`, `test_kiosk_v2_disabled_identity_rejection.py`, `test_kiosk_v2_heartbeat_liveness.py`, `test_kiosk_v2_p0_device_authorization.py`, `test_kiosk_v2_reset_projection_safety.py`, `test_kiosk_v2_shared_terminal.py`, `test_legacy_kiosk_security_phase10.py`, `test_kiosk_offline_sync.py`, `test_offline_sync_concurrency_blocker6.py`, `test_offline_burst_gate14.py`, `test_offline_trusted_timestamp_phase7.py`, `test_kiosk_rebind_security_blocker2.py`, `test_kiosk_lookup_po_status.py` | A — most heavily tested module in the system |
| REQ-KIOSK-004 (wallboard) | `test_employee_productivity_wallboard.py` (23 cases), `tests/e2e/employee-productivity-wallboard.spec.js` | A |
| REQ-SHIFT-* | `test_shift_dashboard.py`, `test_shift_session_lifecycle.py`, `test_scheduling_time_p2.py`, `test_daily_progress_day_state_semantics.py` | A |
| REQ-EXC-* | `test_v67_exception_center.py`, `test_session_exception_workflow.py`, `test_session_exception_resolution_modal.py`, `test_session_audit_phase14.py`, `tests/e2e/exception-center-v67.spec.js`, `session-exception-detail-drawer.spec.js` | A |
| REQ-PROD-* | `tests/integration/test_employee_productivity.py` (14 cases), `test_employee_productivity_wallboard.py` (23 cases) | A |
| REQ-TPL-005 (import/export) | not found as a dedicated pytest file | — |
| REQ-SEARCH-* | `tests/e2e/session-management-dependent-filters.spec.js`, `production-schedule-sticky.spec.js` | A (for those two screens specifically) |
| REQ-TUT-* | `tests/e2e/tutorial-*.spec.js` (3 files), 5 `test_v6584*.py` files | A |
| REQ-SYS-001/002 | `test_v69_system_health.py` family | P |
| REQ-SYS-003 (System Console) | `test_super_admin_system_console.py`/`_unit.py` | A |
| REQ-AUDIT-* | `test_v66_session_service.py`, `test_v72_audit_operations_separation.py`, `test_v74_audit_presentation.py`, `tests/e2e/audit-operations-v72.spec.js`, `business-audit-v74.spec.js` | A |
| REQ-API-001/002 | `test_write_path_po_lock_contention.py`, offline-sync tests above | A |
| REQ-API-003 | `test_postgres_schema.py`, `test_migration_matrix_blocker7.py`, `test_deploy_rollback_migration_aware.py`, `test_api_contract.py` | A |
| Part D (UI/UX) | `tests/e2e/*-visual.spec.js` (catalog, system, ops), `mobile-navigation.spec.js`, `back-navigation.spec.js` | P |
| Part A §14 (NFR) | concurrency/idempotency: A; security/CSRF, browser support, performance SLA: — | P |

---

# PART G — QC Test-Case Generation Guidance

## 20.1 Required output schema

Every generated test case **must** use exactly this shape (field names
as given):

```
TC-ID:              TC-<MODULE>-<###>   (module code matches the REQ- prefix, e.g. TC-SESS-014)
Requirement ID:      REQ-... and/or BR-...  (one or more, comma-separated)
Title:               one-line description of what this specific case checks
Priority:            P0 | P1 | P2   (inherit from the requirement unless the specific case is narrower)
Type:                positive | negative | boundary | RBAC | state-transition | concurrency | recovery | responsive
Preconditions:       exact starting DB/session state (cite §13's sample data by name where possible)
Test Data:           concrete values — never "a PO" or "some employee," always a real code/id from §13 or a newly-specified equivalent
Steps:               numbered, one observable action per step
Expected Result:     one expectation per step, or a single combined expectation for the final state — must be objectively checkable (an exact status code, an exact field value, an exact enum, not "should look right")
Postconditions:      state to leave the environment in / cleanup needed
Environment:         which tier from §12 this case targets
Role:                which persona from §13.1 executes it
Automation Candidate: Yes | No
```

### Naming convention

`TC-<MODULE>-<###>` where `<MODULE>` is the same short code as the
requirement's ID prefix (`AUTH`, `DASH`, `PO`, `PART`, `TPL`, `EMP`,
`SESS`, `KIOSK`, `SHIFT`, `EXC`, `PROD`, `SEARCH`, `TUT`, `SYS`,
`AUDIT`, `API`, `UI`, `NFR`). Number sequentially within each module,
zero-padded to 3 digits, never reused even if a case is later removed.

## 20.2 Generation rule — one requirement → many test cases

For every `REQ-*` and `BR-*` in Part B/C, generate at minimum:

1. **Positive** — the documented main flow succeeds exactly as
   specified in that requirement's "Main flow" and "Expected output"
   fields.
2. **Negative** — every distinct rule in that requirement's
   "Validation"/"Errors" fields, one test case per distinct rule (not
   one combined case for all of them).
3. **Boundary** — every case explicitly named in that requirement's
   "Boundary" field (these are not hypothetical — each one listed in
   this document was chosen because it is a real, previously-relevant
   edge).
4. **RBAC** — for any requirement with a non-`N/A` "Permission" field:
   one case per role that should succeed, one case per role that
   should be refused (`403`), citing the exact permission code from
   §3.1.
5. **State transition** — for any requirement whose "State transition"
   field references Part A §5's diagrams: both the documented valid
   transition and at least one explicitly-invalid one (e.g. finishing
   an already-`CLOSED` session).
6. **Concurrency/idempotency** — only for requirements whose
   "Concurrency" field is not `N/A` — do not invent concurrency cases
   for requirements that explicitly have none.
7. **Recovery** — for any requirement describing an error condition
   with a documented resolution path (auto-close→correction, exception
   detection→acknowledge/resolve), a case that walks the full
   error→recovery sequence, not just the error in isolation.
8. **Responsive** — only for Part D (UI/UX) requirements — use the
   3-viewport matrix from REQ-UI-006.

## 20.3 Priority inheritance

Use the requirement's own stated Priority as the default for every
generated case; a case may be raised (never lowered) if it covers a
security- or data-integrity-critical boundary specifically (e.g. an
RBAC negative case for a P1 requirement whose boundary happens to be
the `admin`-vs-`super_admin` distinction should be treated as P0).

## 20.4 Self-sufficiency check (do this before finalizing any test case)

Before finalizing a generated test case, confirm every value in "Test
Data" and "Steps" is either (a) taken verbatim from §13's sample
data/personas, or (b) fully specified inline with no unresolved
reference to "the current data" or "an existing record" — if a test
case cannot be fully specified without asking a question, that is a
signal this document is missing something; do not silently invent an
answer, log it as a gap instead (§21's format).

---

# PART H — Known Gaps / Open Questions

Kept separate from Part A–G's normal behavior — nothing here should be
treated as spec'd behavior for test-case generation; each is either a
genuinely unverified fact (`SPEC-GAP`) or a decision only a human can
make (`OPEN-QUESTION`).

| ID | Gap |
|---|---|
| SPEC-GAP-001 | Whether every low-privilege-role page consistently *hides* (vs. shows-then-403s) its edit controls was not audited page-by-page — §3.3 explicitly says API-level `403` is the authoritative signal, button-presence is not. |
| SPEC-GAP-002 | No stricter Production Order status transition graph beyond enum membership + the Start action was confirmed (§5.3) — whether the UI itself additionally restricts e.g. `PAUSED→COMPLETED` directly is unverified. |
| SPEC-GAP-003 | The exact shift-boundary-resolution algorithm for a timestamp landing in a gap between shifts, or in an ambiguous cross-midnight window, was summarized (§4.10/§6.4) but not exhaustively traced line-by-line. |
| SPEC-GAP-004 | No "reopen a CLOSED session" code path was found. Do not assume this feature exists; if asked to test it, flag rather than guess. |
| SPEC-GAP-005 | `exception_records.status='AUTO_IGNORED'` — the exact trigger/condition for the system (not a human) auto-ignoring an exception was not traced to its source. |
| SPEC-GAP-006 | No CSRF-token mechanism was confirmed present. This may be intentional (SameSite=Lax + same-origin frontend) or a real gap — needs a dedicated security review, not a guess either way in this document. |
| SPEC-GAP-007 | No supported-browser statement exists in the system; automated e2e coverage is Chromium-only via Playwright. Do not assert cross-browser parity. |
| SPEC-GAP-008 | No documented numeric performance/SLA target exists anywhere in the system. `MESFLOW_ACTION_LOG_SLOW_MS` is an internal logging threshold, not a user-facing target — do not conflate the two. |
| SPEC-GAP-009 | No dedicated automated test file for the Excel import/export validation rules (§10/REQ-TPL-005) was found — these rules are documented from direct code reading, not from an existing passing test asserting each one. |
| SPEC-GAP-010 | Password-strength policy for REQ-SYS-002 (self-service change) and account creation was not fully confirmed — test with an intentionally weak password and record actual behavior. |
| SPEC-GAP-011 | Whether an Excel import with one invalid row among many valid ones is fully transactional (all-or-nothing) or partially applies valid rows before hitting the invalid one was not conclusively confirmed. |
| SPEC-GAP-012 | The exact split in access between `logs.view` (manager-held) and the `@admin_required` action-log/error-trace screen (REQ-AUDIT-001) needs a dedicated boundary test — the grant table and the route decorator appear to describe two different things under adjacent names. |
| OPEN-QUESTION-001 | Real public `mesflow.net`'s actual origin server has, at various points in this system's operational history, been genuinely ambiguous/unconfirmed from the internal dev environment — any test plan that assumes a specific environment is "real production" should reconfirm that identity via a live, deterministic check (not an assumed domain-name mapping) before running anything against it. |
| OPEN-QUESTION-002 | Whether System Console (§2's "Hệ thống" nav group, super_admin-only) and Business Audit Trail (REQ-AUDIT-002) are considered in-scope for the tutorial-video coverage system is a product decision, not a fact this document can resolve — flagged here, not assumed either way. |

---

## 21. Self-containment self-check

**Question asked of this document**: *if only `docs/MESFLOW_MASTER_REQUIREMENTS.md`
is given to a QA agent with no access to MESFlow's source code, no
running instance, and no memory of this conversation, can it generate
valid test cases without reading code or asking a clarifying
question?*

**Answer**: Yes, with the explicit exceptions listed in Part H, which
are deliberately called out rather than papered over. Every functional
requirement in Part B carries concrete input shapes, exact validation
rules, exact error messages/codes, and either a specific state
transition or an explicit `N/A` with a reason. Every requirement's
"Boundary" and "RBAC" fields point to real, named test data in §13
rather than an abstract "some user." The 14 Part A appendices contain
every formula, enum, table schema, and workflow diagram a requirement
references — an agent never needs to leave this file to resolve a
citation like "§8" or "§13.4," because those sections are in the same
document. Where this document itself is uncertain (Part H), that
uncertainty is the deliberate, correct output — an agent encountering
a `SPEC-GAP` should generate a test case that *checks and records*
actual behavior rather than assert a guessed expectation, exactly as
§20.4 instructs.

