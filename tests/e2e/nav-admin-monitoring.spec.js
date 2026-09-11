// Nhóm con "Theo dõi & Nhật ký" trong Quản trị (REQ-NAV-001).
//
// Ba màn tra cứu/đối soát -- Truy vết sản xuất (production-trace), Nhật ký
// nghiệp vụ (business-audit), Nhật ký ứng dụng (system-logs) -- trước đây nằm
// lẫn trong nhóm "Điều hành" cùng các màn vận hành hằng ngày. Chúng đã được
// chuyển sang Quản trị dưới một sub-heading.
//
// ĐIỀU QUAN TRỌNG NHẤT spec này canh: chuyển nhóm KHÔNG được cấp thêm quyền.
// Mỗi mục vẫn do đúng permission cũ trong PAGE_PERMISSION quyết định.
const { test, expect } = require('@playwright/test');

const ADMIN_GROUP = 'Quản trị';
const SUBHEADING = 'Theo dõi & Nhật ký';
const MOVED = ['Truy vết sản xuất', 'Nhật ký nghiệp vụ', 'Nhật ký ứng dụng'];

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
}

// Giả role bằng cách ghi đè window.MESFLOW_USER ngay trong HTML trả về, vì
// template đặt biến này inline TRƯỚC app.js -- addInitScript sẽ bị ghi đè.
async function asRole(page, role, permissions) {
  await page.route('**/app*', async route => {
    const res = await route.fetch();
    let body = await res.text();
    body = body.replace(
      /window\.MESFLOW_USER=\{[^;]*\};/,
      `window.MESFLOW_USER=${JSON.stringify({ id: 999, username: 'stub', role, permissions })};`
    );
    await route.fulfill({ response: res, body });
  });
}

function groupPanel(page, label) {
  return page.locator('.sidebar-group', { has: page.locator(`.sidebar-group-trigger:has-text("${label}")`) });
}

test('admin thấy đủ ba mục dưới Quản trị, trong nhóm con Theo dõi & Nhật ký', async ({ page }) => {
  await login(page);
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });

  const admin = groupPanel(page, ADMIN_GROUP);
  await expect(admin).toHaveCount(1);
  await expect(admin.locator('.sidebar-sub-heading', { hasText: SUBHEADING })).toHaveCount(1);
  for (const label of MOVED) {
    await expect(admin.locator('.sidebar-sub-item', { hasText: label })).toHaveCount(1);
  }
});

test('ba mục đã rời khỏi nhóm Điều hành', async ({ page }) => {
  await login(page);
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });

  const dieuHanh = groupPanel(page, 'Điều hành');
  await expect(dieuHanh).toHaveCount(1);
  for (const label of MOVED) {
    await expect(dieuHanh.locator('.sidebar-sub-item', { hasText: label })).toHaveCount(0);
  }
  // các mục vận hành vẫn ở nguyên chỗ cũ
  await expect(dieuHanh.locator('.sidebar-sub-item', { hasText: 'Quản lý Session' })).toHaveCount(1);
  await expect(dieuHanh.locator('.sidebar-sub-item', { hasText: 'Hàng chờ sửa' })).toHaveCount(1);
});

test('role không có quyền audit/log thì không thấy mục nào, và không còn tiêu đề trống', async ({ page }) => {
  await asRole(page, 'operator', []);          // không permission nào
  await login(page);
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });

  for (const label of MOVED) {
    await expect(page.locator('.sidebar-sub-item', { hasText: label })).toHaveCount(0);
  }
  // Đây là phần dễ hỏng nhất: heading phải biến mất cùng các mục, không được
  // để lại một tiêu đề nhóm con trống trơn.
  await expect(page.locator('.sidebar-sub-heading', { hasText: SUBHEADING })).toHaveCount(0);
});

test('chuyển nhóm không cấp thêm quyền: operator chỉ thấy đúng mục quyền cũ cho phép', async ({ page }) => {
  // operator thật có session.view (xem SEED_ROLES trong rbac.py) nhưng KHÔNG có
  // business_audit.view hay logs.view. production-trace dùng chung session.view
  // nên operator vẫn thấy nó -- đúng như trước khi chuyển nhóm, không rộng hơn.
  await asRole(page, 'operator', ['session.view']);
  await login(page);
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });

  await expect(page.locator('.sidebar-sub-item', { hasText: 'Truy vết sản xuất' })).toHaveCount(1);
  await expect(page.locator('.sidebar-sub-item', { hasText: 'Nhật ký nghiệp vụ' })).toHaveCount(0);
  await expect(page.locator('.sidebar-sub-item', { hasText: 'Nhật ký ứng dụng' })).toHaveCount(0);
});

test('deep-link cũ vẫn mở đúng trang, không đổi URL', async ({ page }) => {
  await login(page);
  for (const slug of ['production-trace', 'business-audit', 'system-logs']) {
    await page.goto(`/app?page=${slug}`);
    await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
    await expect(page.locator('body')).toHaveAttribute('data-page', slug);
    expect(page.url()).toContain(`page=${slug}`);
  }
});

test('mobile: mở drawer thấy nhóm con, không tràn ngang', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });

  await page.locator('#mobileMenuToggle').click();
  await expect(page.locator('body')).toHaveClass(/sidebar-mobile-open/);

  const admin = groupPanel(page, ADMIN_GROUP);
  await admin.locator('.sidebar-group-trigger').click();
  await expect(admin.locator('.sidebar-sub-heading', { hasText: SUBHEADING })).toBeVisible();
  for (const label of MOVED) {
    await expect(admin.locator('.sidebar-sub-item', { hasText: label })).toBeVisible();
  }
  const over = await page.evaluate(() =>
    document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(over, 'drawer làm tràn ngang').toBeLessThanOrEqual(1);
});
