// ADMIN / MASTER DATA: list and card surfaces must round on one scale.
//
// This measures COMPUTED style in a real browser, not the stylesheet. Card
// shape is enforced by a suffix-scanning `[class$="-card"]` rule with
// !important, so reading a component's own declaration proves nothing about
// the pixels a user sees — only getComputedStyle does.
//
// NEGATIVE PROOF: revert `.op-list` in ui.css to `--radius-control` and
// "Part/Operation primitive" fails (5px container under a 7px header).
// Remove the `[class$="-card"]` rule and "one rounding scale" fails.
const { test, expect } = require('@playwright/test');

// The allowed values are READ FROM :root at run time rather than written here
// as pixels. The integration lane renamed and re-valued the scale
// (--radius-surface / --radius-surface-row became canonical, --radius-control
// went 5px -> 8px); a hardcoded list would have gone quietly stale and this
// test would have kept passing while measuring the wrong thing.
const scaleFrom = page => page.evaluate(() => {
  const root = getComputedStyle(document.documentElement);
  const read = name => root.getPropertyValue(name).trim();
  const surface = ['--radius-surface', '--radius-surface-row', '--radius-control'].map(read).filter(Boolean);
  const legacy = ['--radius-card', '--radius-panel', '--radius-row', '--radius-overlay'].map(read).filter(Boolean);
  return {
    // Flat and pill are deliberate shapes, not steps on the scale.
    allowed: [...new Set([...surface, ...legacy, '0px', '999px', '50%'])],
    container: [...new Set(surface)],
  };
});

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
}

// Every element that visually reads as a list item / card: it carries a
// border, it is big enough to be a surface rather than a chip, and it rounds.
const surfaces = page => page.evaluate(() => {
  const out = [];
  document.querySelectorAll('#content *').forEach(el => {
    const cs = getComputedStyle(el);
    if (parseFloat(cs.borderTopWidth) <= 0) return;
    const rect = el.getBoundingClientRect();
    if (rect.width < 120 || rect.height < 28) return;
    const cls = (el.className || '').toString().trim();
    if (!cls) return;
    out.push({ cls: cls.split(/\s+/).slice(0, 2).join('.'), radius: cs.borderTopLeftRadius });
  });
  return out;
});

const ADMIN_SCREENS = [
  ['PO list',       '/app?page=production-orders'],
  ['Employee list', '/app?page=employees'],
  ['Kiosk/Station', '/app?page=kiosk-management'],
  ['Template list', '/app?page=templates'],
  ['QR print',      '/app?page=qr-print'],
  ['Equipment',     '/app?page=equipment'],
];

for (const [w, h, label] of [[1920, 1080, '1920x1080'], [1366, 768, '1366x768'], [390, 844, '390x844']]) {
  test(`admin list/card surfaces keep one rounding scale @ ${label}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await login(page);
    await page.goto(ADMIN_SCREENS[0][1]);
    const allowed = new Set((await scaleFrom(page)).allowed);
    const offenders = [];
    for (const [name, url] of ADMIN_SCREENS) {
      await page.goto(url);
      await page.waitForTimeout(1200);
      for (const s of await surfaces(page)) {
        if (!allowed.has(s.radius)) offenders.push(`${name} .${s.cls} = ${s.radius}`);
      }
      // Responsive: an admin surface may never push the page sideways.
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
        `${name} overflows horizontally at ${label}`).toBe(true);
    }
    expect(offenders, 'off-scale radius on an admin list/card surface').toEqual([]);
  });
}

test('Part/Operation primitive: nested list is one step inside its card', async ({ page }) => {
  test.setTimeout(180000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await page.goto('/app?page=production-orders');
  await page.waitForTimeout(1500);
  await page.locator('[data-po-row]').first().click();
  await expect(page.locator('.part-block').first()).toBeVisible({ timeout: 15000 });

  const m = await page.evaluate(() => {
    const list = document.querySelector('.op-list');
    const get = el => el && getComputedStyle(el).borderTopLeftRadius;
    const root = getComputedStyle(document.documentElement);
    return {
      part: get(document.querySelector('.part-block')),
      list: get(list),
      head: get(list && list.querySelector('.op-list-head')),
      surface: root.getPropertyValue('--radius-surface').trim(),
      surfaceRow: root.getPropertyValue('--radius-surface-row').trim(),
    };
  });
  const scale = await scaleFrom(page);
  const container = new Set(scale.container);

  // The canonical vocabulary gives a nested block its OWN step: the outer card
  // is --radius-surface, a list inside it is --radius-surface-row. So list and
  // card must NOT be equal -- an earlier version of this test asserted they
  // were, which was the pre-canonical reading.
  expect(container.has(m.list), `.op-list must use a canonical surface radius, got ${m.list}`).toBe(true);
  expect(container.has(m.part), `.part-block must use a canonical surface radius, got ${m.part}`).toBe(true);
  expect(m.surfaceRow, '.op-list must sit on the nested step').toBe(m.list);
  expect(m.surface, '.part-block must sit on the outer step').toBe(m.part);
  expect(parseFloat(m.list)).toBeLessThan(parseFloat(m.part));

  // The header is the list's own first child and the list clips it, so the two
  // must agree exactly. A header rounder than the box cutting it is the defect
  // this file was written for.
  expect(m.list, '.op-list and its own .op-list-head must agree').toBe(m.head);
});
