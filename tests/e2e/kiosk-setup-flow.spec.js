// Kiosk: tem SETUP quét như một Operation bình thường, và không chặn gì cả.
//
// SETUP là OP phụ có liên quan tới OP chính, không phải điều kiện tiên quyết:
// một lần setup phục vụ nhiều lượt sản xuất, và người điều phối quyết định khi
// nào cần chạy. Bản trước của spec này khẳng định điều ngược lại — quét OP
// chính khi chưa setup thì bị từ chối kèm mã tem — luật đó đã bỏ 2026-09-09.
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
    const qr = String((route.request().postDataJSON() || {}).qr || '');
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
          parent_operation_id: OPERATION.id } } });
    }
    // OP chính luôn quét được — dù setup chưa từng chạy.
    return route.fulfill({ json: { ok: true, type: 'operation', operation: OPERATION } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    const operationId = Number((route.request().postDataJSON() || {}).operation_id);
    state.started.push(operationId);
    if (operationId === SETUP_OP.id) state.openSetupSession = true;
    return route.fulfill({ json: { ok: true, session: { id: 555 } } });
  });
  await page.route(/\/api\/kiosk-web\/finish/, route => {
    state.openSetupSession = false;
    state.finished.push(route.request().postDataJSON() || {});
    return route.fulfill({ json: { ok: true, session: { id: 555, status: 'CLOSED' } } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

function freshState() { return { openSetupSession: false, started: [], finished: [] }; }

test('quét OP chính chạy được ngay dù setup chưa từng thực hiện', async ({ page }) => {
  const state = freshState();
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);

  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|OP01'));

  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  expect(state.started).toEqual([OPERATION.id]);
  // Không màn hình setup nào tồn tại để rơi vào.
  expect(await page.locator('#screen-setup').count()).toBe(0);
});

test('tem SETUP chạy như một Operation bình thường, kết thúc không cần nhập sản lượng', async ({ page }) => {
  const state = freshState();
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);

  // Quét thẻ, quét tem SETUP: một lần start bình thường.
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OPID|4243'));
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await expect(page.locator('#started-operation')).toContainText('PA-OP01-SU');
  expect(state.started).toEqual([SETUP_OP.id]);

  // Quét lại thẻ: setup không sinh sản lượng nên xác nhận thẳng, bỏ qua keypad.
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await expect(page.locator('#finish-confirm-summary')).toContainText('Setup máy');
  await page.locator('#finish-confirm-ok').click();
  await expect(page.locator('#screen-finished')).toHaveClass(/active/, { timeout: 10000 });
  expect(state.finished[0].good_qty).toBe(0);

  // Và sản xuất vẫn chạy y như trước khi setup — không có gì được "mở khóa".
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/, { timeout: 10000 });
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|OP|OP01'));
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  expect(state.started).toEqual([SETUP_OP.id, OPERATION.id]);
});
