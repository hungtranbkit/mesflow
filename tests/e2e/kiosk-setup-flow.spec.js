// Browser kiosk: setup is scanned, not navigated to.
//
// The ESP terminal is fixed hardware whose firmware cannot grow a setup
// screen, so the browser kiosk deliberately does not have one either -- it
// performs the SAME four steps the device does: card, SETUP label, card,
// confirm. Scanning the production label too early is an ordinary rejection
// that names the label to go and find.
const { test, expect } = require('@playwright/test');

const OPERATION = {
  id: 4242, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER', qr: 'WF|OP|OP01',
  operation_type: 'PRODUCTION', requires_setup: true, setup_completed_at: null,
  parent_operation_id: null, part_code: 'PA', part_name: 'Thân', po_code: 'PO-777',
  po_status: 'IN_PROGRESS', status: 'IN_PROGRESS', plan_qty: 100, done_qty: 0, defect_qty: 0,
  part_id: 21, production_order_id: 501,
};
const SETUP_OP = { id: 4243, code: 'OP01-SU', display_key: 'PA-OP01-SU',
  name: 'Setup CẮT LASER', qr: 'WF|OPID|4243', expected_setup_minutes: 15 };

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const body = route.request().postDataJSON() || {};
    const qr = String(body.qr || '');
    if (qr.startsWith('WF|EMP|')) {
      const openSession = state.openSetupSession
        ? { id: 555, operation_id: SETUP_OP.id, operation_code: SETUP_OP.code,
            operation_display_key: SETUP_OP.display_key, operation_name: SETUP_OP.name,
            operation_type: 'SETUP', started_at: '2026-09-09T04:00:00Z', plan_qty: 0 }
        : null;
      return route.fulfill({ json: { ok: true, type: 'employee',
        employee: { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' },
        open_session: openSession } });
    }
    if (qr === SETUP_OP.qr) {
      return route.fulfill({ json: { ok: true, type: 'operation',
        operation: { ...OPERATION, ...SETUP_OP, operation_type: 'SETUP',
          parent_operation_id: OPERATION.id, requires_setup: false } } });
    }
    // The production label, while setup is still pending: one refusal on the
    // screen the kiosk already has, naming the SETUP label.
    if (!state.setupDone) {
      return route.fulfill({ status: 409, json: { ok: false, error: 'SETUP_REQUIRED',
        error_code: 'OP-010', operation: OPERATION, setup_operation: SETUP_OP,
        message: `Cần setup máy trước. Quét QR ${SETUP_OP.display_key}`,
        action: 'Làm theo tờ hướng dẫn setup tại máy, quét tem SETUP để bắt đầu.' } });
    }
    return route.fulfill({ json: { ok: true, type: 'operation',
      operation: { ...OPERATION, setup_completed_at: '2026-09-09T04:05:00Z' } } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    const body = route.request().postDataJSON() || {};
    const operationId = Number(body.operation_id);
    state.started.push(operationId);
    if (operationId === SETUP_OP.id) state.openSetupSession = true;
    return route.fulfill({ json: { ok: true, session: { id: 555 } } });
  });
  await page.route(/\/api\/kiosk-web\/finish/, route => {
    state.openSetupSession = false; state.setupDone = true;
    state.finished.push(route.request().postDataJSON() || {});
    return route.fulfill({ json: { ok: true, session: { id: 555, status: 'CLOSED' } } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

test('quét OP chính khi chưa setup thì báo lỗi kèm mã tem SETUP, không mở màn hình mới', async ({ page }) => {
  const state = { setupDone: false, openSetupSession: false, started: [], finished: [] };
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);

  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|OP01'));

  await expect(page.locator('#screen-error')).toHaveClass(/active/);
  await expect(page.locator('#screen-error')).toContainText('PA-OP01-SU');
  // Nothing was started, and no setup-specific screen exists to land on.
  expect(state.started).toEqual([]);
  expect(await page.locator('#screen-setup').count()).toBe(0);
});

test('quét tem SETUP chạy như một Operation bình thường rồi mở khóa sản xuất', async ({ page }) => {
  const state = { setupDone: false, openSetupSession: false, started: [], finished: [] };
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);

  // Card, then the SETUP label: an ordinary start. Each scan waits for the
  // screen it produces -- the kiosk resets itself between tasks, so firing the
  // next scan before that lands would race the reset, not the code under test.
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OPID|4243'));
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await expect(page.locator('#started-operation')).toContainText('PA-OP01-SU');
  expect(state.started).toEqual([SETUP_OP.id]);

  // Card again: a setup produces nothing, so it confirms instead of asking
  // for quantities -- the keypad screens are skipped, not answered.
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await expect(page.locator('#finish-confirm-summary')).toContainText('Setup máy');
  await page.locator('#finish-confirm-ok').click();
  await expect(page.locator('#screen-finished')).toHaveClass(/active/, { timeout: 10000 });
  expect(state.finished[0].good_qty).toBe(0);

  // Production now starts on the very scan that was refused before.
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/, { timeout: 10000 });
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|OP01'));
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  expect(state.started).toEqual([SETUP_OP.id, OPERATION.id]);
});
