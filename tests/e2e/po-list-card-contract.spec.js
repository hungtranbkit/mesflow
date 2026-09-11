// DANH SÁCH PRODUCTION ORDER: mỗi PO là một THẺ TÁCH RỜI, không phải một dòng
// bảng. Hợp đồng REQ-UI-022.
//
// Bug thật trước bản vá: #poList dựng <table class="table-wrap"> nên mọi PO
// dính thành một khối dài, chỉ ngăn nhau bằng border-bottom xuyên suốt; ở
// 390px thì Trạng thái / Ưu tiên / hạn / Thao tác nằm sau một thanh cuộn
// NGANG bên trong .table-wrap -- người dùng phải kéo mới thấy trạng thái PO.
//
// Bài này đo COMPUTED STYLE trong trình duyệt thật, không đọc stylesheet:
// hình khối của thẻ do rule quét `[class$="-card"]` cấp bằng !important
// (ui.css §838), nên giá trị viết trong khối .po-card chứng minh được gì về
// pixel người dùng thấy. Giá trị bo góc hợp lệ cũng ĐỌC TỪ :root lúc chạy
// chứ không viết cứng -- lane integration đã một lần đổi tên và đổi giá trị
// cả thang (--radius-control 5px -> 8px), một danh sách px cứng sẽ mục âm
// thầm mà vẫn xanh.
//
// NEGATIVE PROOF (đã chạy tay, từng cái một):
//   - `.po-card-list{gap:0}`  -> "khoảng cách dọc thật" đỏ (gap 0px).
//   - `.po-card{border-radius:var(--radius-row)!important}` -> "bo góc
//     canonical" đỏ (5px không thuộc thang surface).
//   - dựng lại <table> trong #poList -> "không còn là bảng dính liền" đỏ.
const { test, expect } = require('@playwright/test');

const BASE = { product: 'Khung máy CNC-200', planned_quantity: 1200,
  source_template_code: 'TPL-KM-200', source_template_version: '2.1',
  planned_start_at: '2026-09-01T07:00:00', planned_end_at: '2026-09-20T17:00:00' };

// MỌI biến thể trạng thái đi qua CÙNG một renderer (draw()), nên mọi trạng
// thái phải là thẻ -- kể cả trạng thái không có nút primary (IN_PROGRESS,
// COMPLETED, CANCELLED), và PO cũ không có template nguồn.
const ITEMS = [
  { ...BASE, id: 1, code: 'QA-CARD-RUN',     status: 'IN_PROGRESS', priority: 'URGENT' },
  { ...BASE, id: 2, code: 'QA-CARD-DRAFT',   status: 'DRAFT',       priority: 'NORMAL' },
  { ...BASE, id: 3, code: 'QA-CARD-PLANNED', status: 'PLANNED',     priority: 'HIGH' },
  { ...BASE, id: 4, code: 'QA-CARD-RELEASED',status: 'RELEASED',    priority: 'NORMAL' },
  { ...BASE, id: 5, code: 'QA-CARD-PAUSED',  status: 'PAUSED',      priority: 'LOW' },
  { ...BASE, id: 6, code: 'QA-CARD-DONE',    status: 'COMPLETED',   priority: 'NORMAL', source_template_code: null },
  { ...BASE, id: 7, code: 'QA-CARD-CANCEL',  status: 'CANCELLED',   priority: 'NORMAL', planned_start_at: null, planned_end_at: null },
];

async function openList(page, items = ITEMS) {
  await page.route(/\/api\/production-orders(\?|$)/, r => r.fulfill({ json: { ok: true, items } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  // /login khi đã có phiên tự chuyển sang /app và cắt ngang goto kế tiếp --
  // cùng nguồn flaky đã ghi trong po-action-menu.spec.js.
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=production-orders');
  await expect(page.locator('.po-card').first()).toBeVisible({ timeout: 20000 });
}

// Thang bo góc canonical, đọc từ :root lúc chạy.
const radiusScale = page => page.evaluate(() => {
  const root = getComputedStyle(document.documentElement);
  const read = n => root.getPropertyValue(n).trim();
  return { surface: read('--radius-surface'),
           container: ['--radius-surface', '--radius-surface-row'].map(read).filter(Boolean) };
});

const cardBoxes = page => page.evaluate(() => [...document.querySelectorAll('#poList .po-card')].map(el => {
  const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
  return { code: el.dataset.poCode, top: r.top, bottom: r.bottom, height: r.height,
           radius: cs.borderTopLeftRadius,
           border: [cs.borderTopWidth, cs.borderRightWidth, cs.borderBottomWidth, cs.borderLeftWidth].map(parseFloat),
           bg: cs.backgroundColor, shadow: cs.boxShadow };
}));

for (const [label, width, height] of [['390', 390, 844], ['1366', 1366, 768], ['1920', 1920, 1080]]) {
  test(`mỗi PO là một thẻ riêng, có khoảng cách dọc thật @ ${label}`, async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize({ width, height });
    await openList(page);

    const boxes = await cardBoxes(page);
    expect(boxes.length, 'mọi trạng thái PO phải render thành thẻ').toBe(ITEMS.length);

    // ĐIỀU KIỆN CỐT LÕI: hai thẻ LIỀN NHAU phải cách nhau > 0px. Dòng bảng cũ
    // cho gap đúng bằng 0 -- đây chính là bài đỏ khi bỏ gap.
    for (let i = 1; i < boxes.length; i++) {
      const gap = boxes[i].top - boxes[i - 1].bottom;
      expect(gap, `thẻ ${boxes[i - 1].code} và ${boxes[i].code} dính nhau (gap ${gap}px)`).toBeGreaterThan(0);
    }

    // Thẻ phải có viền ĐỦ BỐN CẠNH. Bảng cũ chỉ có border-bottom chạy suốt --
    // kiểm "có border" không thôi sẽ không phân biệt được hai thứ.
    for (const b of boxes) {
      expect(b.border.every(w => w > 0), `${b.code} thiếu viền một cạnh: ${b.border.join('/')}`).toBe(true);
      expect(b.shadow, `${b.code} không có shadow tách nền`).not.toBe('none');
      expect(b.bg, `${b.code} phải có nền riêng`).not.toBe('rgba(0, 0, 0, 0)');
    }
  });

  test(`thẻ PO bo bằng token canonical @ ${label}`, async ({ page }) => {
    test.setTimeout(120000);
    await page.setViewportSize({ width, height });
    await openList(page);
    const scale = await radiusScale(page);
    const allowed = new Set(scale.container);
    for (const b of await cardBoxes(page)) {
      expect(allowed.has(b.radius), `${b.code} bo ${b.radius}, ngoài thang canonical ${[...allowed].join('/')}`).toBe(true);
    }
    // Thẻ PO đứng ở BẬC NGOÀI của thang (cùng bậc .dash-po-card/.pc-po-card),
    // không phải bậc lồng bên trong.
    expect((await cardBoxes(page))[0].radius).toBe(scale.surface);
  });
}

test('390px: không tràn ngang, không còn là bảng phải kéo ngang', async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 390, height: 844 });
  await openList(page);

  const m = await page.evaluate(() => {
    const host = document.getElementById('poList');
    return {
      pageOverflow: document.documentElement.scrollWidth - window.innerWidth,
      hostOverflow: host.scrollWidth - host.clientWidth,
      tables: host.querySelectorAll('table').length,
      wraps: host.querySelectorAll('.table-wrap').length,
      // Mọi thẻ phải nằm gọn trong bề ngang khung chứa.
      widest: Math.max(...[...host.querySelectorAll('.po-card')].map(e => e.getBoundingClientRect().width)),
      hostWidth: host.clientWidth,
    };
  });
  expect(m.pageOverflow, 'trang trượt ngang ở 390px').toBeLessThanOrEqual(1);
  expect(m.hostOverflow, '#poList vẫn phải kéo ngang mới xem hết').toBeLessThanOrEqual(1);
  expect(m.tables, 'danh sách PO không còn là bảng dính liền').toBe(0);
  expect(m.wraps, 'danh sách PO không còn .table-wrap (thanh cuộn ngang)').toBe(0);
  expect(m.widest).toBeLessThanOrEqual(m.hostWidth + 1);

  // Ở 390px thông tin phụ phải ĐỌC ĐƯỢC NGAY, không nằm sau thanh cuộn.
  const card = page.locator('.po-card', { has: page.locator('strong:text-is("QA-CARD-PAUSED")') });
  await expect(card.locator('.badge.po-status')).toBeVisible();
  await expect(card.locator('.po-card-meta')).toContainText('Kết thúc dự kiến');
  await expect(card.locator('.po-actions .btn.primary')).toBeVisible();
});

test('lọc theo trạng thái vẫn ra thẻ, không rơi về bảng', async ({ page }) => {
  test.setTimeout(120000);
  await page.setViewportSize({ width: 1366, height: 768 });
  await openList(page);
  for (const [value, code] of [['IN_PROGRESS', 'QA-CARD-RUN'], ['COMPLETED', 'QA-CARD-DONE'], ['CANCELLED', 'QA-CARD-CANCEL']]) {
    await page.selectOption('#poStatus', value);
    await expect(page.locator('#poList .po-card')).toHaveCount(1);
    await expect(page.locator('#poList .po-card strong').first()).toHaveText(code);
    expect(await page.locator('#poList table').count()).toBe(0);
  }
});
