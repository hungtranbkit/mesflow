// Rewritten in full (2026-08-26): every test in this file used to drive
// pages/session-exceptions.js -- confirmed dead code, superseded by
// pages/exception-center.js (see mesflow.spec.js's own confirmation test).
//
// Rewritten again in full (2026-08-28, Inline Session Exception Resolution
// modal task): the drawer used to be a read-only viewer that opened
// /api/sessions/:id/context + /api/exceptions/:id/history separately and
// only let a supervisor "Mở Session #<id>" away to Session Management to
// actually fix anything (window.prompt() for the resolve/ignore reason).
// The field complaint that started that whole task ("chỉ có tính năng xem
// rồi đóng, chưa giải quyết triệt để") was only half-fixed by that
// hand-off -- editing still meant leaving the page. This file now drives
// the real inline modal: a single GET /api/session-exceptions/:id/
// resolution-context loads exception+session+activity+history+
// editable_fields together, tabs (Tổng quan/Điều chỉnh/Kiểm tra/Lịch sử)
// render in place, and Nhận xử lý/Lưu điều chỉnh/Hoàn tất xử lý/Bỏ qua all
// happen via footer [data-action] buttons + a shared #ecReason textarea --
// never a window.prompt(), never a navigation. "Mở Session đầy đủ" is kept
// only as the documented secondary fallback (see the last test below).
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

// Field names match ExceptionRepository.list()'s real row shape
// (exception_records.* joined with employee/po/part/operation labels).
function exceptionItems() {
  const items = [];
  for (let i = 0; i < 14; i++) {
    items.push({
      id: 6000 + i,
      session_id: 500 + i,
      exception_type: 'LONG_OPEN_SESSION',
      severity: i === 0 ? 'HIGH' : 'MEDIUM',
      title: 'Session mở quá lâu',
      message: 'Session đang mở quá 12 giờ',
      recommended_action: 'Kiểm tra Session và xác nhận trạng thái.',
      detected_at: new Date(Date.now() - (17 - i * 0.1) * 3600000).toISOString(),
      status: 'OPEN',
      row_version: 1,
      employee_id: 900 + i, employee_code: `NV-${String(i + 1).padStart(3, '0')}`,
      employee_name: i === 0 ? 'Phạm Văn A' : `Nhân viên Test ${i + 1}`,
      operation_code: 'OP-CAT-LASER', operation_name: 'CẮT LASER',
      po_code: 'PO-260813-01', part_code: 'PART-01'
    });
  }
  return items;
}

// Mirrors GET /api/session-exceptions/:id/resolution-context's real shape
// (app/mesflow/web/exceptions.py) -- exception/session/activity/history/
// editable_fields together, matching EDITABLE_FIELDS_BY_EXCEPTION_TYPE's
// real LONG_OPEN_SESSION entry (ended_at, status), never invented fields.
function resolutionContextPayload(item, overrides = {}) {
  return {
    ok: true,
    exception: { ...item, ...(overrides.exception || {}) },
    session: {
      session_id: item.session_id, employee_id: item.employee_id, device_uuid: 'ESP-KIOSK-07',
      status: 'OPEN', started_at: item.detected_at, ended_at: null, updated_at: item.detected_at,
      good_qty: 0, defect_qty: 0, rework_qty: 0,
      employee_code: item.employee_code, employee_name: item.employee_name,
      po_code: item.po_code, part_code: item.part_code, part_name: 'Chi tiết mẫu',
      operation_code: item.operation_code, operation_name: item.operation_name,
      station_code: 'ST-07', station_name: 'Trạm cắt laser 07', duration_seconds: 3600,
      ...(overrides.session || {})
    },
    activity: overrides.activity || [
      { occurred_at: item.detected_at, event_type: 'SCAN_EMPLOYEE', message: 'Quét nhân viên thành công' },
      { occurred_at: item.detected_at, event_type: 'SESSION_START', message: 'Bắt đầu Session' }
    ],
    history: overrides.history || [],
    editable_fields: overrides.editable_fields || ['ended_at', 'status']
  };
}

async function mockApis(page, items) {
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    route.fulfill({ json: { ok: true, items, total: items.length } });
  });
  await page.route(/\/api\/session-exceptions\/\d+\/resolution-context$/, route => {
    const id = Number(route.request().url().match(/session-exceptions\/(\d+)\/resolution-context/)[1]);
    const item = items.find(x => x.id === id) || items[0];
    route.fulfill({ json: resolutionContextPayload(item) });
  });
}

async function openScreen(page, viewport, items) {
  await page.setViewportSize(viewport);
  await login(page);
  await mockApis(page, items);
  await page.evaluate(() => openPage('session-exceptions'));
  await expect(page.locator('.ec-card')).toHaveCount(items.length);
}

test('Mở ngoại lệ trong modal tại chỗ, không điều hướng, không cần cuộn', async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  const firstCard = page.locator('.ec-card').first();
  await expect(firstCard.locator('.ec-context b')).toHaveText('Phạm Văn A');
  await expect(firstCard.locator('button.ec-review')).toHaveText('Xử lý');

  await page.evaluate(() => window.scrollTo(0, 200));
  const scrollBefore = await page.evaluate(() => window.scrollY);
  const urlBefore = page.url();

  await page.locator('.ec-card').nth(4).click();

  // Modal appears in place; default tab is Tổng quan with full session
  // identity/timing/quantities/exception detail -- no navigation, no
  // scrolling to find it elsewhere.
  await expect(page.locator('.ec-resolution')).toBeVisible();
  expect(page.url()).toContain(urlBefore.split('?')[0]);
  expect(page.url()).not.toContain('session-management');
  await expect(page.locator('#pageTitle')).toHaveText('Trung tâm ngoại lệ');
  await expect(page.locator('.ec-resolution header')).toContainText('Nhân viên Test 5');
  await expect(page.locator('.ec-resolution header')).toContainText('SESSION #504');
  await expect(page.locator('.ec-drawer-body')).toContainText('Session mở quá lâu');
  await expect(page.locator('.ec-drawer-body')).toContainText('Trạm cắt laser 07');
  await expect(page.locator('.ec-modal-tabs button')).toHaveCount(4);
  for (const label of ['Tổng quan', 'Điều chỉnh', 'Kiểm tra', 'Lịch sử'])
    await expect(page.locator('.ec-modal-tabs button', { hasText: label })).toBeVisible();

  await page.locator('#ecClose').click();
  await expect(page.locator('.ec-drawer-shell')).toHaveCount(0);
  await expect(page.locator('.ec-card')).toHaveCount(items.length);
  const scrollAfter = await page.evaluate(() => window.scrollY);
  expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThanOrEqual(2);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test('Tab Điều chỉnh chỉ hiển thị đúng trường theo loại ngoại lệ', async ({ page }) => {
  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  await page.locator('.ec-card').first().click();
  await page.locator('.ec-modal-tabs button', { hasText: 'Điều chỉnh' }).click();

  // LONG_OPEN_SESSION's real editable_fields is (ended_at, status) --
  // never good_qty/defect_qty/employee_id/etc for this type.
  await expect(page.locator('[data-field="status"]')).toBeVisible();
  await expect(page.locator('[data-field="ended_at"]')).toHaveCount(1);
  await expect(page.locator('[data-field="good_qty"]')).toHaveCount(0);
  await expect(page.locator('[data-field="employee_id"]')).toHaveCount(0);
  // ended_at starts disabled while status is still OPEN (mirrors Session
  // Management's own smEditStatus/smEditEnd pairing).
  await expect(page.locator('[data-field="ended_at"]')).toBeDisabled();
});

test('Sửa Session hiện before/after rồi lưu, modal không tự đóng', async ({ page }) => {
  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);
  const target = items[0];

  await page.locator('.ec-card').first().click();
  await page.locator('.ec-modal-tabs button', { hasText: 'Điều chỉnh' }).click();

  await page.locator('[data-field="status"]').selectOption('CLOSED');
  await expect(page.locator('[data-field="ended_at"]')).toBeEnabled();

  // Diff preview reflects the pending change before any save.
  await expect(page.locator('.ec-diff')).toContainText('Trạng thái');
  await expect(page.locator('.ec-diff')).toContainText('Đang mở');
  await expect(page.locator('.ec-diff')).toContainText('Đã đóng');

  let correctBody = null;
  await page.route(/\/api\/session-exceptions\/\d+\/correct-session$/, async route => {
    correctBody = route.request().postDataJSON();
    await route.fulfill({
      json: {
        ok: true,
        old: { status: 'OPEN' },
        item: { ...target, status: 'CLOSED', updated_at: new Date().toISOString() },
        exception: { ...target, status: 'ACKNOWLEDGED', condition_active: false, row_version: 2 },
        cleared: true
      }
    });
  });

  // Saving without a reason is blocked client-side -- no request fires.
  await page.locator('[data-action="save"]').click();
  await expect(page.locator('.ec-resolution')).toBeVisible();
  expect(correctBody).toBeNull();

  await page.locator('#ecReason').fill('Đã kiểm tra thực tế, Session bị bỏ quên không đóng.');
  await page.locator('[data-action="save"]').click();

  await expect.poll(() => correctBody).not.toBeNull();
  expect(correctBody.status).toBe('CLOSED');
  expect(correctBody.reason).toContain('Đã kiểm tra thực tế');
  expect(correctBody.good_qty).toBeUndefined(); // never sent -- not in editable_fields

  // Modal stays open (no auto-close) and shows the cleared result inline.
  await expect(page.locator('.ec-resolution')).toBeVisible();
  await expect(page.locator('.ec-banner.success')).toContainText('không còn hiệu lực');
  await expect(page.locator('[data-action="resolve"]')).toBeEnabled();
});

test('Ngoại lệ vẫn còn sau khi lưu điều chỉnh thì Hoàn tất bị khoá', async ({ page }) => {
  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);
  const target = items[0];

  await page.locator('.ec-card').first().click();
  await page.locator('.ec-modal-tabs button', { hasText: 'Điều chỉnh' }).click();
  await page.locator('#ecReason').fill('Thử sửa nhưng chưa đúng.');

  await page.route(/\/api\/session-exceptions\/\d+\/correct-session$/, route => route.fulfill({
    json: {
      ok: true, old: {}, item: { ...target, status: 'OPEN' },
      exception: { ...target, status: 'OPEN', message: 'Session vẫn đang mở quá 12 giờ.', row_version: 2 },
      cleared: false
    }
  }));
  await page.locator('[data-action="save"]').click();

  await expect(page.locator('.ec-banner.warn')).toContainText('vẫn còn');
  await expect(page.locator('.ec-banner.warn')).toContainText('Session vẫn đang mở quá 12 giờ');
  await expect(page.locator('[data-action="resolve"]')).toBeDisabled();
});

test('Phát hiện Session bị người khác thay đổi (SESSION_CHANGED)', async ({ page }) => {
  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);
  const target = items[0];

  await page.locator('.ec-card').first().click();
  await page.locator('.ec-modal-tabs button', { hasText: 'Điều chỉnh' }).click();
  await page.locator('[data-field="status"]').selectOption('CLOSED');
  await page.locator('#ecReason').fill('Đóng session treo.');

  const freshUpdatedAt = new Date().toISOString();
  await page.route(/\/api\/session-exceptions\/\d+\/correct-session$/, route => route.fulfill({
    status: 409,
    json: {
      ok: false, error: 'SESSION_CHANGED',
      message: 'Session đã được người khác thay đổi. Vui lòng xem lại dữ liệu mới nhất.',
      current: { session_id: target.session_id, status: 'CLOSED', ended_at: freshUpdatedAt, updated_at: freshUpdatedAt, good_qty: 5, defect_qty: 0 }
    }
  }));
  await page.locator('[data-action="save"]').click();

  await expect(page.locator('.ec-banner.danger')).toContainText('đã được người khác thay đổi');
  // The Session snapshot underneath the form is refreshed to the server's
  // current values -- never silently overwritten by the stale draft.
  await page.locator('.ec-modal-tabs button', { hasText: 'Điều chỉnh' }).click();
  await expect(page.locator('[data-field="status"]')).toHaveValue('CLOSED');
});

test('Nhận xử lý và Bỏ qua đều xảy ra tại chỗ, không điều hướng', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));

  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);
  const target = items[0]; // HIGH severity -> reason required to ignore/resolve

  await page.locator('.ec-card').first().click();
  await expect(page.locator('.ec-resolution')).toBeVisible();

  let acknowledged = false;
  await page.route(/\/api\/exceptions\/\d+\/acknowledge$/, route => {
    acknowledged = true;
    route.fulfill({ json: { ok: true, item: { ...target, status: 'ACKNOWLEDGED', row_version: 2 } } });
  });
  await page.locator('[data-action="take"]').click();
  await expect.poll(() => acknowledged).toBe(true);
  // Nhận xử lý updates in place -- modal stays open, no navigation.
  await expect(page.locator('.ec-resolution')).toBeVisible();
  await expect(page.locator('.ec-resolution .ec-status')).toHaveText('Đã xác nhận');
  await expect(page.locator('[data-action="take"]')).toHaveCount(0); // already acknowledged

  // Ignore without a reason is blocked client-side.
  let ignoreCalled = false;
  await page.route(/\/api\/exceptions\/\d+\/ignore$/, route => {
    ignoreCalled = true;
    route.fulfill({ json: { ok: true, item: { ...target, status: 'MANUAL_IGNORED' } } });
  });
  await page.locator('[data-action="ignore"]').click();
  await page.waitForTimeout(200);
  expect(ignoreCalled).toBe(false);
  await expect(page.locator('.ec-resolution')).toBeVisible();

  let listReloaded = false;
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    listReloaded = true;
    const updated = items.filter(x => x.id !== target.id);
    route.fulfill({ json: { ok: true, items: updated, total: updated.length } });
  });
  await page.locator('#ecReason').fill('Đã xác nhận với tổ trưởng, chấp nhận trường hợp này.');
  await page.locator('[data-action="ignore"]').click();

  await expect.poll(() => ignoreCalled).toBe(true);
  await expect.poll(() => listReloaded).toBe(true);
  await expect(page.locator('.ec-drawer-shell')).toHaveCount(0);
  expect(page.url()).not.toContain('session-management');
  expect(pageErrors).toEqual([]);
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
  test(`bố cục không vỡ tại ${viewport.width}x${viewport.height} kể cả tab Điều chỉnh`, async ({ page }) => {
    const items = exceptionItems();
    await openScreen(page, viewport, items);
    await page.locator('.ec-card').first().click();
    await page.locator('.ec-modal-tabs button', { hasText: 'Điều chỉnh' }).click();
    await expect(page.locator('.ec-field-grid')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    if (viewport.width === 1366) {
      await page.waitForTimeout(200);
      await page.screenshot({ path: `test-results/session-exception-resolution-modal-${viewport.width}.png` });
    }
  });
}

test('Tab Lịch sử hiển thị kết quả đã xử lý (danh sách cấp trang)', async ({ page }) => {
  const items = exceptionItems().map((x, i) => i === 0 ? { ...x, status: 'RESOLVED' } : x);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    const url = route.request().url();
    const view = url.includes('view=history') ? 'history' : 'action';
    const filtered = view === 'history' ? items.filter(x => x.status === 'RESOLVED') : items.filter(x => x.status === 'OPEN');
    route.fulfill({ json: { ok: true, items: filtered, total: filtered.length, view } });
  });
  await page.evaluate(() => openPage('session-exceptions'));
  await page.locator('.ec-tabs button[data-view="history"]').click();
  await expect(page.locator('.ec-card')).toHaveCount(1);
  await expect(page.locator('.ec-card .ec-severity span')).toHaveText('Đã giải quyết');
});

test('Mở Session đầy đủ vẫn là phương án dự phòng, giữ ngữ cảnh quay lại', async ({ page }) => {
  const items = exceptionItems();
  const target = items[3]; // an arbitrary non-first row -- proves the RIGHT session opens
  await page.setViewportSize({ width: 1366, height: 768 });
  await login(page);
  await mockApis(page, items);
  await page.route(/\/api\/session-management\/operations\?/, route =>
    route.fulfill({ json: { ok: true, items: [], filters: { production_orders: [], parts: [], operations: [], employees: [], stations: [] } } }));
  await page.route(/\/api\/session-management\?/, route =>
    route.fulfill({ json: { ok: true, items: [], filters: { production_orders: [], parts: [], operations: [], employees: [], stations: [] } } }));

  await page.evaluate(() => openPage('session-exceptions'));
  await page.locator(`.ec-card[data-id="${target.id}"]`).click();
  await expect(page.locator('.ec-resolution')).toContainText(`SESSION #${target.session_id}`);

  // Secondary/fallback action -- not the primary "Xử lý" path, but still
  // deep-links to the exact Session, same mechanism as before.
  await page.getByRole('button', { name: 'Mở Session đầy đủ' }).click();

  await expect(page.locator('#pageTitle')).toHaveText('Quản lý Session');
  await expect(page.locator('.session-exception-context')).toContainText(`Session #${target.session_id}`);
  await expect(page.locator('.session-exception-context')).toContainText('Session mở quá lâu');

  await page.locator('[data-nav-back]').click();
  await expect(page.locator('#pageTitle')).toHaveText('Trung tâm ngoại lệ');
  await expect(page.locator('.ec-card')).toHaveCount(items.length);
});
