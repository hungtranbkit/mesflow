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

test('danh sách toàn chiều rộng và accordion chỉ mở một session', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await openScreen(page, { width: 1366, height: 768 });
  await expect(page.locator('.session-op-layout')).toHaveCount(0);
  await expect(page.locator('#smDetail')).toHaveCount(0);
  await expect(page.locator('.session-accordion-trigger').first()).toContainText(/Đang chạy.*\d+h/);

  await page.locator('.session-accordion-trigger').first().click();
  await expect(page.locator('.session-accordion-detail')).toHaveCount(1);
  await expect(page.locator('.session-accordion-detail')).toContainText('KIOSK-01');
  await expect(page.locator('.session-accordion-detail')).toContainText('Kiểm tra keo đầu ca');
  await expect(page.locator('.sm-edit')).toBeVisible();

  await page.locator('.session-accordion-trigger').nth(1).click();
  await expect(page.locator('.session-accordion-detail')).toHaveCount(1);
  await expect(page.locator('.session-accordion-trigger').nth(1)).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.session-accordion-trigger').first()).toHaveAttribute('aria-expanded', 'false');
  expect(errors).toEqual([]);
});

test('lọc và làm mới giữ session đang mở, không nhảy scroll', async ({ page }) => {
  await openScreen(page, { width: 1366, height: 768 });
  await page.locator('#smSearch').fill('Nhân viên 18');
  await expect(page.locator('.session-accordion-item')).toHaveCount(1);
  await page.locator('.session-accordion-trigger').click();
  await page.locator('.session-accordion-trigger').scrollIntoViewIfNeeded();
  const before = await page.evaluate(() => window.scrollY);
  await Promise.all([
    page.waitForResponse(response => response.url().includes('/api/session-management?')),
    page.locator('#smReload').click()
  ]);
  await page.waitForTimeout(100);
  await expect(page.locator('#smSearch')).toHaveValue('Nhân viên 18');
  await expect(page.locator('.session-accordion-trigger')).toHaveAttribute('aria-expanded', 'true');
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
