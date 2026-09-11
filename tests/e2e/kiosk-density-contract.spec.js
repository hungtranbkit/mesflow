const { test, expect } = require('@playwright/test');

// Kiosk điều hành -- HỢP ĐỒNG MẬT ĐỘ (REQ-KIOSK-012).
//
// File này không kiểm hành vi (phân trang, cô lập PO, giữ task vừa xong -- đã
// có ở kiosk-po-focus.spec.js) và không kiểm vận hành (deep-link, tự làm mới,
// API hỏng -- đã có ở daily-dashboard-kiosk.spec.js). Nó canh đúng MỘT thứ:
// màn hình treo tường phải CHỨA ĐƯỢC BAO NHIÊU CHUYỂN ĐỘNG CÙNG LÚC.
//
// Vì sao cần một file riêng cho việc đó: mật độ là thứ trôi ngược lại dễ nhất.
// Không ai cố ý làm màn hình thưa đi; nó thưa dần vì mỗi lần sửa một chi tiết
// lại cộng thêm 2px padding, 1px line-height, nửa point font -- và không bài
// test nào trong repo biết đau. Bản trước đo được: 1366 hiện 7 hàng task với
// header cao 127px (hai hàng), panel cảnh báo hiện đúng MỘT dòng và dòng đó bị
// cắt ngang thân, còn panel "Sản lượng theo giờ" chiếm 272px ở 1920 mà không
// vẽ được cột nào.
//
// Nên ở đây có hai loại ngưỡng, và cả hai đều cần thiết:
//   * SÀN mật độ  -- số task/sự kiện thấy được, để không phình lại;
//   * TRẦN kích thước (bước nhảy hàng, chiều cao header+KPI) -- vì "đủ hàng"
//     một mình vẫn có thể đạt được bằng cách bóp chữ xuống mức không đọc nổi
//     từ 3 mét. Nên có thêm SÀN cỡ chữ đi kèm.
//
// Mọi con số dưới đây là SỐ ĐO THẬT của layout hiện tại, chừa một biên nhỏ --
// không phải con số mong muốn. Hạ sàn xuống dưới số đo thật là làm bài test
// ngừng bảo vệ chính thứ nó sinh ra để bảo vệ.

const PO_A = { id: 101, code: 'PO-A-001', product: 'Khung thép A gia công nguội', status: 'IN_PROGRESS', planned_quantity: 500 };
const PO_B = { id: 202, code: 'PO-B-002', product: 'Vỏ máy B', status: 'IN_PROGRESS', planned_quantity: 300 };

// Tên Operation tiếng Việt có dấu, dài ngắn khác nhau -- chuỗi "OP-01" ngắn
// tũn không bao giờ làm tràn một ô, nên nó không kiểm được gì.
const NAMES = ['Cắt phôi thép tấm', 'Chấn thân vỏ', 'Hàn khung đáy', 'Mài ba via mối hàn',
  'Khoan lỗ bắt vít', 'Tẩy dầu - phốt phát', 'Sơn tĩnh điện lớp 1', 'Sấy sơn 180°C',
  'Lắp ray trượt', 'Lắp bản lề cửa', 'Dán gioăng cách âm', 'Kiểm tra kích thước',
  'Đóng gói xốp', 'Dán tem QC', 'Nhập kho thành phẩm', 'Cắt tôn nắp trên',
  'Đột lỗ thông gió', 'Gấp mép nắp', 'Hàn chốt định vị', 'Vệ sinh bề mặt',
  'Kiểm tra ngoại quan', 'Bọc màng PE', 'Xếp pallet', 'Cân đối trọng lượng'];

function task(i) {
  return {
    po_id: PO_A.id, po_code: PO_A.code,
    operation_id: 1000 + i, operation_code: `OP-${String(i).padStart(2, '0')}`,
    operation_name: NAMES[(i - 1) % NAMES.length], operation_status: 'IN_PROGRESS',
    day_state: i % 4 === 0 ? 'NEEDS_REVIEW' : (i % 3 === 0 ? 'RUNNING' : 'UPDATED'),
    open_session_count: i % 3 === 0 ? 1 : 0,
    planned_quantity: 500, total_good_qty: 40 + i * 7, day_good_qty: 10 + i,
    day_defect_qty: i % 4 === 0 ? 12 : 0, day_rework_qty: 0,
    unconfirmed_count: i % 7 === 0 ? 2 : 0,
    active_workers: [{ employee_id: i, name: `Nguyễn Văn ${String.fromCharCode(65 + (i % 26))}` }],
  };
}

function event(id, i) {
  return {
    id,
    event_type: ['GOOD_QUANTITY_RECORDED', 'DEFECT_QUANTITY_RECORDED', 'SESSION_STARTED',
      'OPERATION_COMPLETED', 'SESSION_AUTO_CLOSED'][i % 5],
    category: 'QUANTITY', occurred_at: new Date(Date.now() - i * 65000).toISOString(),
    actor_name: `Trần Thị ${String.fromCharCode(65 + (i % 26))}`,
    actor_kind: i % 5 === 4 ? 'SYSTEM' : 'PERSON',
    po_id: PO_A.id, po_code: PO_A.code, operation_id: 1000 + (i % 12) + 1,
    operation_code: `OP-${String((i % 12) + 1).padStart(2, '0')}`,
    operation_name: NAMES[i % NAMES.length],
    operation_done_qty: 100 + i, operation_plan_qty: 120, session_id: 9,
    title: 'Ghi nhận', description: '', quantity_delta: 24 - i, source: 'NATIVE',
  };
}

function session(i) {
  const base = new Date(); base.setHours(7, 0, 0, 0);
  return {
    id: i, po_id: PO_A.id, status: 'CLOSED',
    started_at: new Date(base.getTime() + i * 3600000).toISOString(),
    ended_at: new Date(base.getTime() + i * 3600000 + 1800000).toISOString(),
    good_qty: 30 + i * 9, defect_qty: i % 3 === 0 ? 4 : 0,
    employee_name: `Thợ ${i}`, operation_code: `OP-0${(i % 9) + 1}`,
  };
}

/** Fixture "ngày bận": đủ task, đủ sự kiện, đủ cảnh báo để mọi panel đầy. */
async function mockBusyDay(page, { taskCount = 24, eventCount = 12 } = {}) {
  await page.route('**/api/kiosk-board?*', route => route.fulfill({
    json: {
      ok: true, date: '2026-09-11', context: { date: '2026-09-11' },
      production_order: PO_A,
      po_options: [{ ...PO_A, open_sessions: 3, operation_count: taskCount },
        { ...PO_B, open_sessions: 1, operation_count: 4 }],
      kpis: {
        day_good_qty: 2103, day_defect_qty: 48, day_rework_qty: 11,
        open_session_count: 8, active_worker_count: 12,
        operation_count: taskCount, planned_quantity: 500,
      },
      tasks: Array.from({ length: taskCount }, (_, i) => task(i + 1)),
      sessions: Array.from({ length: 9 }, (_, i) => session(i + 1)),
    },
  }));
  await page.route('**/api/kiosk-board/activity?*', route => route.fulfill({
    json: {
      ok: true, po_id: PO_A.id,
      events: Array.from({ length: eventCount }, (_, i) => event(i + 1, i)),
      other_events: [{ ...event(90, 2), id: 90, po_id: PO_B.id, po_code: PO_B.code },
        { ...event(91, 3), id: 91, po_id: PO_B.id, po_code: PO_B.code }],
      latest_id: 1,
    },
  }));
}

async function openKiosk(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=daily-dashboard-kiosk&date=2026-09-11&po_id=${PO_A.id}`);
  await expect(page.locator('#kioskRoot')).toBeVisible();
  await expect(page.locator('.kiosk-task').first()).toBeVisible();
}

/** Số phần tử nằm TRỌN trong khung cha -- hàng bị cắt ngang không được tính. */
function countWholeRowsIn(page, boxSel, rowSel) {
  return page.evaluate(([boxSel, rowSel]) => {
    const box = document.querySelector(boxSel);
    if (!box) return { inside: 0, clipped: 0 };
    const b = box.getBoundingClientRect();
    const rows = [...document.querySelectorAll(rowSel)].filter(el => el.getBoundingClientRect().height > 0);
    const clipped = rows.filter(el => {
      const r = el.getBoundingClientRect();
      return r.bottom > b.bottom + 1 || r.top < b.top - 1;
    }).length;
    return { inside: rows.length - clipped, clipped };
  }, [boxSel, rowSel]);
}

// Ngưỡng theo bậc màn hình. `minTasks` là yêu cầu vận hành (1920: 8-10 task
// cùng lúc, 1366: 6-8); số đo thật hiện tại cao hơn sàn, biên đó là chỗ cho
// một lần chỉnh nhỏ mà không phải sửa test.
const TIERS = [
  { name: '1920x1080', width: 1920, height: 1080, minTasks: 10, maxPitch: 56, minName: 15, maxName: 20 },
  { name: '1366x768', width: 1366, height: 768, minTasks: 6, maxPitch: 50, minName: 13.5, maxName: 17 },
];

for (const vp of TIERS) {
  test.describe(`${vp.name}`, () => {
    test.beforeEach(async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await mockBusyDay(page);
      await openKiosk(page);
      await page.waitForTimeout(600);   // để nhịp đo lại số hàng chạy xong
    });

    test('đủ số task nhìn được cùng lúc, không hàng nào bị cắt', async ({ page }) => {
      const { inside, clipped } = await countWholeRowsIn(page, '#kioskTasks', '.kiosk-task');
      expect(clipped).toBe(0);
      expect(inside).toBeGreaterThanOrEqual(vp.minTasks);
      // Ảnh của fixture "ngày bận" -- đây là bản được chép vào docs/screenshots,
      // nên nó phải đến từ đúng fixture mà hợp đồng này đo, không phải một cảnh
      // dựng riêng cho đẹp.
      await page.screenshot({ path: `test-results/kiosk-density-${vp.name}.png`, fullPage: false });
    });

    test('hàng task không phình: bước nhảy có trần, cỡ chữ có sàn', async ({ page }) => {
      const m = await page.evaluate(() => {
        const rows = [...document.querySelectorAll('.kiosk-task')];
        const r0 = rows[0].getBoundingClientRect();
        return {
          pitch: rows[1] ? rows[1].getBoundingClientRect().top - r0.top : r0.height,
          name: parseFloat(getComputedStyle(rows[0].querySelector('.kiosk-task-main b')).fontSize),
          code: parseFloat(getComputedStyle(rows[0].querySelector('.kiosk-task-main small')).fontSize),
        };
      });
      // Trần: chống phình lại.
      expect(m.pitch).toBeLessThanOrEqual(vp.maxPitch);
      // Sàn + trần cỡ chữ: dày hàng bằng cách bóp chữ không tính là mật độ --
      // màn này đọc từ 3-5 mét.
      expect(m.name).toBeGreaterThanOrEqual(vp.minName);
      expect(m.name).toBeLessThanOrEqual(vp.maxName);
      // Thứ bậc giữ nguyên ở mọi bậc màn: TÊN Operation lớn hơn MÃ.
      expect(m.name).toBeGreaterThan(m.code);
    });

    test('header + dải KPI không ăn quá 20% chiều cao màn', async ({ page }) => {
      const share = await page.evaluate(() => {
        const h = document.querySelector('.kiosk-header').getBoundingClientRect();
        const k = document.querySelector('.kiosk-kpis').getBoundingClientRect();
        return (k.bottom - h.top) / innerHeight;
      });
      expect(share).toBeLessThanOrEqual(0.20);
    });

    test('dòng hoạt động hiện 4-6 sự kiện gần nhất, không cắt dở', async ({ page }) => {
      const { inside, clipped } = await countWholeRowsIn(page, '#kioskFeed', '.kiosk-event');
      expect(clipped).toBe(0);
      expect(inside).toBeGreaterThanOrEqual(4);
      // Mỗi dòng phải trả lời đủ ai · làm gì · trên cái gì · lúc nào.
      const first = page.locator('.kiosk-event').first();
      await expect(first.locator('.kiosk-actor')).not.toBeEmpty();
      await expect(first.locator('time b')).not.toBeEmpty();
    });

    test('cảnh báo và biến động PO khác gọn, không cắt dở, không chiếm nửa màn', async ({ page }) => {
      const attn = await countWholeRowsIn(page, '#kioskAttention', '.kiosk-attn');
      expect(attn.clipped).toBe(0);
      expect(attn.inside).toBeGreaterThanOrEqual(2);
      const other = await countWholeRowsIn(page, '#kioskOther', '.kiosk-other-row');
      expect(other.clipped).toBe(0);
      expect(other.inside).toBeGreaterThanOrEqual(1);

      // Fixture có 24 task, nhiều hơn số dòng cảnh báo vẽ ra -> phần dư phải
      // được NÓI RA bằng số, không im lặng biến mất.
      await expect(page.locator('.kiosk-attn-more')).toContainText('điểm cần xử lý khác');
      // Nhãn đếm là TỔNG, không phải số dòng đang vẽ.
      const [badge, drawn] = await page.evaluate(() => [
        document.getElementById('kioskAttentionCount').textContent.trim(),
        document.querySelectorAll('.kiosk-attn').length]);
      expect(Number(badge)).toBeGreaterThan(drawn);

      const share = await page.evaluate(() => {
        const a = document.querySelector('.kiosk-attention-panel').getBoundingClientRect();
        const o = document.querySelector('.kiosk-other-panel').getBoundingClientRect();
        return (a.height + o.height) / innerHeight;
      });
      expect(share).toBeLessThanOrEqual(0.5);
    });

    test('biểu đồ giờ vẽ ra CỘT thật, không phải một dãy số lơ lửng', async ({ page }) => {
      // Bản trước: paintHourly() dựng `<i style="height:N%">` thẳng trong
      // `.kiosk-bar` còn CSS chỉ có luật cho `.kiosk-bar-stack i` -- một cấu
      // trúc không còn ai dựng. Kết quả đo được: mọi cột w=0 h=0, nền trong
      // suốt, panel chiếm 272px ở 1920 mà không hiển thị gì.
      const bars = await page.evaluate(() => [...document.querySelectorAll('.kiosk-bar > i')]
        .map(el => {
          const r = el.getBoundingClientRect();
          const cs = getComputedStyle(el);
          return { w: r.width, h: r.height, bg: cs.backgroundColor, pct: parseFloat(el.style.height) };
        }));
      expect(bars.length).toBe(24);
      expect(bars.every(b => b.w > 0)).toBe(true);
      expect(bars.every(b => b.bg !== 'rgba(0, 0, 0, 0)')).toBe(true);
      // Cột cao nhất phải cao hơn hẳn cột rỗng -- tức chiều cao theo dữ liệu
      // thật chứ không phải ai cũng bằng nhau ở mức min-height.
      const tallest = bars.reduce((a, b) => (b.pct > a.pct ? b : a));
      expect(tallest.pct).toBe(100);
      expect(tallest.h).toBeGreaterThan(12);
    });

    test('không tràn ngang, không phải cuộn dọc để thấy việc', async ({ page }) => {
      const o = await page.evaluate(() => ({
        x: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        y: document.documentElement.scrollHeight - document.documentElement.clientHeight,
      }));
      expect(o.x).toBeLessThanOrEqual(1);
      expect(o.y).toBeLessThanOrEqual(1);
    });
  });
}

// Mobile không phải màn hình đích, nhưng route KHÔNG ĐƯỢC VỠ: header một hàng
// là luật của TV, ép nó xuống 390px chỉ đẻ ra tràn ngang (đo được 162px thừa
// khi `flex-wrap:nowrap` chưa được trả lại ở bậc <=900px).
test('390px: route không vỡ, không tràn ngang', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockBusyDay(page);
  await openKiosk(page);
  const overflowX = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflowX).toBeLessThanOrEqual(1);
  expect(await page.locator('.kiosk-task').count()).toBeGreaterThan(0);
  await expect(page.locator('.kiosk-event').first()).toBeVisible();
});
