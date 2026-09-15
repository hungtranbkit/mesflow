// Kiosk tự nạp bản mới sau khi deploy -- nhưng không bao giờ giữa chừng.
//
// VÌ SAO CẦN. Máy ở xưởng bị khoá bàn phím và không ai với tới được. Một tab đã
// mở sẽ chạy đúng bộ JS/CSS nó nạp lúc đầu cho tới khi có người bấm F5 -- tức
// là bản vá có thể nằm trên máy chủ nhiều ngày mà màn hình ngoài xưởng vẫn cũ.
//
// VÌ SAO KHÔNG ĐƯỢC NẠP BỪA. Nạp lại giữa lúc đang nhập sản lượng là mất con số
// người ta vừa gõ, và họ không có cách nào biết vì sao. Một lần như vậy đủ để
// người đứng máy thôi tin màn hình.
//
// BỐN THỨ SPEC NÀY CANH:
//   1. rảnh  -> nạp ngay
//   2. bận   -> KHÔNG nạp, nhưng nhớ lại
//   3. xong  -> nạp đúng lúc quay về màn chờ, không cần thêm vòng mạng nào
//   4. lỗi mạng / cùng phiên bản -> không nạp, và không có vòng lặp nạp lại
const { test, expect } = require('@playwright/test');

const EMP = { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' };
const OP = {
  id: 4401, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER',
  operation_type: 'PRODUCTION', status: 'IN_PROGRESS', po_status: 'IN_PROGRESS',
  part_code: 'PA', part_name: 'Thân', po_code: 'PO-777', plan_qty: 100,
  done_qty: 0, defect_qty: 0, part_id: 21, production_order_id: 501,
  requires_setup: false, setup_completed_at: null, parent_operation_id: null,
};

function freshState() { return { open: [], heartbeats: 0, heartbeatFails: false }; }

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const qr = String((route.request().postDataJSON() || {}).qr || '');
    if (qr.startsWith('WF|EMP|')) {
      return route.fulfill({ json: { ok: true, type: 'employee', employee: EMP,
        open_session: state.open[0] || null, open_sessions: state.open } });
    }
    return route.fulfill({ json: { ok: true, type: 'operation', operation: OP } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    const session = { id: 901, operation_id: OP.id, operation_code: OP.code,
      operation_display_key: OP.display_key, operation_name: OP.name,
      operation_type: 'PRODUCTION', started_at: '2026-09-15T01:00:00Z', plan_qty: 100 };
    state.open = [session];
    return route.fulfill({ json: { ok: true, session } });
  });
  await page.route(/\/api\/kiosk-web\/heartbeat/, route => {
    state.heartbeats += 1;
    if (state.heartbeatFails) return route.fulfill({ status: 500, json: { ok: false, error: 'BOOM' } });
    return route.fulfill({ json: { ok: true, status: {}, version: state.serverVersion } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

async function boot(page, state) {
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  // Mốc chỉ sống trong ĐÚNG một lần nạp trang: nó biến mất khi và chỉ khi trang
  // được nạp lại. Đây là cách đo "có reload hay không" mà không phải rình sự
  // kiện điều hướng.
  await page.evaluate(() => { window.__aliveMarker = 'A'; });
}
const marker = page => page.evaluate(() => window.__aliveMarker || null);
const serve = (page, v) => page.evaluate(x => window.MESFlowKioskDemo.applyServerVersion(x), v);
const scan = (page, qr) => page.evaluate(code => window.MESFlowKioskDemo.scan(code), qr);

test('rảnh: thấy bản mới -> nạp lại ngay', async ({ page }) => {
  const state = freshState();
  await boot(page, state);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
  expect(await marker(page)).toBe('A');

  await serve(page, '99.0.0.999');
  await page.waitForFunction(() => !window.__aliveMarker, null, { timeout: 10000 });

  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
});

test('bận: đang nhập sản lượng thì KHÔNG nạp lại', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

  // Gõ một con số: đây chính là thứ một lần nạp lại sẽ cướp mất.
  await page.keyboard.press('7');
  await serve(page, '99.0.0.999');
  await page.waitForTimeout(800);

  expect(await marker(page)).toBe('A');                       // không nạp lại
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  await expect(page.locator('#good-qty')).toHaveValue('7');   // số vẫn còn
});

test('xong việc: quay về màn chờ là nạp lại, không cần thêm vòng mạng', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

  await serve(page, '99.0.0.999');
  await page.waitForTimeout(500);
  expect(await marker(page)).toBe('A');                       // hoãn lại

  // Cắt mạng NGAY sau khi phát hiện: bản vá vẫn phải tới được máy, vì cờ đã
  // nằm sẵn trong tab chứ không phải phải đi hỏi lại máy chủ.
  state.heartbeatFails = true;
  await page.locator('#screen-quantity-good [data-action="cancel"]').click();

  await page.waitForFunction(() => !window.__aliveMarker, null, { timeout: 10000 });
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
});

test('cùng phiên bản hoặc heartbeat lỗi: không nạp lại, không vòng lặp', async ({ page }) => {
  const state = freshState();
  await boot(page, state);
  const loaded = await page.evaluate(() => window.MESFlowKioskDemo.loadedVersion());
  expect(loaded).toBeTruthy();

  // Đúng bản đang chạy -> không có lý do gì để nạp lại.
  await serve(page, loaded);
  // Máy chủ không trả phiên bản (endpoint lỗi/đứt mạng) -> bỏ qua, không đoán.
  await serve(page, '');
  state.heartbeatFails = true;
  await page.waitForTimeout(1500);

  expect(await marker(page)).toBe('A');
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);

  // Và khi mạng trở lại với ĐÚNG bản cũ, vẫn không nạp: "khác" mới là điều
  // kiện, không phải "vừa có lỗi".
  state.heartbeatFails = false;
  await serve(page, loaded);
  await page.waitForTimeout(500);
  expect(await marker(page)).toBe('A');
});

test('deploy rồi rollback về đúng bản đang chạy: cờ chờ được xoá, không nạp', async ({ page }) => {
  const state = freshState();
  await boot(page, state);

  await scan(page, 'WF|EMP|NV-009');
  await scan(page, 'WF|OP|OP01');
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 10000 });
  await scan(page, 'WF|EMP|NV-009');
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

  const loaded = await page.evaluate(() => window.MESFlowKioskDemo.loadedVersion());
  await serve(page, '99.0.0.999');   // thấy bản mới lúc đang bận
  await serve(page, loaded);         // máy chủ quay về đúng bản tab này đang chạy

  await page.locator('#screen-quantity-good [data-action="cancel"]').click();
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
  await page.waitForTimeout(800);
  expect(await marker(page)).toBe('A');   // không còn lý do nạp -> không nạp
});
