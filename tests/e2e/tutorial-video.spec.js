const { test, expect } = require('@playwright/test');

const WAIT = Number(process.env.MESFLOW_TUTORIAL_WAIT_MS || 1800);
const LONG_WAIT = Number(process.env.MESFLOW_TUTORIAL_LONG_WAIT_MS || 2800);

async function pause(page, ms = WAIT) {
  await page.waitForTimeout(ms);
}

async function titleCard(page, title, subtitle = '') {
  await page.evaluate(({ title, subtitle }) => {
    document.getElementById('__mesflowTutorialCard')?.remove();
    const card = document.createElement('div');
    card.id = '__mesflowTutorialCard';
    card.style.cssText = [
      'position:fixed','inset:0','z-index:2147483647','display:flex','align-items:center','justify-content:center',
      'background:rgba(8,15,26,.86)','color:#fff','font-family:Arial,sans-serif','pointer-events:none'
    ].join(';');
    card.innerHTML = `<div style="max-width:1100px;text-align:center;padding:56px 70px;border-radius:28px;background:rgba(17,29,48,.94);box-shadow:0 24px 80px rgba(0,0,0,.45)"><div style="font-size:58px;font-weight:800;line-height:1.15">${title}</div>${subtitle ? `<div style="margin-top:22px;font-size:28px;line-height:1.45;opacity:.88">${subtitle}</div>` : ''}</div>`;
    document.body.appendChild(card);
  }, { title, subtitle });
  await pause(page, LONG_WAIT);
  await page.evaluate(() => document.getElementById('__mesflowTutorialCard')?.remove());
  await pause(page, 500);
}

async function openPage(page, id, title, subtitle) {
  await page.evaluate(pageId => {
    const button = document.querySelector(`[data-page="${pageId}"]`);
    if (typeof window.openPage !== 'function') throw new Error('MESFlow openPage() is unavailable');
    return window.openPage(pageId, button);
  }, id);
  await expect(page.locator('#content')).toBeVisible();
  await pause(page, 900);
  if (title) await titleCard(page, title, subtitle);
  await pause(page);
}

test('MESFlow — video hướng dẫn tổng quan hệ thống', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));

  const tutorialUser = process.env.MESFLOW_TUTORIAL_USERNAME || 'admin';
  const tutorialPassword = process.env.MESFLOW_TUTORIAL_PASSWORD || '';
  expect(tutorialPassword, 'Thiếu MESFLOW_TUTORIAL_PASSWORD để quay video production-safe').toBeTruthy();

  await page.goto('/login');
  const login = await page.request.post('/api/auth/login', {
    data: { username: tutorialUser, password: tutorialPassword }
  });
  const loginBody = await login.text();
  expect(login.ok(), `Đăng nhập tutorial thất bại: HTTP ${login.status()} ${loginBody.slice(0,200)}`).toBeTruthy();
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();

  await titleCard(page, 'MESFlow', 'Video hướng dẫn tổng quan — giao diện Full HD 1920 × 1080');

  await openPage(page, 'overview', '1. Tổng quan sản xuất', 'Theo dõi tình trạng xưởng, tiến độ PO và các việc cần xử lý.');
  await openPage(page, 'dashboard', '2. Dashboard theo ngày', 'Theo dõi ca sản xuất, KPI và hoạt động trong ngày.');
  await titleCard(page, 'Phân biệt hai loại tiến độ', 'Thời gian dùng timeline mảnh có marker hiện tại; sản phẩm dùng thanh đặc và số lượng đạt / kế hoạch.');
  await openPage(page, 'production-orders', '3. Production Order', 'Quản lý lệnh sản xuất và theo dõi trạng thái PO.');
  await openPage(page, 'templates', '4. Template sản xuất', 'Quản lý Part, Operation và định mức thời gian chuẩn.');
  await openPage(page, 'production-schedule', '5. Tiến trình sản xuất', 'Theo dõi lịch và tiến độ thực hiện theo PO/Operation.');
  await openPage(page, 'session-management', '6. Quản lý Session', 'Xem thời gian làm việc, sản lượng đạt, lỗi và số lượng sửa được.');
  await openPage(page, 'session-exceptions', '7. Ngoại lệ Session', 'Kiểm tra các session bất thường và luồng xử lý ngoại lệ.');
  await openPage(page, 'employees', '8. Nhân viên', 'Quản lý danh sách nhân viên và mã nhận diện.');
  await openPage(page, 'qr-print', '9. Trung tâm QR', 'Lọc và in mã QR phục vụ vận hành tại xưởng.');
  await openPage(page, 'kiosk-management', '10. Quản lý Kiosk', 'Theo dõi trạng thái thiết bị, heartbeat, offline sync và lỗi.');
  await openPage(page, 'working-calendar', '11. Lịch làm việc', 'Quản lý ca làm và khoảng nghỉ dùng trong tính toán sản xuất.');
  await openPage(page, 'system-logs', '12. Nhật ký hệ thống', 'Tra cứu Action Log, Error Trace và dữ liệu hỗ trợ chẩn đoán.');

  await titleCard(page, 'Hoàn tất', 'Video chỉ đọc và trình diễn giao diện; không tạo, sửa hoặc xóa dữ liệu sản xuất.');

  expect(pageErrors, `Page errors khi quay tutorial: ${pageErrors.join(' | ')}`).toEqual([]);
});
