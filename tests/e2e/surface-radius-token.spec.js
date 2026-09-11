// REQ-UI-013 -- bo góc của mọi bề mặt phải đến từ design token, không phải px viết cứng.
//
// Hợp đồng "mặt thẻ" (card-surface-contract.spec.js) đã khoá các class kết thúc
// bằng "-card": chúng do rule quét `.admin-body :where(.card,[class$="-card"],...)`
// đặt bằng !important nên luôn bằng --radius-card. Spec này phủ phần CÒN LẠI --
// panel, control và khung bao ngoài của bảng ở nhóm KIOSK / QR / danh mục / tiện
// ích -- vốn trước đây mỗi chỗ tự viết một con số.
//
// Đo trên TEST trước lần chuẩn hoá này, chín bề mặt cùng vai trò cho ra bảy giá trị:
//
//   .kiosk-panel 12px   .kiosk-header 12px   .kiosk-kpi 11px   .kiosk-empty 10px
//   .tutorial-hero 10px .esp-guide-workspace 10px  .qr-preview-box 10px
//   .template-old-op-table 6px (trong khi .op-list -- CÙNG một phần tử -- là 5px)
//   .se-review-note 6px
//
// Spec không cần dữ liệu thật: nó dựng phần tử mang đúng class vào trang đã tải
// rồi đọc computed style, tức kiểm ĐÚNG hợp đồng CSS, phủ được cả bề mặt mà môi
// trường test hôm nay chưa có dữ liệu để render.
const { test, expect } = require('@playwright/test');

// class -> tên token bắt buộc
const SURFACES = {
  // Khối/section
  'kiosk-panel':           '--radius-panel',
  'kiosk-header':          '--radius-panel',
  'kiosk-empty':           '--radius-panel',
  'tutorial-hero':         '--radius-panel',
  'esp-guide-workspace':   '--radius-panel',
  // Ô KPI đi cùng mặt thẻ
  'kiosk-kpi':             '--radius-card',
  // Control / ô nhỏ / khung bao ngoài của bảng
  'qr-preview-box':        '--radius-control',
  'template-old-op-table': '--radius-control',
  'op-list':               '--radius-control',
  'se-review-note':        '--radius-control',
};

async function open(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
}

test('bo góc của panel/control/bảng lấy từ token, không phải px viết cứng', async ({ page }) => {
  await open(page);
  const got = await page.evaluate((SURFACES) => {
    const host = document.createElement('div');
    host.style.cssText = 'position:absolute;left:-9999px;top:0;width:400px';
    document.body.appendChild(host);
    const root = getComputedStyle(document.documentElement);
    const out = {};
    for (const [cls, token] of Object.entries(SURFACES)) {
      const el = document.createElement('div');
      el.className = cls;
      host.appendChild(el);
      out[cls] = {
        actual: getComputedStyle(el).borderTopLeftRadius,
        expected: root.getPropertyValue(token).trim(),
        token,
      };
    }
    host.remove();
    return out;
  }, SURFACES);

  const wrong = Object.entries(got)
    .filter(([, v]) => v.actual !== v.expected)
    .map(([k, v]) => `  .${k}: ${v.actual} (phải là ${v.token} = ${v.expected})`);
  expect(wrong.join('\n'), `bề mặt không dùng token:\n${wrong.join('\n')}`).toBe('');
});

// .op-list và .template-old-op-table nằm trên CÙNG một phần tử
// (class="op-list template-old-op-table"). Trước lần chuẩn hoá này chúng khai báo
// hai giá trị khác nhau, nên hình khối phụ thuộc vào thứ tự rule trong file --
// đúng loại lỗi im lặng mà đổi thứ tự CSS là vỡ.
test('hai class trên cùng phần tử bảng OP không khai báo hai bo góc khác nhau', async ({ page }) => {
  await open(page);
  const g = await page.evaluate(() => {
    const mk = cls => {
      const e = document.createElement('div');
      e.className = cls;
      e.style.cssText = 'position:absolute;left:-9999px';
      document.body.appendChild(e);
      const v = getComputedStyle(e).borderTopLeftRadius;
      e.remove();
      return v;
    };
    return { both: mk('op-list template-old-op-table'), opList: mk('op-list'), old: mk('template-old-op-table') };
  });
  expect(g.opList).toBe(g.old);
  expect(g.both).toBe(g.opList);
});
