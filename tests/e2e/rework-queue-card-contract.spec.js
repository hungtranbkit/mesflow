// "Hàng chờ sửa": mỗi sản phẩm chờ sửa là một THẺ độc lập (REQ-UI-016).
//
// Báo từ người dùng kèm ảnh thật: các kết quả đang là row vuông nối liền trong
// một bảng. Đo lại đúng vậy trước bản vá: `.rq-row` là lưới 6 cột với
// `min-width:1000px` và `border-bottom:1px solid #e8edf2`, nằm trong
// `.rq-table{overflow:auto}` -- ở 390px phải kéo ngang gần ba lần bề ngang màn
// hình mới đọc hết MỘT bản ghi, và các bản ghi dính liền bằng kẻ ngang.
//
// Bài này đo trên DOM thật (không đọc CSS gap) ở cả ba viewport.
const { test, expect } = require('@playwright/test');
const F = require('./helpers/hp3-fixtures');

async function openRework(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=rework-queue');
  await expect(page.locator('.rq-card').first()).toBeVisible({ timeout: 20000 });
}

for (const [w, h, vp] of [[390, 844, '390'], [1366, 768, '1366'], [1920, 1080, '1920']]) {
  test(`thẻ chờ sửa: bo góc canonical + gap dọc + không kẻ ngang @${vp}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockAll(page);
    await openRework(page);

    const g = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const list = document.querySelector('.rq-list');
      const cards = [...document.querySelectorAll('.rq-card')];
      const cs = cards.map(c => getComputedStyle(c));
      const rects = cards.map(c => c.getBoundingClientRect());
      const gaps = rects.slice(1).map((r, i) => Math.round(r.top - rects[i].bottom));
      return {
        count: cards.length,
        listGap: list ? getComputedStyle(list).rowGap : null,
        radii: [...new Set(cs.map(c => c.borderTopLeftRadius))],
        gaps: [...new Set(gaps)],
        // Thẻ = viền khép kín bốn cạnh; dòng bảng = chỉ có kẻ dưới.
        openOutlines: cs.filter(c => new Set([c.borderTopWidth, c.borderRightWidth,
          c.borderBottomWidth, c.borderLeftWidth]).size !== 1).length,
        tokenSurface: root.getPropertyValue('--radius-surface').trim(),
        tokenSpace3: root.getPropertyValue('--ui-space-3').trim(),
        headRows: document.querySelectorAll('.rq-list .head').length,
        // Không bản ghi nào bắt người dùng kéo ngang để đọc.
        widest: Math.max(...cards.map(c => c.scrollWidth - c.clientWidth)),
        docOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      };
    });

    expect(g.count).toBeGreaterThan(1);
    expect(g.radii, 'mọi thẻ cùng một bo góc').toHaveLength(1);
    expect(g.radii[0], 'thẻ phải bo theo --radius-surface').toBe(g.tokenSurface);
    expect(g.listGap, 'danh sách phải có gap dọc lấy từ thang spacing').toBe(g.tokenSpace3);
    expect(g.gaps, 'khoảng hở thật giữa các thẻ phải đều').toHaveLength(1);
    expect(g.gaps[0], 'các thẻ phải TÁCH nhau, không dính thành bảng').toBeGreaterThan(0);
    expect(g.openOutlines, 'thẻ phải có viền khép kín, không phải kẻ ngang chia dòng').toBe(0);
    expect(g.headRows, 'danh sách thẻ không có hàng tiêu đề kiểu bảng').toBe(0);
    expect(g.widest, 'không thẻ nào phải cuộn ngang để đọc').toBe(0);
    expect(g.docOverflow, `trang tràn ngang @${vp}`).toBe(false);
  });
}

test('thẻ chờ sửa giữ thứ bậc: tên Operation chính, mã/Part phụ, số chờ sửa bên phải', async ({ page }) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 390, height: 844 });
  await F.mockAll(page);
  await openRework(page);
  const g = await page.evaluate(() => {
    const card = document.querySelector('.rq-card');
    const title = card.querySelector('.row-title');
    const code = card.querySelector('.row-code');
    const meta = card.querySelector('.op-identity-meta');
    const aside = card.querySelector('.op-card-aside');
    const px = v => parseFloat(v);
    return {
      title: title?.textContent?.trim(), code: code?.textContent?.trim(),
      titleSize: px(getComputedStyle(title).fontSize),
      codeSize: code ? px(getComputedStyle(code).fontSize) : null,
      metaSize: meta ? px(getComputedStyle(meta).fontSize) : null,
      titleColor: getComputedStyle(title).color,
      codeColor: code ? getComputedStyle(code).color : null,
      asideRight: Math.round(aside.getBoundingClientRect().right),
      cardRight: Math.round(card.getBoundingClientRect().right),
      identityLeft: Math.round(card.querySelector('.op-card-identity').getBoundingClientRect().left),
      pending: aside.querySelector('strong')?.textContent?.trim(),
    };
  });
  expect(g.title, 'tên Operation phải có mặt').toBeTruthy();
  expect(g.codeSize).toBeLessThan(g.titleSize);
  expect(g.metaSize).toBeLessThan(g.titleSize);
  expect(g.codeColor).not.toBe(g.titleColor);
  expect(g.pending, 'số chờ sửa là dữ kiện chính bên phải').toBeTruthy();
  expect(g.asideRight).toBeGreaterThan(g.identityLeft);
  expect(g.cardRight - g.asideRight, 'khối phải phải bám mép phải của thẻ').toBeLessThan(40);
});
