const { test, expect } = require('@playwright/test');

const employees = [
  { id: 1, employee_no: 'NV024', name: 'Nguyễn Văn Kiểm Thử', department: 'Lắp ráp', team: 'Tổ A', employment_status: 'Đang làm', phone: '0900000001', session_count: 2, total_good_qty: 27 },
  { id: 2, employee_no: 'NV025', name: 'Tên nhân viên rất dài để kiểm tra wrap', department: 'Hoàn thiện', team: 'Tổ B', employment_status: 'Thử việc', phone: '', session_count: 0, total_good_qty: 0 },
];

async function openEmployees(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await page.route('**/api/employees?limit=1000', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ items: employees, total: employees.length }),
  }));
  await page.evaluate(() => openPage('employees'));
  await expect(page.locator('.employee-result-count')).toContainText('Hiển thị 2 / 2 nhân viên');
}

for (const viewport of [{ name: 'mobile', width: 390, height: 844 }, { name: 'desktop', width: 1366, height: 768 }]) {
  test(`employee filter summary stays aligned at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await openEmployees(page);
    const metrics = await page.locator('.employee-result-count').evaluate(el => {
      const range = document.createRange();
      range.selectNodeContents(el.firstChild);
      const text = range.getBoundingClientRect();
      const number = el.querySelector('b').getBoundingClientRect();
      const box = el.getBoundingClientRect();
      const body = el.parentElement.getBoundingClientRect();
      const style = getComputedStyle(el);
      return {
        box: { x: box.x, y: box.y, width: box.width, height: box.height },
        text: { y: text.y, height: text.height },
        number: { y: number.y, height: number.height },
        body: { x: body.x, y: body.y, width: body.width },
        display: style.display,
        alignItems: style.alignItems,
        lineHeight: style.lineHeight,
        paddingTop: style.paddingTop,
        paddingBottom: style.paddingBottom,
      };
    });
    expect(metrics.display).toBe('flex');
    expect(metrics.alignItems).toBe('baseline');
    expect(metrics.box.y).toBeGreaterThanOrEqual(metrics.body.y);
    expect(metrics.box.x).toBeGreaterThanOrEqual(metrics.body.x);
    expect(metrics.box.x + metrics.box.width).toBeLessThanOrEqual(metrics.body.x + metrics.body.width + 0.5);
    expect(Math.abs(metrics.text.y - metrics.number.y)).toBeLessThanOrEqual(1);
    expect(metrics.paddingTop).toBe('12px');
    expect(metrics.paddingBottom).toBe('10px');
    await page.screenshot({ path: `test-results/employee-filter-summary-${viewport.name}-after.png`, fullPage: true });
  });
}
