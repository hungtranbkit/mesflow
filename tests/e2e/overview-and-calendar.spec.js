const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

test('tổng quan sản xuất dễ quét và không tràn ở viewport chính', async ({ page }) => {
  // Rewritten (2026-08-26): this page was rebuilt on the MFUI Golden
  // Reference primitives (filterBar/pageShell) some time ago -- the old
  // bespoke "Việc cần xử lý trong xưởng" <h2> and .overview-filters wrapper
  // are gone from the source entirely (confirmed via grep across
  // app/mesflow/web/), not merely renamed; #pageTitle alone now carries the
  // page's title. The real filter bar is MFUI.filterBar's
  // .ui-filter-controls, with 5 fields (Tìm nhanh/Production
  // Order/Repair/Tình trạng/Sắp xếp), not 4.
  await login(page);
  await expect(page.locator('#pageTitle')).toHaveText('Tổng quan sản xuất');
  await expect(page.locator('.ui-filter-controls label')).toHaveCount(5);
  await expect(page.locator('.overview-po-list, .overview-empty, .overview-loading').first()).toBeVisible();
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate(el => el.clientWidth));
});

test('dashboard theo ngày mở ổn định và dùng dữ liệu ca từ API', async ({ page }) => {
  // Rewritten (2026-08-26): "Báo cáo ca sản xuất" is not in the source
  // anywhere (grep-confirmed) -- #pageTitle ("Dashboard theo ngày") is the
  // only page-level heading now; #dailyKpis/#dailyShift already cover the
  // real content this test needs.
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page);
  await page.evaluate(() => openPage('dashboard'));
  await expect(page.locator('#pageTitle')).toHaveText('Dashboard theo ngày');
  await expect(page.locator('#dailyShift option')).not.toHaveCount(0);
  await expect(page.locator('#dailyKpis .daily-kpi')).toHaveCount(4);
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate(el => el.clientWidth));
  expect(errors).toEqual([]);
});

test('danh sách Production Order có luồng tạo và lọc rõ ràng', async ({ page }) => {
  // Rewritten (2026-08-26): "Quản lý lệnh sản xuất" is not in the source
  // anywhere (grep-confirmed) -- #pageTitle ("Production Order") plus
  // #poSummary/#poStatus/the "+ Tạo PO từ Template" button are the real
  // current page-identity markers.
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await login(page);
  await page.evaluate(() => openPage('production-orders'));
  await expect(page.locator('#pageTitle')).toHaveText('Production Order');
  await expect(page.getByRole('button', { name: '+ Tạo PO từ Template' })).toBeVisible();
  await expect(page.locator('#poStatus')).toBeVisible();
  await expect(page.locator('#poStatus option[value="DRAFT"]')).toHaveText('Bản nháp');
  await expect(page.locator('#poStatus option[value="CANCELLED"]')).toHaveText('Đã hủy');
  await expect(page.locator('#poSummary')).not.toBeEmpty();
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate(el => el.clientWidth));
  expect(errors).toEqual([]);
});

test('thêm, sửa giờ, tải lại và xóa ca làm việc', async ({ page }) => {
  await login(page);
  const original = await page.request.get('/api/settings/work-shifts').then(r => r.json());
  const code = `E2E${Date.now()}`;
  const name = `Ca kiểm thử ${code}`;
  try {
    await page.evaluate(() => openPage('working-calendar'));
    await page.getByRole('button', { name: '+ Thêm ca' }).click();
    await page.locator('[name="code"]').fill(code);
    await page.locator('[name="name"]').fill(name);
    await page.getByRole('button', { name: 'Lưu ca làm việc' }).click();
    await expect(page.locator('#shiftList')).toContainText(name);

    const row = page.locator('#shiftList tbody tr').filter({ hasText: code });
    await row.getByRole('button', { name: 'Sửa' }).click();
    await page.locator('[name="anchor_start"]').fill('07:30');
    await page.locator('[name="anchor_start"]').dispatchEvent('change');
    await page.getByRole('button', { name: 'Lưu ca làm việc' }).click();

    await page.reload();
    await page.evaluate(() => openPage('working-calendar'));
    const reloaded = page.locator('#shiftList tbody tr').filter({ hasText: code });
    await expect(reloaded).toContainText('07:30');

    page.once('dialog', dialog => dialog.accept());
    await reloaded.getByRole('button', { name: 'Xóa' }).click();
    await expect(page.locator('#shiftList')).not.toContainText(code);
  } finally {
    await page.request.put('/api/settings/work-shifts', { data: { items: original.items } });
  }
});
