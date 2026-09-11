const { test, expect } = require('@playwright/test');

// Kiosk điều hành -- hợp đồng TƯƠNG PHẢN của vùng điều khiển (REQ-KIOSK-010,
// REQ-UI-006 cho ma trận 3 viewport).
//
// Vì sao có file này: kiosk là màn TỐI duy nhất trong một ứng dụng shell SÁNG.
// Lớp nền chung trong ui.css đặt cho MỌI select `background:#fff!important`;
// select chọn PO của kiosk vẫn giữ `color` sáng, nên bộ chọn ra CHỮ TRẮNG TRÊN
// NỀN TRẮNG -- đo được 1.16:1, người dùng báo "không đọc được gì".
//
// NEGATIVE PROOF -- mỗi bài dưới đây đỏ khi một thứ cụ thể bị bỏ:
//   * po_select_is_not_the_light_shell_surface
//       -> đỏ nếu bỏ `!important` ở `.kiosk-display .kiosk-po-pick select`
//          (nền quay về #fff, tỉ lệ tụt về ~1.16:1).
//   * option_list_is_dark          -> đỏ nếu bỏ luật <option> hoặc color-scheme:dark.
//   * every_control_state          -> đỏ nếu một state (hover/focus/disabled) rơi khỏi token.
//   * buttons_stay_legible         -> đỏ nếu "Làm mới"/"Thoát" mất bề mặt token.
//   * whole_screen_meets_AA        -> đỏ nếu BẤT KỲ chữ nào trên kiosk tụt dưới 4.5:1,
//                                     ở cả 1920x1080, 1366x768 và mobile. Cũng đỏ nếu
//                                     luật .sr-only bị xoá: nhãn "Chọn Production Order"
//                                     hiện lại ở kích thước thật, ~2.2:1 trên header tối.
//
// Đo bằng getComputedStyle chứ không so ảnh: giá trị màu viết trong ui.css
// thường là giá trị CHẾT (5 lớp chuẩn hoá ghi đè nhau), nên chỉ con số
// computed mới nói được màu đang chạy là màu nào.

const AA = 4.5;                                  // WCAG 2.1 AA, chữ thường
const PO_A = { id: 6126, code: '6126', product: 'Lộ trình sản xuất NEWARK ARM CHAIR', status: 'IN_PROGRESS', planned_quantity: 500 };
const PO_B = { id: 111, code: '111', product: 'Thùng rác E10GRE & SMR10GRE', status: 'IN_PROGRESS', planned_quantity: 300 };

function task(i) {
  return {
    po_id: PO_A.id, po_code: PO_A.code,
    operation_id: 1000 + i, operation_code: `OP-${String(i).padStart(2, '0')}`,
    operation_name: `Công đoạn ${i}`, operation_status: 'IN_PROGRESS',
    day_state: i % 3 === 0 ? 'RUNNING' : 'UPDATED',
    open_session_count: i % 3 === 0 ? 1 : 0,
    planned_quantity: 500, total_good_qty: 40 + i, day_good_qty: 10 + i,
    day_defect_qty: i % 4 === 0 ? 2 : 0, day_rework_qty: 0,
    active_workers: [{ employee_id: i, name: `Thợ ${i}` }],
  };
}

function event(id, extra = {}) {
  return {
    id, event_type: 'GOOD_QUANTITY_RECORDED', category: 'QUANTITY',
    occurred_at: new Date().toISOString(), actor_name: 'Lê Văn Lý', actor_kind: 'PERSON',
    po_id: PO_A.id, po_code: PO_A.code, operation_id: 1001,
    operation_code: 'OP-01', operation_name: 'Chấn thân vỏ',
    operation_done_qty: 120, operation_plan_qty: 120,
    session_id: 9, title: 'Ghi nhận sản lượng đạt', description: '',
    quantity_delta: 24, source: 'NATIVE', ...extra,
  };
}

async function mockKiosk(page) {
  const tasks = Array.from({ length: 12 }, (_, i) => task(i + 1));
  await page.route('**/api/kiosk-board?*', route => route.fulfill({
    json: {
      ok: true, date: '2026-09-11', context: { date: '2026-09-11' },
      production_order: PO_A,
      po_options: [
        { ...PO_A, open_sessions: 3, operation_count: tasks.length },
        { ...PO_B, open_sessions: 1, operation_count: 4 },
      ],
      kpis: {
        day_good_qty: 210, day_defect_qty: 4, day_rework_qty: 1,
        open_session_count: 3, active_worker_count: 3,
        operation_count: tasks.length, planned_quantity: 500,
      },
      tasks, sessions: [],
    },
  }));
  await page.route('**/api/kiosk-board/activity?*', route => route.fulfill({
    json: {
      ok: true, po_id: PO_A.id, events: [event(1)],
      other_events: [event(99, { po_id: PO_B.id, po_code: PO_B.code })], latest_id: 1,
    },
  }));
}

async function openKiosk(page, width = 1920, height = 1080) {
  await mockKiosk(page);
  await page.setViewportSize({ width, height });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto(`/app?page=daily-dashboard-kiosk&date=2026-09-11&po_id=${PO_A.id}`);
  await expect(page.locator('#kioskRoot')).toBeVisible();
  await expect(page.locator('#kioskPoSelect option').first()).toHaveCount(1);
}

/* ------------------------------------------------------------------ helpers */

/** Hàm tương phản WCAG + nền HIỆU DỤNG (đi ngược cây tới nền đục đầu tiên).
    Cùng một bản cài trong trang để test và scan dùng chung một phép đo. */
const INSTALL = () => {
  const lum = (r, g, b) => {
    const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  };
  const parse = c => {
    const m = String(c).match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(',').map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1,
  });
  const effBg = el => {
    let acc = null, n = el;
    while (n && n.nodeType === 1) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) acc = acc ? over(acc, c) : c;
      if (acc && acc.a >= 1) return acc;
      n = n.parentElement;
    }
    return acc || { r: 255, g: 255, b: 255, a: 1 };
  };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  window.__kc = {
    parse, effBg, hex,
    ratio(a, b) {
      const l1 = lum(a.r, a.g, a.b), l2 = lum(b.r, b.g, b.b);
      return Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100;
    },
    /** Đọc một control: màu chữ, nền hiệu dụng, tỉ lệ. bgOf cho <option> là
        chính <select> -- popup native vẽ trên bề mặt của select. */
    read(sel, opts) {
      const bgFrom = (opts || {}).bgFrom;
      const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
      const cs = getComputedStyle(el);
      const fg0 = parse(cs.color);
      const bg = effBg(bgFrom ? el.closest(bgFrom) : el);
      const fg = fg0.a < 1 ? over(fg0, bg) : fg0;
      return {
        color: hex(fg), bg: hex(bg), ratio: this.ratio(fg, bg),
        border: cs.borderTopColor,
        outlineStyle: cs.outlineStyle, outlineColor: hex(parse(cs.outlineColor)),
        colorScheme: cs.colorScheme, boxShadow: cs.boxShadow,
      };
    },
    /** Giá trị token đã RESOLVE về hex, để so thẳng với màu computed. */
    token(name) {
      const probe = document.createElement('i');
      probe.style.color = `var(${name})`;
      document.getElementById('kioskRoot').appendChild(probe);
      const v = hex(parse(getComputedStyle(probe).color));
      probe.remove();
      return v;
    },
  };
};

/** Lớp nền chung đặt transition .14s trên select; đọc computed ngay sau
    hover/focus sẽ bắt được giá trị ĐANG chuyển, không phải giá trị đích. */
const SETTLE = 260;

async function readControl(page, sel, opts) {
  await page.evaluate(INSTALL);
  return page.evaluate(([s, o]) => window.__kc.read(s, o), [sel, opts || null]);
}

async function token(page, name) {
  await page.evaluate(INSTALL);
  return page.evaluate(n => window.__kc.token(n), name);
}

/* ------------------------------------------------------- bộ chọn Production Order */

test.describe('Bộ chọn Production Order', () => {
  test('nền KHÔNG phải bề mặt sáng của shell -- chữ trắng trên trắng là lỗi đã sửa', async ({ page }) => {
    await openKiosk(page);
    const sel = await readControl(page, '#kioskPoSelect');

    // Chính con số đã đo lúc lỗi: 1.16:1. Ngưỡng AA là 4.5.
    expect(sel.ratio).toBeGreaterThanOrEqual(AA);
    // Và nói rõ HƯỚNG: nền phải TỐI, không phải #ffffff của lớp shell sáng.
    expect(sel.bg).not.toBe('#ffffff');
    expect(sel.bg).toBe(await page.evaluate(() => window.__kc.token('--k-control-bg')));
    expect(sel.color).toBe(await page.evaluate(() => window.__kc.token('--k-control-text')));
    // Inset shadow của shell sáng (vệt trắng bên trong) phải bị tắt trên nền tối.
    expect(sel.boxShadow).toBe('none');
  });

  test('mọi option trong danh sách đọc được, không có màu gắn riêng từng option', async ({ page }) => {
    await openKiosk(page);
    // Đúng các chuỗi người dùng báo, để bài test soi vào nội dung thật.
    await expect(page.locator('#kioskPoSelect')).toContainText('6126 · Lộ trình sản xuất NEWARK ARM CHAIR');
    await expect(page.locator('#kioskPoSelect')).toContainText('111 · Thùng rác E10GRE & SMR10GRE — 1 đang làm');

    await page.evaluate(INSTALL);
    const opts = await page.evaluate(() => Array.from(document.querySelectorAll('#kioskPoSelect option'))
      .map(o => ({ text: o.textContent, inlineStyle: o.getAttribute('style') || '', ...window.__kc.read(o, { bgFrom: 'select' }) })));

    expect(opts.length).toBeGreaterThan(1);
    for (const o of opts) {
      expect(o.ratio, `option "${o.text}" ${o.color} trên ${o.bg}`).toBeGreaterThanOrEqual(AA);
      expect(o.bg).not.toBe('#ffffff');
      // Yêu cầu: theme bằng token, KHÔNG phải màu viết cứng từng option.
      expect(o.inlineStyle).not.toMatch(/color|background/i);
    }
  });

  test('popup native được ép tối bằng color-scheme, không dựa vào kế thừa màu', async ({ page }) => {
    await openKiosk(page);
    // color-scheme là lối duy nhất tác động được vào popup/mũi tên/scrollbar
    // mà CSS của trang không vẽ được -- thiếu nó thì Chromium/Safari vẫn bung
    // ra một popup sáng bất kể background của <option>.
    for (const sel of ['#kioskRoot', '#kioskPoSelect']) {
      expect((await readControl(page, sel)).colorScheme, sel).toBe('dark');
    }
    await expect(page.locator('body')).toHaveCSS('color-scheme', 'dark');
  });

  test('giữ tương phản ở CẢ rest / hover / focus / disabled', async ({ page }) => {
    await openKiosk(page);
    const states = {};
    states.rest = await readControl(page, '#kioskPoSelect');

    await page.locator('#kioskPoSelect').hover();
    await page.waitForTimeout(SETTLE);
    states.hover = await readControl(page, '#kioskPoSelect');

    await page.locator('#kioskPoSelect').focus();
    await page.waitForTimeout(SETTLE);
    states.focus = await readControl(page, '#kioskPoSelect');

    await page.evaluate(() => { document.getElementById('kioskPoSelect').disabled = true; });
    await page.waitForTimeout(SETTLE);
    states.disabled = await readControl(page, '#kioskPoSelect');

    for (const [name, s] of Object.entries(states)) {
      expect(s.ratio, `${name}: ${s.color} trên ${s.bg}`).toBeGreaterThanOrEqual(AA);
      expect(s.bg, name).not.toBe('#ffffff');
    }
    // Hover/focus phải NHÌN THẤY được là đổi, không chỉ "vẫn đọc được".
    expect(states.hover.bg).not.toBe(states.rest.bg);
    // Vòng focus phải là màu focus của KIOSK, không phải --action-primary của
    // shell sáng (lớp nền chung đặt luật :focus-visible bằng !important).
    expect(states.focus.outlineStyle).toBe('solid');
    expect(states.focus.outlineColor).toBe(await token(page, '--k-control-focus'));
  });
});

/* ----------------------------------------------------------------- nút hành động */

test('nút "Làm mới" và "Thoát" dùng cùng bề mặt token và đọc được ở mọi state', async ({ page }) => {
  await openKiosk(page);
  await expect(page.locator('#kioskRefresh')).toHaveText('Làm mới');
  await expect(page.locator('#kioskExit')).toHaveText('Thoát');

  const controlBg = await token(page, '--k-control-bg');

  for (const id of ['#kioskRefresh', '#kioskExit']) {
    const rest = await readControl(page, id);
    expect(rest.ratio, `${id} rest`).toBeGreaterThanOrEqual(AA);
    // Cùng MỘT bề mặt với select ngay bên cạnh -- đây là điều kiện làm cho
    // "select bị lớp shell ép sang trắng" không tái diễn ở nút.
    expect(rest.bg, `${id} rest bg`).toBe(controlBg);

    await page.locator(id).hover();
    await page.waitForTimeout(SETTLE);
    const hover = await readControl(page, id);
    expect(hover.ratio, `${id} hover`).toBeGreaterThanOrEqual(AA);
    expect(hover.bg, `${id} hover bg`).not.toBe(rest.bg);

    await page.evaluate(s => { document.querySelector(s).disabled = true; }, id);
    await page.waitForTimeout(SETTLE);
    const disabled = await readControl(page, id);
    expect(disabled.ratio, `${id} disabled`).toBeGreaterThanOrEqual(AA);
    await page.evaluate(s => { document.querySelector(s).disabled = false; }, id);
  }
});

/* ------------------------------------------------- quét toàn màn, 3 viewport */

const SWEEP = () => {
  const rows = [];
  for (const el of document.getElementById('kioskRoot').querySelectorAll('*')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) continue;
    // KHÔNG loại theo tên class: .sr-only chỉ thật sự ẩn khi luật của nó còn
    // tồn tại. Lọc theo HÌNH HỌC, nên nếu luật bị xoá, nhãn hiện lại ở kích
    // thước thật và rơi vào phép đo -- đó là cách lỗi này bị bắt lần đầu.
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const ownText = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3 && n.textContent.trim()).map(n => n.textContent.trim()).join(' ');
    const isControl = /^(SELECT|BUTTON|OPTION|INPUT)$/.test(el.tagName);
    if (!ownText && !isControl) continue;
    const m = window.__kc.read(el, el.tagName === 'OPTION' ? { bgFrom: 'select' } : undefined);
    rows.push({
      where: `${el.tagName}${el.id ? '#' + el.id : ''}${el.className ? '.' + String(el.className).trim().split(/\s+/).join('.') : ''}`,
      text: (ownText || el.textContent || '').trim().slice(0, 48), ...m,
    });
  }
  return rows;
};

// REQ-UI-006: 1920x1080 + 1366x768 + một cỡ mobile.
for (const [w, h, label] of [[1920, 1080, 'TV treo tường'], [1366, 768, 'laptop chuẩn'], [390, 844, 'mobile']]) {
  test(`không còn chữ nào dưới AA trên toàn màn kiosk -- ${w}x${h} (${label})`, async ({ page }) => {
    await openKiosk(page, w, h);
    await page.evaluate(INSTALL);
    const rows = await page.evaluate(SWEEP);

    expect(rows.length).toBeGreaterThan(20);          // quét thật, không quét rỗng
    const failing = rows.filter(r => r.ratio < AA)
      .map(r => `${r.ratio}:1  ${r.where}  ${r.color} trên ${r.bg}  "${r.text}"`);
    expect(failing, `dưới ${AA}:1 ở ${w}x${h}:\n` + failing.join('\n')).toEqual([]);

    // Màn treo tường không được có thanh cuộn ngang (REQ-UI-006 / khối kiosk).
    if (w >= 1366) {
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(1);
    }

    await page.screenshot({ path: `test-results/kiosk-control-contrast-${w}x${h}.png`, fullPage: w < 800 });
  });
}

// Ảnh riêng cho vùng điều khiển: bằng chứng trực quan kèm số đo ở trên.
test('ảnh chụp vùng điều khiển kiosk (bằng chứng trực quan)', async ({ page }) => {
  await openKiosk(page);
  await page.locator('.kiosk-header').screenshot({ path: 'test-results/kiosk-control-header-1920.png' });
  await page.locator('.kiosk-actions').screenshot({ path: 'test-results/kiosk-control-actions-1920.png' });
});
