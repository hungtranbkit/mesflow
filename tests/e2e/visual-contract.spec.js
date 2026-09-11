// Hợp đồng thị giác đo TRÊN TRANG THẬT, ở bốn viewport.
//
// Bổ sung cho tests/test_ui_surface_radius_is_canonical.py (đọc file CSS) và
// card-surface-contract.spec.js (đo mặt thẻ). Hai bộ đó trả lời "CSS viết đúng
// chưa"; bộ này trả lời "kết quả trên màn hình có đúng không" -- và cả loạt lỗi
// của dự án nằm đúng ở chỗ hai câu trả lời đó khác nhau:
//
//   * `.op-list-head` góc vuông chọc ra khỏi góc tròn của `.op-list`: cả hai
//     đều dùng token hợp lệ, không assertion nào so góc trong với góc ngoài.
//   * Rule quét ép mọi thẻ về 7px trong khi CSS tại chỗ viết 12-14px: file CSS
//     "đúng", chênh lệch chỉ hiện ra khi đọc computed style.
//   * Trung tâm ngoại lệ ở 390px: mọi phần tử đều tồn tại và đúng token, chỉ
//     BỐ CỤC là sai.
//
// Xem skills/visual-ui-audit/SKILL.md cho pipeline đầy đủ. File này là bước 1
// và bước 2; bước 3 (người/agent tự soi ảnh) KHÔNG tự động hoá được, và không
// được coi là đã làm chỉ vì bộ test này xanh.
const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

// 390 điện thoại · 768 tablet · 1366 desktop chính của dự án (REQ-UI-005) · 1920
const VIEWPORTS = [
  { name: '390', width: 390, height: 844 },
  { name: '768', width: 768, height: 1024 },
  { name: '1366', width: 1366, height: 768 },
  { name: '1920', width: 1920, height: 1080 },
];

const SHOTS = path.join('test-results', 'visual-audit');

// Màn đại diện: mỗi cái mang một HỌ list khác nhau. Không cần phủ hết 30 view --
// mục tiêu là bắt việc một họ bị lệch, mà lệch thì lệch ở primitive dùng chung.
const SCREENS = [
  { name: 'overview', url: '/app?page=overview' },
  { name: 'production-orders', url: '/app?page=production-orders' },
  { name: 'exception-center', url: '/app?page=exception-center' },
  { name: 'qr-print', url: '/app?page=qr-print' },
];


// Ảnh `loading="lazy"` nằm dưới màn hình đầu tiên CHƯA tải khi Playwright chụp
// fullPage -- nó ghép ảnh chứ không thật sự cuộn qua từng đoạn. Hậu quả không
// vô hại: bản chụp đầu tiên của màn "In tem QR" ở 390px cho ra 10 thẻ có mã QR
// và 16 thẻ trống trơn, trông y hệt một lỗi sinh ảnh hàng loạt.
//
// Một audit ảnh không xử việc này sẽ sinh kết luận sai theo CẢ HAI hướng: báo
// nhầm lỗi không có, rồi dạy người soi quen bỏ qua ô trắng -- nên lần có ô
// trắng THẬT cũng bị bỏ qua.
async function settleLazyImages(page) {
  await page.evaluate(async () => {
    const step = window.innerHeight;
    for (let y = 0; y < document.body.scrollHeight; y += step) {
      window.scrollTo(0, y);
      await new Promise(r => requestAnimationFrame(r));
    }
    window.scrollTo(0, 0);
    await Promise.all([...document.images]
      .filter(img => !img.complete)
      .map(img => new Promise(done => {
        img.addEventListener('load', done, { once: true });
        img.addEventListener('error', done, { once: true });
      })));
  });
}

async function signIn(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
}

test.beforeAll(() => fs.mkdirSync(SHOTS, { recursive: true }));

test('token bo góc giải được ra px thật, không phải chuỗi rỗng', async ({ page }) => {
  // Trỏ tới một token đã bị xoá làm cả khai báo border-radius thành không hợp
  // lệ và phần tử rơi về góc vuông -- CSS không báo gì cả. Bài này bắt đúng
  // trạng thái đó trên trang thật.
  await signIn(page);
  const resolved = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement);
    const names = ['--radius-surface', '--radius-surface-row', '--radius-control', '--radius-overlay'];
    const out = {};
    for (const n of names) out[n] = root.getPropertyValue(n).trim();
    return out;
  });
  for (const [name, value] of Object.entries(resolved)) {
    expect(value, `${name} không giải ra được -- token bị xoá khỏi :root?`).toMatch(/^\d+px$/);
  }
  // Không được silent-skip: nếu một token biến mất, vòng lặp trên phải đỏ chứ
  // không phải chạy qua một dict rỗng.
  expect(Object.keys(resolved).length).toBe(4);
});

test('thẻ trong một card-list không dính nhau', async ({ page }) => {
  await signIn(page);
  const gaps = await page.evaluate(() => {
    const out = [];
    for (const list of document.querySelectorAll('.lead-list,.overview-list,.control-bottleneck-list,.mf-history,.session-manage-table')) {
      const cs = getComputedStyle(list);
      const items = [...list.children].filter(n => n.nodeType === 1);
      if (items.length < 2) continue;
      const rowGap = parseFloat(cs.rowGap) || 0;
      const margin = parseFloat(getComputedStyle(items[1]).marginTop) || 0;
      // Khoảng cách thật giữa hai item liền nhau, đo bằng hình học chứ không
      // tin một thuộc tính đơn lẻ: gap và margin có thể thay nhau.
      const a = items[0].getBoundingClientRect();
      const b = items[1].getBoundingClientRect();
      out.push({ cls: list.className, rowGap, margin, geometric: Math.round(b.top - a.bottom) });
    }
    return out;
  });
  for (const g of gaps) {
    expect(Math.max(g.rowGap, g.margin, g.geometric),
      `card-list "${g.cls}" có hai thẻ dính nhau (gap=${g.rowGap} margin=${g.margin} hình học=${g.geometric})`)
      .toBeGreaterThan(0);
  }
});

for (const vp of VIEWPORTS) {
  test(`không tràn ngang và không có con vượt biên cha @${vp.name}`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await signIn(page);

    for (const screen of SCREENS) {
      await page.goto(screen.url);
      await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });

      const problems = await page.evaluate(() => {
        const found = [];
        // 1. Trang không được cuộn ngang.
        const doc = document.documentElement;
        if (doc.scrollWidth > doc.clientWidth + 1) {
          found.push(`trang cuộn ngang: scrollWidth=${doc.scrollWidth} > clientWidth=${doc.clientWidth}`);
        }
        // 2. Con không được tràn ra ngoài cha. Bỏ qua chỗ CỐ Ý cuộn ngang
        //    (bảng dày, gantt) -- chúng có overflow riêng và đó là thiết kế.
        for (const parent of document.querySelectorAll('.panel,.card,.content-panel,.part-block')) {
          const ps = getComputedStyle(parent);
          if (ps.overflowX === 'auto' || ps.overflowX === 'scroll' || ps.overflowX === 'hidden') continue;
          const pr = parent.getBoundingClientRect();
          if (pr.width === 0) continue;
          for (const child of parent.children) {
            const cs = getComputedStyle(child);
            if (cs.position === 'absolute' || cs.position === 'fixed') continue;
            if (cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
            const cr = child.getBoundingClientRect();
            if (cr.width === 0) continue;
            if (cr.right > pr.right + 1) {
              found.push(`${child.className || child.tagName} tràn khỏi ${parent.className}: ${Math.round(cr.right - pr.right)}px`);
            }
          }
        }
        return found;
      });

      expect(problems, `${screen.name} @${vp.name}:\n  ${problems.join('\n  ')}`).toEqual([]);
    }
  });

  test(`chụp màn đại diện @${vp.name}`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await signIn(page);

    for (const screen of SCREENS) {
      await page.goto(screen.url);
      await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
      await settleLazyImages(page);
      const file = path.join(SHOTS, `${screen.name}-${vp.name}.png`);
      await page.screenshot({ path: file, fullPage: true });

      // Ảnh 0 byte hoặc sai bề rộng nghĩa là bước chụp hỏng, và mọi kết luận
      // "đã soi ảnh" sau đó là vô giá trị. Khẳng định thay vì tin.
      const stat = fs.statSync(file);
      expect(stat.size, `${file} rỗng`).toBeGreaterThan(1000);
      const header = fs.readFileSync(file).subarray(16, 24);
      const width = header.readUInt32BE(0);
      expect(width, `${file} rộng ${width}px, mong đợi ${vp.width}px`).toBe(vp.width);
    }
  });
}
