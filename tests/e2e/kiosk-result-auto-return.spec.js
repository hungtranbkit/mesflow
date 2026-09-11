// Kiosk web: màn kết quả tự trả máy về "chờ quét thẻ nhân viên" sau 15 giây.
//
// Máy kiosk đứng một mình giữa hai lượt thợ. Trước đây màn "ĐÃ GHI NHẬN" chỉ
// tự tắt khi scheduleReset() kịp cắm timer — mà nó bỏ qua toàn bộ khi bảng mô
// phỏng đang mở (chính là cách người dùng trình duyệt thao tác), nên máy nằm ở
// màn kết quả vô hạn. Spec này chốt: sau finish THẬT SỰ thành công, tối đa 15s
// là máy sạch và về màn chờ; trước 15s thì chưa; flow mới huỷ timer cũ; và
// submit lỗi thì không được xoá gì.
const { test, expect } = require('@playwright/test');

const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' };
const OPERATION = {
  id: 4242, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER', qr: 'WF|OP|OP01',
  operation_type: 'PRODUCTION', part_code: 'PA', po_code: 'PO-777', po_status: 'IN_PROGRESS',
  status: 'IN_PROGRESS', plan_qty: 100, done_qty: 0, defect_qty: 0,
};
const OPEN_SESSION = {
  id: 555, operation_id: OPERATION.id, operation_code: OPERATION.code,
  operation_display_key: OPERATION.display_key, operation_name: OPERATION.name,
  operation_type: 'PRODUCTION', started_at: '2026-09-11T04:00:00Z', plan_qty: 100,
};

// finishStatus: 200 = backend nhận thật; 500 = chưa gửi được.
async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const qr = String((route.request().postDataJSON() || {}).qr || '');
    if (qr.startsWith('WF|EMP|')) {
      return route.fulfill({ json: { ok: true, type: 'employee', employee: EMPLOYEE,
        open_session: state.hasOpenSession ? OPEN_SESSION : null } });
    }
    return route.fulfill({ json: { ok: true, type: 'operation', operation: OPERATION } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route =>
    route.fulfill({ json: { ok: true, session: { id: 556 } } }));
  await page.route(/\/api\/kiosk-web\/finish/, route => {
    if (state.finishStatus !== 200) {
      return route.fulfill({ status: state.finishStatus, json: { ok: false, error: 'SYS-500' } });
    }
    state.finished.push(route.request().postDataJSON() || {});
    state.hasOpenSession = false;
    return route.fulfill({ json: { ok: true, session: { id: 555, status: 'CLOSED' } } });
  });
  await page.route(/\/api\/kiosk-web\/demo-data/, route =>
    route.fulfill({ json: { ok: true, employees: [{ ...EMPLOYEE, qr: 'WF|EMP|NV-009' }],
      operations: [OPERATION] } }));
  await page.route(/\/api\/kiosk-web\/heartbeat/, route => route.fulfill({ json: { ok: true } }));
}

function freshState(finishStatus = 200) {
  return { hasOpenSession: true, finishStatus, finished: [] };
}

async function openKiosk(page, state) {
  await mockKiosk(page, state);
  // Đồng hồ giả: 15 giây đo được chính xác, không phải chờ thật.
  await page.clock.install();
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
}

// Quét thẻ (đang có phiên mở) rồi nhập Đạt/NG. Dừng ngay sau ô NG: NG>0 rẽ
// sang màn hỏi hàng sửa được, NG=0 đi thẳng tới màn xác nhận.
async function enterQuantities(page, { good = '5', defect = '0' } = {}) {
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await page.locator('#good-qty').fill(good);
  await page.locator('#good-next').click();
  await page.locator('#defect-qty').fill(defect);
  await page.locator('#defect-next').click();
}

async function finishOpenSession(page, quantities = {}) {
  await enterQuantities(page, quantities);
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await page.locator('#finish-confirm-ok').click();
}

test('finish thành công: kết quả giữ đúng 15 giây rồi tự về màn chờ quét thẻ', async ({ page }) => {
  const state = freshState();
  await openKiosk(page, state);
  await finishOpenSession(page);

  // t=0: vẫn phải thấy kết quả.
  await expect(page.locator('#screen-finished')).toHaveClass(/active/);
  await expect(page.locator('#finished-summary')).toContainText('Đạt 5');
  expect(state.finished).toHaveLength(1);

  // t=14.9s: chưa được reset.
  await page.clock.fastForward(14900);
  await expect(page.locator('#screen-finished')).toHaveClass(/active/);

  // t=15s: về màn chờ, và context đã sạch.
  await page.clock.fastForward(100);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
  await expect(page.locator('#screen-finished')).not.toHaveClass(/active/);
  await expect(page.locator('#good-qty')).toHaveValue('0');
  await expect(page.locator('#defect-qty')).toHaveValue('0');
  await expect(page.locator('#rework-qty')).toHaveValue('0');
});

test('bảng mô phỏng đang mở cũng không giữ được màn kết quả quá 15 giây', async ({ page }) => {
  // Đây chính là root cause: scheduleReset() bỏ qua khi bảng mô phỏng mở, nên
  // người thao tác trên trình duyệt không bao giờ được trả về màn chờ.
  const state = freshState();
  await openKiosk(page, state);
  await page.evaluate(() => window.MESFlowKioskDemo.open());
  await expect(page.locator('#demo-panel')).toHaveClass(/open/);

  await finishOpenSession(page);
  await expect(page.locator('#screen-finished')).toHaveClass(/active/);

  await page.clock.fastForward(15000);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
});

test('quét thẻ mới trước 15 giây: timer cũ bị huỷ, không reset flow mới', async ({ page }) => {
  const state = freshState();
  await openKiosk(page, state);
  await finishOpenSession(page);
  await expect(page.locator('#screen-finished')).toHaveClass(/active/);

  // t=10s: thợ tiếp theo quét thẻ, bắt đầu lượt mới.
  await page.clock.fastForward(10000);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);

  // t=16s so với lần finish: timer cũ mà còn sống thì lượt mới đã bị xoá ở đây.
  await page.clock.fastForward(6000);
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await expect(page.locator('#employee-code')).toContainText('NV-009');

  // Và timer mới chỉ thuộc về màn kết quả — màn chọn Operation thì chờ mãi cũng không tự xoá.
  await page.clock.fastForward(60000);
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
});

test('submit thất bại: không reset, không xoá sản lượng, không hẹn giờ', async ({ page }) => {
  const state = freshState(500);
  await openKiosk(page, state);
  await enterQuantities(page, { good: '7', defect: '2' });
  // NG > 0 -> hỏi hàng sửa được -> chọn "không".
  await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
  await page.locator('#rework-none').click();
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await page.locator('#finish-confirm-ok').click();

  // finish là idempotent nên lớp mạng tự gửi lại vài nhịp có backoff trước khi
  // chịu thua. Đồng hồ đang giả, nên phải tự đẩy thời gian qua các nhịp chờ đó.
  await expect(async () => {
    await page.clock.runFor(1000);
    await expect(page.locator('#finish-submit-error')).toHaveText('CHƯA GỬI ĐƯỢC SẢN LƯỢNG', { timeout: 500 });
  }).toPass({ timeout: 15000 });
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);

  // Qua mốc 15s: sản lượng chưa gửi được vẫn phải còn nguyên để thợ bấm THỬ LẠI.
  await page.clock.fastForward(30000);
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await expect(page.locator('#finish-confirm-summary')).toContainText('7');
  await expect(page.locator('#finish-submit-retry')).toBeVisible();
  expect(state.finished).toHaveLength(0);

  // Gửi lại thành công mới bắt đầu tính 15 giây.
  state.finishStatus = 200;
  await page.locator('#finish-submit-retry').click();
  await expect(page.locator('#screen-finished')).toHaveClass(/active/);
  await page.clock.fastForward(15000);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
  expect(state.finished).toHaveLength(1);
});
