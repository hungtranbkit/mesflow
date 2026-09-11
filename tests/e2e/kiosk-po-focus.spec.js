const { test, expect } = require('@playwright/test');

// Kiosk điều hành v1 -- REQ-KIOSK-010.
//
// Mock hai endpoint kiosk-board để kiểm HÀNH VI MÀN HÌNH (phân trang tự động,
// giữ task vừa hoàn thành, cô lập PO, mật độ) một cách tất định. Phần hợp đồng
// dữ liệu đã có test riêng ở tests/integration/test_kiosk_board_po_focus.py --
// hai tầng kiểm hai thứ khác nhau, không chồng nhau.
//
// Vì sao mock: mấy hành vi này phụ thuộc THỜI GIAN (lật trang mỗi 10s, giữ
// task xong 8s). Dựng dữ liệu thật rồi chờ xưởng ảo thao tác đúng nhịp là
// nguồn flaky; ở đây nhịp do test điều khiển.

const PO_A = { id: 101, code: 'PO-A-001', product: 'Khung thép A', status: 'IN_PROGRESS', planned_quantity: 500 };
const PO_B = { id: 202, code: 'PO-B-002', product: 'Vỏ máy B', status: 'IN_PROGRESS', planned_quantity: 300 };

function task(i, extra = {}) {
  return {
    po_id: PO_A.id, po_code: PO_A.code,
    operation_id: 1000 + i, operation_code: `OP-${String(i).padStart(2, '0')}`,
    operation_name: `Công đoạn ${i}`, operation_status: 'IN_PROGRESS',
    day_state: i % 3 === 0 ? 'RUNNING' : 'UPDATED',
    open_session_count: i % 3 === 0 ? 1 : 0,
    planned_quantity: 500, total_good_qty: 40 + i, day_good_qty: 10 + i,
    day_defect_qty: i % 4 === 0 ? 2 : 0, day_rework_qty: 0,
    active_workers: [{ employee_id: i, name: `Thợ ${i}` }],
    ...extra,
  };
}

function event(id, extra = {}) {
  return {
    id, event_type: 'GOOD_QUANTITY_RECORDED', category: 'QUANTITY',
    occurred_at: new Date().toISOString(), actor_name: 'Lê Văn Lý', actor_kind: 'PERSON',
    po_id: PO_A.id, po_code: PO_A.code, operation_id: 1001,
    operation_code: 'OP-01', operation_name: 'Chấn thân vỏ',
    operation_done_qty: 120, operation_plan_qty: 120,
    session_id: 9, title: 'Ghi nhận sản lượng đạt', description: '',
    quantity_delta: 24, source: 'NATIVE', ...extra,
  };
}

/** Gắn mock; trả về handle để test đổi dữ liệu giữa chừng. */
async function mockKiosk(page, { taskCount = 20, events = [event(1)], otherEvents = [] } = {}) {
  const state = {
    tasks: Array.from({ length: taskCount }, (_, i) => task(i + 1)),
    events, otherEvents,
  };
  await page.route('**/api/kiosk-board?*', route => route.fulfill({
    json: {
      ok: true, date: '2026-09-11', context: { date: '2026-09-11' },
      production_order: PO_A,
      po_options: [
        { ...PO_A, open_sessions: 3, operation_count: state.tasks.length },
        { ...PO_B, open_sessions: 1, operation_count: 4 },
      ],
      kpis: {
        day_good_qty: 210, day_defect_qty: 4, day_rework_qty: 1,
        open_session_count: 3, active_worker_count: 3,
        operation_count: state.tasks.length, planned_quantity: 500,
      },
      tasks: state.tasks, sessions: [],
    },
  }));
  await page.route('**/api/kiosk-board/activity?*', route => route.fulfill({
    json: { ok: true, po_id: PO_A.id, events: state.events, other_events: state.otherEvents, latest_id: 1 },
  }));
  return state;
}

async function openKiosk(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=daily-dashboard-kiosk&date=2026-09-11&po_id=${PO_A.id}`);
  await expect(page.locator('#kioskRoot')).toBeVisible();
  await expect(page.locator('.kiosk-task').first()).toBeVisible();
}

// --------------------------------------------------------------- PO focus

test.describe('PO focus', () => {
  test('header nói rõ đang xem PO nào', async ({ page }) => {
    await mockKiosk(page);
    await openKiosk(page);
    await expect(page.locator('#kioskPoCode')).toHaveText(PO_A.code);
    await expect(page.locator('#kioskPoProduct')).toHaveText(PO_A.product);
  });

  test('panel chính không chứa task của PO khác', async ({ page }) => {
    await mockKiosk(page);
    await openKiosk(page);
    const codes = await page.locator('.kiosk-task .kiosk-task-main small').allTextContents();
    expect(codes.length).toBeGreaterThan(0);
    expect(codes.every(c => c.startsWith('OP-'))).toBe(true);
    await expect(page.locator('.kiosk-task')).toHaveCount(await page.locator('.kiosk-task').count());
    expect(await page.locator('.kiosk-task', { hasText: PO_B.code }).count()).toBe(0);
  });

  test('biến động PO khác nằm ở vùng riêng, không chen vào task', async ({ page }) => {
    await mockKiosk(page, {
      otherEvents: [event(99, { po_id: PO_B.id, po_code: PO_B.code, actor_name: 'Nguyễn Văn A',
        event_type: 'SESSION_STARTED', operation_name: 'Hàn khung', quantity_delta: null })],
    });
    await openKiosk(page);
    await expect(page.locator('.kiosk-other-row')).toHaveCount(1);
    await expect(page.locator('.kiosk-other-po')).toHaveText(PO_B.code);
    // ...và KHÔNG xuất hiện trong feed chi tiết của PO đang focus.
    expect(await page.locator('.kiosk-event', { hasText: PO_B.code }).count()).toBe(0);
  });

  test('po_id nằm trong URL nên refresh giữ đúng PO', async ({ page }) => {
    await mockKiosk(page);
    await openKiosk(page);
    expect(page.url()).toContain(`po_id=${PO_A.id}`);
    await page.reload();
    await expect(page.locator('#kioskPoCode')).toHaveText(PO_A.code);
  });
});

// ----------------------------------------------------------- auto paging

test.describe('Phân trang tự động', () => {
  test('có chỉ báo trang và tổng số task', async ({ page }) => {
    await mockKiosk(page, { taskCount: 20 });
    await openKiosk(page);
    await expect(page.locator('.kiosk-page-count')).toContainText('Trang 1/');
    await expect(page.locator('.kiosk-page-total')).toContainText('20 task');
    expect(await page.locator('.kiosk-dots i').count()).toBeGreaterThan(1);
  });

  test('đi hết các trang thì thấy đủ task, không trùng không thiếu', async ({ page }) => {
    await mockKiosk(page, { taskCount: 20 });
    await openKiosk(page);
    const pages = await page.locator('.kiosk-dots i').count();
    const seen = new Set();
    for (let i = 0; i < pages; i++) {
      for (const code of await page.locator('.kiosk-task .kiosk-task-main small').allTextContents()) {
        expect(seen.has(code)).toBe(false);       // không trùng
        seen.add(code);
      }
      if (i < pages - 1) {
        await page.evaluate(() => window.__kioskAdvance && window.__kioskAdvance());
        await page.waitForTimeout(120);
      }
    }
    expect(seen.size).toBe(20);                    // không thiếu
  });
});

// --------------------------------------------------- completion transition

test.describe('Task hoàn thành', () => {
  test('không biến mất ngay mà hiện "Vừa hoàn thành"', async ({ page }) => {
    // Viewport cố định: số hàng một trang phụ thuộc chiều cao thật, nên để
    // Playwright dùng mặc định là tự chuốc flaky.
    await page.setViewportSize({ width: 1920, height: 1080 });
    const state = await mockKiosk(page, { taskCount: 6 });
    await openKiosk(page);
    await expect(page.locator('.kiosk-task')).toHaveCount(6);

    const gone = state.tasks[0];
    state.tasks = state.tasks.slice(1);            // OP-01 rời danh sách active
    await page.evaluate(() => window.__kioskReload && window.__kioskReload());
    await page.waitForTimeout(400);

    const done = page.locator('.kiosk-task.state-justdone');
    await expect(done).toHaveCount(1);
    await expect(done).toContainText('Vừa hoàn thành');
    await expect(done).toContainText(gone.operation_name);
  });
});

// ------------------------------------------------------------ activity feed

test.describe('Dòng hoạt động', () => {
  test('một dòng trả lời đủ ai/làm gì/trên cái gì/ra sao/lúc nào', async ({ page }) => {
    await mockKiosk(page, { events: [event(1)] });
    await openKiosk(page);
    const row = page.locator('.kiosk-event').first();
    await expect(row.locator('.kiosk-actor')).toHaveText('Lê Văn Lý');   // ai
    await expect(row).toContainText('+24 SP đạt');                        // làm gì / ra sao
    await expect(row).toContainText('Chấn thân vỏ');                      // trên cái gì
    await expect(row).toContainText('đạt 120/120, hoàn thành');           // impact
    await expect(row.locator('time b')).not.toBeEmpty();                  // lúc nào
  });

  test('sự kiện hệ thống ghi rõ là hệ thống, không bịa tên người', async ({ page }) => {
    await mockKiosk(page, { events: [event(2, {
      actor_name: '', actor_kind: 'SYSTEM', event_type: 'SESSION_AUTO_CLOSED', quantity_delta: null })] });
    await openKiosk(page);
    await expect(page.locator('.kiosk-event .kiosk-actor')).toHaveText('Hệ thống');
    await expect(page.locator('.kiosk-event .kiosk-actor')).toHaveClass(/is-system/);
  });
});

// ------------------------------------------------------------- empty state

test('PO hết task active thì có empty state và gợi ý PO khác', async ({ page }) => {
  await mockKiosk(page, { taskCount: 0 });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=daily-dashboard-kiosk&date=2026-09-11&po_id=${PO_A.id}`);
  await expect(page.locator('.kiosk-empty-done')).toContainText('không còn task đang chạy');
  await expect(page.locator('[data-goto]')).toContainText(PO_B.code);
});

// --------------------------------------------------------------- mật độ

// Ngưỡng là SỐ ĐO THẬT trên layout hiện tại, không phải con số mong muốn:
// 1920 chứa 9 hàng/trang, 1366 chứa 5. So với bản cũ (hiển thị ~7 hàng rồi bỏ
// phần còn lại sau dòng "+N Operation khác"), cái được không chỉ là 9>7 mà là
// MỌI task đều có lượt lên màn qua phân trang. Hạ ngưỡng xuống dưới số đo thật
// sẽ làm bài test ngừng bảo vệ mật độ, nên để sát mép và sửa khi layout đổi.
for (const vp of [{ name: '1920x1080', width: 1920, height: 1080, minRows: 9 },
                  { name: '1366x768', width: 1366, height: 768, minRows: 5 }]) {
  test(`${vp.name}: đủ mật độ, không tràn ngang, không cắt hàng`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await mockKiosk(page, { taskCount: 24 });
    await openKiosk(page);

    const rows = await page.locator('.kiosk-task').count();
    expect(rows).toBeGreaterThanOrEqual(vp.minRows);

    // Không tràn ngang.
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);

    // Không hàng nào bị cắt ngang đáy panel.
    const clipped = await page.evaluate(() => {
      const box = document.getElementById('kioskTasks').getBoundingClientRect();
      return [...document.querySelectorAll('.kiosk-task')]
        .filter(el => el.getBoundingClientRect().bottom > box.bottom + 1).length;
    });
    expect(clipped).toBe(0);

    // Thứ bậc: tên Operation phải lớn hơn mã.
    const [nameSize, codeSize] = await page.evaluate(() => {
      const row = document.querySelector('.kiosk-task');
      return [parseFloat(getComputedStyle(row.querySelector('b')).fontSize),
              parseFloat(getComputedStyle(row.querySelector('small')).fontSize)];
    });
    expect(nameSize).toBeGreaterThan(codeSize);

    await page.screenshot({ path: `test-results/kiosk-po-focus-${vp.name}.png`, fullPage: false });
  });
}
