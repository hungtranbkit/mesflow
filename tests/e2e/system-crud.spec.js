const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

test('sửa tài khoản và giữ đúng dữ liệu sau khi tải lại trang', async ({ page }) => {
  await login(page);
  const response = await page.request.get('/api/users');
  expect(response.ok()).toBeTruthy();
  const users = await response.json();
  const original = users.items.find(user => user.role === 'admin' && user.active);
  expect(original).toBeTruthy();
  const changedName = `${original.display_name} E2E`;

  try {
    await page.evaluate(() => openPage('users'));
    const row = page.locator('#userList tbody tr').filter({ hasText: `@${original.username}` });
    await row.getByRole('button', { name: 'Sửa tài khoản' }).click();
    await page.locator('[name="display_name"]').fill(changedName);
    await page.getByRole('button', { name: 'Lưu thay đổi' }).click();
    await expect(page.locator('#userList')).toContainText(changedName);

    await page.reload();
    await page.evaluate(() => openPage('users'));
    await expect(page.locator('#userList')).toContainText(changedName);
  } finally {
    await page.request.patch(`/api/users/${original.id}`, {
      data: {
        display_name: original.display_name,
        role: original.role,
        active: original.active,
      },
    });
  }
});
