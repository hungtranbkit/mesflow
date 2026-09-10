// Trong hàng nghiệp vụ, TÊN tiếng Việt là chữ chính, MÃ là chữ phụ.
//
// Quy ước đã chốt từ đợt QR/Operation list: người vận hành tìm việc theo tên
// công đoạn, không theo mã. Mã chỉ dùng để đối chiếu SAU khi đã tìm thấy.
//
// Audit 2026-09-10 đo thấy hai màn vẫn ghép cả hai vào MỘT thẻ <b>, mã đứng
// trước:
//
//     111-THAN-THUNG-R-01 · CẮT PHÔI CHO THÂN THÙNG RÁC
//
// Đọc lướt thì thấy một dãy ký tự vô nghĩa trước, tên thật bị đẩy ra sau và
// thường bị cắt ở cột hẹp. Cả hai màn nay tách thành .row-title (tên) và
// .row-code (mã).
//
// Bài test đo TRỌNG LƯỢNG THỊ GIÁC chứ không đọc chuỗi: chữ chính phải to hơn
// hoặc đậm hơn chữ phụ. Đó mới là thứ mắt người thật sự dùng để phân cấp, và
// nó không vỡ khi ai đó đổi cách viết mã.
const { test, expect } = require('@playwright/test');

// Dữ liệu giả lập: bài test phải có nghĩa trên môi trường CI sạch, không phụ
// thuộc việc TEST tình cờ có PO nào đang chờ sửa hay không. Mã cố ý dài và
// khác hẳn tên, đúng hình đã gây ra vấn đề.
const OP_CODE = '111-THAN-THUNG-R-01';
const OP_NAME = 'CẮT PHÔI CHO THÂN THÙNG RÁC';

async function mockOverview(page) {
  const EMPTY = { production_orders: [], operations: [] };
  await page.route(/\/api\/dashboard\/overview/, r => r.fulfill({ json: {
    ok: true,
    production_orders: [{
      po_id: 1, po_code: '111', product: 'Thùng rác', status: 'IN_PROGRESS',
      planned_quantity: 1000, good_quantity: 308, defect_quantity: 20, scrap_quantity: 0,
      remaining_quantity: 692, progress_percent: 30.8, repair_pending_quantity: 0,
      repair_unconfigured_operation_count: 0, estimated_repair_work_seconds: 0,
      due_date: '2026-09-30', control_state: 'ON_TRACK',
    }],
    operations: [{
      po_id: 1, po_code: '111', part_id: 11, part_code: '10025-FB-201', part_name: 'Thân thùng rác',
      operation_id: 101, operation_code: OP_CODE, operation_name: OP_NAME, operation_sort: 0,
      progress_percent: 30.8, done_qty: 308, defect_qty: 20, repair_pending_quantity: 0,
      estimated_repair_work_seconds: 0, control_state: 'ON_TRACK',
    }],
    summary: { unconfirmed_quantity_sessions: 0 },
  } }));
  await page.route(/\/api\/production-control/, r => r.fulfill({ json: { ok: true, ...EMPTY } }));
}

async function mockReworkQueue(page) {
  await page.route(/\/api\/rework\/queue/, r => r.fulfill({ json: { ok: true, items: [{
    source_session_id: 9001, operation_id: 101, operation_code: OP_CODE, operation_name: OP_NAME,
    po_code: '111', part_code: '10025-FB-201', part_name: 'Thân thùng rác',
    employee_name: 'Trần Tấn Đạt', employee_code: 'NV01',
    ended_at: '2026-09-02T06:40:47Z', defect_qty: 8, rework_qty: 0, scrap_qty: 0, pending_qty: 8,
    repair_cycle_time_seconds_per_unit: 0,
  }] } }));
  await page.route(/\/api\/employees/, r => r.fulfill({ json: { ok: true, items: [
    { id: 1, employee_no: 'NV01', name: 'Trần Tấn Đạt', active: true }] } }));
}

const MOCKS = { overview: mockOverview, 'rework-queue': mockReworkQueue };

const SCREENS = [
  ['overview', '.overview-op-row'],
  ['rework-queue', '.rq-row:not(.head)'],
];

async function open(page, key, width = 1366) {
  await page.setViewportSize({ width, height: 900 });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await MOCKS[key](page);
  await page.goto(`/app?page=${key}`);
  await page.waitForTimeout(1200);
}

for (const [key, rowSelector] of SCREENS) {
  for (const width of [1366, 390]) {
    test(`${key} @ ${width}px: tên là chữ chính, mã là chữ phụ`, async ({ page }) => {
      await open(page, key, width);
      const row = page.locator(rowSelector).first();
      await expect(row).toBeVisible({ timeout: 15000 });
      const g = await row.evaluate(el => {
        const title = el.querySelector('.row-title');
        const code = el.querySelector('.row-code');
        if (!title || !code) return null;
        const t = getComputedStyle(title), c = getComputedStyle(code);
        return {
          titleText: title.textContent.trim(),
          codeText: code.textContent.trim(),
          titleSize: parseFloat(t.fontSize), codeSize: parseFloat(c.fontSize),
          titleWeight: +t.fontWeight, codeWeight: +c.fontWeight,
          titleTop: title.getBoundingClientRect().top,
          codeTop: code.getBoundingClientRect().top,
        };
      });
      expect(g, `${key}: hàng không có .row-title/.row-code`).not.toBeNull();

      expect(g.titleSize, `tên ${g.titleSize}px vs mã ${g.codeSize}px`)
        .toBeGreaterThan(g.codeSize);
      expect(g.titleWeight).toBeGreaterThanOrEqual(g.codeWeight);
      // Tên đứng TRƯỚC mã theo chiều đọc.
      expect(g.titleTop).toBeLessThanOrEqual(g.codeTop);
      // Và tên không được rỗng -- tách ra mà bỏ quên nội dung thì tệ hơn cũ.
      expect(g.titleText.length, 'tên công đoạn rỗng').toBeGreaterThan(0);
    });
  }
}

test('mã không còn bị nhét chung vào thẻ tên', async ({ page }) => {
  // Chốt đúng hình dạng cũ để nó không quay lại: một <b> chứa cả mã lẫn tên,
  // ngăn bằng dấu chấm giữa.
  for (const [key, rowSelector] of SCREENS) {
    await open(page, key);
    const row = page.locator(rowSelector).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    const merged = await row.evaluate(el => {
      const title = el.querySelector('.row-title');
      if (!title) return true;
      const text = title.textContent.trim();
      // Dạng cũ luôn có " · " giữa mã và tên trong CÙNG một thẻ.
      return / · /.test(text) && /^[A-Z0-9-]{6,}/.test(text);
    });
    expect(merged, `${key}: mã và tên lại bị ghép vào một thẻ`).toBe(false);
  }
});

test('cùng một primitive thì cùng một cỡ chữ ở mọi màn', async ({ page }) => {
  // Bẫy đã sập một lần ngay trong chính đợt này: .overview-op-row small đặt
  // 10px với độ ưu tiên (0,1,1), cao hơn .row-code (0,1,0). Cùng một class
  // ra 11px ở Hàng chờ sửa và 10px ở Tổng quan -- đúng thứ lệch âm thầm mà
  // primitive dùng chung sinh ra để dẹp, và không bài test nào so title/code
  // trong CÙNG một màn nhìn thấy được.
  const seen = {};
  for (const [key, rowSelector] of SCREENS) {
    await open(page, key);
    const row = page.locator(rowSelector).first();
    await expect(row).toBeVisible({ timeout: 15000 });
    seen[key] = await row.evaluate(el => {
      const cs = n => getComputedStyle(el.querySelector(n));
      return {
        code: parseFloat(cs('.row-code').fontSize),
        title: parseFloat(cs('.row-title').fontSize),
        codeWeight: +cs('.row-code').fontWeight,
        titleWeight: +cs('.row-title').fontWeight,
      };
    });
  }
  const keys = Object.keys(seen);
  expect(JSON.stringify(seen[keys[0]]), `lệch giữa các màn: ${JSON.stringify(seen)}`)
    .toBe(JSON.stringify(seen[keys[1]]));
});
