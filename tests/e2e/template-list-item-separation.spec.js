// Template list: every item is its OWN card, with air between them.
//
// The items were already rounded (the canonical [class$="-card"] rule gives
// them --radius-surface, a border and a shadow), but measured on the running
// screen the vertical gap between consecutive items was 0 and the list panel
// had no padding: rounded cards sat flush, their borders touching, and the
// whole thing read as one block rather than a list of cards.
//
// Measured, not eyeballed — this asserts computed style at the three sizes the
// product cares about.
//
// NEGATIVE PROOF: set .template-old-list back to `gap:0` in ui.css and
// "items are separated" fails at every viewport with the measured 0px.
const { test, expect } = require('@playwright/test');

const ITEM = '.template-old-card';
const VIEWPORTS = [[1920, 1080, '1920x1080'], [1366, 768, '1366x768'], [390, 844, '390x844']];

async function openTemplates(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=templates');
  // The page renders the list, then auto-opens the first template, which
  // re-renders the list — measuring in that window sees zero items. Wait for
  // the list to settle at its final count instead of for the first paint.
  await expect.poll(async () => page.locator(ITEM).count(), { timeout: 20000, intervals: [250] })
    .toBeGreaterThan(1);
  await page.waitForTimeout(400);
  await expect(page.locator(ITEM).first()).toBeVisible();
}

/** Geometry + the token scale, read from the live page. */
const measure = page => page.evaluate(sel => {
  const items = [...document.querySelectorAll(sel)].filter(e => e.getBoundingClientRect().height > 10);
  const root = getComputedStyle(document.documentElement);
  const first = items[0] && getComputedStyle(items[0]);
  const gaps = [];
  for (let i = 1; i < items.length; i++) {
    gaps.push(items[i].getBoundingClientRect().top - items[i - 1].getBoundingClientRect().bottom);
  }
  return {
    count: items.length,
    gaps,
    radius: first && first.borderTopLeftRadius,
    borderTop: first && parseFloat(first.borderTopWidth),
    shadow: first && first.boxShadow,
    listRowGap: items[0] && getComputedStyle(items[0].parentElement).rowGap,
    tokens: {
      surface: root.getPropertyValue('--radius-surface').trim(),
      surfaceRow: root.getPropertyValue('--radius-surface-row').trim(),
      spaces: [1, 2, 3, 4, 5, 6].map(n => root.getPropertyValue(`--ui-space-${n}`).trim()).filter(Boolean),
    },
  };
}, ITEM);

for (const [width, height, label] of VIEWPORTS) {
  test(`Template items are separated cards @ ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openTemplates(page);
    const m = await measure(page);

    expect(m.count, 'need at least two items to measure separation').toBeGreaterThan(1);

    // Each item reads as a card in its own right.
    expect([m.tokens.surface, m.tokens.surfaceRow], `radius ${m.radius} is off the canonical scale`)
      .toContain(m.radius);
    expect(m.borderTop, 'a card must carry its own border, not a shared divider').toBeGreaterThan(0);
    expect(m.shadow, 'a card carries a light shadow').not.toBe('none');

    // ...and the cards do not touch. This is the defect being fixed.
    for (const gap of m.gaps) {
      expect(gap, `items are flush (gap ${gap}px) -- borders touch and the list reads as one block`)
        .toBeGreaterThan(0);
    }

    // The gap comes from the spacing primitive, not an invented number.
    expect(m.tokens.spaces, `list row-gap ${m.listRowGap} is not one of --ui-space-*`)
      .toContain(m.listRowGap);
  });
}

test('the gap survives the narrowest supported width without clipping', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openTemplates(page);
  // The panel needs inner padding too, or a rounded card sits flush against
  // the panel edge and loses the same air vertically gained between items.
  const inset = await page.evaluate(sel => {
    const item = document.querySelector(sel);
    const panel = item.closest('.template-old-list-panel') || item.parentElement.parentElement;
    const a = item.getBoundingClientRect(), p = panel.getBoundingClientRect();
    return { left: Math.round(a.left - p.left), right: Math.round(p.right - a.right) };
  }, ITEM);
  expect(inset.left, 'card touches the panel edge').toBeGreaterThan(0);
  expect(inset.right, 'card touches the panel edge').toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
});
