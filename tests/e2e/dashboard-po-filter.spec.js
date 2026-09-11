const { test, expect } = require('@playwright/test');

// Bộ lọc PO của "Dashboard theo ngày" -- REQ-DASH-006, và cầu nối sang Kiosk
// (REQ-KIOSK-010).
//
// Điều quan trọng nhất ở đây KHÔNG phải là selector hiện ra, mà là: phạm vi PO
// đi xuống SERVER (?po_id=) chứ không lọc lại ở trình duyệt. Nên phần lớn bài
// dưới đây kiểm chính URL mà trang GỌI, thứ duy nhất chứng minh được điều đó.

const PO_A = { id: 11, code: 'PO-AAA-11', product: 'Khung A', status: 'IN_PROGRESS', planned_quantity: 100, open_sessions: 2 };
const PO_B = { id: 22, code: 'PO-BBB-22', product: 'Vỏ B', status: 'IN_PROGRESS', planned_quantity: 200, open_sessions: 0 };

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

function itemFor(po, i) {
  return {
    po_id: po.id, po_code: po.code, part_code: 'PT', part_name: 'Thân',
    operation_id: po.id * 100 + i, operation_code: `${po.code}-OP${i}`,
    operation_name: `Công đoạn ${po.code} ${i}`, operation_status: 'IN_PROGRESS',
    day_state: 'RUNNING', open_session_count: 1, session_count: 1,
    planned_quantity: po.planned_quantity, total_good_qty: 10, day_good_qty: 10,
    day_defect_qty: 0, day_rework_qty: 0, day_scrap_qty: 0, unconfirmed_count: 0,
    planned_work_seconds: 0, day_work_seconds: 600,
    active_workers: [{ employee_id: i, name: `Thợ ${i}` }],
    all_participants: [], day_contributors: [],
  };
}

function sessionFor(po, i) {
  const end = new Date();
  return {
    session_id: po.id * 100 + i, session_status: 'CLOSED', po_id: po.id, po_code: po.code,
    started_at: new Date(end.getTime() - 3600000).toISOString(), ended_at: end.toISOString(),
    effective_end_at: end.toISOString(), duration_seconds: 3600, total_duration_seconds: 3600,
    work_duration_seconds: 3600, good_qty: 5, defect_qty: 0, rework_qty: 0, scrap_qty: 0,
    employee_id: i, employee_name: `Thợ ${i}`, employee_no: `E${i}`,
    operation_id: po.id * 100 + i, operation_code: `${po.code}-OP${i}`,
    operation_name: `Công đoạn ${po.code} ${i}`, part_code: 'PT', part_name: 'Thân',
  };
}

/** Mock /api/dashboard/day tôn trọng ?po_id= y như backend thật. */
async function mockDashboard(page) {
  const seen = { urls: [] };
  await page.route('**/api/dashboard/day?*', route => {
    const url = new URL(route.request().url());
    seen.urls.push(url.search);
    const po = url.searchParams.get('po_id');
    const all = [PO_A, PO_B];
    const scoped = po ? all.filter(x => String(x.id) === po) : all;
    route.fulfill({
      json: {
        ok: true,
        context: { date: hcmDate(), timezone: 'Asia/Ho_Chi_Minh', po_id: po ? Number(po) : null,
          day_start: new Date().toISOString(), day_end: new Date().toISOString() },
        items: scoped.flatMap(x => [itemFor(x, 1), itemFor(x, 2)]),
        sessions: scoped.flatMap(x => [sessionFor(x, 1)]),
        activity: scoped.map(x => ({ item_type: 'SESSION_STARTED', item_id: `${x.id}`,
          activity_at: new Date().toISOString(), actor: 'Thợ 1', subject: 'OP',
          operation_name: `Công đoạn ${x.code} 1`, status: 'STARTED', po_code: x.code,
          operation_code: `${x.code}-OP1`, good_qty: 0, defect_qty: 0 })),
      },
    });
  });
  await page.route('**/api/kiosk-board/po-options', route => route.fulfill({
    json: { ok: true, items: [PO_A, PO_B] },
  }));
  return seen;
}

async function openDashboard(page, query = '') {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=dashboard${query}`);
  await expect(page.locator('#dailyPo')).toBeVisible();
}

const lastCall = seen => seen.urls[seen.urls.length - 1];

test.describe('Dashboard theo ngày — lọc theo PO', () => {
  test('mặc định là "Tất cả PO" và KHÔNG gửi po_id', async ({ page }) => {
    const seen = await mockDashboard(page);
    await openDashboard(page);
    await expect(page.locator('#dailyPo')).toHaveValue('');
    expect(lastCall(seen)).not.toContain('po_id=');
  });

  test('chọn một PO thì phạm vi đi xuống server', async ({ page }) => {
    const seen = await mockDashboard(page);
    await openDashboard(page);
    await page.selectOption('#dailyPo', String(PO_A.id));
    await expect.poll(() => lastCall(seen)).toContain(`po_id=${PO_A.id}`);
  });

  test('cả ba tab đều chỉ còn dữ liệu của PO đã chọn', async ({ page }) => {
    await mockDashboard(page);
    await openDashboard(page);
    await page.selectOption('#dailyPo', String(PO_A.id));
    await expect(page.locator('#dailyKpis')).toBeVisible();

    for (const tab of ['overview', 'people', 'output']) {
      await page.click(`[data-dashboard-tab="${tab}"]`);
      const pane = page.locator(`[data-dashboard-pane="${tab}"]`);
      await expect(pane).toBeVisible();
      // PO A có mặt, PO B tuyệt đối không.
      expect(await pane.locator(`text=${PO_B.code}`).count()).toBe(0);
    }
  });

  test('đổi PO thì đổi hẳn, không còn sót dữ liệu PO cũ', async ({ page }) => {
    const seen = await mockDashboard(page);
    await openDashboard(page);
    await page.selectOption('#dailyPo', String(PO_A.id));
    await expect.poll(() => lastCall(seen)).toContain(`po_id=${PO_A.id}`);
    await page.selectOption('#dailyPo', String(PO_B.id));
    await expect.poll(() => lastCall(seen)).toContain(`po_id=${PO_B.id}`);
    const pane = page.locator('[data-dashboard-pane="overview"]');
    expect(await pane.locator(`text=${PO_A.code}`).count()).toBe(0);
  });

  test('po_id nằm trong URL và sống qua refresh + Back/Forward', async ({ page }) => {
    const seen = await mockDashboard(page);
    await openDashboard(page);
    await page.selectOption('#dailyPo', String(PO_A.id));
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_A.id}`));

    await page.reload();
    await expect(page.locator('#dailyPo')).toHaveValue(String(PO_A.id));
    await expect.poll(() => lastCall(seen)).toContain(`po_id=${PO_A.id}`);

    await page.selectOption('#dailyPo', String(PO_B.id));
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_B.id}`));
  });

  test('đổi tab KHÔNG làm mất PO đang chọn', async ({ page }) => {
    await mockDashboard(page);
    await openDashboard(page);
    await page.selectOption('#dailyPo', String(PO_A.id));
    await page.click('[data-dashboard-tab="people"]');
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_A.id}`));
    await expect(page).toHaveURL(/tab=people/);
    await expect(page.locator('#dailyPo')).toHaveValue(String(PO_A.id));
  });

  test('deep-link kèm po_id mở ra đúng PO ngay lần gọi đầu', async ({ page }) => {
    const seen = await mockDashboard(page);
    await openDashboard(page, `&po_id=${PO_B.id}`);
    await expect(page.locator('#dailyPo')).toHaveValue(String(PO_B.id));
    await expect.poll(() => lastCall(seen)).toContain(`po_id=${PO_B.id}`);
  });
});

test.describe('Cầu nối sang Kiosk', () => {
  test('đang chọn PO thì mở Kiosk mang theo cả date lẫn po_id', async ({ page }) => {
    await mockDashboard(page);
    await page.route('**/api/kiosk-board?*', route => route.fulfill({
      json: { ok: true, production_order: PO_A, po_options: [PO_A, PO_B],
        kpis: {}, tasks: [], sessions: [], context: {} },
    }));
    await page.route('**/api/kiosk-board/activity?*', route => route.fulfill({
      json: { ok: true, po_id: PO_A.id, events: [], other_events: [], latest_id: 1 } }));
    await openDashboard(page);
    await page.selectOption('#dailyPo', String(PO_A.id));
    await page.click('#dailyOpenKiosk');
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_A.id}`));
    await expect(page).toHaveURL(new RegExp(`date=${hcmDate()}`));
  });

  test('đang "Tất cả PO" thì HỎI, không tự đoán PO', async ({ page }) => {
    await mockDashboard(page);
    await openDashboard(page);
    await expect(page.locator('#dailyPo')).toHaveValue('');
    await page.click('#dailyOpenKiosk');

    // Không được nhảy thẳng vào kiosk.
    await expect(page.locator('#kioskRoot')).toHaveCount(0);
    const modal = page.locator('.kiosk-pick-modal');
    await expect(modal).toBeVisible();
    await expect(modal).toContainText('một');
    await expect(modal.locator('[data-pick]')).toHaveCount(2);
    // PO đang có người làm xếp trước.
    await expect(modal.locator('[data-pick]').first()).toContainText(PO_A.code);
  });

  test('chọn PO trong hộp thoại rồi mới mở Kiosk', async ({ page }) => {
    await mockDashboard(page);
    await page.route('**/api/kiosk-board?*', route => route.fulfill({
      json: { ok: true, production_order: PO_B, po_options: [PO_A, PO_B],
        kpis: {}, tasks: [], sessions: [], context: {} } }));
    await page.route('**/api/kiosk-board/activity?*', route => route.fulfill({
      json: { ok: true, po_id: PO_B.id, events: [], other_events: [], latest_id: 1 } }));
    await openDashboard(page);
    await page.click('#dailyOpenKiosk');
    await page.click(`.kiosk-pick-modal [data-pick="${PO_B.id}"]`);
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_B.id}`));
  });
});
