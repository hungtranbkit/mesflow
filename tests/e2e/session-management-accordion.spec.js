const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

const filters = {
  production_orders: [{ id: 1, code: 'PO-SESSION-LONG-001', product: 'Cụm carton kiểm tra' }],
  parts: [{ id: 11, production_order_id: 1, code: 'PART-LONG-001', name: 'Chi tiết carton tên rất dài' }],
  operations: [{ id: 101, production_order_id: 1, part_id: 11, code: 'OP-101', name: 'Dán keo carton có tên operation rất dài để kiểm tra ellipsis' }],
  employees: [{ id: 201, employee_no: 'EMP-201', name: 'Lê Đức Thịnh' }],
  stations: [{ id: 301, code: 'ST-01', name: 'Trạm dán keo' }]
};

function sessions() {
  return Array.from({ length: 24 }, (_, index) => ({
    session_id: index + 1,
    employee_id: 201,
    employee_code: `EMP-${String(index + 1).padStart(3, '0')}`,
    employee_name: index ? `Nhân viên ${index + 1}` : 'Lê Đức Thịnh',
    operation_id: 101,
    operation_code: `OP-${String(index + 1).padStart(3, '0')}`,
    operation_name: index ? `Operation ${index + 1}` : 'Dán keo carton có tên operation rất dài để kiểm tra ellipsis',
    po_id: 1, po_code: 'PO-SESSION-LONG-001', part_id: 11,
    part_code: 'PART-LONG-001', part_name: 'Chi tiết carton tên rất dài',
    station_id: 301, station_code: 'ST-01', station_name: 'Trạm dán keo', device_uuid: 'KIOSK-01',
    status: index < 2 ? 'OPEN' : 'CLOSED',
    started_at: new Date(Date.now() - (index + 1) * 3600000).toISOString(),
    ended_at: index < 2 ? null : new Date(Date.now() - index * 3600000).toISOString(),
    duration_seconds: 3600, good_qty: 10 + index, defect_qty: 2, rework_qty: 1,
    note: index === 0 ? 'Kiểm tra keo đầu ca' : ''
  }));
}

async function mockSessionApis(page) {
  await page.route('**/api/session-management/operations?**', route => route.fulfill({ json: { ok: true, items: [], filters } }));
  await page.route(/\/api\/session-management\?.*/, route => route.fulfill({ json: { ok: true, items: sessions(), filters } }));
}

async function openScreen(page, viewport) {
  await page.setViewportSize(viewport);
  await login(page);
  await mockSessionApis(page);
  await page.evaluate(() => openPage('session-management'));
  await expect(page.locator('.session-accordion-item')).toHaveCount(24);
}

// Real fixture for the SessionDetailDrawer's own two API calls
// (/api/session-management/{id} and /api/sessions/{id}/trace), matching
// sessions()[0] above.
function sessionDetailPayload(row) {
  return {
    session: {
      session_id: row.session_id, employee_id: row.employee_id, operation_id: row.operation_id,
      station_id: row.station_id, device_uuid: row.device_uuid, status: row.status,
      started_at: row.started_at, ended_at: row.ended_at,
      good_qty: row.good_qty, defect_qty: row.defect_qty, rework_qty: row.rework_qty, note: row.note,
      employee_code: row.employee_code, employee_name: row.employee_name,
      po_id: row.po_id, po_code: row.po_code, part_id: row.part_id, part_code: row.part_code, part_name: row.part_name,
      operation_code: row.operation_code, operation_name: row.operation_name,
      station_code: row.station_code, station_name: row.station_name, duration_seconds: row.duration_seconds,
      data_source: 'UNKNOWN'
    },
    exceptions: [], activity: [], reviews: []
  };
}

test('accordion trigger mở drawer chi tiết Session (không mở rộng tại chỗ)', async ({ page }) => {
  // Rewritten (2026-08-26): a session row used to expand
  // .session-accordion-detail inline (one at a time, tracked via
  // aria-expanded), with its own "Sửa Session" (.sm-edit) button. app.js's
  // drawSessions() now binds every .session-accordion-trigger to
  // SessionDetailDrawer.open(sessionId,{onOpenManagement:...}) instead --
  // the old inline-detail template is confirmed dead code (nothing calls
  // it from the live render path anymore). "Sửa Session" now lives behind
  // the drawer's "Mở trong Quản lý Session" action, which opens the
  // existing #smModal edit form.
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const rows = sessions();
  await openScreen(page, { width: 1366, height: 768 });
  await expect(page.locator('.session-op-layout')).toHaveCount(0);
  await expect(page.locator('#smDetail')).toHaveCount(0);
  await expect(page.locator('.session-accordion-trigger').first()).toContainText(/Đang chạy.*\d+h/);

  await page.route(/\/api\/session-management\/1$/, route => route.fulfill({ json: { ok: true, ...sessionDetailPayload(rows[0]) } }));
  await page.route(/\/api\/sessions\/1\/trace/, route => route.fulfill({ json: { ok: true, events: [] } }));

  await page.locator('.session-accordion-trigger').first().click();
  await expect(page.locator('.ui-drawer')).toBeVisible();
  await expect(page.locator('.ui-drawer')).toContainText('KIOSK-01');
  await expect(page.locator('.ui-drawer')).toContainText('Kiểm tra keo đầu ca');

  await page.locator('#sdActOpenManagement').click();
  // Fixed 2026-08-26: onOpenManagement now closes the drawer before opening
  // #smModal -- otherwise the modal rendered underneath the drawer's own
  // overlay (z-index 1000 vs the modal's 40) and was unusable.
  await expect(page.locator('.ui-drawer')).toHaveCount(0);
  await expect(page.locator('#smModal')).not.toHaveClass(/hidden/);
  await expect(page.locator('#smEditId')).toHaveText('#1');
  await page.locator('#smClose').click();

  // Only one Session's drawer at a time; closing it never mutates the list.
  await expect(page.locator('.session-accordion-item')).toHaveCount(24);
  expect(errors).toEqual([]);
});

test('lọc và làm mới giữ bộ lọc và vị trí cuộn, không nhảy scroll', async ({ page }) => {
  // The "stays expanded across a reload" half of this test's old name has
  // no current equivalent: the accordion no longer has any expanded state
  // to preserve (see the test above) -- only the filter/scroll-preservation
  // half still applies, so that's all this asserts now.
  await openScreen(page, { width: 1366, height: 768 });
  await page.locator('#smSearch').fill('Nhân viên 18');
  await expect(page.locator('.session-accordion-item')).toHaveCount(1);
  await page.locator('.session-accordion-trigger').scrollIntoViewIfNeeded();
  const before = await page.evaluate(() => window.scrollY);
  await Promise.all([
    page.waitForResponse(response => response.url().includes('/api/session-management?')),
    page.locator('#smReload').click()
  ]);
  await page.waitForTimeout(100);
  await expect(page.locator('#smSearch')).toHaveValue('Nhân viên 18');
  await expect(page.locator('.session-accordion-item')).toHaveCount(1);
  expect(Math.abs((await page.evaluate(() => window.scrollY)) - before)).toBeLessThanOrEqual(2);
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 390, height: 844 }]) {
  test(`không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await openScreen(page, viewport);
    await page.locator('.session-accordion-trigger').first().click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await page.screenshot({ path: `test-results/session-management-${viewport.width}x${viewport.height}.png`, fullPage: true });
  });
}
