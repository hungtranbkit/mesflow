const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

function exceptionItems() {
  const items = [];
  for (let i = 0; i < 14; i++) {
    items.push({
      session_id: 500 + i,
      exception_code: 'OPEN_TOO_LONG',
      exception_fingerprint: `OPEN_TOO_LONG:0#${i}`,
      severity: 'ERROR',
      exception_message: 'Session đang mở quá 12 giờ',
      conflict_session_id: null,
      is_active: true,
      secondary_evidence: false,
      session_status: 'OPEN',
      started_at: new Date(Date.now() - (17 - i * 0.1) * 3600000).toISOString(),
      ended_at: null,
      duration_seconds: (17 - i * 0.1) * 3600,
      good_qty: 0, defect_qty: 0, rework_qty: 0,
      station_id: 301, device_uuid: 'ESP-KIOSK-07',
      data_source: 'UNKNOWN', source_trace_id: '',
      employee_id: 900 + i, employee_code: `NV-${String(i + 1).padStart(3, '0')}`,
      employee_name: i === 0 ? 'Phạm Văn A' : `Nhân viên Test ${i + 1}`,
      operation_code: 'OP-CAT-LASER', operation_name: 'CẮT LASER',
      po_code: 'PO-260813-01', part_code: 'PART-01',
      workflow_status: 'NEW', resolution: '', review_note: '', assigned_to: '',
      review_started_at: null, started_by: '', review_created_at: null,
      resolved_at: null, resolved_by: '', review_updated_at: null,
      classification: 'ACTION_REQUIRED', data_impact: 'working_time/employee_state',
      human_decision_required: true
    });
  }
  return items;
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
      operation_id_ref: 101, operation_code: item.operation_code, operation_name: item.operation_name,
      station_code: 'ST-07', station_name: 'Trạm cắt laser 07', duration_seconds: item.duration_seconds,
      data_source: 'UNKNOWN'
    },
    exceptions: [item],
    activity: [
      { id: 1, event_type: 'SCAN_EMPLOYEE', severity: 'INFO', status: 'OK', message: 'Quét nhân viên thành công', occurred_at: item.started_at },
      { id: 2, event_type: 'SESSION_START', severity: 'INFO', status: 'OK', message: 'Bắt đầu Session', occurred_at: item.started_at }
    ],
    reviews: []
  };
}

async function mockApis(page, items) {
  await page.route(/\/api\/session-exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    route.fulfill({ json: { ok: true, items, view: 'inbox' } });
  });
  await page.route(/\/api\/session-management\/\d+$/, route => {
    const id = Number(route.request().url().match(/\/(\d+)$/)[1]);
    const item = items.find(x => x.session_id === id) || items[0];
    route.fulfill({ json: { ok: true, ...sessionDetailPayload(item) } });
  });
  await page.route(/\/api\/session-exceptions\/workflow$/, route => {
    route.fulfill({ json: { ok: true, items: [], updated_count: 1 } });
  });
}

async function openScreen(page, viewport, items) {
  await page.setViewportSize(viewport);
  await login(page);
  await mockApis(page, items);
  await page.evaluate(() => openPage('session-exceptions'));
  await expect(page.locator('.se-card')).toHaveCount(items.length);
}

test('Xem session mở drawer tại chỗ, không điều hướng trang', async ({ page }) => {
  const pageErrors = [];
  const consoleErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  // 1. Danh sách hiển thị dạng card Header/Body/Footer.
  const firstCard = page.locator('.se-card').first();
  await expect(firstCard.locator('.se-card-who b')).toHaveText('Phạm Văn A');
  await expect(firstCard.locator('.se-card-op')).toContainText('CẮT LASER');
  await expect(firstCard.locator('.se-card-message')).toContainText('Session đang mở quá 12 giờ');
  await expect(firstCard.locator('.se-card-impact')).toContainText('Ảnh hưởng');
  await expect(firstCard.locator('[data-act="process"]')).toBeVisible();
  await expect(firstCard.locator('[data-act="ignore"]')).toBeVisible();
  await expect(firstCard.locator('[data-act="view"]')).toBeVisible();

  await page.screenshot({ path: 'test-results/session-exception-list-1920.png', fullPage: true });

  // 2. Apply a filter.
  await page.locator('#seSearch').fill('Test 5');
  await expect(page.locator('.se-card')).toHaveCount(1);

  // 3. Scroll down.
  await page.evaluate(() => window.scrollTo(0, 200));
  const scrollBefore = await page.evaluate(() => window.scrollY);

  // 4. Click Xem session.
  const urlBefore = page.url();
  await page.locator('.se-card [data-act="view"]').click();

  // 5. Drawer appears.
  await expect(page.locator('.drawer-panel')).toBeVisible();
  // 6. URL/page does not change to Session Management.
  expect(page.url()).toContain(urlBefore.split('?')[0]);
  expect(page.url()).not.toContain('session-management');
  await expect(page.locator('#pageTitle')).toHaveText('Phiên làm việc bất thường');

  // 7. Session data is correct.
  await expect(page.locator('.drawer-head')).toContainText('Nhân viên Test 5');
  await expect(page.locator('.drawer-body')).toContainText('Session đang mở quá 12 giờ');
  await expect(page.locator('.drawer-body')).toContainText('Ảnh hưởng: thời gian công đoạn đang sai');
  await expect(page.locator('.drawer-body')).toContainText('ESP-KIOSK-07');
  await expect(page.locator('.drawer-body')).toContainText('SCAN_EMPLOYEE');
  // Technical details collapsible.
  await expect(page.locator('.drawer-tech summary')).toHaveText('Chi tiết kỹ thuật');

  await page.waitForTimeout(250); // let the drawer's slide-in animation settle before capturing
  // Viewport-only (not fullPage): fullPage screenshot-stitching duplicates a
  // position:fixed element (the drawer) across tiles, producing a ghosting
  // artifact -- the drawer is 100vh tall so nothing below the fold to miss.
  await page.screenshot({ path: 'test-results/session-detail-drawer-1920.png' });

  // 8. Close drawer.
  await page.locator('#sdClose').click();
  await expect(page.locator('.drawer-backdrop')).toBeHidden();

  // 9. Filter and scroll position remain.
  await expect(page.locator('#seSearch')).toHaveValue('Test 5');
  await expect(page.locator('.se-card')).toHaveCount(1);
  const scrollAfter = await page.evaluate(() => window.scrollY);
  expect(Math.abs(scrollAfter - scrollBefore)).toBeLessThanOrEqual(2);

  // 10. Open another session.
  await page.locator('#seSearch').fill('');
  await expect(page.locator('.se-card')).toHaveCount(items.length);
  await page.locator('.se-card').nth(2).locator('[data-act="view"]').click();
  await expect(page.locator('.drawer-panel')).toBeVisible();
  await expect(page.locator('.drawer-head')).toContainText(items[2].employee_name);

  expect(pageErrors).toEqual([]);
  expect(consoleErrors).toEqual([]);
});

test('Xử lý trong drawer cập nhật danh sách, không điều hướng', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));

  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);

  await page.locator('.se-card').first().locator('[data-act="view"]').click();
  await expect(page.locator('.drawer-panel')).toBeVisible();

  // 11. Resolve/Ignore test case (safe mocked fixture).
  await page.locator('#sdActClaim').click();
  await expect(page.locator('#seModal')).toBeVisible();
  await page.locator('#seAssigned').fill('Quản đốc test');

  let listReloaded = false;
  await page.route(/\/api\/session-exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    listReloaded = true;
    const updated = items.map(x => x.session_id === items[0].session_id ? { ...x, workflow_status: 'IN_PROGRESS' } : x);
    route.fulfill({ json: { ok: true, items: updated, view: 'inbox' } });
  });

  await page.locator('#seModalSave').click();
  await expect(page.locator('#seModal')).toBeHidden();

  // 12. Active list updates without full-page navigation.
  await expect.poll(() => listReloaded).toBe(true);
  await expect(page.locator('#appLayout')).toBeVisible();
  expect(page.url()).not.toContain('session-management');

  // Drawer closed/updated after the workflow save, per spec.
  await expect(page.locator('.drawer-backdrop')).toBeHidden();

  expect(pageErrors).toEqual([]);
});

test('Mở trong Quản lý Session là hành động phụ, không bắt buộc', async ({ page }) => {
  const items = exceptionItems();
  await openScreen(page, { width: 1920, height: 1080 }, items);
  await page.locator('.se-card').first().locator('[data-act="view"]').click();
  await expect(page.locator('.drawer-panel')).toBeVisible();
  const openMgmt = page.locator('#sdActOpenManagement');
  await expect(openMgmt).toBeVisible();
  await expect(openMgmt).toHaveText('Mở trong Quản lý Session');
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }]) {
  test(`bố cục không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const items = exceptionItems();
    await openScreen(page, viewport, items);
    await page.locator('.se-card').first().locator('[data-act="view"]').click();
    await expect(page.locator('.drawer-panel')).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    if (viewport.width === 1366) {
      await page.waitForTimeout(250);
      await page.screenshot({ path: `test-results/session-detail-drawer-${viewport.width}.png` });
    }
  });
}

test('Tab Lịch sử hiển thị kết quả đã xử lý', async ({ page }) => {
  const items = exceptionItems().map((x, i) => i === 0 ? { ...x, workflow_status: 'RESOLVED', resolution: 'DATA_CORRECTED', resolved_by: 'admin', resolved_at: new Date().toISOString(), classification: 'HISTORY_ONLY' } : x);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await page.route(/\/api\/session-exceptions(\?.*)?$/, route => {
    if (route.request().method() !== 'GET') return route.fallback();
    const url = route.request().url();
    const view = url.includes('view=history') || url.includes('view=all') ? 'history' : 'inbox';
    route.fulfill({ json: { ok: true, items: view === 'history' ? items : items.filter(x => x.workflow_status !== 'RESOLVED'), view } });
  });
  await page.evaluate(() => openPage('session-exceptions'));
  await page.locator('[data-se-view="HISTORY"]').click();
  await expect(page.locator('.se-card')).toHaveCount(1);
  await expect(page.locator('.se-card .workflow-badge').first()).toHaveText('Đã xử lý');
  await page.screenshot({ path: 'test-results/session-history-tab.png', fullPage: true });
});
