const { fullDayContext } = require('./helpers/day-calendar-fixture');
const { test, expect } = require('@playwright/test');

// BƯỚC VÀO Dashboard = xem HÔM NAY.
//
// Lỗi gốc: setPageUrl() chỉ ghi đè `page=`, nên `date=` của lần xem trước sống
// sót qua mọi màn khác rồi quay lại nguyên vẹn. Chọn 01/09 -> sang Template ->
// bấm Dashboard, URL vẫn còn date=2026-09-01 và người dùng nhìn số liệu ngày cũ
// tưởng hệ thống hỏng.
//
// Ranh giới mới là thứ đáng test, không phải riêng ca sửa: F5, link dán tay và
// Back/Forward vẫn PHẢI giữ ngày -- nếu không thì deep link và nút Back mất tác
// dụng; và đang ở trong Dashboard tự đổi ngày thì không được tự nhảy về hôm nay.

const OLD_DATE = '2026-09-01';

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

async function mockEmpty(page) {
  await page.route('**/api/dashboard/day?*', route => route.fulfill({
    json: { ok: true, context: { ...fullDayContext, date: hcmDate(), timezone: 'Asia/Ho_Chi_Minh', po_id: null,
      day_start: new Date().toISOString(), day_end: new Date().toISOString() },
      items: [], sessions: [], activity: [] },
  }));
  await page.route('**/api/kiosk-board/po-options*', route => route.fulfill({ json: { ok: true, items: [] } }));
}

async function signIn(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
}

// Sidebar groups are collapsed by default, so a nested destination button can
// legitimately be hidden.  Exercise the same navigation handler directly;
// visibility of that unrelated disclosure is not part of this date test.
const navTo = (page, id) => page.evaluate(pageId => {
  const button = document.querySelector(`[data-page="${pageId}"]`);
  return openPage(pageId, button);
}, id);

test.describe('Dashboard — ngày reset khi bước vào', () => {
  test.beforeEach(async ({ page }) => { await mockEmpty(page); await signIn(page); });

  test('chọn ngày cũ -> đi màn khác -> bấm Dashboard -> ngày = hôm nay', async ({ page }) => {
    await page.goto('/app?page=dashboard');
    await expect(page.locator('#dailyDate')).toBeVisible();

    await page.fill('#dailyDate', OLD_DATE);
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
    expect(page.url()).toContain(`date=${OLD_DATE}`);

    await navTo(page, 'templates');
    await expect(page.locator('#dailyDate')).toHaveCount(0);

    await navTo(page, 'dashboard');
    await expect(page.locator('#dailyDate')).toBeVisible();
    await expect(page.locator('#dailyDate')).toHaveValue(hcmDate());
    // Dashboard now canonicalizes its selected date in the URL.  The
    // regression is the stale OLD_DATE surviving navigation, not the mere
    // presence of a date query parameter.
    expect(new URL(page.url()).searchParams.get('date')).toBe(hcmDate());
  });

  test('đang ở Dashboard đổi ngày thì GIỮ, không nhảy về hôm nay khi làm mới', async ({ page }) => {
    await page.goto('/app?page=dashboard');
    await page.fill('#dailyDate', OLD_DATE);
    await page.click('#dailyRefresh');
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
    // Đổi tab cũng chỉ replaceState, không được đụng tới ngày.
    await page.click('[data-dashboard-tab="output"]');
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
  });

  test('F5 / deep-link kèm date vẫn mở đúng ngày đó', async ({ page }) => {
    await page.goto(`/app?page=dashboard&date=${OLD_DATE}`);
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
    await page.reload();
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
  });

  test('Back quay lại Dashboard giữ nguyên ngày đang xem', async ({ page }) => {
    await page.goto(`/app?page=dashboard&date=${OLD_DATE}`);
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
    await navTo(page, 'templates');
    await expect(page.locator('#dailyDate')).toHaveCount(0);
    await page.goBack();
    await expect(page.locator('#dailyDate')).toHaveValue(OLD_DATE);
  });
});
