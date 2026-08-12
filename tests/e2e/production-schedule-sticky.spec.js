const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

function scheduleRows() {
  const rows = [];
  for (let po = 1; po <= 3; po += 1) {
    for (let op = 1; op <= 22; op += 1) {
      const start = new Date(`2026-08-${String(10 + po).padStart(2, '0')}T08:00:00+07:00`);
      start.setMinutes(start.getMinutes() + op * 30);
      const end = new Date(start.getTime() + 45 * 60000);
      rows.push({
        po_id: po, po_code: `PO-STICKY-${po}`, product: `Sản phẩm kiểm tra ${po}`,
        po_status: 'IN_PROGRESS', po_end: `2026-08-${18 + po}T17:00:00+07:00`, planned_quantity: 100,
        part_id: po * 10 + Math.ceil(op / 11), part_code: `PART-${po}-${Math.ceil(op / 11)}`,
        part_name: `Part dài của PO ${po}`, operation_id: po * 100 + op,
        operation_code: `OP-${po}-${String(op).padStart(2, '0')}`,
        operation_name: op === 1 ? 'Operation có tên rất dài để kiểm tra không làm vỡ sticky group header' : `Operation ${op}`,
        operation_status: op <= 7 ? 'COMPLETED' : 'READY', done_qty: op <= 7 ? 100 : op * 2,
        defect_qty: 0, rework_qty: 0, progress_percent: op <= 7 ? 100 : op * 2,
        planned_start_at: start.toISOString(), planned_end_at: end.toISOString(), active_sessions: op === 8 ? 1 : 0,
        blocked: false, input_flow_enabled: false
      });
    }
  }
  return rows;
}

async function mockSchedule(page) {
  await page.route('**/api/production-schedule?**', route => route.fulfill({ json: { ok: true, items: scheduleRows() } }));
}

test('filter và PO group header sticky đúng tầng, không duplicate', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width: 1366, height: 768 });
  await login(page);
  await mockSchedule(page);
  await page.evaluate(() => openPage('production-schedule'));

  await expect(page.locator('.schedule-po')).toHaveCount(3);
  await expect(page.locator('.schedule-po-head')).toHaveCount(3);
  await expect(page.locator('.schedule-po').first().locator('.gantt-row')).toHaveCount(22);
  await expect(page.locator('.schedule-po-head').first()).toContainText('7/22 OP hoàn thành');

  const toolbarPosition = await page.locator('#scheduleStickyToolbar').evaluate(el => getComputedStyle(el).position);
  const groupPosition = await page.locator('.schedule-po-head').first().evaluate(el => getComputedStyle(el).position);
  expect(toolbarPosition).toBe('sticky');
  expect(groupPosition).toBe('sticky');

  await page.locator('.schedule-po').first().evaluate(el => window.scrollTo(0, el.offsetTop + 500));
  await page.waitForTimeout(100);
  const toolbar = await page.locator('#scheduleStickyToolbar').boundingBox();
  const group = await page.locator('.schedule-po-head').first().boundingBox();
  expect(group.y).toBeGreaterThanOrEqual(toolbar.y + toolbar.height - 2);
  expect(group.y).toBeLessThanOrEqual(toolbar.y + toolbar.height + 3);

  await page.locator('.schedule-po').nth(1).evaluate(el => window.scrollTo(0, el.offsetTop + 400));
  await page.waitForTimeout(100);
  const nextToolbar = await page.locator('#scheduleStickyToolbar').boundingBox();
  const nextGroup = await page.locator('.schedule-po-head').nth(1).boundingBox();
  const previousGroup = await page.locator('.schedule-po-head').first().boundingBox();
  expect(nextGroup.y).toBeGreaterThanOrEqual(nextToolbar.y + nextToolbar.height - 2);
  expect(nextGroup.y).toBeLessThanOrEqual(nextToolbar.y + nextToolbar.height + 3);
  expect(previousGroup.y + previousGroup.height).toBeLessThanOrEqual(nextGroup.y + 1);
  expect(errors).toEqual([]);
});

test('filter giữ state và refresh không đưa scroll về đầu', async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await mockSchedule(page);
  await page.evaluate(() => openPage('production-schedule'));

  await page.locator('#schedulePoFilter').selectOption('2');
  await expect(page.locator('.schedule-po')).toHaveCount(1);
  await expect(page.locator('.schedule-po-head')).toContainText('PO-STICKY-2');
  await page.locator('.gantt-row').nth(12).scrollIntoViewIfNeeded();
  const before = await page.evaluate(() => window.scrollY);
  await Promise.all([
    page.waitForResponse(response => response.url().includes('/api/production-schedule?')),
    page.locator('#scheduleReload').click()
  ]);
  await page.waitForTimeout(100);
  const after = await page.evaluate(() => window.scrollY);
  await expect(page.locator('#schedulePoFilter')).toHaveValue('2');
  await expect(page.locator('.schedule-po')).toHaveCount(1);
  expect(Math.abs(after - before)).toBeLessThanOrEqual(2);
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 390, height: 844 }]) {
  test(`production schedule không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page);
    await mockSchedule(page);
    await page.evaluate(() => openPage('production-schedule'));
    await expect(page.locator('#schedulePoFilter')).toBeVisible();
    await expect(page.locator('.schedule-po')).toHaveCount(3);
    expect(await page.locator('body').evaluate(body => body.scrollWidth > body.clientWidth)).toBe(false);
    await page.screenshot({ path: `test-results/production-schedule-${viewport.width}x${viewport.height}.png`, fullPage: true });
  });
}
