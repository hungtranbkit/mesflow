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
});
