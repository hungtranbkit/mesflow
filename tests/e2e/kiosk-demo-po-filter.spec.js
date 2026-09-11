// REQ-KIOSK-012 -- bảng mô phỏng quét QR của kiosk phải lọc được theo PO.
//
// Xưởng báo: màn mô phỏng có quá nhiều Operation nên không tìm nổi. Trước đây
// mọi công đoạn của MỌI lệnh đang chạy nằm chung một <select> và bị cắt ở
// LIMIT 500 -- phần đuôi không có đường nào chạm tới.
//
// Mock ở đây KHÔNG trả một danh sách cố định: nó thực thi đúng hợp đồng của
// server (po_id, q, include, LIMIT). Nhờ vậy bài test chứng minh được điều cần
// chứng minh -- phía client THẬT SỰ gửi phạm vi xuống server -- thay vì chỉ
// chứng minh nó biết lọc lại một mảng đã nằm sẵn trong trình duyệt.
const { test, expect } = require('@playwright/test');

const OP_LIMIT = 500;               // = DEMO_OP_LIMIT trong app/mesflow/web/kiosk.py
const PO_COUNT = 45;                // > 40: yêu cầu "PO thứ 41 vẫn phải chọn được"
const OPS_PER_PO = 45;              // 45 x 45 = 2025 OP, vượt hẳn LIMIT

const pad = n => String(n).padStart(3, '0');
const PRODUCTION_ORDERS = [
  ...Array.from({ length: PO_COUNT }, (_, i) => ({
    id: 100 + i, code: `PO-${pad(i + 1)}`, product: `Sản phẩm ${i + 1}`,
    operation_count: OPS_PER_PO,
  })),
  // PO đang chạy nhưng chưa có công đoạn nào quét được.
  { id: 900, code: 'PO-RONG', product: 'Chưa lên chuyền', operation_count: 0 },
];
const ALL_OPS = PRODUCTION_ORDERS.flatMap(po => Array.from(
  { length: po.operation_count }, (_, k) => ({
    id: po.id * 1000 + k, code: `${po.code}-OP${pad(k + 1)}`,
    name: k === 0 ? 'Cắt laser' : `Nguyên công ${k + 1}`,
    qr: `WF|OP|${po.code}-OP${pad(k + 1)}`, status: 'IN_PROGRESS',
    po_id: po.id, po_code: po.code, part_code: `${po.code}-PART`, part_name: 'Chi tiết',
  })));
const EMPLOYEES = [
  { id: 9, employee_no: 'NV-009', name: 'Thợ Chín', department: 'CNC', qr: 'WF|EMP|NV-009' },
  { id: 10, employee_no: 'NV-010', name: 'Thợ Mười', department: 'CNC', qr: 'WF|EMP|NV-010' },
];

const LAST_PO = PRODUCTION_ORDERS[PO_COUNT - 1];
const LAST_OP = `${LAST_PO.code}-OP${pad(OPS_PER_PO)}`;   // nằm sau chỗ cắt LIMIT 500

async function mockKiosk(page, calls) {
  await page.route(/\/api\/kiosk-web\/demo-data/, route => {
    const url = new URL(route.request().url());
    calls.push({
      po_id: url.searchParams.get('po_id'),
      q: url.searchParams.get('q'),
      include: url.searchParams.get('include'),
    });
    const include = (url.searchParams.get('include') || '').split(',').filter(Boolean);
    const wants = section => include.length === 0 || include.includes(section);
    const poId = url.searchParams.get('po_id') || '';
    const term = (url.searchParams.get('q') || '').trim().toLowerCase();
    const body = { ok: true, po_id: poId ? Number(poId) : null, q: term };
    if (wants('employees')) body.employees = EMPLOYEES;
    if (wants('production_orders')) {
      body.production_orders = PRODUCTION_ORDERS;
      body.production_orders_total = PRODUCTION_ORDERS.length;
    }
    if (wants('operations')) {
      let rows = ALL_OPS;
      if (poId) rows = rows.filter(op => String(op.po_id) === poId);
      if (term) rows = rows.filter(op =>
        `${op.code} ${op.name} ${op.part_code}`.toLowerCase().includes(term));
      body.operations_total = rows.length;
      body.operations = rows.slice(0, OP_LIMIT);   // server cắt, client không biết phần đuôi
    }
    route.fulfill({ json: body });
  });
  await page.route(/\/api\/kiosk-web\/heartbeat/, r => r.fulfill({ json: { ok: true } }));
}

async function openDemo(page, { url = '/kiosk', calls } = {}) {
  await mockKiosk(page, calls);
  await page.goto(url);
  await page.waitForFunction(() => !!window.MESFlowKioskDemo);
  await page.click('#demo-toggle');
  await expect(page.locator('#demo-content')).toBeVisible();
  return page;
}

const opCodes = page => page.$$eval('#demo-operation option',
  nodes => nodes.map(n => n.textContent.split(' · ')[2]));
const opCount = page => page.locator('#demo-operation option').count();
const lastCall = calls => calls[calls.length - 1];

test.describe('Kiosk demo · lọc theo Production Order', () => {
  test('mặc định là "Tất cả PO" và mọi PO đang chạy đều chọn được', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await expect(page.locator('#demo-po')).toHaveValue('');
    const options = await page.$$eval('#demo-po option', n => n.map(x => x.textContent));
    expect(options[0]).toContain('Tất cả PO');
    // PO thứ 41..45 phải nằm trong danh sách: không xếp hạng, không cắt bớt.
    expect(options.some(x => x.startsWith(LAST_PO.code))).toBe(true);
    expect(options.some(x => x.startsWith('PO-041'))).toBe(true);
    expect(lastCall(calls).po_id).toBeNull();
  });

  test('chọn PO A thì không còn công đoạn nào của PO B', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await expect.poll(() => lastCall(calls).po_id).toBe(String(PRODUCTION_ORDERS[0].id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
    const codes = await opCodes(page);
    expect(codes.every(code => code.startsWith('PO-001-'))).toBe(true);
    expect(codes.some(code => code.startsWith('PO-002-'))).toBe(false);
  });

  test('đổi PO thì toàn bộ danh sách đổi theo', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[1].id));
    await expect.poll(async () => (await opCodes(page))[0]).toContain('PO-002-');
    expect((await opCodes(page)).some(code => code.startsWith('PO-001-'))).toBe(false);
  });

  test('phạm vi đi xuống server, không lọc lại trong trình duyệt', async ({ page }) => {
    // Cột mốc thật của yêu cầu: nếu client tự lọc trên tập 500 dòng đã bị cắt
    // thì công đoạn cuối của PO cuối KHÔNG BAO GIỜ hiện ra.
    const calls = [];
    await openDemo(page, { calls });
    expect(await opCount(page)).toBe(OP_LIMIT);
    expect(await opCodes(page)).not.toContain(LAST_OP);

    await page.selectOption('#demo-po', String(LAST_PO.id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
    expect(await opCodes(page)).toContain(LAST_OP);
  });

  test('PO không có công đoạn: empty state nói rõ, không im lặng', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', '900');
    await expect(page.locator('#demo-operation-empty')).toBeVisible();
    await expect(page.locator('#demo-operation-empty')).toContainText('PO-RONG');
    await expect(page.locator('#demo-operation-count')).toHaveText('0 công đoạn');
    await expect(page.locator('#demo-operation')).toBeHidden();
    // Không còn gì để quét thì nút quét phải tắt, không để bấm vào khoảng không.
    await expect(page.locator('#demo-scan-operation')).toBeDisabled();
  });
});

test.describe('Kiosk demo · tìm công đoạn', () => {
  test('tìm theo mã, theo tên và theo Part, trong đúng PO đang chọn', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);

    await page.fill('#demo-operation-search', 'OP007');
    await expect.poll(() => opCount(page)).toBe(1);
    expect((await opCodes(page))[0]).toBe('PO-001-OP007');
    expect(lastCall(calls).q).toBe('OP007');
    expect(lastCall(calls).po_id).toBe(String(PRODUCTION_ORDERS[0].id));

    // Poll thẳng vào KẾT QUẢ, không vào số lượng: lần tìm trước cũng trả về
    // đúng 1 dòng, nên poll số lượng sẽ xanh ngay trước khi request mới về.
    await page.fill('#demo-operation-search', 'Cắt laser');
    await expect.poll(() => opCodes(page)).toEqual(['PO-001-OP001']);

    await page.fill('#demo-operation-search', 'PO-001-PART');
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
  });

  test('tìm kiếm không kéo công đoạn của PO khác vào', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[1].id));
    await page.fill('#demo-operation-search', 'OP001');
    await expect.poll(() => opCount(page)).toBe(1);
    expect((await opCodes(page))[0]).toBe('PO-002-OP001');
  });

  test('không khớp gì: empty state nêu đúng từ khoá và lối thoát', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await page.fill('#demo-operation-search', 'khong-ton-tai');
    await expect(page.locator('#demo-operation-empty')).toBeVisible();
    await expect(page.locator('#demo-operation-empty')).toContainText('khong-ton-tai');
    await expect(page.locator('#demo-operation-empty')).toContainText('Tất cả PO');
  });

  test('tìm được cả công đoạn nằm sau chỗ cắt của danh sách tổng', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.fill('#demo-operation-search', LAST_OP);
    await expect.poll(() => opCount(page)).toBe(1);
    expect((await opCodes(page))[0]).toBe(LAST_OP);
  });
});

test.describe('Kiosk demo · số kết quả và giữ lựa chọn', () => {
  test('số kết quả hiện đúng, và nói thẳng khi danh sách đang bị cắt', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    const badge = page.locator('#demo-operation-count');
    await expect(badge).toHaveText(`${OP_LIMIT}/${ALL_OPS.length} công đoạn`);
    await expect(badge).toHaveClass(/is-capped/);

    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await expect(badge).toHaveText(`${OPS_PER_PO} công đoạn`);
    await expect(badge).not.toHaveClass(/is-capped/);
  });

  test('"Tải lại danh sách" giữ nguyên PO và công đoạn đang chọn', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[2].id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
    const chosen = String(PRODUCTION_ORDERS[2].id * 1000 + 4);
    await page.selectOption('#demo-operation', chosen);

    await page.click('#demo-refresh');
    await expect.poll(() => lastCall(calls).include).toBeNull();
    await expect(page.locator('#demo-po')).toHaveValue(String(PRODUCTION_ORDERS[2].id));
    await expect(page.locator('#demo-operation')).toHaveValue(chosen);
  });

  test('tải lại trang: PO đang chọn vẫn còn', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[3].id));
    await expect.poll(() => lastCall(calls).po_id).toBe(String(PRODUCTION_ORDERS[3].id));

    await page.reload();
    await page.waitForFunction(() => !!window.MESFlowKioskDemo);
    await page.click('#demo-toggle');
    await expect(page.locator('#demo-po')).toHaveValue(String(PRODUCTION_ORDERS[3].id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
  });
});

test.describe('Kiosk demo · po_id trên URL', () => {
  test('mở /kiosk?po_id=… thì chọn đúng PO đó ngay', async ({ page }) => {
    const calls = [];
    await openDemo(page, { url: `/kiosk?po_id=${LAST_PO.id}`, calls });
    await expect(page.locator('#demo-po')).toHaveValue(String(LAST_PO.id));
    expect(calls[0].po_id).toBe(String(LAST_PO.id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);
    expect(await opCodes(page)).toContain(LAST_OP);
  });

  test('po_id rác trên URL không làm hỏng panel, rơi về "Tất cả PO"', async ({ page }) => {
    const calls = [];
    await openDemo(page, { url: '/kiosk?po_id=khong-phai-so', calls });
    await expect(page.locator('#demo-po')).toHaveValue('');
    expect(calls[0].po_id).toBeNull();   // không gửi rác xuống server
    await expect.poll(() => opCount(page)).toBe(OP_LIMIT);
  });

  test('po_id URL trỏ vào PO không còn chạy: giữ nguyên phạm vi, nói rõ lý do', async ({ page }) => {
    const calls = [];
    await openDemo(page, { url: '/kiosk?po_id=777777', calls });
    await expect(page.locator('#demo-po')).toHaveValue('777777');
    await expect(page.locator('#demo-po')).toContainText('không còn đang chạy');
    await expect(page.locator('#demo-operation-empty')).toBeVisible();
  });

  test('người dùng tự chọn PO khác thì URL không kéo ngược lại nữa', async ({ page }) => {
    const calls = [];
    await openDemo(page, { url: `/kiosk?po_id=${LAST_PO.id}`, calls });
    await expect(page.locator('#demo-po')).toHaveValue(String(LAST_PO.id));

    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await expect.poll(() => lastCall(calls).po_id).toBe(String(PRODUCTION_ORDERS[0].id));

    // Nạp lại đầy đủ -- đúng chỗ mà một mặc định "thông minh" sẽ nhảy về URL.
    await page.click('#demo-refresh');
    await expect.poll(() => lastCall(calls).include).toBeNull();
    await expect(page.locator('#demo-po')).toHaveValue(String(PRODUCTION_ORDERS[0].id));
    expect(lastCall(calls).po_id).toBe(String(PRODUCTION_ORDERS[0].id));
  });
});

test.describe('Kiosk demo · bố cục', () => {
  test('390px: không tràn ngang, các ô vẫn nằm trong panel', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 780 });
    const calls = [];
    await openDemo(page, { calls });
    await page.selectOption('#demo-po', String(PRODUCTION_ORDERS[0].id));
    await expect.poll(() => opCount(page)).toBe(OPS_PER_PO);

    const overflow = await page.evaluate(() => {
      const doc = document.documentElement;
      const panel = document.getElementById('demo-panel');
      const inside = ['demo-po', 'demo-operation-search', 'demo-operation', 'demo-operation-count']
        .map(id => document.getElementById(id).getBoundingClientRect());
      const box = panel.getBoundingClientRect();
      return {
        page: doc.scrollWidth - doc.clientWidth,
        panel: panel.scrollWidth - panel.clientWidth,
        escaped: inside.filter(r => r.left < box.left - 0.5 || r.right > box.right + 0.5).length,
      };
    });
    expect(overflow.page).toBeLessThanOrEqual(0);
    expect(overflow.panel).toBeLessThanOrEqual(0);
    expect(overflow.escaped).toBe(0);
  });

  test('bộ lọc gọn, bo tròn và có khoảng cách -- không phải ba ô dính nhau', async ({ page }) => {
    const calls = [];
    await openDemo(page, { calls });
    const style = await page.evaluate(() => {
      const scope = getComputedStyle(document.querySelector('.demo-scope'));
      const badge = getComputedStyle(document.getElementById('demo-operation-count'));
      return { radius: scope.borderRadius, gap: scope.rowGap, badgeRadius: badge.borderRadius };
    });
    expect(Number.parseFloat(style.radius)).toBeGreaterThan(0);
    expect(Number.parseFloat(style.gap)).toBeGreaterThan(0);
    expect(Number.parseFloat(style.badgeRadius)).toBeGreaterThan(0);
  });
});
