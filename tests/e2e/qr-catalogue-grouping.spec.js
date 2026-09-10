// Danh sách QR: tên công việc là thông tin chính, gom theo PO → Part.
//
// Trước 2026-09-09 màn này là một lưới phẳng hàng trăm thẻ, mỗi thẻ mở đầu
// bằng MÃ ở cỡ chữ lớn nhất còn tên tiếng Việt là dòng phụ — muốn tìm "Chấn
// mép" phải quét mã của cả danh sách. Spec này khoá lại hành vi mới.
//
// Dữ liệu được mock ở tầng /api/qr-labels: thứ đang kiểm là logic gom nhóm và
// sắp xếp trong qr-print.js. Hợp đồng của chính API đó được kiểm riêng, bằng
// dữ liệu thật, ở tests/integration/test_qr_catalogue_grouping.py.
const { test, expect } = require('@playwright/test');
const { openFilters } = require('./helpers/filters');

test.beforeEach(async ({ page }) => {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  // /login khi đã có phiên tự chuyển sang /app; goto ngay sau đó bị chính nó
  // cắt ngang, và với các bài dùng goBack() thì lịch sử duyệt còn bị hỏng
  // theo. Đợi chuyển hướng tự động xong ngay trong helper đăng nhập.
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
});

const OPERATIONS = [
  // sort_order dựng ngược với thứ tự mã: sắp theo mã sẽ ra sai trình tự.
  { id: 1, qr_type: 'OPERATION', code: 'THAN-OP10', name: 'Cắt phôi', qr_payload: 'WF|OP|THAN-OP10',
    group_name: 'PO-777', part_code: 'THAN', part_name: 'Thân thùng', part_sort: 0,
    operation_sort: 0, operation_type: 'PRODUCTION', detail: 'THAN · Thân thùng', active: true },
  { id: 2, qr_type: 'OPERATION', code: 'THAN-OP2', name: 'Chấn mép', qr_payload: 'WF|OP|THAN-OP2',
    group_name: 'PO-777', part_code: 'THAN', part_name: 'Thân thùng', part_sort: 0,
    operation_sort: 1, operation_type: 'PRODUCTION', detail: 'THAN · Thân thùng', active: true },
  { id: 3, qr_type: 'OPERATION', code: 'THAN-OP2-SU', name: 'Setup máy chấn', qr_payload: 'WF|OPID|3',
    group_name: 'PO-777', part_code: 'THAN', part_name: 'Thân thùng', part_sort: 0,
    operation_sort: 2147483646, operation_type: 'SETUP', parent_operation_id: 2,
    parent_name: 'Chấn mép', detail: 'THAN · Thân thùng · Setup máy', active: true },
  { id: 4, qr_type: 'OPERATION', code: 'NAP-OP1', name: 'Dập nắp', qr_payload: 'WF|OP|NAP-OP1',
    group_name: 'PO-777', part_code: 'NAP', part_name: 'Nắp thùng', part_sort: 1,
    operation_sort: 0, operation_type: 'PRODUCTION', detail: 'NAP · Nắp thùng', active: true },
];

async function openCatalogue(page, rows = OPERATIONS) {
  await page.route(/\/api\/qr-labels/, route => {
    const q = decodeURIComponent(new URL(route.request().url()).searchParams.get('q') || '').toLowerCase();
    const strip = s => String(s || '').toLowerCase();
    const items = !q ? rows : rows.filter(x =>
      strip(x.name).includes(q) || strip(x.code).includes(q) ||
      strip(x.part_code).includes(q) || strip(x.part_name).includes(q));
    return route.fulfill({ json: { ok: true, items, type: 'OPERATION' } });
  });
  await page.route(/\/api\/qr-image/, route =>
    route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"></svg>' }));
  await page.goto('/app?page=qr-print');
  // Bộ lọc gập mặc định ở <=700px (MFUI.filterBar), và #qrType nằm trong đó.
  // Helper tự bỏ qua khi màn rộng, nên gọi vô điều kiện là an toàn.
  await openFilters(page);
  await page.locator('#qrType').selectOption('OPERATION');
  await expect(page.locator('.qr-catalog-card').first()).toBeVisible({ timeout: 15000 });
}

test('tên công việc là dòng chính, mã chỉ là dòng phụ', async ({ page }) => {
  await openCatalogue(page);
  const card = page.locator('.qr-catalog-card').first();
  await expect(card.locator('.qr-item-name')).toHaveText('Cắt phôi');
  await expect(card.locator('.qr-item-code')).toHaveText('THAN-OP10');

  // Tên phải to hơn mã — đây là toàn bộ mục đích của thay đổi.
  const nameSize = await card.locator('.qr-item-name').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
  const codeSize = await card.locator('.qr-item-code').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
  expect(nameSize).toBeGreaterThan(codeSize);

  // Payload dài không chiếm chỗ trên thẻ; phải bấm mới xem.
  await expect(card).not.toContainText('WF|OP|');
});

test('gom theo Part và sắp theo trình tự công nghệ, không theo mã', async ({ page }) => {
  await openCatalogue(page);
  const heads = await page.locator('.qr-part-head span').allTextContents();
  expect(heads).toEqual(['THAN · Thân thùng', 'NAP · Nắp thùng']);

  const firstGroup = page.locator('.qr-part-group').first();
  const names = await firstGroup.locator('> .qr-catalog-grid .qr-item-name').allTextContents();
  // Theo mã sẽ là OP10, OP2 -> "Cắt phôi","Chấn mép" trùng hợp đúng; nhưng
  // theo trình tự thì Cắt phôi (0) phải đứng trước Chấn mép (1) bất kể mã.
  expect(names).toEqual(['Cắt phôi', 'Chấn mép']);
});

test('OP phụ nằm trong mục riêng của đúng Part, không trộn ngang hàng', async ({ page }) => {
  await openCatalogue(page);
  const firstGroup = page.locator('.qr-part-group').first();
  // Không nằm trong lưới OP sản xuất...
  await expect(firstGroup.locator('> .qr-catalog-grid .qr-item-name'))
    .toHaveText(['Cắt phôi', 'Chấn mép']);
  // ...mà trong mục "OP phụ · Setup", mặc định mở.
  const support = firstGroup.locator('.qr-support-group');
  await expect(support).toHaveCount(1);
  await expect(support).toHaveAttribute('open', '');
  // Đọc ra ngay là setup của việc nào, không phải đoán qua hậu tố '-SU'.
  await expect(support.locator('.qr-item-name')).toHaveText('Setup · Chấn mép');
  await expect(support.locator('.qr-item-code')).toHaveText('THAN-OP2-SU');
  await expect(support.locator('.qr-item-badge')).toHaveText('Setup máy');
});

test('tìm theo tên tiếng Việt và theo tên Part', async ({ page }) => {
  await openCatalogue(page);
  await page.locator('#qrSearch').fill('chấn');
  await expect(page.locator('.qr-catalog-card')).toHaveCount(2, { timeout: 10000 }); // Chấn mép + setup của nó
  await expect(page.locator('.qr-item-name').first()).toHaveText('Chấn mép');

  await page.locator('#qrSearch').fill('nắp');
  await expect(page.locator('.qr-catalog-card')).toHaveCount(1, { timeout: 10000 });
  await expect(page.locator('.qr-item-name')).toHaveText('Dập nắp');
  await expect(page.locator('.qr-part-head span')).toHaveText('NAP · Nắp thùng');
});

test('xem QR mới hiện payload, và mã dài không làm vỡ layout', async ({ page }) => {
  const longCode = 'PO-10025-FB-304-111-CHOT-PIN-BAN-01-PHAY-MAT-CHUAN-XYZ';
  await openCatalogue(page, [{ ...OPERATIONS[0], code: longCode, name: 'Phay mặt chuẩn' }]);
  const card = page.locator('.qr-catalog-card').first();
  await expect(card.locator('.qr-item-code')).toHaveText(longCode);
  // Mã dài phải ellipsis trong thẻ, không đẩy trang trượt ngang.
  const overflow = await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await card.locator('[data-show-payload]').click();
  await expect(page.locator('.qr-detail code')).toContainText('WF|OP|');
});

for (const [label, width, height] of [['1920', 1920, 1080], ['1366', 1366, 768], ['mobile', 390, 844]]) {
  test(`không tràn ngang tại ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openCatalogue(page);
    const overflow = await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth);
    expect(overflow, `body tràn ngang ${overflow}px tại ${label}`).toBeLessThanOrEqual(1);
    await expect(page.locator('.qr-part-head').first()).toBeVisible();
  });
}

test('bấm vào cả thẻ là chọn, và nút trong thẻ không làm chọn nhầm', async ({ page }) => {
  await openCatalogue(page);
  const card = page.locator('.qr-catalog-card').first();
  // Không còn ô tick nhỏ ở góc.
  expect(await page.locator('.qr-item-check').count()).toBe(0);

  // Bấm vào phần nội dung của thẻ (tên việc) — vùng lớn nhất và tự nhiên nhất.
  await card.locator('.qr-item-name').click();
  await expect(card).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#qrSummary')).toContainText('Đã chọn 1 tem');

  await card.locator('.qr-item-name').click();
  await expect(card).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#qrSummary')).toContainText('Đã chọn 0 tem');

  // "Xem QR" mở chi tiết chứ không chọn thẻ.
  await card.locator('[data-show-payload]').click();
  await expect(page.locator('.qr-detail')).toBeVisible();
  await expect(card).toHaveAttribute('aria-pressed', 'false');
  await expect(page.locator('#qrSummary')).toContainText('Đã chọn 0 tem');
});

test('chọn được bằng bàn phím', async ({ page }) => {
  await openCatalogue(page);
  const card = page.locator('.qr-catalog-card').first();
  await card.focus();
  await page.keyboard.press('Enter');
  await expect(card).toHaveAttribute('aria-pressed', 'true');
  await page.keyboard.press(' ');
  await expect(card).toHaveAttribute('aria-pressed', 'false');
});
