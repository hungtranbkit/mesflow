const { test, expect } = require('@playwright/test');

const ITEMS = [
  { id: 44, code: 'AA-TIED', product: 'Product', planned_quantity: 1, status: 'PLANNED', created_at: '2026-11-28T01:00:00Z' },
  { id: 43, code: 'ZZ-TIED', product: 'Product', planned_quantity: 1, status: 'PLANNED', created_at: '2026-11-28T01:00:00Z' },
  { id: 42, code: 'AA-OLDER', product: 'Product', planned_quantity: 1, status: 'PLANNED', created_at: '2026-11-28T00:00:00Z' },
  { id: 41, code: 'ZZ-OLDEST', product: 'Product', planned_quantity: 1, status: 'PLANNED', created_at: '2026-11-27T23:00:00Z' },
];

async function openProductionOrders(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=production-orders&tab=overview&date=2026-11-28');
  await expect(page.locator('.po-card').first()).toBeVisible();
}

test('production order page preserves API creation order on load and reload', async ({ page }) => {
  const listRequests = [];
  await page.route(/\/api\/production-orders\?/, async route => {
    listRequests.push(new URL(route.request().url()).searchParams.toString());
    await route.fulfill({ json: { ok: true, items: ITEMS } });
  });

  await openProductionOrders(page);
  const codes = () => page.locator('#poList .po-card').evaluateAll(cards => cards.map(card => card.dataset.poCode));
  expect(await codes()).toEqual(ITEMS.map(item => item.code));
  expect(listRequests[0]).toBe('limit=500'); // URL date/tab are not a list filter today.

  await page.locator('#reloadPO').click();
  await expect.poll(codes).toEqual(ITEMS.map(item => item.code));
  expect(listRequests).toHaveLength(2);
  expect(listRequests[1]).toBe('limit=500');
});
