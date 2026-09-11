// E2E for "Kiosk điều hành" — the control-room display opened from
// Dashboard theo ngày. Every API is mocked, so this exercises the route,
// the URL/date round-trip, the layout at TV resolutions and the failure
// behaviour without needing production data.
const { test, expect } = require('@playwright/test');

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'
}).format(new Date());

const at = (date, hour, minute = 0) =>
  new Date(`${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00+07:00`).toISOString();

const SHIFTS = [
  { id: 1, code: 'DAY', name: 'Ca ngày', active: true, anchor_start: '07:30', anchor_end: '17:00', cross_midnight: false, target_minutes: 480,
    intervals: [{ interval_type: 'WORK', start_minute: 450, end_minute: 1020, sort_order: 0 }] },
  { id: 2, code: 'NIGHT', name: 'Ca tối', active: true, anchor_start: '18:00', anchor_end: '00:00', cross_midnight: true, target_minutes: 360,
    intervals: [{ interval_type: 'WORK', start_minute: 1080, end_minute: 1440, sort_order: 0 }] }
];

// One Operation with a deliberately long code, so the "name primary / code
// secondary" convention is tested against the exact case it exists for.
const LONG_CODE = '111-THAN-THUNG-R-04-LONG-CODE';
const OP_NAME = 'Hàn thùng rác inox';

function dayPayload(date, { good = 120, bumped = false } = {}) {
  const items = [
    { po_id: 1, po_code: 'PO-KIOSK-1', product: 'Thùng rác inox', part_id: 1, part_code: 'PART-1', part_name: 'Thân thùng',
      operation_id: 11, operation_code: LONG_CODE, operation_name: OP_NAME, operation_status: 'IN_PROGRESS',
      total_good_qty: 300, total_defect_qty: 12, planned_quantity: 500, standard_seconds_per_unit: 60,
      planned_work_seconds: 30000, session_count: 3, open_session_count: 1,
      day_good_qty: good, day_defect_qty: 18, day_rework_qty: 0, day_scrap_qty: 0, day_work_seconds: 21000,
      active_workers: [{ employee_id: 1, name: 'Nguyễn Văn A' }], all_participants: [], day_contributors: [],
      last_report_at: at(date, 14), unconfirmed_count: 0, day_state: 'RUNNING' },
    { po_id: 1, po_code: 'PO-KIOSK-1', product: 'Thùng rác inox', part_id: 1, part_code: 'PART-1', part_name: 'Thân thùng',
      operation_id: 12, operation_code: 'OP-SON-02', operation_name: 'Sơn tĩnh điện', operation_status: 'IN_PROGRESS',
      total_good_qty: 150, total_defect_qty: 2, planned_quantity: 500, standard_seconds_per_unit: 30,
      planned_work_seconds: 15000, session_count: 1, open_session_count: 0,
      day_good_qty: 40, day_defect_qty: 1, day_rework_qty: 0, day_scrap_qty: 0, day_work_seconds: 9000,
      active_workers: [], all_participants: [], day_contributors: [],
      last_report_at: at(date, 11), unconfirmed_count: 2, day_state: 'NEEDS_REVIEW' }
  ];
  const sessions = [
    { session_id: 1, session_status: 'OPEN', started_at: at(date, 8), ended_at: null, effective_end_at: at(date, 9),
      duration_seconds: 3600, work_duration_seconds: 3600, good_qty: good, defect_qty: 18, rework_qty: 0, scrap_qty: 0,
      employee_id: 1, employee_code: 'EMP-001', employee_name: 'Nguyễn Văn A',
      po_id: 1, po_code: 'PO-KIOSK-1', part_id: 1, part_code: 'PART-1', part_name: 'Thân thùng',
      operation_id: 11, operation_code: LONG_CODE, operation_name: OP_NAME },
    { session_id: 2, session_status: 'CLOSED', started_at: at(date, 10), ended_at: at(date, 11), effective_end_at: at(date, 11),
      duration_seconds: 3600, work_duration_seconds: 3600, good_qty: 40, defect_qty: 1, rework_qty: 0, scrap_qty: 0,
      employee_id: 2, employee_code: 'EMP-002', employee_name: 'Trần Thị B',
      po_id: 1, po_code: 'PO-KIOSK-1', part_id: 1, part_code: 'PART-1', part_name: 'Thân thùng',
      operation_id: 12, operation_code: 'OP-SON-02', operation_name: 'Sơn tĩnh điện' }
  ];
  if (bumped) sessions.push({ ...sessions[1], session_id: 3, started_at: at(date, 13), ended_at: at(date, 14),
    effective_end_at: at(date, 14), good_qty: 77, defect_qty: 0 });
  return { ok: true, context: { date, timezone: 'Asia/Ho_Chi_Minh', day_start: at(date, 0), day_end: at(date, 23, 59) },
    items, sessions, activity: [] };
}

const OVERVIEW = {
  ok: true,
  summary: { unconfirmed_quantity_sessions: 2 },
  production_orders: [{ po_id: 1, po_code: 'PO-KIOSK-1', product: 'Thùng rác inox', planned_quantity: 500,
    good_quantity: 300, defect_quantity: 12, scrap_quantity: 0, remaining_quantity: 200, progress_percent: 60,
    due_date: '2026-09-30', repair_pending_quantity: 9, repair_unconfigured_operation_count: 0,
    estimated_repair_work_seconds: 3600, control_state: 'WARNING' }],
  operations: []
};

const CONTROL = {
  ok: true,
  production_orders: [{ po_id: 1, control_state: 'WARNING', control_label: 'CẦN CHÚ Ý' }],
  operations: [{ po_id: 1, operation_id: 11, operation_code: LONG_CODE, operation_name: OP_NAME,
    control_state: 'CRITICAL', control_label: 'LÀM NGAY', recommended_action: 'Ưu tiên cấp người/máy cho Operation này' }]
};

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
}

async function mockAll(page, date, opts = {}) {
  const state = { dayCalls: 0 };
  await page.route('**/api/settings/work-shifts', r => r.fulfill({ json: { ok: true, items: SHIFTS } }));
  await page.route('**/api/dashboard/day?**', r => {
    state.dayCalls += 1;
    if (opts.failDayAfter && state.dayCalls > opts.failDayAfter) {
      return r.fulfill({ status: 500, json: { ok: false, message: 'Mô phỏng lỗi API' } });
    }
    r.fulfill({ json: dayPayload(date, { good: 120, bumped: state.dayCalls > 1 }) });
  });
  await page.route('**/api/dashboard/overview**', r => r.fulfill({ json: OVERVIEW }));
  await page.route('**/api/production-control**', r => r.fulfill({ json: CONTROL }));
  return state;
}

async function openKioskFromDashboard(page, date) {
  await page.goto(`/app?page=dashboard&date=${date}`);
  await expect(page.locator('#appLayout')).toBeVisible();
  await expect(page.locator('#dailyOpenKiosk')).toBeVisible();
  await page.locator('#dailyOpenKiosk').click();
  await expect(page.locator('#kioskRoot')).toBeVisible();
}

// Nothing in this view may write to the console; a TV nobody is watching
// must not be quietly throwing.
function watchConsole(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  return errors;
}

const noHorizontalOverflow = async page => page.evaluate(() =>
  document.documentElement.scrollWidth <= window.innerWidth + 1);

// A wall display cannot be scrolled, so a row sliced through the middle is a
// layout defect, not "there is more below". Every rendered Operation row must
// sit fully inside its panel.
const noClippedRow = async page => page.evaluate(() => {
  const body = document.querySelector('#kioskStations');
  if (!body) return true;
  const limit = body.getBoundingClientRect().bottom + 1;
  // Measure what is PAINTED, not what is flagged: `.kiosk-tr{display:grid}`
  // outranks the UA `[hidden]` rule, so `el.hidden` alone is not proof a row
  // is off screen.
  return [...body.querySelectorAll('.kiosk-tr')]
    .filter(el => !el.classList.contains('kiosk-more'))
    .filter(el => el.offsetParent !== null && el.getBoundingClientRect().height > 0)
    .every(el => el.getBoundingClientRect().bottom <= limit);
});

// The whole-row trim must never starve the table down to zero Operation rows:
// a panel whose entire content is "+N khác" tells the quản đốc nothing.
const paintedRowCount = async page => page.evaluate(() => {
  const body = document.querySelector('#kioskStations');
  if (!body) return 0;
  return [...body.querySelectorAll('.kiosk-tr')]
    .filter(el => !el.classList.contains('kiosk-more') && !el.classList.contains('kiosk-th'))
    .filter(el => el.offsetParent !== null && el.getBoundingClientRect().height > 0).length;
});

// The colour key is the only thing that says which bar means what; a tighter
// viewport must shrink it, never squeeze it out of the panel.
const legendVisible = async page => page.evaluate(() => {
  const el = document.querySelector('.kiosk-chart-legend');
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const panel = el.closest('.kiosk-panel').getBoundingClientRect();
  return r.height > 0 && r.bottom <= panel.bottom + 1;
});

test.describe('Kiosk điều hành', () => {
  test('mở từ Dashboard theo ngày, giữ đúng date qua refresh và Back/Forward', async ({ page }) => {
    const errors = watchConsole(page);
    const date = hcmDate();
    await mockAll(page, date);
    await login(page);

    // 1 + 2: opened by the button, on the date the dashboard was showing.
    await openKioskFromDashboard(page, date);
    await expect(page).toHaveURL(new RegExp(`page=daily-dashboard-kiosk`));
    await expect(page).toHaveURL(new RegExp(`date=${date}`));
    await expect(page.locator('#kioskDate')).toContainText(date.slice(8, 10));

    // 3: refresh keeps the date (deep-link works, screen is not blank).
    await page.reload();
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`date=${date}`));
    await expect(page.locator('#kioskKpis .kiosk-kpi').first()).toBeVisible();

    // 4: Back returns to the dashboard, Forward returns to the kiosk.
    await page.goBack();
    await expect(page.locator('#dailyDate')).toBeVisible();
    await expect(page.locator('#kioskRoot')).toHaveCount(0);
    await page.goForward();
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`date=${date}`));

    expect(errors).toEqual([]);
  });

  test('hiển thị dữ liệu thật, tên OP là chính và mã là phụ', async ({ page }) => {
    const errors = watchConsole(page);
    const date = hcmDate();
    await mockAll(page, date);
    await login(page);
    await openKioskFromDashboard(page, date);

    // 5: real numbers on screen, nothing blank.
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    await expect(page.locator('#kioskKpis')).toContainText('Sản lượng đạt');
    await expect(page.locator('#kioskHourly .kiosk-bar')).toHaveCount(24);
    await expect(page.locator('#kioskStations .kiosk-tr').first()).toBeVisible();
    await expect(page.locator('#kioskLiveText')).toContainText('Cập nhật lần cuối');

    // 10: Operation name is the headline, the long code is the small line.
    // Addressed by content: the table sorts exceptions (NEEDS_REVIEW) to the
    // top, so a row index is not a stable handle for a specific Operation.
    const row = page.locator('#kioskStations .kiosk-tr').filter({ hasText: OP_NAME });
    await expect(row).toHaveCount(1);
    await expect(row.locator('.kiosk-op b')).toHaveText(OP_NAME);
    await expect(row.locator('.kiosk-op small')).toContainText(LONG_CODE);
    const nameSize = await row.locator('.kiosk-op b').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
    const codeSize = await row.locator('.kiosk-op small').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
    expect(nameSize).toBeGreaterThan(codeSize);

    // E: the dispatch panel surfaces the real signals, and names what it cannot source.
    await expect(page.locator('#kioskAttention')).toContainText('Session chưa xác nhận');
    await expect(page.locator('#kioskAttentionFoot')).toContainText('chưa có nguồn dữ liệu');

    expect(errors).toEqual([]);
  });

  test('1920x1080 và 1366x768 không tràn ngang', async ({ page }) => {
    const errors = watchConsole(page);
    const date = hcmDate();
    await mockAll(page, date);
    await login(page);

    // 7
    await page.setViewportSize({ width: 1920, height: 1080 });
    await openKioskFromDashboard(page, date);
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    expect(await noHorizontalOverflow(page)).toBe(true);
    // The whole display fits the first viewport at TV size -- no vertical
    // scrolling for something meant to be read passively from a distance.
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 2)).toBe(true);
    expect(await noClippedRow(page)).toBe(true);

    // 8 + 9: the smaller wall/laptop size keeps ALL eight KPI tiles and still
    // fits one screen -- a display nobody can scroll must not hide half itself.
    await page.setViewportSize({ width: 1366, height: 768 });
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    expect(await noHorizontalOverflow(page)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight + 2)).toBe(true);
    await expect(page.locator('#kioskStations .kiosk-tr').first()).toBeVisible();
    expect(await noClippedRow(page)).toBe(true);
    expect(await paintedRowCount(page)).toBeGreaterThanOrEqual(2);
    expect(await legendVisible(page)).toBe(true);
    // The side column's dispatch panel must still be on screen at this size.
    await expect(page.locator('#kioskAttention')).toBeVisible();

    expect(errors).toEqual([]);
  });

  test('auto refresh cập nhật tại chỗ, không reload và không phá layout', async ({ page }) => {
    test.setTimeout(90000);
    const errors = watchConsole(page);
    const date = hcmDate();
    await mockAll(page, date);
    await login(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await openKioskFromDashboard(page, date);

    // Mark the live DOM: if the poll reloaded the page (instead of updating in
    // place) this marker would be gone.
    await page.evaluate(() => { window.__kioskAlive = true; });
    const firstStamp = await page.locator('#kioskLiveText').textContent();

    // 6: the 20s poll fires, the numbers change, the shell survives.
    await expect.poll(async () => page.locator('#kioskLiveText').textContent(), { timeout: 45000, intervals: [1000] })
      .not.toBe(firstStamp);
    expect(await page.evaluate(() => window.__kioskAlive === true)).toBe(true);
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    expect(await noHorizontalOverflow(page)).toBe(true);

    expect(errors).toEqual([]);
  });

  test('lỗi API giữ nguyên dữ liệu cũ và báo mất kết nối', async ({ page }) => {
    const errors = watchConsole(page);
    const date = hcmDate();
    // call 1 = Dashboard theo ngày, call 2 = the kiosk's initial load,
    // call 3 = the manual refresh below, which is the one that must fail.
    await mockAll(page, date, { failDayAfter: 2 });
    await login(page);
    await openKioskFromDashboard(page, date);
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    const before = await page.locator('#kioskKpis').textContent();

    // 11: a failing poll must not blank the wall display.
    await page.locator('#kioskRefresh').click();
    await expect(page.locator('#kioskLive')).toHaveAttribute('data-state', 'stale');
    await expect(page.locator('#kioskLiveText')).toContainText('Mất kết nối');
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    expect(await page.locator('#kioskKpis').textContent()).toBe(before);

    // 12: no APPLICATION error. The browser itself always logs a
    // "Failed to load resource: 500" network line for the deliberately
    // failed request -- that is Chrome's network log, not something the page
    // threw, so it is the one entry allowed here. Anything else (an uncaught
    // exception, a console.error from our own code) still fails the test.
    const appErrors = errors.filter(e => !/Failed to load resource/.test(e));
    expect(appErrors).toEqual([]);
  });

  test('empty state của biểu đồ và các panel vẫn đẹp', async ({ page }) => {
    const errors = watchConsole(page);
    const date = hcmDate();
    await page.route('**/api/settings/work-shifts', r => r.fulfill({ json: { ok: true, items: SHIFTS } }));
    await page.route('**/api/dashboard/day?**', r => r.fulfill({
      json: { ok: true, context: { date, timezone: 'Asia/Ho_Chi_Minh', day_start: at(date, 0), day_end: at(date, 23, 59) },
        items: [], sessions: [], activity: [] } }));
    await page.route('**/api/dashboard/overview**', r => r.fulfill({ json: { ok: true, summary: {}, production_orders: [], operations: [] } }));
    await page.route('**/api/production-control**', r => r.fulfill({ json: { ok: true, production_orders: [], operations: [] } }));
    await login(page);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await openKioskFromDashboard(page, date);

    // 13
    await expect(page.locator('#kioskHourly .kiosk-empty')).toBeVisible();
    await expect(page.locator('#kioskHourly')).toContainText('Chưa có sản lượng ghi nhận');
    await expect(page.locator('#kioskStations')).toContainText('Chưa có Operation hoạt động');
    await expect(page.locator('#kioskAttention')).toContainText('Không có điểm cần xử lý');
    await expect(page.locator('#kioskAttentionCount')).toHaveText('Sạch');
    // Still a complete, non-blank screen.
    await expect(page.locator('#kioskKpis .kiosk-kpi')).toHaveCount(8);
    expect(await noHorizontalOverflow(page)).toBe(true);

    expect(errors).toEqual([]);
  });
});
