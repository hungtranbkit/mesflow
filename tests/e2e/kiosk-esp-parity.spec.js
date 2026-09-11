// Kiosk web phải gõ và cư xử giống ESP v2 ở luồng kết thúc session.
//
// Bảng đối chiếu đầy đủ (kèm neo dòng trong firmware) ở docs/KIOSK_ESP_PARITY.md.
// Ở đây chỉ khoá những điều KHÁC BIỆT MỘT DÒNG LÀ SAI:
//   * NG = 0 -> không hỏi "có lỗi sửa được" (ESP cũng bỏ qua);
//   * NG > 0 -> hỏi, và phím 1 = CÓ, 2/#/Enter = tiếp tục;
//   * lỗi sửa được nằm trong 0..NG, vượt NG thì ở lại màn;
//   * gửi xong thì tự về màn chờ quét thẻ, KHÔNG đứng lại màn kết quả;
//   * không state cũ nào sống sót sang người tiếp theo.
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

function freshState() { return { hasOpenSession: true, finished: [], failNext: false }; }

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
    if (state.failNext) {
      state.failNext = false;
      return route.fulfill({ status: 500, json: { ok: false, message: 'server sập' } });
    }
    state.hasOpenSession = false;
    state.finished.push(route.request().postDataJSON() || {});
    return route.fulfill({ json: { ok: true, session: { id: 555, status: 'CLOSED' } } });
  });
  await page.route(/\/api\/kiosk\/(register|heartbeat)/, route => route.fulfill({ json: { ok: true } }));
}

/** Quét thẻ nhân viên khi đang có session mở -> vào thẳng màn nhập "SẢN PHẨM ĐẠT". */
async function openQuantityFlow(page, state) {
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
}

async function typeQty(page, id, value) {
  const field = page.locator(`#${id}`);
  await field.fill(String(value));
}

test.describe('Luồng NG / lỗi sửa được — parity với ESP v2', () => {
  test('NG = 0 thì KHÔNG hỏi lỗi sửa được (ESP cũng bỏ qua bước này)', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);

    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();

    await expect(page.locator('#screen-ask-rework')).not.toHaveClass(/active/);
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
    await expect(page.locator('#finish-confirm-summary')).not.toContainText('Sửa được');
  });

  test('NG > 0 thì hỏi, và phím 1 = CÓ -> màn nhập lỗi sửa được', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 6);
    await page.locator('#defect-next').click();

    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
    // Nhãn phải nói đúng việc phím làm, không chỉ code làm đúng.
    await expect(page.locator('#rework-yes')).toContainText('1');
    await expect(page.locator('#rework-yes')).toContainText('CÓ');
    await expect(page.locator('#rework-none')).toContainText('2');

    await page.keyboard.press('1');
    await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);
    await expect(page.locator('#rework-max')).toContainText('0 đến 6');
  });

  for (const key of ['2', '#', 'Enter']) {
    test(`phím ${key} = tiếp tục, không nhập lỗi sửa được`, async ({ page }) => {
      const state = freshState();
      await openQuantityFlow(page, state);
      await typeQty(page, 'good-qty', 40);
      await page.locator('#good-next').click();
      await typeQty(page, 'defect-qty', 6);
      await page.locator('#defect-next').click();
      await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);

      await page.keyboard.press(key);
      await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
      await expect(page.locator('#finish-confirm-summary')).not.toContainText('Sửa được');

      await page.locator('#finish-confirm-ok').click();
      await expect.poll(() => state.finished.length).toBe(1);
      expect(state.finished[0].rework_qty).toBe(0);
      expect(state.finished[0].defect_qty).toBe(6);
    });
  }

  test('chọn 1 rồi nhập số: gửi đúng rework, KHÔNG cộng vào sản lượng đạt', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 6);
    await page.locator('#defect-next').click();
    await page.keyboard.press('1');

    await typeQty(page, 'rework-qty', 4);
    await page.locator('#rework-next').click();
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
    await expect(page.locator('#finish-confirm-summary')).toContainText('Sửa được');

    await page.locator('#finish-confirm-ok').click();
    await expect.poll(() => state.finished.length).toBe(1);
    const sent = state.finished[0];
    // Lỗi sửa được đi vào HÀNG CHỜ SỬA, không phải sản lượng đạt: cộng vào
    // good ở đây là đếm hai lần khi có người sửa xong và resolve.
    expect(sent.good_qty).toBe(40);
    expect(sent.defect_qty).toBe(6);
    expect(sent.rework_qty).toBe(4);
  });

  test('lỗi sửa được vượt NG thì ở lại màn và báo lý do', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 6);
    await page.locator('#defect-next').click();
    await page.keyboard.press('1');

    await typeQty(page, 'rework-qty', 9);
    await page.locator('#rework-next').click();
    await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);
    await expect(page.locator('#rework-validation')).toContainText('không thể lớn hơn');
    expect(state.finished.length).toBe(0);
  });

  test('nhập 0 ở màn lỗi sửa được được chấp nhận, kết quả như chọn tiếp tục', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 6);
    await page.locator('#defect-next').click();
    await page.keyboard.press('1');

    await typeQty(page, 'rework-qty', 0);
    await page.locator('#rework-next').click();
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
    await expect(page.locator('#finish-confirm-summary')).not.toContainText('Sửa được');
  });
});

test.describe('Kết thúc rồi phải về màn chờ quét thẻ', () => {
  test('gửi xong KHÔNG đứng lại màn kết quả, và xoá sạch state', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 12);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();
    await page.locator('#finish-confirm-ok').click();

    await expect(page.locator('#screen-finished')).toHaveClass(/active/);
    // Tự quay về, không cần ai bấm gì.
    await expect(page.locator('#screen-ready')).toHaveClass(/active/, { timeout: 15000 });

    // Không còn dấu vết của người vừa xong.
    expect(await page.locator('#good-qty').inputValue()).toBe('0');
    expect(await page.locator('#defect-qty').inputValue()).toBe('0');
    expect(await page.locator('#rework-qty').inputValue()).toBe('0');
    expect(await page.evaluate(() => document.getElementById('rework-validation').textContent)).toBe('');
  });

  test('người tiếp theo quét thẻ không thấy số của người trước', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 77);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();
    await page.locator('#finish-confirm-ok').click();
    await expect(page.locator('#screen-ready')).toHaveClass(/active/, { timeout: 15000 });

    state.hasOpenSession = true;
    await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
    await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
    // Ô rỗng chứ không phải '0' là ĐÚNG: màn hình tự xoá số 0 khi focus để gõ
    // nhanh hơn (rời ô thì 0 quay lại). Điều cần khẳng định là không còn số
    // của người trước, nên kiểm đúng điều đó thay vì kiểm một chuỗi cụ thể.
    const carried = await page.locator('#good-qty').inputValue();
    expect(carried).not.toBe('77');
    expect(['', '0']).toContain(carried);
  });

  test('gửi lỗi thì giữ nguyên số đã nhập để thử lại, không mất dữ liệu', async ({ page }) => {
    const state = freshState();
    state.failNext = true;
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 33);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();
    await page.locator('#finish-confirm-ok').click();

    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
    await expect(page.locator('#finish-submit-error')).toContainText('CHƯA GỬI ĐƯỢC');
    await expect(page.locator('#finish-submit-retry')).toBeVisible();
    // Thử lại thành công và vẫn gửi đúng số cũ.
    await page.locator('#finish-submit-retry').click();
    await expect.poll(() => state.finished.length).toBe(1);
    expect(state.finished[0].good_qty).toBe(33);
  });

  test('tải lại trang giữa chừng thì về màn chờ thẻ, không giữ state cũ', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 55);
    await page.locator('#good-next').click();
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

    await page.reload();
    await page.waitForFunction(() => !!window.MESFlowKioskDemo);
    await expect(page.locator('#screen-ready')).toHaveClass(/active/);
    expect(await page.locator('#good-qty').inputValue()).toBe('0');
  });
});

test.describe('Phím nhập số giống bàn phím ESP', () => {
  test('# xác nhận từng màn nhập số', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 10);
    await page.keyboard.press('#');
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
    await typeQty(page, 'defect-qty', 2);
    await page.keyboard.press('#');
    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
  });

  test('* quay lại màn trước', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 10);
    await page.locator('#good-next').click();
    await page.keyboard.press('*');
    await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  });

  test('* ở màn hỏi lỗi sửa được quay lại màn nhập NG', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 10);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 3);
    await page.locator('#defect-next').click();
    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
    await page.keyboard.press('*');
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
  });
});
