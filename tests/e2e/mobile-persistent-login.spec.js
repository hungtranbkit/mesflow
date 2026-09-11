// Đăng nhập phải sống sót những gì ĐIỆN THOẠI làm với một tab, không chỉ
// những gì máy bàn làm.
//
// Vì sao cần một bộ riêng bên cạnh persistent-login.spec.js: bộ đó chạy
// Chromium mặc định, trên máy bàn, nơi tiến trình trình duyệt gần như không
// bao giờ chết. iOS thì ngược lại — Safari thu hồi tab nền liên tục, và khi
// tab bị thu hồi thì MỌI cookie không có Expires/Max-Age biến mất cùng nó.
// Đó chính là triệu chứng "trên điện thoại cứ bị văng về màn đăng nhập" trong
// khi máy bàn vẫn qua. Một bộ test chỉ chạy máy bàn KHÔNG BAO GIỜ bắt được lỗi
// này, nên ở đây dùng WebKit thật (cùng engine với Safari iOS) và device
// descriptor iPhone thật, chứ không phải chỉ đổi kích thước khung nhìn.
const { test, expect, devices } = require('@playwright/test');
const { webkit } = require('playwright');

const IPHONE = devices['iPhone 13'];
const BASE = process.env.MESFLOW_BASE_URL || 'http://127.0.0.1:8080';
const USER = { username: 'admin', password: 'Admin@123456' };

// Vài màn hình đại diện, mỗi màn là một ĐIỀU HƯỚNG THẬT (deep link `?page=`),
// giống hệt việc mở lại bookmark trên điện thoại chứ không phải chuyển tab
// trong bộ nhớ.
const SCREENS = ['overview', 'production-orders', 'session-management', 'employees', 'tutorials'];

let browser;
test.beforeAll(async () => { browser = await webkit.launch(); });
test.afterAll(async () => { await browser?.close(); });

const phone = storageState => browser.newContext({ ...IPHONE, baseURL: BASE, storageState });

/** Đăng nhập qua ĐÚNG form người dùng bấm, không phải POST thẳng vào API.
 *  `?noauto=1` tắt auto-login của lane test — nếu không, test sẽ đo cookie do
 *  một đường đăng nhập khác phát ra chứ không phải đường thật. */
async function loginOnPhone(page) {
  await page.goto('/login?noauto=1');
  await page.locator('#username').fill(USER.username);
  await page.locator('#password').fill(USER.password);
  await page.locator('#loginForm button[type=submit]').click();
  await page.waitForURL(/\/app/, { timeout: 20000 });
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 20000 });
}

const sessionCookie = async ctx => (await ctx.cookies()).find(c => c.name === 'session');

test('iPhone: cookie đăng nhập có hạn thật, không chết theo tab', async () => {
  const ctx = await phone();
  const page = await ctx.newPage();
  await loginOnPhone(page);

  const c = await sessionCookie(ctx);
  expect(c, 'không có cookie session nào được đặt').toBeTruthy();
  // expires === -1 là cách Playwright biểu diễn cookie-theo-phiên-trình-duyệt.
  // Đây LÀ lỗi: trên iOS nó biến mất ngay khi hệ điều hành thu hồi tab.
  expect(c.expires,
    'cookie không có hạn -> iOS thu hồi tab là mất đăng nhập').toBeGreaterThan(0);
  const days = (c.expires * 1000 - Date.now()) / 86400000;
  expect(days, 'hạn cookie ngắn hơn hợp đồng 14 ngày nhàn rỗi').toBeGreaterThan(13);
  expect(c.httpOnly, 'cookie phiên phải HttpOnly').toBe(true);
  expect(c.path).toBe('/');
  await ctx.close();
});

test('iPhone: đi qua nhiều màn hình không sinh 401 và không bị đá về /login', async () => {
  const ctx = await phone();
  const page = await ctx.newPage();

  // Ghi lại MỌI phản hồi cùng origin để khi hỏng còn nói được chính xác
  // request nào đá người dùng ra, chứ không chỉ "bị văng".
  const unauthorized = [];
  const loginRedirects = [];
  page.on('response', r => {
    const url = r.url();
    if (!url.startsWith(BASE)) return;
    if (r.status() === 401) unauthorized.push(`${r.request().method()} ${url} -> 401`);
    const location = r.headers()['location'] || '';
    if (r.status() >= 300 && r.status() < 400 && location.includes('/login')) {
      loginRedirects.push(`${r.request().method()} ${url} -> ${r.status()} ${location}`);
    }
  });

  await loginOnPhone(page);
  for (const screen of SCREENS) {
    await page.goto(`/app?page=${screen}`);
    await expect(page.locator('#appLayout'), `màn ${screen} không dựng được`)
      .toBeVisible({ timeout: 20000 });
    expect(page.url(), `màn ${screen} bị đá về đăng nhập`).not.toContain('/login');
  }

  expect(unauthorized, `API trả 401 khi phiên vẫn phải còn hiệu lực:\n${unauthorized.join('\n')}`)
    .toEqual([]);
  expect(loginRedirects, `bị chuyển hướng về /login giữa chừng:\n${loginRedirects.join('\n')}`)
    .toEqual([]);
  await ctx.close();
});

test('iPhone: iOS thu hồi tab rồi mở lại -> vẫn còn đăng nhập', async () => {
  // Đây là lỗi thật trên điện thoại. Một context mới dựng từ CÙNG storage là
  // đúng cái xảy ra khi iOS giết tiến trình tab rồi người dùng mở lại app:
  // chỉ cookie CÓ HẠN mới sống qua được.
  const first = await phone();
  const page = await first.newPage();
  await loginOnPhone(page);
  const state = await first.storageState();
  await first.close();

  expect(state.cookies.some(c => c.name === 'session' && c.expires > 0),
    'không cookie phiên nào sống sót qua việc tab bị thu hồi').toBe(true);

  const reopened = await phone(state);
  const back = await reopened.newPage();
  await back.goto('/');
  // Không chỉ kiểm "có cookie": phải chứng minh cookie đó CÒN DÙNG ĐƯỢC.
  await expect(back.locator('#appLayout')).toBeVisible({ timeout: 20000 });
  expect(back.url()).toContain('/app');
  const me = await back.request.get('/api/auth/me');
  expect(me.status(), 'cookie sống sót nhưng API vẫn từ chối').toBe(200);
  await reopened.close();
});

test('iPhone: mất cookie phiên thì phản hồi đá về đăng nhập là 302 /login + API 401', async () => {
  // Chốt CHÍNH XÁC phản hồi nào đá người dùng ra, để lần sau không phải đoán:
  // điều hướng trang trả 302 tới /login, còn API trả 401 AUTH_REQUIRED và
  // net.js biến nó thành location.href='/login'.
  const ctx = await phone();
  const page = await ctx.newPage();
  await loginOnPhone(page);

  const kept = (await ctx.cookies()).filter(c => c.name !== 'session');
  await ctx.clearCookies();
  await ctx.addCookies(kept);

  const nav = await page.request.get('/', { maxRedirects: 0 });
  expect(nav.status()).toBe(302);
  expect(nav.headers()['location'] || '').toContain('/login');

  const api = await page.request.get('/api/auth/me');
  expect(api.status()).toBe(401);
  expect((await api.json()).error).toBe('AUTH_REQUIRED');
  await ctx.close();
});
