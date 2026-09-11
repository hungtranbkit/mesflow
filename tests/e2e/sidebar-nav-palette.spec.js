// The sidebar is dark. No nav control may render on a light surface.
//
// ROOT CAUSE this guards, measured on the running app: .sidebar-item and
// .sidebar-sub-item each pick up a reset (the former through the legacy
// .nav-item rule, the latter from its own declaration), but
// .sidebar-group-trigger got NEITHER — and it is a <button>, so it fell back
// to the user-agent default:
//
//     background rgb(239,239,239)   (ButtonFace)
//     border     2px rgb(0,0,0)
//
// which is why exactly the four group headers (KẾ HOẠCH / ĐIỀU HÀNH /
// DANH MỤC / QUẢN TRỊ) rendered as light blocks on a navy sidebar while every
// other row looked right. Not a design-system rule leaking a surface token —
// no app-wide card/list rule matches these selectors at all.
//
// NEGATIVE PROOF: delete the `.app-sidebar :where(.sidebar-item,
// .sidebar-group-trigger,.sidebar-sub-item)` reset from ui.css and
// "no nav control sits on a light surface" fails, naming the trigger and its
// measured rgb(239,239,239).
const { test, expect } = require('@playwright/test');

/** Perceived lightness 0..255 of a computed rgb()/rgba() colour. */
function lightness(css) {
  const m = String(css).match(/rgba?\(([^)]+)\)/);
  if (!m) return null;
  const [r, g, b, a = '1'] = m[1].split(',').map(s => parseFloat(s));
  if (parseFloat(a) === 0) return null;          // transparent: inherits the dark shell
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

async function openApp(page, { mobile = false } = {}) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=dashboard');
  // Count on the LOCATOR, not on .first() -- .first() can only ever be 0 or 1.
  await expect(page.locator('#nav .sidebar-group-trigger')).toHaveCount(4, { timeout: 15000 });
  // On a phone the sidebar is off-canvas until the menu is opened, so the
  // toggle has to come BEFORE waiting for anything in the nav to be visible.
  if (mobile) {
    await page.locator('#mobileMenuToggle').click();
    await page.waitForTimeout(500);
  }
  await expect(page.locator('#nav .sidebar-group-trigger').first()).toBeVisible({ timeout: 15000 });
}

const navControls = page => page.evaluate(() => {
  const out = [];
  document.querySelectorAll('#nav button, #nav a').forEach(el => {
    const cs = getComputedStyle(el);
    out.push({
      cls: (el.className || '').toString(),
      label: (el.textContent || '').trim().split('\n')[0].slice(0, 24),
      bg: cs.backgroundColor,
      color: cs.color,
      borderWidth: parseFloat(cs.borderTopWidth),
    });
  });
  return out;
});

for (const [width, height, label] of [[1440, 900, 'desktop'], [390, 844, 'mobile']]) {
  test(`no nav control sits on a light surface @ ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openApp(page, { mobile: label === 'mobile' });
    const controls = await navControls(page);
    expect(controls.length).toBeGreaterThan(5);

    const offenders = [];
    for (const c of controls) {
      const l = lightness(c.bg);
      // The sidebar shell is navy (~#18364e, lightness ≈ 50). Anything close to
      // a content surface is the ButtonFace regression coming back.
      if (l !== null && l > 120) offenders.push(`${c.label} [${c.cls}] bg=${c.bg}`);
      // A UA button border is 2px; nav rows carry none.
      if (c.borderWidth >= 2) offenders.push(`${c.label} [${c.cls}] border=${c.borderWidth}px`);
    }
    expect(offenders, 'nav controls rendering on a light/UA surface').toEqual([]);
  });
}

test('group headers are muted but readable, and the active route is brighter', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openApp(page);
  const controls = await navControls(page);
  const triggers = controls.filter(c => c.cls.includes('sidebar-group-trigger'));
  const active = controls.find(c => c.cls.includes('active'));

  expect(triggers.length, 'expected the four collapsed groups').toBeGreaterThanOrEqual(4);
  expect(active, 'no active nav item found').toBeTruthy();

  // Hierarchy: the active route reads brighter than an inactive group header,
  // and the header is still light enough to read on navy.
  const activeL = lightness(active.color);
  for (const t of triggers) {
    const l = lightness(t.color);
    expect(l, `group header "${t.label}" is too dim on a navy sidebar`).toBeGreaterThan(120);
    expect(l, `group header "${t.label}" is as bright as the active route`).toBeLessThan(activeL);
  }
  // ...and they all share one colour, rather than four different ones.
  expect(new Set(triggers.map(t => t.color)).size,
    'group headers do not share a single muted colour').toBe(1);
});

test('hover and active states stay inside the sidebar palette', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await openApp(page);
  const trigger = page.locator('#nav .sidebar-group-trigger').first();
  const rest = await trigger.evaluate(el => getComputedStyle(el).backgroundColor);
  await trigger.hover();
  await page.waitForTimeout(250);
  const hovered = await trigger.evaluate(el => getComputedStyle(el).backgroundColor);
  expect(hovered, 'hover must give feedback').not.toBe(rest);
  const l = lightness(hovered);
  expect(l, `hover background ${hovered} left the dark palette`).toBeLessThan(120);
});
