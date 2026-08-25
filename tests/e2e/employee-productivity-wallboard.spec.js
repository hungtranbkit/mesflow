const { test, expect } = require('@playwright/test');

// Kiosk trình chiếu năng suất nhân viên -- public/unauthenticated route, so
// no login needed. Mocks /api/wallboard/employee-productivity directly
// (same convention as the other *-visual.spec.js files in this folder) --
// no business logic under test here, only the display-settings wiring
// (employees_per_page / columns / auto_page_flip / auto_page_flip_seconds)
// added 2026-08-23.

function employees(count) {
  return Array.from({ length: count }, (_, i) => ({
    employee_id: i + 1,
    employee_code: `EMP-${String(i + 1).padStart(3, '0')}`,
    employee_name: `Nhân viên ${String(i + 1).padStart(2, '0')}`,
    department: 'May 1',
    completed_sessions: 30 + i,
    productivity_percent: 100 - i,
    good_qty: 500, defect_qty: 5,
    worked_seconds: 3600 * 8,
  }));
}

async function mockWallboard(page, { config, employeeCount = 25 }) {
  await page.route('**/api/wallboard/employee-productivity', route => route.fulfill({
    json: {
      ok: true, configured: true,
      config: {
        date_mode: 'dynamic_mtd', sort: 'productivity_desc', page_size: 10, refresh_interval_seconds: 300,
        employees_per_page: 20, columns: 'auto', auto_page_flip: true, auto_page_flip_seconds: 10,
        display_mode: 'grid', updated_by: 'admin', updated_at: new Date().toISOString(),
        ...config,
      },
      summary: { avg_employee_productivity_percent: 92.5, employee_count: employeeCount, completed_sessions: 900, total_good_qty: 12000, from: '2026-08-01', to: '2026-08-22' },
      employees: employees(employeeCount),
    },
  }));
}

async function goto(page) {
  await page.goto('/kiosk/employee-productivity');
  await expect(page.locator('#wbList .wb-card').first()).toBeVisible();
}

function columnCount(gridTemplateColumns) {
  // getComputedStyle resolves repeat()/var() into a space-separated list of
  // resolved track sizes, e.g. "622px 622px" for 2 columns.
  return gridTemplateColumns.trim().split(/\s+/).filter(Boolean).length;
}

test('no progress bar and no horizontal overflow on the wallboard', async ({ page }) => {
  await mockWallboard(page, { config: {} });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await goto(page);
  await expect(page.locator('.wb-row-bar')).toHaveCount(0);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('AUTO columns: 800px=>1, 1024px=>2, 1920px=>3', async ({ page }) => {
  await mockWallboard(page, { config: { columns: 'auto' } });
  for (const [width, expected] of [[800, 1], [1024, 2], [1920, 3]]) {
    await page.setViewportSize({ width, height: 900 });
    await goto(page);
    const gtc = await page.locator('#wbList').evaluate(el => getComputedStyle(el).gridTemplateColumns);
    expect(columnCount(gtc)).toBe(expected);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  }
});

test('explicit 3-column mode works on a large viewport', async ({ page }) => {
  await mockWallboard(page, { config: { columns: '3' } });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await goto(page);
  const gtc = await page.locator('#wbList').evaluate(el => getComputedStyle(el).gridTemplateColumns);
  expect(columnCount(gtc)).toBe(3);
});

test('explicit 3-column mode safely falls back on a small viewport', async ({ page }) => {
  await mockWallboard(page, { config: { columns: '3' } });
  await page.setViewportSize({ width: 480, height: 800 });
  await goto(page);
  const gtc = await page.locator('#wbList').evaluate(el => getComputedStyle(el).gridTemplateColumns);
  expect(columnCount(gtc)).toBe(1);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
});

test('employees_per_page limits cards shown per page and shows a page indicator', async ({ page }) => {
  await mockWallboard(page, { config: { employees_per_page: 20 }, employeeCount: 25 });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await goto(page);
  await expect(page.locator('#wbList .wb-card')).toHaveCount(20);
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 1/2');
});

test('employees_per_page=30 shows all 25 employees on a single page and disables auto flip', async ({ page }) => {
  await mockWallboard(page, { config: { employees_per_page: 30, auto_page_flip: true, auto_page_flip_seconds: 5 }, employeeCount: 25 });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await goto(page);
  await expect(page.locator('#wbList .wb-card')).toHaveCount(25);
  await expect(page.locator('#wbPrev')).toBeHidden();
  await expect(page.locator('#wbNext')).toBeHidden();
});

test('auto flip uses the configured interval and manual Next resets it', async ({ page }) => {
  await mockWallboard(page, { config: { employees_per_page: 10, auto_page_flip: true, auto_page_flip_seconds: 5 }, employeeCount: 25 });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await goto(page);
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 1/3');
  await page.waitForTimeout(5600);
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 2/3');
  // Manual Prev takes it straight back to page 1 and resets the timer --
  // it must NOT also auto-flip a few ms later from the old schedule.
  await page.locator('#wbPrev').click();
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 1/3');
  await page.waitForTimeout(2000);
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 1/3');
});

test('page flip pauses on interaction and auto-resumes after idle', async ({ page }) => {
  // #wbShell covers the entire 100vw/100vh viewport by design (a TV
  // wallboard has no chrome around it to hover over instead) -- there is
  // no in-page location a real mouse move could land on to "leave" it, so
  // pause here uses an idle-timeout model (mousemove pauses, auto-resumes
  // after a few seconds of no further interaction), the same pattern a
  // video player's on-screen controls use, rather than a binary
  // enter/leave zone that a full-viewport element can never provide.
  await mockWallboard(page, { config: { employees_per_page: 10, auto_page_flip: true, auto_page_flip_seconds: 3 }, employeeCount: 25 });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await goto(page);
  await page.mouse.move(500, 500); // real mousemove -- pauses and (re)starts the idle-resume timer
  await page.waitForTimeout(3500); // past the first tick (3s) while still paused (idle-resume is 4s)
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 1/3'); // that tick was skipped
  await page.waitForTimeout(3500); // idle-resume fires at 4s; next tick at 6s
  await expect(page.locator('#wbPageIndicator')).toContainText('Trang 2/3');
});
