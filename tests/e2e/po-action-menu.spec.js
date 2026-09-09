// Ô "Thao tác" của danh sách PO: một primary cố định theo trạng thái, menu chỉ
// chứa thao tác phụ, và menu không bị cắt cũng không đẻ ra thanh cuộn.
//
// Bug thật trên TEST: PO chạy được thì primary là "Bắt đầu sản xuất" và menu
// lại chứa "Mở PO"; PO khác thì "Mở PO" nằm ngoài. Cùng một action lúc ngoài
// lúc trong menu. Và menu là <details> nằm trong .table-wrap{overflow:auto},
// nên mở ra là bị cắt + wrapper mọc thanh cuộn dọc (đo được 2229px so với
// 2104px trước khi sửa).
const { test, expect } = require('@playwright/test');

const PROD = { id: 1, code: 'QA-PO-RUN', product: 'Khung máy', planned_quantity: 100,
  status: 'IN_PROGRESS', priority: 'NORMAL', source_template_code: 'TPL-1', source_template_version: '1.0' };
const DRAFT = { ...PROD, id: 2, code: 'QA-PO-DRAFT', status: 'DRAFT' };
const DONE = { ...PROD, id: 3, code: 'QA-PO-DONE', status: 'COMPLETED' };
const PAUSED = { ...PROD, id: 4, code: 'QA-PO-PAUSED', status: 'PAUSED' };

async function openList(page, items = [PROD, DRAFT, DONE, PAUSED]) {
  await page.route(/\/api\/production-orders(\?|$)/, route =>
    route.fulfill({ json: { ok: true, items } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=production-orders');
  await expect(page.locator('.po-actions').first()).toBeVisible({ timeout: 20000 });
}

const rowFor = (page, code) => page.locator('tr', { has: page.locator(`strong:text-is("${code}")`) });

test('mỗi trạng thái đúng một primary, và menu không lặp lại nó', async ({ page }) => {
  await openList(page);

  // Primary cố định theo trạng thái.
  await expect(rowFor(page, 'QA-PO-DRAFT').locator('.po-actions .btn.primary')).toHaveText('Bắt đầu sản xuất');
  await expect(rowFor(page, 'QA-PO-PAUSED').locator('.po-actions .btn.primary')).toHaveText('Tiếp tục sản xuất');
  await expect(rowFor(page, 'QA-PO-RUN').locator('.po-actions .btn.primary')).toHaveText('Mở PO');
  await expect(rowFor(page, 'QA-PO-DONE').locator('.po-actions .btn.primary')).toHaveText('Xem PO');

  // Menu chỉ có thao tác phụ — không có "Mở PO"/"Bắt đầu sản xuất" trong đó.
  for (const code of ['QA-PO-DRAFT', 'QA-PO-RUN']) {
    await rowFor(page, code).locator('[data-po-menu]').click();
    const menu = page.locator('.ui-row-menu');
    await expect(menu).toBeVisible();
    await expect(menu.locator('button')).toHaveText(['Sửa thông tin', 'Xóa PO', 'Force Delete · Test/Admin']);
    await page.keyboard.press('Escape');
    await expect(menu).toHaveCount(0);
  }
});

test('mở menu không đẻ thanh cuộn và không làm cao thêm dòng', async ({ page }) => {
  await openList(page);
  const before = await page.evaluate(() => {
    const w = document.querySelector('.table-wrap');
    return { scrollH: w.scrollHeight, clientH: w.clientHeight,
             rowH: document.querySelector('tbody tr').getBoundingClientRect().height };
  });
  await page.locator('[data-po-menu]').first().click();
  await expect(page.locator('.ui-row-menu')).toBeVisible();
  const after = await page.evaluate(() => {
    const w = document.querySelector('.table-wrap');
    return { scrollH: w.scrollHeight, clientH: w.clientHeight,
             rowH: document.querySelector('tbody tr').getBoundingClientRect().height,
             menuParent: document.querySelector('.ui-row-menu').parentElement.tagName };
  });
  expect(after.menuParent).toBe('BODY');                    // portal, không nằm trong ô
  expect(after.scrollH).toBe(before.scrollH);               // wrapper không cao thêm
  expect(after.scrollH).toBeLessThanOrEqual(after.clientH + 1); // không có thanh cuộn dọc
  expect(after.rowH).toBeCloseTo(before.rowH, 0);           // dòng không giãn ra
});

for (const [label, width, height] of [['1920', 1920, 1080], ['1366', 1366, 768], ['thấp', 1366, 560]]) {
  test(`menu của dòng cuối không bị cắt tại ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openList(page);
    await page.locator('[data-po-menu]').last().click();
    const menu = page.locator('.ui-row-menu');
    await expect(menu).toBeVisible();
    const box = await menu.boundingBox();
    expect(box.y, `menu tràn lên trên tại ${label}`).toBeGreaterThanOrEqual(0);
    expect(box.y + box.height, `menu tràn xuống dưới tại ${label}`).toBeLessThanOrEqual(height + 1);
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(width + 1);
    // Và trang vẫn không trượt ngang.
    expect(await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth))
      .toBeLessThanOrEqual(1);
  });
}

test('đóng bằng Escape, bằng click ra ngoài, và aria-expanded đúng', async ({ page }) => {
  await openList(page);
  const trigger = page.locator('[data-po-menu]').first();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');

  await trigger.click();
  await expect(page.locator('.ui-row-menu')).toBeVisible();
  await expect(trigger).toHaveAttribute('aria-expanded', 'true');
  await page.keyboard.press('Escape');
  await expect(page.locator('.ui-row-menu')).toHaveCount(0);
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');

  await trigger.click();
  await expect(page.locator('.ui-row-menu')).toBeVisible();
  await page.locator('h1, .page-header, header').first().click({ force: true });
  await expect(page.locator('.ui-row-menu')).toHaveCount(0);
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

test('bấm vào dòng là mở PO', async ({ page }) => {
  await openList(page);
  await page.route(/\/api\/production-orders\/1(\?|$)/, route =>
    route.fulfill({ json: { ok: true, item: PROD } }));
  await rowFor(page, 'QA-PO-RUN').locator('td').first().click();
  // Điều hướng sang không gian chi tiết PO (tiêu đề đổi theo mã PO).
  await expect(page.locator('#pageTitle, h1').first()).toContainText('QA-PO-RUN', { timeout: 15000 });
});
