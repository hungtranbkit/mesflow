const { test, expect } = require('@playwright/test');

for (const status of [200, 404]) {
  test(`late KIMEX manifest ${status} cannot corrupt the ESP tutorial tab`, async ({ page }) => {
    await page.goto('/login');
    await page.request.post('/api/auth/test-auto-login');
    await page.goto('/app');
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    let capture;
    const pending = new Promise(resolve => { capture = resolve; });
    await page.route('**/tutorials/manifest.json', route => { capture(route); });
    await page.evaluate(() => {
      window.pendingTutorialRender = renderVideoGuideKimex().then(
        () => ({ ok: true }), error => ({ ok: false, error: error.message }));
    });
    const route = await pending;
    await page.evaluate(() => renderEspKioskTutorial());
    await expect(page.locator('#espTutorialWorkspace')).toBeVisible();
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ videos: [] }) });
    expect(await page.evaluate(() => window.pendingTutorialRender)).toEqual({ ok: true });
    expect(errors).toEqual([]);
    await expect(page.locator('#espTutorialWorkspace')).toBeVisible();
    await expect(page.getByRole('button', { name: 'ESP Kiosk', exact: true })).toHaveClass(/active/);
  });
}
