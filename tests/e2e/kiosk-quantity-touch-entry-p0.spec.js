// P0 vòng 2 (xưởng vẫn báo sau 71.0.0.287): nhập Đạt/Lỗi xong, màn XÁC NHẬN
// vẫn hiện 0/0 và bước "CÓ LỖI SỬA ĐƯỢC?" vẫn không ra.
//
// Vòng 1 (c9a4322) đã bỏ được phụ thuộc focus cho đường `keydown`. Chỗ còn hở:
//
//  1. Bàn phím MỀM / IME / dán / đọc chính tả KHÔNG gửi keydown mang chữ số
//     (Gboard bắn key='Unidentified', keyCode 229 rồi chèn chữ bằng
//     beforeinput/input). Đường đó vẫn rơi vào phần tử ĐANG FOCUS, nên ngay
//     sau khi chuyển màn -- lúc ô cũ vừa bị display:none làm mất focus -- chữ
//     số lại rơi mất y như trước. Người gõ bàn phím CỨNG không dính, nên mọi
//     bài cũ (kể cả bài gõ keyboard.press) đều xanh trong khi xưởng vẫn hỏng.
//
//  2. Ô rỗng bị đọc thành 0 (`Number('') === 0`) nên một lần rơi phím đi thẳng
//     vào sản lượng như số 0 hợp lệ, KHÔNG báo lỗi; và defect=0 làm
//     nextDefect() bỏ luôn bước hỏi sửa được -- đúng hai triệu chứng đã báo.
//
// (Ghi nhận riêng, KHÔNG sửa ở lane này: ba màn nhập xếp nút "TIẾP TỤC" gần
//  trùng toạ độ nên một cú double-tap đi xuyên hai màn tới thẳng Confirm 0/0.
//  Đó là khuyết tật BỐ CỤC, chặn bằng hẹn giờ sẽ nuốt cả cú bấm hợp lệ và làm
//  đỏ bộ kiosk-esp-parity -- phải sửa bằng cách bỏ chồng toạ độ, lane UI.)
//
// Vì vậy các bài dưới đây bấm bằng CLICK/TAP THẬT (không dùng Enter để sang
// màn) và nhập bằng cả hai đường: phím cứng và bàn phím mềm.
//
// CHỨNG MINH NGƯỢC: chạy lại chính file này với
//   MESFLOW_KIOSK_JS=$(git show c9a4322:app/mesflow/web/static/kiosk.js > /tmp/old.js; echo /tmp/old.js) npx playwright test tests/e2e/kiosk-quantity-touch-entry-p0.spec.js
// -> các bài bàn phím mềm và double-tap phải ĐỎ.
const fs = require('fs');
const { test, expect, devices } = require('@playwright/test');

const OVERRIDE_JS = process.env.MESFLOW_KIOSK_JS || '';
const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ Chín' };
const OPEN_SESSION = { id: 555, operation_code:'OP-77', operation_name:'Chấn', operation_display_key:'OP-77', operation_type:'PRODUCTION' };

async function mockKiosk(page, state) {
  if (OVERRIDE_JS) {
    const body = fs.readFileSync(OVERRIDE_JS, 'utf8');
    await page.route(/\/static\/kiosk\.js/, r => r.fulfill({ contentType:'application/javascript; charset=utf-8', body }));
  }
  await page.route(/\/api\/kiosk-web\/heartbeat/, r => r.fulfill({ json:{ ok:true } }));
  await page.route(/\/api\/kiosk-web\/scan/, r => {
    const qr = String((r.request().postDataJSON()||{}).qr||'');
    if (qr.startsWith('WF|EMP|')) return r.fulfill({ json:{ ok:true, type:'employee', employee:EMPLOYEE, open_session:OPEN_SESSION } });
    return r.fulfill({ json:{ ok:true, type:'operation', operation:{ id:77, code:'OP-77', name:'Chấn' } } });
  });
  await page.route(/\/api\/kiosk-web\/finish/, r => {
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

const active  = page => page.evaluate(() => document.querySelector('.screen.active')?.id);
const summary = page => page.evaluate(() => document.getElementById('finish-confirm-summary')?.innerText || '');

// Bàn phím MỀM / IME: keydown KHÔNG mang chữ số, chữ tới bằng input.
// Đây là đường mà bản vá theo-state của vòng 1 không đỡ được.
const softType = (page, digits) => page.evaluate(async text => {
  for (const ch of String(text)) {
    document.activeElement.dispatchEvent(new KeyboardEvent('keydown', { key:'Unidentified', keyCode:229, bubbles:true }));
    const el = document.activeElement;
    if (el && 'value' in el) {
      el.value = String(el.value || '') + ch;
      el.dispatchEvent(new InputEvent('input', { data:ch, inputType:'insertText', bubbles:true }));
    }
    await new Promise(r => setTimeout(r, 10));
  }
}, digits);

const hardType = async (page, digits) => { for (const ch of String(digits)) await page.keyboard.press(ch); };

// Một nhịp ngắn để trình duyệt vẽ xong màn mới trước bước kế.
const beat = page => page.waitForTimeout(60);

// Đi hết luồng bằng CHẠM/CLICK, nhập bằng `type` được truyền vào.
async function runFlow(page, state, { good, defect, rework, type }) {
  await toQtyGood(page, state);
  await page.click('#good-qty');
  await type(page, good);
  // Trên máy thật, chuyển màn làm ô cũ mất focus và ô mới không chắc nhận
  // được -- ép đúng điều kiện đó thay vì tin vào may rủi của trình duyệt.
  await beat(page); await page.click('#good-next');
  await page.evaluate(() => document.activeElement?.blur());
  await type(page, defect);
  await beat(page); await page.click('#defect-next');
  if (await active(page) === 'screen-ask-rework') {
    if (rework === null) { await beat(page); await page.click('#rework-none'); }
    else {
      await beat(page); await page.click('#rework-yes');
      await page.evaluate(() => document.activeElement?.blur());
      await type(page, rework);
      await beat(page); await page.click('#rework-next');
    }
  }
  await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
}

for (const [label, typeFn] of [['bàn phím mềm/IME', softType], ['bàn phím cứng', hardType]]) {
  test(`[${label}] 8 đạt / 2 NG / sửa 1: XÁC NHẬN hiện đúng số và payload 8/2/1`, async ({ page }) => {
    const st = { finished: [] };
    await runFlow(page, st, { good:'8', defect:'2', rework:'1', type:typeFn });
    expect(await page.locator('#good-qty').inputValue()).toBe('8');
    expect(await page.locator('#defect-qty').inputValue()).toBe('2');
    const s = await summary(page);
    expect(s, 'màn XÁC NHẬN phải hiện đúng số vừa nhập, không phải 0').toContain('8');
    expect(s).toContain('2');
    expect(s).toContain('1');
    await beat(page); await page.click('#finish-confirm-ok');
    await expect.poll(() => st.finished.length).toBe(1);
    expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:2, rework_qty:1 });
  });

  test(`[${label}] 8 đạt / 2 NG: bước CÓ LỖI SỬA ĐƯỢC phải xuất hiện`, async ({ page }) => {
    const st = { finished: [] };
    await toQtyGood(page, st);
    await page.click('#good-qty'); await typeFn(page, '8');
    await beat(page); await page.click('#good-next');
    await page.evaluate(() => document.activeElement?.blur());
    await typeFn(page, '2');
    await beat(page); await page.click('#defect-next');
    expect(await active(page), 'NG=2 > 0 nên phải hỏi sửa được').toBe('screen-ask-rework');
  });

  test(`[${label}] 8 đạt / 0 NG: bỏ qua hỏi sửa được, payload 8/0/0`, async ({ page }) => {
    const st = { finished: [] };
    await runFlow(page, st, { good:'8', defect:'0', rework:null, type:typeFn });
    expect(await summary(page)).toContain('8');
    await beat(page); await page.click('#finish-confirm-ok');
    await expect.poll(() => st.finished.length).toBe(1);
    expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:0, rework_qty:0 });
  });

  test(`[${label}] 0 đạt / 2 NG: payload 0/2/0`, async ({ page }) => {
    const st = { finished: [] };
    await runFlow(page, st, { good:'0', defect:'2', rework:null, type:typeFn });
    await beat(page); await page.click('#finish-confirm-ok');
    await expect.poll(() => st.finished.length).toBe(1);
    expect(st.finished[0]).toMatchObject({ good_qty:0, defect_qty:2, rework_qty:0 });
  });

  test(`[${label}] sửa số bằng Backspace rồi nhập lại: 12 -> 5`, async ({ page }) => {
    const st = { finished: [] };
    await toQtyGood(page, st);
    await page.click('#good-qty'); await typeFn(page, '12');
    expect(await page.locator('#good-qty').inputValue()).toBe('12');
    await page.keyboard.press('Backspace'); await page.keyboard.press('Backspace');
    await typeFn(page, '5');
    expect(await page.locator('#good-qty').inputValue(), 'sửa số không được để lại chữ số cũ').toBe('5');
    await beat(page); await page.click('#good-next');
    await page.evaluate(() => document.activeElement?.blur());
    await typeFn(page, '3');
    await beat(page); await page.click('#defect-next');
    await beat(page); await page.click('#rework-none');
    await beat(page); await page.click('#finish-confirm-ok');
    await expect.poll(() => st.finished.length).toBe(1);
    expect(st.finished[0]).toMatchObject({ good_qty:5, defect_qty:3, rework_qty:0 });
  });
}

test('mobile (Pixel 7, chạm thật + bàn phím mềm): 8/2/1 tới đúng payload', async ({ browser }) => {
  const context = await browser.newContext({ ...devices['Pixel 7'] });
  const page = await context.newPage();
  const st = { finished: [] };
  await runFlow(page, st, { good:'8', defect:'2', rework:'1', type:softType });
  const s = await summary(page);
  expect(s).toContain('8'); expect(s).toContain('2'); expect(s).toContain('1');
  await beat(page); await page.tap('#finish-confirm-ok');
  await expect.poll(() => st.finished.length).toBe(1);
  expect(st.finished[0]).toMatchObject({ good_qty:8, defect_qty:2, rework_qty:1 });
  await context.close();
});
