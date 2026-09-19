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
  // Trang /login khi đã có phiên sẽ tự điều hướng sang /app; lần goto ngay
  // sau đó bị chính nó cắt ngang ("interrupted by another navigation").
  // Đợi chuyển hướng tự động xong rồi mới đi tiếp -- nguồn flaky lác đác
  // của cả bộ E2E, tìm ra khi truy po-action-menu (2026-09-09).
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
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
  await page.route('**/api/dashboard/day?**', route => {
    const sessions = sessionsFor(date);
    sessions.push({ ...sessions[1], session_id: 101, employee_id: 21, employee_code: 'EMP-021', employee_name: 'Nhân viên ca tối', started_at: at(date, 19), operation_id: 201, operation_code: 'OP-NIGHT' });
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
  await page.locator('[data-dashboard-tab="people"]').click();

  await expect(page.locator('#dailyEmployeeSort')).toHaveValue('start');
  await expect(page.locator('.running-session-card')).toHaveCount(0);
  await expect(page.locator('.employee-day-row')).toHaveCount(21);
  await expect(page.locator('.employee-session-chips span.open').first()).toContainText('Đang chạy');
  // v71.0.0.235: duration shortened from "X giờ Y phút" to "Xg Yp".
  await expect(page.locator('.employee-session-chips span.open').first()).toContainText(/\dp\b/);
  await expect(page.locator('#dailySessionStatus')).toContainText('21 session đang chạy');
  // The date dashboard uses one full-day timeline, so sessions are not
  // split by a selected shift's break window.
  await expect(page.locator('.employee-day-row').first().locator('.employee-session-segment')).toHaveCount(2);

  await page.locator('#dailyEmployeeSort').selectOption('name');
  await expect(page.locator('.employee-day-person b').first()).toHaveText('Nhân viên 01');
  await page.locator('#dailyRefresh').click();
  await expect(page.locator('.employee-day-row')).toHaveCount(21);
  expect(errors).toEqual([]);
});

test('dashboard ngày vẫn hiển thị session ca tối cùng ngày', async ({ page }) => {
  const date = hcmDate();
  await login(page);
  await mockDashboard(page, date);
  await page.evaluate(() => openPage('dashboard'));
  await page.locator('#dailyDate').fill('2026-08-01');
  await page.locator('[data-dashboard-tab="people"]').click();
  await page.locator('[data-dashboard-tab="output"]').click();
  await page.locator('[data-dashboard-tab="overview"]').click();
  await expect(page.locator('#dailyDate')).toHaveValue('2026-08-01');
  await page.locator('[data-dashboard-tab="people"]').click();
  await expect(page.locator('#dailyShift')).toHaveCount(0);
  await expect(page.locator('.employee-day-person b', { hasText: 'Nhân viên ca tối' })).toBeVisible();
  await expect(page.locator('.employee-day-row', { hasText: 'Nhân viên ca tối' }).locator('.employee-session-chips span.open')).toContainText('Đang chạy');
});

for (const viewport of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 390, height: 844 }]) {
  test(`timeline không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const date = hcmDate();
    await page.setViewportSize(viewport);
    await login(page);
    await mockDashboard(page, date);
    await page.evaluate(() => openPage('dashboard'));
    await page.locator('[data-dashboard-tab="people"]').click();
    await expect(page.locator('.session-timeline-panel')).toBeVisible();
    const overflow = await page.locator('body').evaluate(body => body.scrollWidth > body.clientWidth);
    expect(overflow).toBe(false);
    await page.screenshot({ path: `test-results/dashboard-timeline-${viewport.width}x${viewport.height}.png`, fullPage: true });
  });
}

// ---------------------------------------------------------------------------
// HOTFIX -- timeline chỉ được nói một thứ bằng màu.
//
// Hai điều bài test dưới đây đo trên trình duyệt thật, vì cả hai đều là câu
// hỏi về computed style / thứ tự dựng DOM mà đọc file nguồn không trả lời được:
//
//   1. Khoảng hở, giờ nghỉ và ngoài ca phải ra ĐÚNG một nền. Trước hotfix
//      chúng có bốn công thức, hai trong đó vàng cam rực hơn thanh việc thật.
//   2. Tông thanh việc phải đi theo công đoạn, không theo vị trí trong vòng
//      lặp. Fixture cố tình đảo thứ tự hai OP giữa hai nhân viên: với mã cũ
//      (palette[i%6]) cùng một OP sẽ ra hai màu khác nhau.
// ---------------------------------------------------------------------------

const TONE_A = 11, TONE_B = 22; // hai operation_id bất kỳ, miễn khác nhau

async function mockToneFixture(page, date) {
  const session = (id, employee, operation, fromHour, toHour) => ({
    session_id: id, session_status: 'CLOSED',
    started_at: at(date, fromHour), ended_at: at(date, toHour),
    employee_id: employee, employee_code: `EMP-${employee}`,
    employee_name: `Nhân viên ${employee}`,
    operation_id: operation, operation_code: `OP-${operation}`,
    operation_name: `Operation ${operation}`,
    po_code: 'PO-TONE', part_code: 'PART-TONE', good_qty: 1, defect_qty: 0
  });
  // Cùng hai OP, thứ tự đảo ngược giữa hai người. Khoảng 09:00-10:00 bỏ trống
  // ở cả hai hàng -> 60 phút -> .employee-gap.long.
  const sessions = [
    session(1, 1, TONE_A, 8, 9), session(2, 1, TONE_B, 10, 11),
    session(3, 2, TONE_B, 8, 9), session(4, 2, TONE_A, 10, 11)
  ];
  await page.route('**/api/settings/work-shifts', route => route.fulfill({ json: { ok: true, items: [] } }));
  await page.route('**/api/dashboard/day?**', route =>
    route.fulfill({ json: { ok: true, items: [], activity: [], sessions } }));
}

async function openToneDashboard(page, date) {
  await page.clock.setFixedTime(new Date(`${date}T14:30:00+07:00`));
  await mockToneFixture(page, date);
  await page.evaluate(() => openPage('dashboard'));
  await page.locator('[data-dashboard-tab="people"]').click();
  await expect(page.locator('.employee-day-row')).toHaveCount(2);
}

const toneOf = async (page, row, index) => {
  const className = await page.locator('.employee-day-row').nth(row)
    .locator('.employee-session-segment').nth(index).getAttribute('class');
  return className.split(/\s+/).find(name => name.startsWith('tone-'));
};

test('tông thanh việc đi theo công đoạn, không theo vị trí trong hàng', async ({ page }) => {
  const date = hcmDate();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await openToneDashboard(page, date);

  const [firstA, firstB, secondB, secondA] = await Promise.all([
    toneOf(page, 0, 0), toneOf(page, 0, 1), toneOf(page, 1, 0), toneOf(page, 1, 1)
  ]);
  for (const tone of [firstA, firstB, secondB, secondA]) {
    expect(tone, 'thanh việc phải mang đúng một lớp tone-N').toBeTruthy();
  }
  // OP_A đứng đầu hàng 1 và đứng cuối hàng 2 -- vẫn phải cùng một tông.
  expect(firstA, `OP-${TONE_A} đổi tông theo vị trí`).toBe(secondA);
  expect(firstB, `OP-${TONE_B} đổi tông theo vị trí`).toBe(secondB);
  // ...và hai OP khác nhau thì không được trùng tông trong cùng một hàng.
  expect(firstA).not.toBe(firstB);
});

test('khoảng hở, giờ nghỉ và ngoài ca dùng chung đúng một nền yên', async ({ page }) => {
  const date = hcmDate();
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await openToneDashboard(page, date);

  await expect(page.locator('.employee-gap.long').first()).toBeVisible();
  // .shift-lunch chỉ dựng khi ca có khoảng BREAK, mà dashboard ngày luôn dùng
  // khung nguyên ngày -- gắn một phần tử dò để vẫn đo được nền của nó thật.
  await page.locator('.employee-day-track').first()
    .evaluate(track => track.insertAdjacentHTML('beforeend', '<i class="shift-lunch probe"></i>'));

  const backgroundOf = selector => page.locator(selector).first()
    .evaluate(element => getComputedStyle(element).backgroundImage);
  const quiet = ['.employee-gap', '.employee-gap.long', '.shift-off.after',
    '.shift-lunch.probe', '.legend-gap', '.legend-lunch', '.legend-off'];
  const backgrounds = await Promise.all(quiet.map(backgroundOf));

  for (const [index, background] of backgrounds.entries()) {
    expect(background, `${quiet[index]} phải có nền sọc yên`).toContain('repeating-linear-gradient');
    expect(background, `${quiet[index]} lệch khỏi nền chung`).toBe(backgrounds[0]);
    // Không màu nào trong nền được ngả ấm -- đó chính là vàng/cam đã bỏ.
    for (const [, r, g, b] of background.matchAll(/rgba?\((\d+),\s*(\d+),\s*(\d+)/g)) {
      expect(Number(b), `${quiet[index]} còn màu ấm: ${background}`).toBeGreaterThanOrEqual(Number(r));
      expect(Math.max(r, g, b) - Math.min(r, g, b), `${quiet[index]} còn màu đậm`).toBeLessThan(40);
    }
  }

  // Thanh việc thật thì ngược lại: nền đặc, không sọc.
  const bar = await backgroundOf('.employee-session-segment');
  expect(bar).toBe('none');

  await page.screenshot({ path: 'test-results/timeline-quiet-gap-1920x1080.png', fullPage: true });
  await page.setViewportSize({ width: 1366, height: 768 });
  await expect(page.locator('.session-timeline-panel')).toBeVisible();
  const overflow = await page.locator('body').evaluate(body => body.scrollWidth > body.clientWidth);
  expect(overflow).toBe(false);
  await page.screenshot({ path: 'test-results/timeline-quiet-gap-1366x768.png', fullPage: true });
});
