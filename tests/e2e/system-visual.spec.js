const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
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
