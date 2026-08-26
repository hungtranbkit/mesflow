const { test, expect } = require('@playwright/test');

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'
}).format(new Date());

const at = (date, hour, minute = 0, dayOffset = 0) => {
  const value = new Date(`${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00+07:00`);
  value.setDate(value.getDate() + dayOffset);
  return value.toISOString();
};

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

function sessionsFor(date) {
  const sessions = Array.from({ length: 20 }, (_, index) => ({
    session_id: index + 1,
    session_status: 'OPEN',
    started_at: at(date, 8 + Math.floor(index / 4), (index % 4) * 10),
    ended_at: null,
    employee_id: index + 1,
    employee_code: `EMP-${String(index + 1).padStart(3, '0')}`,
    employee_name: `Nhân viên ${String(index + 1).padStart(2, '0')}`,
    operation_id: index + 1,
    operation_code: `OP-${String(index + 1).padStart(3, '0')}`,
    operation_name: index === 0 ? 'Operation có tên rất dài để kiểm tra không làm vỡ timeline ngày công' : `Operation ${index + 1}`,
    po_code: 'PO-E2E', part_code: 'PART-E2E', good_qty: 0, defect_qty: 0
  }));
  sessions.push({ ...sessions[0], session_id: 100, session_status: 'CLOSED', started_at: at(date, 6, 0), ended_at: at(date, 7, 30), operation_id: 100, operation_code: 'OP-CLOSED' });
  return sessions;
}

async function mockDashboard(page, date) {
  const shifts = [
    { id: 1, code: 'DAY', name: 'Ca ngày', active: true, anchor_start: '00:00', anchor_end: '23:59', cross_midnight: false, target_minutes: 480,
      intervals: [{ interval_type: 'WORK', start_minute: 0, end_minute: 720, sort_order: 0 }, { interval_type: 'BREAK', start_minute: 720, end_minute: 780, label: 'Nghỉ giữa ca', sort_order: 1 }, { interval_type: 'WORK', start_minute: 780, end_minute: 1439, sort_order: 2 }] },
    { id: 2, code: 'NIGHT', name: 'Ca tối', active: true, anchor_start: '18:00', anchor_end: '03:00', cross_midnight: true, target_minutes: 480,
      intervals: [{ interval_type: 'WORK', start_minute: 1080, end_minute: 1440, sort_order: 0 }, { interval_type: 'BREAK', start_minute: 1440, end_minute: 1470, label: 'Nghỉ giữa ca', sort_order: 1 }, { interval_type: 'WORK', start_minute: 1470, end_minute: 1620, sort_order: 2 }] }
  ];
  await page.route('**/api/settings/work-shifts', route => route.fulfill({ json: { ok: true, items: shifts } }));
  await page.route('**/api/dashboard/shift?**', route => {
    const url = new URL(route.request().url());
    const shiftId = Number(url.searchParams.get('shift_id'));
    const sessions = shiftId === 2 ? [{ ...sessionsFor(date)[0], started_at: at(date, 19), employee_name: 'Nhân viên ca tối' }] : sessionsFor(date);
    route.fulfill({ json: { ok: true, items: [], activity: [], sessions } });
  });
}

test('timeline là nguồn session duy nhất, OPEN có duration và refresh không duplicate', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const date = hcmDate();
  await login(page);
  // Fixed (2026-08-26): the OPEN session's "now" boundary used to be the
  // real wall clock at test-run time. sessionsFor()'s first employee starts
  // at 08:00 -- whether their running segment has crossed the 12:00-13:00
  // lunch break (and so renders as 3 segments: closed + open-before-break +
  // open-after-break) depended entirely on what real time the suite
  // happened to run at, so this failed whenever CI ran before 13:00 HCM.
  // Freezing the page's clock to a fixed afternoon time makes the expected
  // 3-segment split deterministic regardless of wall-clock run time.
  await page.clock.setFixedTime(new Date(`${date}T14:30:00+07:00`));
  await mockDashboard(page, date);
  await page.evaluate(() => openPage('dashboard'));

  await expect(page.locator('#dailyEmployeeSort')).toHaveValue('start');
  await expect(page.locator('.running-session-card')).toHaveCount(0);
  await expect(page.locator('.employee-day-row')).toHaveCount(20);
  await expect(page.locator('.employee-session-chips span.open').first()).toContainText('Đang chạy');
  await expect(page.locator('.employee-session-chips span.open').first()).toContainText(/phút|giờ/);
  await expect(page.locator('#dailySessionStatus')).toContainText('20 session đang chạy');
  // One closed session plus one OPEN session split around the configured break.
  await expect(page.locator('.employee-day-row').first().locator('.employee-session-segment')).toHaveCount(3);

  await page.locator('#dailyEmployeeSort').selectOption('name');
  await expect(page.locator('.employee-day-person b').first()).toHaveText('Nhân viên 01');
  await page.locator('#dailyRefresh').click();
  await expect(page.locator('.employee-day-row')).toHaveCount(20);
  expect(errors).toEqual([]);
});

test('ca qua nửa đêm là một timeline liên tục và lịch sử không có vạch NOW', async ({ page }) => {
  const date = hcmDate();
  await login(page);
  await mockDashboard(page, date);
  await page.evaluate(() => openPage('dashboard'));
  await page.locator('#dailyDate').fill('2026-08-01');
  await page.locator('#dailyShift').selectOption('2');
  await expect(page.locator('.shift-scale-mark', { hasText: '18:00' })).toHaveCount(1);
  await expect(page.locator('.shift-scale-mark', { hasText: '00:00' })).toHaveCount(1);
  await expect(page.locator('.shift-scale-mark', { hasText: '03:00' })).toHaveCount(1);
  await expect(page.locator('.shift-now')).toHaveCount(0);
  await expect(page.locator('.employee-session-chips span.open')).toContainText('Đang chạy');
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 390, height: 844 }]) {
  test(`timeline không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const date = hcmDate();
    await page.setViewportSize(viewport);
    await login(page);
    await mockDashboard(page, date);
    await page.evaluate(() => openPage('dashboard'));
    await expect(page.locator('.session-timeline-panel')).toBeVisible();
    const overflow = await page.locator('body').evaluate(body => body.scrollWidth > body.clientWidth);
    expect(overflow).toBe(false);
    await page.screenshot({ path: `test-results/dashboard-timeline-${viewport.width}x${viewport.height}.png`, fullPage: true });
  });
}
