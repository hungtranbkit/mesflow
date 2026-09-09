const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  // Trang /login khi đã có phiên sẽ tự điều hướng sang /app; lần goto ngay
  // sau đó bị chính nó cắt ngang ("interrupted by another navigation").
  // Đợi chuyển hướng tự động xong rồi mới đi tiếp -- nguồn flaky lác đác
  // của cả bộ E2E, tìm ra khi truy po-action-menu (2026-09-09).
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

for (const pageId of ['users', 'working-calendar']) {
  test(`capture system ${pageId}`, async ({ page }) => {
    await login(page);
    for (const width of [1920, 1366]) {
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 768 });
      await page.evaluate(id => openPage(id), pageId);
      await page.waitForTimeout(200);
      await page.screenshot({ path: `runtime/screenshots/system-after-${pageId}-${width}.png`, fullPage: true });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(id => openPage(id), pageId);
    await page.screenshot({ path: `runtime/screenshots/system-after-${pageId}-390.png`, fullPage: true });
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate(el => el.clientWidth));
  });
}
