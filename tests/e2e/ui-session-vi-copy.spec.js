const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

async function mockDashboard(page) {
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(new Date());
  await page.route('**/api/settings/work-shifts', route => route.fulfill({ json: { ok: true, items: [{
    id: 1, code: 'DAY', name: 'Ca ngày', active: true, anchor_start: '00:00', anchor_end: '23:59',
    cross_midnight: false, target_minutes: 480,
    intervals: [{ interval_type: 'WORK', start_minute: 0, end_minute: 1439, sort_order: 0 }]
  }] } }));
  await page.route('**/api/dashboard/day?**', route => route.fulfill({ json: {
    ok: true,
    items: [{
      operation_id: 7, operation_code: 'OP-CAT-LASER-WITH-A-VERY-LONG-CODE-001',
      operation_name: 'Setup CAT LASER / CAT LASER với tên công đoạn rất dài',
      po_code: 'PO-E2E-WITH-A-VERY-LONG-CODE', part_code: 'PART-E2E-WITH-A-VERY-LONG-CODE',
      part_name: 'Chi tiết CAT LASER', day_work_seconds: 3000, planned_work_seconds: 6000,
      planned_quantity: 200, total_good_qty: 0, day_good_qty: 0, day_defect_qty: 0,
      day_rework_qty: 0, session_count: 2, open_session_count: 1, day_state: 'RUNNING',
      active_workers: [{ employee_id: 24, employee_name: 'Nguyễn Chí Linh với tên hiển thị rất dài' }]
    }],
    activity: [],
    sessions: [{
      session_id: 71, session_status: 'OPEN', started_at: `${today}T01:00:00.000Z`, ended_at: null,
      employee_id: 24, employee_code: 'NV024-WITH-A-VERY-LONG-CODE',
      employee_name: 'Nguyễn Chí Linh với tên hiển thị rất dài', operation_id: 7,
      operation_code: 'OP-CAT-LASER-WITH-A-VERY-LONG-CODE-001',
      operation_name: 'Setup CAT LASER / CAT LASER với tên công đoạn rất dài',
      po_code: 'PO-E2E-WITH-A-VERY-LONG-CODE', part_code: 'PART-E2E-WITH-A-VERY-LONG-CODE',
      good_qty: 0, defect_qty: 0, output_recorded: false
    }]
  } }));
}

for (const viewport of [
  { width: 390, height: 844 }, { width: 428, height: 926 },
  { width: 768, height: 900 }, { width: 1366, height: 768 }
]) {
  test(`copy phiên làm việc và hai tab Dashboard không tràn tại ${viewport.width}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await login(page);
    await mockDashboard(page);
    await page.evaluate(() => openPage('dashboard'));

    await expect(page.locator('[data-dashboard-tab="people"]')).toHaveText('B · Nhân viên / phiên làm việc');
    const operationCard = page.locator('[data-dashboard-pane="overview"] .op-card:visible').first();
    await expect(operationCard).toContainText('2 phiên làm việc · 1 đang chạy');
    const operationFonts = await operationCard.locator('.op-identity').evaluate(el => ({
      title: getComputedStyle(el.querySelector('.row-title')).fontSize,
      meta: getComputedStyle(el.querySelector('.op-identity-meta')).fontSize,
    }));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: `test-results/ui-session-vi-operation-${viewport.width}.png`, fullPage: true });

    await page.locator('[data-dashboard-tab="people"]').click();
    await expect(page.locator('[data-dashboard-pane="people"]')).toBeVisible();
    await expect(page.locator('.employee-day-person')).toContainText('1 phiên làm việc · 1 chưa đóng');
    const peopleIdentity = page.locator('.emp-op-item .op-identity').first();
    await expect(peopleIdentity).toBeVisible();
    const peopleFonts = await peopleIdentity.evaluate(el => ({
      title: getComputedStyle(el.querySelector('.row-title')).fontSize,
      meta: getComputedStyle(el.querySelector('.op-identity-meta')).fontSize,
    }));
    if (viewport.width <= 768) expect(peopleFonts).toEqual(operationFonts);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
    await page.screenshot({ path: `test-results/ui-session-vi-people-${viewport.width}.png`, fullPage: true });

    await page.evaluate(() => openPage('session-exceptions'));
    await expect(page.locator('#nav button[data-page="session-exceptions"]')).toContainText('Phiên làm việc bất thường');
    await expect(page.locator('#pageTitle')).toHaveText('Các phiên làm việc bất thường');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true);
  });
}
