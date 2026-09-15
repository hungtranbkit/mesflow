// Kiosk web: một người giữ nhiều việc cùng lúc (migration 0054).
//
// NGỮ NGHĨA MÁY QUÉT, một câu cho cả ba màn:
//   thẻ          -> xác định NGƯỜI
//   tem CHƯA mở  -> BẮT ĐẦU việc mới
//   tem ĐANG mở  -> CHỌN việc đó để nhập sản lượng
// Kết thúc chỉ xảy ra sau bước xác nhận. Quét không bao giờ tự đóng session.
//
// BA THỨ DỄ HỎNG mà spec này canh:
//
//   1. Một việc thì KHÔNG được đổi gì. Luồng cũ (quét thẻ -> vào thẳng nhập sản
//      lượng) là đại đa số ca làm; thêm một nhịp chọn cho họ là bước lùi.
//   2. Quét giữa lúc đang nhập số phải chạy được, và không được đóng nhầm
//      session nào. Màn nhập số nuốt phím theo STATE, nên chuỗi từ súng quét
//      rất dễ rơi vào đúng cái hố đó.
//   3. Chốt xong một việc chỉ gỡ đúng việc đó -- những việc còn lại vẫn chạy.
const { test, expect } = require('@playwright/test');

const EMP = { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' };

const OPS = {
  'WF|OP|OP01': { id: 4301, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER' },
  'WF|OP|OP02': { id: 4302, code: 'OP02', display_key: 'PA-OP02', name: 'CHẤN' },
  'WF|OP|OP03': { id: 4303, code: 'OP03', display_key: 'PA-OP03', name: 'HÀN' },
};
const BASE_OP = {
  operation_type: 'PRODUCTION', status: 'IN_PROGRESS', po_status: 'IN_PROGRESS',
  part_code: 'PA', part_name: 'Thân', po_code: 'PO-777', plan_qty: 100,
  done_qty: 0, defect_qty: 0, part_id: 21, production_order_id: 501,
  requires_setup: false, setup_completed_at: null, parent_operation_id: null,
};

function freshState() { return { open: [], started: [], finished: [], nextId: 900 }; }

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const qr = String((route.request().postDataJSON() || {}).qr || '');
    if (qr.startsWith('WF|EMP|')) {
      return route.fulfill({ json: { ok: true, type: 'employee', employee: EMP,
        // Đúng hình dạng máy chủ trả về từ 0054: trường cũ `open_session` giữ
        // nguyên (phần tử đầu) cho client cũ, `open_sessions` là danh sách đủ.
        open_session: state.open[0] || null,
        open_sessions: state.open } });
    }
    const op = OPS[qr];
    if (!op) return route.fulfill({ status: 404, json: { ok: false, error: 'NOT_FOUND', message: 'không có tem này' } });
    return route.fulfill({ json: { ok: true, type: 'operation', operation: { ...BASE_OP, ...op } } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    const operationId = Number((route.request().postDataJSON() || {}).operation_id);
    const op = Object.values(OPS).find(o => o.id === operationId);
    if (state.open.some(s => s.operation_id === operationId)) {
      return route.fulfill({ status: 409, json: { ok: false, error: 'CONFLICT', error_code: 'SES-409',
        message: 'Nhân viên đang mở Operation này rồi.' } });
    }
    const session = { id: state.nextId++, operation_id: operationId,
      operation_code: op.code, operation_display_key: op.display_key, operation_name: op.name,
      operation_type: 'PRODUCTION', started_at: '2026-09-15T01:00:00Z', plan_qty: 100 };
    state.started.push(operationId);
    state.open = [session, ...state.open];
    return route.fulfill({ json: { ok: true, session } });
  });
  await page.route(/\/api\/kiosk-web\/finish\/(\d+)/, route => {
    const id = Number(route.request().url().match(/finish\/(\d+)/)[1]);
    state.finished.push({ id, body: route.request().postDataJSON() || {} });
    state.open = state.open.filter(s => s.id !== id);
    return route.fulfill({ json: { ok: true, session: { id, status: 'CLOSED' } } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

async function boot(page, state) {
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
}
const scan = (page, qr) => page.evaluate(code => window.MESFlowKioskDemo.scan(code), qr);

// Mở thêm một việc theo ĐÚNG thao tác thật: màn "ĐÃ BẮT ĐẦU" bảo người dùng
// quét lại thẻ, và quét thẻ là thứ nạp lại danh sách việc đang giữ. Từ đó tem
// của một việc CHƯA mở sẽ bắt đầu nó -- dù đang đứng ở màn nhập sản lượng (một
// việc) hay màn danh sách (từ hai việc).
async function startAnother(page, qr) {
  await scan(page, 'WF|EMP|NV-009');
  // PHẢI chờ màn trung gian hiện ra trước khi quét tem tiếp.
  //
  // Quét thẻ khi đang đứng ở màn "ĐÃ BẮT ĐẦU" đi qua reset() + setTimeout(...,50)
  // rồi mới quét lại, nên promise của lần evaluate này resolve TRƯỚC khi luồng
  // thật sự chạy xong. Quét tem ngay lúc đó là đua với chính nó, và lần quét
  // tem sẽ rơi vào trạng thái 'ready' -> "Hãy quét thẻ nhân viên trước".
  //
  // Một việc -> màn nhập sản lượng; từ hai việc -> màn danh sách. Chờ cái nào
  // tới trước.
  await expect(page.locator('#screen-quantity-good.active, #screen-sessions.active'))
    .toHaveCount(1, { timeout: 10000 });
  await scan(page, qr);
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
}

async function enterQty(page, good) {
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await page.keyboard.press(String(good));
  await page.keyboard.press('Enter');          // Đạt -> Lỗi
  await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
  await page.keyboard.press('0');
  await page.keyboard.press('Enter');          // Lỗi -> xác nhận
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await page.locator('#finish-confirm-ok').click();
}

test('T5: đúng MỘT việc đang mở -> vào thẳng màn nhập sản lượng như trước', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });

  // Quét lại thẻ: một việc -> KHÔNG có màn chọn, vào thẳng keypad.
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await expect(page.locator('#screen-sessions')).not.toHaveClass(/active/);
  await expect(page.locator('#finish-operation')).toContainText('PA-OP01');
});

test('T6: đang nhập sản lượng OP01, quét tem OP02 -> OP02 START, OP01 vẫn mở', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

  // Quét ngay giữa lúc đang ở màn nhập số.
  await scan(page, 'WF|OP|OP02');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });

  expect(state.started).toEqual([4301, 4302]);
  expect(state.finished).toEqual([]);                       // không đóng gì cả
  expect(state.open.map(s => s.operation_id).sort()).toEqual([4301, 4302]);
});

test('T8: quét tem một việc ĐANG mở -> chuyển sang việc đó, không start/close nhầm', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await startAnother(page, 'WF|OP|OP02');

  // Hai việc -> quét thẻ hiện danh sách, KHÔNG tự chọn hộ.
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-sessions')).toHaveClass(/active/);
  await expect(page.locator('#sessions-list li')).toHaveCount(2);
  await expect(page.locator('#screen-sessions')).toContainText('QUÉT MÃ CÔNG ĐOẠN');

  // Quét tem việc đang mở -> đúng việc đó, không tạo session mới.
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await expect(page.locator('#finish-operation')).toContainText('PA-OP01');
  expect(state.started).toEqual([4301, 4302]);              // không start thêm
  expect(state.finished).toEqual([]);                        // không đóng gì
});

test('R6: chốt sản lượng OP02 chỉ đóng OP02; OP01/OP03 vẫn chạy', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await startAnother(page, 'WF|OP|OP02');
  await startAnother(page, 'WF|OP|OP03');
  expect(state.open).toHaveLength(3);

  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#sessions-list li')).toHaveCount(3);
  await scan(page, 'WF|OP|OP02');
  await enterQty(page, 7);

  await expect(page.locator('#screen-finished')).toHaveClass(/active/, { timeout: 10000 });
  expect(state.finished).toHaveLength(1);
  expect(state.finished[0].body.good_qty).toBe(7);
  expect(state.open.map(s => s.operation_id).sort()).toEqual([4301, 4303]);
  // Người đứng máy phải biết mình còn việc đang chạy trước khi rời đi.
  await expect(page.locator('#finished-note')).toContainText('2 việc');
});

test('đóng xuống còn 1 việc -> lần quét thẻ sau quay về luồng cũ', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await startAnother(page, 'WF|OP|OP02');

  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-sessions')).toHaveClass(/active/);
  await scan(page, 'WF|OP|OP02');
  await enterQty(page, 3);
  await expect(page.locator('#screen-finished')).toHaveClass(/active/, { timeout: 10000 });

  // Còn đúng một việc -> không còn màn chọn nữa.
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await expect(page.locator('#screen-sessions')).not.toHaveClass(/active/);
  await expect(page.locator('#finish-operation')).toContainText('PA-OP01');
});

test('T16: F5 giữa chừng không đóng/mất session nào', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await startAnother(page, 'WF|OP|OP02');

  await page.reload();
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
  expect(state.finished).toEqual([]);                  // F5 không đóng gì

  // Trạng thái thật nằm ở máy chủ, không ở màn hình: quét lại thẻ là thấy đủ.
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-sessions')).toHaveClass(/active/);
  await expect(page.locator('#sessions-list li')).toHaveCount(2);
});

test('R3/bố cục: màn danh sách đọc được ở 1366x768 và 390px, không tràn ngang', async ({ page }) => {
  const state = freshState();
  await boot(page, state);
  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await startAnother(page, 'WF|OP|OP02');
  await startAnother(page, 'WF|OP|OP03');
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-sessions')).toHaveClass(/active/);

  for (const [w, h] of [[1366, 768], [390, 844]]) {
    await page.setViewportSize({ width: w, height: h });
    await expect(page.locator('#sessions-list li')).toHaveCount(3);
    // Mã việc là thứ người đứng máy đối chiếu với tem đang cầm -- không được
    // mờ đi ở bề rộng nào.
    await expect(page.locator('#sessions-list li').first()).toContainText('PA-OP');
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `tràn ngang ở ${w}px`).toBeLessThanOrEqual(1);
  }
});
