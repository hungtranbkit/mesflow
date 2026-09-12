// Xem trước khi nhập Excel: checkbox OP Setup và nút xuất file trên màn PO.
//
// Hai thứ được khoá ở đây chỉ thấy được trên trình duyệt thật:
//
//   1. OP nào có 'Thời gian setup > 0' thì hàng OP SETUP phải HIỆN và được
//      TICK SẴN -- người dùng không phải đi bật từng cái. Bỏ tick OP cha thì ô
//      setup vừa tắt vừa KHOÁ, nên không có đường nào bấm ra một setup mồ côi.
//      Tick lại cha thì setup quay về mặc định, TRỪ KHI người dùng đã tự tay
//      đổi nó -- lúc đó ý muốn của họ thắng.
//
//   2. Màn chi tiết PO phải có nút xuất file rõ ràng, không giấu trong menu, và
//      bấm vào phải tải ĐÚNG PO đang mở.
const { test, expect } = require('@playwright/test');

const TEMPLATE_ID = 77;

// Đúng hình dạng /api/templates/preview-workbook trả về.
const PREVIEW = {
  ok: true,
  filename: 'Lộ trình sản xuất NEWARK.xlsx',
  template: { code: 'TPL-6126', name: 'Lộ trình sản xuất NEWARK', product: 'NEWARK', version: '1.0' },
  po: '6126', qty: 110,
  warnings: ["Sheet 'Thanh la khung ngồi' dòng 32: Part này đã có Operation số 02, nên block 'LÀM NGUỘI' được nhập với mã KM-317-OP02-2 để hai Operation không dùng chung một danh tính."],
  counts: { parts: 2, operations: 3, setups: 2 },
  parts: [
    { code: 'KM-001', name: 'Chân ghế A - Trái', sort_order: 0, operations: [
      { code: 'KM-001-OP01', name: 'CẮT LASER', sort_order: 0, standard_seconds_per_unit: 100,
        setup_declared: true, requires_setup: true, expected_setup_minutes: 20,
        setup_code: 'KM-001-OP01-SU', setup_name: 'Setup CẮT LASER',
        sheet: 'Chân ghế A - Trái', row: 8 },
      { code: 'KM-001-OP02', name: 'LÀM NGUỘI', sort_order: 1, standard_seconds_per_unit: 50,
        setup_declared: true, requires_setup: false, expected_setup_minutes: null,
        setup_code: null, setup_name: null, sheet: 'Chân ghế A - Trái', row: 20 },
    ] },
    { code: 'KM-002', name: 'HÀN ROBOT - Hàn vòng đệm', sort_order: 1, operations: [
      { code: 'KM-002-OP01', name: 'HÀN ROBOT', sort_order: 0, standard_seconds_per_unit: 120,
        setup_declared: true, requires_setup: true, expected_setup_minutes: 120,
        setup_code: 'KM-002-OP01-SU', setup_name: 'Setup HÀN ROBOT',
        sheet: 'HÀN ROBOT - Hàn vòng đệm', row: 8 },
    ] },
  ],
};

async function openTemplatesPage(page, state) {
  await page.route(/\/api\/templates\/preview-workbook/, route =>
    route.fulfill({ json: PREVIEW }));
  await page.route(/\/api\/templates\/import-workbook/, async route => {
    const body = route.request().postData() || '';
    // Lấy lại phần selection từ multipart để kiểm đúng cái UI đã gửi đi.
    const match = /name="selection"\r?\n\r?\n([\s\S]*?)\r?\n--/.exec(body);
    state.selection = match ? JSON.parse(match[1]) : null;
    return route.fulfill({ json: { ok: true, template_id: TEMPLATE_ID,
      message: 'Đã tạo Template TPL-6126: 2 Part, 3 Operation, 2 OP Setup.',
      part_count: 2, operation_count: 3, setup_count: 2, warnings: [], dropped_setups: [] } });
  });
  await page.route(/\/api\/templates(\?|$)/, route =>
    route.fulfill({ json: { ok: true, items: [] } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=templates');
  // "Nhập từ Excel" nằm trong <details class="template-tools"> đang đóng.
  await page.locator('.template-tools > summary').click();
  await expect(page.locator('#tplImport')).toBeVisible({ timeout: 20000 });
}

// Đẩy một file .xlsx giả vào input; nội dung không quan trọng vì preview đã mock.
async function chooseFile(page) {
  await page.setInputFiles('#tplImportFile', {
    name: 'Lộ trình sản xuất NEWARK.xlsx',
    mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    buffer: Buffer.from('PK fake'),
  });
  await expect(page.locator('.tpl-preview')).toBeVisible({ timeout: 20000 });
}

const opRow = (page, code) => page.locator(`.tpl-preview-op[data-key$="|${code}"]`);
const opBox = (page, code) => opRow(page, code).locator('.tpl-pv-op');
const setupBox = (page, code) => opRow(page, code).locator('.tpl-pv-setup');

test.describe('Xem trước nhập Excel', () => {
  test('OP có setup > 0 thì hàng Setup hiện và được tick sẵn', async ({ page }) => {
    await openTemplatesPage(page, {});
    await chooseFile(page);

    // OP sản xuất: mặc định tick, như hành vi cũ.
    await expect(opBox(page, 'KM-001-OP01')).toBeChecked();
    await expect(opBox(page, 'KM-001-OP02')).toBeChecked();

    // Có setup -> hàng setup tồn tại và ĐÃ tick sẵn.
    await expect(setupBox(page, 'KM-001-OP01')).toBeChecked();
    await expect(setupBox(page, 'KM-002-OP01')).toBeChecked();
    await expect(opRow(page, 'KM-001-OP01')).toContainText('Tạo OP Setup');
    await expect(opRow(page, 'KM-001-OP01')).toContainText('Thời gian setup: 20 phút');
    await expect(opRow(page, 'KM-002-OP01')).toContainText('Thời gian setup: 120 phút');

    // Không có setup -> KHÔNG được đẻ ra hàng setup nào.
    await expect(setupBox(page, 'KM-001-OP02')).toHaveCount(0);

    // Tên là dòng chính, mã là dòng phụ.
    await expect(opRow(page, 'KM-001-OP01').locator('.tpl-preview-main b').first())
      .toHaveText('CẮT LASER');
    await expect(opRow(page, 'KM-001-OP01')).toContainText('KM-001-OP01');
  });

  test('cảnh báo trùng mã Operation hiện lên chứ không bị nuốt', async ({ page }) => {
    await openTemplatesPage(page, {});
    await chooseFile(page);
    await expect(page.locator('.tpl-preview-warn')).toBeVisible();
    await expect(page.locator('.tpl-preview-warn')).toContainText('KM-317-OP02-2');
  });

  test('bỏ tick OP cha thì ô Setup tắt và khoá lại', async ({ page }) => {
    await openTemplatesPage(page, {});
    await chooseFile(page);

    await opBox(page, 'KM-001-OP01').uncheck();
    await expect(setupBox(page, 'KM-001-OP01')).not.toBeChecked();
    await expect(setupBox(page, 'KM-001-OP01')).toBeDisabled();
    await expect(opRow(page, 'KM-001-OP01')).toHaveClass(/is-off/);

    // Tick lại cha -> setup trở về mặc định (đang tick) vì người dùng chưa đổi nó.
    await opBox(page, 'KM-001-OP01').check();
    await expect(setupBox(page, 'KM-001-OP01')).toBeEnabled();
    await expect(setupBox(page, 'KM-001-OP01')).toBeChecked();
  });

  test('người dùng tự bỏ tick Setup thì tick lại cha không bật lại hộ', async ({ page }) => {
    await openTemplatesPage(page, {});
    await chooseFile(page);

    await setupBox(page, 'KM-001-OP01').uncheck();     // ý muốn rõ ràng
    await opBox(page, 'KM-001-OP01').uncheck();
    await opBox(page, 'KM-001-OP01').check();
    await expect(setupBox(page, 'KM-001-OP01')).not.toBeChecked();
  });

  test('selection gửi lên đúng những gì đang tick', async ({ page }) => {
    const state = {};
    await openTemplatesPage(page, state);
    await chooseFile(page);

    await setupBox(page, 'KM-002-OP01').uncheck();   // giữ OP, bỏ setup
    await opBox(page, 'KM-001-OP02').uncheck();      // bỏ hẳn một OP
    await page.locator('#tplPvConfirm').click();
    await expect(page.locator('.tpl-preview')).toHaveCount(0, { timeout: 20000 });

    const sent = Object.fromEntries((state.selection || []).map(x => [x.operation_code, x]));
    expect(Object.keys(sent).sort()).toEqual(['KM-001-OP01', 'KM-002-OP01']);
    expect(sent['KM-001-OP01'].include_setup).toBe(true);
    expect(sent['KM-002-OP01'].include_setup).toBe(false);
    expect(sent['KM-001-OP01'].part_code).toBe('KM-001');
  });

  test('bỏ tick hết thì không cho nhập', async ({ page }) => {
    await openTemplatesPage(page, {});
    await chooseFile(page);
    await page.locator('#tplPvAll').uncheck();
    await expect(page.locator('#tplPvConfirm')).toBeDisabled();
  });
});

// --- nút xuất file trên màn chi tiết PO ----------------------------------

const PO = {
  id: 4242, code: 'QA-PO-ROUTER', product: 'NEWARK', status: 'IN_PROGRESS',
  planned_quantity: 110, priority: 'NORMAL', notes: '',
};

async function openPoDetail(page, state) {
  await page.route(/\/api\/production-orders\/4242\/router\.xlsx/, route => {
    state.exportedPoId = 4242;
    return route.fulfill({
      status: 200,
      headers: { 'X-MESFlow-Router-Labels': '5',
                 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
      body: Buffer.from('PK xlsx'),
    });
  });
  // Bất kỳ PO nào KHÁC bị gọi tới đều là lỗi "xuất nhầm PO".
  await page.route(/\/api\/production-orders\/(?!4242)\d+\/router\.xlsx/, route => {
    state.wrongPo = route.request().url();
    return route.fulfill({ status: 500, json: { ok: false, message: 'sai PO' } });
  });
  // Màn chi tiết PO nạp bốn nguồn; thiếu cái nào là màn không dựng xong.
  await page.route(/\/api\/production-orders\/4242(\?|$)/, route =>
    route.fulfill({ json: { ok: true, item: PO, ...PO } }));
  await page.route(/\/api\/parts\?production_order_id=4242/, route =>
    route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/operations\?production_order_id=4242/, route =>
    route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/equipment/, route =>
    route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-control/, route =>
    route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/production-orders(\?|$)/, route =>
    route.fulfill({ json: { ok: true, items: [PO] } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=production-orders&po_id=4242');
  await expect(page.locator('#poExportRouter')).toBeVisible({ timeout: 20000 });
}

test.describe('Nút xuất Excel + QR trên màn PO', () => {
  test('nút nằm ngay trên thanh thao tác, không giấu trong menu', async ({ page }) => {
    await openPoDetail(page, {});
    const button = page.locator('#poExportRouter');
    await expect(button).toBeVisible();
    await expect(button).toHaveText(/Xuất Excel \+ QR/);
    // Phải là con trực tiếp của thanh thao tác PO, không nằm trong <details>.
    await expect(page.locator('.po-detail-actions > #poExportRouter')).toHaveCount(1);
    await expect(page.locator('details #poExportRouter')).toHaveCount(0);
  });

  test('bấm thì tải đúng PO đang mở', async ({ page }) => {
    const state = {};
    await openPoDetail(page, state);
    const download = page.waitForEvent('download').catch(() => null);
    await page.locator('#poExportRouter').click();
    await download;
    expect(state.exportedPoId).toBe(4242);
    expect(state.wrongPo).toBeUndefined();
  });
});
