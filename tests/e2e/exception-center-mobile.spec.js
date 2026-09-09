// Trung tâm ngoại lệ trên máy điện thoại, và hai primitive dùng chung mà nó
// làm lộ ra (.mf-tabs / .ui-filter-bar).
//
// Bug thật, screenshot iPhone 2026-09-09: 5 tab trạng thái xếp thành một cột
// cao 255px, gạch active kéo hết chiều ngang nên đọc như đường kẻ phân cách;
// các ô lọc so le 105/267/175/125px; ô ngày chỉ 125px; ngoại lệ đầu tiên nằm
// ở 876px, tức gần một màn hình rưỡi cuộn trước khi thấy nội dung chính.
//
// Hai nguyên nhân gốc, cả hai đều nằm trong CSS DÙNG CHUNG:
//
//   1. @media(max-width:520px){.mf-tab{width:100%}} -- vô hại ở dải tab không
//      wrap (flex-shrink co lại: tab rộng nhất của Production Trace là 96px ở
//      cả 390px lẫn 1366px), nhưng .ec-tabs có flex-wrap:wrap nên mỗi tab
//      chiếm trọn một dòng.
//   2. .ui-filter-controls là flex-wrap, mỗi <label> tự co theo nội dung rộng
//      nhất của nó -- cùng bộ lọc cho ra đúng những bề rộng so le đó ở MỌI
//      viewport. Màn rộng che đi, màn 390px thì phơi ra.
//
// Vì vậy spec này kiểm cả các trang khác dùng chung hai primitive: sửa
// primitive mà làm hỏng chỗ khác thì phải đỏ ở đây, không phải ngoài hiện
// trường.
const { test, expect } = require('@playwright/test');

const PHONES = [['iPhone 12/13/14', 390, 844], ['iPhone X', 375, 812],
                ['iPhone 14 Pro Max', 430, 932]];
const WIDE = [['tablet', 834, 1112], ['laptop', 1366, 768], ['desktop', 1920, 1080]];

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
}

async function open(page, key, { width, height }) {
  await page.setViewportSize({ width, height });
  await page.goto(`/app?page=${key}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
}

const geometry = () => {
  const box = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
  const tabs = box('.mf-tabs');
  const active = document.querySelector('.mf-tabs .mf-tab.active');
  const bar = box('.ui-filter-bar');
  const list = box('.ec-list');
  return {
    viewport: document.body.clientWidth,
    overflow: document.body.scrollWidth - document.body.clientWidth,
    tabsHeight: tabs ? Math.round(tabs.height) : null,
    tabWidths: [...document.querySelectorAll('.mf-tabs .mf-tab')].map(e => Math.round(e.getBoundingClientRect().width)),
    activeWidth: active ? Math.round(active.getBoundingClientRect().width) : null,
    barHeight: bar ? Math.round(bar.height) : null,
    listTop: list ? Math.round(list.top + window.scrollY) : null,
    fieldWidths: [...document.querySelectorAll('.ui-filter-controls > label')]
      .map(e => Math.round(e.getBoundingClientRect().width)),
    dateWidths: [...document.querySelectorAll('.ui-filter-controls input[type=date]')]
      .map(e => Math.round(e.getBoundingClientRect().width)),
    applyWidth: (() => { const b = box('.ui-filter-bar-actions .btn'); return b ? Math.round(b.width) : null; })(),
  };
};

for (const [label, width, height] of PHONES) {
  test(`${label} (${width}px): dải tab là hàng pill, không phải cột cao`, async ({ page }) => {
    await login(page);
    await open(page, 'session-exceptions', { width, height });
    const g = await page.evaluate(geometry);

    // Bản lỗi: 255px (5 tab × 44px + summary). Hai hàng pill + summary vừa
    // dưới 160px; ngưỡng này đỏ ngay nếu tab lại xếp thành cột.
    expect(g.tabsHeight, `dải tab cao ${g.tabsHeight}px`).toBeLessThan(160);

    // Không tab nào được chiếm trọn chiều ngang -- đó chính là cái làm nó
    // thành cột, và làm gạch active trông như đường kẻ phân cách.
    for (const w of g.tabWidths) {
      expect(w, `tab rộng ${w}px trên viewport ${g.viewport}px`).toBeLessThan(g.viewport * 0.8);
    }
    // Gạch active nằm đúng trên item đang chọn.
    expect(g.activeWidth).toBeLessThan(g.viewport * 0.8);
    expect(g.overflow, `tràn ngang ${g.overflow}px`).toBeLessThanOrEqual(1);
  });

  test(`${label} (${width}px): bộ lọc là lưới đều, ô ngày rộng dùng được`, async ({ page }) => {
    await login(page);
    await open(page, 'session-exceptions', { width, height });
    const g = await page.evaluate(geometry);

    // Bản lỗi cho ra 105/267/175/175/175/125/125/134 -- so le ở mọi viewport.
    // Sau bản vá mỗi ô hoặc là nửa hàng, hoặc là trọn hàng (ô ngày), nên chỉ
    // còn tối đa hai bề rộng khác nhau.
    const distinct = [...new Set(g.fieldWidths)];
    expect(distinct.length, `bề rộng ô lọc: ${g.fieldWidths}`).toBeLessThanOrEqual(2);

    // Ô ngày phải trọn hàng: 162px là bấm được nhưng chật, và bản lỗi cho
    // đúng 125px.
    expect(g.dateWidths.length).toBeGreaterThan(0);
    for (const w of g.dateWidths) {
      expect(w, `ô ngày rộng ${w}px`).toBeGreaterThan(g.viewport * 0.7);
    }

    // Nút Áp dụng trải hết chiều ngang, không nép phải nửa vời.
    expect(g.applyWidth, `nút Áp dụng rộng ${g.applyWidth}px`).toBeGreaterThan(g.viewport * 0.7);
    expect(g.overflow).toBeLessThanOrEqual(1);
  });

  test(`${label} (${width}px): tới danh sách ngoại lệ sớm hơn hẳn bản lỗi`, async ({ page }) => {
    await login(page);
    await open(page, 'session-exceptions', { width, height });
    const g = await page.evaluate(geometry);
    // Đo được trên TEST trước bản vá: 876px (390/375), 803px (430). Ngưỡng
    // 800px chốt phần đã lấy lại được -- KHÔNG phải lời hứa rằng bộ lọc đã
    // đủ gọn; 8 trường lọc vẫn là nhiều cho một màn hình dọc.
    expect(g.listTop, `danh sách bắt đầu ở ${g.listTop}px`).toBeLessThan(800);
  });
}

test('không có lỗi console/page trên viewport điện thoại', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 200)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200)); });
  await login(page);
  await open(page, 'session-exceptions', { width: 390, height: 844 });
  await page.locator('.mf-tabs .mf-tab', { hasText: 'Tất cả' }).click();
  await page.waitForTimeout(600);
  expect(errors, errors.join('\n')).toEqual([]);
});

for (const [label, width, height] of WIDE) {
  test(`${label} (${width}px): không đổi -- vẫn một hàng tab, bộ lọc vẫn flex`, async ({ page }) => {
    await login(page);
    await open(page, 'session-exceptions', { width, height });
    const g = await page.evaluate(geometry);
    // Một hàng tab: 44px tab + viền. Bộ lọc giữ nguyên hình flex cũ, nghĩa là
    // các ô VẪN so le (>2 bề rộng ở laptop/desktop) -- đó là hành vi cũ và
    // bản vá cố ý không đụng tới.
    expect(g.tabsHeight).toBeLessThan(60);
    expect(g.overflow).toBeLessThanOrEqual(1);
    if (width >= 1366) {
      expect([...new Set(g.fieldWidths)].length,
        'trên 900px phải giữ nguyên flex cũ, không chuyển sang lưới').toBeGreaterThan(2);
    }
  });
}

// --- primitive dùng chung: các trang khác không được vỡ theo -------------

const SHARED = [
  ['production-trace', '.mf-tabs'],
  ['system-logs', '.mf-tabs'],
  ['rework-queue', '.ui-filter-bar'],
  ['qr-print', '.ui-filter-bar'],
  ['session-management', '.ui-filter-bar'],
];

for (const [key, marker] of SHARED) {
  test(`${key} dùng chung primitive: không tràn ngang, không tab chiếm trọn hàng (390px)`, async ({ page }) => {
    await login(page);
    await open(page, key, { width: 390, height: 844 });
    await expect(page.locator(marker).first()).toBeVisible();
    const g = await page.evaluate(geometry);
    expect(g.overflow, `${key} tràn ngang ${g.overflow}px`).toBeLessThanOrEqual(1);
    for (const w of g.tabWidths) {
      expect(w, `${key}: tab rộng ${w}px`).toBeLessThan(g.viewport * 0.8);
    }
    if (g.fieldWidths.length) {
      expect([...new Set(g.fieldWidths)].length,
        `${key}: bề rộng ô lọc ${g.fieldWidths}`).toBeLessThanOrEqual(2);
    }
  });
}

test('tablet 834px giữ nguyên bộ lọc dạng flex, không bị đẩy cao lên', async ({ page }) => {
  await login(page);
  await open(page, 'session-exceptions', { width: 834, height: 1112 });
  const g = await page.evaluate(geometry);
  // Đo được: flex xếp 8 trường vừa 2 hàng (192px). Một bản vá đặt ngưỡng lưới
  // ở 900px thay vì 700px đẩy con số này lên 453px -- chính là lý do có bài
  // test này.
  expect(g.barHeight, `bộ lọc cao ${g.barHeight}px ở 834px`).toBeLessThan(260);
  expect(g.overflow).toBeLessThanOrEqual(1);
});

test('trạng thái rỗng xuống dòng, không dính tiêu đề vào phần giải thích', async ({ page }) => {
  await login(page);
  await open(page, 'session-exceptions', { width: 390, height: 844 });
  const empty = page.locator('.ec-list .empty');
  if (await empty.count()) {
    const stacked = await empty.first().evaluate(el => {
      const b = el.querySelector('b'), s = el.querySelector('span');
      if (!b || !s) return true;
      return s.getBoundingClientRect().top >= b.getBoundingClientRect().bottom - 1;
    });
    expect(stacked, 'tiêu đề và phần giải thích của trạng thái rỗng nằm cùng dòng').toBe(true);
  }
});
