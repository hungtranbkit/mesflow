// Ba chỉnh sửa giao diện của cùng một ý: đưa thứ NGƯỜI DÙNG tìm lên trước, và
// bỏ những thứ chỉ có nghĩa với phần mềm.
//
//   * Danh sách PO không còn nút "Xuất Excel": nó tải Operation của MỌI PO,
//     không phải của PO nào cả. Xuất Excel chỉ có nghĩa trong ngữ cảnh một PO,
//     và ở đó đã có "Xuất Excel + QR".
//   * Danh sách Template là những THẺ RỜI có khe dọc nhìn thấy được, và thẻ
//     đang chọn phải nhận ra ngay -- kể cả bằng bàn phím và bằng trợ năng.
//   * Thẻ Part lấy TÊN TIẾNG VIỆT làm nội dung chính. 'Part 1' là số thứ tự
//     của giao diện; không ai trong xưởng gọi 'Thân thùng rác' là "Part 1".
const { test, expect } = require('@playwright/test');

const TEMPLATES = [
  { id: 5, code: 'TPL-UI', name: 'Quy trình mẫu', product: 'Thùng rác', version: '1.0',
    active: true, part_count: 1, operation_count: 2 },
  { id: 6, code: 'TPL-UI-2', name: 'Quy trình thứ hai', product: 'Ghế', version: '1.0',
    active: true, part_count: 1, operation_count: 1 },
];
const TPL_TREE = {
  ok: true, template: TEMPLATES[0],
  parts: [{ id: 51, template_id: 5, code: '10025-FB-201', name: 'Thân thùng rác',
            drawing_code: 'KM- 100.25FB- 201', sort_order: 0, drawing_path: '' }],
  operations: [{ id: 511, template_id: 5, part_id: 51, code: 'THAN-01',
                 name: 'CẮT PHÔI', sort_order: 0, equipment_code: '',
                 standard_seconds_per_unit: '18.000',
                 repair_cycle_time_seconds_per_unit: '0.000', input_flow_enabled: false,
                 input_source_code: null, input_source_kind: 'GOOD',
                 defects_consume_input: true, requires_setup: false,
                 expected_setup_minutes: null, setup_note: '' }],
  equipment: [],
};

const PO = { id: 9, code: 'PO-UI', product: 'Thùng rác', planned_quantity: 500,
             status: 'IN_PROGRESS', priority: 'NORMAL' };
const PO_PARTS = [{ id: 91, production_order_id: 9, code: '10025-FB-201',
                    name: 'Thân thùng rác', drawing_code: 'KM- 100.25FB- 201',
                    sort_order: 0 }];
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

// Cả HAI Template phải trả lời được: bài "chọn thẻ thứ hai" bấm vào template 6,
// và nếu chỉ giả lập template 5 thì lần fetch hỏng, màn không vẽ lại, và bài
// trượt vì một lý do chẳng liên quan gì tới trạng thái chọn.
function treeFor(id) {
  const template = TEMPLATES.find(t => Number(t.id) === Number(id)) || TEMPLATES[0];
  return {
    ...TPL_TREE, template,
    parts: TPL_TREE.parts.map(p => ({ ...p, template_id: template.id })),
    operations: TPL_TREE.operations.map(o => ({ ...o, template_id: template.id })),
  };
}

async function routeTemplates(page) {
  await page.route(/\/api\/templates(\?|$)/, r => r.fulfill({ json: { ok: true, items: TEMPLATES } }));
  await page.route(/\/api\/templates\/\d+\/import-history/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/templates\/(\d+)\/tree/, r => r.fulfill({
    json: treeFor(r.request().url().match(/\/templates\/(\d+)\/tree/)[1]) }));
  await page.route(/\/api\/templates\/(\d+)(\?|$)/, r => {
    const id = r.request().url().match(/\/templates\/(\d+)/)[1];
    r.fulfill({ json: { ok: true, item: treeFor(id).template } });
  });
  await page.route(/\/api\/equipment/, r => r.fulfill({ json: { ok: true, items: [] } }));
}

async function routePo(page) {
  await page.route(/\/api\/production-orders\?/, r => r.fulfill({ json: { ok: true, items: [PO] } }));
  await page.route(/\/api\/production-orders\/9(\?|$)/, r => r.fulfill({ json: { ok: true, item: PO } }));
  await page.route(/\/api\/parts\?/, r => r.fulfill({ json: { ok: true, items: PO_PARTS } }));
  await page.route(/\/api\/operations\?/, r => r.fulfill({ json: { ok: true, items: PO_OPS } }));
  await page.route(/\/api\/equipment\?/, r => r.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-control\?/, r => r.fulfill({ json: { ok: true, operations: [] } }));
}

// --- danh sách PO: không còn nút xuất Excel toàn cục ----------------------

test('danh sách PO không có nút "Xuất Excel" — xuất Excel thuộc về MỘT PO', async ({ page }) => {
  await login(page);
  await routePo(page);
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/app?page=production-orders');
  const header = page.locator('.page-header-actions');
  await expect(header).toBeVisible({ timeout: 20000 });
  await expect(header.getByRole('button', { name: /Xuất Excel/i })).toHaveCount(0);
  // Nút tạo PO vẫn còn -- bài này chỉ gỡ đúng một thứ.
  await expect(header.getByRole('button', { name: /Tạo PO từ Template/i })).toHaveCount(1);
});

test('màn CHI TIẾT PO vẫn có nút xuất Excel kèm QR', async ({ page }) => {
  await login(page);
  await routePo(page);
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/app?page=production-orders&po_id=9');
  await expect(page.locator('.po-detail-actions')).toBeVisible({ timeout: 20000 });
  await expect(page.locator('#poExportRouter')).toHaveText(/Xuất Excel \+ QR/);
});

// --- danh sách Template: thẻ rời, trạng thái chọn rõ ----------------------

async function openTemplateList(page) {
  await routeTemplates(page);
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/app?page=templates');
  await expect(page.locator('.template-old-card').first()).toBeVisible({ timeout: 20000 });
}

test('thẻ Template rời nhau: có khe dọc nhìn thấy được và bo góc riêng', async ({ page }) => {
  await login(page);
  await openTemplateList(page);
  const cards = page.locator('.template-old-card');
  await expect(cards).toHaveCount(2);
  const [a, b] = [await cards.nth(0).boundingBox(), await cards.nth(1).boundingBox()];
  const gap = b.y - (a.y + a.height);
  expect(gap, `khe dọc giữa hai thẻ chỉ ${gap}px`).toBeGreaterThanOrEqual(4);
  const shape = await cards.first().evaluate(el => {
    const cs = getComputedStyle(el);
    return { radius: parseFloat(cs.borderTopLeftRadius), width: parseFloat(cs.borderTopWidth) };
  });
  expect(shape.radius, 'thẻ phải bo góc').toBeGreaterThan(0);
  expect(shape.width, 'thẻ phải có viền riêng, không chỉ một đường kẻ dưới').toBeGreaterThan(0);
});

test('thẻ đang chọn nói ra được cho cả mắt lẫn trợ năng', async ({ page }) => {
  await login(page);
  await openTemplateList(page);
  const cards = page.locator('.template-old-card');
  const background = i => cards.nth(i).evaluate(el => getComputedStyle(el).backgroundColor);
  // Chọn thẻ THỨ HAI: màn có thể đã tự chọn thẻ đầu khi mở, nên so thẻ vừa
  // chọn với thẻ còn lại mới nói được điều gì.
  await cards.nth(1).click();
  await expect(cards.nth(1)).toHaveAttribute('aria-current', 'true');
  await expect(cards.nth(0)).not.toHaveAttribute('aria-current', 'true');
  expect(await background(1), 'thẻ đang chọn phải khác nền thẻ thường')
    .not.toBe(await background(0));
});

test('đi bằng bàn phím thì thấy viền focus', async ({ page }) => {
  await login(page);
  await openTemplateList(page);
  // focus-visible chỉ bật khi tiêu điểm ĐẾN TỪ BÀN PHÍM, nên phải Tab thật
  // chứ không gọi .focus().
  await page.locator('#tplSearch').focus();
  let reached = false;
  for (let i = 0; i < 25 && !reached; i += 1) {
    await page.keyboard.press('Tab');
    reached = await page.evaluate(
      () => !!document.activeElement?.classList?.contains('template-old-card'));
  }
  expect(reached, 'không Tab tới được thẻ Template').toBe(true);
  const outline = await page.evaluate(
    () => getComputedStyle(document.activeElement).outlineWidth);
  expect(parseFloat(outline), 'không có viền focus thì bàn phím đi mù').toBeGreaterThan(0);
});

// --- thẻ Part: tên tiếng Việt là chính -----------------------------------

test('thẻ Part ở màn PO: tên tiếng Việt to nhất, mã và số OP là chú thích', async ({ page }) => {
  await login(page);
  await routePo(page);
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/app?page=production-orders&po_id=9');
  const card = page.locator('.part-block').first();
  await expect(card).toBeVisible({ timeout: 20000 });

  const title = card.locator('.part-identity > h2');
  await expect(title).toHaveText('Thân thùng rác');
  const meta = card.locator('.part-meta');
  await expect(meta.locator('.part-meta-code')).toHaveText('10025-FB-201');
  await expect(meta.locator('.part-meta-drawing')).toHaveText('Bản vẽ KM- 100.25FB- 201');
  await expect(meta.locator('.part-meta-ops')).toHaveText('3 Operation');

  const sizes = await card.evaluate(el => ({
    title: parseFloat(getComputedStyle(el.querySelector('.part-identity > h2')).fontSize),
    meta: parseFloat(getComputedStyle(el.querySelector('.part-meta')).fontSize),
    titleColor: getComputedStyle(el.querySelector('.part-identity > h2')).color,
    metaColor: getComputedStyle(el.querySelector('.part-meta')).color,
  }));
  expect(sizes.title, 'tên Part phải to hơn dòng chú thích').toBeGreaterThan(sizes.meta);
  expect(sizes.metaColor, 'chú thích phải mờ hơn tên').not.toBe(sizes.titleColor);
  await expect(card.locator('.part-block-head')).not.toHaveText(/\bPart\s*\d+\b/i);
});

test('dòng chú thích căn giữa theo chiều dọc, số Operation không bị lệch', async ({ page }) => {
  await login(page);
  await routePo(page);
  await page.setViewportSize({ width: 1366, height: 900 });
  await page.goto('/app?page=production-orders&po_id=9');
  await expect(page.locator('.part-block').first()).toBeVisible({ timeout: 20000 });
  const centers = await page.locator('.part-meta').first().evaluate(el =>
    [...el.querySelectorAll('.part-meta-code, .part-meta-drawing, .part-meta-ops')]
      .map(e => { const r = e.getBoundingClientRect(); return Math.round(r.top + r.height / 2); }));
  expect(centers.length).toBe(3);
  const spread = Math.max(...centers) - Math.min(...centers);
  expect(spread, `tâm dọc lệch ${spread}px: ${centers}`).toBeLessThanOrEqual(1);
});

test('Template editor cũng bỏ nhãn "Part 1"', async ({ page }) => {
  await login(page);
  await openTemplateList(page);
  await page.locator('.template-old-card').first().click();
  const card = page.locator('.part-block').first();
  await expect(card).toBeVisible({ timeout: 20000 });
  await expect(card.locator('.part-block-head')).not.toHaveText(/\bPart\s*\d+\b/i);
});
