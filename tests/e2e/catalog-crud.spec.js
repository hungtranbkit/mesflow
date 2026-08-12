const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

test('thêm, sửa, tải lại và xóa nhân viên', async ({ page }) => {
  await login(page);
  const code = `NV${Date.now()}`;
  await page.evaluate(() => openPage('employees'));
  await page.locator('#employeeAdd').click();
  await page.locator('[name="employee_no"]').fill(code);
  await page.locator('[name="name"]').fill('Nhân viên kiểm thử');
  await page.locator('[name="department"]').fill('KIỂM THỬ');
  await page.getByRole('button', { name: 'Lưu nhân viên' }).click();
  await page.locator('#employeeSearch').fill(code);
  await expect(page.locator('#employeeList')).toContainText('Nhân viên kiểm thử');
  await page.getByRole('button', { name: 'Sửa' }).click();
  await page.locator('[name="name"]').fill('Nhân viên đã chỉnh sửa');
  await page.getByRole('button', { name: 'Lưu nhân viên' }).click();
  await page.reload();
  await page.evaluate(() => openPage('employees'));
  await page.locator('#employeeSearch').fill(code);
  await expect(page.locator('#employeeList')).toContainText('Nhân viên đã chỉnh sửa');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Xóa' }).click();
  await expect(page.locator('#employeeList')).not.toContainText(code);
});

test('thêm, sửa, tải lại và xóa thiết bị', async ({ page }) => {
  await login(page);
  const code = `TB${Date.now()}`;
  await page.evaluate(() => openPage('equipment'));
  await page.locator('#equipmentAdd').click();
  await page.locator('[name="code"]').fill(code);
  await page.locator('[name="name"]').fill('Thiết bị kiểm thử');
  await page.locator('[name="equipment_type"]').fill('Máy kiểm thử');
  await page.getByRole('button', { name: 'Thêm thiết bị', exact: true }).click();
  await page.locator('#equipmentSearch').fill(code);
  await expect(page.locator('#equipmentList')).toContainText('Thiết bị kiểm thử');
  await page.getByRole('button', { name: 'Sửa' }).click();
  await page.locator('[name="name"]').fill('Thiết bị đã chỉnh sửa');
  await page.getByRole('button', { name: 'Lưu thay đổi' }).click();
  await page.reload();
  await page.evaluate(() => openPage('equipment'));
  await page.locator('#equipmentSearch').fill(code);
  await expect(page.locator('#equipmentList')).toContainText('Thiết bị đã chỉnh sửa');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', { name: 'Xóa' }).click();
  await expect(page.locator('#equipmentList')).not.toContainText(code);
});

test('QR lấy dữ liệu thật và giữ thao tác chọn rõ ràng', async ({ page }) => {
  await login(page);
  await page.evaluate(() => openPage('qr-print'));
  await expect(page.locator('.qr-catalog-card').first()).toBeVisible();
  await page.locator('.qr-item-check').first().check();
  await expect(page.locator('#qrSummary')).toContainText('Đã chọn 1 tem');
  await page.locator('#qrClear').click();
  await expect(page.locator('#qrSummary')).toContainText('Đã chọn 0 tem');
});
