// Hợp đồng "mặt sidebar": mọi hàng điều hướng trong rail trái là nền TỐI hoặc
// trong suốt -- không bao giờ là một mặt sáng kiểu thẻ nội dung.
//
// Vì sao cần bài này: 2026-09-11, rule .sidebar-sub-heading được chèn vào GIỮA
// danh sách selector của nút sidebar, ngay sau `.sidebar-group-trigger,`:
//
//   .sidebar-item,.sidebar-group-trigger,/*…*/.sidebar-sub-heading{…heading…}
//   .sidebar-sub-item{border:0;background:transparent;…}
//
// Dấu phẩy đó cắt đôi danh sách cũ. .sidebar-item và .sidebar-group-trigger
// nhận declaration của heading và MẤT `border:0;background:transparent`, nên
// <button> rơi về mặt mặc định của trình duyệt: nền #efefef, viền 2px outset.
// Đo được trên TEST trước khi vá:
//
//   .sidebar-group-trigger  bg rgb(239,239,239)  border 2px outset  color #8ba0b6
//
// Cộng với border-radius vẫn còn, bốn nhóm KẾ HOẠCH / ĐIỀU HÀNH / DANH MỤC /
// QUẢN TRỊ hiện thành khối TRẮNG bo góc chữ nhạt giữa một sidebar navy.
// .sidebar-item thoát nạn chỉ vì nó mang thêm class .nav-item cũ (cũng khai
// border:0 + background:transparent) -- một lưới an toàn tình cờ mà
// .sidebar-group-trigger không có. Tức đây là lỗi CƠ CHẾ của cascade, không
// phải một màu viết sai: bài này đo computed style nên bắt được mọi cách làm
// hỏng lại, dù nguyên nhân sau này là rule quét, token hay UA style.
//
// Bài này KHÔNG cần dữ liệu nghiệp vụ: sidebar dựng từ menu tĩnh trong app.js.
const { test, expect } = require('@playwright/test');

// Hàng điều hướng và vỏ của chúng. Tất cả phải ở trên nền tối.
const NAV_PARTS = ['.sidebar-item', '.sidebar-group-trigger', '.sidebar-sub-item',
                   '.sidebar-sub-heading', '.sidebar-group', '.sidebar-group-panel'];

const parseRgb = s => {
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const [r, g, b, a = '1'] = m[1].split(',').map(x => parseFloat(x));
  return { r, g, b, a: Number(a) };
};
const luminance = ({ r, g, b }) => {
  const f = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const contrast = (fg, bg) => {
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
};

// Nền THỰC SỰ nhìn thấy: đi ngược lên cây cho tới lớp đục đầu tiên, đúng như
// mắt người đọc một phần tử có nền trong suốt.
const PROBE = `(sel) => [...document.querySelectorAll(sel)].map(el => {
  const cs = getComputedStyle(el);
  let node = el, effective = 'rgba(0, 0, 0, 0)';
  while (node) {
    const bg = getComputedStyle(node).backgroundColor;
    const m = bg.match(/rgba?\\(([^)]+)\\)/);
    if (m && (m[1].split(',')[3] === undefined || parseFloat(m[1].split(',')[3]) > 0.95)) { effective = bg; break; }
    node = node.parentElement;
  }
  const r = el.getBoundingClientRect();
  return { sel, text: (el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 24),
           bg: cs.backgroundColor, effective, color: cs.color,
           borderWidth: cs.borderTopWidth, borderStyle: cs.borderTopStyle,
           visible: r.width > 0 && r.height > 0 };
})`;

async function probe(page, sel) {
  return page.evaluate(new Function('sel', `return (${PROBE})(sel)`), sel);
}

async function open(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
  await page.locator('.sidebar-group-trigger').first().waitFor({ state: 'attached', timeout: 20000 });
}

// Nền tối hoặc trong suốt -- KHÔNG bao giờ là mặt sáng.
function expectDarkSurface(rows) {
  expect(rows.length, 'sidebar phải dựng được ít nhất một hàng').toBeGreaterThan(0);
  for (const row of rows) {
    const bg = parseRgb(row.bg);
    if (bg && bg.a > 0.02) {
      expect(luminance(bg),
        `${row.sel} "${row.text}" có nền SÁNG ${row.bg} -- hàng nav phải tối hoặc trong suốt`
      ).toBeLessThan(0.15);
    }
    const eff = parseRgb(row.effective);
    expect(eff, `${row.sel} "${row.text}" không tìm được nền đục nào phía sau`).not.toBeNull();
    expect(luminance(eff),
      `${row.sel} "${row.text}" nằm trên nền sáng ${row.effective}`
    ).toBeLessThan(0.15);
  }
}

// Mặt nút mặc định của trình duyệt luôn kèm viền outset -- dấu vân tay của
// đúng lỗi cascade đã gây ra hồi quy này.
function expectNoUaButtonBorder(rows) {
  for (const row of rows) {
    expect(`${row.borderWidth} ${row.borderStyle}`,
      `${row.sel} "${row.text}" đang mang viền nút mặc định của trình duyệt`
    ).not.toContain('outset');
    expect(parseFloat(row.borderWidth),
      `${row.sel} "${row.text}" phải không viền (đang ${row.borderWidth})`
    ).toBe(0);
  }
}

async function auditAllStates(page) {
  for (const sel of NAV_PARTS) {
    const rows = (await probe(page, sel)).filter(r => r.visible);
    if (!rows.length) continue;
    expectDarkSurface(rows);
    if (sel !== '.sidebar-group' && sel !== '.sidebar-group-panel') expectNoUaButtonBorder(rows);
  }
}

test.describe('mặt sidebar điều hướng', () => {
  test('desktop: nhóm nav là nền tối, không phải khối trắng', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);

    const triggers = await probe(page, '.sidebar-group-trigger');
    expect(triggers.length, 'phải có nhóm nav để kiểm').toBeGreaterThanOrEqual(3);
    expectDarkSurface(triggers);
    expectNoUaButtonBorder(triggers);
    await auditAllStates(page);

    testInfo.attach('sidebar-desktop.png',
      { body: await page.locator('.app-sidebar').screenshot(), contentType: 'image/png' });
  });

  test('chữ nav đủ tương phản trên nền navy', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    // Mở một nhóm để cả sub-item lẫn sub-heading cùng hiện.
    await page.locator('.sidebar-group-trigger').last().click();
    await page.waitForTimeout(250);

    for (const sel of ['.sidebar-item', '.sidebar-group-trigger', '.sidebar-sub-item', '.sidebar-sub-heading']) {
      for (const row of (await probe(page, sel)).filter(r => r.visible)) {
        const ratio = contrast(parseRgb(row.color), parseRgb(row.effective));
        expect(ratio,
          `${sel} "${row.text}": ${row.color} trên ${row.effective} chỉ đạt ${ratio.toFixed(2)}:1`
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  test('hover / mở nhóm / thu gọn đều giữ nền tối', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);

    // hover
    await page.locator('.sidebar-group-trigger').first().hover();
    await page.waitForTimeout(200);
    await auditAllStates(page);

    // mở nhóm (panel + chevron xoay)
    const trigger = page.locator('.sidebar-group-trigger').first();
    await trigger.click();
    await expect(page.locator('.sidebar-group').first()).toHaveClass(/open/);
    await expect(page.locator('.sidebar-group').first().locator('.sidebar-group-panel')).toBeVisible();
    const chevron = await page.locator('.sidebar-group').first().locator('.sidebar-group-trigger i').evaluate(
      el => ({ transform: getComputedStyle(el).transform, text: el.textContent.trim() }));
    expect(chevron.text, 'chevron của nhóm phải còn').not.toBe('');
    expect(chevron.transform, 'chevron phải xoay khi nhóm mở').not.toBe('none');
    await auditAllStates(page);

    // focus bàn phím
    await trigger.focus();
    await auditAllStates(page);

    // thu gọn sidebar
    await page.locator('#sidebarToggle').click();
    await expect(page.locator('#appLayout')).toHaveClass(/sidebar-collapsed/);
    await page.waitForTimeout(250);
    await auditAllStates(page);
    // icon vẫn vẽ được khi thu gọn -- nếu không, rail thu gọn thành cột trống
    expect(await page.locator('.sidebar-group-trigger .sidebar-item-icon svg').first().isVisible()).toBe(true);
  });

  test('mục đang mở giữ nền nhấn tối và thanh accent', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    const active = page.locator('.sidebar-item.active').first();
    await expect(active).toBeVisible();
    const got = await active.evaluate(el => {
      const cs = getComputedStyle(el);
      return { bg: cs.backgroundColor, color: cs.color, shadow: cs.boxShadow };
    });
    expect(luminance(parseRgb(got.bg)), `mục active phải có nền nhấn TỐI, đang ${got.bg}`).toBeLessThan(0.15);
    // Nền active phải tách khỏi hàng thường, nếu không "đang ở màn nào" biến mất.
    expect(parseRgb(got.bg).a, 'mục active phải có nền, không trong suốt').toBeGreaterThan(0.02);
    expect(got.shadow, 'mục active phải giữ thanh accent inset').toContain('inset');
    expect(contrast(parseRgb(got.color), parseRgb(got.bg))).toBeGreaterThanOrEqual(4.5);
  });

  test('mobile 390px: drawer giữ mặt tối và không tràn ngang', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await open(page);
    await page.locator('#mobileMenuToggle').click();
    await expect(page.locator('.app-sidebar')).toBeVisible();
    await page.waitForTimeout(350);

    await page.locator('.sidebar-group-trigger').last().click();
    await page.waitForTimeout(250);
    await auditAllStates(page);

    const overflow = await page.evaluate(() => {
      const nav = document.querySelector('.sidebar-nav'), aside = document.querySelector('.app-sidebar');
      return { navScroll: nav.scrollWidth, navClient: nav.clientWidth,
               asideScroll: aside.scrollWidth, asideClient: aside.clientWidth,
               bodyScroll: document.documentElement.scrollWidth,
               bodyClient: document.documentElement.clientWidth };
    });
    expect(overflow.navScroll, 'sidebar-nav tràn ngang').toBeLessThanOrEqual(overflow.navClient + 1);
    expect(overflow.asideScroll, 'app-sidebar tràn ngang').toBeLessThanOrEqual(overflow.asideClient + 1);
    expect(overflow.bodyScroll, 'trang tràn ngang khi mở drawer').toBeLessThanOrEqual(overflow.bodyClient + 1);

    testInfo.attach('sidebar-mobile.png',
      { body: await page.locator('.app-sidebar').screenshot(), contentType: 'image/png' });
  });

  // --- Thang trạng thái ------------------------------------------------
  //
  // Hồi quy "khối trắng" là một nửa vấn đề; nửa còn lại là bốn nhóm KẾ HOẠCH /
  // ĐIỀU HÀNH / DANH MỤC / QUẢN TRỊ nói quá ít về trạng thái của chúng: nhóm
  // đang MỞ trông y hệt nhóm đang đóng, và mọi màu nav từng nằm ở hai chỗ
  // trong ui.css với hai giá trị khác nhau. Bài dưới đây đo bốn trạng thái
  // trên CÙNG một nút và bắt chúng phải khác nhau, nổi dần theo đúng thứ tự
  // idle < open < hover < active -- "đang ở đâu" luôn là hàng nổi nhất.
  const cssVar = (page, name) => page.evaluate(
    n => getComputedStyle(document.documentElement).getPropertyValue(n).trim(), name);
  // Token viết bằng hex, computed style trả về rgb() -- quy về một dạng để so.
  const asRgb = value => value.startsWith('#')
    ? { r: parseInt(value.slice(1, 3), 16), g: parseInt(value.slice(3, 5), 16), b: parseInt(value.slice(5, 7), 16), a: 1 }
    : parseRgb(value);
  const bgOf = locator => locator.evaluate(el => {
    const cs = getComputedStyle(el);
    return { bg: cs.backgroundColor, color: cs.color, shadow: cs.boxShadow, outline: cs.outlineColor };
  });
  // Chuột đứng xa rail trái: một cú .click() của Playwright để lại con trỏ
  // NGAY TRÊN nút vừa bấm, nên đo "đang mở, không hover" sau đó sẽ đo nhầm
  // hover. Trạng thái mở vì vậy được bật bằng el.click() trong trang.
  const parkMouse = page => page.mouse.move(1200, 600);

  test('bốn nhóm: idle / mở / hover / đang xem là bốn mặt khác nhau, đúng hướng', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    await parkMouse(page);

    const groups = page.locator('.sidebar-group');
    expect(await groups.count(), 'phải đủ bốn nhóm nav').toBeGreaterThanOrEqual(4);

    // Một nhóm KHÔNG chứa trang hiện tại -- trang mở là overview, mục cấp một.
    const group = groups.first();
    const trigger = group.locator('.sidebar-group-trigger');
    await expect(group).not.toHaveClass(/has-active/);

    const idle = await bgOf(trigger);
    expect(parseRgb(idle.bg).a, 'nhóm chưa mở phải trong suốt trên nền rail').toBeLessThan(0.02);

    await trigger.evaluate(el => el.click());          // mở nhóm, chuột vẫn ở xa
    await expect(group).toHaveClass(/open/);
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    const opened = await bgOf(trigger);

    await trigger.hover();
    await page.waitForTimeout(120);
    const hovered = await bgOf(trigger);
    await parkMouse(page);

    // Trang hiện tại nằm TRONG một nhóm: bấm một mục con rồi đo chính nút nhóm.
    const target = groups.nth(2).locator('.sidebar-group-trigger');
    await target.evaluate(el => el.click());
    await groups.nth(2).locator('.sidebar-sub-item').first().evaluate(el => el.click());
    await expect(groups.nth(2)).toHaveClass(/has-active/);
    await page.waitForTimeout(150);
    const active = await bgOf(groups.nth(2).locator('.sidebar-group-trigger'));
    await parkMouse(page);

    const L = s => luminance(parseRgb(s.bg));
    const rail = luminance(parseRgb(await page.evaluate(
      () => getComputedStyle(document.querySelector('.app-sidebar')).backgroundColor)));

    // Hợp đồng là HƯỚNG, không phải một thang đậm dần: mọi thứ không phải
    // trang hiện tại thì LÕM xuống dưới mặt rail, trang hiện tại NỔI lên.
    for (const [name, state] of [['mở', opened], ['hover', hovered], ['đang xem', active]]) {
      expect(parseRgb(state.bg).a, `trạng thái ${name} phải có nền thật, không trong suốt`).toBeGreaterThan(0.02);
      expect(L(state), `trạng thái ${name} đã thành mặt SÁNG (${state.bg})`).toBeLessThan(0.15);
    }
    expect(L(opened),
      `nhóm đang mở (${opened.bg}, L ${L(opened).toFixed(4)}) phải lõm xuống dưới mặt rail (L ${rail.toFixed(4)})`
    ).toBeLessThan(rail);
    expect(L(hovered),
      `hover (${hovered.bg}) phải lõm sâu hơn nhóm đang mở (${opened.bg})`
    ).toBeLessThan(L(opened));
    expect(L(active),
      `trang hiện tại (${active.bg}) phải NỔI lên khỏi mặt rail (L ${rail.toFixed(4)}) -- ` +
      'nó là hàng duy nhất đi ngược hướng với phần còn lại'
    ).toBeGreaterThan(rail);

    // Bốn mặt phải là bốn màu khác nhau, không chỉ khác độ sáng.
    const faces = new Set([`rail:${rail.toFixed(5)}`, opened.bg, hovered.bg, active.bg]);
    expect(faces.size, `idle/mở/hover/đang xem đang trùng mặt nhau: ${[...faces].join(' | ')}`).toBe(4);
    expect(active.shadow, 'nhóm chứa trang hiện tại phải có thanh accent inset').toContain('inset');
    // ... và chỉ MỘT mình nó mang thanh accent.
    for (const [name, state] of [['mở', opened], ['hover', hovered]]) {
      expect(state.shadow, `trạng thái ${name} không được mang thanh accent của trang hiện tại`).not.toContain('inset');
    }

    // Thanh accent lấy đúng token, không phải một hex viết lại lần nữa.
    const accent = asRgb(await cssVar(page, '--nav-accent'));
    expect(accent, '--nav-accent phải tồn tại trong khối token').not.toBeNull();
    expect(active.shadow.replace(/\s/g, ''),
      `thanh accent phải là var(--nav-accent), đang là ${active.shadow}`
    ).toContain(`rgb(${accent.r},${accent.g},${accent.b})`.replace(/\s/g, ''));

    // Và chữ trên mọi trạng thái vẫn đọc được.
    for (const [name, state] of [['mở', opened], ['hover', hovered], ['đang xem', active]]) {
      const bg = parseRgb(state.bg);
      expect(contrast(parseRgb(state.color), bg),
        `chữ nhóm ở trạng thái ${name} chỉ đạt ${contrast(parseRgb(state.color), bg).toFixed(2)}:1 trên ${state.bg}`
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  test('màu nav đến từ token --nav-*, không từ hex rải rác', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    // Rail và hàng nav phải khớp token: nếu ai đó viết cứng một hex mới ở đâu
    // đó trong ui.css thì hai giá trị này lệch nhau ngay.
    const railToken = await cssVar(page, '--nav-surface');
    const rail = await page.evaluate(() => getComputedStyle(document.querySelector('.app-sidebar')).backgroundColor);
    const t = asRgb(railToken);
    const r = parseRgb(rail);
    expect([r.r, r.g, r.b], `nền rail ${rail} không khớp --nav-surface ${railToken}`).toEqual([t.r, t.g, t.b]);

    for (const name of ['--nav-surface-open', '--nav-surface-hover', '--nav-surface-active',
                        '--nav-accent', '--nav-text', '--nav-heading']) {
      expect((await cssVar(page, name)).trim(), `thiếu token ${name}`).not.toBe('');
    }
  });

  test('bàn phím: nhóm nav có dấu focus riêng và nói được trạng thái mở', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    const trigger = page.locator('.sidebar-group-trigger').first();

    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    // Tab trước rồi mới focus: :focus-visible chỉ ăn khi phương thức nhập gần
    // nhất là bàn phím, nên một .focus() trần có thể không vẽ vòng nào.
    await page.keyboard.press('Tab');
    await trigger.focus();
    const focusRing = await trigger.evaluate(el => {
      const cs = getComputedStyle(el);
      return { width: cs.outlineWidth, style: cs.outlineStyle, color: cs.outlineColor };
    });
    await page.keyboard.press('Enter');
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');

    expect(parseFloat(focusRing.width), 'nút nhóm phải có vòng focus thấy được').toBeGreaterThanOrEqual(2);
    expect(focusRing.style, 'vòng focus không được là none').not.toBe('none');
    await auditAllStates(page);
  });

  test('thu gọn: mục đang mở vẫn mang thanh accent, không phải vạch trắng cũ', async ({ page }) => {
    // Rail thu gọn từng có ngoại lệ riêng: một rule `.sidebar-collapsed
    // .sidebar-item.active{box-shadow:inset 1px 0 #fff!important}` của lớp cũ
    // thắng thanh accent nhờ specificity, nên cùng một "mục đang mở" có hai
    // hình dạng khác nhau tuỳ sidebar đang mở hay thu gọn.
    await page.setViewportSize({ width: 1440, height: 900 });
    await open(page);
    const accent = asRgb(await cssVar(page, '--nav-accent'));
    await page.locator('#sidebarToggle').click();
    await expect(page.locator('#appLayout')).toHaveClass(/sidebar-collapsed/);
    await page.waitForTimeout(250);

    const active = page.locator('.sidebar-item.active, .sidebar-group.has-active>.sidebar-group-trigger').first();
    await expect(active).toBeVisible();
    const shadow = (await active.evaluate(el => getComputedStyle(el).boxShadow)).replace(/\s/g, '');
    expect(shadow, `thu gọn: thanh accent phải là var(--nav-accent), đang là ${shadow}`)
      .toContain(`rgb(${accent.r},${accent.g},${accent.b})`.replace(/\s/g, ''));
    expect(shadow, 'thu gọn: không được quay lại vạch trắng 1px của lớp cũ').not.toContain('rgb(255,255,255)');
  });
});
