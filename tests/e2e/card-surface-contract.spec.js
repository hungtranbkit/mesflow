// Hợp đồng "mặt thẻ": mọi thẻ danh sách nghiệp vụ phải cùng bo góc, cùng viền,
// cùng nền, cùng đổ bóng -- bất kể nó ở màn nào (GĐ5 chuẩn hoá UI).
//
// Đo trên TEST trước GĐ5, năm thẻ cùng vai trò cho ra ba hình khác nhau:
//
//   .qr-catalog-card        7px  #c8d0d8  bóng .075
//   .kiosk-card             7px  #c8d0d8  bóng .075
//   .session-accordion-item 7px  #c8d0d8  bóng .075
//   .ec-card                8px  #d7dfe6  KHÔNG bóng
//   .ba-card                8px  #d6dce3  KHÔNG bóng
//   .kiosk-generation-card  8px  #d9dee7  KHÔNG bóng, nền #f7f9fa
//
// Nguyên nhân không phải "mỗi màn tự viết CSS": hình khối thẻ do MỘT rule quét
// [class$="-card"] đặt, rồi một danh sách LIỆT KÊ TAY ở dưới ghi đè cho từng
// tên cụ thể. Thẻ nào chưa được thêm tên vào danh sách thì lệch. Đó là lỗi của
// cơ chế, không phải của người quên -- nên bản vá bỏ danh sách tay và để rule
// quét mang thẳng hình khối đúng.
//
// Spec này KHÔNG cần dữ liệu thật: nó dựng phần tử mang đúng class vào trang
// đã tải rồi đọc computed style, tức là kiểm ĐÚNG hợp đồng CSS. Danh sách phủ
// cả những thẻ hôm nay chưa có dữ liệu trên môi trường test.
const { test, expect } = require('@playwright/test');

// Thẻ danh sách nghiệp vụ -- tất cả phải cùng một mặt.
const CARDS = [
  'qr-catalog-card',        // Danh mục QR
  'kiosk-card',             // Quản lý Kiosk
  'kiosk-generation-card',  // Quản lý Kiosk -- thẻ thế hệ token
  'ec-card',                // Trung tâm ngoại lệ
  'ba-card',                // Nhật ký nghiệp vụ
  'session-accordion-item', // Quản lý Session
  'shift-config-card',      // Lịch làm việc
  'guide-card',             // Hướng dẫn
  'tutorial-card',
];

// Ô KPI / thẻ tóm tắt -- khác vai trò nhưng vẫn phải cùng mặt.
const SURFACES = ['card', 'daily-kpi', 'pc-kpi', 'dash-metric'];

const PROPS = ['borderTopLeftRadius', 'borderTopWidth', 'borderTopColor',
               'backgroundColor', 'boxShadow'];

async function measure(page, classes) {
  return page.evaluate(({ classes, props }) => {
    const host = document.createElement('div');
    host.style.cssText = 'position:absolute;left:-9999px;top:0;width:400px';
    document.body.appendChild(host);
    const out = {};
    for (const cls of classes) {
      const el = document.createElement('div');
      el.className = cls;
      host.appendChild(el);
      const cs = getComputedStyle(el);
      out[cls] = props.map(p => cs[p]).join(' | ');
    }
    host.remove();
    return out;
  }, { classes, props: PROPS });
}

async function open(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
}

test('mọi thẻ danh sách nghiệp vụ có cùng một mặt', async ({ page }) => {
  await open(page);
  const got = await measure(page, CARDS);
  const distinct = [...new Set(Object.values(got))];
  const report = Object.entries(got).map(([k, v]) => `  .${k}\n      ${v}`).join('\n');
  expect(distinct.length, `${distinct.length} hình khác nhau:\n${report}`).toBe(1);
});

test('ô KPI và thẻ tóm tắt dùng cùng mặt với thẻ danh sách', async ({ page }) => {
  await open(page);
  const got = await measure(page, [...CARDS, ...SURFACES]);
  const distinct = [...new Set(Object.values(got))];
  const report = Object.entries(got).map(([k, v]) => `  .${k}\n      ${v}`).join('\n');
  expect(distinct.length, `${distinct.length} hình khác nhau:\n${report}`).toBe(1);
});

test('mặt thẻ lấy từ token, không phải giá trị viết cứng', async ({ page }) => {
  await open(page);
  const g = await page.evaluate(() => {
    const el = document.createElement('div');
    el.className = 'qr-catalog-card';
    el.style.cssText = 'position:absolute;left:-9999px';
    document.body.appendChild(el);
    const cs = getComputedStyle(el);
    const root = getComputedStyle(document.documentElement);
    const out = {
      radius: cs.borderTopLeftRadius, shadow: cs.boxShadow, border: cs.borderTopColor,
      // Bậc canonical của khối nội dung (2026-09-11). Trước đây là
      // --radius-card = 7px; tên đó nay phục vụ phần tử NHỎ (icon sidebar,
      // thanh gantt), còn thẻ/panel/section lấy --radius-surface.
      tokenRadius: root.getPropertyValue('--radius-surface').trim(),
      tokenBorder: root.getPropertyValue('--border-default').trim(),
    };
    el.remove();
    return out;
  });
  expect(g.radius).toBe(g.tokenRadius);
  // #c8d0d8 -> rgb(200, 208, 216)
  const hex = g.tokenBorder.replace('#', '');
  const rgb = `rgb(${parseInt(hex.slice(0, 2), 16)}, ${parseInt(hex.slice(2, 4), 16)}, ${parseInt(hex.slice(4, 6), 16)})`;
  expect(g.border).toBe(rgb);
  expect(g.shadow, 'thẻ phải có đổ bóng tinh tế, không phải none').not.toBe('none');
});

test('.part-block giữ mặt riêng, không bị rule quét "-card" cuốn theo', async ({ page }) => {
  await open(page);
  const g = await page.evaluate(() => {
    const mk = cls => { const e = document.createElement('div'); e.className = cls;
      e.style.cssText = 'position:absolute;left:-9999px'; document.body.appendChild(e);
      const cs = getComputedStyle(e); const v = cs.borderTopColor; e.remove(); return v; };
    return { part: mk('part-block po-part-card'), card: mk('qr-catalog-card') };
  });
  // Khối Part cố ý dùng --border-block (đậm hơn) để thấy ranh giới giữa các Part.
  expect(g.part).not.toBe(g.card);
});
