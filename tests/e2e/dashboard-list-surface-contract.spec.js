// Hợp đồng "mặt danh sách" cho nhóm DASHBOARD / REPORT / EXCEPTION / SESSION.
//
// Bổ sung cho hai lớp guard đã có, KHÔNG thay chúng:
//   * tests/test_ui_surface_radius_is_canonical.py -- đọc CSS tĩnh.
//   * tests/e2e/card-surface-contract.spec.js      -- khoá mặt THẺ.
// Cái này khoá hai thứ cả hai đều không nói được:
//
//   1. Dải TAB phải lấy từ primitive dùng chung .mf-tabs/.mf-tab, không màn nào
//      tự vẽ lại.
//   2. Mọi surface trên 4 nhóm màn này phải lấy bo góc TỪ THANG CANONICAL
//      (--radius-surface / --radius-surface-row / --radius-control), đo bằng
//      computed style thật.
//
// Vì sao cần (2) dù đã có guard Python: `_is_surface` bên đó nhận diện surface
// bằng HẬU TỐ selector `-card|-panel|-section`. Vỏ bảng, dòng danh sách và
// banner (`.op-time-table`, `.daily-op-table`, `.session-manage-row`,
// `.session-inbox-banner`, `.session-accordion-item`) không khớp hậu tố nào nên
// guard bỏ qua -- và đó là đúng cách một lane trước (chính lane này) để lọt
// `--radius-card` lên một vỏ bảng mà mọi bài test vẫn xanh. Bài dưới đo DOM
// thật nên không phụ thuộc cách đặt tên class.
//
// Đo trên TEST trước bản vá, dải tab "Dashboard theo ngày" là bản dựng lại hoàn
// toàn riêng của .mf-tabs, sáu giá trị viết cứng:
//
//   .dashboard-tabs   nền #f8fafb, viền dưới #d9dee7
//   .dashboard-tab    chữ #667382, hover #eef3f6
//   .dashboard-tab.active  chữ #18324a, gạch chân #245b82
//
// trong khi Trung tâm ngoại lệ / Nhật ký ứng dụng / Production Trace / Hướng
// dẫn đều đã dùng .mf-tabs (toàn token). Cùng vai trò, hai hình. Nguyên nhân là
// cơ chế: primitive có sẵn nhưng không gì BẮT màn mới dùng -- nên spec này so
// hai dải tab VỚI NHAU, không so với một danh sách giá trị chép tay (danh sách
// chép tay chính là thứ đã hỏng ở lần chuẩn hoá trước).
const { test, expect } = require('@playwright/test');
const F = require('./helpers/hp3-fixtures');

async function open(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
}

// Chữ ký hình học của một dải tab + một tab chưa chọn. Cố ý KHÔNG gồm màu chữ
// của tab đang chọn: đó là accent theo trạng thái, không phải hình khối.
const stripSignature = (stripSel, tabSel) => ({ stripSel, tabSel });
async function readStrip(page, { stripSel, tabSel }) {
  return page.evaluate(({ stripSel, tabSel }) => {
    const strip = document.querySelector(stripSel);
    const tab = document.querySelector(tabSel);
    if (!strip || !tab) return `MISSING(${stripSel} | ${tabSel})`;
    const a = getComputedStyle(strip), b = getComputedStyle(tab);
    return [
      `strip.radius=${a.borderTopLeftRadius}`,
      `strip.borderBottom=${a.borderBottomWidth} ${a.borderBottomColor}`,
      `strip.display=${a.display}`, `strip.overflowX=${a.overflowX}`,
      `tab.padding=${b.padding}`, `tab.fontSize=${b.fontSize}`, `tab.fontWeight=${b.fontWeight}`,
      `tab.color=${b.color}`, `tab.borderBottomWidth=${b.borderBottomWidth}`,
      `tab.background=${b.backgroundColor}`,
    ].join(' | ');
  }, { stripSel, tabSel });
}

test('dải tab Dashboard theo ngày dùng chung primitive với Trung tâm ngoại lệ', async ({ page }) => {
  await F.mockAll(page);
  await open(page);

  await page.goto('/app?page=session-exceptions');
  await expect(page.locator('.ec-tabs')).toBeVisible({ timeout: 15000 });
  const ec = await readStrip(page, stripSignature('.ec-tabs', '.mf-tab:not(.active)'));

  await page.goto('/app?page=dashboard&tab=overview');
  await expect(page.locator('.dashboard-tabs')).toBeVisible({ timeout: 15000 });
  const dash = await readStrip(page, stripSignature('.dashboard-tabs', '.dashboard-tab:not(.active)'));

  expect(dash, `dải tab Dashboard lệch khỏi primitive dùng chung\n  EC  : ${ec}\n  DASH: ${dash}`).toBe(ec);
});

test('ba tab A/B/C thực sự mang class của primitive, không chỉ trông giống', async ({ page }) => {
  await F.mockAll(page);
  await open(page);
  await page.goto('/app?page=dashboard&tab=overview');
  await expect(page.locator('.dashboard-tabs')).toBeVisible({ timeout: 15000 });
  // Trông giống mà không dùng chung class thì lần đổi token sau lại lệch tiếp.
  await expect(page.locator('nav.dashboard-tabs.mf-tabs')).toHaveCount(1);
  await expect(page.locator('button.dashboard-tab.mf-tab')).toHaveCount(3);
  // Vai trò/a11y giữ nguyên -- bản vá này chỉ đổi lớp trình bày.
  await expect(page.locator('nav.dashboard-tabs[role="tablist"]')).toHaveCount(1);
  await expect(page.locator('button.dashboard-tab[role="tab"][aria-selected="true"]')).toHaveCount(1);
});

test('danh sách Operation là THẺ độc lập: bo góc canonical + gap dọc, không kẻ ngang', async ({ page }) => {
  test.setTimeout(180000);
  await F.mockAll(page);
  await open(page);
  for (const [q, listSel] of [
    ['dashboard&tab=overview', '#opTimeProgress .op-card-list'],
    ['dashboard&tab=output', '#dailyAttention .op-card-list'],
  ]) {
    await page.goto(`/app?page=${q}`);
    await expect(page.locator(listSel)).toBeVisible({ timeout: 15000 });
    const g = await page.evaluate(listSel => {
      const root = getComputedStyle(document.documentElement);
      const list = document.querySelector(listSel);
      const cards = [...list.querySelectorAll('.op-card')];
      const cs = cards.map(c => getComputedStyle(c));
      const rects = cards.map(c => c.getBoundingClientRect());
      // Khoảng hở THẬT giữa hai thẻ liên tiếp, đo trên DOM chứ không đọc CSS gap:
      // gap chỉ có nghĩa nếu nó thực sự tách hai thẻ ra.
      const gaps = rects.slice(1).map((r, i) => Math.round(r.top - rects[i].bottom));
      return {
        count: cards.length,
        listGap: getComputedStyle(list).rowGap,
        radii: [...new Set(cs.map(c => c.borderTopLeftRadius))],
        gaps: [...new Set(gaps)],
        // Phân biệt THẺ với DÒNG BẢNG: thẻ có viền KHÉP KÍN (bốn cạnh bằng
        // nhau) và tách nhau bằng gap; dòng bảng chỉ có kẻ dưới, dính liền
        // nhau. Không kiểm "bottom = 0" -- thẻ vẫn có viền dưới, đó là một
        // cạnh của đường bao, không phải đường kẻ chia dòng.
        openOutlines: cs.filter(c => new Set([c.borderTopWidth, c.borderRightWidth,
          c.borderBottomWidth, c.borderLeftWidth]).size !== 1).length,
        borderWidths: [...new Set(cs.map(c => c.borderTopWidth))],
        tokenSurface: root.getPropertyValue('--radius-surface').trim(),
        tokenSpace3: root.getPropertyValue('--ui-space-3').trim(),
        // Không còn hàng tiêu đề kiểu bảng.
        headRows: document.querySelectorAll(`${listSel} .head`).length,
      };
    }, listSel);

    expect(g.count, `${q}: phải có thẻ Operation`).toBeGreaterThan(1);
    expect(g.radii, `${q}: mọi thẻ Operation cùng một bo góc`).toHaveLength(1);
    expect(g.radii[0], `${q}: thẻ phải bo theo --radius-surface`).toBe(g.tokenSurface);
    expect(g.listGap, `${q}: danh sách phải có gap dọc từ token`).toBe(g.tokenSpace3);
    expect(g.gaps, `${q}: khoảng hở thật giữa các thẻ phải đều`).toHaveLength(1);
    expect(g.gaps[0], `${q}: các thẻ phải TÁCH nhau, không dính thành bảng`).toBeGreaterThan(0);
    expect(g.openOutlines, `${q}: thẻ phải có viền khép kín bốn cạnh, không phải kẻ ngang chia dòng`).toBe(0);
    expect(g.borderWidths, `${q}: mọi thẻ cùng độ dày viền`).toHaveLength(1);
    expect(parseFloat(g.borderWidths[0]), `${q}: thẻ phải có viền nhẹ`).toBeGreaterThan(0);
    expect(g.headRows, `${q}: danh sách thẻ không có hàng tiêu đề kiểu bảng`).toBe(0);
  }
});

test('thẻ Operation giữ thứ bậc: tên chính bên trái, thời gian/session bên phải', async ({ page }) => {
  test.setTimeout(180000);
  await F.mockAll(page);
  await open(page);
  await page.goto('/app?page=dashboard&tab=overview');
  await expect(page.locator('#opTimeProgress .op-card').first()).toBeVisible({ timeout: 15000 });
  const g = await page.evaluate(() => {
    const card = document.querySelector('#opTimeProgress .op-card');
    const title = card.querySelector('.op-card-identity .row-title');
    const code = card.querySelector('.op-card-identity .row-code');
    const aside = card.querySelector('.op-card-aside');
    const px = v => parseFloat(v);
    return {
      titleText: title?.textContent?.trim(),
      titleSize: px(getComputedStyle(title).fontSize),
      titleWeight: getComputedStyle(title).fontWeight,
      codeSize: code ? px(getComputedStyle(code).fontSize) : null,
      codeColor: code ? getComputedStyle(code).color : null,
      titleColor: getComputedStyle(title).color,
      asideRight: Math.round(aside.getBoundingClientRect().right),
      identityLeft: Math.round(card.querySelector('.op-card-identity').getBoundingClientRect().left),
      cardRight: Math.round(card.getBoundingClientRect().right),
    };
  });
  // Tên Operation là chữ chính.
  expect(g.titleText).toBeTruthy();
  expect(g.codeSize === null || g.codeSize < g.titleSize,
    `mã phải nhỏ hơn tên (tên ${g.titleSize}px, mã ${g.codeSize}px)`).toBe(true);
  expect(g.codeColor === null || g.codeColor !== g.titleColor,
    'mã phải mờ hơn tên, không cùng một màu').toBe(true);
  // Thời gian/session nằm bên phải thẻ, không nằm dưới tên.
  expect(g.asideRight).toBeGreaterThan(g.identityLeft);
  expect(g.cardRight - g.asideRight, 'khối phải phải bám mép phải của thẻ').toBeLessThan(40);
});

test('thẻ danh sách của 4 nhóm màn hp3 dùng chung một mặt', async ({ page }) => {
  await F.mockAll(page);
  await open(page);
  const faces = {};
  const read = async (url, sel, key) => {
    await page.goto(url);
    await expect(page.locator(sel).first()).toBeVisible({ timeout: 15000 });
    faces[key] = await page.evaluate(sel => {
      const cs = getComputedStyle(document.querySelector(sel));
      return [cs.borderTopLeftRadius, cs.borderTopWidth, cs.borderTopColor, cs.backgroundColor].join(' | ');
    }, sel);
  };
  await read('/app?page=session-management', '.session-accordion-item', 'Quản lý Session');
  await read('/app?page=session-exceptions', '.ec-card', 'Trung tâm ngoại lệ');
  await read('/app?page=business-audit', '.ba-card', 'Nhật ký nghiệp vụ');
  await read('/app?page=dashboard&tab=overview', '.daily-kpi', 'Dashboard theo ngày (KPI)');
  await read('/app?page=dashboard&tab=overview', '.op-card', 'Dashboard theo ngày (thẻ Operation)');

  const distinct = [...new Set(Object.values(faces))];
  const report = Object.entries(faces).map(([k, v]) => `  ${k}\n      ${v}`).join('\n');
  expect(distinct.length, `${distinct.length} mặt khác nhau:\n${report}`).toBe(1);
});

for (const [w, h, name] of [[1920, 1080, '1920'], [1366, 768, '1366'], [390, 844, '390']]) {
  test(`nhóm màn hp3 không tràn ngang @${name}`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h });
    await F.mockAll(page);
    await open(page);
    for (const q of ['dashboard&tab=overview', 'dashboard&tab=people', 'dashboard&tab=output',
                     'session-management', 'session-exceptions', 'business-audit']) {
      await page.goto(`/app?page=${q}`);
      await page.waitForTimeout(1500);
      const g = await page.evaluate(() => {
        const n = document.querySelector('.dashboard-tabs');
        return {
          bodyOverflows: document.documentElement.scrollWidth > document.documentElement.clientWidth,
          // Dải tab hẹp hơn nội dung thì PHẢI cuộn được, không được cắt cụt.
          tabsOk: !n || n.scrollWidth <= n.clientWidth || getComputedStyle(n).overflowX === 'auto',
        };
      });
      expect(g.bodyOverflows, `${q} tràn ngang @${name}`).toBe(false);
      expect(g.tabsOk, `dải tab bị cắt cụt @${name} trên ${q}`).toBe(true);
    }
  });
}

// Bịt đúng cái lỗ đã để lọt --radius-card lên một vỏ bảng: đo DOM thật nên
// không phụ thuộc hậu tố class như guard Python. Mọi mặt CÓ SƠN (viền/nền/bóng)
// và đủ lớn để đọc là một khối nội dung đều phải lấy bo góc từ thang canonical.
test('mọi surface trên 4 nhóm màn lấy bo góc từ thang canonical', async ({ page }) => {
  test.setTimeout(180000);
  await F.mockAll(page);
  await open(page);

  const PAGES = [
    ['dashboard&tab=overview', 'Dashboard ngày — tab A'],
    ['dashboard&tab=people', 'Dashboard ngày — tab B'],
    ['dashboard&tab=output', 'Dashboard ngày — tab C'],
    ['session-management', 'Quản lý Session'],
    ['session-exceptions', 'Trung tâm ngoại lệ'],
    ['business-audit', 'Nhật ký nghiệp vụ'],
  ];
  const offenders = [];
  for (const [q, label] of PAGES) {
    await page.goto(`/app?page=${q}`);
    await page.waitForTimeout(1800);
    const bad = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const scale = new Set(['--radius-surface', '--radius-surface-row', '--radius-control']
        .map(t => root.getPropertyValue(t).trim()));
      // Hình dạng chủ ý, không phải bậc thang.
      const intentional = new Set(['0px', '999px', '9999px']);
      const out = [];
      for (const el of (document.querySelector('#content') || document.body).querySelectorAll('*')) {
        const cls = typeof el.className === 'string' ? el.className.trim() : '';
        if (!cls) continue;
        const cs = getComputedStyle(el);
        const painted = (cs.borderTopWidth !== '0px' && cs.borderTopStyle !== 'none')
          || !['rgba(0, 0, 0, 0)', 'transparent'].includes(cs.backgroundColor)
          || cs.boxShadow !== 'none';
        if (!painted) continue;
        const r = el.getBoundingClientRect();
        // Khối nội dung, không phải huy hiệu/chấm/nút nhỏ.
        if (r.width < 200 || r.height < 40) continue;
        const radius = cs.borderTopLeftRadius;
        if (intentional.has(radius)) continue;          // vuông chủ ý, viên thuốc
        if (radius.endsWith('%')) continue;             // hình tròn
        if (scale.has(radius)) continue;                // đúng thang
        out.push(`${el.tagName.toLowerCase()}.${cls.split(/\s+/).join('.')} -> ${radius} (${Math.round(r.width)}x${Math.round(r.height)})`);
      }
      return [...new Set(out)];
    });
    bad.forEach(b => offenders.push(`  [${label}] ${b}`));
  }
  const scaleText = await page.evaluate(() => {
    const r = getComputedStyle(document.documentElement);
    return ['--radius-surface', '--radius-surface-row', '--radius-control']
      .map(t => `${t}=${r.getPropertyValue(t).trim()}`).join('  ');
  });
  expect(offenders, `Surface không lấy bo góc từ thang canonical (${scaleText}):\n${offenders.join('\n')}`)
    .toEqual([]);
});
