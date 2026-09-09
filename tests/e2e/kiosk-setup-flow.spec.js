// Kiosk setup flow: scan the PRODUCTION QR, run the checklist, then produce.
//
// The worker never scans a second label -- the device is handed over to the
// linked SETUP operation by the scan response, and the backend blocks the
// production start until the checklist is done, so a client that ignores the
// handover still cannot skip it.
const { test, expect } = require('@playwright/test');

const OPERATION = {
  id: 4242, code: 'PA-OP01', name: 'CẮT LASER', qr: 'WF|OP|PA-OP01',
  operation_type: 'PRODUCTION', requires_setup: true, setup_completed_at: null,
  parent_operation_id: null, part_code: 'PA', part_name: 'Thân', po_code: 'PO-777',
  po_status: 'IN_PROGRESS', status: 'IN_PROGRESS', plan_qty: 100, done_qty: 0, defect_qty: 0,
  part_id: 21, production_order_id: 501,
};
const SETUP_OP = { id: 4243, code: 'PA-OP01-SETUP', name: 'Setup CẮT LASER',
  qr: 'WF|OPID|4243', expected_setup_minutes: 15, step_count: 2 };
const STEPS = [
  { id: 71, sort_order: 0, instruction: 'Lắp khuôn số 3', required: true, done: false },
  { id: 72, sort_order: 1, instruction: 'Ghi nhật ký', required: false, done: false },
];

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const body = route.request().postDataJSON() || {};
    const qr = String(body.qr || '');
    if (qr.startsWith('WF|EMP|')) {
      // /api/kiosk-web/scan answers with type:'employee' + employee (the
      // 'worker' shape belongs to the other scan endpoint).
      return route.fulfill({ json: { ok: true, type: 'employee',
        employee: { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' },
        open_session: null } });
    }
    // The production scan hands over to setup while setup is still pending.
    if (!state.setupDone) {
      return route.fulfill({ json: { ok: true, type: 'operation', operation: OPERATION,
        next_action: 'SETUP_REQUIRED', setup_operation: SETUP_OP,
        message: 'Cần setup máy trước khi sản xuất' } });
    }
    return route.fulfill({ json: { ok: true, type: 'operation',
      operation: { ...OPERATION, setup_completed_at: '2026-09-09T04:00:00Z' } } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    const body = route.request().postDataJSON() || {};
    state.started.push(Number(body.operation_id));
    return route.fulfill({ json: { ok: true, session: { id: 555 } } });
  });
  await page.route(/\/api\/setup-sessions\/555$/, route => {
    const missing = STEPS.filter(s => s.required && !s.done);
    return route.fulfill({ json: { ok: true, session_id: 555, steps: STEPS,
      missing_required: missing, can_complete: missing.length === 0 } });
  });
  await page.route(/\/api\/setup-sessions\/555\/steps\/\d+$/, route => {
    const id = Number(route.request().url().split('/').pop());
    const body = route.request().postDataJSON() || {};
    const step = STEPS.find(s => s.id === id);
    if (step) step.done = body.done !== false;
    const missing = STEPS.filter(s => s.required && !s.done);
    return route.fulfill({ json: { ok: true, steps: STEPS, missing_required: missing,
      can_complete: missing.length === 0 } });
  });
  await page.route(/\/api\/setup-sessions\/555\/complete$/, route => {
    state.setupDone = true;
    return route.fulfill({ json: { ok: true, setup_completed: true } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

test('quét QR OP chính khi cần setup thì kiosk chuyển sang checklist, xong mới sản xuất', async ({ page }) => {
  const state = { setupDone: false, started: [] };
  await mockKiosk(page, state);
  await page.goto('/kiosk');

  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|PA-OP01'));

  // Handed over to the setup screen rather than starting production.
  await expect(page.locator('#screen-setup')).toHaveClass(/active/);
  await expect(page.locator('#setup-operation')).toContainText('PA-OP01');
  await expect(page.locator('#setup-steps .setup-check')).toHaveCount(2);
  // The SETUP session was opened; production was NOT started.
  expect(state.started).toEqual([SETUP_OP.id]);

  // Required step still open -> cannot finish.
  await expect(page.locator('#setup-complete')).toBeDisabled();
  await expect(page.locator('#setup-remaining')).toContainText('bắt buộc');

  await page.locator('#setup-steps input[data-step="71"]').check();
  await expect(page.locator('#setup-complete')).toBeEnabled();

  await page.locator('#setup-complete').click();
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await expect(page.locator('#started-operation')).toContainText('PA-OP01');
  // Setup first, then the production Operation -- in that order.
  expect(state.started).toEqual([SETUP_OP.id, OPERATION.id]);
});
