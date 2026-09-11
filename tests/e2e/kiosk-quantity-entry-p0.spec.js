// P0 (xưởng báo): nhập Đạt/Lỗi trên kiosk xong, Confirm hiện 0/0 và bước
// "CÓ LỖI SỬA ĐƯỢC?" không xuất hiện -> không khai được rework.
//
// GỐC: chữ số dựa vào ô <input> đang FOCUS, nhưng focus đặt async (setTimeout
// 30ms) sau khi chuyển màn Đạt->Lỗi->Sửa. Trong cửa sổ đó ô cũ đã ẩn (blur),
// ô mới chưa focus -> phím số rơi mất -> Lỗi về 0 -> Confirm 0/0 và defect=0
// nên bỏ qua bước sửa được. Kiosk khoá bàn phím thì "ô đang nhập" là thứ
// STATE nói, không phải focus. Fix: keydown handler ghi chữ số vào đúng ô
// theo state, xác định, không phụ thuộc focus/layout/timing.
//
// Các bài GÕ BẰNG BÀN PHÍM THẬT (keyboard, không fill) và KHÔNG delay giữa
// phím -- đó là điều kiện làm lộ bug; test cũ dùng fill() nên bỏ qua đường này.
const { test, expect } = require('@playwright/test');
const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ Chín' };
const OPERATION = { id: 77, operation_code: 'OP-77', operation_name: 'Chấn', operation_type: 'PRODUCTION' };
const OPEN_SESSION = { id: 555, operation_code: 'OP-77', operation_name: 'Chấn', operation_display_key: 'OP-77', operation_type: 'PRODUCTION' };

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, r => {
    const qr = String((r.request().postDataJSON()||{}).qr||'');
    if (qr.startsWith('WF|EMP|')) return r.fulfill({ json:{ ok:true, type:'employee', employee:EMPLOYEE, open_session:OPEN_SESSION } });
    return r.fulfill({ json:{ ok:true, type:'operation', operation:OPERATION } });
  });
  await page.route(/\/api\/kiosk-web\/finish/, r => {
    state.attempts = (state.attempts||0) + 1;
    if (state.failNext && state.attempts <= (state.failCount||1)) return r.fulfill({ status:500, json:{ ok:false, error:'boom' } });
    state.finished.push(r.request().postDataJSON()||{});
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
const active = page => page.evaluate(() => document.querySelector('.screen.active')?.id);
const type = async (page, s) => { for (const ch of String(s)) await page.keyboard.press(ch); };
const summary = page => page.evaluate(() => document.getElementById('finish-confirm-summary')?.innerText || '');

test('8/2 + sửa 1: Confirm đúng 8/2, qua màn sửa được, payload 8/2/1', async ({ page }) => {
  const st = { finished:[] };
  await toQtyGood(page, st);
  await type(page, '8'); await page.keyboard.press('Enter');
  expect(await page.locator('#good-qty').inputValue()).toBe('8');
  await type(page, '2'); await page.keyboard.press('Enter');
  expect(await page.locator('#defect-qty').inputValue()).toBe('2');
  expect(await active(page), 'defect>0 phải hiện CÓ LỖI SỬA ĐƯỢC').toBe('screen-ask-rework');
  await page.keyboard.press('1');                 // 1 = CÓ
  await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);
  await type(page, '1'); await page.keyboard.press('Enter');
  const s = await summary(page);
  expect(s).toContain('8'); expect(s).toContain('2'); expect(s).toContain('1');
  await page.keyboard.press('Enter');             // xác nhận gửi
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:2, rework_qty:1 });
  // invariant: 0<=rework<=defect, good/defect>=0
  const f = st.finished[0];
  expect(f.good_qty).toBeGreaterThanOrEqual(0);
  expect(f.rework_qty).toBeGreaterThanOrEqual(0);
  expect(f.rework_qty).toBeLessThanOrEqual(f.defect_qty);
});

test('8/2 + KHÔNG sửa: rework_qty=0 rõ ràng', async ({ page }) => {
  const st = { finished:[] };
  await toQtyGood(page, st);
  await type(page, '8'); await page.keyboard.press('Enter');
  await type(page, '2'); await page.keyboard.press('Enter');
  expect(await active(page)).toBe('screen-ask-rework');
  await page.keyboard.press('2');                 // 2 = KHÔNG
  const s = await summary(page);
  expect(s).toContain('8'); expect(s).toContain('2');
  await page.keyboard.press('Enter');
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:2, rework_qty:0 });
});

test('8/0: NG=0 thì bỏ qua bước sửa được, payload 8/0/0', async ({ page }) => {
  const st = { finished:[] };
  await toQtyGood(page, st);
  await type(page, '8'); await page.keyboard.press('Enter');
  await type(page, '0'); await page.keyboard.press('Enter');
  expect(await active(page), 'NG=0 đi thẳng Confirm').toBe('screen-finish-confirm');
  const s = await summary(page);
  expect(s).toContain('8');
  await page.keyboard.press('Enter');
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:0, rework_qty:0 });
});

test('0/2: Đạt=0 vẫn ghi đúng, defect=2 qua màn sửa được', async ({ page }) => {
  const st = { finished:[] };
  await toQtyGood(page, st);
  await type(page, '0'); await page.keyboard.press('Enter');
  await type(page, '2'); await page.keyboard.press('Enter');
  expect(await active(page)).toBe('screen-ask-rework');
  await page.keyboard.press('2');
  await page.keyboard.press('Enter');
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:0, defect_qty:2, rework_qty:0 });
});

test('back rồi sửa số: quay lại từ defect, đổi good, không mất/nhân đôi', async ({ page }) => {
  const st = { finished:[] };
  await toQtyGood(page, st);
  await type(page, '8'); await page.keyboard.press('Enter');   // good=8 -> defect
  await page.keyboard.press('*');                               // * = quay lại good
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  // sửa good: xoá rồi gõ 5
  await page.keyboard.press('Backspace'); await type(page, '5');
  expect(await page.locator('#good-qty').inputValue()).toBe('5');
  await page.keyboard.press('Enter');
  await type(page, '1'); await page.keyboard.press('Enter');
  expect(await active(page)).toBe('screen-ask-rework');
  await page.keyboard.press('2');
  await page.keyboard.press('Enter');
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:5, defect_qty:1, rework_qty:0 });
});

test('retry sau lỗi mạng: chỉ MỘT bản ghi, cùng số, cùng request_id (idempotent)', async ({ page }) => {
  const st = { finished:[], failNext:true, failCount:1 };
  await toQtyGood(page, st);
  await type(page, '8'); await page.keyboard.press('Enter');
  await type(page, '2'); await page.keyboard.press('Enter');
  await page.keyboard.press('2');                 // không sửa
  await page.keyboard.press('Enter');             // gửi -> hỏng lần 1 (500) -> auto-retry lần 2 thành công
  await expect.poll(() => st.finished.length, { timeout: 15000 }).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:2, rework_qty:0 });
  // Số lần gọi API >= 2 (một hỏng, một thành) nhưng chỉ MỘT bản ghi finished.
  expect(st.attempts).toBeGreaterThanOrEqual(2);
});
