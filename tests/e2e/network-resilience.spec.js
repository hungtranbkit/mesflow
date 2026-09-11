// Hành vi khi mạng chớp tắt: lỗi tạm thời tự hồi phục và người dùng không
// thấy gì; chỉ khi hết lượt thử lại (hoặc mất mạng thật) mới có thông báo,
// và thông báo đó là tiếng Việt chứ không phải "Failed to fetch".
//
// Mỗi bài dưới đây tương ứng một cách hỏng đã tái hiện được: rớt gói một
// nhịp, 502/503/504 kéo dài, offline thật, request bị bỏ khi đổi màn, và
// lệnh ghi gặp lỗi mạng (nơi thử lại sai sẽ ghi trùng sản lượng).
const { test, expect } = require('@playwright/test');

async function login(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

const RAW_LEAKS = ['Failed to fetch', 'NetworkError', 'TypeError', 'ERR_', 'net::'];

async function expectNoRawError(page) {
  const text = await page.locator('body').innerText();
  for (const leak of RAW_LEAKS) expect(text).not.toContain(leak);
}

// Tổng quan gọi song song hai endpoint; bài nào chỉ muốn làm hỏng một cái
// thì cái còn lại phải trả lời ngay, nếu không thời gian chờ trộn vào nhau.
async function stubProductionControl(page) {
  await page.route(/\/api\/production-control\?/, route =>
    route.fulfill({ json: { ok: true, production_orders: [], operations: [], summary: {} } }));
}

test.describe('Lỗi tạm thời tự hồi phục', () => {
  test('rớt hai nhịp đầu rồi thành công: người dùng không thấy lỗi nào', async ({ page }) => {
    await login(page);
    await stubProductionControl(page);
    let attempts = 0;
    await page.route(/\/api\/dashboard\/overview\?/, route => {
      attempts += 1;
      if (attempts <= 2) return route.abort('connectionfailed');
      return route.fulfill({ json: { ok: true, production_orders: [], operations: [] } });
    });

    await page.goto('/app?page=overview');
    await expect.poll(() => attempts, { timeout: 15000 }).toBe(3);
    // Lần thứ ba thành công -> màn vẽ bình thường, IM LẶNG: không toast,
    // không khối lỗi, không dấu vết kỹ thuật nào.
    await expect(page.locator('#ovPos')).toBeVisible();
    await expect(page.locator('.ui-error')).toHaveCount(0);
    await expectNoRawError(page);
    // Chỉ báo "Đang kết nối lại…" chỉ sống trong lúc chờ, xong thì biến mất.
    await expect.poll(() => page.evaluate(() => {
      const el = document.getElementById('netStatus');
      return !el || el.hidden;
    }), { timeout: 10000 }).toBe(true);
  });

  test('503 liên tục: thử lại đúng 3 lần rồi báo bằng tiếng Việt kèm nút Thử lại', async ({ page }) => {
    await login(page);
    await stubProductionControl(page);
    let attempts = 0;
    await page.route(/\/api\/dashboard\/overview\?/, route => {
      attempts += 1;
      return route.fulfill({ status: 503, json: { ok: false, message: 'upstream unavailable' } });
    });

    await page.goto('/app?page=overview');
    const error = page.locator('.ui-error');
    await expect(error).toBeVisible({ timeout: 20000 });
    // 1 lần đầu + 3 lần thử lại, không hơn: retry phải có trần.
    expect(attempts).toBe(4);
    await expect(error).toContainText('Máy chủ tạm thời không phản hồi');
    await expect(error.getByRole('button', { name: 'Thử lại' })).toBeVisible();
    // Câu của server ("upstream unavailable") là chữ kỹ thuật cho người vận
    // hành xưởng -- nó ở lại trong console/Error Trace, không lên màn hình.
    await expect(error).not.toContainText('upstream unavailable');
    await expectNoRawError(page);
  });

  test('mất mạng thật: báo "Mất kết nối mạng", không phải lỗi của trình duyệt', async ({ page, context }) => {
    await login(page);
    await context.setOffline(true);
    try {
      await page.evaluate(() => openPage('overview', document.querySelector('[data-page="overview"]')));
      await expect(page.locator('.ui-error')).toContainText('Mất kết nối mạng', { timeout: 20000 });
      await expect(page.locator('#netStatus')).toHaveAttribute('data-state', 'offline');
      await expectNoRawError(page);
    } finally {
      await context.setOffline(false);
    }
  });
});

test.describe('Lệnh ghi: tuyệt đối không gửi trùng', () => {
  test('POST gặp lỗi mạng KHÔNG được tự gửi lại', async ({ page }) => {
    await login(page);
    let posts = 0, gets = 0;
    await page.route('**/api/__net-probe', route => {
      if (route.request().method() === 'POST') posts += 1; else gets += 1;
      return route.abort('connectionfailed');
    });

    const result = await page.evaluate(async () => {
      const out = {};
      try { await MFNet.json('/api/__net-probe', { method: 'POST', body: '{}' }); }
      catch (e) { out.post = { message: e.message, attempts: e.attempts, kind: e.kind }; }
      try { await MFNet.json('/api/__net-probe'); }
      catch (e) { out.get = { message: e.message, attempts: e.attempts }; }
      return out;
    });

    // Cùng một URL, cùng một kiểu hỏng -- khác nhau chỉ ở method, và đó đúng
    // là ranh giới an toàn: một POST đã đi tới server rồi mới đứt đường về
    // thì gửi lại là ghi hai lần.
    expect(posts).toBe(1);
    expect(result.post.attempts).toBe(1);
    expect(gets).toBe(4);
    expect(result.get.attempts).toBe(4);
    expect(result.post.message).toBe('Kết nối chưa ổn định, vui lòng thử lại');
    for (const leak of RAW_LEAKS) expect(result.post.message).not.toContain(leak);
  });

  test('Kiosk finish: gửi lại được vì mang request_id, và gửi lại đúng id cũ', async ({ page }) => {
    await login(page);
    const bodies = [];
    await page.route('**/api/kiosk-web/finish/**', route => {
      bodies.push(JSON.parse(route.request().postData() || '{}'));
      if (bodies.length === 1) return route.abort('connectionfailed');
      return route.fulfill({ json: { ok: true, idempotent_replay: true } });
    });

    const result = await page.evaluate(() => MFNet.json('/api/kiosk-web/finish/1', {
      idempotent: true, method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ good_qty: 5, defect_qty: 0, rework_qty: 0, request_id: 'DEV-001-FINISH-1757500000000' }),
    }));

    expect(result.ok).toBe(true);
    // Đã thật sự gửi lại...
    expect(bodies).toHaveLength(2);
    // ...nhưng với ĐÚNG một request_id, nên kiosk_idempotency phía backend
    // trả lại chính bản ghi cũ thay vì cộng sản lượng lần thứ hai. Đó là
    // điều kiện duy nhất để một POST được phép tự gửi lại.
    expect(bodies[0].request_id).toBe(bodies[1].request_id);
    expect(bodies[0]).toEqual(bodies[1]);
  });
});

test.describe('Request cũ bị bỏ thì phải im lặng', () => {
  test('request bị thay chỗ (đổi bộ lọc) không resolve, không reject, không báo lỗi', async ({ page }) => {
    await login(page);
    let served = 0;
    await page.route('**/api/__net-slot', async route => {
      served += 1;
      await new Promise(r => setTimeout(r, 300));
      try { await route.fulfill({ json: { ok: true, seq: served } }); } catch (_) { /* đã bị huỷ */ }
    });

    const outcome = await page.evaluate(async () => {
      let first = 'pending';
      MFNet.json('/api/__net-slot', { slot: 'probe' }).then(() => { first = 'resolved'; }, () => { first = 'rejected'; });
      await new Promise(r => setTimeout(r, 30));
      const second = await MFNet.json('/api/__net-slot', { slot: 'probe' });
      await new Promise(r => setTimeout(r, 500));
      return { first, second };
    });

    // "pending" là cả hợp đồng: request bị chính ta bỏ không được resolve
    // (vẽ dữ liệu của bộ lọc cũ) mà cũng không được reject (mọi call site
    // đều kết thúc bằng `catch(e){hiện e.message}` -- reject là hiện lỗi).
    expect(outcome.first).toBe('pending');
    expect(outcome.second.ok).toBe(true);
    await expect(page.locator('.ui-error')).toHaveCount(0);
    await expectNoRawError(page);
  });

  test('đổi màn giữa lúc đang tải: màn mới không dính khối lỗi của màn cũ', async ({ page }) => {
    await login(page);
    await page.route(/\/api\/production-control\?/, async route => {
      await new Promise(r => setTimeout(r, 4000));
      try { await route.abort('connectionfailed'); } catch (_) { /* đã bị huỷ */ }
    });

    await page.goto('/app?page=po-control');
    await page.waitForTimeout(300);
    // Rời màn trong lúc request còn bay.
    await page.evaluate(() => openPage('production-orders', document.querySelector('[data-page="production-orders"]')));
    await expect(page.locator('#poList')).toBeVisible({ timeout: 15000 });

    // Chờ quá thời điểm request cũ hỏng: nó phải chết im lặng.
    await page.waitForTimeout(4500);
    await expect(page.locator('.ui-error')).toHaveCount(0);
    await expectNoRawError(page);
  });
});

test.describe('Màn tự làm mới giữ dữ liệu cũ', () => {
  test('nhịp làm mới hỏng không được xoá bảng đang hiển thị', async ({ page }) => {
    test.setTimeout(60000);
    await login(page);

    let failing = false;
    await page.route(/\/api\/dashboard\/overview\?/, route => {
      if (failing) return route.abort('connectionfailed');
      return route.fulfill({
        json: {
          ok: true,
          production_orders: [{ po_id: 9001, po_code: 'PO-NET-TEST', product: 'Khung nhôm', progress_percent: 42, due_date: '2026-12-31' }],
          operations: [],
        },
      });
    });
    await stubProductionControl(page);

    await page.goto('/app?page=overview');
    await expect(page.locator('#ovPos')).toContainText('PO-NET-TEST', { timeout: 15000 });

    // Từ đây mọi nhịp làm mới (15s) đều hỏng.
    failing = true;
    await page.waitForTimeout(21000);

    // Dữ liệu cũ vài giây vẫn đúng hơn nhiều so với một khối lỗi thay cho
    // cả bảng -- đây chính là hồi quy mà bài này khoá lại.
    await expect(page.locator('#ovPos')).toContainText('PO-NET-TEST');
    await expect(page.locator('.ui-error')).toHaveCount(0);
    await expectNoRawError(page);
  });
});
