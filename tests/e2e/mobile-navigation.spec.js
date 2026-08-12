const { test, expect } = require('@playwright/test');
const path = require('path');

test('mobile sidebar allows switching to another tab', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/login');
  if (await page.locator('#loginForm').isVisible()) {
    await page.request.post('/api/auth/test-auto-login');
    await page.goto('/app');
  }
  await page.addStyleTag({ path: path.join(__dirname, '../../app/mesflow/web/static/ui.css') });

  await page.locator('#mobileMenuToggle').click();
  await expect(page.locator('#appSidebar')).toBeVisible();
  await page.getByRole('button', { name: 'Kế hoạch' }).click();
  await page.locator('[data-page="production-orders"]').click();

  await expect(page.locator('#pageTitle')).toHaveText('Production Order');
  await expect(page.locator('body')).not.toHaveClass(/sidebar-mobile-open/);
});
