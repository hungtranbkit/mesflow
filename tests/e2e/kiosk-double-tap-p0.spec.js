// P0 (xưởng báo): trên Kiosk web, chạm liên tiếp ở MỘT CHỖ đi xuyên qua nhiều
// màn và kết thúc bằng "XÁC NHẬN 0/0" — sản lượng 0 được ghi mà không ai nhập.
//
// CƠ CHẾ, đo được trước khi sửa (không suy đoán). Một cú chạm sinh đúng một
// click (đã kiểm), nên đây là NHIỀU cú chạm thật. Vấn đề là nút "đi tiếp" của
// các màn liên tiếp CHỒNG VÙNG lên nhau tại cùng một toạ độ:
//
//   Pixel 7, x≈306:  good-next y 396–444 · defect-next y 418–466
//                    rework-next y 395–443 · finish-confirm-ok y 382–458
//   Desktop, x≈683:  good-next y 432–480 · defect-next y 453–501
//                    rework-next y 427–475 · finish-confirm-ok y 403–519
//
// Ngón tay không nhúc nhích: chạm 1 → quantity-defect, chạm 2 → finish-confirm
// (vì defect=0 bỏ qua ASK_REWORK, đúng firmware), chạm 3 → GỬI 0/0.
// Đi lọt được là vì số 0 DỰNG SẴN trong ô được đọc như một câu trả lời hợp lệ.
//
// SỬA (không có cửa sổ thời gian nào, không nuốt cú chạm hợp lệ nào):
//   1. TRẠNG THÁI — `qtyTouched`: số 0 hiển thị sẵn không phải câu trả lời.
//      Mọi đường nhập đều đánh dấu, kể cả bàn phím mềm/Gboard/IME đi bằng
//      beforeinput/input chứ không bằng keydown mang chữ số.
//   2. BỐ CỤC — hàng nút của màn XÁC NHẬN bị đẩy xuống đáy, nên vùng XÁC NHẬN
//      không còn giao với vùng TIẾP TỤC của bất kỳ màn nhập số nào.
const { test, expect, devices } = require('@playwright/test');
const { defaultBrowserType: _dbt, ...PIXEL7 } = devices['Pixel 7'];

const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ Chín' };
const OPEN_SESSION = { id: 555, operation_code:'OP-77', operation_name:'Chấn', operation_display_key:'OP-77', operation_type:'PRODUCTION' };

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, r => r.fulfill({
    json: { ok:true, type:'employee', employee:EMPLOYEE, open_session:OPEN_SESSION } }));
  await page.route(/\/api\/kiosk-web\/finish/, r => {
    state.finished.push(r.request().postDataJSON() || {});
    r.fulfill({ json:{ ok:true, session:{ id:555, status:'CLOSED' } } });
  });
}
async function toQtyGood(page, state) {
  await mockKiosk(page, state);
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
}
const activeScreen = page => page.evaluate(() => document.querySelector('.screen.active')?.id);
const centreOf = async (page, id) => {
  const b = await page.locator(`#${id}`).boundingBox();
  return [b.x + b.width / 2, b.y + b.height / 2];
};

/** Vùng dọc [top,bottom] của nút "đi tiếp" trên TỪNG màn, đo với đúng một màn
 *  hiện tại một thời điểm và bảng xác nhận đã có nội dung thật (bảng rỗng làm
 *  nút nằm cao hơn thực tế — đo như thế là tự lừa mình). */
const confirmBands = page => page.evaluate(() => {
  const map = {'screen-quantity-good':'good-next', 'screen-quantity-defect':'defect-next',
               'screen-quantity-rework':'rework-next', 'screen-finish-confirm':'finish-confirm-ok'};
  const all = [...document.querySelectorAll('.screen')];
  const was = all.filter(s => s.classList.contains('active')).map(s => s.id);
  document.getElementById('finish-confirm-summary').innerHTML =
    '<div><span>Đạt</span><strong>8</strong></div><div><span>NG</span><strong>2</strong></div>';
  const out = {};
  for (const [screenId, buttonId] of Object.entries(map)) {
    all.forEach(s => s.classList.toggle('active', s.id === screenId));
    const r = document.getElementById(buttonId).getBoundingClientRect();
    out[buttonId] = [Math.round(r.top), Math.round(r.bottom)];
  }
  all.forEach(s => s.classList.toggle('active', was.includes(s.id)));
  return out;
});

/** Gõ như BÀN PHÍM MỀM (Gboard/IME), không như bàn phím cứng: keydown mang
 *  key='Unidentified'/keyCode 229 và KHÔNG mang chữ số, chữ được chèn bằng
 *  beforeinput + input. Đây là đường mà mọi bài test gõ keyboard.press() bỏ
 *  sót — và là đường người dùng điện thoại thật sự đi. */
async function softKeyboardType(page, id, text) {
  await page.evaluate(([id, text]) => {
    const el = document.getElementById(id);
    el.focus();
    for (const ch of String(text)) {
      el.dispatchEvent(new KeyboardEvent('keydown', {key:'Unidentified', keyCode:229, which:229, bubbles:true}));
      el.dispatchEvent(new InputEvent('beforeinput', {inputType:'insertText', data:ch, bubbles:true, cancelable:true}));
      el.value = (el.value === '0' ? '' : el.value) + ch;
      el.dispatchEvent(new InputEvent('input', {inputType:'insertText', data:ch, bubbles:true}));
    }
  }, [id, text]);
}

for (const [label, viewport] of [['desktop', {}], ['Pixel 7', PIXEL7]]) {
  test.describe(label, () => {
    test.use(viewport);

    test(`${label}: chạm nhiều lần ở MỘT chỗ không đi xuyên màn và không gửi 0/0`, async ({ page }) => {
      const st = { finished: [] };
      await toQtyGood(page, st);
      const [cx, cy] = await centreOf(page, 'good-next');
      // Bốn lần, cùng một điểm, nhịp 150ms — đúng nhịp chạm lặp của người
      // tưởng máy chưa nhận. Trước khi sửa: chạm 3 đã GỬI 0/0.
      for (let i = 0; i < 4; i += 1) { await page.mouse.click(cx, cy); await page.waitForTimeout(150); }
      expect(await activeScreen(page), 'chạm lặp đã đi xuyên qua màn khác').toBe('screen-quantity-good');
      expect(st.finished, 'đã gửi sản lượng mà không ai nhập số').toEqual([]);
      // Cú chạm KHÔNG bị nuốt: nó vẫn chạy và vẫn nói cho người đứng máy biết
      // phải làm gì. Im lặng mới là nuốt.
      await expect(page.locator('#good-validation')).toHaveText(/Nhập số sản phẩm đạt/);
    });

    test(`${label}: vùng XÁC NHẬN không giao với vùng TIẾP TỤC của mọi màn nhập số`, async ({ page }) => {
      const st = { finished: [] };
      await toQtyGood(page, st);
      const bands = await confirmBands(page);
      const [okTop, okBottom] = bands['finish-confirm-ok'];
      for (const id of ['good-next', 'defect-next', 'rework-next']) {
        const [top, bottom] = bands[id];
        const overlaps = okTop < bottom && top < okBottom;
        expect(overlaps,
          `XÁC NHẬN [${okTop},${okBottom}] giao với ${id} [${top},${bottom}] -> một ngón tay đứng yên bấm gửi được`
        ).toBe(false);
      }
    });

    test(`${label}: nhập đủ rồi chạm đúp vẫn KHÔNG tự gửi`, async ({ page }) => {
      // Kể cả khi mọi số đều do người nhập thật, cú chạm thứ hai không được
      // thay người bấm XÁC NHẬN: bảng số sinh ra để người ĐỌC trước khi gửi.
      //
      // Đường đi ở đây là đường NGUY HIỂM NHẤT còn lại sau guard trạng thái:
      // NG = 0 nên bỏ qua "CÓ LỖI SỬA ĐƯỢC?" (đúng firmware) và nhảy thẳng
      // sang màn xác nhận với bảng 2 dòng — trước khi sửa bố cục, nút XÁC
      // NHẬN của bảng 2 dòng nằm đúng chồng lên nút TIẾP TỤC vừa bấm.
      const st = { finished: [] };
      await toQtyGood(page, st);
      await softKeyboardType(page, 'good-qty', '8');
      await page.locator('#good-next').click();
      await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
      await softKeyboardType(page, 'defect-qty', '0');

      const [cx, cy] = await centreOf(page, 'defect-next');
      await page.mouse.click(cx, cy); await page.waitForTimeout(60);
      await page.mouse.click(cx, cy); await page.waitForTimeout(250);   // cú thứ hai của cùng nhịp chạm đúp
      await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
      expect(st.finished, 'chạm đúp đã bấm XÁC NHẬN thay người').toEqual([]);
      // Và nút XÁC NHẬN vẫn bấm được bình thường — không có gì bị vô hiệu hoá.
      await page.locator('#finish-confirm-ok').click();
      await expect.poll(() => st.finished.length).toBe(1);
      expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:0, rework_qty:0 });
    });
  });
}

test('bàn phím mềm / Gboard / IME vẫn được tính là ĐÃ NHẬP', async ({ page }) => {
  // Đường beforeinput/input KHÔNG đi qua keydown mang chữ số. Nếu guard chỉ
  // nhận keydown thì người gõ bằng bàn phím điện thoại sẽ bị kẹt vĩnh viễn ở
  // màn nhập số — đó sẽ là "nuốt thao tác hợp lệ", đúng thứ phải tránh.
  const st = { finished: [] };
  await toQtyGood(page, st);
  await softKeyboardType(page, 'good-qty', '12');
  expect(await page.locator('#good-qty').inputValue()).toBe('12');
  await page.locator('#good-next').click();
  await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
  await softKeyboardType(page, 'defect-qty', '0');
  await page.locator('#defect-next').click();
  // NG = 0 -> bỏ qua "CÓ LỖI SỬA ĐƯỢC?" (đúng firmware, KIOSK_ESP_PARITY §1).
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
  await page.locator('#finish-confirm-ok').click();
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty: 12, defect_qty: 0, rework_qty: 0 });
});

test('số 0 do người THẬT SỰ bấm vẫn đi tiếp được', async ({ page }) => {
  // Guard chỉ phân biệt "chưa ai trả lời" với "trả lời là 0". Một ca thật sự
  // không có sản phẩm đạt phải đi tiếp được bằng đúng một phím.
  const st = { finished: [] };
  await toQtyGood(page, st);
  await page.keyboard.press('0');
  await page.locator('#good-next').click();
  await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
  await page.keyboard.press('3');
  await page.locator('#defect-next').click();
  await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);
});

test('bàn phím cứng: # liên tiếp cũng không đi xuyên màn', async ({ page }) => {
  // Cùng một lỗ hổng qua đường phím: Enter/# bấm liên tiếp trước đây cũng
  // chạy hết luồng bằng số 0 dựng sẵn.
  const st = { finished: [] };
  await toQtyGood(page, st);
  for (let i = 0; i < 4; i += 1) { await page.keyboard.press('Enter'); await page.waitForTimeout(60); }
  expect(await activeScreen(page)).toBe('screen-quantity-good');
  expect(st.finished).toEqual([]);
});

test('lượt mới không thừa hưởng số của lượt trước', async ({ page }) => {
  const st = { finished: [] };
  await toQtyGood(page, st);
  await softKeyboardType(page, 'good-qty', '77');
  await page.locator('#good-next').click();
  await softKeyboardType(page, 'defect-qty', '0');
  await page.locator('#defect-next').click();
  await page.locator('#finish-confirm-ok').click();
  await expect(page.locator('#screen-finished')).toHaveClass(/active/);

  // Người kế tiếp quét thẻ ngay trên màn kết quả: scan() từ 'finished' chạy
  // reset() rồi quét lại, nên đây đúng là lượt mới của một người mới.
  await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  expect(await page.locator('#good-qty').inputValue(), 'số của lượt trước còn trên màn').toBe('0');
  await page.locator('#good-next').click();
  expect(await activeScreen(page), 'số 0 thừa kế lại được coi là câu trả lời').toBe('screen-quantity-good');
});
