// Kiosk web: luồng mô phỏng quét QR không được nhảy layout vì loading.
//
// Hồi quy thật đã xảy ra: #demo-loading là một khối chữ "Đang tải dữ liệu..."
// nằm trong luồng, ngay TRÊN #demo-content. loadDemoData() bật nó lên ở MỌI
// lần gọi -- kể cả lần tự làm mới 10 giây/lần chạy trong lúc người ta đang
// quét -- nên toàn bộ select / nút / ô QR bị đẩy xuống ~70px rồi nhảy ngược
// lên khi response về. Nút "Tải lại danh sách" còn tệ hơn: nó đặt
// demoLoaded=false, làm #demo-content bị ẩn hẳn -> bảng trắng rồi dựng lại.
//
// Spec này chốt bốn điều, ở cả desktop lẫn tablet/mobile:
//   1. Không có chữ "Đang tải dữ liệu..." nào xuất hiện trong suốt luồng.
//   2. Đo bounding box vùng chính TRƯỚC / TRONG / SAU một request bị làm chậm:
//      dịch chuyển dọc phải ~0.
//   3. Làm mới không bao giờ làm trắng/thu nhỏ bảng -- giữ state cũ tới khi có
//      response.
//   4. Quét liên tục employee -> operation -> qty/NG -> finish: không cú nhảy
//      dọc nào do loading.
const { test, expect } = require('@playwright/test');

const LOADING_TEXT = 'Đang tải dữ liệu';
// Ngưỡng đo: 1px cho sai số làm tròn subpixel của trình duyệt. Bug cũ dịch ~70px.
const SHIFT_TOLERANCE = 1;

const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' };
const OPERATION = {
  id: 4242, code: 'OP01', display_key: 'PA-OP01', name: 'CẮT LASER', qr: 'WF|OP|OP01',
  operation_type: 'PRODUCTION', part_code: 'PA', po_code: 'PO-777', po_status: 'IN_PROGRESS',
  status: 'IN_PROGRESS', plan_qty: 100, done_qty: 0, defect_qty: 0,
};
const OPEN_SESSION = {
  id: 555, operation_id: OPERATION.id, operation_code: OPERATION.code,
  operation_display_key: OPERATION.display_key, operation_name: OPERATION.name,
  operation_type: 'PRODUCTION', started_at: '2026-09-11T04:00:00Z', plan_qty: 100,
};

const VIEWPORTS = [
  { name: 'desktop', size: { width: 1280, height: 900 } },
  { name: 'tablet', size: { width: 820, height: 1180 } },
  { name: 'mobile', size: { width: 390, height: 844 } },
];

function freshState() {
  return { hasOpenSession: false, demoDelayMs: 0, demoStatus: 200, demoCalls: 0, finished: [] };
}

async function mockKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/scan/, route => {
    const qr = String((route.request().postDataJSON() || {}).qr || '');
    if (qr.startsWith('WF|EMP|')) {
      return route.fulfill({ json: { ok: true, type: 'employee', employee: EMPLOYEE,
        open_session: state.hasOpenSession ? OPEN_SESSION : null } });
    }
    return route.fulfill({ json: { ok: true, type: 'operation', operation: OPERATION } });
  });
  await page.route(/\/api\/kiosk-web\/start/, route => {
    state.hasOpenSession = true;
    return route.fulfill({ json: { ok: true, session: { id: 556 } } });
  });
  await page.route(/\/api\/kiosk-web\/finish/, route => {
    state.finished.push(route.request().postDataJSON() || {});
    state.hasOpenSession = false;
    return route.fulfill({ json: { ok: true, session: { id: 555, status: 'CLOSED' } } });
  });
  // Đường request cần đo: độ trễ và mã lỗi do từng test điều khiển.
  await page.route(/\/api\/kiosk-web\/demo-data/, async route => {
    state.demoCalls += 1;
    if (state.demoDelayMs) await new Promise(r => setTimeout(r, state.demoDelayMs));
    if (state.demoStatus !== 200) {
      return route.fulfill({ status: state.demoStatus, json: { ok: false, error: 'SYS-500' } });
    }
    return route.fulfill({ json: { ok: true,
      employees: [{ ...EMPLOYEE, qr: 'WF|EMP|NV-009' }], operations: [OPERATION] } });
  });
  await page.route(/\/api\/kiosk-web\/heartbeat/, route => route.fulfill({ json: { ok: true } }));
}

async function openKiosk(page, state, viewport, {clock = false} = {}) {
  await page.setViewportSize(viewport);
  await mockKiosk(page, state);
  // Đồng hồ giả phải cắm TRƯỚC goto thì setInterval của trang mới đi qua nó.
  if (clock) await page.clock.install();
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
}

// Gõ từng chữ số qua bàn phím thật: màn nhập số của kiosk tự bắt phím, không
// đi qua fill()/type() trên input (xem kiosk-quantity-entry-p0.spec.js).
async function typeDigits(page, digits) {
  for (const ch of String(digits)) await page.keyboard.press(ch);
}

async function openDemoPanel(page) {
  await page.evaluate(() => window.MESFlowKioskDemo.open());
  // "Sẵn sàng" = đã có mã để chọn. Cố ý KHÔNG đọc data-demo-state ở đây: bài
  // đo phải chạy được y hệt trên bản CHƯA sửa, nếu không "revert thì đỏ" chỉ
  // chứng minh là thiếu markup mới, chứ không chứng minh được nó bắt cú nhảy.
  await expect(page.locator('#demo-employee option')).not.toHaveCount(0);
  await expect(page.locator('#demo-content')).toBeVisible();
  await settle(page);
}

// Chờ mock NHẬN được request (route handler tăng bộ đếm trước khi ngủ), nên ta
// đo đúng lúc request đang bay -- không phải đoán bằng một khoảng chờ cứng.
async function waitForDemoCall(state, target, timeoutMs = 5000) {
  const deadline = Date.now() + timeoutMs;
  while (state.demoCalls < target) {
    if (Date.now() > deadline) throw new Error(`demo-data không được gọi tới lần ${target}`);
    await new Promise(r => setTimeout(r, 20));
  }
}

// Ép trình duyệt layout + paint xong rồi mới đo.
async function settle(page) {
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
}

// Mốc đo: đỉnh của từng vùng chính. Loading chỉ được phép không đụng tới chúng.
// `.screen.active` luôn là màn đang hiện: nó phải giữ NGUYÊN khung dù luồng đi
// tới bước nào (.screen{flex:1} trong cột min-height:100dvh), nên so sánh giữa
// các bước vẫn có nghĩa. Phần còn lại là các control trong bảng mô phỏng.
const PROBES = ['.screen.active', '.kiosk-shell footer', '#demo-content',
  '#demo-employee', '#demo-operation', '#demo-refresh'];

async function measure(page) {
  const out = {};
  for (const selector of PROBES) {
    const box = await page.locator(selector).first().boundingBox().catch(() => null);
    if (box) out[selector] = box;
  }
  out.__scrollHeight = await page.evaluate(() => document.documentElement.scrollHeight);
  return out;
}

function assertNoShift(before, after, label) {
  for (const key of Object.keys(before)) {
    if (key === '__scrollHeight') {
      expect(Math.abs(after[key] - before[key]),
        `${label}: chiều cao tài liệu đổi ${before[key]} -> ${after[key]}`).toBeLessThanOrEqual(SHIFT_TOLERANCE);
      continue;
    }
    // Probe đo được trước mà sau lại không đo được nghĩa là nó vừa bị ẩn/gỡ --
    // đúng kiểu "blank rồi render lại". Bỏ qua ở đây thì bài đo mù hẳn.
    expect(Boolean(after[key]),
      `${label}: "${key}" biến mất khỏi layout (bị ẩn/blank giữa chừng)`).toBe(true);
    expect(Math.abs(after[key].y - before[key].y),
      `${label}: "${key}" dịch dọc ${before[key].y} -> ${after[key].y}`).toBeLessThanOrEqual(SHIFT_TOLERANCE);
    expect(Math.abs(after[key].height - before[key].height),
      `${label}: "${key}" đổi chiều cao ${before[key].height} -> ${after[key].height}`).toBeLessThanOrEqual(SHIFT_TOLERANCE);
  }
}

// Chữ chờ không được xuất hiện ở BẤT KỲ đâu trong DOM đang hiển thị.
async function expectNoLoadingText(page, label) {
  const found = await page.evaluate(t => document.body.innerText.includes(t), LOADING_TEXT);
  expect(found, `${label}: vẫn thấy chữ "${LOADING_TEXT}" trong luồng quét`).toBe(false);
  await expect(page.locator(`text=${LOADING_TEXT}`)).toHaveCount(0);
}

for (const { name, size } of VIEWPORTS) {
  test.describe(`kiosk ${name} (${size.width}x${size.height})`, () => {
    test('làm mới dữ liệu mô phỏng: không nhảy layout, không chữ chờ', async ({ page }) => {
      const state = freshState();
      await openKiosk(page, state, size);
      await openDemoPanel(page);

      const before = await measure(page);
      await expectNoLoadingText(page, 'trước request');

      // Request chậm 1,2 giây: đủ dài để đo được "trong lúc chờ".
      state.demoDelayMs = 1200;
      const callsBefore = state.demoCalls;
      const reload = page.evaluate(() => window.MESFlowKioskDemo.reload());

      await waitForDemoCall(state, callsBefore + 1);
      await settle(page);
      const during = await measure(page);
      assertNoShift(before, during, 'trong lúc chờ');
      await expectNoLoadingText(page, 'trong lúc chờ');
      // Giữ state cũ: danh sách vẫn nguyên, không bị ẩn/xoá trong lúc chờ.
      await expect(page.locator('#demo-content')).toBeVisible();
      await expect(page.locator('#demo-employee option')).toHaveCount(1);

      await reload;
      await settle(page);
      expect(state.demoCalls).toBeGreaterThan(callsBefore);

      const after = await measure(page);
      assertNoShift(before, after, 'sau request');
      await expectNoLoadingText(page, 'sau request');
    });

    test('quét liên tục employee -> operation -> qty/NG -> finish: không nhảy dọc do loading',
      async ({ page }) => {
      const state = freshState();
      // Mọi lần làm mới nền trong luồng đều chậm, để nếu có chỉ báo chiếm chỗ
      // thì chắc chắn nó đang hiện lúc ta đo.
      state.demoDelayMs = 400;
      await openKiosk(page, state, size);
      await openDemoPanel(page);

      const baseline = await measure(page);

      // 1) quét thẻ nhân viên -> màn QUÉT CÔNG ĐOẠN
      await page.evaluate(() => window.MESFlowKioskDemo.scanEmployee());
      await expect(page.locator('#screen-operation')).toHaveClass(/active/);
      await expectNoLoadingText(page, 'sau khi quét thẻ');

      // 2) quét công đoạn -> ĐANG BẮT ĐẦU -> ĐÃ BẮT ĐẦU
      await page.evaluate(() => window.MESFlowKioskDemo.scanOperation());
      await expect(page.locator('#screen-started')).toHaveClass(/active/);
      await expectNoLoadingText(page, 'sau khi quét công đoạn');
      assertNoShift(baseline, await measure(page), 'bảng mô phỏng sau khi bắt đầu');

      // 3) quét lại thẻ -> màn nhập sản lượng
      await page.evaluate(() => window.MESFlowKioskDemo.scanEmployee());
      await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
      const atQuantity = await measure(page);

      // Lần tự làm mới nền 10 giây/lần chính là thủ phạm cũ: ép nó chạy ngay
      // giữa lúc người ta đang nhập số và đo xem có đẩy gì không.
      const callsAtQuantity = state.demoCalls;
      const reload = page.evaluate(() => window.MESFlowKioskDemo.reload());
      await waitForDemoCall(state, callsAtQuantity + 1);
      await settle(page);
      assertNoShift(atQuantity, await measure(page), 'làm mới giữa lúc nhập sản lượng');
      await expectNoLoadingText(page, 'giữa lúc nhập sản lượng');
      await reload;
      await settle(page);
      assertNoShift(atQuantity, await measure(page), 'sau khi làm mới giữa lúc nhập sản lượng');

      // 4) nhập đạt/lỗi rồi xác nhận -- GÕ BÀN PHÍM như bàn phím số của trạm
      // (cùng lối với kiosk-quantity-entry-p0.spec.js), và bảng mô phỏng vẫn
      // mở suốt: đó đúng là tình huống "quét liên tục" mà bug cũ phá.
      await typeDigits(page, '12'); await page.keyboard.press('Enter');
      await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);
      await expectNoLoadingText(page, 'màn sản phẩm lỗi');
      assertNoShift(atQuantity, await measure(page), 'bảng mô phỏng ở màn sản phẩm lỗi');

      await typeDigits(page, '0'); await page.keyboard.press('Enter');
      await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);
      await expectNoLoadingText(page, 'màn xác nhận');

      // Gửi finish với một lần làm mới nền chen ngang đúng lúc đang gửi.
      const beforeSubmit = await measure(page);
      state.demoDelayMs = 600;
      const reloadAtSubmit = page.evaluate(() => window.MESFlowKioskDemo.reload());
      await page.keyboard.press('Enter');
      await expect(page.locator('#screen-finished')).toHaveClass(/active/);
      await reloadAtSubmit;
      await expectNoLoadingText(page, 'sau khi ghi nhận');
      assertNoShift(beforeSubmit, await measure(page), 'bảng mô phỏng sau khi ghi nhận');
      expect(state.finished.length, 'finish phải gửi đúng một lần').toBe(1);
    });

    // Bài đo THẲNG VÀO thủ phạm: setInterval 10 giây/lần của chính trang, chạy
    // trong lúc bảng đang mở giữa luồng quét. Đây là đường mà bản cũ vẫn để
    // #demo-content HIỆN rồi chèn khối chờ lên TRÊN nó -- tức là cú nhảy dọc
    // người dùng nhìn thấy, không phải cảnh blank.
    test('tự làm mới nền 10 giây/lần: không đẩy layout một pixel nào', async ({ page }) => {
      const state = freshState();
      await openKiosk(page, state, size, {clock: true});
      await openDemoPanel(page);

      const before = await measure(page);
      const callsBefore = state.demoCalls;

      state.demoDelayMs = 3000;            // vẫn đang bay khi ta đo
      await page.clock.runFor(10_000);     // đúng chu kỳ tự làm mới
      await waitForDemoCall(state, callsBefore + 1);
      await settle(page);

      assertNoShift(before, await measure(page), 'giữa lúc tự làm mới nền');
      await expectNoLoadingText(page, 'giữa lúc tự làm mới nền');
    });

    test('lỗi tải dữ liệu: giữ nguyên danh sách cũ, error nhỏ không đẩy control nào',
      async ({ page }) => {
      const state = freshState();
      await openKiosk(page, state, size);
      await openDemoPanel(page);

      const before = await measure(page);
      const callsBefore = state.demoCalls;
      state.demoStatus = 500;
      await page.evaluate(() => window.MESFlowKioskDemo.reload());
      await waitForDemoCall(state, callsBefore + 1);
      await settle(page);

      // Danh sách cũ còn nguyên -- không blank/reset.
      await expect(page.locator('#demo-content')).toBeVisible();
      await expect(page.locator('#demo-employee option')).toHaveCount(1);
      await expectNoLoadingText(page, 'sau khi lỗi');

      // Error là phần tử cuối bảng: mọi control phía trên phải đứng yên. Bản
      // cũ nhét thẳng câu lỗi vào khối chờ NẰM TRÊN danh sách, nên chính dòng
      // này đỏ khi revert.
      const after = await measure(page);
      for (const key of ['#demo-employee', '#demo-operation', '#demo-refresh', '#demo-content']) {
        if (!before[key] || !after[key]) continue;
        expect(Math.abs(after[key].y - before[key].y),
          `error đẩy "${key}" ${before[key].y} -> ${after[key].y}`).toBeLessThanOrEqual(SHIFT_TOLERANCE);
      }
      await expect(page.locator('#demo-error')).toBeVisible();
    });
  });
}

test('chỉ báo chờ không chiếm chỗ trong luồng và bảng không bao giờ bị ẩn', async ({ page }) => {
  const state = freshState();
  await openKiosk(page, state, VIEWPORTS[0].size);
  await openDemoPanel(page);

  state.demoDelayMs = 800;
  const reload = page.evaluate(() => window.MESFlowKioskDemo.reload());
  await expect(page.locator('#demo-panel')).toHaveAttribute('data-demo-state', 'loading');

  // Thanh chờ phải là phần tử absolute (không chiếm chỗ) và mỏng.
  const busy = await page.evaluate(() => {
    const el = document.getElementById('demo-busy');
    if (!el) return null;
    const cs = getComputedStyle(el);
    return { position: cs.position, height: el.getBoundingClientRect().height };
  });
  expect(busy, '#demo-busy phải tồn tại làm chỉ báo không-layout').not.toBeNull();
  expect(busy.position, 'chỉ báo chờ phải absolute để không đẩy layout').toBe('absolute');
  expect(busy.height, 'chỉ báo chờ phải mỏng').toBeLessThanOrEqual(4);

  // Trong lúc chờ, thao tác bị khoá thay vì bị thay bằng màn loading.
  await expect(page.locator('#demo-refresh')).toBeDisabled();
  await expect(page.locator('#demo-content')).toBeVisible();

  await reload;
  await expect(page.locator('#demo-refresh')).toBeEnabled();
  await expect(page.locator('#demo-panel')).toHaveAttribute('data-demo-state', 'ready');
});
