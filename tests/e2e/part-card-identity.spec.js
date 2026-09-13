// Thẻ Part gọi tên chi tiết bằng TÊN của nó, không bằng vị trí trong danh sách.
//
// Thẻ cũ mở đầu bằng huy hiệu 'PART 1' rồi '<mã> · <tên>' cùng một cỡ chữ.
// Người mở màn PO đang tìm 'Thân thùng rác', mà chuỗi đó nằm sau một con số
// thứ tự của giao diện và một mã máy. Không ai trong xưởng gọi chi tiết đó là
// "Part 1" -- con số ấy chỉ là vị trí trong danh sách, và nó chiếm mất chỗ
// đứng đầu của thứ người ta thật sự đọc.
//
// Hai màn (Template editor, PO detail) dùng CÙNG một khuôn, nên cả hai phải
// cùng bỏ nhãn đó.
const { test, expect, devices } = require('@playwright/test');

const TEMPLATES = [{ id: 5, code: 'TPL-UI', name: 'Quy trình mẫu', product: 'Thùng rác',
                     version: '1.0', active: true, part_count: 1, operation_count: 1 }];
const TPL_TREE = {
  ok: true, template: TEMPLATES[0],
  parts: [{ id: 51, template_id: 5, code: '10025-FB-201', name: 'Thân thùng rác',
            sort_order: 0, drawing_path: '' }],
  operations: [{ id: 511, template_id: 5, part_id: 51, code: 'THAN-01', name: 'CẮT PHÔI',
                 sort_order: 0, equipment_code: '', standard_seconds_per_unit: '18.000',
                 repair_cycle_time_seconds_per_unit: '0.000', input_flow_enabled: false,
                 input_source_code: null, input_source_kind: 'GOOD', defects_consume_input: true,
                 requires_setup: false, expected_setup_minutes: null, setup_note: '' }],
  equipment: [],
};
const PO = { id: 9, code: 'PO-UI', product: 'Thùng rác', planned_quantity: 500,
             status: 'IN_PROGRESS', priority: 'NORMAL' };
const PO_PARTS = [{ id: 91, production_order_id: 9, code: '10025-FB-201',
                    name: 'Thân thùng rác', sort_order: 0 }];
const PO_OPS = [0, 1, 2].map(i => ({
  id: 900 + i, production_order_id: 9, part_id: 91, code: `PO-UI-OP${i + 1}`,
  name: ['CẮT PHÔI', 'ĐỘT', 'CHẤN'][i], display_key: `PO-UI-OP${i + 1}`,
  operation_type: 'PRODUCTION', status: 'PLANNED', done_qty: 0, defect_qty: 0,
  rework_qty: 0, sort_order: i, qr: `WF|OP|PO-UI-OP${i + 1}`,
}));

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
}

async function openPo(page) {
  await page.route(/\/api\/production-orders\?/, r => r.fulfill({ json: { ok: true, items: [PO] } }));
  await page.route(/\/api\/production-orders\/9(\?|$)/, r => r.fulfill({ json: { ok: true, item: PO } }));
  await page.route(/\/api\/parts\?/, r => r.fulfill({ json: { ok: true, items: PO_PARTS } }));
  await page.route(/\/api\/operations\?/, r => r.fulfill({ json: { ok: true, items: PO_OPS } }));
  await page.route(/\/api\/equipment\?/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-control\?/, r => r.fulfill({ json: { ok: true, operations: [] } }));
  await page.goto('/app?page=production-orders&po_id=9');
  await expect(page.locator('.part-block').first()).toBeVisible({ timeout: 20000 });
}

async function openTemplate(page) {
  await page.route(/\/api\/templates(\?|$)/, r => r.fulfill({ json: { ok: true, items: TEMPLATES } }));
  await page.route(/\/api\/templates\/5\/tree/, r => r.fulfill({ json: TPL_TREE }));
  await page.route(/\/api\/templates\/5(\?|$)/, r => r.fulfill({ json: { ok: true, item: TEMPLATES[0] } }));
  await page.route(/\/api\/templates\/5\/import-history/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/equipment/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.goto('/app?page=templates');
  await page.locator('.template-old-card').first().click();
  await expect(page.locator('.part-block').first()).toBeVisible({ timeout: 20000 });
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1366, height: 900 });
  await login(page);
});

test('màn PO: tên tiếng Việt là chữ chính, mã và số OP là chú thích mờ hơn', async ({ page }) => {
  await openPo(page);
  const card = page.locator('.part-block').first();
  await expect(card.locator('.part-identity > h2')).toHaveText('Thân thùng rác');
  const meta = card.locator('.part-meta');
  await expect(meta.locator('.part-meta-code')).toHaveText('10025-FB-201');
  await expect(meta.locator('.part-meta-ops')).toHaveText('3 Operation');

  const style = await card.evaluate(el => ({
    title: parseFloat(getComputedStyle(el.querySelector('.part-identity > h2')).fontSize),
    meta: parseFloat(getComputedStyle(el.querySelector('.part-meta')).fontSize),
    titleColor: getComputedStyle(el.querySelector('.part-identity > h2')).color,
    metaColor: getComputedStyle(el.querySelector('.part-meta')).color,
  }));
  expect(style.title, 'tên Part phải to hơn dòng chú thích').toBeGreaterThan(style.meta);
  expect(style.metaColor, 'chú thích phải mờ hơn tên').not.toBe(style.titleColor);
});

test('dòng chú thích căn giữa theo chiều dọc, số Operation không bị lệch', async ({ page }) => {
  await openPo(page);
  const centers = await page.locator('.part-meta').first().evaluate(el =>
    [...el.querySelectorAll('.part-meta-code, .part-meta-ops')]
      .map(e => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); }));
  expect(centers.length).toBe(2);
  const spread = Math.max(...centers) - Math.min(...centers);
  expect(spread, `tâm dọc lệch ${spread}px: ${centers}`).toBeLessThanOrEqual(1);
});

for (const [label, open] of [['PO detail', openPo], ['Template editor', openTemplate]]) {
  test(`${label}: không còn nhãn "Part N"`, async ({ page }) => {
    await open(page);
    await expect(page.locator('.part-block-head').first()).not.toHaveText(/\bPart\s*\d+\b/i);
    await expect(page.locator('.part-block-badge')).toHaveCount(0);
  });
}
