const { test, expect } = require('@playwright/test');

const surfaces = ['employees', 'qr-print', 'equipment'];

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

for (const pageId of surfaces) {
  test(`capture catalog ${pageId}`, async ({ page }) => {
    await login(page);
    for (const width of [1920, 1366]) {
      await page.setViewportSize({ width, height: width === 1920 ? 1080 : 768 });
      await page.evaluate(id => openPage(id), pageId);
      await page.waitForTimeout(250);
      await page.screenshot({ path: `runtime/screenshots/catalog-after-${pageId}-${width}.png` });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(id => openPage(id), pageId);
    await page.waitForTimeout(150);
    await page.screenshot({ path: `runtime/screenshots/catalog-after-${pageId}-390.png` });
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', await page.locator('body').evaluate(el => el.clientWidth));
  });
}
