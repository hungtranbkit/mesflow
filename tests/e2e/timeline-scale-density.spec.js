// Thang giờ của timeline "Ngày công theo nhân viên": nhãn không được đè nhau.
//
// Lỗi gốc không phải chuyện CSS chật chỗ. Bản cũ chỉ lấy mốc từ BIÊN các
// khoảng ca; Dashboard theo ngày dùng một khoảng WORK 0..1440 nên ra đúng ba
// mốc [0, 1440, 1500], rồi dán nhãn bằng `minute % 1440`:
//
//   mốc    0 -> "00:00" ở   0%
//   mốc 1440 -> "00:00" ở  96%   <-- trùng tên với mốc đầu, và
//   mốc 1500 -> "01:00" ở 100%   <-- chỉ cách nhau 4% bề rộng
//
// Hai nhãn cuối chồng lên nhau ở mọi ngày, mọi bộ dữ liệu. Nay mốc dựng theo
// giờ tròn, giờ không quay vòng (24:00/25:00), và layoutTimelineScale() đo bề
// rộng thật rồi mới quyết hiện bao nhiêu nhãn.
//
// Bài test đo HÌNH HỌC (hộp bao của nhãn), không đếm số nhãn: số nhãn đúng là
// thứ được phép thay đổi theo bề rộng, còn "không đè nhau" thì không.
const { test, expect } = require('@playwright/test');

const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date());
const at = (date, h, m = 0) =>
  new Date(`${date}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+07:00`).toISOString();

const SHIFTS = [{
  id: 1, code: 'DAY', name: 'Ca ngày', active: true, anchor_start: '00:00', anchor_end: '23:59',
  cross_midnight: false, target_minutes: 480,
  intervals: [{ interval_type: 'WORK', start_minute: 0, end_minute: 1439, sort_order: 0 }],
}];

const session = (date, i, { startH, startM = 0, endH, open = false }) => ({
  session_id: i, employee_id: i, employee_code: `NV${String(i).padStart(2, '0')}`,
  employee_name: `Nhân viên ${String(i).padStart(2, '0')}`,
  session_status: open ? 'OPEN' : 'CLOSED',
  started_at: at(date, startH, startM), ended_at: open ? null : at(date, endH),
  operation_id: 101, operation_code: 'OP-A-01', operation_name: 'CHẤN BƯỚC 1',
  po_code: 'PO-111', part_code: 'PART-1', good_qty: 10, defect_qty: 0, rework_qty: 0,
  quantity_confirmed: true, closed_by_system: false, output_recorded: !open,
});

// Ba hình dữ liệu: thưa, dày, và sát hai biên ngày (00:0x và 23:5x) -- biên là
// chỗ nhãn đầu/cuối phải tự canh lề, dễ tràn ra ngoài khung nhất.
const DATASETS = {
  sparse: date => [session(date, 1, { startH: 9, endH: 10 })],
  dense: date => Array.from({ length: 18 }, (_, i) =>
    session(date, i + 1, { startH: 6 + Math.floor(i / 2), startM: (i % 2) * 30, endH: 7 + Math.floor(i / 2) })),
  edges: date => [
    session(date, 1, { startH: 0, startM: 5, endH: 1 }),
    session(date, 2, { startH: 22, startM: 55, endH: 23 }),
    session(date, 3, { startH: 23, startM: 50, open: true }),
  ],
};

async function openTimeline(page, { width, height = 900, dataset = 'dense' }) {
  const date = hcmDate();
  await page.setViewportSize({ width, height });
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.route('**/api/settings/work-shifts', r => r.fulfill({ json: { ok: true, items: SHIFTS } }));
  await page.route('**/api/dashboard/day?**', r => r.fulfill({ json: {
    ok: true, items: [], activity: [], sessions: DATASETS[dataset](date),
  } }));
  await page.goto('/app?page=dashboard&tab=people');
  await page.waitForTimeout(1500);
  await expect(page.locator('.session-timeline-panel')).toBeVisible();
  return date;
}

const readScale = page => page.evaluate(() => {
  const scale = document.querySelector('.employee-day-scale');
  if (!scale) return { present: false };
  const visible = [...scale.querySelectorAll('.shift-scale-mark')].filter(m => !m.hidden);
  const scaleBox = scale.getBoundingClientRect();
  return {
    present: true,
    scaleVisible: scaleBox.width > 0,
    scaleBox: { left: scaleBox.left, right: scaleBox.right },
    labels: visible.map(m => {
      const b = m.getBoundingClientRect();
      return { text: m.textContent.trim(), minute: Number(m.dataset.minute), left: b.left, right: b.right };
    }),
    allLabels: [...scale.querySelectorAll('.shift-scale-mark')].map(m => m.textContent.trim()),
    visibleMinutes: visible.map(m => m.dataset.minute),
    visibleGridMinutes: [...document.querySelectorAll('.employee-day-track .shift-grid-line')]
      .filter(l => !l.hidden).map(l => l.dataset.minute),
  };
});

const VIEWPORTS = [320, 390, 430, 768, 1024, 1366, 1920];

for (const width of VIEWPORTS) {
  for (const dataset of ['sparse', 'dense', 'edges']) {
    test(`@${width}px · ${dataset}: nhãn giờ không đè nhau, trang không tràn ngang`, async ({ page }) => {
      await openTimeline(page, { width, dataset });
      const s = await readScale(page);
      expect(s.present, 'không dựng được thang giờ').toBe(true);

      // Dưới 1150px .employee-day-head là display:none theo thiết kế sẵn có
      // (mỗi hàng tự cuộn ngang, một thang dùng chung sẽ lệch). Ẩn thì không
      // có gì để đè -- nhưng vẫn phải kiểm tràn ngang bên dưới.
      if (s.scaleVisible) {
        expect(s.labels.length, 'ẩn sạch nhãn thì thang giờ vô dụng').toBeGreaterThanOrEqual(2);
        const sorted = [...s.labels].sort((a, b) => a.left - b.left);
        for (let i = 1; i < sorted.length; i++) {
          const prev = sorted[i - 1], cur = sorted[i];
          expect(cur.left, `"${prev.text}" và "${cur.text}" đè nhau tại ${width}px`)
            .toBeGreaterThanOrEqual(prev.right);
        }
        // Nhãn đầu/cuối phải nằm trọn trong khung thang, không thò ra ngoài.
        expect(sorted[0].left).toBeGreaterThanOrEqual(s.scaleBox.left - 1);
        expect(sorted[sorted.length - 1].right).toBeLessThanOrEqual(s.scaleBox.right + 1);
        // Lưới đi theo đúng tập nhãn còn lại -- lệch thì thang giờ nói dối.
        expect(new Set(s.visibleGridMinutes), 'lưới và nhãn không cùng một tập mốc')
          .toEqual(new Set(s.visibleMinutes));
      }

      const overflow = await page.evaluate(() => ({
        body: document.body.scrollWidth > document.body.clientWidth,
        doc: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      }));
      expect(overflow, `tràn ngang tại ${width}px`).toEqual({ body: false, doc: false });
    });
  }
}

test('giờ không quay vòng: mốc nửa đêm là 24:00, không phải một "00:00" thứ hai', async ({ page }) => {
  await openTimeline(page, { width: 1920, dataset: 'dense' });
  const s = await readScale(page);
  // Khoảng nhìn của Dashboard theo ngày là 00:00 -> 25:00 (1440 + 60 phút đệm).
  expect(s.allLabels).toContain('00:00');
  expect(s.allLabels).toContain('24:00');
  // Đúng cái bẫy cũ: hai mốc cách nhau 24 tiếng mang cùng một nhãn.
  const midnightLabels = s.allLabels.filter(x => x === '00:00');
  expect(midnightLabels.length, `"00:00" xuất hiện ${midnightLabels.length} lần trên cùng một thang`).toBe(1);
});

test('thang giờ tính lại khi đổi bề rộng, không cần tải lại dữ liệu', async ({ page }) => {
  await openTimeline(page, { width: 1920, dataset: 'dense' });
  const wide = await readScale(page);
  expect(wide.scaleVisible).toBe(true);

  await page.setViewportSize({ width: 1200, height: 900 });
  await page.waitForTimeout(600);
  const narrow = await readScale(page);
  expect(narrow.scaleVisible).toBe(true);

  // Hẹp lại thì số nhãn phải giảm (hoặc giữ nguyên nếu vốn đã thưa) --
  // nhưng tuyệt đối không được đè nhau.
  expect(narrow.labels.length).toBeLessThanOrEqual(wide.labels.length);
  const sorted = [...narrow.labels].sort((a, b) => a.left - b.left);
  for (let i = 1; i < sorted.length; i++) {
    expect(sorted[i].left, `đè nhau sau khi thu hẹp: "${sorted[i - 1].text}" / "${sorted[i].text}"`)
      .toBeGreaterThanOrEqual(sorted[i - 1].right);
  }
});

test('thanh session vẫn nằm đúng trên thang giờ', async ({ page }) => {
  const date = await openTimeline(page, { width: 1920, dataset: 'sparse' });
  // Session duy nhất chạy 09:00 -> 10:00 trên khoảng nhìn 00:00..25:00.
  const geometry = await page.evaluate(() => {
    const scale = document.querySelector('.employee-day-scale');
    const segment = document.querySelector('.employee-session-segment');
    const track = document.querySelector('.employee-day-track');
    if (!scale || !segment || !track) return null;
    const marks = [...scale.querySelectorAll('.shift-scale-mark')];
    const pctOf = label => {
      const m = marks.find(x => x.textContent.trim() === label);
      return m ? parseFloat(m.style.left) : null;
    };
    return {
      nine: pctOf('09:00'), ten: pctOf('10:00'),
      segLeft: parseFloat(segment.style.left), segWidth: parseFloat(segment.style.width),
    };
  });
  expect(geometry, 'thiếu thanh session hoặc thang giờ').not.toBeNull();
  // Mốc và thanh dùng CÙNG một phép quy đổi phút -> phần trăm, nên phải khớp
  // tới dưới nửa phần trăm. Lệch hơn thế là thang giờ và dữ liệu đã rời nhau.
  expect(Math.abs(geometry.segLeft - geometry.nine)).toBeLessThan(0.5);
  expect(Math.abs((geometry.segLeft + geometry.segWidth) - geometry.ten)).toBeLessThan(0.5);
});
