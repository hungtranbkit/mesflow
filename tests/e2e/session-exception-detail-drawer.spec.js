// Rewritten in full (2026-08-26): every test in this file used to drive
// pages/session-exceptions.js -- its own card markup (.se-card,
// [data-act="process"/"ignore"/"view"]), its own claim/assign modal
// (#seModal/#seAssigned/#seModalSave), and its own custom drawer
// (.drawer-panel/.drawer-head/.drawer-body/.drawer-tech/.drawer-backdrop)
// including a "Mở trong Quản lý Session" secondary action. That page is
// confirmed dead code: app.html no longer loads it, because
// pages/exception-center.js is loaded instead and unconditionally
// overwrites the same renderSessionExceptions global (see
// mesflow.spec.js's "session exception workflow screen renders" test).
//
// The live Exception Center (exception-center.js) keeps the same top-level
// promise -- open a session's exception detail without leaving the page --
// but through a different, simpler implementation: the whole card is
// clickable (no per-card action buttons), the drawer is
// .ec-drawer-shell/.ec-drawer with its own header/body/footer, and
// Acknowledge/Resolve/Ignore all happen in place via footer
// [data-action] buttons calling POST /api/exceptions/{id}/{action}
// directly.
//
// UPDATE (2026-08-27, Session Exception Management task): the "Mở trong
// Quản lý Session" hand-off IS back -- a real field complaint ("chỉ có
// tính năng xem rồi đóng, chưa giải quyết triệt để") traced to exactly
// this gap: the drawer could show Session context read-only but never let
// a manager actually correct it through the real audited Session editor.
// Restored as "Mở Session #<id>" in the footer, reusing the SAME
// window.MESFLOW_SESSION_EXCEPTION_CONTEXT + AppNav.push() + #smBackException
// mechanism Session Management already had (see back-navigation.spec.js's
// employee-context test for proof that mechanism itself was never broken --
// only exception-center.js never triggered it). See the new test below.
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

// Field names here match ExceptionRepository.list()'s real row shape
// (exception_records.* joined with employee/po/part/operation labels),
// not the retired session-exceptions.js workflow_status vocabulary.
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

function sessionContextPayload(item) {
  return {
    session: {
      session_id: item.session_id, employee_id: item.employee_id, device_uuid: 'ESP-KIOSK-07',
      status: 'OPEN', started_at: item.detected_at, ended_at: null,
      good_qty: 0, defect_qty: 0, rework_qty: 0,
      employee_code: item.employee_code, employee_name: item.employee_name,
      po_code: item.po_code, part_code: item.part_code, part_name: 'Chi tiết mẫu',
      operation_code: item.operation_code, operation_name: item.operation_name,
      station_code: 'ST-07', station_name: 'Trạm cắt laser 07', duration_seconds: 3600
    },
    activity: [
      { occurred_at: item.detected_at, event_type: 'SCAN_EMPLOYEE', message: 'Quét nhân viên thành công' },
      { occurred_at: item.detected_at, event_type: 'SESSION_START', message: 'Bắt đầu Session' }
    ],
    center_exceptions: [item]
  };
}

async function mockApis(page, items) {
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    route.fulfill({ json: { ok: true, items, total: items.length } });
  });
  await page.route(/\/api\/sessions\/\d+\/context$/, route => {
    const id = Number(route.request().url().match(/\/sessions\/(\d+)\/context/)[1]);
    const item = items.find(x => x.session_id === id) || items[0];
    route.fulfill({ json: { ok: true, ...sessionContextPayload(item) } });
  });
  await page.route(/\/api\/exceptions\/\d+\/history$/, route => route.fulfill({ json: { ok: true, items: [] } }));
}

async function openScreen(page, viewport, items) {
  await page.setViewportSize(viewport);
  await login(page);
  await mockApis(page, items);
  await page.evaluate(() => openPage('session-exceptions'));
  await expect(page.locator('.ec-card')).toHaveCount(items.length);
}

test('Xem session mở drawer tại chỗ, không điều hướng trang', async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  // 1. Card content.
  const firstCard = page.locator('.ec-card').first();
  await expect(firstCard.locator('.ec-context b')).toHaveText('Phạm Văn A');
  await expect(firstCard.locator('.ec-context')).toContainText('CẮT LASER');
  await expect(firstCard.locator('p')).toContainText('Session đang mở quá 12 giờ');
  await expect(firstCard.locator('.ec-recommend')).toContainText('Cần làm');

  await page.screenshot({ path: 'test-results/session-exception-list-1920.png', fullPage: true });

  // 2. Scroll down (Exception Center's ID-based filters have no free-text
  // name search equivalent to the retired #seSearch -- filtering isn't
  // part of what this test needs to prove, so it's left out rather than
  // faked against a filter field that doesn't exist).
  await page.evaluate(() => window.scrollTo(0, 200));
  const scrollBefore = await page.evaluate(() => window.scrollY);

  // 3. Click a card to open its drawer.
  const urlBefore = page.url();
  await page.locator('.ec-card').nth(4).click();

  // 4. Drawer appears in place.
  await expect(page.locator('.ec-drawer')).toBeVisible();
  // 5. URL/page does not change to Session Management.
  expect(page.url()).toContain(urlBefore.split('?')[0]);
  expect(page.url()).not.toContain('session-management');
  await expect(page.locator('#pageTitle')).toHaveText('Trung tâm ngoại lệ');

  // 6. Session data is correct. (The drawer's "Ngoại lệ liên quan" section
  // shows the exception's title/status, not its free-text message -- the
  // message only appears on the list card, confirmed via live DOM
  // inspection.)
  await expect(page.locator('.ec-drawer header')).toContainText('Nhân viên Test 5');
  await expect(page.locator('.ec-drawer-body')).toContainText('Session mở quá lâu');
  await expect(page.locator('.ec-drawer-body')).toContainText('Trạm cắt laser 07');
  await expect(page.locator('.ec-drawer-body')).toContainText('Bắt đầu Session');

  await page.waitForTimeout(250); // let the drawer's slide-in animation settle before capturing
  await page.screenshot({ path: 'test-results/session-detail-drawer-1920.png' });

  // 7. Close drawer.
  await page.locator('#ecClose').click();
  await expect(page.locator('.ec-drawer-shell')).toHaveCount(0);

  // 8. List/scroll position remain (closeDrawer() restores state.scroll).
  await expect(page.locator('.ec-card')).toHaveCount(items.length);
  const scrollAfter = await page.evaluate(() => window.scrollY);
  expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThanOrEqual(2);

  // 9. Open another session.
  await page.locator('.ec-card').nth(2).click();
  await expect(page.locator('.ec-drawer')).toBeVisible();
  await expect(page.locator('.ec-drawer header')).toContainText(items[2].employee_name);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test('Xử lý trong drawer cập nhật danh sách, không điều hướng', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));

  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  await page.locator('.ec-card').first().click();
  await expect(page.locator('.ec-drawer')).toBeVisible();

  let acknowledged = false;
  await page.route(/\/api\/exceptions\/\d+\/acknowledge$/, route => {
    acknowledged = true;
    route.fulfill({ json: { ok: true, item: { ...items[0], status: 'ACKNOWLEDGED', row_version: 2 } } });
  });
  let listReloaded = false;
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    listReloaded = true;
    const updated = items.map(x => x.id === items[0].id ? { ...x, status: 'ACKNOWLEDGED' } : x);
    route.fulfill({ json: { ok: true, items: updated, total: updated.length } });
  });

  // Acknowledge needs no reason prompt (only resolve/ignore do) -- see
  // exception-center.js's decide().
  await page.locator('[data-action="acknowledge"]').click();

  // Drawer closes and the list reloads without a full-page navigation.
  await expect.poll(() => acknowledged).toBe(true);
  await expect.poll(() => listReloaded).toBe(true);
  await expect(page.locator('.ec-drawer-shell')).toHaveCount(0);
  await expect(page.locator('#appLayout')).toBeVisible();
  expect(page.url()).not.toContain('session-management');

  expect(pageErrors).toEqual([]);
});

test('Ngoại lệ mức cao yêu cầu ghi lý do trước khi Giải quyết/Bỏ qua', async ({ page }) => {
  // Confirmed current behavior (exception-center.js decide()): resolve/ignore
  // prompt for a reason via window.prompt, and a HIGH/CRITICAL severity item
  // refuses to submit with an empty reason. There is no more
  // "Mở trong Quản lý Session" secondary path around this requirement --
  // decide() is the only route to Resolve/Ignore now.
  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  await page.locator('.ec-card').first().click(); // items[0] is HIGH severity
  await expect(page.locator('.ec-drawer')).toBeVisible();

  page.once('dialog', dialog => dialog.accept(''));
  let resolveCalled = false;
  await page.route(/\/api\/exceptions\/\d+\/resolve$/, route => { resolveCalled = true; route.fulfill({ json: { ok: true, item: items[0] } }); });

  await page.locator('[data-action="resolve"]').click();
  await page.waitForTimeout(300);
  expect(resolveCalled).toBe(false); // blocked client-side: empty reason on a HIGH-severity item
  await expect(page.locator('.ec-drawer')).toBeVisible(); // drawer stays open

  page.once('dialog', dialog => dialog.accept('Đã kiểm tra và xác nhận với nhân viên.'));
  await page.route(/\/api\/exceptions\/\d+\/resolve$/, route => { resolveCalled = true; route.fulfill({ json: { ok: true, item: { ...items[0], status: 'RESOLVED' } } }); });
  await page.route(/\/api\/exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    route.fulfill({ json: { ok: true, items: items.filter(x => x.id !== items[0].id), total: items.length - 1 } });
  });
  await page.locator('[data-action="resolve"]').click();
  await expect.poll(() => resolveCalled).toBe(true);
  await expect(page.locator('.ec-drawer-shell')).toHaveCount(0);
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
  test(`bố cục không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const items = exceptionItems();
    await openScreen(page, viewport, items);
    await page.locator('.ec-card').first().click();
    await expect(page.locator('.ec-drawer')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    if (viewport.width === 1366) {
      await page.waitForTimeout(250);
      await page.screenshot({ path: `test-results/session-detail-drawer-${viewport.width}.png` });
    }
  });
}

test('Tab Lịch sử hiển thị kết quả đã xử lý', async ({ page }) => {
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
  await page.screenshot({ path: 'test-results/session-history-tab.png', fullPage: true });
});

test('Mở Session điều hướng đúng Session, giữ ngữ cảnh quay lại', async ({ page }) => {
  const items = exceptionItems();
  const target = items[3]; // an arbitrary non-first row -- proves the RIGHT session opens, not always #0
  await page.setViewportSize({ width: 1366, height: 768 });
  await login(page);
  await mockApis(page, items);
  await page.route(/\/api\/session-management\/operations\?/, route =>
    route.fulfill({ json: { ok: true, items: [], filters: { production_orders: [], parts: [], operations: [], employees: [], stations: [] } } }));
  await page.route(/\/api\/session-management\?/, route =>
    route.fulfill({ json: { ok: true, items: [], filters: { production_orders: [], parts: [], operations: [], employees: [], stations: [] } } }));

  await page.evaluate(() => openPage('session-exceptions'));
  await page.locator(`.ec-card[data-id="${target.id}"]`).click();
  await expect(page.locator('.ec-drawer')).toContainText(`SESSION #${target.session_id}`);

  await page.getByRole('button', { name: `Mở Session #${target.session_id}` }).click();

  // Real navigation to Session Management, not just closing the drawer --
  // the exact gap the field report was about.
  await expect(page.locator('#pageTitle')).toHaveText('Quản lý Session');
  await expect(page.locator('.session-exception-context')).toContainText(`Session #${target.session_id}`);
  await expect(page.locator('.session-exception-context')).toContainText('Session mở quá lâu');

  // Back returns to the exception list, same page identity as before --
  // not a generic Home fallback.
  await page.locator('[data-nav-back]').click();
  await expect(page.locator('#pageTitle')).toHaveText('Trung tâm ngoại lệ');
  await expect(page.locator('.ec-card')).toHaveCount(items.length);
});
