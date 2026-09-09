// Khối "Trình chiếu Kiosk" trên trang quản trị Năng suất nhân viên
// (?page=employee-productivity) -- KHÁC với màn Kiosk công khai
// /kiosk/employee-productivity mà employee-productivity-wallboard.spec.js phủ.
//
// Bug thật, đo trên TEST 2026-09-09: tràn ngang 43px ở iPhone 12 và 113px ở
// iPhone SE (320px). Đáng chú ý vì nó KHÔNG phải kiểu "nút rộng hơn khung
// cha" -- khung cha .wallboard-actions rộng đúng 332px:
//
//   .wallboard-actions là flex-direction:column NHƯNG có flex-wrap:wrap. Ở
//   container dọc, cross-size của một dòng flex do item rộng nhất quyết định,
//   không bị chặn bởi bề rộng container. .wallboard-actions-buttons có
//   flex-shrink:0 và min-width:auto, min-content của nó là tổng ba nút -- riêng
//   #epWbOpenKiosk đã 156px vì white-space:nowrap. Dòng nở ra 400.6px, rồi
//   align-items:stretch kéo luôn thẻ <p> hướng dẫn ra 400.6px.
//
// Vì vậy bài test đo CẢ hai thứ: tràn ngang, và bề rộng thẻ <p> so với khung
// cha. Chỉ đo tràn ngang thôi thì một bản vá kiểu "cho .wallboard-actions
// overflow:hidden" cũng qua được, mà lỗi bố cục vẫn còn nguyên bên trong.
const { test, expect } = require('@playwright/test');

const PHONES = [['iPhone SE', 320, 568], ['iPhone 12', 390, 844], ['iPhone 14 Pro Max', 430, 932]];
const WIDE = [['tablet', 834, 1112], ['laptop', 1366, 768], ['desktop', 1920, 1080]];

async function open(page, { width, height }) {
  await page.setViewportSize({ width, height });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=employee-productivity', { waitUntil: 'networkidle' });
  await expect(page.locator('.wallboard-actions')).toBeVisible({ timeout: 20000 });
}

const probe = () => {
  const vw = document.body.clientWidth;
  const box = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; };
  const actions = box('.wallboard-actions');
  const hint = box('.wallboard-actions-hint');
  const buttons = box('.wallboard-actions-buttons');
  return {
    viewport: vw,
    overflow: document.body.scrollWidth - vw,
    actionsWidth: Math.round(actions.width),
    hintWidth: Math.round(hint.width),
    buttonsWidth: Math.round(buttons.width),
    // Ai thực sự thò ra ngoài mép phải -- để khi đỏ thì biết ngay là cái gì.
    outside: [...document.querySelectorAll('*')]
      .filter(e => e.getBoundingClientRect().right > vw + 1)
      .map(e => (typeof e.className === 'string' && e.className)
        ? e.tagName.toLowerCase() + '.' + e.className.trim().split(/\s+/)[0]
        : e.tagName.toLowerCase())
      .slice(0, 6),
  };
};

for (const [label, width, height] of PHONES) {
  test(`${label} (${width}px): khối hành động Kiosk không tràn ngang`, async ({ page }) => {
    await open(page, { width, height });
    const g = await page.evaluate(probe);
    expect(g.overflow, `tràn ngang ${g.overflow}px, thủ phạm: ${JSON.stringify(g.outside)}`)
      .toBeLessThanOrEqual(1);
  });

  test(`${label} (${width}px): không con nào rộng hơn khung .wallboard-actions`, async ({ page }) => {
    await open(page, { width, height });
    const g = await page.evaluate(probe);
    // Đây mới là bất biến bị vi phạm: <p> 400.6px trong khung 332px.
    expect(g.hintWidth, `hướng dẫn ${g.hintWidth}px / khung ${g.actionsWidth}px`)
      .toBeLessThanOrEqual(g.actionsWidth);
    expect(g.buttonsWidth, `hàng nút ${g.buttonsWidth}px / khung ${g.actionsWidth}px`)
      .toBeLessThanOrEqual(g.actionsWidth);
    expect(g.actionsWidth).toBeLessThanOrEqual(g.viewport);
  });

  test(`${label} (${width}px): mỗi nút một hàng, bấm được cả ba`, async ({ page }) => {
    await open(page, { width, height });
    const buttons = page.locator('.wallboard-actions-buttons .btn');
    await expect(buttons).toHaveCount(3);
    const boxes = [];
    for (let i = 0; i < 3; i++) boxes.push(await buttons.nth(i).boundingBox());
    for (const b of boxes) {
      expect(b.width, `nút rộng ${b.width}px`).toBeGreaterThan(width * 0.7);
      // Nhãn dài không được đẩy nút ra ngoài mép phải.
      expect(Math.round(b.x + b.width)).toBeLessThanOrEqual(width + 1);
    }
    // Xếp dọc: nút sau nằm dưới nút trước.
    expect(boxes[1].y).toBeGreaterThanOrEqual(boxes[0].y + boxes[0].height - 1);
    expect(boxes[2].y).toBeGreaterThanOrEqual(boxes[1].y + boxes[1].height - 1);
  });
}

for (const [label, width, height] of WIDE) {
  test(`${label} (${width}px): giữ nguyên bố cục ngang, hướng dẫn và nút cùng một hàng`, async ({ page }) => {
    await open(page, { width, height });
    const g = await page.evaluate(probe);
    expect(g.overflow).toBeLessThanOrEqual(1);
    // Trên 720px khối này vẫn là hàng ngang: hướng dẫn hẹp hơn hẳn khung, nút
    // nằm bên phải chứ không trải hết. Bản vá cố ý không đụng tới.
    expect(g.hintWidth).toBeLessThan(g.actionsWidth);
    expect(g.buttonsWidth).toBeLessThan(g.actionsWidth);
    const first = await page.locator('.wallboard-actions-buttons .btn').first().boundingBox();
    const last = await page.locator('.wallboard-actions-buttons .btn').last().boundingBox();
    expect(Math.abs(first.y - last.y), 'ba nút phải cùng một hàng ở màn rộng').toBeLessThanOrEqual(2);
  });
}
