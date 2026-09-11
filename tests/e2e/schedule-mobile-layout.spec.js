// "Tiến trình sản xuất" (Gantt) trên màn hẹp: không đè, không cắt chữ.
//
// Báo từ người dùng kèm ảnh thật trên iPhone: mốc thời gian và chữ OPERATION
// chồng lên card PO/Part, bar timeline vượt/che nội dung.
//
// Đo lại ở 390px, sau khi kéo timeline sang phải 300px, nguyên nhân hiện ra --
// và nó KHÔNG phải z-index:
//   * `.gantt-wrap` là lưới [cột nhãn | trục], cả hai nằm trong cùng một vùng
//     `overflow:auto`, nên kéo ngang làm CỘT NHÃN TRÔI KHỎI MÀN HÌNH
//     (đo được `.gantt-label` x = -287px). Bar còn lại lơ lửng không biết thuộc
//     Operation nào; dải Part cũng trôi mất vì nó `grid-column:1/-1`.
//   * Mỗi mốc trục in đủ `HH:mm:ss dd/MM/yyyy` -- năm mốc như vậy không nằm vừa
//     một trục 650px nên chúng cắt nhau và bị cắt cụt ở hai mép.
//   * `transform:translateX(-50%)` áp cho MỌI mốc, kể cả mốc đầu (left:0%) và
//     mốc cuối (left:100%), nên hai mốc đó bị đẩy ra ngoài vùng nhìn thấy.
//
// Bài này khoá cả ba, đo trên DOM thật ở 390/1366/1920.
const { test, expect } = require('@playwright/test');
const F = require('./helpers/hp3-fixtures');

async function openSchedule(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=production-schedule');
  await expect(page.locator('.gantt-wrap').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(600);
}

for (const [w, h, vp] of [[390, 844, '390'], [1366, 768, '1366'], [1920, 1080, '1920']]) {
  test(`Gantt: cột định danh NEO khi kéo timeline @${vp}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockAll(page);
    await openSchedule(page);

    const g = await page.evaluate(() => {
      const wrap = document.querySelector('.gantt-wrap');
      const before = {
        label: document.querySelector('.gantt-label').getBoundingClientRect().x,
        axisLabel: document.querySelector('.gantt-axis-label').getBoundingClientRect().x,
        part: document.querySelector('.gantt-part>h3>span')?.getBoundingClientRect().x,
      };
      wrap.scrollLeft = Math.max(0, wrap.scrollWidth - wrap.clientWidth);
      const wrapX = wrap.getBoundingClientRect().x;
      const after = {
        label: document.querySelector('.gantt-label').getBoundingClientRect().x,
        axisLabel: document.querySelector('.gantt-axis-label').getBoundingClientRect().x,
        part: document.querySelector('.gantt-part>h3>span')?.getBoundingClientRect().x,
      };
      const cs = getComputedStyle(document.querySelector('.gantt-label'));
      return { before, after, wrapX, scrolled: wrap.scrollLeft,
               labelPosition: cs.position,
               labelOpaque: !['rgba(0, 0, 0, 0)', 'transparent'].includes(cs.backgroundColor) };
    });

    // Kéo hết cỡ mà cột định danh vẫn phải nằm trong vùng nhìn thấy.
    expect(g.scrolled, 'timeline phải thực sự cuộn được').toBeGreaterThanOrEqual(0);
    expect(g.labelPosition, 'cột nhãn phải neo (sticky)').toBe('sticky');
    expect(g.labelOpaque, 'cột nhãn phải có nền đục, nếu không bar chạy dưới chữ').toBe(true);
    expect(Math.round(g.after.label), `tên Operation trôi mất khi kéo timeline @${vp}`)
      .toBeGreaterThanOrEqual(Math.round(g.wrapX) - 1);
    expect(Math.round(g.after.axisLabel), `nhãn "Operation" trôi mất @${vp}`)
      .toBeGreaterThanOrEqual(Math.round(g.wrapX) - 1);
    if (g.after.part !== undefined) {
      expect(Math.round(g.after.part), `tên Part trôi mất @${vp}`)
        .toBeGreaterThanOrEqual(Math.round(g.wrapX) - 1);
    }
  });

  test(`Gantt: mốc thời gian không cắt chữ, không đè nhau @${vp}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockAll(page);
    await openSchedule(page);

    const g = await page.evaluate(() => {
      const axis = document.querySelector('.gantt-axis');
      const ar = axis.getBoundingClientRect();
      const ticks = [...axis.querySelectorAll('.gantt-tick')];
      const rects = ticks.map(t => t.getBoundingClientRect());
      // Chồng nhau = hình chữ nhật của hai mốc liền kề giao nhau.
      let overlaps = 0;
      for (let i = 1; i < rects.length; i++) {
        if (rects[i].left < rects[i - 1].right - 0.5) overlaps++;
      }
      return {
        count: ticks.length,
        texts: ticks.map(t => t.textContent.trim()),
        overlaps,
        // Mốc đầu/cuối không được tràn ra ngoài trục.
        spillLeft: Math.round(ar.left - Math.min(...rects.map(r => r.left))),
        spillRight: Math.round(Math.max(...rects.map(r => r.right)) - ar.right),
      };
    });

    expect(g.count).toBeGreaterThan(1);
    expect(g.overlaps, `mốc thời gian đè nhau @${vp}: ${g.texts.join(' | ')}`).toBe(0);
    expect(g.spillLeft, `mốc đầu tràn khỏi mép trái trục @${vp}`).toBeLessThanOrEqual(1);
    expect(g.spillRight, `mốc cuối tràn khỏi mép phải trục @${vp}`).toBeLessThanOrEqual(1);
    // Nhãn gọn: giờ:phút (+ ngày khi sang ngày mới), không phải cả HH:mm:ss dd/MM/yyyy.
    for (const t of g.texts) {
      expect(t.length, `nhãn trục quá dài -> chắc chắn đè/cắt: "${t}"`).toBeLessThanOrEqual(12);
    }
  });

  test(`Gantt: không tràn ngang trang, sticky toolbar không che nội dung @${vp}`, async ({ page }) => {
    test.setTimeout(180000);
    await page.setViewportSize({ width: w, height: h });
    await F.mockAll(page);
    await openSchedule(page);
    const g = await page.evaluate(async () => {
      window.scrollTo(0, 400);
      await new Promise(r => requestAnimationFrame(r));
      const bar = document.querySelector('.schedule-sticky-toolbar');
      const br = bar.getBoundingClientRect();
      // Phần tử nội dung nào đang nằm ngay dưới thanh sticky?
      const probe = document.elementFromPoint(Math.round(br.left + br.width / 2),
                                              Math.round(br.bottom + 4));
      return {
        docOverflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
        barCoversItself: !!bar.contains(probe),
        barBottom: Math.round(br.bottom),
      };
    });
    expect(g.docOverflow, `trang tràn ngang @${vp}`).toBe(false);
    // Ngay dưới mép dưới thanh sticky phải là NỘI DUNG, không phải chính nó.
    expect(g.barCoversItself, `thanh sticky che nội dung @${vp}`).toBe(false);
  });
}
