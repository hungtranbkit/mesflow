// Tổng quan quy mô PO ngay trên header chi tiết: Part / OP sản xuất / OP phụ.
//
// Đếm phải theo đúng semantics đang dùng: SETUP và SỬA HÀNG là OP phụ, không
// bao giờ làm tăng số OP sản xuất. Số liệu tính ở client từ dữ liệu
// openProductionOrder đã nạp sẵn, nên spec này mock thẳng các endpoint đó.
const { test, expect } = require('@playwright/test');

const PO = { id: 7, code: 'QA-SCALE-PO', product: 'Thùng rác', planned_quantity: 500,
  status: 'IN_PROGRESS', priority: 'NORMAL' };

const PARTS = [
  { id: 71, production_order_id: 7, code: 'THAN', name: 'Thân thùng', sort_order: 0 },
  { id: 72, production_order_id: 7, code: 'NAP', name: 'Nắp thùng', sort_order: 1 },
];

const op = (id, part_id, code, name, type, extra = {}) => ({
  id, production_order_id: 7, part_id, code, name, display_key: code,
  operation_type: type, status: 'IN_PROGRESS', done_qty: 0, defect_qty: 0, rework_qty: 0,
  sort_order: id, qr: `WF|OP|${code}`, ...extra,
});

async function openDetail(page, { parts = PARTS, ops } = {}) {
  await page.route(/\/api\/production-orders\?/, r => r.fulfill({ json: { ok: true, items: [PO] } }));
  await page.route(/\/api\/production-orders\/7(\?|$)/, r => r.fulfill({ json: { ok: true, item: PO } }));
  await page.route(/\/api\/parts\?/, r => r.fulfill({ json: { ok: true, items: parts } }));
  await page.route(/\/api\/operations\?/, r => r.fulfill({ json: { ok: true, items: ops } }));
  await page.route(/\/api\/equipment\?/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-control\?/, r => r.fulfill({ json: { ok: true, operations: [] } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=production-orders&po_id=7');
  await expect(page.locator('.po-workspace-metrics')).toBeVisible({ timeout: 20000 });
}

const chip = (page, label) => page.locator('.po-workspace-metrics span', {
  has: page.locator(`small:text-is("${label}")`) }).locator('b');

test('đếm Part và OP sản xuất, OP phụ tách riêng không lẫn vào', async ({ page }) => {
  await openDetail(page, { ops: [
    op(1, 71, 'THAN-OP1', 'Cắt phôi', 'PRODUCTION'),
    op(2, 71, 'THAN-OP2', 'Chấn mép', 'PRODUCTION'),
    op(3, 71, 'THAN-OP2-SU', 'Setup Chấn mép', 'SETUP', { parent_operation_id: 2 }),
    op(4, 72, 'NAP-OP1', 'Dập nắp', 'PRODUCTION'),
    op(5, 72, 'REWORK-7-NAP', 'SỬA HÀNG', 'REWORK'),
  ]});
  await expect(chip(page, 'Part')).toHaveText('2');
  await expect(chip(page, 'OP sản xuất')).toHaveText('3');
  // SETUP + SỬA HÀNG gộp vào OP phụ, và KHÔNG cộng vào 3 ở trên.
  await expect(chip(page, 'OP phụ')).toHaveText('2');
});

test('PO không có OP phụ thì không hiện chip OP phụ', async ({ page }) => {
  await openDetail(page, { ops: [
    op(1, 71, 'THAN-OP1', 'Cắt phôi', 'PRODUCTION'),
    op(2, 72, 'NAP-OP1', 'Dập nắp', 'PRODUCTION'),
  ]});
  await expect(chip(page, 'OP sản xuất')).toHaveText('2');
  await expect(page.locator('.po-workspace-metrics small:text-is("OP phụ")')).toHaveCount(0);
});

test('PO chưa có Part nào vẫn hiện số 0, không vỡ', async ({ page }) => {
  await openDetail(page, { parts: [], ops: [] });
  await expect(chip(page, 'Part')).toHaveText('0');
  await expect(chip(page, 'OP sản xuất')).toHaveText('0');
  await expect(page.locator('.po-empty, .po-tree')).toBeVisible();
});

test('PO nhiều Part và nhiều OP đếm đúng', async ({ page }) => {
  const parts = Array.from({ length: 6 }, (_, i) =>
    ({ id: 80 + i, production_order_id: 7, code: `P${i}`, name: `Part ${i}`, sort_order: i }));
  const ops = [];
  parts.forEach((p, pi) => {
    for (let k = 0; k < 4; k++) ops.push(op(100 + pi * 10 + k, p.id, `${p.code}-OP${k}`, `Việc ${k}`, 'PRODUCTION'));
    ops.push(op(500 + pi, p.id, `${p.code}-OP0-SU`, `Setup Việc 0`, 'SETUP', { parent_operation_id: 100 + pi * 10 }));
  });
  await openDetail(page, { parts, ops });
  await expect(chip(page, 'Part')).toHaveText('6');
  await expect(chip(page, 'OP sản xuất')).toHaveText('24');
  await expect(chip(page, 'OP phụ')).toHaveText('6');
});

for (const [label, width, height] of [['1920', 1920, 1080], ['1366', 1366, 768], ['mobile', 390, 844]]) {
  test(`dải tổng quan không tràn ngang tại ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openDetail(page, { ops: [
      op(1, 71, 'THAN-OP1', 'Cắt phôi', 'PRODUCTION'),
      op(2, 71, 'THAN-OP1-SU', 'Setup Cắt phôi', 'SETUP', { parent_operation_id: 1 }),
    ]});
    await expect(chip(page, 'Part')).toBeVisible();
    const overflow = await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth);
    expect(overflow, `tràn ngang ${overflow}px tại ${label}`).toBeLessThanOrEqual(1);
    // Mọi ô đều nằm trong dải, không ô nào bị đẩy ra ngoài.
    const inside = await page.evaluate(() => {
      const row = document.querySelector('.po-workspace-metrics').getBoundingClientRect();
      return [...document.querySelectorAll('.po-workspace-metrics span')]
        .every(el => el.getBoundingClientRect().right <= row.right + 1);
    });
    expect(inside).toBe(true);
  });
}

test('thêm OP rồi tải lại chi tiết thì summary cập nhật, không stale', async ({ page }) => {
  let ops = [op(1, 71, 'THAN-OP1', 'Cắt phôi', 'PRODUCTION')];
  await page.route(/\/api\/production-orders\?/, r => r.fulfill({ json: { ok: true, items: [PO] } }));
  await page.route(/\/api\/production-orders\/7(\?|$)/, r => r.fulfill({ json: { ok: true, item: PO } }));
  await page.route(/\/api\/parts\?/, r => r.fulfill({ json: { ok: true, items: PARTS } }));
  await page.route(/\/api\/operations\?/, r => r.fulfill({ json: { ok: true, items: ops } }));
  await page.route(/\/api\/equipment\?/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-control\?/, r => r.fulfill({ json: { ok: true, operations: [] } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=production-orders&po_id=7');
  await expect(chip(page, 'OP sản xuất')).toHaveText('1');
  await expect(page.locator('.po-workspace-metrics small:text-is("OP phụ")')).toHaveCount(0);

  // Thêm một OP sản xuất và một OP setup, rồi vẽ lại đúng như sau khi Lưu.
  ops = [...ops,
    op(2, 71, 'THAN-OP2', 'Chấn mép', 'PRODUCTION'),
    op(3, 71, 'THAN-OP2-SU', 'Setup Chấn mép', 'SETUP', { parent_operation_id: 2 })];
  await page.evaluate(() => window.openProductionOrder(7, { pushNav: false, pushUrl: false }));
  await expect(chip(page, 'OP sản xuất')).toHaveText('2');
  await expect(chip(page, 'OP phụ')).toHaveText('1');
});
