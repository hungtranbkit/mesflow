// Kiosk web là bề mặt CÔNG KHAI: máy xưởng mở /kiosk trực tiếp, không đăng nhập.
//
// Quyết định của chủ sở hữu nghiệp vụ (2026-09-12). Bài test này chạy bằng
// trình duyệt THẬT với context hoàn toàn trắng -- không cookie, không
// localStorage, không token kiosk -- vì đó chính xác là cái máy xưởng có.
// Ranh giới ở phía máy chủ: app/mesflow/web/auth.py :: kiosk_public.
//
// Nửa còn lại của bài test cũng quan trọng như nửa đầu: cùng trình duyệt trắng
// đó vẫn PHẢI bị đẩy về /login khi vào /app. "Mở kiosk" không được phép biến
// thành "mở cả ứng dụng".
const { test, expect } = require('@playwright/test');

// Không dùng storageState nào cả -- mỗi test một context trắng.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe('Kiosk công khai — không yêu cầu đăng nhập', () => {
  test('mở /kiosk khi chưa từng đăng nhập thì vào thẳng màn quét, không redirect', async ({ page }) => {
    const response = await page.goto('/kiosk');
    expect(response.status()).toBe(200);
    expect(new URL(page.url()).pathname).toBe('/kiosk');

    // Màn chờ quét thẻ phải sẵn sàng, và không có bất kỳ lời mời đăng nhập nào.
    await expect(page.locator('#screen-ready')).toHaveClass(/active/);
    await page.waitForFunction(() => !!window.MESFlowKioskDemo);
    await expect(page.locator('text=/đăng nhập/i')).toHaveCount(0);
  });

  test('tải lại trang vẫn ở Kiosk (yêu cầu 4: cookie hết hạn / chưa từng có)', async ({ page, context }) => {
    await page.goto('/kiosk');
    // Một cookie phiên cũ/hỏng đúng như máy xưởng có sau khi phiên hết hạn.
    await context.addCookies([{ name: 'session', value: 'stale.invalid.cookie',
                                url: new URL(page.url()).origin }]);
    const reloaded = await page.reload();
    expect(reloaded.status()).toBe(200);
    expect(new URL(page.url()).pathname).toBe('/kiosk');
    await expect(page.locator('#screen-ready')).toHaveClass(/active/);
  });

  test('quét thẻ nhân viên hoạt động khi chưa đăng nhập (không có 401)', async ({ page }) => {
    const denied = [];
    page.on('response', r => {
      if (r.url().includes('/api/kiosk-web/') && (r.status() === 401 || r.status() === 403)) {
        denied.push(`${r.status()} ${r.url()}`);
      }
    });
    // Chỉ chặn lớp mạng để bài test không phụ thuộc dữ liệu thật; điều đang đo
    // là trình duyệt trắng có gọi được và có bị chặn xác thực hay không.
    await page.route(/\/api\/kiosk-web\/scan/, route => route.fulfill({
      json: { ok: true, type: 'employee',
              employee: { id: 9, employee_no: 'NV-009', name: 'Thợ A', department: 'Cơ khí' },
              open_session: null } }));
    await page.goto('/kiosk');
    await page.waitForFunction(() => !!window.MESFlowKioskDemo);
    await page.evaluate(() => window.MESFlowKioskDemo.scan('WF|EMP|NV-009'));

    await expect(page.locator('#screen-error')).not.toHaveClass(/active/);
    expect(denied, 'kiosk browser was refused by auth').toEqual([]);
  });

  test('cùng trình duyệt trắng đó vẫn KHÔNG vào được /app', async ({ page }) => {
    await page.goto('/app');
    expect(new URL(page.url()).pathname).toBe('/login');
  });
});
