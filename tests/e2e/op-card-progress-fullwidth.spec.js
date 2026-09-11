// Dashboard theo ngày › Tiến độ theo Operation: the progress block is the
// card's main content, not a column beside the facts.
//
// ROOT CAUSE this guards, measured on the running screen: .op-card-body is a
// `repeat(auto-fit,minmax(230px,1fr))` grid and .op-dual-progress was just
// another track in it. At a 1094px inner card that gave:
//
//     .op-dual-progress   542px   (~49%)
//     .op-card-fact       542px   ("Người làm")
//
// so both status bars stopped halfway across the card while the right half was
// the workers cell. Fixed by letting the progress span the row and lead it; the
// facts reflow underneath through the same auto-fit grid, so no breakpoint or
// bespoke measurement was added.
//
// NEGATIVE PROOF: remove `.op-card-body>.op-dual-progress{grid-column:1/-1}`
// from ui.css and every viewport fails, reporting the measured ~49%.
const { test, expect } = require('@playwright/test');

const VIEWPORTS = [[1920, 1080, '1920x1080'], [1366, 768, '1366x768'], [390, 844, '390x844']];
const MIN_RATIO = 0.7;   // "gần bằng inner width, cho phép padding"

async function openDashboard(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=dashboard');
  await expect(page.locator('.op-card').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(600);
}

const geometry = page => page.evaluate(() => {
  const card = document.querySelector('.op-card');
  const cs = getComputedStyle(card);
  const inner = card.getBoundingClientRect().width
    - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
  const pick = sel => {
    const el = card.querySelector(sel);
    return el ? Math.round(el.getBoundingClientRect().width) : null;
  };
  const head = card.querySelector('.op-card-head');
  const progress = card.querySelector('.op-dual-progress');
  const facts = card.querySelector('.op-card-fact');
  const box = el => el && el.getBoundingClientRect();
  return {
    inner: Math.round(inner),
    head: pick('.op-card-head'),
    progress: pick('.op-dual-progress'),
    timeMeter: pick('.op-time-meter'),
    productMeter: pick('.op-product-meter'),
    // the workers block must sit BELOW the progress, not beside it
    progressBottom: progress ? Math.round(box(progress).bottom) : null,
    factsTop: facts ? Math.round(box(facts).top) : null,
    headBottom: head ? Math.round(box(head).bottom) : null,
    progressTop: progress ? Math.round(box(progress).top) : null,
  };
});

for (const [width, height, label] of VIEWPORTS) {
  test(`progress spans the card @ ${label}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await openDashboard(page);
    const g = await geometry(page);

    expect(g.progress, 'no .op-dual-progress rendered').toBeTruthy();

    const ratio = g.progress / g.inner;
    expect(ratio, `progress is ${g.progress}px of ${g.inner}px inner width (${Math.round(ratio * 100)}%)`)
      .toBeGreaterThanOrEqual(MIN_RATIO);

    // Both bars, not just their container, must actually stretch.
    for (const [name, w] of [['time meter', g.timeMeter], ['product meter', g.productMeter]]) {
      if (w === null) continue;
      expect(w / g.inner, `${name} is only ${Math.round((w / g.inner) * 100)}% of the card`)
        .toBeGreaterThanOrEqual(0.5);
    }

    // Reading order: header, then progress, then the workers/facts row.
    expect(g.progressTop, 'progress must sit below the header').toBeGreaterThanOrEqual(g.headBottom - 1);
    if (g.factsTop !== null) {
      expect(g.factsTop, 'the workers row must sit below the progress, not beside it')
        .toBeGreaterThanOrEqual(g.progressBottom - 1);
    }

    // Nothing may push the page sideways at any of the three sizes.
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1),
      `horizontal overflow at ${label}`).toBe(true);
  });
}
