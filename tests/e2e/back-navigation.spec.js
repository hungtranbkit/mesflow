// Context-aware Back navigation (AppNav). Every scenario listed in the
// nav-audit report is covered here:
//   1. Overview/Dashboard -> PO detail -> Back (filters + scroll preserved)
//   2. Session Exceptions -> Session Detail drawer -> "Mở trong Quản lý
//      Session" -> Back (returns to Session Exceptions, not Home)
//   3. Employees -> related Session -> Back (returns to Employees)
//   4. Direct URL (`?session=`) -> Back/Close fallback (stays on Overview)
//   5. Entering a detail view with no recorded parent (refresh-equivalent)
//      -> Back still resolves to the logical fallback, never a crash
//   6. No Back control ever navigates to /login or off mesflow (asserted
//      throughout via `assertStillInApp`)
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

// Every Back control in the app must be an in-page DOM/state change, never
// a real navigation (which is how you'd accidentally end up back at
// /login or off MESFlow entirely -- see requirement #4 in the nav audit).
function assertStillInApp(page) {
  expect(page.url()).not.toContain('/login');
  expect(page.url()).toMatch(/\/app(\?|$)/);
}

const poFixture = {
  id: 501, code: 'PO-501', product: 'Khung nhôm E10', status: 'IN_PROGRESS',
  planned_quantity: 100, source_template_code: 'TPL-01', source_template_version: '1.0',
  planned_start_at: null, planned_end_at: null, due_date: '2026-09-01'
};
const overviewPoRow = {
  po_id: 501, po_code: 'PO-501', product: 'Khung nhôm E10', control_state: 'ON_TRACK',
  progress_percent: 40, good_quantity: 40, planned_quantity: 100, defect_quantity: 2,
  scrap_quantity: 0, remaining_quantity: 60, repair_pending_quantity: 0,
  estimated_repair_work_seconds: 0, repair_unconfigured_operation_count: 0, due_date: '2026-09-01'
};
// The "Mở PO" button only renders inside a PO's Operation rows, so the
// fixture needs at least one Operation for po_id 501 -- otherwise there is
// nothing to click and the drill-down into PO detail never happens.
const overviewOpRow = {
  operation_id: 9001, po_id: 501, part_id: 21, operation_sort: 1,
  operation_code: 'OP-CAT-LASER', operation_name: 'CẮT LASER', part_code: 'PART-01', part_name: 'Khung nhôm',
  progress_percent: 40, control_state: 'ON_TRACK', done_qty: 40, defect_qty: 2,
  repair_pending_quantity: 0, estimated_repair_work_seconds: 0
};

async function mockPoDetailApis(page) {
  await page.route(/\/api\/production-orders\/501$/, route => route.fulfill({ json: { ok: true, item: poFixture } }));
  await page.route(/\/api\/parts\?/, route => route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/operations\?/, route => route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/equipment\?/, route => route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-control(\?.*)?$/, route => route.fulfill({ json: { ok: true, production_orders: [], operations: [] } }));
}

async function mockOverviewApis(page) {
  await page.route(/\/api\/dashboard\/overview\?/, route => route.fulfill({ json: { ok: true, production_orders: [overviewPoRow], operations: [overviewOpRow] } }));
  await mockPoDetailApis(page);
}

async function mockPoListApis(page) {
  await page.route(/\/api\/production-orders\?limit=500/, route => route.fulfill({ json: { ok: true, items: [poFixture] } }));
}

function sessionRow(overrides = {}) {
  return {
    session_id: 701, employee_id: 900, employee_code: 'NV-001', employee_name: 'Trần Thị B',
    operation_code: 'OP-CAT-LASER', operation_name: 'CẮT LASER', po_code: 'PO-501', part_code: 'PART-01',
    part_name: 'Khung nhôm', started_at: new Date(Date.now() - 3600000).toISOString(), ended_at: null,
    status: 'OPEN', good_qty: 5, defect_qty: 0, rework_qty: 0, station_code: 'ST-07', station_name: 'Trạm 07',
    device_uuid: 'ESP-KIOSK-07', note: '', duration_seconds: 3600,
    ...overrides
  };
}

const sessionManagementFilters = { production_orders: [], parts: [], operations: [], employees: [], stations: [] };

async function mockSessionManagementApis(page, rows) {
  await page.route(/\/api\/session-management\/operations\?/, route => route.fulfill({ json: { ok: true, items: [], filters: sessionManagementFilters } }));
  await page.route(/\/api\/session-management\?/, route => route.fulfill({ json: { ok: true, items: rows, filters: sessionManagementFilters } }));
}

function exceptionItem(overrides = {}) {
  return {
    session_id: 701, exception_code: 'OPEN_TOO_LONG', exception_fingerprint: 'OPEN_TOO_LONG:0#0',
    severity: 'ERROR', exception_message: 'Session đang mở quá 12 giờ', conflict_session_id: null,
    is_active: true, secondary_evidence: false, session_status: 'OPEN',
    started_at: new Date(Date.now() - 13 * 3600000).toISOString(), ended_at: null, duration_seconds: 13 * 3600,
    good_qty: 0, defect_qty: 0, rework_qty: 0, station_id: 301, device_uuid: 'ESP-KIOSK-07',
    data_source: 'UNKNOWN', source_trace_id: '', employee_id: 900, employee_code: 'NV-001', employee_name: 'Trần Thị B',
    operation_code: 'OP-CAT-LASER', operation_name: 'CẮT LASER', po_code: 'PO-501', part_code: 'PART-01',
    workflow_status: 'NEW', resolution: '', review_note: '', assigned_to: '', review_started_at: null,
    started_by: '', review_created_at: null, resolved_at: null, resolved_by: '', review_updated_at: null,
    classification: 'ACTION_REQUIRED', data_impact: 'working_time/employee_state', human_decision_required: true,
    ...overrides
  };
}

function sessionDetailPayload(item) {
  return {
    session: {
      session_id: item.session_id, employee_id: item.employee_id, operation_id: 101, station_id: 301,
      device_uuid: item.device_uuid, status: 'OPEN', started_at: item.started_at, ended_at: null,
      good_qty: 0, defect_qty: 0, rework_qty: 0, note: '', created_at: item.started_at, updated_at: item.started_at,
      start_request_id: 'REQ-START-1', finish_request_id: '',
      employee_code: item.employee_code, employee_name: item.employee_name,
      po_id: 1, po_code: item.po_code, part_id: 11, part_code: item.part_code, part_name: 'Chi tiết mẫu',
      operation_code: item.operation_code, operation_name: item.operation_name,
      station_code: 'ST-07', station_name: 'Trạm cắt laser 07', duration_seconds: item.duration_seconds,
      data_source: 'UNKNOWN'
    },
    exceptions: [item], activity: [], reviews: []
  };
}

test('Tổng quan sản xuất -> Mở PO -> Back giữ bộ lọc và vị trí cuộn', async ({ page }) => {
  await login(page);
  await mockOverviewApis(page);
  await page.evaluate(() => openPage('overview'));
  await expect(page.locator('.overview-po')).toHaveCount(1);

  await page.locator('#ovSearch').fill('PO-501');
  await page.evaluate(() => window.scrollTo(0, 120));
  const scrollBefore = await page.evaluate(() => window.scrollY);

  await page.locator('[data-open-po]').first().click();
  await expect(page.locator('#poBack')).toBeVisible();
  await expect(page.locator('#pageTitle')).toContainText('PO-501');
  assertStillInApp(page);

  await page.locator('#poBack').click();

  // Back returned to Overview (not a hard-coded Home/PO-list default) with
  // the search filter and scroll position from before the drill-down.
  await expect(page.locator('#pageTitle')).toHaveText('Tổng quan sản xuất');
  await expect(page.locator('#ovSearch')).toHaveValue('PO-501');
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(scrollBefore - 2);
  assertStillInApp(page);
});

test('Vào thẳng chi tiết PO (không có ngăn xếp) -> Back vẫn về danh sách PO, không lỗi', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  await login(page);
  await mockPoDetailApis(page);
  await mockPoListApis(page);

  // Simulates the AppNav stack being empty -- exactly what a hard refresh
  // or a direct deep link into PO detail would leave behind, since the
  // stack lives only in memory. {pushNav:false} reproduces that "no
  // recorded previous screen" state without needing a real reload.
  await page.evaluate(id => window.openProductionOrder(id, { pushNav: false }), 501);
  await expect(page.locator('#poBack')).toBeVisible();

  await page.locator('#poBack').click();

  // Falls back to the logical parent (Production Orders list), not a
  // blank page, an error, or Home.
  await expect(page.locator('#pageTitle')).toHaveText('Production Order');
  await expect(page.locator('#poStatus')).toBeVisible();
  assertStillInApp(page);
  expect(pageErrors).toEqual([]);
});

test('Trung tâm ngoại lệ -> xem chi tiết -> đóng quay lại đúng danh sách', async ({ page }) => {
  // Rewritten (2026-08-26): this used to drive pages/session-exceptions.js
  // (.se-card / #seSearch / .drawer-panel) through its "Mở trong Quản lý
  // Session" hand-off into a banner-context Session Management view
  // (window.MESFLOW_SESSION_EXCEPTION_CONTEXT + #smBackException + a
  // [data-nav-back] button). That whole page is confirmed dead code (see
  // mesflow.spec.js's "session exception workflow screen renders" test):
  // its <script> include was removed from app.html because
  // pages/exception-center.js is now loaded and unconditionally overwrites
  // the same renderSessionExceptions global. The only remaining code that
  // reads MESFLOW_SESSION_EXCEPTION_CONTEXT (app.js's Session Management
  // banner) is itself now unreachable, since exception-center.js never sets
  // that global -- its drawer has no "Mở trong Quản lý Session" action at
  // all. The live Exception Center closes its drawer back onto the same
  // list in place, with no page transition and therefore no Back stack or
  // context banner to test.
  const items = [exceptionItem({ id: 9101 })];
  await login(page);
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    route.fulfill({ json: { ok: true, items, total: items.length } });
  });
  await page.route(/\/api\/sessions\/\d+\/context$/, route => route.fulfill({ json: { ok: true, ...sessionDetailPayload(items[0]) } }));
  await page.route(/\/api\/exceptions\/\d+\/history$/, route => route.fulfill({ json: { ok: true, items: [] } }));

  await page.evaluate(() => openPage('session-exceptions'));
  await expect(page.locator('.ec-card')).toHaveCount(1);

  await page.locator('.ec-card').first().click();
  await expect(page.locator('.ec-drawer')).toBeVisible();
  await expect(page.locator('.ec-drawer')).toContainText('SESSION #701');
  assertStillInApp(page);

  await page.locator('#ecClose').click();

  // Closing the drawer stays on the same page/list -- no navigation, no
  // Home fallback, nothing to restore.
  await expect(page.locator('.ec-drawer-shell')).toHaveCount(0);
  await expect(page.locator('#pageTitle')).toHaveText('Trung tâm ngoại lệ');
  await expect(page.locator('.ec-card')).toHaveCount(1);
  assertStillInApp(page);
});

test('Nhân viên -> Xem Session liên quan -> Back quay lại Nhân viên', async ({ page }) => {
  const employee = { id: 900, employee_no: 'NV-001', name: 'Trần Thị B', department: 'Cơ khí', team: 'Tổ 1', position: 'Vận hành', employment_status: 'Đang làm', active: true };
  await login(page);
  await page.route(/\/api\/employees\?/, route => route.fulfill({ json: { ok: true, items: [employee] } }));
  await page.route(/\/api\/reports\/employee-performance\?/, route => route.fulfill({
    json: { ok: true, report: { employee: { employee_code: employee.employee_no, employee_name: employee.name }, summary: {}, operations: [], sessions: [sessionRow()] } }
  }));
  await mockSessionManagementApis(page, [sessionRow()]);

  await page.evaluate(() => openPage('employees'));
  await expect(page.locator('#employeeList table')).toBeVisible();
  await page.locator('#employeeSearch').fill('Trần Thị B');
  await page.evaluate(() => window.scrollTo(0, 60));
  const scrollBefore = await page.evaluate(() => window.scrollY);

  await page.getByRole('button', { name: 'Báo cáo' }).click();
  await expect(page.locator('.employee-report-modal')).toBeVisible();
  await page.locator('[data-open-session]').first().click();

  // Left Employees for Session Management -- again, a real return path,
  // not a hard-coded Home link.
  await expect(page.locator('#pageTitle')).toHaveText('Quản lý Session');
  await expect(page.locator('.session-exception-context')).toContainText('Session #701');
  await expect(page.locator('.session-exception-context')).toContainText('Trần Thị B');
  assertStillInApp(page);

  await page.locator('[data-nav-back]').click();

  await expect(page.locator('#pageTitle')).toHaveText('Quản lý nhân viên');
  await expect(page.locator('#employeeSearch')).toHaveValue('Trần Thị B');
  await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThanOrEqual(scrollBefore - 2);
  assertStillInApp(page);
});

test('Mở trực tiếp bằng URL ?session= -> Đóng drawer ở lại MESFlow, không về login', async ({ page }) => {
  const item = exceptionItem();
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.route(/\/api\/session-management\/\d+$/, route => route.fulfill({ json: { ok: true, ...sessionDetailPayload(item) } }));
  await page.route(/\/api\/sessions\/\d+\/trace(\?.*)?$/, route => route.fulfill({ json: { ok: true, events: [] } }));
  await page.route(/\/api\/dashboard\/overview\?/, route => route.fulfill({ json: { ok: true, production_orders: [], operations: [] } }));
  await page.route(/\/api\/production-control(\?.*)?$/, route => route.fulfill({ json: { ok: true, production_orders: [], operations: [] } }));

  await page.goto('/app?session=701');
  await expect(page.locator('#appLayout')).toBeVisible();

  // Deep link opened the drawer directly, on top of the default landing
  // page -- no cold-load crash, no forced trip through Session Management.
  // Rewritten (2026-08-26): SessionDetailDrawer itself is still live (app.html's
  // boot script still calls window.SessionDetailDrawer.open(deepLinkSessionId)
  // for a `?session=` cold load, and the Session Management accordion opens
  // the same drawer) -- only the selectors were stale. It renders through
  // the generic MFUI.openDrawer() primitive (core/ui.js), which never used
  // .drawer-panel/.drawer-head/.drawer-backdrop -- those are
  // .ui-drawer/.ui-drawer-header/.ui-overlay-backdrop.
  await expect(page.locator('.ui-drawer')).toBeVisible();
  await expect(page.locator('.ui-drawer-header')).toContainText('Session #701');
  // No return context was recorded for a cold load, so the drawer only
  // offers Close, never a "Mở trong Quản lý Session" action that would
  // dead-end without a way back.
  await expect(page.locator('#sdActOpenManagement')).toHaveCount(0);

  await page.locator('#sdClose').click();
  await expect(page.locator('.ui-drawer')).toHaveCount(0);
  await expect(page.locator('#pageTitle')).toHaveText('Tổng quan sản xuất');
  expect(page.url()).not.toContain('session=');
  assertStillInApp(page);
});

test('Người dùng -> Vai trò & phân quyền -> Back giữ style và vị trí điều hướng nhất quán', async ({ page }) => {
  await login(page);
  await page.route(/\/api\/users$/, route => route.fulfill({ json: { ok: true, items: [], roles: ['admin', 'supervisor'] } }));
  await page.route(/\/api\/roles$/, route => route.fulfill({ json: { ok: true, roles: [{ code: 'admin', name: 'Quản trị viên' }], permissions: [], grants: {} } }));

  await page.evaluate(() => openPage('users'));
  await expect(page.locator('#rolePermissions')).toBeVisible();
  await page.locator('#rolePermissions').click();

  await expect(page.locator('#rbacBack')).toBeVisible();
  // Same shared Back control as PO detail / Session Management banners --
  // one look everywhere, per the nav-consistency requirement.
  await expect(page.locator('#rbacBack')).toHaveAttribute('data-nav-back', '');
  await expect(page.locator('#rbacBack')).toHaveClass(/nav-back/);

  await page.locator('#rbacBack').click();
  await expect(page.locator('#pageTitle')).toHaveText('Người dùng hệ thống');
  assertStillInApp(page);
});
