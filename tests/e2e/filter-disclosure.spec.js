// Bộ lọc gập lại trên máy điện thoại -- primitive dùng chung cho 20 nơi gọi
// MFUI.filterBar().
//
// VÌ SAO PHẢI GẬP. Trung tâm ngoại lệ có 8 trường lọc. Ở 390px chúng chiếm
// 509px và đẩy ngoại lệ đầu tiên xuống 740px -- gần một màn hình rưỡi cuộn
// trước khi thấy nội dung chính. Đã thử sắp lại: một cột thành 8 hàng (655px,
// tệ hơn), hai cột còn 509px. Tám trường KHÔNG vừa một màn hình dọc, nên thứ
// duy nhất còn lại là đừng hiện chúng cho tới khi người dùng cần.
//
// Đo được sau khi gập: 509 -> 114px, và danh sách bắt đầu ở 395px thay vì 740.
//
// BA THỨ DỄ HỎNG mà spec này canh:
//
//   1. Desktop phải KHÔNG đổi gì cả. <details> ở màn rộng phải trong suốt
//      hoàn toàn -- không dòng tiêu đề, không mũi tên, không viền.
//   2. Gập rồi mở lại không được mất thứ người dùng đã gõ. <details> đóng chỉ
//      ẩn chứ không xoá DOM, nhưng đó là chi tiết cài đặt, phải chốt lại.
//   3. Bàn phím phải dùng được. Đây là lý do chọn <details>/<summary> thật
//      thay vì div giả -- nhưng "chọn đúng thẻ" không tự nó thành bằng chứng.
const { test, expect } = require('@playwright/test');
const { openFilters } = require('./helpers/filters');

const MOBILE = [['nhỏ', 320, 700], ['iPhone', 390, 844], ['lớn', 430, 932]];
const WIDE = [['tablet', 834, 1112], ['laptop', 1366, 768], ['desktop', 1920, 1080]];

async function open(page, key, width, height) {
  await page.setViewportSize({ width, height });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=${key}`);
  await expect(page.locator('.ui-filter-bar').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(300);
}

const probe = () => {
  const disclosure = document.querySelector('.ui-filter-disclosure');
  const summary = document.querySelector('.ui-filter-summary');
  const bar = document.querySelector('.ui-filter-bar');
  const list = document.querySelector('.ec-list');
  return {
    open: disclosure ? disclosure.open : null,
    summaryShown: summary ? getComputedStyle(summary).display !== 'none' : null,
    barHeight: bar ? Math.round(bar.getBoundingClientRect().height) : null,
    listTop: list ? Math.round(list.getBoundingClientRect().top + window.scrollY) : null,
    overflow: document.body.scrollWidth - document.body.clientWidth,
  };
};

for (const [label, width, height] of MOBILE) {
  test(`${label} (${width}px): bộ lọc gập sẵn, nội dung lên cao hẳn`, async ({ page }) => {
    await open(page, 'session-exceptions', width, height);
    const g = await page.evaluate(probe);
    expect(g.open, 'bộ lọc phải gập sẵn trên máy điện thoại').toBe(false);
    expect(g.summaryShown, 'phải thấy dòng "Bộ lọc" để biết mà mở').toBe(true);
    // Bản trước khi gập: 509px. Ngưỡng 200 chốt phần đã lấy lại được.
    expect(g.barHeight, `dải lọc cao ${g.barHeight}px`).toBeLessThan(200);
    // Trước GĐ2: 876px. Sau lưới 2 cột: 740px. Sau khi gập: ~395px.
    expect(g.listTop, `danh sách bắt đầu ở ${g.listTop}px`).toBeLessThan(500);
    expect(g.overflow).toBeLessThanOrEqual(1);
  });
}

for (const [label, width, height] of WIDE) {
  test(`${label} (${width}px): KHÔNG đổi gì -- bộ lọc mở, không có dòng gập`, async ({ page }) => {
    await open(page, 'session-exceptions', width, height);
    const g = await page.evaluate(probe);
    expect(g.open, 'màn rộng phải mở sẵn').toBe(true);
    expect(g.summaryShown, '<details> phải trong suốt ở màn rộng').toBe(false);
    expect(g.overflow).toBeLessThanOrEqual(1);
    // Các ô lọc phải thật sự dùng được, không chỉ "có trong DOM".
    await expect(page.locator('#ecSeverity')).toBeVisible();
  });
}

test('mở ra rồi gõ, gập lại rồi mở lại: không mất gì', async ({ page }) => {
  await open(page, 'session-exceptions', 390, 844);
  await openFilters(page);
  await page.locator('#ecPo').fill('123');
  await page.locator('#ecSeverity').selectOption('HIGH');

  await page.locator('.ui-filter-summary').click();          // gập
  await expect(page.locator('.ui-filter-disclosure')).not.toHaveAttribute('open', '');
  await page.locator('.ui-filter-summary').click();          // mở lại

  await expect(page.locator('#ecPo')).toHaveValue('123');
  await expect(page.locator('#ecSeverity')).toHaveValue('HIGH');
});

test('đổi tab KHÔNG xoá bộ lọc đang nhập', async ({ page }) => {
  // Đổi tab là vẽ lại toàn bộ innerHTML, nên trước bản vá các ô lọc bị thay
  // mới và giá trị vừa gõ biến mất. Không ai yêu cầu điều đó -- đổi tab là đổi
  // NHÓM ngoại lệ đang xem, không phải bỏ điều kiện lọc.
  await open(page, 'session-exceptions', 390, 844);
  await openFilters(page);
  await page.locator('#ecPo').fill('123');
  await page.locator('#ecSeverity').selectOption('HIGH');

  await page.locator('.mf-tab', { hasText: 'Tất cả' }).click();
  await page.waitForTimeout(900);
  await openFilters(page);
  await expect(page.locator('#ecPo')).toHaveValue('123');
  await expect(page.locator('#ecSeverity')).toHaveValue('HIGH');
});

test('dùng được bằng bàn phím', async ({ page }) => {
  await open(page, 'session-exceptions', 390, 844);
  const summary = page.locator('.ui-filter-summary');
  await summary.focus();
  expect(await page.evaluate(() => document.activeElement?.className))
    .toContain('ui-filter-summary');
  await page.keyboard.press('Enter');
  await expect(page.locator('.ui-filter-disclosure')).toHaveAttribute('open', '');
  await page.keyboard.press('Enter');
  await expect(page.locator('.ui-filter-disclosure')).not.toHaveAttribute('open', '');
  // Viền focus phải nhìn thấy -- gập bằng bàn phím mà không biết con trỏ ở đâu
  // thì không dùng được.
  const outline = await summary.evaluate(el => {
    el.focus();
    const cs = getComputedStyle(el, ':focus-visible');
    return cs.outlineStyle !== 'none' || cs.outlineWidth !== '0px';
  });
  expect(outline).toBe(true);
});

test('mọi trang dùng filterBar đều gập được, không trang nào vỡ', async ({ page }) => {
  // 20 nơi gọi filterBar; đây là mẫu đại diện đủ khác nhau về hình dạng bộ lọc
  // (một ô, nhiều ô, ô lọc con có lưới riêng, có checkbox, có nút hành động).
  for (const key of ['session-exceptions', 'rework-queue', 'qr-print', 'system-logs',
                     'session-management', 'production-trace', 'employee-productivity']) {
    await open(page, key, 390, 844);
    const g = await page.evaluate(probe);
    expect(g.open, `${key}: bộ lọc không gập`).toBe(false);
    expect(g.summaryShown, `${key}: không thấy dòng "Bộ lọc"`).toBe(true);
    expect(g.overflow, `${key}: tràn ngang ${g.overflow}px`).toBeLessThanOrEqual(1);
    expect(await openFilters(page), `${key}: không mở được bộ lọc`).toBe(true);
    await expect(page.locator('.ui-filter-controls').first()).toBeVisible();
  }
});

test('không có lỗi console khi gập/mở', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 200)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200)); });
  await open(page, 'session-exceptions', 390, 844);
  await page.locator('.ui-filter-summary').click();
  await page.waitForTimeout(300);
  await page.locator('.ui-filter-summary').click();
  await page.waitForTimeout(300);
  expect(errors, errors.join('\n')).toEqual([]);
});
