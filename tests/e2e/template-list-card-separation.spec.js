// "Danh sách Template" (màn Quy trình sản xuất mẫu) phải là DANH SÁCH THẺ RỜI.
//
// Báo từ người dùng kèm ảnh chụp trên iPhone: từng item đã bo góc nhưng dính
// sát nhau, viền dưới của thẻ trên chạm viền trên của thẻ dưới, cả danh sách
// đọc thành MỘT KHỐI DÀI. Đây là lỗi cài đặt của hợp đồng đã có (REQ-UI-017:
// "the cards are SEPARATED by a vertical gap taken from the spacing scale"),
// không phải thiếu hợp đồng.
//
// Đo trên TEST trước bản vá (computed style, 6 item, cả ba viewport):
//   .template-old-list  rowGap = 0px  (di sản thời item là dòng border-bottom)
//   khoảng cách bounding box giữa hai thẻ liên tiếp = 0px ở cả năm cặp
//   .template-old-card  radius 12px + viền 1px + bóng  (rule quét hậu tố "-card")
// tức hình khối thẻ đã đúng; đúng một thứ thiếu là separation.
//
// Vì sao đo CẢ HAI (rowGap và bounding box) chứ không chỉ một: rowGap bắt đúng
// nguyên nhân nhưng không chứng minh được kết quả (một `margin:0!important`
// hay `position` lạ vẫn kéo thẻ dính lại); bounding box chứng minh kết quả
// nhưng không nói vì sao. Bỏ bản vá thì cả hai cùng đỏ.
//
// 390px là acceptance CHÍNH (ảnh người dùng chụp trên iPhone); 1366/1920 đi kèm
// vì ở >=900px danh sách là rail dọc sticky, ở <900px nó đổi sang lưới auto-fill
// -- hai bố cục khác nhau của cùng một vỏ.
const { test, expect } = require('@playwright/test');

// Sáu mẫu: yêu cầu tối thiểu là 5, và số chẵn để lưới auto-fill ở màn hẹp
// không có hàng lẻ làm nhiễu phép đo.
const TPLS = Array.from({ length: 6 }, (_, i) => ({
  id: i + 1,
  code: `TPL-SEP-${String(i + 1).padStart(2, '0')}`,
  name: `Quy trình sản xuất mẫu số ${i + 1}`,
  product: `Sản phẩm ${i + 1}`,
  version: '1.0',
  active: i % 2 === 0,
  part_count: 2,
  operation_count: 3,
}));

const TREE = {
  template: TPLS[0],
  parts: [
    { id: 1, key: 'p1', code: 'P01', name: 'Thân thùng', sort_order: 0 },
    { id: 2, key: 'p2', code: 'P02', name: 'Nắp thùng', sort_order: 1 },
  ],
  operations: [
    { id: 11, part_key: 'p1', part_id: 1, code: 'OP01', name: 'Cắt', sort_order: 0, standard_seconds_per_unit: 60 },
    { id: 12, part_key: 'p1', part_id: 1, code: 'OP02', name: 'Hàn', sort_order: 1, standard_seconds_per_unit: 90 },
    { id: 13, part_key: 'p2', part_id: 2, code: 'OP03', name: 'Sơn', sort_order: 0, standard_seconds_per_unit: 30 },
  ],
  equipment: [],
};

const VIEWPORTS = [
  { width: 390, height: 844, name: '390 (iPhone — acceptance chính)' },
  { width: 1366, height: 768, name: '1366' },
  { width: 1920, height: 1080, name: '1920' },
];

async function openTemplates(page) {
  await page.route('**/api/templates?limit=500', r => r.fulfill({ json: { items: TPLS } }));
  await page.route('**/api/equipment*', r => r.fulfill({ json: { items: [] } }));
  await page.route(/\/api\/templates\/\d+$/, r => r.fulfill({ json: { item: TPLS[0] } }));
  await page.route(/\/api\/templates\/\d+\/tree$/, r => r.fulfill({ json: TREE }));
  await page.route('**/api/templates/*/import-history*', r => r.fulfill({ json: { items: [] } }));

  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  // Trang /login khi đã có phiên sẽ tự điều hướng sang /app và cắt ngang lần
  // goto ngay sau đó -- cùng nguồn flaky đã ghi trong template-ui.spec.js.
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
  await page.evaluate(() => openPage('templates', document.querySelector('[data-page="templates"]')));
  await expect(page.locator('.template-old-card').first()).toBeVisible({ timeout: 15000 });
}

// Đọc một lần, trả về mọi thứ cần khẳng định ở viewport hiện tại.
function measure(page) {
  return page.evaluate(() => {
    const list = document.querySelector('.template-old-list');
    if (!list) return { missing: true };
    const cs = getComputedStyle(list);
    const cards = [...list.querySelectorAll('.template-old-card')];
    const boxes = cards.map(c => c.getBoundingClientRect());
    const shape = cards.map(c => {
      const s = getComputedStyle(c);
      return {
        radius: parseFloat(s.borderTopLeftRadius),
        borderTop: parseFloat(s.borderTopWidth),
        borderBottom: parseFloat(s.borderBottomWidth),
        borderLeft: parseFloat(s.borderLeftWidth),
        borderRight: parseFloat(s.borderRightWidth),
        shadow: s.boxShadow,
      };
    });
    return {
      count: cards.length,
      rowGap: parseFloat(cs.rowGap),
      rowGapRaw: cs.rowGap,
      // Khoảng hở THẬT giữa hai thẻ liên tiếp trên cùng một cột. Ở màn hẹp vỏ
      // là lưới auto-fill nên hai thẻ cạnh nhau có thể nằm cùng hàng -- chỉ
      // lấy cặp thực sự xếp dọc (thẻ sau bắt đầu thấp hơn thẻ trước).
      verticalGaps: boxes.slice(1).map((b, i) => {
        const a = boxes[i];
        if (b.top < a.top + 1) return null;                 // cùng hàng
        return +(b.top - (a.top + a.height)).toFixed(2);
      }).filter(g => g !== null),
      shape,
    };
  });
}

test('mỗi Template trong "Danh sách Template" là thẻ rời, có khoảng cách dọc thật', async ({ page }) => {
  await openTemplates(page);

  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.evaluate(() => typeof closeMobileSidebar === 'function' && closeMobileSidebar());
    // Một khung hình để layout ổn định trước khi đo bounding box.
    await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));

    const m = await measure(page);
    const where = `@${vp.name}`;
    expect(m.missing, `${where}: không tìm thấy .template-old-list`).toBeFalsy();
    expect(m.count, `${where}: cần ít nhất 5 item để phép đo có nghĩa`).toBeGreaterThanOrEqual(5);

    // (1) Nguyên nhân: vỏ danh sách phải khai separation qua thang spacing.
    expect(m.rowGap, `${where}: .template-old-list rowGap=${m.rowGapRaw} -- các thẻ dính sát nhau`)
      .toBeGreaterThan(0);

    // (2) Kết quả: không cặp thẻ liên tiếp nào chạm nhau.
    expect(m.verticalGaps.length, `${where}: không đo được cặp thẻ nào xếp dọc`).toBeGreaterThanOrEqual(4);
    for (const [i, gap] of m.verticalGaps.entries()) {
      expect(gap, `${where}: thẻ ${i + 1} và ${i + 2} chạm nhau (khoảng hở ${gap}px)`).toBeGreaterThan(0);
    }

    // (3) Hình khối thẻ giữ nguyên: viền KHÉP KÍN bốn cạnh + bo góc + bóng
    // (REQ-UI-017). Chặn cách "sửa" bằng việc bỏ luôn mặt thẻ đi.
    for (const [i, s] of m.shape.entries()) {
      expect(s.radius, `${where}: thẻ ${i + 1} mất bo góc`).toBeGreaterThan(0);
      expect(
        Math.min(s.borderTop, s.borderBottom, s.borderLeft, s.borderRight),
        `${where}: thẻ ${i + 1} không có viền khép kín bốn cạnh (${JSON.stringify(s)})`
      ).toBeGreaterThan(0);
      expect(s.shadow, `${where}: thẻ ${i + 1} mất bóng thẻ`).not.toBe('none');
    }
  }
});

// Quét cùng-primitive trong CHÍNH màn Template: bất cứ vỏ nào đang xếp nhiều
// surface dạng thẻ (bo góc + viền khép kín) theo chiều dọc thì hai cái liên
// tiếp không được chạm nhau. Mục đích là không để sót một chỗ gap=0 thứ hai ở
// trên/dưới cùng trang, chứ không mở rộng ra ngoài màn này.
test('không còn vỏ nào trong màn Template xếp thẻ dính nhau', async ({ page }) => {
  await openTemplates(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => typeof closeMobileSidebar === 'function' && closeMobileSidebar());
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));

  const offenders = await page.evaluate(() => {
    // "Cùng primitive" = thứ mà rule quét hình khối ở cuối ui.css coi là THẺ:
    // nhận theo hậu tố tên class (-card / card / -block / -item), đúng cách
    // rule đó nhận. Lọc theo hình dạng thuần tuý thì ô nhập và nút trong
    // .template-old-op-row cũng lọt (radius 8px của --radius-control, có viền)
    // -- chúng là CONTROL, không phải surface, và nằm cạnh nhau là đúng.
    const NAMED_SURFACE = /(^|\s)(card|[\w-]+-(card|block|item))(\s|$)/;
    const isCardSurface = el => {
      const cls = typeof el.className === 'string' ? el.className : '';
      if (!NAMED_SURFACE.test(cls)) return false;
      const s = getComputedStyle(el);
      return parseFloat(s.borderTopLeftRadius) >= 8
        && parseFloat(s.borderTopWidth) > 0 && parseFloat(s.borderBottomWidth) > 0
        && el.getBoundingClientRect().height > 0;
    };
    const bad = [];
    for (const el of document.querySelectorAll('#content *')) {
      const kids = [...el.children].filter(isCardSurface);
      if (kids.length < 2) continue;
      const boxes = kids.map(k => k.getBoundingClientRect());
      for (let i = 1; i < boxes.length; i++) {
        const a = boxes[i - 1], b = boxes[i];
        if (b.top < a.top + 1) continue;               // cùng hàng, không phải cặp dọc
        const gap = b.top - (a.top + a.height);
        if (gap <= 0) {
          bad.push(`${el.className.trim().split(/\s+/).join('.') || el.tagName} `
            + `[${kids[i - 1].className.trim().split(/\s+/)[0]} -> ${kids[i].className.trim().split(/\s+/)[0]}] `
            + `gap=${gap.toFixed(2)}px`);
          break;
        }
      }
    }
    return bad;
  });

  expect(offenders, `vỏ còn xếp thẻ dính nhau:\n  ${offenders.join('\n  ')}`).toEqual([]);
});
