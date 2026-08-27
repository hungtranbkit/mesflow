const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

test('Quản lý Session dependent filters với dữ liệu DEV thật', async ({ page }) => {
  test.skip(process.env.MESFLOW_REAL_DATA_SMOKE !== '1', 'Chỉ chạy trên DEV dataset đã preflight');
  const screenshotDir = process.env.MESFLOW_SMOKE_SCREENSHOT_DIR || '/tmp/mesflow-session-filter-smoke';
  fs.mkdirSync(screenshotDir, { recursive: true });

  await page.goto('/login');
  const login = await page.request.post('/api/auth/test-auto-login');
  expect(login.ok()).toBe(true);
  await page.goto('/app');
  await page.evaluate(() => renderSessionManagement());
  await expect(page.locator('#smSessionCount')).toContainText('session');

  const catalogResponse = await page.request.get('/api/session-management/operations?activity=recent&limit=1');
  expect(catalogResponse.ok()).toBe(true);
  const catalog = (await catalogResponse.json()).filters;
  const poIdsWithMultipleParts = catalog.production_orders
    .filter(po => catalog.parts.filter(part => part.production_order_id === po.id).length >= 2)
    .map(po => String(po.id));
  expect(poIdsWithMultipleParts.length).toBeGreaterThanOrEqual(2);

  for (const poId of poIdsWithMultipleParts.slice(0, 2)) {
    await page.locator('#smPo').selectOption(poId);
    const expectedParts = catalog.parts.filter(part => String(part.production_order_id) === poId);
    const expectedOperations = catalog.operations.filter(operation => String(operation.production_order_id) === poId);
    await expect(page.locator('#smPart option')).toHaveCount(expectedParts.length + 1);
    await expect(page.locator('#smOp option')).toHaveCount(expectedOperations.length + 1);

    const partId = String(expectedParts[0].id);
    await page.locator('#smPart').selectOption(partId);
    const partOperations = expectedOperations.filter(operation => String(operation.part_id) === partId);
    await expect(page.locator('#smOp option')).toHaveCount(partOperations.length + 1);
  }

  await page.setViewportSize({ width: 1366, height: 768 });
  await page.screenshot({ path: path.join(screenshotDir, 'session-management-filters-1366x768.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.screenshot({ path: path.join(screenshotDir, 'session-management-filters-390x844.png'), fullPage: true });
});
