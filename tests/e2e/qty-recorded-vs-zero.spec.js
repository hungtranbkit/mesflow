// "Chưa nhập sản lượng" KHÁC "đã chốt và bằng 0".
//
// good_qty/defect_qty trong CSDL là NOT NULL DEFAULT 0 (migration 0003), nên
// một session vừa mở và một session người thật chốt đúng 0/0 mang y hệt con
// số. Tầng hiển thị trước đây in cả hai thành "Đạt 0 · NG 0": quản đốc đọc
// "NG 0" của ca đang chạy thành "đã kiểm, không có hàng lỗi".
//
// Ba trạng thái phải phân biệt được:
//   (1) chưa nhập        -> "Đạt — · NG —"
//   (2) đã chốt bằng 0   -> "Đạt 0 · NG 0"
//   (3) đã chốt, > 0     -> số thật
//
// Nguồn sự thật là output_recorded / recorded_session_count do API trả về
// (xem daily_sessions()/daily_progress()), KHÔNG phải bản thân con số.
const { test, expect } = require('@playwright/test');

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());
const at = (date, h, m = 0) =>
  new Date(`${date}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+07:00`).toISOString();

const SHIFTS = [{
  id: 1, code: 'DAY', name: 'Ca ngày', active: true, anchor_start: '00:00', anchor_end: '23:59',
  cross_midnight: false, target_minutes: 480,
  intervals: [{ interval_type: 'WORK', start_minute: 0, end_minute: 1439, sort_order: 0 }],
}];

// Bốn nhân viên, mỗi người đúng một session -- để mỗi hàng timeline nói về
// đúng một trạng thái, không phải tổng của nhiều trạng thái trộn lẫn.
function payload(date) {
  const base = { po_code: 'PO-111', part_code: 'PART-1', operation_id: 101,
    operation_code: 'OP-A-01', operation_name: 'CHẤN BƯỚC 1', rework_qty: 0, scrap_qty: 0 };
  const sessions = [
    // (1) đang chạy, chưa ai nhập gì
    { ...base, session_id: 1, employee_id: 1, employee_code: 'NV01', employee_name: 'An Chưa Nhập',
      session_status: 'OPEN', started_at: at(date, 8), ended_at: null,
      good_qty: 0, defect_qty: 0, quantity_confirmed: true, closed_by_system: false, output_recorded: false },
    // (2) đã kết thúc, người thật xác nhận đúng 0/0
    { ...base, session_id: 2, employee_id: 2, employee_code: 'NV02', employee_name: 'Bình Chốt Không',
      session_status: 'CLOSED', started_at: at(date, 6), ended_at: at(date, 7),
      good_qty: 0, defect_qty: 0, quantity_confirmed: true, closed_by_system: false, output_recorded: true },
    // (3) đã kết thúc, có số thật
    { ...base, session_id: 3, employee_id: 3, employee_code: 'NV03', employee_name: 'Cường Ba Hai',
      session_status: 'CLOSED', started_at: at(date, 9), ended_at: at(date, 11),
      good_qty: 32, defect_qty: 2, quantity_confirmed: true, closed_by_system: false, output_recorded: true },
    // (4) máy tự đóng cuối ca, chưa ai xác nhận số liệu
    { ...base, session_id: 4, employee_id: 4, employee_code: 'NV04', employee_name: 'Dũng Tự Đóng',
      session_status: 'CLOSED', started_at: at(date, 13), ended_at: at(date, 17),
      good_qty: 0, defect_qty: 0, quantity_confirmed: false, closed_by_system: true, output_recorded: false },
  ];
  const opBase = { po_id: 1, po_code: 'PO-111', part_id: 11, part_code: 'PART-1', part_name: 'Thân thùng',
    session_count: 1, open_session_count: 0, day_work_seconds: 3600, planned_work_seconds: 7200,
    planned_quantity: 1000, total_good_qty: 0, total_defect_qty: 0, total_rework_qty: 0,
    day_rework_qty: 0, day_scrap_qty: 0, standard_seconds_per_unit: 7, day_state: 'UPDATED',
    last_started_at: at(date, 8), last_report_at: at(date, 9) };
  const items = [
    // OP chưa session nào chốt số -> tổng 0 là "chưa có số", không phải "làm ra 0"
    { ...opBase, operation_id: 101, operation_code: 'OP-A-01', operation_name: 'CHẤN BƯỚC 1',
      day_good_qty: 0, day_defect_qty: 0, recorded_session_count: 0, open_session_count: 1,
      day_state: 'RUNNING',
      day_contributors: [{ employee_id: 1, name: 'An Chưa Nhập', good_qty: 0, defect_qty: 0, rework_qty: 0, scrap_qty: 0, recorded_sessions: 0 }],
      active_workers: [{ employee_id: 1, name: 'An Chưa Nhập' }], all_participants: [] },
    // OP đã có session chốt, số thật bằng 0 -> phải hiện "0", không được giấu
    { ...opBase, operation_id: 102, operation_code: 'OP-B-01', operation_name: 'HÀN GÓC',
      day_good_qty: 0, day_defect_qty: 0, recorded_session_count: 1,
      day_contributors: [{ employee_id: 2, name: 'Bình Chốt Không', good_qty: 0, defect_qty: 0, rework_qty: 0, scrap_qty: 0, recorded_sessions: 1 }],
      active_workers: [], all_participants: [] },
    // OP có số thật
    { ...opBase, operation_id: 103, operation_code: 'OP-C-01', operation_name: 'SƠN TĨNH ĐIỆN',
      day_good_qty: 32, day_defect_qty: 2, recorded_session_count: 1,
      day_contributors: [{ employee_id: 3, name: 'Cường Ba Hai', good_qty: 32, defect_qty: 2, rework_qty: 0, scrap_qty: 0, recorded_sessions: 1 }],
      active_workers: [], all_participants: [] },
  ];
  return { ok: true, items, sessions, activity: [] };
}

async function openDashboard(page, tab, { width = 1440, transform } = {}) {
  const date = hcmDate();
  await page.setViewportSize({ width, height: 1000 });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.route('**/api/settings/work-shifts', r => r.fulfill({ json: { ok: true, items: SHIFTS } }));
  await page.route('**/api/dashboard/day?**', r => {
    const body = payload(date);
    r.fulfill({ json: transform ? transform(body) : body });
  });
  await page.goto(`/app?page=dashboard&tab=${tab}`);
  await page.waitForTimeout(1500);
  return date;
}

// --- A. Hợp đồng của chính hàm dựng -------------------------------------
// Chạy trong trang thật (MFUI là IIFE gắn vào window), nên đo đúng đoạn mã
// được giao đi chứ không phải một bản chép lại trong test.
test('MFUI.qtyValue/qtyLine: chưa nhập, chốt 0 và số dương ra ba kết quả khác nhau', async ({ page }) => {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();

  const r = await page.evaluate(() => ({
    // qtyValue
    unknownNull: MFUI.qtyValue(null, false),
    unknownZero: MFUI.qtyValue(0, false),
    unknownUndefined: MFUI.qtyValue(undefined, true),
    recordedZero: MFUI.qtyValue(0, true),
    recordedPositive: MFUI.qtyValue(32, true),
    recordedThousand: MFUI.qtyValue(1234, true),
    // qtyLine (plain, dễ so chuỗi)
    lineUnknown: MFUI.qtyLine({ good: 0, defect: 0, recorded: false, plain: true }),
    lineZero: MFUI.qtyLine({ good: 0, defect: 0, recorded: true, plain: true }),
    linePositive: MFUI.qtyLine({ good: 32, defect: 2, recorded: true, plain: true }),
    lineRework: MFUI.qtyLine({ good: 5, defect: 1, rework: 3, recorded: true, plain: true }),
    lineScrap: MFUI.qtyLine({ good: 5, defect: 4, rework: 0, scrap: 4, recorded: true, plain: true }),
    // mfOutputRecorded: luật NGHIỆP VỤ nên sống ở app.js, không phải trong
    // core/ui.js -- tầng nền cố ý không biết tên cột nào của MESFlow
    // (tests/test_v71_ui_foundation.py canh ranh giới đó).
    foundationStaysBusinessFree: typeof MFUI.outputRecorded === 'undefined',
    openNeverEntered: mfOutputRecorded({ session_status: 'OPEN', good_qty: 0, defect_qty: 0, quantity_confirmed: true }),
    closedConfirmedZero: mfOutputRecorded({ session_status: 'CLOSED', good_qty: 0, defect_qty: 0, quantity_confirmed: true }),
    autoClosedUnconfirmed: mfOutputRecorded({ session_status: 'CLOSED', good_qty: 0, defect_qty: 0, quantity_confirmed: false }),
    openButAdjusted: mfOutputRecorded({ session_status: 'OPEN', good_qty: 7, defect_qty: 0, quantity_confirmed: true }),
    fieldWins: mfOutputRecorded({ session_status: 'OPEN', good_qty: 0, defect_qty: 0, output_recorded: true }),
    // status (Quản lý Session) và session_status (Dashboard) là cùng một cột,
    // hai endpoint đặt tên khác nhau -- hàm phải hiểu cả hai.
    statusAliasWorks: mfOutputRecorded({ status: 'CLOSED', good_qty: 0, defect_qty: 0, quantity_confirmed: true }),
  }));

  expect(r.unknownNull).toBe('—');
  expect(r.unknownZero, 'recorded=false thì số 0 vẫn là "chưa biết"').toBe('—');
  expect(r.unknownUndefined, 'không có giá trị thì không được bịa ra 0').toBe('—');
  expect(r.recordedZero, 'đã chốt bằng 0 phải hiện "0", không được giấu thành "—"').toBe('0');
  expect(r.recordedPositive).toBe('32');
  expect(r.recordedThousand).toBe((1234).toLocaleString('vi-VN'));

  expect(r.lineUnknown).toBe('Đạt — · NG —');
  // Đạt và NG luôn đi cùng nhau khi đã chốt: "Đạt 32" trơ trọi không nói được
  // NG vắng mặt vì bằng 0 hay vì chưa biết.
  expect(r.lineZero).toBe('Đạt 0 · NG 0');
  expect(r.linePositive).toBe('Đạt 32 · NG 2');
  expect(r.lineRework).toBe('Đạt 5 · NG 1 · Sửa 3');
  expect(r.lineScrap).toBe('Đạt 5 · NG 4 · Phế 4');

  expect(r.foundationStaysBusinessFree, 'luật nghiệp vụ lọt vào tầng nền core/ui.js').toBe(true);
  expect(r.openNeverEntered, 'session đang chạy chưa nhập gì -> chưa chốt').toBe(false);
  expect(r.closedConfirmedZero, 'đã kết thúc và xác nhận -> đã chốt, kể cả khi bằng 0').toBe(true);
  expect(r.autoClosedUnconfirmed, 'máy tự đóng cuối ca -> chưa ai xác nhận').toBe(false);
  expect(r.openButAdjusted, 'đã có số dương thì phải hiện số thật').toBe(true);
  expect(r.fieldWins, 'có field của API thì field thắng, không suy đoán').toBe(true);
  expect(r.statusAliasWorks, 'không nhận ra cột status của Quản lý Session').toBe(true);
});

// --- B. Bốn trạng thái trên đúng bề mặt người dùng nhìn -------------------
const PEOPLE_CASES = [
  ['An Chưa Nhập', 'Đạt — · NG —', 'đang chạy, chưa nhập'],
  ['Bình Chốt Không', 'Đạt 0 · NG 0', 'đã chốt đúng 0'],
  ['Cường Ba Hai', 'Đạt 32 · NG 2', 'đã chốt số thật'],
  ['Dũng Tự Đóng', 'Đạt — · NG —', 'máy tự đóng, chưa xác nhận'],
];

for (const [employee, expected, label] of PEOPLE_CASES) {
  test(`tab Nhân viên / Session -- ${label}: ${expected}`, async ({ page }) => {
    await openDashboard(page, 'people');
    const row = page.locator('.employee-day-row', { hasText: employee });
    await expect(row).toBeVisible({ timeout: 15000 });
    // Dòng tổng của nhân viên
    await expect(row.locator('.employee-day-summary > small')).toHaveText(expected);
    // Và chính con chip của session đó
    await expect(row.locator('.employee-session-chips .op-identity-meta').first()).toContainText(expected.replace('Đạt ', 'Đạt '));
  });
}

test('tab Tổng quan Operation: chưa chốt ra "—", chốt-bằng-0 ra "0"', async ({ page }) => {
  await openDashboard(page, 'overview');
  // Dòng "Trong ca" nằm ở ô cuối của hàng; các số được bọc trong span .qty-*
  // riêng nên bắt theo chữ của cả hàng thay vì đi vào một span cụ thể.
  const rowOf = name => page.locator('.op-time-row:not(.head)', { hasText: name });
  await expect(rowOf('CHẤN BƯỚC 1')).toContainText('Trong ca: Đạt — · NG —');
  await expect(rowOf('HÀN GÓC')).toContainText('Trong ca: Đạt 0 · NG 0');
  await expect(rowOf('SƠN TĨNH ĐIỆN')).toContainText('Trong ca: Đạt 32 · NG 2');
  // Và phần bóc tách theo từng người phải nói cùng một chuyện.
  await expect(rowOf('CHẤN BƯỚC 1').locator('.op-worker-line')).toContainText('An Chưa Nhập: Đạt — · NG —');
  await expect(rowOf('HÀN GÓC').locator('.op-worker-line')).toContainText('Bình Chốt Không: Đạt 0 · NG 0');
});

test('KPI ngày: chưa session nào chốt số thì không in ra 0', async ({ page }) => {
  // Chỉ giữ đúng session đang chạy chưa nhập gì -- cả ngày chưa ai chốt số.
  await openDashboard(page, 'people', {
    transform: body => ({ ...body, sessions: body.sessions.filter(s => s.session_id === 1) }),
  });
  const kpis = page.locator('.daily-kpi');
  await expect(kpis.nth(2)).toContainText('Sản lượng đạt');
  await expect(kpis.nth(2).locator('strong')).toHaveText('—');
  await expect(kpis.nth(2)).toContainText('Chưa session nào chốt số');
  await expect(kpis.nth(3).locator('strong')).toHaveText('—');
  // Hai KPI đếm người/đếm session thì 0 vẫn là 0 thật -- đếm được, không phụ
  // thuộc ai đã nhập gì.
  await expect(kpis.nth(0).locator('strong')).toHaveText('1');
});

test('payload cũ không có output_recorded thì lùi về luật của backend, không coi mọi thứ là đã chốt', async ({ page }) => {
  await openDashboard(page, 'people', {
    transform: body => ({
      ...body,
      sessions: body.sessions.map(({ output_recorded, ...rest }) => rest),
    }),
  });
  // OPEN chưa nhập -> vẫn "—" nhờ (status + quantity_confirmed), không phải 0.
  await expect(page.locator('.employee-day-row', { hasText: 'An Chưa Nhập' })
    .locator('.employee-day-summary > small')).toHaveText('Đạt — · NG —');
  // CLOSED + quantity_confirmed=false -> vẫn "—".
  await expect(page.locator('.employee-day-row', { hasText: 'Dũng Tự Đóng' })
    .locator('.employee-day-summary > small')).toHaveText('Đạt — · NG —');
  // CLOSED + đã xác nhận, số 0 -> vẫn phải ra "0".
  await expect(page.locator('.employee-day-row', { hasText: 'Bình Chốt Không' })
    .locator('.employee-day-summary > small')).toHaveText('Đạt 0 · NG 0');
});

test('"—" và "0" không chỉ khác chữ mà còn khác trọng lượng thị giác', async ({ page }) => {
  await openDashboard(page, 'people');
  const weights = await page.evaluate(() => {
    const pick = name => [...document.querySelectorAll('.employee-day-row')]
      .find(r => r.textContent.includes(name));
    const styleOf = (row, sel) => {
      const el = row.querySelector(sel);
      return el ? { weight: +getComputedStyle(el).fontWeight, color: getComputedStyle(el).color } : null;
    };
    return {
      unknown: styleOf(pick('An Chưa Nhập'), '.employee-day-summary .qty-empty'),
      zero: styleOf(pick('Bình Chốt Không'), '.employee-day-summary .qty-good'),
    };
  });
  expect(weights.unknown, 'chưa nhập phải dùng .qty-empty').not.toBeNull();
  expect(weights.zero, 'đã chốt phải dùng .qty-good').not.toBeNull();
  // Chưa-nhập nhẹ hơn đã-chốt: mắt lướt qua không đọc nhầm thành số đã xác nhận.
  expect(weights.unknown.weight).toBeLessThan(weights.zero.weight);
  expect(weights.unknown.color).not.toBe(weights.zero.color);
});
