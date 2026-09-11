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

function freshState() { return { hasOpenSession: true, finished: [], attempts: 0, failAll: false, abortNetwork: false }; }

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
    // Hai loại hỏng đi hai đường khác nhau ở lớp mạng: abort = fetch ném
    // (TypeError, 'network'), còn 500 = máy chủ có trả lời ('server'). Gộp cả
    // hai vào một mock để không phải đăng ký chồng route -- page.unroute() với
    // cùng regex sẽ gỡ luôn handler gốc, và bài test im lặng đo sai.
    if (state.abortNetwork) return route.abort('failed');
    if (state.failAll) {
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

  test('lỗi DAI DẲNG: giữ nguyên số, hiện nút thử lại, gửi lại đúng số cũ', async ({ page }) => {
    // Lỗi DAI DẲNG chứ không phải chớp nhoáng. Đây là ranh giới đúng của nút
    // "Thử lại" thủ công: ESP v2 cũng chỉ hiện màn FINISH_RETRY khi nó THẬT SỰ
    // không đi tiếp được (mất WiFi / chưa bind), còn lỗi tạm thời thì firmware
    // tự gửi lại nền mỗi PENDING_RETRY_MS = 10s (mesflow_app.cpp:6136) mà
    // không phiền tới người đứng máy.
    //
    // Vì thế bài test này KHÔNG dùng "hỏng đúng một lần": ở tổ hợp có lớp
    // mạng tự thử lại, một lỗi chớp nhoáng sẽ tự lành và không bao giờ hiện
    // nút — đúng như thiết kế, nhưng bài test sẽ đỏ vì lý do sai.
    const state = freshState();
    state.failAll = true;
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 33);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();
    await page.locator('#finish-confirm-ok').click();

    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
    await expect(page.locator('#finish-submit-error')).toContainText('CHƯA GỬI ĐƯỢC');
    await expect(page.locator('#finish-submit-retry')).toBeVisible();
    expect(state.finished.length).toBe(0);

    // Máy chủ trở lại: bấm thử lại phải gửi ĐÚNG số đã nhập, đúng MỘT lần.
    state.failAll = false;
    await page.locator('#finish-submit-retry').click();
    await expect.poll(() => state.finished.length).toBe(1);
    expect(state.finished[0].good_qty).toBe(33);
    expect(state.finished[0].defect_qty).toBe(0);
  });

  test('mọi lần gửi lại đều mang CÙNG request_id nên máy chủ khử được trùng', async ({ page }) => {
    // Đây là thứ khiến "tự thử lại" an toàn. request_id sinh MỘT lần lúc vào
    // luồng (kiosk.js), không sinh lại mỗi lần gửi, nên backend khử trùng qua
    // kiosk_idempotency. Nếu ai đó chuyển sang sinh id mỗi lần gửi thì mỗi lần
    // thử lại thành một giao dịch mới -- bài test này đỏ ngay.
    const state = freshState();
    state.failAll = true;
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 15);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();

    const seen = [];
    await page.route(/\/api\/kiosk-web\/finish/, async route => {
      seen.push((route.request().postDataJSON() || {}).request_id);
      await route.fallback();
    });

    await page.locator('#finish-confirm-ok').click();
    await expect(page.locator('#finish-submit-retry')).toBeVisible();
    await page.locator('#finish-submit-retry').click();
    await expect.poll(() => seen.length).toBeGreaterThanOrEqual(2);
    expect(new Set(seen).size).toBe(1);
    expect(seen[0]).toBeTruthy();
  });

  test('mất mạng hẳn: vẫn giữ số và hiện nút thử lại (nhánh lỗi MẠNG, không phải 500)', async ({ page }) => {
    // Hai loại hỏng đi hai đường khác nhau: HTTP 500 là "máy chủ trả lời nhưng
    // lỗi", còn mất mạng là fetch ném luôn. Các bài trên dùng 500; bài này phủ
    // nhánh còn lại, vì trên sàn xưởng rớt Wi-Fi mới là ca hay gặp.
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 21);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();

    state.abortNetwork = true;
    await page.locator('#finish-confirm-ok').click();
    await expect(page.locator('#finish-submit-error')).toContainText('CHƯA GỬI ĐƯỢC');
    await expect(page.locator('#finish-submit-retry')).toBeVisible();
    expect(state.finished.length).toBe(0);

    // Mạng trở lại: bấm thử lại gửi đúng số cũ, đúng một lần.
    state.abortNetwork = false;
    await page.locator('#finish-submit-retry').click();
    await expect.poll(() => state.finished.length).toBe(1);
    expect(state.finished[0].good_qty).toBe(21);
  });

  test('bấm XÁC NHẬN nhiều lần lúc đang gửi chỉ tạo MỘT lượt gửi', async ({ page }) => {
    // ESP bỏ qua phím khi đang ở UiState::FINISHING. Trên bàn phím khoá cứng,
    // màn hình đứng vài giây là người ta bấm lại -- không ghi trùng nhờ
    // request_id dùng lại, nhưng mỗi lần bấm vẫn là một lượt gọi mạng thừa.
    const state = freshState();
    await openQuantityFlow(page, state);
    await typeQty(page, 'good-qty', 8);
    await page.locator('#good-next').click();
    await typeQty(page, 'defect-qty', 0);
    await page.locator('#defect-next').click();

    let release;
    const held = new Promise(resolve => { release = resolve; });
    await page.route(/\/api\/kiosk-web\/finish/, async route => {
      await held;
      await route.fallback();
    });

    await page.locator('#finish-confirm-ok').click();
    await page.keyboard.press('Enter');
    await page.keyboard.press('#');
    await page.waitForTimeout(150);
    release();

    await expect.poll(() => state.finished.length).toBe(1);
    expect(state.attempts).toBe(1);
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

// --- Vị trí nút trên màn hình -------------------------------------------------
//
// Bàn phím ESP không có chuột: công nhân nhớ VỊ TRÍ chứ không đọc chữ. Firmware
// vẽ mọi màn qua drawFooterTwoActions(left, right) (mesflow_app.cpp:1386) và
// MỌI lời gọi đều là ("* ...", "# ...") -- lùi bên trái, xác nhận bên phải.
// Kiosk web từng xếp ngược ở màn XÁC NHẬN (# bên trái, * bên phải) vì
// #finish-confirm-ok đứng trước trong DOM. Ở đây đo TOẠ ĐỘ THẬT sau layout,
// không đọc markup: đó là thứ duy nhất nói đúng người dùng nhìn thấy gì.

/** Hình học từng hàng nút của một màn: hộp của các ô back/confirm đang hiện. */
async function actionRows(page, screenId) {
  return page.evaluate(id => {
    const screen = document.getElementById(id);
    const seen = el => !!el.offsetParent && !el.hidden;
    const box = el => { const r = el.getBoundingClientRect(); return { id: el.id, left: r.left, right: r.right, top: r.top, height: r.height, width: r.width }; };
    return [...screen.querySelectorAll('.actions, .choice-grid')].map(row => ({
      back: [...row.querySelectorAll('[data-action-slot="back"]')].filter(seen).map(box),
      confirm: [...row.querySelectorAll('[data-action-slot="confirm"]')].filter(seen).map(box),
    }));
  }, screenId);
}

/** Trả về số hàng đã thực sự kiểm -- để không có bài test xanh vì rỗng. */
async function expectConfirmOnTheRight(page, screenId) {
  const rows = await actionRows(page, screenId);
  let checked = 0;
  for (const row of rows) {
    if (!row.back.length || !row.confirm.length) continue;
    checked += 1;
    const backEdge = Math.max(...row.back.map(b => b.right));
    for (const c of row.confirm) {
      expect(c.left, `${screenId}: ${c.id} phải nằm bên PHẢI ô lùi`).toBeGreaterThanOrEqual(backEdge - 0.5);
    }
  }
  return checked;
}

/** Đi tới màn xác nhận, có hoặc không đi qua bước lỗi sửa được. */
async function reachConfirm(page, state, { defect = 0 } = {}) {
  await openQuantityFlow(page, state);
  await typeQty(page, 'good-qty', 40);
  await page.locator('#good-next').click();
  await typeQty(page, 'defect-qty', defect);
  await page.locator('#defect-next').click();
  if (defect > 0) {
    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
    await page.keyboard.press('2');
  }
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
}

test.describe('Ô XÁC NHẬN nằm bên phải, giống footer ESP', () => {
  test('màn XÁC NHẬN: * QUAY LẠI bên trái, # XÁC NHẬN bên phải', async ({ page }) => {
    const state = freshState();
    await reachConfirm(page, state);

    const ok = page.locator('#finish-confirm-ok');
    const edit = page.locator('#finish-confirm-edit');
    await expect(ok).toContainText('XÁC NHẬN');
    await expect(edit).toContainText('QUAY LẠI');
    expect(await expectConfirmOnTheRight(page, 'screen-finish-confirm')).toBe(1);

    // Đảo vị trí mà vẫn bấm đúng nút: click # vẫn phải gửi.
    await ok.click();
    await expect.poll(() => state.finished.length).toBe(1);
  });

  test('nút THỬ LẠI cũng là ô "#" nên cũng phải ở bên phải', async ({ page }) => {
    const state = freshState();
    state.failAll = true;
    await reachConfirm(page, state);
    await page.locator('#finish-confirm-ok').click();
    await expect(page.locator('#finish-submit-retry')).toBeVisible();
    expect(await expectConfirmOnTheRight(page, 'screen-finish-confirm')).toBe(1);
  });

  test('mọi màn nhập số cũng xếp lùi-trái / tiến-phải', async ({ page }) => {
    const state = freshState();
    await openQuantityFlow(page, state);
    expect(await expectConfirmOnTheRight(page, 'screen-quantity-good')).toBe(1);

    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    expect(await expectConfirmOnTheRight(page, 'screen-quantity-defect')).toBe(1);

    await typeQty(page, 'defect-qty', 6);
    await page.locator('#defect-next').click();
    await page.keyboard.press('1');
    await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);
    expect(await expectConfirmOnTheRight(page, 'screen-quantity-rework')).toBe(1);
  });

  test('phím vật lý # vẫn xác nhận, phím * vẫn quay lại (vị trí đổi, ngữ nghĩa không)', async ({ page }) => {
    const state = freshState();
    await reachConfirm(page, state, { defect: 6 });

    await page.keyboard.press('*');
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
    await page.locator('#defect-next').click();
    await page.keyboard.press('2');
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);

    await page.keyboard.press('#');
    await expect.poll(() => state.finished.length).toBe(1);
  });

  test('390px: không tràn ngang, nút vẫn đủ to để bấm, # vẫn bên phải', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 780 });
    const state = freshState();
    await reachConfirm(page, state, { defect: 6 });

    expect(await expectConfirmOnTheRight(page, 'screen-finish-confirm')).toBe(1);
    const rows = await actionRows(page, 'screen-finish-confirm');
    for (const b of [...rows[0].back, ...rows[0].confirm]) {
      expect(b.height, `${b.id} quá thấp để bấm bằng ngón tay`).toBeGreaterThanOrEqual(44);
      expect(b.left).toBeGreaterThanOrEqual(-0.5);
      expect(b.right).toBeLessThanOrEqual(390.5);
    }
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, 'trang tràn ngang ở 390px').toBeLessThanOrEqual(0);
  });

  test('390px: các màn nhập số và màn hỏi lỗi sửa được cũng không tràn ngang', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 780 });
    const state = freshState();
    await openQuantityFlow(page, state);
    const noOverflow = async where => {
      const over = await page.evaluate(() =>
        document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over, `tràn ngang ở ${where}`).toBeLessThanOrEqual(0);
    };
    await noOverflow('SẢN PHẨM ĐẠT');
    expect(await expectConfirmOnTheRight(page, 'screen-quantity-good')).toBe(1);

    await typeQty(page, 'good-qty', 40);
    await page.locator('#good-next').click();
    await noOverflow('SẢN PHẨM LỖI');

    await typeQty(page, 'defect-qty', 6);
    await page.locator('#defect-next').click();
    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
    await noOverflow('CÓ LỖI SỬA ĐƯỢC?');

    await page.keyboard.press('1');
    await noOverflow('LỖI SỬA ĐƯỢC');
    expect(await expectConfirmOnTheRight(page, 'screen-quantity-rework')).toBe(1);
  });
});
