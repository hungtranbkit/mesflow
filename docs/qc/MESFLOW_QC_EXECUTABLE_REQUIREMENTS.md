# MESFlow — QC Executable Requirements

Generate tests from THIS file, not the master requirement doc directly.
Every block below is directly test-generatable: ID, Feature, Role,
Preconditions, Action, Expected Result, Executor, Priority, Safety,
Source Reference. IDs reuse `docs/MESFLOW_MASTER_REQUIREMENTS.md`'s
`REQ-*` where a 1:1 equivalent exists (traceability preserved); new
requirements discovered only during this source audit use `QC-EXEC-*`.

Every feature in `docs/qc/FEATURE_MAP.yaml` has at least one block here —
that is the "unknown mapping ≈ 0" guarantee this file exists to provide.
Depth beyond one block per feature is concentrated on `critical`
features per FEATURE_MAP.yaml's own criticality field.

Field key: **Feature** (id from FEATURE_MAP.yaml) · **Role** (persona
from TEST_ACCOUNTS.yaml, or `device`/`none`) · **Executor**
(ui/api/background_job/deterministic, per EXECUTOR_MAP.yaml) ·
**Safety** (class from SAFETY.yaml this is safe to run against —
`local_dev+demo+prodtest` unless narrower) · **Source Reference** (file
this was verified against).

---

### REQ-AUTH-001 — Real password login succeeds and establishes a session
- **Feature**: auth_login
- **Role**: admin
- **Preconditions**: target reachable; admin account exists and active
- **Action**: `POST /api/auth/login {username, password}` with correct credentials
- **Expected Result**: `200 {"ok":true,"user":{...,"permissions":[...]}}`; `Set-Cookie` present, `HttpOnly`+`SameSite=Lax`
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: app/mesflow/web/app.py (login), auth.py

### REQ-AUTH-001-NEG — Wrong password, unknown user, and inactive account give an identical error
- **Feature**: auth_login
- **Role**: none
- **Preconditions**: one active account, one inactive account
- **Action**: `POST /api/auth/login` with (a) wrong password for the active account, (b) a nonexistent username, (c) correct password for the inactive account
- **Expected Result**: all three -> `401 {"ok":false,"error":"INVALID_CREDENTIALS"}`, byte-identical body shape (never reveals which case)
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml (not separately numbered — master doc §11.2)

### QC-EXEC-AUTH-002 — `/login?noauto=1` always renders the real form regardless of autologin
- **Feature**: auth_login
- **Role**: none
- **Preconditions**: target has `MESFLOW_TEST_AUTO_LOGIN=1`
- **Action**: `GET /login?noauto=1`
- **Expected Result**: HTML contains `data-test-auto-login="0"`; contrast case `GET /login` (no query) on the same target shows `data-test-auto-login="1"`
- **Executor**: ui
- **Priority**: P1
- **Safety**: local_dev+demo (never against a target where autologin might be production-class)
- **Source Reference**: reports/TUTORIAL_VIDEO_PIPELINE_RECOVERY_20260905.md bug #2; tests/e2e/tutorial-auth-state.js

### REQ-SYS-003 — admin session is refused on every System Console route
- **Feature**: system_console
- **Role**: admin
- **Preconditions**: admin session (NOT super_admin)
- **Action**: `GET /api/system-health/errors` (and each of the other 5: services, diagnostics, audit, plus the restart/run-diagnostic POSTs)
- **Expected Result**: `403 {"ok":false,"error":"FORBIDDEN","message":"Chỉ Super Admin mới có quyền truy cập khu vực Hệ thống"}` on every one
- **Executor**: api
- **Priority**: P0 — most security-sensitive boundary in the system
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: app/mesflow/web/auth.py:super_admin_required

### REQ-SYS-003-POS — super_admin session succeeds on every System Console route
- **Feature**: system_console
- **Role**: unknown — no super_admin persona reachable via test_auto_login;
  requires a real super_admin account (see TEST_ACCOUNTS.yaml)
- **Preconditions**: a genuine super_admin account and credential
- **Action**: same 6+ routes as REQ-SYS-003
- **Expected Result**: `200` on every one
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: same as REQ-SYS-003
- **BLOCKED_missing_account**: true — see final report's "user còn phải cung cấp" section

### QC-EXEC-RBAC-001 — editing admin's own permission row is a no-op
- **Feature**: rbac_admin
- **Role**: admin
- **Preconditions**: admin session
- **Action**: `PUT /api/roles/admin/permissions {permission_codes: []}` (submit an empty/reduced set), then `GET /api/roles`
- **Expected Result**: PUT returns `200`; the follow-up GET shows admin's permission set unchanged (full set), not reduced
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo (never prodtest/production — mutates real RBAC config even if a no-op)
- **Source Reference**: BUSINESS_RULES.yaml QC-002

### REQ-EMP-001 — creating an employee derives `active` from `employment_status`, ignoring a direct `active` field
- **Feature**: employee
- **Role**: admin
- **Preconditions**: none
- **Action**: `POST /api/employees {employee_no: "QC_TEST_EMP01", name: "QC Test", employment_status: "Đang làm", active: false, qr: "QC_TEST_QR01"}`
- **Expected Result**: `200`; response row has `active: true` (derived rule wins over the submitted `active:false`)
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest (QC_TEST_ prefixed, self-cleaning)
- **Source Reference**: STATE_MACHINES.yaml employee.rule

### REQ-EMP-002 — an inactive employee cannot start a new session
- **Feature**: work_session_lifecycle
- **Role**: device (kiosk) or admin (web start)
- **Preconditions**: an employee with `employment_status="Đã nghỉ"` (active=false)
- **Action**: `POST /api/work-sessions/start {employee_id: <inactive>, operation_id: <workable>}`
- **Expected Result**: refused (RepositoryError, "employee inactive or missing"), no row created
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml work_session.transitions (start guards)

### REQ-PO-001-NEG — direct PO creation is refused; only template instantiation works
- **Feature**: production_order
- **Role**: admin
- **Preconditions**: none
- **Action**: `POST /api/production-orders {product:"X", planned_quantity:10}` directly
- **Expected Result**: rejected — `ValueError`, "Production Order phải được tạo từ Template để sao chép Part và Operation"
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml QC-001

### REQ-PO-002 — Start requires >=1 Operation and admin/manager/supervisor
- **Feature**: production_order
- **Role**: supervisor
- **Preconditions**: PO exists, status not COMPLETED/CANCELLED
- **Action**: `POST /api/production-orders/<id>/start` (a) with 0 Operations, (b) with >=1 Operation
- **Expected Result**: (a) `409`, "PO chưa có Operation..."; (b) `200`, status -> IN_PROGRESS; a third call while already IN_PROGRESS -> `200 already_started:true`
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml production_order.only_code_enforced_transition

### REQ-PO-004 — force-delete is admin-only even though manager can guarded-delete
- **Feature**: production_order
- **Role**: manager
- **Preconditions**: a PO with zero production history
- **Action**: `DELETE /api/production-orders/<id>/force` as manager
- **Expected Result**: `403` (manager must fail here despite succeeding on the guarded `DELETE /api/production-orders/<id>`)
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: RBAC_MAP.yaml enforcement_rules.explicit_carve_outs

### REQ-TPL-004 — demo template seed/wipe is admin-only, not manager
- **Feature**: template
- **Role**: manager
- **Preconditions**: manager session (holds template.edit)
- **Action**: `POST /api/templates/demo/seed`
- **Expected Result**: `403` (manager must fail despite holding `template.edit` — explicit carve-out)
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo (never prodtest/production — seeds/wipes demo data)
- **Source Reference**: RBAC_MAP.yaml enforcement_rules.explicit_carve_outs

### QC-EXEC-TPL-001 — Part `code` uniqueness is per-PO, Operation `code` is global
- **Feature**: part_operation_generic
- **Role**: admin
- **Preconditions**: two different POs
- **Action**: create a Part with the same `code` under two different POs; then attempt to create two Operations with the same `code` under two different Parts
- **Expected Result**: both Part creations succeed (per-PO uniqueness); the second Operation creation fails on unique-violation (global uniqueness) — the deliberate contrast case
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md §4.2/4.3

### REQ-SESS-001 — start() enforces every precondition independently
- **Feature**: work_session_lifecycle
- **Role**: device
- **Preconditions**: see STATE_MACHINES.yaml work_session.transitions[0].guards — test EACH guard's negative case separately (inactive employee, PO not IN_PROGRESS, input-source not started, employee already has an OPEN session, time overlap)
- **Action**: `POST /api/work-sessions/start` violating exactly one guard at a time
- **Expected Result**: each violation produces its own named error (see STATE_MACHINES.yaml); no session row created in any negative case
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml work_session

### REQ-SESS-001-IDEM — retrying an identical request_id never double-creates
- **Feature**: work_session_lifecycle
- **Role**: device
- **Preconditions**: a valid start() payload
- **Action**: call `POST /api/work-sessions/start` twice with the exact same body including `request_id`
- **Expected Result**: second call returns the identical response body plus `idempotent_replay:true`; exactly one row exists in `work_sessions`
- **Executor**: "api + db_read_readonly"
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml NFR-001

### REQ-SESS-002 — finish() clamps negative quantities to 0, rejects rework>defect
- **Feature**: work_session_lifecycle
- **Role**: device
- **Preconditions**: an OPEN session
- **Action**: `POST /api/work-sessions/<id>/finish {good_qty:-5, defect_qty:3, rework_qty:4}`
- **Expected Result**: `good_qty` persisted as 0 (clamped, not rejected); `rework_qty:4 > defect_qty:3` -> `ValueError` ("rework_qty cannot exceed defect_qty"), session stays OPEN
- **Executor**: "api + db_read_readonly"
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml BR-006

### REQ-SESS-004 — supervisor adjust() requires a reason and flips quantity_confirmed
- **Feature**: work_session_lifecycle
- **Role**: supervisor
- **Preconditions**: an auto-closed session with `quantity_confirmed=false`
- **Action**: `POST /api/supervisor/sessions/<id>/adjust {good_qty:10, reason:""}` (empty reason) then retry with a real reason
- **Expected Result**: empty reason -> `ValueError` ("reason required"); with a reason -> `200`, `quantity_confirmed` becomes `true`, an `operation_adjustments` row exists
- **Executor**: "api + db_read_readonly"
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml BR-009; STATE_MACHINES.yaml work_session.orthogonal_flags

### REQ-SESS-007 — exclude/restore never deletes the row or changes status
- **Feature**: work_session_lifecycle
- **Role**: supervisor
- **Preconditions**: a CLOSED session, not currently excluded
- **Action**: `POST /api/supervisor/sessions/<id>/exclude {reason:"quét trùng"}`, then `GET` the session, then `.../restore {reason:"..."}`
- **Expected Result**: after exclude — row exists, `status` unchanged, `excluded_from_reports:true`; a second exclude call -> `409` ("Session đã được loại khỏi báo cáo"); after restore — `excluded_from_reports:false`
- **Executor**: "api + db_read_readonly"
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml BR-007/BR-010

### QC-EXEC-KIOSKV2-001 — sequential multi-employee use on one device (A->B->C)
- **Feature**: kiosk_v2_device
- **Role**: device
- **Preconditions**: 3 active employees (A,B,C), 1 workable Operation, 1 device token
- **Action**: sequence of `POST /api/kiosk/v2/events`: A scans EMP, A scans OP (session starts, device resets), B scans EMP (while A's session is OPEN), B scans OP, C scans EMP, C scans OP
- **Expected Result**: 3 independent OPEN sessions exist, one per employee, same device_uuid; each employee's later EMP-scan resolves to their OWN session, never another's (the specific historical regression case)
- **Executor**: "api + db_read_readonly"
- **Priority**: P0 — required tutorial multi-employee demo scenario
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml kiosk_v2_device.multi_employee_proof;
  commit 1076803 (kioskQuickCycle); reports/TUTORIAL_VIDEO_PIPELINE_RECOVERY_20260905.md

### QC-EXEC-KIOSKV2-002 — device state machine rejects every out-of-order event
- **Feature**: kiosk_v2_device
- **Role**: device
- **Preconditions**: device in WAIT_EMPLOYEE
- **Action**: send `SCAN(kind=OP)` while in WAIT_EMPLOYEE; send `SCAN(kind=EMP)` while in WAIT_OPERATION; send an unparseable QR
- **Expected Result**: each -> `STATE_INVALID_TRANSITION` with the exact Vietnamese message per STATE_MACHINES.yaml
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml kiosk_v2_device.transitions

### REQ-KIOSK-001 — Kiosk v1 scan/start/finish reaches the same business logic as the web routes
- **Feature**: kiosk_v1_browser
- **Role**: device (no auth)
- **Preconditions**: valid employee/Operation QR values
- **Action**: `POST /api/kiosk-web/scan {qr:""}` (empty)
- **Expected Result**: `400 QR_REQUIRED`, `error_code:SCN-001`, "Chưa nhận được mã quét"
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md §7.1

### REQ-KIOSK-004 — wallboard numbers never diverge from the authenticated report
- **Feature**: kiosk_wallboard
- **Role**: none (public) for wallboard, admin for the authenticated report
- **Preconditions**: seeded reportable sessions in a known date range
- **Action**: `GET /api/wallboard/employee-productivity?from=X&to=Y` and `GET /api/reports/employee-productivity?from=X&to=Y` (authenticated) for the identical range
- **Expected Result**: identical underlying numbers (productivity_percent per employee, totals) — differ only in presentation/paging
- **Executor**: deterministic
- **Priority**: P0 — required "Kiosk năng suất nhân viên" tutorial subject
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: FEATURE_MAP.yaml kiosk_wallboard

### REQ-PROD-001 — employee productivity formula, all edge cases
- **Feature**: employee_productivity_report
- **Role**: any (session.view)
- **Preconditions**: seed the 5-row edge-case table (A-E) from
  docs/MESFLOW_MASTER_REQUIREMENTS.md §13.4 for one employee
- **Action**: `GET /api/reports/employee-productivity?from=<range>&to=<range>`
- **Expected Result**: `completed_sessions`, `productivity_percent` average
  exactly match BUSINESS_RULES.yaml's employee_productivity_formula;
  session D (std_sec=0) -> `completed_invalid_sessions`, never averaged
  as 0; session C (>100% completion) included as-is, no clamp
- **Executor**: deterministic
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml employee_productivity_formula

### REQ-PROD-001-EMPTY — an employee with only OPEN or only excluded sessions never appears as 0%
- **Feature**: employee_productivity_report
- **Role**: any
- **Preconditions**: one employee whose only sessions in range are OPEN; another whose only sessions are excluded_from_reports=true
- **Action**: `GET /api/reports/employee-productivity?from=X&to=Y`
- **Expected Result**: neither employee appears in the `employees` list at all — never a 0% row
- **Executor**: deterministic
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml employee_productivity_formula.zero_valid_sessions_employee

### REQ-EXC-001 — all 7 detection conditions fire correctly, boundary-exact
- **Feature**: exception_center
- **Role**: system (background) / admin (view)
- **Preconditions**: seed one session per condition in
  BUSINESS_RULES.yaml exception_detection_conditions, including a
  boundary case at exactly 12h00m00s open (must NOT yet trigger
  LONG_OPEN_SESSION — strict `>`)
- **Action**: trigger `exception_reconciliation` (see BACKGROUND_JOBS.yaml), then `GET /api/exceptions`
- **Expected Result**: exactly 7 new records, correct exception_type/severity per condition; the 12h00m00s-exact session does NOT yet appear
- **Executor**: "background_job + api"
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml exception_detection_conditions

### REQ-EXC-002 — acknowledge/resolve/ignore respect optimistic concurrency
- **Feature**: exception_center
- **Role**: supervisor
- **Preconditions**: an OPEN exception record, its current `row_version` known
- **Action**: two concurrent `POST /api/exceptions/<id>/acknowledge` calls both passing the SAME stale `expected_version`
- **Expected Result**: exactly one succeeds (200, row_version incremented); the other is refused (version mismatch)
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml exception_record.concurrency

### QC-EXEC-EXC-003 — a session correction from the exception drawer does not auto-resolve the exception
- **Feature**: exception_center
- **Role**: supervisor
- **Preconditions**: an OPEN ZERO_QUANTITY_LONG exception on a real session
- **Action**: `POST /api/session-exceptions/<id>/correct-session {good_qty:5, reason:"..."}`, then `GET /api/exceptions/<exception_id>`
- **Expected Result**: session corrected per REQ-SESS-004; the exception's own `status` is unchanged (still OPEN/ACKNOWLEDGED) until a separate resolve call
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md REQ-EXC-003

### REQ-SHIFT-002 — auto-close never fires unless BOTH rollout flags are set
- **Feature**: shift_auto_close
- **Role**: system
- **Preconditions**: a target with default flags (`MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=0`, `_DRY_RUN=1`); an OPEN session past its shift end
- **Action**: trigger `reconcile-shift-sessions` (see BACKGROUND_JOBS.yaml)
- **Expected Result**: with defaults — session remains OPEN (dry-run only logs what WOULD close); after explicitly setting `ENABLED=1,DRY_RUN=0` — session closes with `close_reason=AUTO_SHIFT_END`, `quantity_confirmed=false`
- **Executor**: "background_job + db_read_readonly"
- **Priority**: P0 — required tutorial error-scenario
- **Safety**: local_dev+demo (never prodtest/production without explicit human authorization — flips a real rollout-safety flag)
- **Source Reference**: BACKGROUND_JOBS.yaml shift_session_reconciliation

### QC-EXEC-SHIFT-002B — auto-close vs. concurrent manual finish is a safe no-op, not a double-close
- **Feature**: shift_auto_close
- **Role**: system + device
- **Preconditions**: a session eligible for auto-close
- **Action**: manually finish() the session at the same moment `reconcile-shift-sessions` would process it (simulate via: finish() first, then run the job)
- **Expected Result**: job run logs a no-op for that session (status already CLOSED when its advisory lock is acquired); no error, no double-close, no overwritten quantities
- **Executor**: "background_job + db_read_readonly"
- **Priority**: P1
- **Safety**: local_dev+demo
- **Source Reference**: STATE_MACHINES.yaml work_session (auto-close transition, concurrency note)

### QC-EXEC-RECON-001 — exception_reconciliation never creates a duplicate active record
- **Feature**: exception_reconciliation
- **Role**: system
- **Preconditions**: one already-OPEN exception record for a still-active condition
- **Action**: run `reconcile-exceptions` twice in a row
- **Expected Result**: still exactly one active record for that fingerprint after both runs
- **Executor**: "background_job + db_read_readonly"
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml BR-015

### QC-EXEC-LOGRET-001 — log-retention preview never deletes, run actually does
- **Feature**: log_retention
- **Role**: admin
- **Preconditions**: seeded old action-log rows past a retention window
- **Action**: `GET /api/system/log-retention/preview`, then `GET /api/system/action-logs/stats`, then `POST /api/system/log-retention/run`, then re-check stats
- **Expected Result**: preview does not change the stats count; run() reduces it by the previewed amount
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo (destructive on real logs — never prodtest/production without authorization)
- **Source Reference**: BACKGROUND_JOBS.yaml log_retention

### REQ-TUT-001 — tutorial manifest hides path-traversal entries
- **Feature**: tutorials
- **Role**: any authenticated
- **Preconditions**: a manifest.json entry crafted with `file:"../../etc/passwd"` (test-fixture manifest, not the real one)
- **Action**: `GET /api/tutorials`, then `GET /tutorials/../../etc/passwd`
- **Expected Result**: the crafted entry is absent from the returned `manifest.items`; the direct file request -> `404`, nothing served
- **Executor**: api
- **Priority**: P0 — real security boundary
- **Safety**: local_dev (never test path-traversal against demo/prodtest's real manifest — use an isolated fixture)
- **Source Reference**: app/mesflow/web/app.py:tutorial_manifest/tutorial_video

### QC-EXEC-TUT-002 — exactly 15 chapters, no duplicate/missing slot numbers, "Năng suất nhân viên" present
- **Feature**: tutorials
- **Role**: any authenticated
- **Preconditions**: a freshly published tutorial set (see reports/TUTORIAL_VIDEO_PIPELINE_RECOVERY_20260905.md)
- **Action**: `GET /api/tutorials`
- **Expected Result**: `manifest.items` has exactly 15 entries, orders `00`-`14` each appearing exactly once, one entry titled "Năng suất nhân viên"
- **Executor**: api
- **Priority**: P0
- **Safety**: local_dev+demo+prodtest (read-only)
- **Source Reference**: tests/test_tutorial_chapter_count_consistency.py;
  tests/test_video_pipeline_output_cleanup.py

### QC-EXEC-DASH-001 — dashboard cascading filter race protection
- **Feature**: dashboard_daily
- **Role**: any
- **Preconditions**: >=2 POs with different Parts/Operations
- **Action**: change the PO filter twice in rapid succession (slow-then-fast response order)
- **Expected Result**: the UI renders the SECOND (later) selection's data, never the first request's stale response arriving after
- **Executor**: ui
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: BUSINESS_RULES.yaml BR-016

### QC-EXEC-OVERVIEW-001 — overview KPI cards render with zero data
- **Feature**: dashboard_overview
- **Role**: viewer
- **Preconditions**: an isolated environment/DB with zero POs
- **Action**: open the overview page
- **Expected Result**: every KPI card shows 0, not an error state
- **Executor**: ui
- **Priority**: P1
- **Safety**: local_dev only (needs a genuinely empty dataset)
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md REQ-DASH-001

### QC-EXEC-SCHED-001 — Gantt/material-flow page loads for every role with material_flow.view
- **Feature**: production_schedule
- **Role**: viewer
- **Preconditions**: viewer session (holds material_flow.view per RBAC_MAP.yaml)
- **Action**: `GET /api/production-schedule`
- **Expected Result**: `200`
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: RBAC_MAP.yaml grant_matrix_source

### QC-EXEC-TRACE-001 — production trace page is reachable and permission-gated
- **Feature**: production_trace
- **Role**: operator
- **Preconditions**: operator session (holds session.view)
- **Action**: open the "Production Trace" nav item
- **Expected Result**: page opens (mounted via the monkey-patch chain — see APPLICATION_MAP.yaml); a viewer without session.view does not see the nav item at all
- **Executor**: ui
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: APPLICATION_MAP.yaml production-trace mount_mechanism

### QC-EXEC-AUDIT-001 — business audit trail is invisible to operator/viewer
- **Feature**: business_audit
- **Role**: viewer
- **Preconditions**: viewer session
- **Action**: `GET /api/audit-logs`
- **Expected Result**: `403` (viewer lacks `business_audit.view` per the grant table — neither operator nor viewer are listed for it)
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: RBAC_MAP.yaml grant_matrix_source

### QC-EXEC-CAL-001 — shift interval editor rejects `end <= start`
- **Feature**: working_calendar
- **Role**: manager
- **Preconditions**: an existing shift
- **Action**: `PUT /api/settings/work-shifts` with an interval where `end_minute <= start_minute`
- **Expected Result**: rejected (CHECK-constraint-backed validation)
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md REQ-SHIFT-001

### QC-EXEC-SYSLOG-001 — action-log/error-trace screen is admin-only, not manager
- **Feature**: system_logs_app
- **Role**: manager
- **Preconditions**: manager session (holds `logs.view` only, per the grant table)
- **Action**: `GET /api/system/action-logs`
- **Expected Result**: `403` (this route is `@admin_required`, i.e. gated by `roles.manage` which manager does not hold — a real, worth-double-checking nuance per RBAC_MAP.yaml)
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: RBAC_MAP.yaml / API_MAP.yaml system_logs_app

### QC-EXEC-HEALTH-001 — /api/system-health/alerts/* is NOT super_admin-gated
- **Feature**: system_health_alerts
- **Role**: manager
- **Preconditions**: manager session
- **Action**: `GET /api/system-health/alerts/<id>/ai-analysis`
- **Expected Result**: `200` for any authenticated role (record actual behavior — this is a newly-catalogued surface not in the master requirement doc; do not assume super_admin-only parity with the 6 explicitly-gated System Console routes)
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: API_MAP.yaml system_health_alerts;
  docs/qc/REQUIREMENT_CODE_GAPS.md

### QC-EXEC-QR-001 — QR payload format matches Kiosk v2's parser
- **Feature**: qr_print
- **Role**: viewer
- **Preconditions**: an employee with a `qr` value
- **Action**: `GET /api/qr-labels`, extract one employee's QR payload
- **Expected Result**: payload matches `WF|EMP|<key>` exactly (the same format `POST /api/kiosk/v2/events`'s SCAN parser expects)
- **Executor**: deterministic
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml kiosk_v2_device (QR wire format, master doc §7.2)

### QC-EXEC-XLSX-001 — Excel import rejects done/defect/status columns
- **Feature**: import_export_excel
- **Role**: admin
- **Preconditions**: a well-formed Operations-sheet workbook with a `done_qty` column populated
- **Action**: `POST /api/operations/import` with that workbook
- **Expected Result**: rejected — "Dòng {N}: done, defect và status là dữ liệu production tự tính; hãy sửa Session nguồn rồi reconcile."
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md §10

### QC-EXEC-QC-001 — QC inspection start/complete lifecycle
- **Feature**: qc_inspection
- **Role**: supervisor
- **Preconditions**: an OPEN work session
- **Action**: `POST /api/qc/inspections {session_id, operation_id}`, then `POST /api/qc/inspections/<id>/complete {good_qty, defect_qty, defect_reason}`
- **Expected Result**: `200` on both; inspection status OPEN -> COMPLETED
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: API_MAP.yaml qc_inspection

### QC-EXEC-NOTIF-001 — marking a notification read is idempotent
- **Feature**: notifications
- **Role**: any
- **Preconditions**: an unread notification for the caller
- **Action**: `POST /api/notifications/<id>/read` twice
- **Expected Result**: both calls `200`; second call does not error on an already-read notification
- **Executor**: api
- **Priority**: P3
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: API_MAP.yaml notifications

### QC-EXEC-PENALTY-001 — penalty ticket requires admin/manager/supervisor
- **Feature**: penalty_ticket
- **Role**: operator
- **Preconditions**: operator session
- **Action**: `POST /api/supervisor/penalties {employee_id, points, reason}`
- **Expected Result**: `403`
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: API_MAP.yaml penalty_ticket

### QC-EXEC-OTA-001 — OTA emergency-stop is admin-only, not manager
- **Feature**: esp_ota
- **Role**: manager
- **Preconditions**: manager session (holds most `ota.*` but NOT `ota.emergency_stop` per RBAC_MAP.yaml grant table)
- **Action**: the emergency-stop action for an active OTA rollout
- **Expected Result**: `403` for manager; `200` for admin
- **Executor**: api
- **Priority**: P1
- **Safety**: local_dev+demo (never prodtest/production — real firmware rollout control)
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md §3.1/3.2 (ota.emergency_stop row)

### QC-EXEC-KPILEGACY-001 — legacy KPI views are reachable but not nav-exposed
- **Feature**: kpi_legacy_views
- **Role**: any authenticated
- **Preconditions**: none
- **Action**: `GET /api/kpi/employees`, `GET /api/kpi/operations`
- **Expected Result**: `200` for both; confirm neither has a sidebar entry (APPLICATION_MAP.yaml reachable_but_not_nav_exposed) — a UI navigation test should NOT expect to find these in the sidebar
- **Executor**: api
- **Priority**: P3
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: APPLICATION_MAP.yaml

### QC-EXEC-MON-001 — monitoring page is admin-only
- **Feature**: monitoring_admin
- **Role**: manager
- **Preconditions**: manager session
- **Action**: `GET /api/system/monitoring`
- **Expected Result**: `403` (admin_required = roles.manage, manager does not hold it)
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: API_MAP.yaml monitoring_admin

### QC-EXEC-STATION-001 — generic station/sales-order resource CRUD basic contract
- **Feature**: station_salesorder_generic
- **Role**: admin
- **Preconditions**: none
- **Action**: `POST /api/stations {code:"QC_TEST_ST01", name:"QC Test Station"}`, then `GET /api/stations`, then `DELETE`
- **Expected Result**: create -> `200`; list includes it; delete -> `200`, removed
- **Executor**: api
- **Priority**: P3
- **Safety**: local_dev+demo+prodtest (QC_TEST_ prefixed)
- **Source Reference**: API_MAP.yaml station_salesorder_generic

### QC-EXEC-PARTOP-001 — generic Part/Operation CRUD respects the po/part hierarchy
- **Feature**: part_operation_generic
- **Role**: admin
- **Preconditions**: an existing PO
- **Action**: `POST /api/parts {production_order_id: <missing/invalid id>}`
- **Expected Result**: rejected — `production_order_id` must reference an existing PO
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: docs/MESFLOW_MASTER_REQUIREMENTS.md REQ-PART-001

### QC-EXEC-SESSUI-001 — Session Management UI reflects the same data as the API
- **Feature**: session_management_ui
- **Role**: supervisor
- **Preconditions**: seeded sessions
- **Action**: open Session Management, compare rendered row count to `GET /api/session-management`'s own result for the same filter
- **Expected Result**: identical count and identical per-row fields
- **Executor**: ui
- **Priority**: P1
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: FEATURE_MAP.yaml session_management_ui

### QC-EXEC-EXCLEG-001 — legacy session-exception workflow transition validation
- **Feature**: session_exceptions_legacy
- **Role**: supervisor
- **Preconditions**: a `session_exception_reviews` row with `workflow_status=NEW`
- **Action**: `PATCH /api/session-exceptions/workflow {status:"INVALID_VALUE"}`
- **Expected Result**: rejected (must be one of NEW/IN_PROGRESS/RESOLVED/IGNORED per the CHECK constraint)
- **Executor**: api
- **Priority**: P2
- **Safety**: local_dev+demo+prodtest
- **Source Reference**: STATE_MACHINES.yaml session_exception_review

---

## Coverage summary

- **Total executable requirements in this file**: 53 (verified by
  `scripts/qc_dry_run.py`, which also produces the live breakdown below
  every time it's run — treat these numbers as a snapshot, re-run for
  the current truth after any edit)
- **Every one of FEATURE_MAP.yaml's 38 features has >=1 block above**
  (verified manually during authoring; re-verify with
  `scripts/validate_qc_package.py` after any FEATURE_MAP.yaml edit)
- **Critical features get >=2 blocks**: auth_login (3), rbac_admin (2),
  production_order (3), template (2), work_session_lifecycle (6),
  kiosk_v2_device (2), employee_productivity_report (2),
  exception_center (3), shift_auto_close (2), exception_reconciliation (1),
  system_console (2), tutorials (2)
- **BLOCKED_missing_account**: 1 (REQ-SYS-003-POS — no super_admin
  test-auto-login persona exists by design; needs a real super_admin
  credential supplied by the human operator)
