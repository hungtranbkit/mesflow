// Khu tiến độ của thẻ "Tiến độ theo Operation" phải chiếm ~2/3 bề rộng dùng
// được của thẻ trên desktop.
//
// Vì sao cần bài này: `.op-card-body` dùng chung cho BỐN danh sách thẻ, và rule
// desktop của nó là `repeat(auto-fit,minmax(230px,1fr))` -- chia đều mọi cột.
// Với ba danh sách kia (Dashboard theo ngày, danh sách Operation, Hàng chờ sửa)
// chia đều là đúng: chúng chỉ xếp các ô dữ kiện ngang hàng. Nhưng thẻ "Tiến độ
// theo Operation" có `.op-dual-progress` -- hai thanh đo là NỘI DUNG CHÍNH --
// cạnh một cột chỉ vài dòng chữ ngắn. Đo ở 1366x768 trước khi vá:
//
//   grid-template-columns: 519px 519px   -> thanh đo 49.6% bề rộng dùng được
//
// tức nửa phải của thẻ gần như trống trong khi thanh đo bị bóp còn một nửa.
//
// Bài này đo HÌNH HỌC THẬT (getBoundingClientRect), không đọc CSS: nó còn đúng
// dù sau này tỉ lệ đến từ grid, flex hay token khác. Ngưỡng đặt theo yêu cầu
// người dùng (~2/3), có biên để không vỡ vì làm tròn hay đổi gap.
const { test, expect } = require('@playwright/test');
const F = require('./helpers/hp3-fixtures');

async function open(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
}

async function measure(page) {
  await page.goto('/app?page=dashboard&tab=overview');
  await expect(page.locator('#opTimeProgress .op-card').first()).toBeVisible({ timeout: 20000 });
  return page.evaluate(() => {
    const card = document.querySelector('#opTimeProgress .op-card');
    const body = card.querySelector('.op-card-body');
    const prog = card.querySelector('.op-dual-progress');
    const fact = card.querySelector('.op-card-fact');
    const r = el => el.getBoundingClientRect();
    const bodyR = r(body), progR = r(prog), factR = r(fact);
    // Chữ có bị tràn ra khỏi cột của nó không -- đo trên MỌI phần tử con.
    const overflowing = [...body.querySelectorAll('*')].filter(el => {
      const p = el.parentElement;
      return p && el.getBoundingClientRect().right > p.getBoundingClientRect().right + 1;
    }).length;
    return {
      bodyW: bodyR.width,
      progPct: progR.width / bodyR.width * 100,
      factW: factR.width,
      stacked: factR.top >= progR.bottom - 1,
      // Hai cột có thực sự nằm cạnh nhau và KHÔNG chồng lên nhau không.
      overlap: !(factR.left >= progR.right - 1 || factR.top >= progR.bottom - 1),
      overflowing,
      docOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      timeMeterW: card.querySelector('.op-time-meter').getBoundingClientRect().width,
      productMeterW: card.querySelector('.op-product-meter').getBoundingClientRect().width,
    };
  });
}

for (const [w, h] of [[1366, 768], [1024, 768]]) {
  test(`@${w}x${h}: khu tiến độ chiếm ~2/3 bề rộng thẻ`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockAll(page);
    await open(page);
    const m = await measure(page);

    expect(m.stacked, 'desktop phải xếp NGANG hai cột').toBe(false);
    expect(m.progPct, `khu tiến độ đang chiếm ${m.progPct.toFixed(1)}% bề rộng dùng được, `
      + 'cần ~2/3 (66-70%)').toBeGreaterThanOrEqual(64);
    expect(m.progPct, `khu tiến độ chiếm ${m.progPct.toFixed(1)}%, rộng quá thì cột dữ kiện `
      + 'bên phải bị bóp').toBeLessThanOrEqual(72);

    // Cột dữ kiện vẫn phải dùng được, không bị bóp thành một sợi.
    expect(m.factW, 'cột "Người làm"/sản lượng bị bóp quá hẹp').toBeGreaterThanOrEqual(180);
    expect(m.overlap, 'hai cột chồng lên nhau').toBe(false);
    expect(m.overflowing, 'có phần tử tràn ra ngoài cột của nó').toBe(0);
    expect(m.docOverflow, 'trang tràn ngang').toBeLessThanOrEqual(0);

    // Cả hai thanh đo cùng rộng ra, không phải chỉ thanh thời gian.
    expect(m.timeMeterW).toBeGreaterThan(m.bodyW * 0.5);
    expect(m.productMeterW).toBeGreaterThan(m.bodyW * 0.5);
  });
}

test('@390x844: mobile vẫn xếp một cột, thanh đo chiếm trọn bề rộng, không tràn ngang', async ({ page }) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 390, height: 844 });
  await F.mockAll(page);
  await open(page);
  const m = await measure(page);

  expect(m.stacked, 'mobile phải xếp DỌC, dữ kiện xuống dưới thanh đo').toBe(true);
  expect(m.progPct, 'mobile: thanh đo phải chiếm trọn bề rộng').toBeGreaterThanOrEqual(99);
  expect(m.overflowing, 'có phần tử tràn ra ngoài cột của nó').toBe(0);
  expect(m.docOverflow, 'trang tràn ngang ở mobile').toBeLessThanOrEqual(0);
});

// Ba danh sách thẻ KHÁC vẫn chia đều -- bản vá chỉ được chạm .op-time-panel.
test('@1366x768: các danh sách .op-card khác không bị đổi tỉ lệ cột', async ({ page }) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 1366, height: 768 });
  await F.mockAll(page);
  await open(page);
  await page.goto('/app?page=dashboard&tab=output');
  await expect(page.locator('#dailyAttention .op-card').first()).toBeVisible({ timeout: 20000 });
  const cols = await page.evaluate(() => {
    const body = document.querySelector('#dailyAttention .op-card .op-card-body');
    const w = [...body.children].map(c => Math.round(c.getBoundingClientRect().width));
    return { widths: w, distinct: [...new Set(w)].length };
  });
  expect(cols.widths.length, 'thẻ này phải có ít nhất hai ô dữ kiện').toBeGreaterThan(1);
  expect(cols.distinct, `các ô phải rộng BẰNG NHAU, đo được ${cols.widths.join('/')}`).toBe(1);
});
