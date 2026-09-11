// Quản lý Session -- danh sách Session: TÊN Operation là chữ chính, MÃ là chip
// phụ.
//
// Hình cũ của cột Operation là MỘT thẻ <b> ghép mã trước tên, cùng cỡ chữ và
// cùng nét với tên:
//
//   011 · CẮT PHÔI THÂN THÙNG
//   PO-2609-114 / 10025-FB-201 · Thân thùng
//
// Mã đứng đầu ở trọng lượng của chữ chính nên nó là thứ đọc được trước, dù
// người trực xưởng tìm việc theo TÊN công đoạn. Cùng quy ước đã chốt ở
// dashboard-op-name-hierarchy.spec.js / row-text-hierarchy.spec.js, nay áp
// cho màn Quản lý Session bằng chính primitive MFUI.opIdentity({inline:true}).
//
// Bài test đo TRỌNG LƯỢNG THỊ GIÁC và HÌNH HỌC (cỡ chữ, nét, độ cao, padding,
// độ bão hoà màu nền) chứ không so chuỗi, nên nó không vỡ khi ai đó đổi cách
// viết mã -- và nó chặn đúng cái đã xảy ra: chip phình lại thành pill to, hoặc
// quay về nền màu thương hiệu.
const { test, expect } = require('@playwright/test');

const OPS = [
  { id: 1, code: '011', name: 'CẮT PHÔI THÂN THÙNG' },
  { id: 2, code: '012', name: 'CHẤN BƯỚC 1' },
  { id: 3, code: '013', name: 'HÀN GHÉP KHUNG' },
  // Tên dài cố ý: cột Operation phải cắt TÊN bằng ellipsis chứ không đẩy chip
  // mã ra khỏi hàng.
  { id: 4, code: '014', name: 'SƠN TĨNH ĐIỆN VÀ SẤY KHÔ TRONG LÒ LIÊN TỤC BƯỚC HAI' },
];

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());

const at = (date, h, m) =>
  new Date(`${date}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+07:00`).toISOString();

const OPTIONS = {
  ok: true,
  filters: {
    production_orders: [{ id: 1, code: 'PO-2609-114', product: 'Thùng rác công nghiệp 240L' }],
    parts: [{ id: 11, code: '10025-FB-201', name: 'Thân thùng' }],
    operations: OPS.map(o => ({ id: o.id, code: o.code, name: o.name })),
    employees: [{ id: 1, employee_no: 'NV01', name: 'Trần Tấn Đạt' }],
  },
  items: [],
};

const sessions = date => ({
  ok: true,
  items: OPS.map((o, i) => ({
    session_id: 900 + i,
    employee_id: 1 + i,
    employee_code: 'NV0' + (i + 1),
    employee_name: ['Trần Tấn Đạt', 'Lê Văn Bình', 'Nguyễn Thị Hồng Ngọc', 'Phạm Quốc Cường'][i],
    operation_id: o.id, operation_code: o.code, operation_name: o.name,
    po_code: 'PO-2609-114', part_code: '10025-FB-201', part_name: 'Thân thùng',
    started_at: at(date, 7, 30 + i), ended_at: i === 0 ? null : at(date, 11, 15 + i),
    status: i === 0 ? 'OPEN' : 'CLOSED',
    duration_seconds: 3600 * (2 + i),
    good_qty: 120 + i * 17, defect_qty: i, rework_qty: i % 2,
    station_code: 'TRAM-0' + (i + 1), device_uuid: 'KIOSK-0' + (i + 1), data_source: 'REAL_USER',
  })),
});

async function openSessionList(page, width = 1366) {
  const date = hcmDate();
  await page.setViewportSize({ width, height: 950 });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.route('**/api/session-management/operations**', r => r.fulfill({ json: OPTIONS }));
  await page.route('**/api/session-management?**', r => r.fulfill({ json: sessions(date) }));
  await page.goto('/app');
  await page.waitForFunction(() => typeof window.openPage === 'function', null, { timeout: 20000 });
  await page.evaluate(() => window.openPage('session-management', document.querySelector('[data-page="session-management"]')));
  await expect(page.locator('.session-accordion-item')).toHaveCount(OPS.length, { timeout: 20000 });
  return date;
}

// rgb(...) -> độ bão hoà: 0 là xám thuần. Dùng để chốt "chip TRUNG TÍNH", tức
// nền không phải màu thương hiệu, mà không phải ghim cứng một mã màu.
const saturationOf = css => {
  const [r, g, b] = (css.match(/[\d.]+/g) || []).slice(0, 3).map(Number);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  return max === 0 ? 0 : (max - min) / max;
};

test.describe('Quản lý Session · cột Operation', () => {
  for (const width of [1920, 1366, 390]) {
    test(`@ ${width}px: tên là chữ chính, mã là chip phụ nhỏ`, async ({ page }) => {
      await openSessionList(page, width);
      const block = page.locator('.session-row-operation .op-identity.inline').first();
      await expect(block).toBeVisible();

      const g = await block.evaluate(el => {
        const title = el.querySelector('b.row-title');
        const code = el.querySelector('small.row-code');
        if (!title || !code) return null;
        const t = getComputedStyle(title), c = getComputedStyle(code);
        return {
          titleText: title.textContent.trim(), codeText: code.textContent.trim(),
          titleSize: parseFloat(t.fontSize), codeSize: parseFloat(c.fontSize),
          titleWeight: +t.fontWeight, codeWeight: +c.fontWeight,
          titleH: title.getBoundingClientRect().height,
          codeH: code.getBoundingClientRect().height,
          codeTop: code.getBoundingClientRect().top,
          titleTop: title.getBoundingClientRect().top,
          codeLeft: code.getBoundingClientRect().left,
          titleLeft: title.getBoundingClientRect().left,
          titleRight: title.getBoundingClientRect().right,
          padTop: parseFloat(c.paddingTop), padBottom: parseFloat(c.paddingBottom),
          padLeft: parseFloat(c.paddingLeft), padRight: parseFloat(c.paddingRight),
          bg: c.backgroundColor,
        };
      });
      expect(g, 'không có .row-title + .row-code trong cột Operation').not.toBeNull();

      // 1 · Tên đọc trước mã, và mã không còn dính vào chuỗi tên.
      expect(g.titleText).toBe(OPS[0].name);
      expect(g.codeText).toBe(OPS[0].code);
      expect(g.titleLeft, 'tên phải đứng TRƯỚC mã theo chiều đọc').toBeLessThan(g.codeLeft);
      // Chip phải bám ngay sau tên. Ở màn rộng, một lưới chia đều phần thừa sẽ
      // đẩy chip ra tít mép phải cột -- lúc đó nó không còn đọc ra là chú thích
      // của cái tên nữa.
      expect(g.codeLeft - g.titleRight, 'chip mã bị đẩy rời khỏi tên')
        .toBeLessThanOrEqual(10);

      // 2 · Thứ bậc: mã nhỏ hơn và KHÔNG đậm hơn tên.
      expect(g.codeSize, `mã ${g.codeSize}px vs tên ${g.titleSize}px`).toBeLessThan(g.titleSize);
      expect(g.codeWeight, 'mã đậm hơn tên').toBeLessThanOrEqual(g.titleWeight);

      // 3 · Chip không phình: cỡ chữ, padding và ĐỘ CAO đều bị chặn trên. Độ
      //     cao phải nằm trong line-box của tên, nếu không nó lại đẩy hàng cao
      //     lên và làm lệch các cột bên cạnh.
      expect(g.codeSize, 'cỡ chữ mã vượt 11px').toBeLessThanOrEqual(11);
      expect(g.padTop, 'padding dọc của chip vượt 2px').toBeLessThanOrEqual(2);
      expect(g.padBottom).toBeLessThanOrEqual(2);
      expect(g.padLeft, 'padding ngang của chip vượt 6px').toBeLessThanOrEqual(6);
      expect(g.padRight).toBeLessThanOrEqual(6);
      expect(g.codeH, `chip cao ${g.codeH}px, vượt line-box ${g.titleH}px của tên`)
        .toBeLessThanOrEqual(g.titleH);

      // 4 · Chip TRUNG TÍNH, không phải pill nền màu thương hiệu.
      expect(saturationOf(g.bg), `nền chip ${g.bg} quá bão hoà -- đã quay lại pill màu`)
        .toBeLessThan(0.12);
    });
  }

  test('mọi hàng dùng chung một hình dạng chip (không chỗ to chỗ nhỏ)', async ({ page }) => {
    await openSessionList(page, 1366);
    const shapes = await page.locator('.session-row-operation small.row-code').evaluateAll(
      els => els.map(el => {
        const cs = getComputedStyle(el);
        return [cs.fontSize, cs.fontWeight, cs.padding, cs.borderRadius, cs.backgroundColor,
          Math.round(el.getBoundingClientRect().height)].join('|');
      }));
    expect(shapes).toHaveLength(OPS.length);
    expect(new Set(shapes).size, `chip lệch nhau giữa các hàng: ${[...new Set(shapes)].join(' // ')}`).toBe(1);
  });

  test('các cột trong một hàng thẳng chân, và các hàng cao bằng nhau', async ({ page }) => {
    await openSessionList(page, 1366);
    const rows = await page.locator('.session-accordion-trigger').evaluateAll(triggers =>
      triggers.map(row => {
        const first = sel => row.querySelector(sel)?.getBoundingClientRect().top ?? null;
        return {
          h: Math.round(row.getBoundingClientRect().height),
          tops: [
            first('.session-row-employee b'),
            first('.session-row-operation b.row-title'),
            first('.session-row-time b'),
            first('.session-row-output b'),
          ],
        };
      }));
    for (const [i, r] of rows.entries()) {
      expect(r.tops.every(t => t !== null), `hàng ${i}: thiếu dòng chính của một cột`).toBe(true);
      const spread = Math.max(...r.tops) - Math.min(...r.tops);
      expect(spread, `hàng ${i}: dòng chính các cột lệch ${spread}px`).toBeLessThanOrEqual(1);
    }
    const heights = new Set(rows.map(r => r.h));
    expect(heights.size, `các hàng cao khác nhau: ${[...heights].join(', ')}`).toBe(1);
  });

  test('390px: không tràn ngang, chip mã vẫn hiện đủ', async ({ page }) => {
    await openSessionList(page, 390);
    const overflow = await page.evaluate(() => ({
      body: document.body.scrollWidth > document.body.clientWidth,
      doc: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    }));
    expect(overflow, 'danh sách Session tràn ngang ở 390px').toEqual({ body: false, doc: false });
    // Hàng cuối có tên rất dài: TÊN được phép cắt, chip mã thì không được biến
    // mất hay bị đẩy ra ngoài mép cột.
    const last = page.locator('.session-row-operation small.row-code').last();
    await expect(last).toHaveText(OPS[OPS.length - 1].code);
    const inside = await last.evaluate(el => {
      const chip = el.getBoundingClientRect();
      const col = el.closest('.session-row-operation').getBoundingClientRect();
      return chip.right <= col.right + 1 && chip.left >= col.left - 1;
    });
    expect(inside, 'chip mã bị đẩy ra ngoài cột Operation').toBe(true);
  });

  test('không còn thẻ chữ-chính nào lấy mã OP làm phần mở đầu', async ({ page }) => {
    await openSessionList(page, 1366);
    const offenders = await page.evaluate(() =>
      [...document.querySelectorAll('#smSessionList b, #smSessionList strong')]
        .map(el => el.textContent.trim())
        .filter(text => /^[A-Z0-9][A-Z0-9-]{2,}\s+·\s+\S/.test(text)));
    expect(offenders, 'mã OP lại làm chữ chính trong danh sách Session').toEqual([]);
  });
});
