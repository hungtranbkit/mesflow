// Kiosk web, bảng "Mô phỏng quét QR": quét NV rồi quét OP phải đi đúng như quét
// thẻ thật rồi quét tem thật.
//
// Lỗi P0 trên dev.mesflow.net/kiosk (2026-09-29): chọn NV -> "Quét" -> chọn OP
// -> "Quét" -> máy chủ từ chối (vd. SES-409 ngoài ca) -> bấm "Quét" OP lần nữa
// -> SCN-003 "Hãy quét thẻ nhân viên trước" dù thẻ vừa quét xong. Gốc: lúc bảng
// mô phỏng mở, màn kết quả ('error', 'started') bị ghim; một lần quét ở đó đi
// qua reset() -- xoá NGƯỜI -- rồi quét lại ở 'ready', nên mọi tem Operation bị
// từ chối. Lần quét lại đó còn gửi /scan thêm một vòng và để trống một khe ở
// 'ready' mà cú bấm kế tiếp rơi vào.
//
// Spec này chốt:
//   D1. NV -> OP (bị từ chối) -> OP lại: thử lại /start với ĐÚNG người đó.
//   D2. NV -> OP01 đã bắt đầu (màn ghim) -> OP02: bắt đầu OP02 cho cùng người,
//       và OP01 vẫn nằm trong danh sách việc đang giữ.
//   D3. Từ màn lỗi, quét NV khác rồi quét OP NGAY: OP thuộc NV mới, mỗi cú
//       bấm đúng một lần /scan (không còn quét lại).
//   D4. Đã reset (nút Huỷ/Quét lại) thì chưa có ai -> quét OP vẫn SCN-003 và
//       KHÔNG gọi /start.
//   D5. Súng quét thật (MESFlowKioskDemo.scan) KHÔNG đổi: tem sau màn lỗi vẫn
//       đòi quét thẻ trước.
//   D6. Lần hai (2026-09-29): trên DEV, /start bị từ chối vì NGOÀI CA, và
//       màn hình chỉ nói "Công đoạn này hiện không thể bắt đầu" + "quét lại
//       thẻ" -- trông y hệt lỗi cũ. Nay hiện đúng lý do + mã SHF-409 của máy
//       chủ, rồi khi vào ca thì cả chuỗi NV -> OP bắt đầu được.
//   D7. NV ngừng hoạt động ở /start: EMP-001 + câu của máy chủ.
//   D8. 409 KHÔNG có `reason` (máy chủ cũ): vẫn câu chung như trước.
const { test, expect } = require('@playwright/test');

const EMPS = [
  { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí', qr: 'WF|EMP|NV-009' },
  { id: 10, employee_no: 'NV-010', name: 'Thợ B', department: 'Cơ khí', qr: 'WF|EMP|NV-010' },
];
const BASE_OP = {
  operation_type: 'PRODUCTION', status: 'IN_PROGRESS', po_status: 'IN_PROGRESS',
  part_code: 'PA', part_name: 'Thân', po_code: 'PO-777', plan_qty: 100,
  done_qty: 0, defect_qty: 0, part_id: 21, production_order_id: 501,
  requires_setup: false, setup_completed_at: null, parent_operation_id: null,
};
const OPS = [
  { ...BASE_OP, id: 4301, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER', qr: 'WF|OP|OP01' },
  { ...BASE_OP, id: 4302, code: 'OP02', display_key: 'PA-OP02', name: 'CHẤN', qr: 'WF|OP|OP02' },
];

function freshState() {
  // rejectStarts: số lần /start kế tiếp bị từ chối kiểu "ngoài ca".
  return { rejectStarts: 0, scans: [], starts: [], open: {}, nextId: 900 };
}

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const qr = String((route.request().postDataJSON() || {}).qr || '');
    state.scans.push(qr);
    const emp = EMPS.find(e => e.qr === qr);
    if (emp) {
      const open = state.open[emp.id] || [];
      return route.fulfill({ json: { ok: true, type: 'employee', employee: emp,
        open_session: open[0] || null, open_sessions: open } });
    }
    const op = OPS.find(o => o.qr === qr);
    if (!op) return route.fulfill({ status: 404, json: { ok: false, error: 'NOT_FOUND' } });
    return route.fulfill({ json: { ok: true, type: 'operation', operation: op } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    const body = route.request().postDataJSON() || {};
    state.starts.push({ employee_id: body.employee_id, operation_id: body.operation_id });
    // Một lần từ chối có hình dạng tuỳ ý (status + body), đúng như máy chủ trả.
    if (state.refusals && state.refusals.length) {
      const r = state.refusals.shift();
      return route.fulfill({ status: r.status, json: r.json });
    }
    if (state.rejectStarts > 0) {
      state.rejectStarts -= 1;
      return route.fulfill({ status: 409, json: { ok: false, error: 'CONFLICT', error_code: 'SES-409',
        message: 'Ngoài ca làm việc. Không thể bắt đầu phiên.' } });
    }
    const op = OPS.find(o => o.id === Number(body.operation_id));
    const session = { id: state.nextId++, operation_id: op.id, operation_code: op.code,
      operation_display_key: op.display_key, operation_name: op.name,
      operation_type: 'PRODUCTION', started_at: '2026-09-29T01:00:00Z', plan_qty: 100 };
    state.open[body.employee_id] = [session, ...(state.open[body.employee_id] || [])];
    return route.fulfill({ json: { ok: true, session } });
  });
  await page.route(/\/api\/kiosk-web\/demo-data/, route =>
    route.fulfill({ json: { ok: true, employees: EMPS, operations: OPS } }));
  await page.route(/\/api\/kiosk(-web)?\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

async function openDemoKiosk(page, state) {
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.locator('#demo-toggle').click();
  await expect(page.locator('#demo-panel')).toHaveAttribute('data-demo-state', 'ready');
}

// Đúng thao tác người dùng: chọn trong danh sách rồi bấm nút "Quét".
async function demoScanEmployee(page, id) {
  await page.locator('#demo-employee').selectOption(String(id));
  await page.locator('#demo-scan-employee').click();
}
async function demoScanOperation(page, id) {
  await page.locator('#demo-operation').selectOption(String(id));
  await page.locator('#demo-scan-operation').click();
}
const screen = page => page.evaluate(() => document.body.dataset.screen);

test('D1: NV -> OP bị từ chối -> quét OP lại thử /start với đúng NV, không SCN-003', async ({ page }) => {
  const state = freshState();
  state.rejectStarts = 1;
  await openDemoKiosk(page, state);

  await demoScanEmployee(page, 9);
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-error')).toHaveClass(/active/);
  await expect(page.locator('#error-code')).toHaveText('SES-409');

  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-started')).toHaveClass(/active/);
  await expect(page.locator('#error-code')).not.toHaveText('SCN-003');
  expect(state.starts).toEqual([
    { employee_id: 9, operation_id: 4301 },
    { employee_id: 9, operation_id: 4301 },
  ]);
  // Một cú bấm = một lần /scan. Trước đây lần thứ hai gửi /scan hai lần.
  expect(state.scans).toEqual(['WF|EMP|NV-009', 'WF|OP|OP01', 'WF|OP|OP01']);
});

test('D2: màn "ĐÃ BẮT ĐẦU" bị ghim -> quét OP khác bắt đầu cho cùng NV, việc cũ vẫn giữ', async ({ page }) => {
  const state = freshState();
  await openDemoKiosk(page, state);

  await demoScanEmployee(page, 9);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-started')).toHaveClass(/active/);
  // Bảng mở -> không có lần tự trả về sau 3.5s: màn vẫn là 'started'.
  await page.waitForTimeout(4000);
  expect(await screen(page)).toBe('started');

  await demoScanOperation(page, 4302);
  await expect(page.locator('#started-operation')).toContainText('PA-OP02');
  await expect(page.locator('#started-note')).toContainText('2 việc');
  expect(state.starts).toEqual([
    { employee_id: 9, operation_id: 4301 },
    { employee_id: 9, operation_id: 4302 },
  ]);

  // OP01 vẫn nằm trong danh sách việc đang giữ: tem của nó mở màn nhập sản
  // lượng, không bắt đầu thêm một session nữa.
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await expect(page.locator('#finish-operation')).toContainText('PA-OP01');
  expect(state.starts).toHaveLength(2);
});

test('D3: từ màn lỗi quét NV khác rồi quét OP ngay -> OP thuộc NV mới', async ({ page }) => {
  const state = freshState();
  state.rejectStarts = 1;
  await openDemoKiosk(page, state);

  await demoScanEmployee(page, 9);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-error')).toHaveClass(/active/);

  await demoScanEmployee(page, 10);
  // Không chờ gì thêm ngoài chính màn đích: trước đây ở đây có một khe
  // 'ready' (reset + setTimeout + /scan lần hai) mà cú bấm kế tiếp rơi vào.
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await expect(page.locator('#employee-name')).toHaveText('Thợ B');
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-started')).toHaveClass(/active/);
  expect(state.starts.at(-1)).toEqual({ employee_id: 10, operation_id: 4301 });
  expect(state.scans.filter(q => q === 'WF|EMP|NV-010')).toHaveLength(1);
});

test('D4: đã reset thì chưa có ai -> quét OP vẫn SCN-003 và không gọi /start', async ({ page }) => {
  const state = freshState();
  state.rejectStarts = 1;
  await openDemoKiosk(page, state);

  await demoScanEmployee(page, 9);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-error')).toHaveClass(/active/);
  // Nút "Quét lại" trên màn lỗi = reset(): xoá người.
  await page.locator('#screen-error [data-action="reset"], #screen-error [data-action="cancel"]').first().click();
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);

  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-error')).toHaveClass(/active/);
  await expect(page.locator('#error-code')).toHaveText('SCN-003');
  expect(state.starts).toHaveLength(1);
});

test('D5: súng quét thật không đổi -- tem sau màn lỗi vẫn đòi quét thẻ trước', async ({ page }) => {
  const state = freshState();
  state.rejectStarts = 1;
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);

  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|OP01'));
  await expect(page.locator('#error-code')).toHaveText('SES-409');
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|OP01'));
  await expect(page.locator('#error-code')).toHaveText('SCN-003');
  expect(state.starts).toHaveLength(1);
});

const OUTSIDE_SHIFT = { status: 409, json: { ok: false, error: 'CONFLICT', error_code: 'SHF-409',
  reason: 'OUTSIDE_SHIFT',
  message: 'Ngoài ca làm việc. Không thể bắt đầu phiên mới (giờ ca: Ca ngày 08:00–17:00 · Ca tối 18:00–00:00).',
  action: 'Chỉ bắt đầu được trong giờ ca. Chờ tới giờ ca, hoặc nhờ quản đốc kiểm tra Lịch làm việc.' } };

test('D6: ngoài ca -> hiện đúng lý do máy chủ; vào ca -> NV -> OP bắt đầu được', async ({ page }) => {
  const state = freshState();
  state.refusals = [OUTSIDE_SHIFT];
  await openDemoKiosk(page, state);
  // Đăng ký SAU mockKiosk: route đăng ký sau thắng.
  const beats = [];
  await page.route(/\/api\/kiosk-web\/heartbeat/, route => {
    beats.push(route.request().postDataJSON() || {});
    return route.fulfill({ json: { ok: true } });
  });

  await demoScanEmployee(page, 9);
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-error')).toHaveClass(/active/);
  await expect(page.locator('#error-code')).toHaveText('SHF-409');
  await expect(page.locator('#error-message')).toContainText('Ngoài ca làm việc');
  await expect(page.locator('#error-message')).toContainText('08:00–17:00');
  await expect(page.locator('#error-message')).not.toContainText('Công đoạn này hiện không thể bắt đầu');
  await expect(page.locator('#error-action')).toContainText('giờ ca');
  await expect(page.locator('#error-action')).not.toContainText('thẻ nhân viên');
  // Chẩn đoán từ xa mang đủ mã + lý do.
  await expect.poll(() => beats.some(b => String(b.last_error || '').startsWith('SHF-409 OUTSIDE_SHIFT: Ngoài ca'))).toBe(true);

  // Vào ca: đúng chuỗi người dùng làm -- quét NV rồi quét OP -- phải thành công.
  await demoScanEmployee(page, 9);
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#screen-started')).toHaveClass(/active/);
  await expect(page.locator('#started-operation')).toContainText('PA-OP01');
  expect(state.starts).toEqual([
    { employee_id: 9, operation_id: 4301 },
    { employee_id: 9, operation_id: 4301 },
  ]);
});

test('D7: NV ngừng hoạt động ở /start -> EMP-001 + câu của máy chủ', async ({ page }) => {
  const state = freshState();
  state.refusals = [{ status: 400, json: { ok: false, error: 'INVALID_REQUEST', error_code: 'EMP-001',
    reason: 'EMPLOYEE_INACTIVE', message: 'Nhân viên đã ngừng hoạt động hoặc không còn trong danh mục.',
    action: 'Kiểm tra trạng thái nhân viên trong Danh mục, hoặc quét thẻ của người khác.' } }];
  await openDemoKiosk(page, state);
  await demoScanEmployee(page, 9);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#error-code')).toHaveText('EMP-001');
  await expect(page.locator('#error-message')).toHaveText('Nhân viên đã ngừng hoạt động hoặc không còn trong danh mục.');
});

test('D8: 409 không có reason (máy chủ cũ) -> vẫn câu chung như trước', async ({ page }) => {
  const state = freshState();
  state.refusals = [{ status: 409, json: { ok: false, error: 'CONFLICT', error_code: 'SES-409',
    message: 'something internal', action: 'x' } }];
  await openDemoKiosk(page, state);
  await demoScanEmployee(page, 9);
  await demoScanOperation(page, 4301);
  await expect(page.locator('#error-code')).toHaveText('SES-409');
  await expect(page.locator('#error-message')).toHaveText('Công đoạn này hiện không thể bắt đầu.');
});
