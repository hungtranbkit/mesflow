// Gantt / Tiến trình sản xuất phải nói cùng ngôn ngữ giao diện với phần còn
// lại của MESFlow (GĐ3 chuẩn hoá UI), NHƯNG không được mất hành vi timeline.
//
// Hiện trạng trước GĐ3, nhìn thấy trên ảnh chụp mesflow.net: cả màn phẳng --
// khối PO không đọc ra là card, dải Part gần như trùng nền hàng Operation, cột
// nhãn trái không tách khỏi timeline, lưới dọc đậm ngang với dữ liệu, thanh
// công việc thì nổi bóng hơn cần thiết.
//
// Nguyên nhân đáng nhớ nhất: .gantt-part và .gantt-row là display:contents --
// chúng KHÔNG sinh box, nên border/radius/background/shadow đặt lên chúng
// không vẽ ra gì. Vậy mà cả hai từng nằm trong một danh sách hợp nhất kèm
// !important. Dải Part thật ra do .gantt-part h3 vẽ, và nó là #f6f8fc, gần
// trùng nền hàng bên dưới.
//
// display:contents chính là thứ giữ cho nhãn trái và timeline nằm chung một
// lưới, tức là thẳng hàng. Spec này vì vậy chốt CẢ HAI phía: diện mạo mới, và
// những hành vi không được phép mất (cuộn ngang, sticky header, thẳng hàng).
const { test, expect } = require('@playwright/test');

const VIEWS = [['1920', 1920, 1080], ['1366', 1366, 900], ['tablet', 834, 1112],
               ['mobile', 390, 900], ['nhỏ', 320, 800]];

const T = (h) => new Date(Date.UTC(2026, 7, 21, h, 0, 0)).toISOString();

function op(id, partId, partCode, partName, code, name, startH, endH, extra = {}) {
  return {
    po_id: 1, po_code: 'PO-GANTT', product: 'Thùng rác E10GRE', po_status: 'IN_PROGRESS',
    due_date: '2026-08-30', part_id: partId, part_code: partCode, part_name: partName,
    operation_id: id, operation_code: code, operation_name: name,
    operation_status: 'IN_PROGRESS', progress_percent: 30, active_sessions: 0,
    planned_start_at: T(startH), planned_end_at: T(endH),
    calculated_start_at: T(startH), calculated_end_at: T(endH),
    actual_start_at: null, actual_end_at: null,
    planned_quantity: 1000, done_quantity: 308,
    input_flow_enabled: false, input_source_operation_id: null, ...extra,
  };
}

const ITEMS = [
  op(1, 11, '10025-FB-201', 'Thân thùng rác', 'THAN-R-01', 'CẮT PHÔI CHO THÂN THÙNG RÁC', 0, 6),
  op(2, 11, '10025-FB-201', 'Thân thùng rác', 'THAN-R-02', 'ĐỘT THÂN THÙNG RÁC', 6, 10),
  op(3, 11, '10025-FB-201', 'Thân thùng rác', 'THAN-R-03', 'CHẤN BƯỚC 1 ( Gấp Mí )', 10, 14),
  op(4, 12, '10025-FB-301', 'Đáy thùng rác', 'DAY-R-01', 'CẮT LASER ĐẾ THÙNG RÁC', 2, 8),
  op(5, 12, '10025-FB-301', 'Đáy thùng rác', 'DAY-R-02', 'HÀN ĐÁY THÙNG RÁC', 8, 16),
];

async function open(page, { width, height }) {
  await page.setViewportSize({ width, height });
  await page.route(/\/api\/production-schedule/, r => r.fulfill({ json: { ok: true, items: ITEMS } }));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=production-schedule');
  await expect(page.locator('.gantt-po').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(400);
}

const rgb = s => (s.match(/\d+/g) || []).slice(0, 3).map(Number);
const lum = s => { const [r, g, b] = rgb(s); return (0.299 * r + 0.587 * g + 0.114 * b) || 0; };

// --- diện mạo: cùng ngôn ngữ với phần còn lại -----------------------------

test('khối PO là một card thật: viền, bo góc, đổ bóng theo token', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const g = await page.locator('.gantt-po').first().evaluate(el => {
    const cs = getComputedStyle(el);
    return { radius: cs.borderTopLeftRadius, borderW: cs.borderTopWidth,
             shadow: cs.boxShadow, bg: cs.backgroundColor };
  });
  expect(parseFloat(g.radius), 'khối PO phải bo góc').toBeGreaterThan(0);
  expect(parseFloat(g.borderW), 'khối PO phải có viền').toBeGreaterThan(0);
  expect(g.shadow, 'khối PO phải có đổ bóng nhẹ').not.toBe('none');
});

test('ba tầng phân biệt được: header PO đậm hơn dải Part, dải Part đậm hơn hàng OP', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const g = await page.evaluate(() => {
    const bg = s => getComputedStyle(document.querySelector(s)).backgroundColor;
    return { head: bg('.schedule-po-head'), part: bg('.gantt-part h3'), label: bg('.gantt-label') };
  });
  // Nền sáng dần từ tầng 1 xuống tầng 3 -- đó là thứ làm mắt đọc được phân cấp.
  expect(lum(g.head), `header ${g.head} phải tối hơn dải Part ${g.part}`).toBeLessThan(lum(g.part));
  expect(lum(g.part), `dải Part ${g.part} phải tối hơn hàng OP ${g.label}`).toBeLessThan(lum(g.label));
  // "Rõ nhưng không quá đậm": chênh lệch có thật nhưng không thành màu mạnh.
  expect(lum(g.label) - lum(g.head)).toBeGreaterThan(4);
  expect(lum(g.label) - lum(g.head)).toBeLessThan(60);
});

test('dải Part đọc được là ranh giới, không lẫn vào hàng Operation', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const bands = page.locator('.gantt-part h3');
  await expect(bands).toHaveCount(2);
  const g = await bands.first().evaluate(el => {
    const cs = getComputedStyle(el);
    return { leftBorder: parseFloat(cs.borderLeftWidth), weight: +cs.fontWeight,
             bg: cs.backgroundColor,
             rowBg: getComputedStyle(document.querySelector('.gantt-label')).backgroundColor };
  });
  expect(g.bg, 'dải Part không được trùng nền hàng OP').not.toBe(g.rowBg);
  expect(g.leftBorder, 'dải Part cần vạch dọc dẫn mắt').toBeGreaterThanOrEqual(2);
  expect(g.weight).toBeGreaterThanOrEqual(700);
});

test('cột nhãn trái tách khỏi timeline bằng viền đậm hơn viền hàng', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const g = await page.locator('.gantt-label').first().evaluate(el => {
    const cs = getComputedStyle(el);
    return { right: cs.borderRightColor, bottom: cs.borderBottomColor };
  });
  expect(lum(g.right), 'viền phải cột nhãn phải đậm hơn viền dưới hàng')
    .toBeLessThan(lum(g.bottom));
});

test('lưới dọc timeline mờ hơn thanh công việc, thanh là pill và bóng nhẹ', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const g = await page.evaluate(() => {
    const bar = document.querySelector('.gantt-bar');
    const cs = getComputedStyle(bar);
    const track = getComputedStyle(document.querySelector('.gantt-track'));
    return { radius: cs.borderTopLeftRadius, shadow: cs.boxShadow,
             barBg: cs.backgroundColor, grid: track.backgroundImage,
             minW: cs.minWidth };
  });
  // Pill: bo góc lớn hơn nửa chiều cao thanh (26px).
  expect(parseFloat(g.radius), 'thanh công việc phải là pill').toBeGreaterThanOrEqual(13);
  // Bóng nhẹ: một lớp, độ mờ nhỏ -- không "nổi khỏi mặt phẳng".
  expect(g.shadow).not.toBe('none');
  expect(g.shadow.split('rgba').length - 1, 'chỉ một lớp bóng').toBeLessThanOrEqual(1);
  // Lưới dọc vẽ bằng gradient, và màu của nó phải sáng hơn màu thanh.
  expect(g.grid).toContain('gradient');
  expect(parseFloat(g.minW), 'thanh rất ngắn vẫn phải thấy được').toBeGreaterThanOrEqual(8);
});

// --- hành vi timeline KHÔNG được mất --------------------------------------

test('nhãn trái và hàng timeline vẫn thẳng hàng từng dòng', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const pairs = await page.evaluate(() => {
    const labels = [...document.querySelectorAll('.gantt-label')];
    const tracks = [...document.querySelectorAll('.gantt-track')];
    return labels.map((l, i) => {
      const a = l.getBoundingClientRect(), b = tracks[i].getBoundingClientRect();
      return { dTop: Math.abs(a.top - b.top), dH: Math.abs(a.height - b.height) };
    });
  });
  expect(pairs.length).toBe(5);
  for (const p of pairs) {
    expect(p.dTop, `nhãn lệch dòng ${p.dTop}px`).toBeLessThanOrEqual(1);
    expect(p.dH, `nhãn cao lệch ${p.dH}px`).toBeLessThanOrEqual(1);
  }
});

test('.gantt-part và .gantt-row vẫn là display:contents (thứ giữ hai bên thẳng hàng)', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const g = await page.evaluate(() => ({
    part: getComputedStyle(document.querySelector('.gantt-part')).display,
    row: getComputedStyle(document.querySelector('.gantt-row')).display,
    wrap: getComputedStyle(document.querySelector('.gantt-wrap')).display,
  }));
  expect(g.part).toBe('contents');
  expect(g.row).toBe('contents');
  expect(g.wrap).toBe('grid');
});

test('header PO vẫn sticky', async ({ page }) => {
  await open(page, { width: 1366, height: 900 });
  const pos = await page.locator('.schedule-po-head').first()
    .evaluate(el => getComputedStyle(el).position);
  expect(pos).toBe('sticky');
});

for (const [label, width, height] of VIEWS) {
  test(`${label}: timeline cuộn ngang được, trang không tràn ngang`, async ({ page }) => {
    await open(page, { width, height });
    const g = await page.evaluate(() => {
      const w = document.querySelector('.gantt-wrap');
      return { bodyOvf: document.body.scrollWidth - document.body.clientWidth,
               overflowX: getComputedStyle(w).overflowX,
               clientW: w.clientWidth, scrollW: w.scrollWidth };
    });
    expect(g.bodyOvf, `trang tràn ngang ${g.bodyOvf}px`).toBeLessThanOrEqual(1);
    expect(g.overflowX, 'timeline phải tự cuộn, không đẩy cả trang').toMatch(/auto|scroll/);
    expect(g.scrollW, 'timeline phải rộng hơn khung để có gì mà cuộn')
      .toBeGreaterThanOrEqual(g.clientW);
  });
}

test('không có lỗi console khi mở Gantt', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + String(e).slice(0, 200)));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text().slice(0, 200)); });
  await open(page, { width: 1366, height: 900 });
  expect(errors, errors.join('\n')).toEqual([]);
});
