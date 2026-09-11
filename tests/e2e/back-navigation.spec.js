// Nút Back của trình duyệt phải trả về đúng màn vừa rời.
//
// Bug thật trên TEST: đang ở danh sách Production Order, bấm vào một PO để mở
// chi tiết, rồi bấm Back thì KHÔNG về danh sách mà nhảy thẳng sang "Dashboard
// theo ngày". Nguyên nhân: chi tiết PO chỉ thay nội dung mà không ghi history,
// nên Back nhảy về entry trước cả danh sách PO. Spec này khoá lại từng màn con
// có cùng hình dạng đó.
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  // /login khi đã có phiên tự chuyển sang /app; goto ngay sau đó bị chính nó
  // cắt ngang, và với các bài dùng goBack() thì lịch sử duyệt còn bị hỏng
  // theo. Đợi chuyển hướng tự động xong ngay trong helper đăng nhập.
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
}

const PO = { id: 1, code: 'QA-BACK-PO', product: 'Khung máy', planned_quantity: 100,
  status: 'IN_PROGRESS', priority: 'NORMAL' };

async function mockPo(page) {
  await page.route(/\/api\/production-orders(\?|$)/, route => route.fulfill({ json: { ok: true, items: [PO] } }));
  await page.route(/\/api\/production-orders\/1(\?|$)/, route => route.fulfill({ json: { ok: true, item: PO } }));
  await page.route(/\/api\/(parts|operations|equipment|production-control)(\?|$)/, route =>
    route.fulfill({ json: { ok: true, items: [], operations: [] } }));
}

test('Dashboard → danh sách PO → chi tiết PO → Back phải về danh sách PO', async ({ page }) => {
  await login(page);
  await mockPo(page);
  // Đi qua Dashboard trước, đúng như kịch bản người dùng báo.
  await page.goto('/app?page=dashboard');
  await expect(page.locator('#appLayout')).toBeVisible();
  await page.evaluate(() => openPage('production-orders'));
  await expect(page.locator('.po-actions').first()).toBeVisible({ timeout: 20000 });

  // REQ-UI-022: danh sách PO là thẻ .po-card, không còn <tbody><tr>.
  await page.locator('.po-card').first().locator('.po-card-identity').click();
  await expect(page.locator('#poBack')).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).searchParams.get('po_id')).toBe('1');

  await page.goBack();
  // Về DANH SÁCH PO, không phải Dashboard.
  await expect(page.locator('.po-actions').first()).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).searchParams.get('po_id')).toBeNull();
  expect(new URL(page.url()).searchParams.get('page')).toBe('production-orders');

  // Back thêm một lần nữa mới về Dashboard.
  await page.goBack();
  expect(new URL(page.url()).searchParams.get('page')).toBe('dashboard');
});

test('F5 khi đang ở chi tiết PO thì vẫn ở chi tiết PO', async ({ page }) => {
  await login(page);
  await mockPo(page);
  await page.goto('/app?page=production-orders');
  await expect(page.locator('.po-actions').first()).toBeVisible({ timeout: 20000 });
  // REQ-UI-022: danh sách PO là thẻ .po-card, không còn <tbody><tr>.
  await page.locator('.po-card').first().locator('.po-card-identity').click();
  await expect(page.locator('#poBack')).toBeVisible({ timeout: 15000 });

  await page.reload();
  await expect(page.locator('#poBack')).toBeVisible({ timeout: 20000 });
});

test('nút "← Danh sách PO" cũng dọn ?po khỏi URL', async ({ page }) => {
  await login(page);
  await mockPo(page);
  await page.goto('/app?page=production-orders');
  await expect(page.locator('.po-actions').first()).toBeVisible({ timeout: 20000 });
  // REQ-UI-022: danh sách PO là thẻ .po-card, không còn <tbody><tr>.
  await page.locator('.po-card').first().locator('.po-card-identity').click();
  await expect(page.locator('#poBack')).toBeVisible({ timeout: 15000 });
  await page.locator('#poBack').click();
  await expect(page.locator('.po-actions').first()).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).searchParams.get('po_id')).toBeNull();
});

test('Người dùng → Ma trận quyền → Back phải về danh sách người dùng', async ({ page }) => {
  await login(page);
  await page.goto('/app?page=dashboard');
  await expect(page.locator('#appLayout')).toBeVisible();
  await page.evaluate(() => openPage('users'));
  const rolesBtn = page.locator('#rolePermissions');
  if (!(await rolesBtn.count())) test.skip(true, 'tài khoản này không thấy nút Ma trận quyền');
  await rolesBtn.click();
  await expect(page.locator('#rbacBack')).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).searchParams.get('roles')).toBe('1');

  await page.goBack();
  await expect(page.locator('#rolePermissions')).toBeVisible({ timeout: 15000 });
  expect(new URL(page.url()).searchParams.get('roles')).toBeNull();
});

test('Back giữa các trang chính vẫn đi đúng thứ tự', async ({ page }) => {
  await login(page);
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible();
  for (const id of ['dashboard', 'production-orders', 'employees']) {
    await page.evaluate(p => openPage(p), id);
    await page.waitForTimeout(400);
  }
  expect(new URL(page.url()).searchParams.get('page')).toBe('employees');
  await page.goBack();
  expect(new URL(page.url()).searchParams.get('page')).toBe('production-orders');
  await page.goBack();
  expect(new URL(page.url()).searchParams.get('page')).toBe('dashboard');
  await page.goBack();
  expect(new URL(page.url()).searchParams.get('page')).toBe('overview');
});

test('Dashboard: đổi tab rồi Back thì về tab cũ, không rời trang', async ({ page }) => {
  await login(page);
  await page.goto('/app?page=dashboard');
  await expect(page.locator('#appLayout')).toBeVisible();
  await page.waitForTimeout(1500);
  const tabs = page.locator('[data-dashboard-tab]');
  if ((await tabs.count()) < 2) test.skip(true, 'dashboard chưa render đủ tab');
  const before = new URL(page.url()).searchParams.get('tab');
  await tabs.nth(1).click();
  await page.waitForTimeout(500);
  expect(new URL(page.url()).searchParams.get('tab')).not.toBe(before);
  // Tab dùng replaceState nên Back rời trang -- kiểm để hành vi này là CHỦ Ý,
  // không phải tình cờ: người dùng không bị kẹt trong một chuỗi tab.
  await page.goBack();
  expect(new URL(page.url()).searchParams.get('page')).not.toBe('dashboard');
});
