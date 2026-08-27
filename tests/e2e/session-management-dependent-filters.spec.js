const { test, expect } = require('@playwright/test');

const productionOrders = [
  { id: 1, code: 'PO-A', product: 'Sản phẩm A' },
  { id: 2, code: 'PO-B', product: 'Sản phẩm B' },
];
const parts = [
  { id: 11, production_order_id: 1, code: 'PART-A1', name: 'Part A1' },
  { id: 12, production_order_id: 1, code: 'PART-A2', name: 'Part A2' },
  { id: 21, production_order_id: 2, code: 'PART-B1', name: 'Part B1' },
];
const operations = [
  { id: 111, production_order_id: 1, part_id: 11, code: 'OP-A1-01', name: 'Operation A1' },
  { id: 121, production_order_id: 1, part_id: 12, code: 'OP-A2-01', name: 'Operation A2' },
  { id: 211, production_order_id: 2, part_id: 21, code: 'OP-B1-01', name: 'Operation B1' },
];
const employees = [{ id: 31, employee_no: 'NV-031', name: 'Nguyễn Văn A' }];
const stations = [];

async function login(page, query = '') {
  await page.goto('/login');
  const autoLogin = await page.request.post('/api/auth/test-auto-login');
  if (autoLogin.ok()) {
    await page.goto(`/app${query}`);
  } else {
    const password = process.env.MESFLOW_E2E_PASSWORD;
    if (!password) throw new Error('MESFLOW_E2E_PASSWORD is required when test auto-login is disabled');
    await page.locator('#username').fill(process.env.MESFLOW_E2E_USERNAME || 'admin');
    await page.locator('#password').fill(password);
    await page.locator('#loginForm button[type="submit"]').click();
    await page.waitForURL(/\/app/);
    if (query) await page.goto(`/app${query}`);
  }
  await expect(page.locator('#appLayout')).toBeVisible();
}

async function mockSessionApis(page, { delayed = false } = {}) {
  await page.route(/\/api\/session-management\/operations\?/, async route => {
    const url = new URL(route.request().url());
    const po = Number(url.searchParams.get('po_id') || 0);
    const part = Number(url.searchParams.get('part_id') || 0);
    if (delayed && po === 1) await new Promise(resolve => setTimeout(resolve, 180));
    const filteredParts = parts.filter(item => !po || item.production_order_id === po);
    const filteredOperations = operations.filter(item => (!po || item.production_order_id === po) && (!part || item.part_id === part));
    await route.fulfill({ json: { ok: true, items: [], filters: { production_orders: productionOrders, parts: filteredParts, operations: filteredOperations, employees } } });
  });
  await page.route(/\/api\/session-management\?/, route => route.fulfill({ json: { ok: true, items: [], filters: { production_orders: productionOrders, parts, operations, employees, stations } } }));
}

async function openSessionManagement(page) {
  await page.evaluate(() => renderSessionManagement());
  await expect(page.locator('#smSessionCount')).toContainText('0 session');
}

test('filter hiển thị trực tiếp và dependent PO → Part → Operation không giữ stale value', async ({ page }) => {
  await login(page);
  await mockSessionApis(page);
  await openSessionManagement(page);

  for (const id of ['smDate', 'smPo', 'smPart', 'smOp', 'smEmp', 'smStatus', 'smSearch']) await expect(page.locator(`#${id}`)).toBeVisible();
  await expect(page.getByText('Thêm bộ lọc', { exact: true })).toHaveCount(0);
  await expect(page.locator('#smPart option')).toHaveCount(4);
  await expect(page.locator('#smOp option')).toHaveCount(4);

  await page.locator('#smPo').selectOption('1');
  await expect(page.locator('#smPart option')).toHaveText(['Tất cả Part', 'PART-A1 · Part A1', 'PART-A2 · Part A2']);
  await expect(page.locator('#smOp option')).toHaveText(['Tất cả OP', 'OP-A1-01 · Operation A1', 'OP-A2-01 · Operation A2']);

  await page.locator('#smPart').selectOption('11');
  await expect(page.locator('#smOp option')).toHaveText(['Tất cả OP', 'OP-A1-01 · Operation A1']);
  await page.locator('#smOp').selectOption('111');
  await page.locator('#smPart').selectOption('12');
  await expect(page.locator('#smOp')).toHaveValue('');
  await expect(page.locator('#smOp option')).toHaveText(['Tất cả OP', 'OP-A2-01 · Operation A2']);

  await page.locator('#smPart').selectOption('12');
  await page.locator('#smPo').selectOption('2');
  await expect(page.locator('#smPart')).toHaveValue('');
  await expect(page.locator('#smOp')).toHaveValue('');
  await expect(page.locator('#smPart option')).toHaveText(['Tất cả Part', 'PART-B1 · Part B1']);

  await page.locator('#smPo').selectOption('');
  await expect(page.locator('#smPart option')).toHaveCount(4);
  await expect(page.locator('#smOp option')).toHaveCount(4);
  await page.locator('#smPo').selectOption('1');
  await page.locator('#smPart').selectOption('');
  await expect(page.locator('#smOp option')).toHaveText(['Tất cả OP', 'OP-A1-01 · Operation A1', 'OP-A2-01 · Operation A2']);
});

test('URL hợp lệ được restore; URL không tương thích được normalize', async ({ page }) => {
  await login(page, '?po=1&part=11&operation=111&employee=31&status=OPEN&q=Operation');
  await mockSessionApis(page);
  await openSessionManagement(page);
  await expect(page.locator('#smPo')).toHaveValue('1');
  await expect(page.locator('#smPart')).toHaveValue('11');
  await expect(page.locator('#smOp')).toHaveValue('111');
  await expect(page.locator('#smEmp')).toHaveValue('31');
  await expect(page.locator('#smStatus')).toHaveValue('OPEN');
  await expect(page.locator('#smSearch')).toHaveValue('Operation');

  await page.goto('/app?po=1&part=21&operation=211');
  await openSessionManagement(page);
  await expect(page.locator('#smPo')).toHaveValue('1');
  await expect(page.locator('#smPart')).toHaveValue('');
  await expect(page.locator('#smOp')).toHaveValue('');
  expect(new URL(page.url()).searchParams.get('part')).toBe(null);
  expect(new URL(page.url()).searchParams.get('operation')).toBe(null);
});

test('request cũ không ghi đè lựa chọn mới và filter không overflow viewport nhỏ', async ({ page }) => {
  await login(page);
  await mockSessionApis(page, { delayed: true });
  await openSessionManagement(page);
  await page.locator('#smPo').selectOption('1');
  await page.locator('#smPo').selectOption('2');
  await expect(page.locator('#smPo')).toHaveValue('2');
  await expect(page.locator('#smPart option')).toHaveText(['Tất cả Part', 'PART-B1 · Part B1']);

  await page.setViewportSize({ width: 390, height: 844 });
  const geometry = await page.locator('.session-manage-filter').evaluate(element => ({
    left: element.getBoundingClientRect().left,
    right: element.getBoundingClientRect().right,
    viewport: document.documentElement.clientWidth,
    bodyOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  }));
  expect(geometry.left).toBeGreaterThanOrEqual(0);
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewport + 1);
  expect(geometry.bodyOverflow).toBe(false);
  await expect(page.locator('.session-more-filters')).toHaveCount(0);
});
