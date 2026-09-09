// Hàng chờ sửa -- the UI added 2026-09-09 for migration 0044's rework queue,
// which had shipped with a working backend and no interface at all.
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

function queueItem(overrides = {}) {
  return {
    source_session_id: 701, source_operation_id: 91, defect_qty: 8, rework_qty: 0, scrap_qty: 0,
    pending_qty: 8, source_finished_at: '2026-09-08T09:30:00+07:00',
    employee_id: 900, employee_no: 'NV-001', employee_name: 'Trần Thị B',
    operation_code: 'OP-CAT-LASER', operation_name: 'CẮT LASER',
    production_order_id: 501, po_code: 'PO-501', part_id: 21, part_code: 'PART-01', part_name: 'Khung nhôm',
    ...overrides,
  };
}

async function mockQueue(page, items) {
  await page.route(/\/api\/rework\/queue\?/, route => route.fulfill({ json: { ok: true, items } }));
  await page.route(/\/api\/employees\?/, route => route.fulfill({
    json: { ok: true, items: [{ id: 900, employee_no: 'NV-001', name: 'Trần Thị B' }, { id: 901, employee_no: 'NV-002', name: 'Lê Văn C' }] },
  }));
}

test('hàng chờ sửa liệt kê mục chờ xử lý và có URL riêng', async ({ page }) => {
  await login(page);
  await mockQueue(page, [queueItem(), queueItem({ source_session_id: 702, po_code: 'PO-777', production_order_id: 777, pending_qty: 3, defect_qty: 5, rework_qty: 2 })]);

  // Reached the way a real user does: expand the "Điều hành" group, then
  // click the entry -- this also pins where the page lives in the sidebar.
  await page.locator('.sidebar-group-trigger', { hasText: 'Điều hành' }).click();
  await page.locator('[data-page="rework-queue"]').first().click();
  await expect(page.locator('#pageTitle')).toHaveText('Hàng chờ sửa');
  // The URL-state convention every other page follows (openPage owns it).
  await expect.poll(() => new URL(page.url()).searchParams.get('page')).toBe('rework-queue');
  await expect(page.locator('[data-rq-row]')).toHaveCount(2);
  // 8 + 3 pending across the two rows.
  await expect(page.locator('#rqStats')).toContainText('11');
});

test('lọc theo PO và tìm kiếm phản ánh lên URL, refresh giữ nguyên', async ({ page }) => {
  await login(page);
  await mockQueue(page, [queueItem(), queueItem({ source_session_id: 702, po_code: 'PO-777', production_order_id: 777, pending_qty: 3 })]);
  await page.goto('/app?page=rework-queue');
  await expect(page.locator('[data-rq-row]')).toHaveCount(2);

  await page.locator('#rqPo').selectOption('777');
  await expect(page.locator('[data-rq-row]')).toHaveCount(1);
  await expect.poll(() => new URL(page.url()).searchParams.get('po')).toBe('777');

  await page.reload();
  await expect(page.locator('#pageTitle')).toHaveText('Hàng chờ sửa');
  await expect(page.locator('#rqPo')).toHaveValue('777');
  await expect(page.locator('[data-rq-row]')).toHaveCount(1);
});

test('xử lý một mục: gửi đúng payload, chặn vượt số chờ sửa', async ({ page }) => {
  await login(page);
  await mockQueue(page, [queueItem()]);
  let posted = null;
  await page.route(/\/api\/rework\/queue\/\d+\/resolve$/, route => {
    posted = route.request().postDataJSON();
    return route.fulfill({ json: { ok: true, repaired_qty: posted.repaired_qty, scrapped_qty: posted.scrapped_qty, pending_qty: 0 } });
  });

  await page.goto('/app?page=rework-queue');
  await page.locator('[data-rq-resolve="701"]').click();
  await expect(page.locator('#rqResolve, .ui-modal')).toBeVisible();

  // Over the pending quantity -> refused client-side, nothing sent.
  await page.locator('#rqRepaired').fill('7');
  await page.locator('#rqScrapped').fill('5');
  await page.locator('#rqSave').click();
  await expect(page.locator('#rqError')).toBeVisible();
  expect(posted).toBeNull();

  await page.locator('#rqRepaired').fill('6');
  await page.locator('#rqScrapped').fill('2');
  await page.locator('#rqEmployee').selectOption('901');
  await page.locator('#rqSave').click();

  await expect.poll(() => posted && posted.repaired_qty).toBe(6);
  expect(posted.scrapped_qty).toBe(2);
  expect(Number(posted.employee_id)).toBe(901);
  // resolve() dedupes on request_id -- a retry must never double-credit.
  expect(String(posted.request_id || '')).toContain('701');
});
