const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  const errors=[];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
  page.__mesflowErrors=errors;
});

test.afterEach(async ({ page }) => {
  expect(page.__mesflowErrors || []).toEqual([]);
});

test('dashboard renders and shift API responds', async ({ page }) => {
  await expect(page.locator('#pageTitle')).toContainText('Điều hành');
  await expect(page.locator('#dailyDate')).toBeVisible();
  await expect(page.locator('#dailyShift')).toBeVisible();
});

test('employee screen opens integrated report entry point', async ({ page }) => {
  await page.locator('[data-page="employees"]').click();
  await expect(page.locator('#pageTitle')).toContainText('Nhân viên');
  await expect(page.locator('#content')).toBeVisible();
});

test('QR print center renders a result or clear empty state', async ({ page }) => {
  await page.locator('[data-page="qr-print"]').click();
  await expect(page.locator('#qrList')).toBeVisible();
  await expect(page.locator('#qrSummary')).not.toContainText('Đang tải danh sách');
  await expect(page.locator('#qrList')).not.toContainText('Không thể hiển thị danh sách QR');
});

test('session exception workflow screen renders', async ({ page }) => {
  await page.locator('[data-page="session-exceptions"]').click();
  await expect(page.locator('#seList')).toBeVisible();
  await expect(page.locator('#seWorkflow')).toBeVisible();
  await expect(page.locator('#seStart')).toBeVisible();
});


test('QR and system logs render without page errors', async ({ page }) => {
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await page.locator('[data-page="qr-print"]').click();
  await expect(page.locator('#qrSummary')).toBeVisible();
  await expect(page.locator('#qrList')).not.toContainText('Không thể hiển thị danh sách QR');
  await page.locator('[data-page="system-logs"]').click();
  await expect(page.locator('#slRows')).toBeVisible();
  await expect(page.locator('#slRows')).not.toContainText('Không thể tải Nhật ký hệ thống');
  expect(errors).toEqual([]);
});


test('system log center switches across all log types', async ({ page }) => {
  await page.locator('[data-page="system-logs"]').click();
  await expect(page.getByRole('button',{name:'Action Log'})).toBeVisible();
  await page.getByRole('button',{name:'Error Trace'}).click();
  await expect(page.locator('#etRows')).toBeVisible();
  await page.getByRole('button',{name:'Lịch sử Retention'}).click();
  await expect(page.locator('#lrRows')).toBeVisible();
});
