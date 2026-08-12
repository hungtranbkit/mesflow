const { test, expect } = require('@playwright/test');

const pages = [
  'session-management',
  'session-exceptions',
  'production-schedule',
  'kiosk-management',
  'system-logs',
  'working-calendar',
];

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

for (const pageId of pages) {
  test(`capture ${pageId}`, async ({ page }) => {
    await login(page);
    for (const width of [1920, 1366]) {
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 768 });
      await page.evaluate(id => openPage(id), pageId);
      await page.waitForTimeout(200);
      await page.screenshot({ path: `runtime/screenshots/after-${pageId}-${width}.png` });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(id => openPage(id), pageId);
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate(el => el.clientWidth));
  });
}
