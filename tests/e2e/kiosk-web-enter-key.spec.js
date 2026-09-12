// Kiosk WEB: phím xác nhận là `Enter`, và bàn phím số rời phải dùng được.
//
// VÌ SAO (P1, 2026-09-12). Người đứng máy gõ bằng BÀN PHÍM SỐ RỜI. Bàn phím đó
// có 0-9, `.`, `/`, `*`, `-`, `+`, Num Lock và Enter — và KHÔNG CÓ `#`. Trên
// bàn phím đầy đủ `#` là Shift+3. Nghĩa là màn hình in `#` như một phím để bấm,
// trong khi trên thiết bị người ta đang cầm thì phím đó không tồn tại: họ gõ số
// bằng một tay ở cụm số rồi không có cách nào xác nhận.
//
// `*` thì ngược lại — cụm số CÓ `*` — nên phím quay lại giữ nguyên. Thay đổi cố
// ý KHÔNG đối xứng, vì phần cứng không đối xứng.
//
// KHÔNG ĐỤNG ESP. Bàn phím màng của ESP v2 có `#` vật lý và firmware vẫn dùng
// nó; đây thuần tuý là ánh xạ bàn phím của WEB
// (docs/KIOSK_ESP_PARITY.md §2, REQ-KIOSK-015).
const { test, expect } = require('@playwright/test');

const OPERATION = {
  id: 4242, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER', qr: 'WF|OP|OP01',
  operation_type: 'PRODUCTION', requires_setup: false, setup_completed_at: null,
  parent_operation_id: null, part_code: 'PA', part_name: 'Thân', po_code: 'PO-777',
  po_status: 'IN_PROGRESS', status: 'IN_PROGRESS', plan_qty: 100, done_qty: 0, defect_qty: 0,
  part_id: 21, production_order_id: 501,
};
const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' };
const OPEN_SESSION = {
  id: 555, operation_id: OPERATION.id, operation_code: OPERATION.code,
  operation_display_key: OPERATION.display_key, operation_name: OPERATION.name,
  operation_type: 'PRODUCTION', started_at: '2026-09-11T04:00:00Z', plan_qty: 100,
};
const QUANTITY_SCREENS = ['screen-quantity-good', 'screen-quantity-defect', 'screen-quantity-rework'];

const freshState = () => ({ hasOpenSession: true, finished: [], attempts: 0 });

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
    route.fulfill({ json: { ok: true, session: { id: 555 } } }));
  await page.route(/\/api\/kiosk-web\/finish/, route => {
    state.attempts += 1;
    state.hasOpenSession = false;
    state.finished.push(route.request().postDataJSON() || {});
    return route.fulfill({ json: { ok: true, session: { id: 555, status: 'CLOSED' } } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

async function openQuantityFlow(page, state) {
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
}

const typeQty = (page, id, value) => page.locator(`#${id}`).fill(String(value));

test.describe('Kiosk web — Enter là phím xác nhận', () => {
  // `confirmKey` là TÊN PHÍM Playwright gửi đi. Cả hai đều tới trình duyệt với
  // `event.key === 'Enter'`; chúng chỉ khác `event.code`
  // (`Enter` / `NumpadEnter`). Chạy cả hai vì phím người dùng thật bấm là phím
  // trên cụm số, không phải Enter cụm chính.
  for (const confirmKey of ['Enter', 'NumpadEnter']) {
    test(`${confirmKey}: đi hết luồng đạt -> NG -> sửa được -> gửi`, async ({ page }) => {
      const state = freshState();
      await openQuantityFlow(page, state);

      await typeQty(page, 'good-qty', 40);
      await page.keyboard.press(confirmKey);
      await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

      await typeQty(page, 'defect-qty', 6);
      await page.keyboard.press(confirmKey);
      await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);

      // 1 = CÓ, nhập số lỗi sửa được.
      await page.keyboard.press('1');
      await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);
      await typeQty(page, 'rework-qty', 2);
      await page.keyboard.press(confirmKey);
      await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);

      await page.keyboard.press(confirmKey);
      await expect.poll(() => state.finished.length).toBe(1);
      expect(state.finished[0]).toMatchObject({ good_qty: 40, defect_qty: 6, rework_qty: 2 });
    });

    test(`${confirmKey}: trên màn hỏi lỗi sửa được = tiếp tục, không có`, async ({ page }) => {
      const state = freshState();
      await openQuantityFlow(page, state);
      await typeQty(page, 'good-qty', 12);
      await page.keyboard.press(confirmKey);
      await typeQty(page, 'defect-qty', 3);
      await page.keyboard.press(confirmKey);
      await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);

      await page.keyboard.press(confirmKey);
      await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
      await expect(page.locator('#finish-confirm-summary')).not.toContainText('Sửa được');
    });
  }

  // Yêu cầu 4: "Enter chỉ trigger đúng 1 action". Đây là rủi ro THẬT của cách
  // sửa này, không phải rủi ro lý thuyết: nếu ai đó thêm một nhánh
  // `event.code === 'NumpadEnter'` bên cạnh nhánh `event.key === 'Enter'` thì
  // MỘT lần bấm khớp hai nhánh và gửi hai lần.
  test('một lần bấm Enter = đúng một hành động, không đi xuyên hai màn', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);

    await page.keyboard.press('NumpadEnter');
    // Đúng MỘT bước: sang màn NG, không nhảy tiếp sang màn hỏi/xác nhận.
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
    await expect(page.locator('#screen-ask-rework')).not.toHaveClass(/active/);
    await expect(page.locator('#screen-finish-confirm')).not.toHaveClass(/active/);
    // Và ô NG vẫn là ô CHƯA ai nhập -- không bị lần bấm đó trả lời hộ.
    expect(await page.locator('#defect-qty').inputValue()).toBe('0');
  });

  test('giữ/bấm Enter liên tiếp lúc đang gửi chỉ tạo MỘT lượt gửi', async ({ page }) => {
    const state = freshState();
    let release;
    const held = new Promise(resolve => { release = resolve; });
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);
    await page.keyboard.press('Enter');
    await typeQty(page, 'defect-qty', 0);
    await page.keyboard.press('Enter');
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);

    await page.route(/\/api\/kiosk-web\/finish/, async route => { await held; await route.fallback(); });

    await page.keyboard.press('Enter');
    await page.keyboard.press('NumpadEnter');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(150);
    release();

    await expect.poll(() => state.finished.length).toBe(1);
    expect(state.attempts).toBe(1);
  });

  // Yêu cầu 5: không còn hướng dẫn sai "# để tiếp tục" trên Kiosk web, và phím
  // đó cũng không còn làm gì -- nhãn và hành vi phải nói CÙNG một chuyện.
  test('`#` không còn là phím của Kiosk web: không chữ nào in nó, bấm cũng không đi tiếp', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);

    await page.keyboard.press('#');
    await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
    await expect(page.locator('#screen-quantity-defect')).not.toHaveClass(/active/);

    // Enter vẫn đi tiếp bình thường ngay sau đó.
    await page.keyboard.press('Enter');
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

    // Không màn nào còn in `#` như một phím phải bấm.
    for (const id of [...QUANTITY_SCREENS, 'screen-ask-rework', 'screen-finish-confirm']) {
      const text = await page.locator(`#${id}`).innerText();
      expect(text, `${id} vẫn hướng dẫn bấm #`).not.toContain('#');
    }
  });

  test('* vẫn quay lại: cụm phím số CÓ phím này nên nó không đổi', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);
    await page.keyboard.press('Enter');
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

    await page.keyboard.press('*');
    await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  });
});

test.describe('Nhắc Num Lock trên màn nhập số', () => {
  test('hiện trên cả ba màn nhập số, và nói đúng phím xác nhận', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);

    const hintOf = id => page.locator(`#${id} [data-testid="kiosk-key-hint"]`);
    await expect(hintOf('screen-quantity-good')).toBeVisible();
    await expect(hintOf('screen-quantity-good')).toContainText('Num Lock');
    await expect(hintOf('screen-quantity-good')).toContainText('Enter');

    await typeQty(page, 'good-qty', 40);
    await page.keyboard.press('Enter');
    await expect(hintOf('screen-quantity-defect')).toBeVisible();
    await expect(hintOf('screen-quantity-defect')).toContainText('Num Lock');

    await typeQty(page, 'defect-qty', 6);
    await page.keyboard.press('Enter');
    await page.keyboard.press('1');
    await expect(hintOf('screen-quantity-rework')).toBeVisible();
    await expect(hintOf('screen-quantity-rework')).toContainText('Num Lock');
  });

  // "Không gây layout shift" được kiểm bằng HÌNH HỌC, không bằng độ trễ:
  // dòng nhắc nằm SAU hàng nút, nên nó không thể đẩy nút TIẾP TỤC đi đâu cả.
  // Đây chính là ràng buộc REQ-KIOSK-013 dựa vào (vùng TIẾP TỤC không được
  // trôi xuống chỗ vùng XÁC NHẬN của màn kế).
  test('dòng nhắc nằm DƯỚI hàng nút nên không đẩy nút TIẾP TỤC', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);

    const actions = await page.locator('#screen-quantity-good .actions').boundingBox();
    const hint = await page.locator('#screen-quantity-good [data-testid="kiosk-key-hint"]').boundingBox();
    expect(hint.y).toBeGreaterThanOrEqual(actions.y + actions.height - 1);
  });

  test('dòng nhắc có mặt ngay từ lần vẽ đầu và không dịch chỗ khi hiện thông báo lỗi', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);

    const hint = page.locator('#screen-quantity-good [data-testid="kiosk-key-hint"]');
    const before = await hint.boundingBox();

    // Bấm TIẾP TỤC khi chưa ai nhập -> dòng validation hiện lên. Ô validation
    // đã có min-height nên nó KHÔNG được làm dòng nhắc nhảy chỗ.
    await page.locator('#good-next').click();
    await expect(page.locator('#good-validation')).not.toHaveText('');
    const after = await hint.boundingBox();

    expect(Math.abs(after.y - before.y), 'dòng nhắc bị đẩy khi thông báo lỗi hiện').toBeLessThanOrEqual(1);
  });

  test('390px: dòng nhắc vẫn đọc được và không tràn ngang', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 780 });
    const state = freshState();
    await openQuantityFlow(page, state);

    const hint = page.locator('#screen-quantity-good [data-testid="kiosk-key-hint"]');
    await expect(hint).toBeVisible();
    const box = await hint.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(390);
    const scrolls = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(scrolls, 'trang tràn ngang ở 390px').toBe(true);
  });
});
