// REQ-UI-023 -- "Tiến trình sản xuất" trên điện thoại nhỏ.
//
// Báo từ người dùng thật: "scroll qua vùng filter không chạy tự nhiên", và
// "filter fixed/sticky quá cao làm viewport bên dưới rất ngắn".
//
// Đo trên DOM thật trước khi sửa (không đoán):
//   .schedule-sticky-toolbar  444.8px @390x844 · 444.8px @375x667 · 646.6px @320x568
//   --schedule-toolbar-height 445px  · 445px  · 647px   -> chính là `top` sticky
//                                                          của .schedule-po-head
//   phần màn hình còn lại cho nội dung sau khi cuộn:
//       390x844 -> 174.9px (20.7%)
//       375x667 ->  33.8px ( 5.1%)
//       320x568 -> -314.2px  (ÂM: Gantt bị đẩy hẳn ra ngoài màn hình)
//
// Nguyên nhân: trong app.js thẻ <div class="schedule-sticky-toolbar"> mở ra
// nhưng mãi tới sau .schedule-legend mới đóng, nên nó bọc CẢ .ui-filter-bar +
// 4 thẻ KPI .schedule-summary + .schedule-legend, và cả cụm đó sticky.
//
// KHÔNG phải nguyên nhân, đã loại bằng đo: không có listener
// touchstart/touchmove/wheel nào trên màn này; touch-action là `auto` ở mọi
// tầng; .gantt-wrap không lồng cuộn dọc (scrollHeight === clientHeight).
// Vuốt dọc VẪN cuộn trang -- nó chỉ không "chạy tự nhiên" vì thứ dưới ngón
// tay là một khối sticky cao gần bằng màn hình.
//
// Hợp đồng dưới đây là thứ sẽ ĐỎ nếu ai đó revert hotfix.
const { test, expect } = require('@playwright/test');
const F = require('./helpers/hp3-fixtures');

const MOBILE = [[390, 844], [375, 667], [320, 568]];
const DESKTOP = [[1366, 768], [1920, 1080]];

// Thanh sticky trên điện thoại được phép cao bao nhiêu. 44px là ngưỡng vùng
// chạm tối thiểu, 60px là trần -- cao hơn nữa thì nó lại bắt đầu ăn vào
// viewport của Gantt, đúng thứ bài này sinh ra để chặn.
const TOOLBAR_MIN = 44, TOOLBAR_MAX = 60;
// Phần màn hình phải còn lại cho nội dung, tính từ mép dưới cụm chrome sticky
// cấp trang (workspace header + thanh lọc).
const CONTENT_RATIO_MIN = 0.70;

async function open(page, w, h) {
  await page.setViewportSize({ width: w, height: h });
  await F.mockAll(page);
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app?page=production-schedule');
  await expect(page.locator('.gantt-wrap').first()).toBeVisible({ timeout: 20000 });
  await page.waitForTimeout(500);
}

// Cử chỉ CHẠM thật, dựng bằng Input.dispatchTouchEvent -- đây là thứ duy nhất
// chứng minh được touch-action / preventDefault không chặn cuộn.
// (Input.synthesizeScrollGesture với gestureSourceType:'touch' KHÔNG chạy trong
//  Chromium headless của image này: đo được scrollY=0 với cả hai chiều, trong
//  khi chuỗi touchStart/touchMove/touchEnd thủ công thì cuộn đúng. Dùng cái
//  chạy được, đừng dùng cái nghe hay hơn.)
async function touchScroll(page, { x, y, dx = 0, dy = 0, steps = 14 }) {
  const client = await page.context().newCDPSession(page);
  x = Math.round(x); y = Math.round(y);
  await client.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] });
  for (let i = 1; i <= steps; i++) {
    await client.send('Input.dispatchTouchEvent', {
      type: 'touchMove',
      touchPoints: [{ x: x - Math.round(dx * i / steps), y: y - Math.round(dy * i / steps) }],
    });
  }
  await client.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await client.detach();
  await page.waitForTimeout(300);
}

// Bộ dữ liệu mock chỉ có 2 PO và mặc định chỉ MỘT PO mở sẵn (REQ-UI-019), nên
// trang gần như không có gì để cuộn (đo được: cao 888px trên màn 844px -> chỉ
// 44px cuộn). Mở hết PO ra để bài kiểm tra cuộn có quãng đường thật -- đó cũng
// đúng là trạng thái người dùng rơi vào khi họ bấm "Mở tất cả".
async function expandAll(page) {
  await page.evaluate(() => {
    document.querySelectorAll('details.schedule-po').forEach(d => { d.open = true; });
  });
  await page.waitForTimeout(200);
  return page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight);
}

test.describe('REQ-UI-023 · mobile scroll contract', () => {
  test.use({ hasTouch: true });

  for (const [w, h] of MOBILE) {
    test(`@${w}x${h} thanh lọc sticky gọn một hàng, Gantt giữ được viewport`, async ({ page }) => {
      test.setTimeout(180000);
      await open(page, w, h);

      const m = await page.evaluate(() => {
        const tb = document.querySelector('.schedule-sticky-toolbar');
        const r = tb.getBoundingClientRect();
        return {
          vh: window.innerHeight,
          toolbarH: +r.height.toFixed(1),
          toolbarBottom: +r.bottom.toFixed(1),
          position: getComputedStyle(tb).position,
          // Thanh sticky chỉ được chứa MỘT hàng gọn; phần chi tiết phải nằm
          // ngoài dòng chảy (fixed) hoặc bị ẩn hẳn.
          // Thiếu hẳn phần tử = markup cũ (khối lọc chi tiết nằm ngay trong
          // thanh sticky). Báo bằng chuỗi nói rõ điều đó, đừng để bài nổ
          // TypeError rồi người đọc phải tự đoán.
          detailInFlow: (() => {
            const d = document.querySelector('.schedule-toolbar-detail');
            if (!d) return 'KHÔNG CÓ .schedule-toolbar-detail -- markup cũ';
            const cs = getComputedStyle(d);
            return cs.display !== 'none' && cs.position !== 'fixed';
          })(),
          cssVar: getComputedStyle(document.querySelector('.schedule-control-panel'))
                    .getPropertyValue('--schedule-toolbar-height').trim(),
        };
      });

      expect(m.position, 'thanh lọc vẫn phải sticky').toBe('sticky');
      expect(m.detailInFlow, 'khối lọc chi tiết không được nằm thường trực trong dòng chảy ở mobile').toBe(false);
      expect(m.toolbarH, `thanh lọc sticky cao ${m.toolbarH}px @${w}x${h}`)
        .toBeGreaterThanOrEqual(TOOLBAR_MIN);
      expect(m.toolbarH, `thanh lọc sticky cao ${m.toolbarH}px @${w}x${h} -- ăn hết viewport của Gantt`)
        .toBeLessThanOrEqual(TOOLBAR_MAX);
      // --schedule-toolbar-height là `top` sticky của header PO: nó phải bám
      // đúng chiều cao THẬT của thanh, nếu không header PO lại bị ghim ngoài
      // màn hình như trước.
      expect(Math.abs(parseFloat(m.cssVar) - m.toolbarH),
        `--schedule-toolbar-height (${m.cssVar}) lệch chiều cao thật (${m.toolbarH}px)`)
        .toBeLessThanOrEqual(1.5);

      // (c) Sau khi cuộn sâu, phần màn hình dưới cụm chrome sticky phải còn
      //     đủ lớn cho nội dung.
      const after = await page.evaluate(async () => {
        window.scrollTo(0, 600);
        await new Promise(r => requestAnimationFrame(r));
        await new Promise(r => setTimeout(r, 150));
        const tb = document.querySelector('.schedule-sticky-toolbar').getBoundingClientRect();
        return { ratio: +((window.innerHeight - tb.bottom) / window.innerHeight).toFixed(3),
                 px: +(window.innerHeight - tb.bottom).toFixed(1) };
      });
      expect(after.ratio, `chỉ còn ${after.px}px (${after.ratio * 100}%) cho nội dung @${w}x${h}`)
        .toBeGreaterThanOrEqual(CONTENT_RATIO_MIN);
    });

    test(`@${w}x${h} vuốt dọc bắt đầu TRÊN thanh lọc vẫn cuộn trang`, async ({ page }) => {
      test.setTimeout(180000);
      await open(page, w, h);
      const maxScroll = await expandAll(page);
      expect(maxScroll, 'trang phải có gì đó để cuộn thì bài này mới nói được điều gì')
        .toBeGreaterThan(200);
      const want = Math.min(240, maxScroll);
      await page.evaluate(() => window.scrollTo(0, 0));

      const box = await page.locator('.schedule-sticky-toolbar').boundingBox();
      const x = Math.round(box.x + box.width / 2);
      const y = Math.round(box.y + box.height / 2);

      // (a1) chạm thật
      const y0 = await page.evaluate(() => window.scrollY);
      await touchScroll(page, { x, y, dy: 300 });
      const yTouch = await page.evaluate(() => window.scrollY);
      expect(yTouch, `vuốt CHẠM bắt đầu trên thanh lọc không cuộn trang @${w}x${h}`)
        .toBeGreaterThanOrEqual(y0 + want);

      // (a2) con lăn
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.mouse.move(x, y);
      await page.mouse.wheel(0, 400);
      await page.waitForTimeout(250);
      expect(await page.evaluate(() => window.scrollY),
        `cuộn bằng con lăn trên thanh lọc bị chặn @${w}x${h}`).toBeGreaterThanOrEqual(want);

      // (a3) con trỏ kéo (pointer drag) không được nuốt sự kiện rồi đứng im
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.mouse.move(x, y);
      await page.mouse.down();
      await page.mouse.move(x, y - 200, { steps: 12 });
      await page.mouse.up();
      await page.waitForTimeout(150);
      const errs = await page.evaluate(() => window.__mfErrors || []);
      expect(errs, 'kéo con trỏ trên thanh lọc gây lỗi').toEqual([]);

      // Các control thật vẫn bấm được sau khi vuốt.
      await expect(page.locator('#scheduleFilterTrigger')).toBeVisible();
      await page.locator('#scheduleFilterTrigger').click();
      await expect(page.locator('#schedulePoFilter')).toBeVisible();
    });

    test(`@${w}x${h} tấm lọc: mở không che kín, có nút đóng, đóng trả lại viewport`, async ({ page }) => {
      test.setTimeout(180000);
      await open(page, w, h);

      await page.locator('#scheduleFilterTrigger').click();
      await expect(page.locator('#scheduleFilterSheet')).toBeVisible();
      await expect(page.locator('#schedulePoFilter')).toBeVisible();
      await expect(page.locator('#scheduleFilterClose')).toBeVisible();

      const sheet = await page.evaluate(() => {
        const s = document.querySelector('.schedule-toolbar-detail');
        const r = s.getBoundingClientRect();
        const body = document.querySelector('.schedule-sheet-body');
        return {
          coverage: +(r.height / window.innerHeight).toFixed(3),
          top: +r.top.toFixed(1),
          bottomGap: +(window.innerHeight - r.bottom).toFixed(1),
          position: getComputedStyle(s).position,
          bodyOverflow: getComputedStyle(body).overflowY,
          bodyOverscroll: getComputedStyle(body).overscrollBehaviorY,
          // Tấm mở ra KHÔNG được làm thanh sticky cao lên -- nó fixed, nằm
          // ngoài dòng chảy.
          toolbarH: +document.querySelector('.schedule-sticky-toolbar')
                       .getBoundingClientRect().height.toFixed(1),
        };
      });
      expect(sheet.position, 'tấm lọc phải nằm ngoài dòng chảy').toBe('fixed');
      expect(sheet.toolbarH, 'mở tấm lọc không được làm thanh sticky cao lên')
        .toBeLessThanOrEqual(TOOLBAR_MAX);
      expect(sheet.coverage, `tấm lọc che ${sheet.coverage * 100}% màn hình @${w}x${h}`)
        .toBeLessThanOrEqual(0.86);
      expect(sheet.bottomGap, 'phải còn thấy một dải nội dung dưới tấm lọc')
        .toBeGreaterThanOrEqual(24);
      expect(sheet.bodyOverflow, 'ruột tấm lọc phải tự cuộn được').toMatch(/auto|scroll/);
      expect(sheet.bodyOverscroll, 'cuộn trong tấm không được lan ra trang').toBe('contain');

      // Chọn xong thì tấm tự đóng -- không phải đi tìm nút đóng.
      await page.locator('#scheduleStatus').selectOption('running');
      await expect(page.locator('#scheduleFilterSheet')).toBeHidden();
      await expect(page.locator('#scheduleFilterTrigger')).toHaveAttribute('aria-expanded', 'false');
      // Và số bộ lọc đang bật hiện ngay trên nút.
      await expect(page.locator('#scheduleFilterCount')).toHaveText('1');

      // Mở lại rồi bấm Đóng.
      await page.locator('#scheduleFilterTrigger').click();
      await expect(page.locator('#scheduleFilterSheet')).toBeVisible();
      await page.locator('#scheduleFilterClose').click();
      await expect(page.locator('#scheduleFilterSheet')).toBeHidden();

      const closed = await page.evaluate(() => {
        const tb = document.querySelector('.schedule-sticky-toolbar').getBoundingClientRect();
        return +((window.innerHeight - tb.bottom) / window.innerHeight).toFixed(3);
      });
      expect(closed, 'đóng tấm lọc rồi mà viewport nội dung vẫn ngắn')
        .toBeGreaterThanOrEqual(CONTENT_RATIO_MIN);
    });

    test(`@${w}x${h} chart cuộn ngang được, trang không tràn ngang`, async ({ page }) => {
      test.setTimeout(180000);
      await open(page, w, h);

      // (d) không tràn ngang
      const ovf = await page.evaluate(() => ({
        doc: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        body: document.body.scrollWidth - document.body.clientWidth,
      }));
      expect(ovf.doc, `trang tràn ngang ${ovf.doc}px @${w}x${h}`).toBeLessThanOrEqual(1);
      expect(ovf.body, `body tràn ngang ${ovf.body}px @${w}x${h}`).toBeLessThanOrEqual(1);

      // (b) vuốt ngang trong chart -> scrollLeft tăng
      const maxScroll = await expandAll(page);
      const wrap = page.locator('.gantt-wrap').first();
      await wrap.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      const box = await wrap.boundingBox();
      const x = Math.round(box.x + box.width / 2);
      const y = Math.round(box.y + box.height / 2);
      const before = await wrap.evaluate(el => el.scrollLeft);
      await touchScroll(page, { x, y, dx: 200 });
      const afterX = await wrap.evaluate(el => el.scrollLeft);
      expect(afterX, `vuốt ngang trong chart không cuộn timeline @${w}x${h}`)
        .toBeGreaterThan(before + 20);

      // (5) vuốt DỌC bắt đầu trong chart phải đi tiếp thành cuộn trang,
      //     không bị nuốt bởi vùng cuộn lồng nhau.
      await page.evaluate(() => window.scrollTo(0, 0));
      await wrap.scrollIntoViewIfNeeded();
      await page.waitForTimeout(200);
      const box2 = await wrap.boundingBox();
      const pageY0 = await page.evaluate(() => window.scrollY);
      const want = Math.min(200, maxScroll - pageY0);
      expect(want, 'phải còn quãng đường cuộn phía dưới chart').toBeGreaterThan(100);
      await touchScroll(page, {
        x: Math.round(box2.x + box2.width / 2),
        y: Math.round(box2.y + box2.height / 2), dy: 300,
      });
      const pageY1 = await page.evaluate(() => window.scrollY);
      expect(pageY1, `vuốt dọc trong chart bị kẹt, trang không cuộn @${w}x${h}`)
        .toBeGreaterThanOrEqual(pageY0 + want);

      // Không lồng cuộn dọc trong chart -- đó là thứ gây "kẹt" trên iOS.
      const nested = await wrap.evaluate(el => el.scrollHeight - el.clientHeight);
      expect(nested, 'chart không được có thanh cuộn dọc riêng').toBeLessThanOrEqual(1);
    });
  }
});

// (e) Desktop KHÔNG đổi: thanh lọc đầy đủ nằm trong dòng chảy, không có thanh
//     gọn, không có tấm nào, header PO vẫn bám ngay dưới thanh lọc.
for (const [w, h] of DESKTOP) {
  test(`@${w}x${h} desktop giữ nguyên bộ lọc đầy đủ trong dòng chảy`, async ({ page }) => {
    test.setTimeout(180000);
    await open(page, w, h);

    await expect(page.locator('.schedule-compact-bar')).toBeHidden();
    await expect(page.locator('#schedulePoFilter')).toBeVisible();
    await expect(page.locator('#scheduleSearch')).toBeVisible();
    await expect(page.locator('#scheduleStatus')).toBeVisible();
    await expect(page.locator('#scheduleSummary')).toBeVisible();
    await expect(page.locator('.schedule-legend')).toBeVisible();
    await expect(page.locator('#scheduleExpandAll')).toBeVisible();

    const g = await page.evaluate(() => {
      const tb = document.querySelector('.schedule-sticky-toolbar');
      const d = document.querySelector('.schedule-toolbar-detail');
      return {
        toolbarPos: getComputedStyle(tb).position,
        detailPos: getComputedStyle(d).position,
        detailDisplay: getComputedStyle(d).display,
        headPos: getComputedStyle(document.querySelector('.schedule-po-head')).position,
        ovf: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    expect(g.toolbarPos).toBe('sticky');
    expect(g.detailPos, 'desktop: khối lọc phải ở trong dòng chảy như cũ').toBe('static');
    expect(g.detailDisplay).not.toBe('none');
    expect(g.headPos, 'header PO vẫn sticky').toBe('sticky');
    expect(g.ovf, `desktop tràn ngang ${g.ovf}px`).toBeLessThanOrEqual(1);

    // Tầng sticky: header PO ghim đúng ngay dưới thanh lọc. Đo bằng CÔNG THỨC
    // (`top` đã tính của header PO so với offset header + chiều cao thật của
    // thanh lọc) chứ không bằng khoảng cách hình học sau một cú scrollTo --
    // với bộ mock nhỏ, ở 1920x1080 trang không đủ dài để cuộn (maxScroll = 0)
    // nên header PO chưa bao giờ ở trạng thái ghim, và phép đo hình học ở đó
    // chỉ đo được margin 12px của thanh lọc.
    const stack = await page.evaluate(() => {
      const panel = document.querySelector('.schedule-control-panel');
      const cs = getComputedStyle(panel);
      return {
        workspaceOffset: parseFloat(cs.getPropertyValue('--schedule-workspace-offset')),
        toolbarVar: parseFloat(cs.getPropertyValue('--schedule-toolbar-height')),
        toolbarH: +document.querySelector('.schedule-sticky-toolbar')
                     .getBoundingClientRect().height.toFixed(1),
        headTop: parseFloat(getComputedStyle(document.querySelector('.schedule-po-head')).top),
        headerH: +document.querySelector('.workspace-header')
                    .getBoundingClientRect().height.toFixed(1),
      };
    });
    expect(Math.abs(stack.toolbarVar - stack.toolbarH),
      `--schedule-toolbar-height (${stack.toolbarVar}) lệch chiều cao thật (${stack.toolbarH})`)
      .toBeLessThanOrEqual(1.5);
    expect(Math.abs(stack.headTop - (stack.workspaceOffset + stack.toolbarH)),
      `header PO ghim ở ${stack.headTop}px, không khớp header+thanh lọc`)
      .toBeLessThanOrEqual(1.5);
    expect(Math.abs(stack.workspaceOffset - stack.headerH),
      'offset sticky phải bám chiều cao THẬT của workspace header').toBeLessThanOrEqual(1);
  });
}
