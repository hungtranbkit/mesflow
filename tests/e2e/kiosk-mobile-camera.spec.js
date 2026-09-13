// MOBILE KIOSK trên iPhone — chạy bằng WebKit THẬT, không phải Chromium thu nhỏ.
//
// Lý do dùng webkit: thiết bị đích là iPhone, và những thứ quyết định tính
// năng này khác nhau theo ENGINE chứ không theo kích thước khung nhìn --
// WebKit KHÔNG có BarcodeDetector (nên đường giải mã bằng JavaScript mới là
// đường chính trên iPhone, không phải đường dự phòng), không có
// navigator.vibrate, và <video> phải có playsinline.
//
// KHÔNG kiểm được ở đây, và đã ghi rõ trong docs: ảnh camera thật. Không có
// webcam trong CI và WebKit không có cờ "thiết bị media giả" như Chromium.
// Nên phần đọc ảnh -> ra chuỗi được thay bằng một stream giả, còn toàn bộ
// phần SAU khi đã có chuỗi -- chống trùng, đi vào đúng luồng, tắt phần cứng,
// bố cục -- đều chạy thật. Phần đọc ảnh thật thuộc về bài kiểm trên máy.
const fs = require('fs');
const path = require('path');
const { test, expect, devices } = require('@playwright/test');
const { webkit } = require('playwright');

//: Ảnh QR THẬT của chuỗi 'WF|EMP|NV-009', sinh bằng chính thư viện qrcode mà
//: máy chủ dùng để in tem. Dùng ảnh thật để chứng minh đúng thứ quan trọng
//: nhất với iPhone: jsQR ĐỌC ĐƯỢC một mã thật từ khung hình camera. Mọi bài
//: khác chỉ kiểm phần sau khi đã có chuỗi.
const QR_PNG_BASE64 = fs.readFileSync(
  path.join(__dirname, 'fixtures/qr-wf-emp-nv009.png')).toString('base64');

const IPHONE = devices['iPhone 13'];
const BASE = process.env.MESFLOW_BASE_URL || 'http://127.0.0.1:8080';

const EMPLOYEE = { id: 9, employee_no: 'NV-009', name: 'Thợ Chín' };
const OPERATION = { id: 77, code: 'OP-77', name: 'Chấn', display_key: 'OP-77' };
const OPEN_SESSION = { id: 555, operation_code: 'OP-77', operation_name: 'Chấn',
                       operation_display_key: 'OP-77', operation_type: 'PRODUCTION' };

let browser;
test.beforeAll(async () => { browser = await webkit.launch(); });
test.afterAll(async () => { await browser?.close(); });

// Bộ kiểm chạy trên http:// trong mạng container, mà getUserMedia chỉ tồn tại
// ở secure context -- nên trên máy chủ test, `navigator.mediaDevices` KHÔNG có
// thật. Đó là hành vi đúng của trình duyệt và chính là lý do Mobile Kiosk bắt
// buộc HTTPS. Bài ngay dưới khoá đúng điều đó ở môi trường thật; các bài còn
// lại mô phỏng một trang HTTPS để kiểm phần LOGIC camera.
/** Giả lập điều kiện của một trang HTTPS có camera sau lưng. */
const HTTPS_LIKE = () => {
  Object.defineProperty(window, 'isSecureContext', { get: () => true, configurable: true });
};

/** Stream giả từ canvas: đủ để <video> có srcObject và track để dừng. */
const FAKE_CAMERA = () => {
  Object.defineProperty(window, 'isSecureContext', { get: () => true, configurable: true });
  const canvas = document.createElement('canvas');
  canvas.width = 320; canvas.height = 240;
  canvas.getContext('2d').fillRect(0, 0, 320, 240);
  window.__cameraStops = 0;
  // Trên origin http thì navigator.mediaDevices KHÔNG tồn tại; trên origin
  // https nó tồn tại và CHỈ ĐỌC. Gán thẳng chỉ ăn ở trường hợp đầu, nên phải
  // defineProperty để bài chạy được cả khi trỏ vào bản đã deploy.
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: {
      getUserMedia: async () => {
        const stream = canvas.captureStream(5);
        stream.getTracks().forEach(track => {
          const stop = track.stop.bind(track);
          track.stop = () => { window.__cameraStops += 1; stop(); };
        });
        return stream;
      },
      enumerateDevices: async () => ([{ kind: 'videoinput', deviceId: 'back', label: 'Back' }]),
    },
  });
};

async function openKiosk(page, state) {
  await page.route(/\/api\/kiosk-web\/heartbeat/, r => r.fulfill({ json: { ok: true } }));
  await page.route(/\/api\/kiosk-web\/scan/, r => {
    const qr = String((r.request().postDataJSON() || {}).qr || '');
    state.scans.push(qr);
    if (qr.startsWith('WF|EMP|'))
      return r.fulfill({ json: { ok: true, type: 'employee', employee: EMPLOYEE, open_session: null } });
    return r.fulfill({ json: { ok: true, type: 'operation', operation: OPERATION } });
  });
  await page.route(/\/api\/kiosk-web\/start/, r => r.fulfill({ json: { ok: true, session: { id: 555 } } }));
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo && !!window.KioskCamera);
}

const phone = () => browser.newContext({ ...IPHONE, baseURL: BASE });

// --- iPhone thật sự cần đường giải mã bằng JavaScript --------------------

test('WebKit không có BarcodeDetector — nên bộ giải mã JS là đường CHÍNH trên iPhone', async () => {
  const context = await phone();
  const page = await context.newPage();
  await openKiosk(page, { scans: [] });
  expect(await page.evaluate(() => 'BarcodeDetector' in window)).toBe(false);
  await context.close();
});

test('nút camera hiện hay ẩn ĐÚNG THEO việc origin có bảo mật hay không', async () => {
  const context = await phone();
  const page = await context.newPage();
  await openKiosk(page, { scans: [] });
  // Không stub gì: đây là điều kiện THẬT của origin đang chạy bài. Máy chủ
  // test nội bộ là http (không có mediaDevices); bản đã deploy là https (có).
  // Một bài chỉ đúng ở một trong hai thì khi trỏ vào bản deploy sẽ đỏ vì lý do
  // không liên quan -- nên khoá đúng LUẬT: có camera thì hiện nút, không có
  // thì ẩn, không bao giờ hiện một nút bấm vào là báo lỗi.
  const secure = await page.evaluate(() => window.isSecureContext);
  const hasMedia = await page.evaluate(() => !!navigator.mediaDevices);
  expect(hasMedia, 'mediaDevices chỉ tồn tại ở secure context').toBe(secure);
  if (hasMedia) await expect(page.getByTestId('kiosk-camera-toggle')).toBeVisible();
  else await expect(page.getByTestId('kiosk-camera-toggle')).toBeHidden();
  await context.close();
});

test('có camera và HTTPS thì nút "Camera điện thoại" hiện ra', async () => {
  const context = await phone();
  const page = await context.newPage();
  await page.addInitScript(FAKE_CAMERA);
  await openKiosk(page, { scans: [] });
  await expect(page.getByTestId('kiosk-camera-toggle')).toBeVisible();
  await context.close();
});

// --- mã đọc được đi vào ĐÚNG luồng cũ ------------------------------------

test('mã camera đọc được đi qua /api/kiosk-web/scan như máy quét USB', async () => {
  const context = await phone();
  const page = await context.newPage();
  const state = { scans: [] };
  await openKiosk(page, state);
  await page.evaluate(() => window.KioskCamera.emitForTest('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  expect(state.scans).toEqual(['WF|EMP|NV-009']);
  await context.close();
});

test('cùng một mã trong cửa sổ chống trùng chỉ gửi MỘT lần', async () => {
  const context = await phone();
  const page = await context.newPage();
  const state = { scans: [] };
  await openKiosk(page, state);
  await page.evaluate(() => {
    for (let i = 0; i < 8; i += 1) window.KioskCamera.emitForTest('WF|EMP|NV-009');
  });
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  await page.waitForTimeout(300);
  expect(state.scans, `giơ máy một lần không được thành ${state.scans.length} lần quét`)
    .toEqual(['WF|EMP|NV-009']);
  await context.close();
});

test('mã KHÁC được nhận ngay, không phải chờ hết cửa sổ chống trùng', async () => {
  const context = await phone();
  const page = await context.newPage();
  const state = { scans: [] };
  await openKiosk(page, state);
  await page.evaluate(() => window.KioskCamera.emitForTest('WF|EMP|NV-009'));
  await expect(page.locator('#screen-operation')).toHaveClass(/active/);
  // Quét thẻ rồi quét công đoạn là hai mã LIỀN NHAU: chặn theo thời gian
  // thuần tuý sẽ nuốt mất cái thứ hai và người dùng tưởng máy treo.
  await page.evaluate(() => window.KioskCamera.emitForTest('WF|OP|OP-77'));
  await expect(page.locator('#screen-started')).toHaveClass(/active/, { timeout: 15000 });
  expect(state.scans).toEqual(['WF|EMP|NV-009', 'WF|OP|OP-77']);
  await context.close();
});

// --- camera là phần cứng: bật/tắt phải thật -------------------------------

test('bật rồi tắt camera thì track bị DỪNG, không chỉ ẩn thẻ video', async () => {
  const context = await phone();
  const page = await context.newPage();
  await page.addInitScript(FAKE_CAMERA);
  await openKiosk(page, { scans: [] });
  await page.getByTestId('kiosk-camera-toggle').click();
  await expect(page.getByTestId('kiosk-camera-layer')).toHaveClass(/on/);
  // CHỜ chứ không đọc ngay: lớp camera hiện ra TRƯỚC khi bộ giải mã sẵn sàng
  // (cố ý -- xem chú thích trong kiosk-camera.js), và khi bài chạy với bản đã
  // deploy thì jsQR còn phải tải 250 KB qua mạng.
  await page.waitForFunction(() => window.KioskCamera.isRunning(), null, { timeout: 25000 });

  await page.getByTestId('kiosk-camera-close').click();
  await expect(page.getByTestId('kiosk-camera-layer')).not.toHaveClass(/on/);
  expect(await page.evaluate(() => window.__cameraStops)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.querySelector('#camera-video').srcObject)).toBeNull();
  await context.close();
});

test('camera tự tắt khi luồng sang màn nhập sản lượng, và tự bật lại sau đó', async () => {
  const context = await phone();
  const page = await context.newPage();
  await page.addInitScript(FAKE_CAMERA);
  await page.route(/\/api\/kiosk-web\/scan/, r => r.fulfill({
    json: { ok: true, type: 'employee', employee: EMPLOYEE, open_session: OPEN_SESSION } }));
  await page.route(/\/api\/kiosk-web\/heartbeat/, r => r.fulfill({ json: { ok: true } }));
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.KioskCamera);

  await page.getByTestId('kiosk-camera-toggle').click();
  await expect(page.getByTestId('kiosk-camera-layer')).toHaveClass(/on/);

  await page.evaluate(() => window.KioskCamera.emitForTest('WF|EMP|NV-009'));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  // Camera không được che bàn phím số, và không được tiếp tục quay khi không
  // ai yêu cầu nó quay.
  await expect(page.getByTestId('kiosk-camera-layer')).not.toHaveClass(/on/);
  expect(await page.evaluate(() => window.KioskCamera.isRunning())).toBe(false);
  // Nhưng Ý ĐỊNH bật của người dùng vẫn còn: quay lại màn quét là tự mở lại.
  expect(await page.evaluate(() => window.KioskCamera.isWanted())).toBe(true);
  await context.close();
});

// --- bàn phím số cảm ứng --------------------------------------------------

test('màn nhập sản lượng trên điện thoại có bàn phím số lớn và nó ghi đúng số', async () => {
  const context = await phone();
  const page = await context.newPage();
  await page.route(/\/api\/kiosk-web\/scan/, r => r.fulfill({
    json: { ok: true, type: 'employee', employee: EMPLOYEE, open_session: OPEN_SESSION } }));
  await page.route(/\/api\/kiosk-web\/heartbeat/, r => r.fulfill({ json: { ok: true } }));
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.evaluate(() => document.dispatchEvent(
    new CustomEvent('kiosk:camera-scan', { detail: { payload: 'WF|EMP|NV-009' } })));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

  const keypad = page.getByTestId('kiosk-qty-keypad');
  await expect(keypad).toBeVisible();
  const key = digit => keypad.locator(`[data-key="${digit}"]`);
  // Phím đủ lớn để bấm bằng ngón tay có găng: 44px là ngưỡng tối thiểu của
  // hướng dẫn cảm ứng, ở đây đặt 64px.
  const box = await key('7').boundingBox();
  expect(box.height).toBeGreaterThanOrEqual(44);

  await key('1').click(); await key('2').click(); await key('5').click();
  await expect(page.locator('#good-qty')).toHaveValue('125');
  await keypad.locator('[data-key="back"]').click();
  await expect(page.locator('#good-qty')).toHaveValue('12');
  await keypad.locator('[data-key="clear"]').click();
  await expect(page.locator('#good-qty')).toHaveValue('0');
  await context.close();
});

// --- bố cục trên màn điện thoại -------------------------------------------

test('không tràn ngang ở khổ iPhone, dọc lẫn ngang', async () => {
  const context = await phone();
  const page = await context.newPage();
  await openKiosk(page, { scans: [] });
  for (const [w, h] of [[390, 844], [844, 390]]) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(120);
    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `tràn ngang ${overflow}px`).toBeLessThanOrEqual(1);
  }
  await context.close();
});

test('ô nhập sản lượng đủ lớn để iOS không tự phóng to trang', async () => {
  const context = await phone();
  const page = await context.newPage();
  await page.route(/\/api\/kiosk-web\/scan/, r => r.fulfill({
    json: { ok: true, type: 'employee', employee: EMPLOYEE, open_session: OPEN_SESSION } }));
  await page.route(/\/api\/kiosk-web\/heartbeat/, r => r.fulfill({ json: { ok: true } }));
  await page.goto('/kiosk');
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.evaluate(() => document.dispatchEvent(
    new CustomEvent('kiosk:camera-scan', { detail: { payload: 'WF|EMP|NV-009' } })));
  await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);
  const size = await page.locator('#good-qty').evaluate(el => parseFloat(getComputedStyle(el).fontSize));
  expect(size, 'dưới 16px thì Safari tự phóng to khi focus').toBeGreaterThanOrEqual(16);
  await context.close();
});


// --- CHỨNG MINH ĐƯỜNG GIẢI MÃ CỦA iPHONE THẬT SỰ ĐỌC ĐƯỢC ------------------

test('jsQR đọc được một ảnh QR THẬT từ khung hình camera trên WebKit', async () => {
  const context = await phone();
  const page = await context.newPage();
  const state = { scans: [] };
  // Camera giả phát ra một canvas đang VẼ chính ảnh QR thật -- gần nhất với
  // việc giơ điện thoại trước tờ tem mà CI có thể dựng được.
  await page.addInitScript(qrBase64 => {
    Object.defineProperty(window, 'isSecureContext', { get: () => true, configurable: true });
    const canvas = document.createElement('canvas');
    canvas.width = 480; canvas.height = 480;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 480, 480);
    const image = new Image();
    image.onload = () => {
      const paint = () => {
        ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 480, 480);
        ctx.drawImage(image, 120, 120, 240, 240);
        requestAnimationFrame(paint);
      };
      paint();
    };
    image.src = `data:image/png;base64,${qrBase64}`;
    navigator.mediaDevices = navigator.mediaDevices || {};
    navigator.mediaDevices.getUserMedia = async () => canvas.captureStream(10);
    navigator.mediaDevices.enumerateDevices = async () => ([{ kind: 'videoinput', deviceId: 'back', label: 'Back' }]);
  }, QR_PNG_BASE64);

  await openKiosk(page, state);
  expect(await page.evaluate(() => 'BarcodeDetector' in window)).toBe(false);
  await page.getByTestId('kiosk-camera-toggle').click();

  // Không bơm chuỗi vào: chuỗi phải ĐI RA TỪ ẢNH.
  await expect(page.locator('#screen-operation')).toHaveClass(/active/, { timeout: 45000 });
  expect(state.scans).toEqual(['WF|EMP|NV-009']);
  // Và thư viện dự phòng đúng là thứ đã làm việc đó.
  expect(await page.evaluate(() => typeof window.jsQR)).toBe('function');
  await context.close();
});
