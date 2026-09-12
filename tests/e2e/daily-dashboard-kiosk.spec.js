const { test, expect } = require('@playwright/test');

// Kiosk điều hành -- những bảo đảm VẬN HÀNH của một màn hình treo tường.
//
// File này cố ý KHÔNG kiểm lại phần đã có ở kiosk-po-focus.spec.js (cô lập PO,
// phân trang, transition, dòng hoạt động, mật độ). Nó giữ bốn thứ mà một màn
// hình không ai đứng canh phải làm đúng, và bốn thứ đó không đổi khi màn hình
// chuyển sang chế độ một-PO:
//
//   1. deep-link: date + po_id sống qua refresh và Back/Forward;
//   2. tự làm mới TẠI CHỖ -- không reload trang, không nhấp nháy, không mất layout;
//   3. API hỏng thì GIỮ NGUYÊN số liệu tốt cuối cùng và nói rõ là mất kết nối
//      -- một màn điều hành trắng xoá tệ hơn một màn hơi cũ;
//   4. không có dữ liệu thì từng panel có empty state đọc được, không phải ô trống.
//
// (Bản trước của file này kiểm màn hình toàn-xưởng. Màn hình đó đã được thay
// bằng chế độ một-PO theo REQ-KIOSK-010; các bài ở đây là bản chuyển tiếp của
// chính những ý định cũ sang thiết kế mới, không phải bài mới.)

const PO = { id: 77, code: 'PO-KIOSK-77', product: 'Khung inox', status: 'IN_PROGRESS', planned_quantity: 400 };

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

function tasks(n, withNg = true) {
  return Array.from({ length: n }, (_, i) => ({
    po_id: PO.id, po_code: PO.code,
    operation_id: 500 + i, operation_code: `OP-${String(i + 1).padStart(2, '0')}`,
    operation_name: `Công đoạn ${i + 1}`, operation_status: 'IN_PROGRESS',
    day_state: 'RUNNING', open_session_count: 1,
    planned_quantity: 400, total_good_qty: 100 + i, day_good_qty: 20 + i,
    day_defect_qty: withNg && i === 0 ? 9 : 0, day_rework_qty: 0,
    unconfirmed_count: withNg && i === 1 ? 2 : 0,
    active_workers: [{ employee_id: i + 1, name: `Thợ ${i + 1}` }],
  }));
}

function sessions(count) {
  const base = new Date(); base.setHours(9, 0, 0, 0);
  return Array.from({ length: count }, (_, i) => ({
    id: i + 1, po_id: PO.id, status: 'CLOSED',
    started_at: new Date(base.getTime() + i * 3600000).toISOString(),
    ended_at: new Date(base.getTime() + i * 3600000 + 1800000).toISOString(),
    good_qty: 10 + i, defect_qty: i === 0 ? 3 : 0,
    employee_name: `Thợ ${i + 1}`, operation_code: `OP-0${i + 1}`,
  }));
}

/** Mock cả hai endpoint kiosk; trả handle để test đổi dữ liệu/ép lỗi giữa chừng. */
async function mockKiosk(page, { taskCount = 6, sessionCount = 4, date = hcmDate() } = {}) {
  const state = { tasks: tasks(taskCount), sessions: sessions(sessionCount), fail: false, calls: 0 };
  await page.route('**/api/kiosk-board?*', route => {
    state.calls += 1;
    if (state.fail) return route.fulfill({ status: 500, json: { ok: false, detail: 'sập' } });
    route.fulfill({
      json: {
        ok: true, date, context: { date },
        production_order: PO,
        po_options: [{ ...PO, open_sessions: 2, operation_count: state.tasks.length }],
        kpis: {
          day_good_qty: 180, day_defect_qty: 9, day_rework_qty: 1,
          open_session_count: 2, active_worker_count: 2,
          operation_count: state.tasks.length, planned_quantity: 400,
        },
        tasks: state.tasks, sessions: state.sessions,
      },
    });
  });
  await page.route('**/api/kiosk-board/activity?*', route => route.fulfill({
    json: { ok: true, po_id: PO.id, events: [], other_events: [], latest_id: 1 },
  }));
  return state;
}

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
}

async function openKiosk(page, date) {
  await page.goto(`/app?page=daily-dashboard-kiosk&date=${date}&po_id=${PO.id}`);
  await expect(page.locator('#kioskRoot')).toBeVisible();
}

test.describe('Kiosk điều hành', () => {
  test('deep-link giữ đúng date + PO qua refresh và Back/Forward', async ({ page }) => {
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const date = hcmDate();
    await mockKiosk(page, { date });
    await login(page);

    await openKiosk(page, date);
    await expect(page).toHaveURL(new RegExp('page=daily-dashboard-kiosk'));
    await expect(page).toHaveURL(new RegExp(`date=${date}`));
    await expect(page).toHaveURL(new RegExp(`po_id=${PO.id}`));
    await expect(page.locator('#kioskPoCode')).toHaveText(PO.code);

    await page.reload();
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page).toHaveURL(new RegExp(`date=${date}`));
    await expect(page.locator('#kioskPoCode')).toHaveText(PO.code);
    await expect(page.locator('#kioskKpis .kiosk-kpi').first()).toBeVisible();

    await page.goto('/app?page=dashboard');
    await page.goBack();
    await expect(page.locator('#kioskRoot')).toBeVisible();
    await expect(page.locator('#kioskPoCode')).toHaveText(PO.code);

    expect(errors).toEqual([]);
  });

  test('tự làm mới TẠI CHỖ: không reload, không mất layout', async ({ page }) => {
    const date = hcmDate();
    const state = await mockKiosk(page, { date });
    await login(page);
    await openKiosk(page, date);
    await expect(page.locator('.kiosk-task').first()).toBeVisible();

    // Đánh dấu DOM: nếu trang bị reload thì dấu này biến mất.
    await page.evaluate(() => { document.getElementById('kioskRoot').dataset.mark = 'x'; });
    const before = state.calls;

    state.tasks[0].day_good_qty = 999;
    await page.evaluate(() => window.__kioskReload && window.__kioskReload());
    await expect.poll(() => state.calls).toBeGreaterThan(before);

    await expect(page.locator('#kioskRoot')).toHaveAttribute('data-mark', 'x');
    await expect(page.locator('#kioskKpis .kiosk-kpi').first()).toBeVisible();
    await expect(page.locator('.kiosk-task').first()).toBeVisible();
  });

  // Bug P0 (2026-09-12): quét ở kiosk xong, máy báo "Đã bắt đầu", session OPEN có
  // thật trong DB -- mà bảng task không đổi. Phần server đã khoá ở
  // tests/integration/test_kiosk_scan_to_board_contract.py. Bài này giữ phần màn
  // hình: task mới phải lên MÀN trong đúng nhịp làm mới của nó, không đòi ai bấm
  // F5. Một màn hình treo tường không có ai đứng cạnh để bấm.
  test('task vừa được start lên màn trong nhịp làm mới, không cần reload', async ({ page }) => {
    const date = hcmDate();
    const state = await mockKiosk(page, { date, taskCount: 3 });
    await login(page);
    await openKiosk(page, date);
    await expect(page.locator('.kiosk-task')).toHaveCount(3);

    // Dấu trên DOM: còn đây nghĩa là trang KHÔNG hề tải lại.
    await page.evaluate(() => { document.getElementById('kioskRoot').dataset.mark = 'live'; });

    // Ca chuẩn bị máy vừa được quét ở xưởng -- OP phụ, đúng loại từng bị giấu.
    state.tasks.push({
      po_id: PO.id, po_code: PO.code,
      operation_id: 901, operation_code: 'OP-SETUP-01',
      operation_name: 'Chuẩn bị máy CNC', operation_type: 'SETUP',
      operation_status: 'IN_PROGRESS', day_state: 'RUNNING', open_session_count: 1,
      planned_quantity: 400, total_good_qty: 0, day_good_qty: 0,
      day_defect_qty: 0, day_rework_qty: 0, unconfirmed_count: 0,
      active_workers: [{ employee_id: 91, name: 'Thợ Chuẩn Bị' }],
    });

    // Hai nhịp của CHÍNH màn hình này, đúng thứ tự timer gọi chúng: nạp dữ liệu
    // (BOARD_MS) rồi tới ranh giới trang (PAGE_MS). Dữ liệu mới CỐ Ý chỉ có hiệu
    // lực ở ranh giới trang -- REQ-KIOSK-010 "Trang ổn định": không sắp xếp lại
    // danh sách dưới mắt người đang đọc. Bài này kiểm task mới tới nơi mà KHÔNG
    // ai phải bấm gì, chứ không đòi nó chen ngang giữa một trang đang đọc.
    await page.evaluate(() => window.__kioskReload());
    await page.evaluate(() => window.__kioskAdvance());
    await expect(page.locator('.kiosk-task')).toHaveCount(4);

    const row = page.locator('.kiosk-task[data-op="901"]');
    await expect(row).toBeVisible();
    await expect(row.locator('.kiosk-task-main b')).toHaveText('Chuẩn bị máy CNC');
    await expect(row.locator('.kiosk-state')).toHaveText('Đang chạy');
    await expect(row.locator('.kiosk-task-people')).toContainText('Thợ Chuẩn Bị');

    // Không reload, và người xem không bị kéo ra khỏi màn đang đọc.
    await expect(page.locator('#kioskRoot')).toHaveAttribute('data-mark', 'live');
  });

  // OP phụ ghi nhận CÔNG chứ không ghi nhận sản lượng, nên nó KHÔNG có chỉ tiêu.
  // Vẽ nó bằng đúng ô "Đạt / Kế hoạch" của OP sản xuất là dựng một con số sai
  // trên màn hình treo tường: "0 / 400" đọc ra như một công đoạn đang tụt tiến độ.
  test('task hỗ trợ nói đúng loại việc, không mượn ô sản lượng của OP sản xuất', async ({ page }) => {
    const date = hcmDate();
    const state = await mockKiosk(page, { date, taskCount: 1 });
    state.tasks.push({
      po_id: PO.id, po_code: PO.code,
      operation_id: 902, operation_code: 'OP-SETUP-02',
      operation_name: 'Chuẩn bị máy', operation_type: 'SETUP',
      operation_status: 'IN_PROGRESS', day_state: 'RUNNING', open_session_count: 1,
      planned_quantity: 400, total_good_qty: 0, day_good_qty: 0,
      day_defect_qty: 0, day_rework_qty: 0, unconfirmed_count: 0,
      active_workers: [{ employee_id: 92, name: 'Thợ Chuẩn Bị' }],
    });
    await login(page);
    await openKiosk(page, date);

    const support = page.locator('.kiosk-task[data-op="902"]');
    await expect(support).toBeVisible();
    await expect(support.locator('.kiosk-task-kind')).toHaveText('Chuẩn bị máy');
    // Không "0 / 400", và không thanh tiến độ trên một việc không có tiến độ.
    await expect(support).not.toContainText('/ 400');
    await expect(support.locator('.kiosk-meter')).toHaveCount(0);

    // OP sản xuất bên cạnh KHÔNG đổi: vẫn đủ số và thanh tiến độ.
    const production = page.locator('.kiosk-task[data-op="500"]');
    await expect(production.locator('.kiosk-task-qty b')).toBeVisible();
    await expect(production.locator('.kiosk-meter')).toHaveCount(1);
  });

  test('API hỏng thì giữ số liệu cũ và báo mất kết nối', async ({ page }) => {
    const date = hcmDate();
    const state = await mockKiosk(page, { date });
    await login(page);
    await openKiosk(page, date);
    await expect(page.locator('.kiosk-task').first()).toBeVisible();
    const rowsBefore = await page.locator('.kiosk-task').count();

    state.fail = true;
    await page.evaluate(() => window.__kioskReload && window.__kioskReload());

    await expect(page.locator('#kioskLive')).toHaveAttribute('data-state', 'stale');
    await expect(page.locator('#kioskLiveText')).toContainText('Mất kết nối');
    // Số liệu cũ vẫn đứng nguyên -- đây là điểm chính của bài test.
    await expect(page.locator('.kiosk-task')).toHaveCount(rowsBefore);
    await expect(page.locator('#kioskKpis .kiosk-kpi').first()).toBeVisible();
  });

  test('không có dữ liệu thì mỗi panel có empty state đọc được', async ({ page }) => {
    const date = hcmDate();
    await page.setViewportSize({ width: 1920, height: 1080 });
    await mockKiosk(page, { taskCount: 0, sessionCount: 0, date });
    await login(page);
    await openKiosk(page, date);

    await expect(page.locator('#kioskTasks')).toContainText('không còn task đang chạy');
    await expect(page.locator('#kioskHourly')).toContainText('Chưa có sản lượng ghi nhận');
    await expect(page.locator('#kioskAttention')).toContainText('Không có điểm cần xử lý');
    await expect(page.locator('#kioskAttentionCount')).toHaveText('Sạch');
    await expect(page.locator('#kioskFeed')).toContainText('Chưa có hoạt động');
  });

  test('panel phụ vẫn là của PO đang xem: NG và session chưa xác nhận lên cảnh báo', async ({ page }) => {
    const date = hcmDate();
    await page.setViewportSize({ width: 1920, height: 1080 });
    await mockKiosk(page, { date });
    await login(page);
    await openKiosk(page, date);

    await expect(page.locator('#kioskAttention')).toContainText('Session chưa xác nhận');
    await expect(page.locator('#kioskAttention')).toContainText('Tỉ lệ NG cao');
    await expect(page.locator('#kioskAttentionFoot')).toContainText('chưa có nguồn dữ liệu');
    await expect(page.locator('#kioskChartNote')).toContainText('SP đạt trong ngày');
  });
});
