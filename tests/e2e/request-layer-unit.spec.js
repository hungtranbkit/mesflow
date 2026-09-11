// Test đơn vị cho ba hàm THUẦN của core/net.js: phân loại lỗi, backoff và
// câu báo cho người dùng. Không đụng tới mạng, không mock gì -- gọi thẳng
// từng hàm với đầu vào dựng sẵn.
//
// Chạy trong trình duyệt vì module này là script trình duyệt; nạp qua đúng
// đường app thật nạp nó (/app) chứ không addScriptTag, để bài này cũng là
// bằng chứng rằng thứ tự <script> trong app.html thật sự đưa MFNet lên
// window trước khi màn nào gọi tới.
const { test, expect } = require('@playwright/test');

async function loadLayer(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.waitForURL(/\/app/, { timeout: 20000 }).catch(() => {});
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
  await expect.poll(() => page.evaluate(() => typeof window.MFNet)).toBe('object');
}

test.describe('core/net.js — phân loại lỗi', () => {
  test('chỉ lỗi TẠM THỜI mới được thử lại, và chỉ với method an toàn', async ({ page }) => {
    await loadLayer(page);
    const verdicts = await page.evaluate(() => {
      const net = () => new TypeError('Failed to fetch');
      return {
        get503: MFNet.classify({ status: 503, method: 'GET' }),
        get500: MFNet.classify({ status: 500, method: 'GET' }),
        get429: MFNet.classify({ status: 429, method: 'GET' }),
        get408: MFNet.classify({ status: 408, method: 'GET' }),
        head502: MFNet.classify({ status: 502, method: 'HEAD' }),
        post503: MFNet.classify({ status: 503, method: 'POST' }),
        patch504: MFNet.classify({ status: 504, method: 'PATCH' }),
        delete500: MFNet.classify({ status: 500, method: 'DELETE' }),
        postIdempotent503: MFNet.classify({ status: 503, method: 'POST', idempotent: true }),
        get400: MFNet.classify({ status: 400, method: 'GET' }),
        get401: MFNet.classify({ status: 401, method: 'GET' }),
        get403: MFNet.classify({ status: 403, method: 'GET' }),
        get404: MFNet.classify({ status: 404, method: 'GET' }),
        get409: MFNet.classify({ status: 409, method: 'GET' }),
        get422: MFNet.classify({ status: 422, method: 'GET' }),
        netGet: MFNet.classify({ error: net(), method: 'GET', online: true }),
        netGetOffline: MFNet.classify({ error: net(), method: 'GET', online: false }),
        netPost: MFNet.classify({ error: net(), method: 'POST', online: true }),
        timeoutGet: MFNet.classify({ error: Object.assign(new Error('t'), { name: 'TimeoutError' }), method: 'GET' }),
        aborted: MFNet.classify({ error: Object.assign(new Error('a'), { name: 'AbortError' }), method: 'GET' }),
      };
    });

    // Tạm thời + đọc được => thử lại.
    for (const key of ['get503', 'get500', 'get429', 'get408', 'head502', 'netGet', 'netGetOffline', 'timeoutGet']) {
      expect(verdicts[key].retryable, key).toBe(true);
    }
    // Cùng mã đó nhưng là lệnh GHI => KHÔNG tự gửi lại.
    for (const key of ['post503', 'patch504', 'delete500', 'netPost']) {
      expect(verdicts[key].retryable, key).toBe(false);
    }
    // Trừ khi call site tự cam kết endpoint dedupe được.
    expect(verdicts.postIdempotent503.retryable).toBe(true);
    // Câu trả lời dứt khoát của nghiệp vụ: thử lại mù là sai, kể cả với GET.
    for (const key of ['get400', 'get401', 'get403', 'get404', 'get409', 'get422']) {
      expect(verdicts[key].retryable, key).toBe(false);
    }
    // Huỷ không phải lỗi.
    expect(verdicts.aborted).toEqual({ retryable: false, kind: 'cancelled' });

    // `kind` chọn CÂU BÁO, độc lập với việc có thử lại hay không.
    expect(verdicts.post503.kind).toBe('server');
    expect(verdicts.get429.kind).toBe('busy');
    expect(verdicts.netGet.kind).toBe('network');
    expect(verdicts.netGetOffline.kind).toBe('offline');
    expect(verdicts.timeoutGet.kind).toBe('timeout');
  });
});

test.describe('core/net.js — backoff', () => {
  test('300–500ms → 1s → 2s, jitter ±25%', async ({ page }) => {
    await loadLayer(page);
    const delays = await page.evaluate(() => ({
      mid: [1, 2, 3].map(n => MFNet.backoffDelay(n, { random: () => 0.5 })),
      low: [1, 2, 3].map(n => MFNet.backoffDelay(n, { random: () => 0 })),
      high: [1, 2, 3].map(n => MFNet.backoffDelay(n, { random: () => 1 })),
      // Quá số bậc thì giữ nguyên bậc cuối, không tăng vô hạn.
      beyond: MFNet.backoffDelay(9, { random: () => 0.5 }),
    }));
    expect(delays.mid).toEqual([400, 1000, 2000]);
    expect(delays.low).toEqual([300, 750, 1500]);
    expect(delays.high).toEqual([500, 1250, 2500]);
    expect(delays.beyond).toBe(2000);
  });

  test('Retry-After của server được tôn trọng khi nó dài hơn backoff của mình', async ({ page }) => {
    await loadLayer(page);
    const result = await page.evaluate(() => ({
      seconds: MFNet.parseRetryAfter('3'),
      httpDate: MFNet.parseRetryAfter(new Date(Date.now() + 4000).toUTCString()),
      absent: MFNet.parseRetryAfter(null),
      rubbish: MFNet.parseRetryAfter('không phải số'),
      honoured: MFNet.backoffDelay(1, { retryAfterMs: 5000, random: () => 0.5 }),
      // Retry-After ngắn hơn backoff của mình KHÔNG được kéo ta nhanh hơn --
      // nghe quá sát cũng là một cách tạo retry storm.
      floored: MFNet.backoffDelay(3, { retryAfterMs: 50, random: () => 0.5 }),
    }));
    expect(result.seconds).toBe(3000);
    expect(result.httpDate).toBeGreaterThan(3000);
    expect(result.httpDate).toBeLessThanOrEqual(4000);
    expect(result.absent).toBe(0);
    expect(result.rubbish).toBe(0);
    expect(result.honoured).toBe(5000);
    expect(result.floored).toBe(2000);
  });
});

test.describe('core/net.js — câu báo cho người dùng', () => {
  test('không bao giờ để lộ exception thô', async ({ page }) => {
    await loadLayer(page);
    const messages = await page.evaluate(() => ({
      offline: MFNet.friendlyMessage({ kind: 'offline' }),
      offlineFlag: MFNet.friendlyMessage({ kind: 'network', online: false }),
      network: MFNet.friendlyMessage({ kind: 'network' }),
      timeout: MFNet.friendlyMessage({ kind: 'timeout' }),
      busy: MFNet.friendlyMessage({ kind: 'busy', status: 429 }),
      down502: MFNet.friendlyMessage({ kind: 'server', status: 502 }),
      down503: MFNet.friendlyMessage({ kind: 'server', status: 503 }),
      down504: MFNet.friendlyMessage({ kind: 'server', status: 504 }),
      business: MFNet.friendlyMessage({ kind: 'http', status: 409, serverMessage: 'Session đã kết thúc.' }),
      silent404: MFNet.friendlyMessage({ kind: 'http', status: 404 }),
    }));
    expect(messages.offline).toBe('Mất kết nối mạng');
    expect(messages.offlineFlag).toBe('Mất kết nối mạng');
    expect(messages.network).toBe('Kết nối chưa ổn định, vui lòng thử lại');
    expect(messages.timeout).toBe('Kết nối chưa ổn định, vui lòng thử lại');
    expect(messages.busy).toBe('Kết nối chưa ổn định, vui lòng thử lại');
    expect(messages.down502).toBe('Máy chủ tạm thời không phản hồi');
    expect(messages.down503).toBe('Máy chủ tạm thời không phản hồi');
    expect(messages.down504).toBe('Máy chủ tạm thời không phản hồi');
    // Lỗi nghiệp vụ: câu của server LUÔN thắng -- phủ nó bằng câu chung là
    // làm hỏng thông tin, không phải làm đẹp lỗi.
    expect(messages.business).toBe('Session đã kết thúc.');
    // Server không nói gì thì vẫn phải là tiếng Việt, không phải chuỗi thô.
    expect(messages.silent404).toBe('Yêu cầu không thành công (HTTP 404)');
    for (const value of Object.values(messages)) {
      expect(value).not.toContain('Failed to fetch');
      expect(value).not.toContain('NetworkError');
      expect(value).not.toContain('TypeError');
    }
  });
});
