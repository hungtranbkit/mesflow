// "Tổng quan sản xuất" / "Tiến trình sản xuất" ở QUY MÔ THẬT: progressive
// disclosure, không mất thông tin (REQ-UI-019) + nút "Lên đầu trang" dùng chung
// (REQ-UI-018).
//
// Đo trước bản vá với 8 PO x 2 Part x 5 OP (= 80 Operation), mọi PO mở sẵn:
//   Tổng quan sản xuất : 10.5 / 10.1 / 7.1 viewport (390 / 1366 / 1920)
//   Tiến trình sản xuất: 11.4 / 11.7 / 8.3 viewport
// Người dùng mô tả đúng cái này: "scroll rất dài và khó biết đang xem PO nào".
//
// Điều kiện "không mất thông tin" được kiểm bằng cách ĐẾM: số thẻ PO và số dòng
// Operation trong DOM phải KHÔNG đổi sau khi thu gọn -- thu gọn là giấu, không
// phải cắt bớt dữ liệu.
const { test, expect } = require('@playwright/test');
const F = require('./helpers/hp3-fixtures');
const { openFilters } = require('./helpers/filters');

const SCREENS = [
  ['overview', 'Tổng quan sản xuất', 'details.overview-po', '#ovExpandAll', '#ovCollapseAll'],
  ['production-schedule', 'Tiến trình sản xuất', 'details.schedule-po', '#scheduleExpandAll', '#scheduleCollapseAll'],
];
const VIEWPORTS = [[390, 844, '390'], [1366, 768, '1366'], [1920, 1080, '1920']];

async function open(page, pg) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  // Chờ /login tự chuyển sang /app xong rồi mới goto tiếp. Khi đã có phiên,
  // /login tự điều hướng, và lệnh goto ngay sau đó bị chính nó cắt ngang
  // ("interrupted by another navigation") -- nguồn flaky đã ghi trong
  // production-schedule-sticky.spec.js (2026-09-09). Từ 71.0.0.290 phiên sống
  // dai hơn hẳn (cookie có Max-Age, idle 14 ngày) nên lần chuyển hướng đó xảy
  // ra đều đặn hơn, và nó nổ ngay cả khi chạy --retries=0.
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=${pg}`);
  await expect(page.locator('#content').first()).toBeVisible({ timeout: 20000 });
}

// Ở màn hẹp bộ lọc GẬP LẠI mặc định (đúng thiết kế -- xem core/ui.js), và từ
// REQ-UI-023 "Tiến trình sản xuất" còn đẩy cả khối lọc vào một tấm mở từ thanh
// sticky 48px. Dùng helper CHUNG ./helpers/filters thay vì bản chép tay ở đây
// -- bản chép tay chỉ biết <details> nên nó vẫn "mở bộ lọc" thành công rồi để
// #scheduleSearch / #scheduleExpandAll nằm trong tấm đang đóng, và bài test
// chết ở locator.click chứ không ở điều nó định kiểm.

for (const [w, h, vp] of VIEWPORTS) {
  for (const [pg, label, cardSel, expandSel, collapseSel] of SCREENS) {
    test(`${label}: mặc định thu gọn, trang không dài quá 5 viewport @${vp}`, async ({ page }) => {
      test.setTimeout(180000);
      await page.setViewportSize({ width: w, height: h });
      await F.mockScale(page);
      await open(page, pg);
      await expect(page.locator(cardSel).first()).toBeVisible({ timeout: 20000 });

      const g = await page.evaluate(sel => {
        const cards = [...document.querySelectorAll(sel)];
        return {
          cards: cards.length,
          openCards: cards.filter(c => c.open).length,
          viewports: document.documentElement.scrollHeight / window.innerHeight,
          overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        };
      }, cardSel);

      expect(g.cards, 'phải có nhiều PO để bài này có nghĩa').toBeGreaterThan(4);
      // Đây là điều kiện cốt lõi: KHÔNG mở sẵn tất cả.
      expect(g.openCards, `${label} mở sẵn ${g.openCards}/${g.cards} PO @${vp}`).toBeLessThanOrEqual(1);
      expect(g.viewports, `${label} vẫn dài ${g.viewports.toFixed(1)} viewport @${vp}`).toBeLessThan(5);
      expect(g.overflowX, `${label} tràn ngang @${vp}`).toBe(false);
    });

    test(`${label}: mở/thu từng PO và "Mở tất cả"/"Thu gọn" không mất dữ liệu @${vp}`, async ({ page }) => {
      test.setTimeout(180000);
      await page.setViewportSize({ width: w, height: h });
      await F.mockScale(page);
      await open(page, pg);
      await expect(page.locator(cardSel).first()).toBeVisible({ timeout: 20000 });

      const count = sel => page.evaluate(s => document.querySelectorAll(s).length, sel);
      const opSel = '.overview-op-row,.gantt-label,.schedule-op';
      await openFilters(page);
      const poBefore = await count(cardSel);
      const opsBefore = await count(opSel);

      // Mở tất cả -> mọi thẻ open, số PO/OP trong DOM không đổi.
      // openFilters() trước MỖI lần bấm: ở <=700px tấm lọc tự đóng sau khi
      // chọn xong (REQ-UI-023) -- đó là chủ ý, người dùng cần thấy danh sách
      // bên dưới đổi theo. Ở desktop hàm này không làm gì.
      await openFilters(page);
      await page.locator(expandSel).click();
      await expect.poll(async () => page.evaluate(s =>
        [...document.querySelectorAll(s)].every(c => c.open), cardSel), { timeout: 8000 }).toBe(true);
      expect(await count(cardSel)).toBe(poBefore);
      expect(await count(opSel)).toBe(opsBefore);

      // Thu gọn -> mọi thẻ đóng, và vẫn KHÔNG mất gì trong DOM.
      await openFilters(page);
      await page.locator(collapseSel).click();
      await expect.poll(async () => page.evaluate(s =>
        [...document.querySelectorAll(s)].some(c => c.open), cardSel), { timeout: 8000 }).toBe(false);
      expect(await count(cardSel), 'thu gọn không được xoá thẻ PO').toBe(poBefore);
      expect(await count(opSel), 'thu gọn không được xoá dòng Operation').toBe(opsBefore);

      // Mở lại đúng MỘT thẻ bằng chính <summary> -- bàn phím/chuột đều phải được.
      const first = page.locator(cardSel).first();
      await first.locator('summary').click();
      await expect.poll(async () => first.evaluate(c => c.open), { timeout: 8000 }).toBe(true);
    });
  }

  test(`Tiến trình sản xuất: tìm nhanh lọc theo PO/Part/Operation @${vp}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockScale(page);
    await open(page, 'production-schedule');
    await expect(page.locator('details.schedule-po').first()).toBeVisible({ timeout: 20000 });
    const allPos = await page.evaluate(() => document.querySelectorAll('details.schedule-po').length);
    await openFilters(page);

    await page.locator('#scheduleSearch').fill('PO-1003');
    await expect.poll(async () => page.evaluate(() =>
      document.querySelectorAll('details.schedule-po').length), { timeout: 8000 }).toBeLessThan(allPos);
    const codes = await page.evaluate(() =>
      [...document.querySelectorAll('details.schedule-po')].map(d => d.dataset.poCode));
    expect(codes.every(c => c.includes('PO-1003')), `lọc ra ${codes.join(',')}`).toBe(true);

    // Trạng thái bộ lọc phải nằm trong URL để chia sẻ/refresh được.
    await expect.poll(async () => new URL(page.url()).searchParams.get('q'), { timeout: 8000 })
      .toBe('PO-1003');

    await page.locator('#scheduleSearch').fill('');
    await expect.poll(async () => page.evaluate(() =>
      document.querySelectorAll('details.schedule-po').length), { timeout: 8000 }).toBe(allPos);
  });

  test(`Nút "Lên đầu trang": ẩn ở đỉnh, hiện khi cuộn xa, bấm về đầu @${vp}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockScale(page);
    await open(page, 'production-schedule');
    await openFilters(page);
    await page.locator('#scheduleExpandAll').click();   // làm trang đủ dài
    await page.waitForTimeout(400);

    const btn = page.locator('[data-back-to-top]');
    await expect(btn, 'ở đỉnh trang thì phải ẩn').toBeHidden();

    await page.evaluate(() => window.scrollTo(0, window.innerHeight * 2));
    await expect(btn, 'cuộn qua 1.5 viewport thì phải hiện').toBeVisible({ timeout: 8000 });

    // Không được đè lên bottom bar / vùng safe-area của iPhone.
    const box = await btn.boundingBox();
    const vpH = await page.evaluate(() => window.innerHeight);
    expect(box.y + box.height, 'nút tràn khỏi đáy viewport').toBeLessThanOrEqual(vpH);
    expect(box.height, 'vùng bấm tối thiểu 44px').toBeGreaterThanOrEqual(44);

    await btn.click();
    await expect.poll(async () => page.evaluate(() => window.scrollY), { timeout: 8000 }).toBe(0);
    await expect(btn, 'về đỉnh thì phải ẩn lại').toBeHidden();
  });
}

test('Nút "Lên đầu trang" không hiện trên trang ngắn', async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await F.mockScale(page, { pos: 1, parts: 1, ops: 1 });
  await open(page, 'production-schedule');
  await page.waitForTimeout(1200);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(500);
  await expect(page.locator('[data-back-to-top]'),
    'trang ngắn hơn ngưỡng thì không được hiện nút').toBeHidden();
});

// Nhánh "script nạp SAU khi DOM đã sẵn sàng" -- nhánh `else` của khối auto-mount.
// Hôm nay app không đi vào nhánh đó (core/ui.js là script CHẶN, không defer), nên
// KHÔNG bài nào chạm tới nó: quả mìn nằm im. Nếu khối auto-mount đứng TRƯỚC khai
// báo `const mountBackToTop` thì nhánh này ném ReferenceError ngay, trước cả
// `return {...}` -- window.MFUI không được gán và cả app chết.
//
// Phải nạp vào một trang TRỐNG chứ không phải trang app: core/ui.js khai báo
// `const MFUI` ở tầng global, nạp lần hai trong cùng document là
// "Identifier 'MFUI' has already been declared" -- script không chạy, và bài test
// sẽ đỏ vì lý do chẳng liên quan gì tới TDZ (đã đâm đúng bẫy này một lần).
test('core/ui.js nạp được cả khi DOM đã sẵn sàng (không TDZ)', async ({ page }) => {
  test.setTimeout(120000);
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  // Neo vào một URL cùng origin và KHÔNG redirect. `/login` tự chuyển hướng vì
  // auto-login của môi trường test, và cú chuyển hướng đó huỷ context ngay giữa
  // setContent -- lỗi chẳng liên quan gì tới thứ đang kiểm.
  await page.goto('/static/core/ui.js');
  await page.setContent('<!doctype html><html><body><div id="content"></div></body></html>');
  await page.waitForLoadState('load');

  const ready = await page.evaluate(() => document.readyState);
  expect(ready, 'phải nạp khi DOM đã ready thì mới đúng nhánh cần kiểm').not.toBe('loading');

  await page.addScriptTag({ url: '/static/core/ui.js' });

  const g = await page.evaluate(() => ({
    hasMFUI: typeof window.MFUI === 'object' && window.MFUI !== null,
    hasPrimitive: typeof window.MFUI?.mountBackToTop === 'function',
    mounted: !!document.querySelector('[data-back-to-top]'),
  }));

  expect(g.hasMFUI, 'window.MFUI phải được gán -- nếu không thì IIFE đã ném trước return').toBe(true);
  expect(g.hasPrimitive, 'primitive phải còn trong export (bảo hiểm khi merge lấy nhầm một bên)').toBe(true);
  expect(g.mounted, 'nhánh else phải gắn được nút ngay, không hoãn').toBe(true);
  expect(errors, `lỗi runtime khi nạp core/ui.js lúc DOM đã ready: ${errors.join(' | ')}`).toEqual([]);
});
