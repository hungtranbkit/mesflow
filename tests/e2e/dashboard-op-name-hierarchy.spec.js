// Dashboard theo ngày: TÊN Operation là chữ chính, MÃ là chữ phụ.
//
// Cùng quy ước đã chốt ở row-text-hierarchy.spec.js (Tổng quan, Hàng chờ
// sửa), nay áp cho hai tab người trực xưởng mở nhiều nhất:
//
//   A · Tổng quan Operation   -> .op-time-row
//   B · Nhân viên / Session   -> .employee-day-row (khối tổng hợp + chip)
//
// Hình cũ ở cả hai chỗ là MỘT thẻ <b> ghép mã trước tên:
//
//   111-THAN-THUNG-R-01 · CHẤN BƯỚC 1
//   08:22 – Đang chạy · 5p · 111-THAN-THUNG… · Đạt —
//
// Đọc lướt thì gặp một dãy ký tự vô nghĩa trước; ở chip thì tên còn không có
// mặt, chỉ nằm trong title=. Cả hai nay dựng bằng MFUI.opIdentity().
//
// Bài test đo TRỌNG LƯỢNG THỊ GIÁC (cỡ chữ/độ đậm/thứ tự đọc) chứ không so
// chuỗi, nên nó không vỡ khi ai đó đổi cách viết mã; và tự cấp dữ liệu qua
// page.route để có nghĩa cả trên CSDL test trống.
const { test, expect } = require('@playwright/test');

const OP_CODE = '111-THAN-THUNG-R-01';
const OP_NAME = 'CHẤN BƯỚC 1';
// OP thứ hai cố ý THIẾU tên: nhánh fallback phải đẩy mã lên làm chữ chính,
// không được để trống.
const OP2_CODE = '111-THAN-THUNG-R-02';

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

const at = (date, hour, minute = 0) =>
  new Date(`${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00+07:00`).toISOString();

const SHIFTS = [{
  id: 1, code: 'DAY', name: 'Ca ngày', active: true,
  anchor_start: '00:00', anchor_end: '23:59', cross_midnight: false, target_minutes: 480,
  intervals: [
    { interval_type: 'WORK', start_minute: 0, end_minute: 720, sort_order: 0 },
    { interval_type: 'BREAK', start_minute: 720, end_minute: 780, label: 'Nghỉ giữa ca', sort_order: 1 },
    { interval_type: 'WORK', start_minute: 780, end_minute: 1439, sort_order: 2 },
  ],
}];

function payload(date) {
  const opBase = {
    po_id: 1, po_code: 'PO-111', part_id: 11, part_code: '10025-FB-201', part_name: 'Thân thùng rác',
    session_count: 2, open_session_count: 1, day_work_seconds: 5400, planned_work_seconds: 7200,
    planned_quantity: 1000, total_good_qty: 308, day_good_qty: 120, day_defect_qty: 4,
    day_rework_qty: 0, total_defect_qty: 20, total_rework_qty: 0, standard_seconds_per_unit: 7,
    day_state: 'RUNNING', last_started_at: at(date, 8, 22), last_report_at: at(date, 10, 5),
  };
  const items = [
    { ...opBase, operation_id: 101, operation_code: OP_CODE, operation_name: OP_NAME },
    // Thiếu name -- đúng hình dữ liệu xưởng nhập chưa đủ.
    { ...opBase, operation_id: 102, operation_code: OP2_CODE, operation_name: null, day_work_seconds: 3600 },
  ];
  const sessionBase = {
    employee_id: 1, employee_code: 'NV01', employee_name: 'Trần Tấn Đạt',
    po_code: 'PO-111', part_code: '10025-FB-201', good_qty: 12, defect_qty: 0, rework_qty: 0,
  };
  const sessions = [
    { ...sessionBase, session_id: 1, session_status: 'OPEN', started_at: at(date, 8, 22), ended_at: null,
      operation_id: 101, operation_code: OP_CODE, operation_name: OP_NAME },
    { ...sessionBase, session_id: 2, session_status: 'CLOSED', started_at: at(date, 6, 0), ended_at: at(date, 7, 30),
      operation_id: 102, operation_code: OP2_CODE, operation_name: null },
    { ...sessionBase, session_id: 3, employee_id: 2, employee_code: 'NV02', employee_name: 'Lê Văn Bình',
      session_status: 'CLOSED', started_at: at(date, 9, 0), ended_at: at(date, 11, 0),
      operation_id: 101, operation_code: OP_CODE, operation_name: OP_NAME },
  ];
  const activity = [{
    item_type: 'SESSION_STARTED', item_id: '1', activity_at: at(date, 8, 22), actor: 'Trần Tấn Đạt',
    subject: OP_NAME, operation_name: OP_NAME, operation_code: OP_CODE, status: 'STARTED',
    po_code: 'PO-111', good_qty: 0, defect_qty: 0,
  }];
  return { ok: true, items, sessions, activity };
}

async function openDashboard(page, tab, width = 1366) {
  const date = hcmDate();
  await page.setViewportSize({ width, height: 900 });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.route('**/api/settings/work-shifts', r => r.fulfill({ json: { ok: true, items: SHIFTS } }));
  await page.route('**/api/dashboard/day?**', r => r.fulfill({ json: payload(date) }));
  // Tab nằm trong URL (renderDashboard đọc ?tab=), nên không cần bấm -- vào
  // thẳng đúng tab cần đo, kể cả ở 320px nơi tab có thể phải cuộn ngang.
  await page.goto(`/app?page=dashboard&tab=${tab}`);
  await page.waitForTimeout(1500);
  return date;
}

// Khối nhận dạng của cả hai tab, đọc bằng đúng một selector dùng chung.
const BLOCKS = [
  ['overview', '.op-time-row:not(.head) .op-identity', 'Tổng quan Operation'],
  ['people', '.employee-day-summary .op-identity', 'Nhân viên / Session · khối tổng hợp'],
  ['people', '.employee-session-chips .op-identity', 'Nhân viên / Session · chip timeline'],
];

const measure = el => {
  const title = el.querySelector('.row-title');
  const sub = el.querySelector('.row-code') || el.querySelector('.op-identity-meta');
  if (!title || !sub) return null;
  const t = getComputedStyle(title), s = getComputedStyle(sub);
  return {
    titleText: title.textContent.trim(), subText: sub.textContent.trim(),
    titleSize: parseFloat(t.fontSize), subSize: parseFloat(s.fontSize),
    titleWeight: +t.fontWeight, subWeight: +s.fontWeight,
    titleTop: title.getBoundingClientRect().top, subTop: sub.getBoundingClientRect().top,
  };
};

for (const [tab, selector, label] of BLOCKS) {
  for (const width of [1920, 1366, 390]) {
    test(`${label} @ ${width}px: tên là chữ chính, chữ phụ nhẹ hơn`, async ({ page }) => {
      await openDashboard(page, tab, width);
      const block = page.locator(selector).first();
      await expect(block).toBeVisible({ timeout: 15000 });
      const g = await block.evaluate(measure);
      expect(g, `${label}: không có .row-title + dòng phụ`).not.toBeNull();
      expect(g.titleSize, `tên ${g.titleSize}px vs chữ phụ ${g.subSize}px`).toBeGreaterThan(g.subSize);
      expect(g.titleWeight).toBeGreaterThanOrEqual(g.subWeight);
      expect(g.titleTop, 'tên phải đứng TRƯỚC chữ phụ theo chiều đọc').toBeLessThanOrEqual(g.subTop);
      expect(g.titleText.length, 'tên công đoạn rỗng').toBeGreaterThan(0);
    });
  }
}

test('tên OP thật nằm trên bề mặt, không chỉ trong title=', async ({ page }) => {
  await openDashboard(page, 'overview');
  const first = page.locator('.op-time-row:not(.head)').first();
  await expect(first.locator('.row-title')).toHaveText(OP_NAME);
  await expect(first.locator('.row-code')).toHaveText(OP_CODE);

  await openDashboard(page, 'people');
  // Chip timeline: TÊN hiện ra, phần metadata giữ giờ/trạng thái/thời lượng/
  // sản lượng -- và KHÔNG lặp lại mã dài trên cùng một dòng chật.
  //
  // Chip được xếp theo started_at, nên chip ĐẦU TIÊN của nhân viên này là
  // session 06:00 chạy trên OP cố ý thiếu tên (nhánh fallback, có bài riêng
  // bên dưới). Chốt đúng chip của session đang chạy 08:22 -- OP có tên thật.
  const chip = page.locator('.employee-session-chips .op-identity.open').first();
  await expect(chip.locator('.row-title')).toHaveText(OP_NAME);
  await expect(chip.locator('.op-identity-meta')).toContainText('Đang chạy');
  expect(await chip.innerText()).not.toContain(OP_CODE);
  // Mã vẫn đối chiếu được: title= của chip mang bản đầy đủ.
  expect(await chip.getAttribute('title')).toContain(OP_CODE);
});

test('thiếu operation_name thì mã lên làm chữ chính, không để trống', async ({ page }) => {
  await openDashboard(page, 'overview');
  // Hàng thứ hai trong payload cố ý có operation_name=null.
  const fallbackRow = page.locator('.op-time-row:not(.head)', { hasText: OP2_CODE }).first();
  await expect(fallbackRow).toBeVisible({ timeout: 15000 });
  const shape = await fallbackRow.locator('.op-identity').first().evaluate(el => ({
    title: el.querySelector('.row-title')?.textContent.trim() ?? null,
    codeLines: el.querySelectorAll('.row-code').length,
  }));
  expect(shape.title, 'fallback để tên rỗng').toBe(OP2_CODE);
  // Mã đã lên làm chữ chính thì không in lại ở dòng dưới -- lặp chính nó chỉ
  // tốn chiều cao mà không thêm thông tin.
  expect(shape.codeLines, 'mã bị lặp hai lần khi thiếu tên').toBe(0);
});

test('không còn thẻ tiêu đề nào lấy mã OP làm chữ chính', async ({ page }) => {
  // Chốt đúng hình dạng cũ để nó không quay lại: một thẻ chữ-chính mở đầu
  // bằng mã rồi mới tới tên.
  for (const tab of ['overview', 'people']) {
    await openDashboard(page, tab);
    const offenders = await page.evaluate(() => {
      const pane = document.querySelector('.dashboard-tab-pane.active');
      if (!pane) return ['không thấy pane đang mở'];
      return [...pane.querySelectorAll('b, strong')]
        .map(el => el.textContent.trim())
        .filter(text => /^[A-Z0-9][A-Z0-9-]{5,}\s+·\s+\S/.test(text));
    });
    expect(offenders, `tab ${tab}: mã OP lại làm chữ chính`).toEqual([]);
  }
});

for (const width of [390, 320]) {
  test(`không tràn ngang tại ${width}px trên cả hai tab`, async ({ page }) => {
    for (const tab of ['overview', 'people']) {
      await openDashboard(page, tab, width);
      await expect(page.locator('.dashboard-tab-pane.active')).toBeVisible();
      const overflow = await page.evaluate(() => ({
        body: document.body.scrollWidth > document.body.clientWidth,
        doc: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }));
      expect(overflow, `tab ${tab} @ ${width}px tràn ngang`).toEqual({ body: false, doc: false });
      await page.screenshot({ path: `test-results/dashboard-op-name-${tab}-${width}.png`, fullPage: true });
    }
  });
}
