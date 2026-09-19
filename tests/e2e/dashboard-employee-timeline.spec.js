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
  sessions.push({ ...sessions[0], session_id: 100, session_status: 'CLOSED', started_at: at(date, 6, 0), ended_at: at(date, 7, 30) });
  return sessions;
}

function operationsFor() {
  return [{
    operation_id: 1,
    operation_code: 'OP-CAT-LASER-WITH-A-VERY-LONG-CODE-001',
    operation_name: 'Setup CAT LASER / CAT LASER với tên Operation rất dài',
    po_code: 'PO-E2E-WITH-A-VERY-LONG-CODE',
    part_code: 'PART-E2E-WITH-A-VERY-LONG-CODE',
    part_name: 'Chi tiết CAT LASER',
    day_work_seconds: 3000,
    planned_work_seconds: 6000,
    planned_quantity: 200,
    total_good_qty: 0,
    day_good_qty: 0,
    day_defect_qty: 0,
    day_rework_qty: 0,
    session_count: 2,
    open_session_count: 1,
    day_state: 'RUNNING',
    active_workers: [{ employee_id: 1, employee_name: 'Nhân viên có tên rất dài để kiểm tra' }]
  }];
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
    route.fulfill({ json: { ok: true, context: {target_minutes:480,intervals:shifts[0].intervals}, items: operationsFor(), activity: [], sessions } });
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
  await expect(page.locator('.emp-op-item.running')).toHaveCount(21);
  await expect(page.locator('#dailySessionStatus')).toContainText('21 phiên làm việc đang chạy');
  // Full-day visibility preserves the configured lunch gap: one closed
  // segment, plus the open session before and after lunch.
  await expect(page.locator('.employee-day-row').first().locator('.employee-session-segment')).toHaveCount(3);
  await expect(page.locator('.emp-op-toggle').first()).toHaveAttribute('aria-expanded', 'false');
  await page.locator('.emp-op-toggle').first().click();
  await expect(page.locator('.emp-op-toggle').first()).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.emp-op-sessions').first().locator('.emp-op-session')).toHaveCount(2);
  // v71.0.0.235: duration shortened from "X giờ Y phút" to "Xg Yp".
  await expect(page.locator('.emp-op-sessions').first().locator('.emp-op-session.open .emp-op-dur')).toContainText(/\dp\b/);

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
  const nightRow = page.locator('.employee-day-row', { hasText: 'Nhân viên ca tối' });
  await expect(nightRow.locator('.emp-op-item.running')).toHaveCount(1);
  await expect(nightRow).toContainText('OP-NIGHT');
});

test('renderer thời gian xử lý đúng biên dưới bằng và vượt định mức', async ({ page }) => {
  await login(page);
  const cases = await page.evaluate(() => [59, 60, 61].map(elapsedSeconds => {
    const timing = expectedTiming({
      perUnitSeconds: 60, quantity: 1, elapsedSeconds, totalSecondsOverride: 60
    });
    return {
      elapsedSeconds,
      timing,
      html: expectedTimingHtml(timing, { showPerUnit: false })
    };
  }));

  expect(cases[0].timing.overrunSeconds).toBe(0);
  expect(cases[0].html).not.toContain('Vượt dự kiến');
  expect(cases[0].html).not.toContain('Còn lại');

  expect(cases[1].timing.overrunSeconds).toBe(0);
  expect(cases[1].html).toContain('<small>Đã làm</small><b>1 phút</b>');
  expect(cases[1].html).toContain('<small>Tổng thời gian dự kiến</small><b>1 phút</b>');
  expect(cases[1].html).not.toContain('Vượt dự kiến');
  expect(cases[1].html).not.toContain('Còn lại');

  expect(cases[2].timing.overrunSeconds).toBe(1);
  expect(cases[2].html).toContain('<small>Chậm hơn dự kiến</small>');
  expect(cases[2].html).not.toContain('Còn lại');
});

const dashboardViewports = [
  { width: 1920, height: 1080 },
  { width: 1366, height: 768 },
  { width: 414, height: 896 },
  { width: 390, height: 844 },
  { width: 375, height: 812 }
];

for (const viewport of dashboardViewports) {
  test(`timeline không vỡ tại ${viewport.width}x${viewport.height}`, async ({ page }) => {
    const date = hcmDate();
    await page.setViewportSize(viewport);
    await login(page);
    await mockDashboard(page, date);
    await page.evaluate(() => openPage('dashboard'));
    const overview = page.locator('[data-dashboard-pane="overview"]');
    const operationCard = overview.locator('.op-card').first();
    await expect(operationCard).toBeVisible();
    const operationFonts = await operationCard.locator('.op-identity').evaluate(el => ({
      title: getComputedStyle(el.querySelector('.row-title')).fontSize,
      code: getComputedStyle(el.querySelector('.row-code')).fontSize,
      meta: getComputedStyle(el.querySelector('.op-identity-meta')).fontSize
    }));
    const operationLayout = await operationCard.evaluate(card => {
      const rect = element => element.getBoundingClientRect();
      const cardBox = rect(card);
      const headBox = rect(card.querySelector('.op-card-head'));
      const progressBox = rect(card.querySelector('.op-dual-progress'));
      const bodyBox = rect(card.querySelector('.op-card-body'));
      const factBody = card.querySelector('.op-card-fact>b');
      return {
        bodyFont: getComputedStyle(factBody).fontSize,
        cardRight: cardBox.right,
        progressGap: progressBox.top - headBox.bottom,
        progressWidth: progressBox.width,
        bodyWidth: bodyBox.width,
        viewport: document.documentElement.clientWidth,
        rootOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth
      };
    });
    await expect(operationCard).toContainText('Tiến độ thời gian');
    await expect(operationCard).toContainText('Tiến độ sản phẩm');
    await expect(operationCard.locator('.op-identity')).toHaveAttribute('title', /OP-CAT-LASER-WITH-A-VERY-LONG-CODE-001/);
    const shotPrefix = process.env.MF_DASH_SCREENSHOT_PREFIX || 'after';
    await page.screenshot({ path: `test-results/${shotPrefix}-dashboard-operation-${viewport.width}x${viewport.height}.png`, fullPage: true });
    await page.locator('[data-dashboard-tab="people"]').click();
    await expect(page.locator('.session-timeline-panel')).toBeVisible();
    const peopleFonts = await page.locator('.emp-op-item .op-identity').first().evaluate(el => ({
      title: getComputedStyle(el.querySelector('.row-title')).fontSize,
      code: getComputedStyle(el.querySelector('.row-code')).fontSize,
      meta: getComputedStyle(el.querySelector('.op-identity-meta')).fontSize
    }));
    const layout = await page.evaluate(() => {
      const row = document.querySelector('.employee-day-row').getBoundingClientRect();
      const summary = document.querySelector('.employee-day-summary').getBoundingClientRect();
      const scroller = document.querySelector('.employee-day-track-scroll');
      const employee = document.querySelector('.employee-day-person');
      const firstOp = document.querySelector('.emp-op-item');
      return {
        rootOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        rowRight: row.right,
        summaryRight: summary.right,
        viewport: document.documentElement.clientWidth,
        timelineScrollable: scroller.scrollWidth > scroller.clientWidth,
        employeeTitle: getComputedStyle(employee.querySelector('b')).fontSize,
        employeeMeta: getComputedStyle(employee.querySelector('small')).fontSize,
        factBody: getComputedStyle(firstOp.querySelector('.emp-op-facts b')).fontSize
      };
    });
    expect(layout.rootOverflow).toBe(false);
    expect(layout.rowRight).toBeLessThanOrEqual(layout.viewport + 0.5);
    expect(layout.summaryRight).toBeLessThanOrEqual(layout.viewport + 0.5);
    console.log(JSON.stringify({ viewport, operationFonts, peopleFonts, operationLayout, peopleLayout: layout }));
    await page.screenshot({ path: `test-results/${shotPrefix}-dashboard-people-${viewport.width}x${viewport.height}.png`, fullPage: true });
    if (viewport.width <= 820) {
      expect(layout.timelineScrollable).toBe(true);
      if (process.env.MF_DASH_BASELINE_CAPTURE !== '1') {
        expect(operationFonts).toEqual({ title: '16px', code: '12px', meta: '12px' });
        expect(peopleFonts).toEqual(operationFonts);
        expect(operationLayout.bodyFont).toBe('14px');
        expect(layout).toMatchObject({ employeeTitle: '16px', employeeMeta: '12px', factBody: '14px' });
      }
      if (process.env.MF_DASH_BASELINE_CAPTURE !== '1') {
        expect(Math.abs(operationLayout.progressWidth - operationLayout.bodyWidth)).toBeLessThanOrEqual(1);
      }
    } else if (process.env.MF_DASH_BASELINE_CAPTURE !== '1') {
      expect(operationFonts).toEqual({ title: '13px', code: '11px', meta: '11px' });
      expect(peopleFonts).toEqual(operationFonts);
      expect(operationLayout.bodyFont).toBe('14px');
      expect(layout.factBody).toBe('14px');
    }
    if (process.env.MF_DASH_BASELINE_CAPTURE !== '1') expect(operationLayout.progressGap).toBeLessThanOrEqual(16);
    expect(operationLayout.rootOverflow).toBe(false);
    expect(operationLayout.cardRight).toBeLessThanOrEqual(operationLayout.viewport + 0.5);
  });
}

test('session OPEN xuyên trưa dừng cộng công trong 11:30–13:00 rồi tiếp tục', async ({page}) => {
  const date=hcmDate();
  await login(page);
  const intervals=[
    {interval_type:'BREAK',start_minute:0,end_minute:450,sort_order:0},
    {interval_type:'WORK',start_minute:450,end_minute:690,sort_order:1},
    {interval_type:'BREAK',start_minute:690,end_minute:780,sort_order:2,label:'Nghỉ trưa'},
    {interval_type:'WORK',start_minute:780,end_minute:1020,sort_order:3},
    {interval_type:'BREAK',start_minute:1020,end_minute:1440,sort_order:4},
  ];
  await page.route('**/api/dashboard/day?**', route=>route.fulfill({json:{
    ok:true,context:{date,target_minutes:480,intervals},items:[],activity:[],
    sessions:[{...sessionsFor(date)[0],started_at:at(date,11),employee_name:'Thợ kiểm tra nghỉ trưa'}],
  }}));
  await page.clock.setFixedTime(new Date(`${date}T11:30:00+07:00`));
  await page.goto('/app?page=dashboard&tab=people');
  const work=page.locator('.emp-op-facts b').first();
  await expect(work).toHaveText('30p · đang chạy');
  for(const clock of ['12:15','13:00']){
    await page.clock.setFixedTime(new Date(`${date}T${clock}:00+07:00`));
    await page.locator('#dailyRefresh').click();
    await expect(work).toHaveText('30p · đang chạy');
  }
  await page.clock.setFixedTime(new Date(`${date}T13:15:00+07:00`));
  await page.locator('#dailyRefresh').click();
  await expect(work).toHaveText('45p · đang chạy');
  await expect(page.locator('.employee-session-segment')).toHaveCount(2);
});

test('ngày không có giờ làm vẫn hiện session với 0 phút công', async ({page}) => {
  const date=hcmDate();
  await login(page);
  await page.clock.setFixedTime(new Date(`${date}T14:00:00+07:00`));
  await page.route('**/api/dashboard/day?**', route=>route.fulfill({json:{
    ok:true,context:{date,target_minutes:480,intervals:[
      {interval_type:'BREAK',start_minute:0,end_minute:1440,sort_order:0,label:'Ngoài lịch làm việc'}
    ]},items:[],activity:[],sessions:[sessionsFor(date)[0]]
  }}));
  await page.goto('/app?page=dashboard&tab=people');
  await expect(page.locator('.employee-day-row')).toHaveCount(1);
  await expect(page.locator('.emp-op-facts b').first()).toHaveText('0p · đang chạy');
  await expect(page.locator('.employee-session-segment')).toHaveCount(0);
});
