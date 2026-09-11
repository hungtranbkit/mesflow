// Login must survive a refresh, a browser close and an app restart.
//
// The cookie carried no Max-Age/Expires before this work, so it was a
// browser-session cookie: closing the browser dropped it no matter what the
// server-side policy said. These tests exercise the real login endpoint and
// inspect the real cookie.
const { test, expect } = require('@playwright/test');

const USER = { username: 'admin', password: 'Admin@123456' };

async function login(page) {
  await page.goto('/login');
  const r = await page.request.post('/api/auth/login', { data: USER });
  expect(r.ok(), `login failed: ${r.status()}`).toBe(true);
  return r;
}
const isAuthenticated = async page => {
  const r = await page.request.get('/', { maxRedirects: 0 });
  // "/" redirects to /app when signed in, to /login when not.
  return (r.headers()['location'] || '').includes('/app');
};

test('cookie carries a lifetime, HttpOnly, Path=/ and SameSite=Lax', async ({ page }) => {
  await login(page);
  const [c] = (await page.context().cookies()).filter(x => x.name === 'session');
  expect(c, 'no session cookie was set').toBeTruthy();
  // expires === -1 is Playwright's representation of a browser-session cookie.
  expect(c.expires, 'session cookie has no expiry -> dies when the browser closes').toBeGreaterThan(0);
  const days = (c.expires * 1000 - Date.now()) / 86400000;
  expect(days).toBeGreaterThan(13);
  expect(c.httpOnly).toBe(true);
  expect(c.path).toBe('/');
  expect(String(c.sameSite).toLowerCase()).toBe('lax');
});

test('refresh keeps the session', async ({ page }) => {
  await login(page);
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 15000 });
  await page.reload();
  await expect(page.locator('#appLayout')).toBeVisible({ timeout: 15000 });
  expect(await isAuthenticated(page)).toBe(true);
});

test('closing and reopening the browser keeps the session', async ({ browser }) => {
  // A new context with the SAME storage state is what reopening a browser
  // looks like: only cookies with a real expiry survive it.
  const first = await browser.newContext();
  const page = await first.newPage();
  await login(page);
  const state = await first.storageState();
  await first.close();

  expect(state.cookies.some(c => c.name === 'session' && c.expires > 0),
    'no persistent session cookie survived the context').toBe(true);

  const second = await browser.newContext({ storageState: state });
  const reopened = await second.newPage();
  await reopened.goto('/app');
  await expect(reopened.locator('#appLayout')).toBeVisible({ timeout: 15000 });
  await second.close();
});

test('logout invalidates the cookie immediately and it cannot be replayed', async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page);
  const before = await ctx.storageState();

  await page.request.post('/api/auth/logout');
  expect(await isAuthenticated(page)).toBe(false);

  // Replay the pre-logout cookie in a fresh context: server-side clearing must
  // make the old value useless, not merely remove it from this browser.
  const replay = await browser.newContext({ storageState: before });
  const replayed = await replay.newPage();
  const r = await replayed.request.get('/', { maxRedirects: 0 });
  expect((r.headers()['location'] || '')).toContain('/login');
  await replay.close();
  await ctx.close();
});

test('a tampered cookie is refused', async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page);
  const cookies = await ctx.cookies();
  const sess = cookies.find(c => c.name === 'session');
  await ctx.clearCookies();
  // Flip a character inside the signed payload: the HMAC must reject it.
  await ctx.addCookies([{ ...sess, value: sess.value.replace(/.$/, m => (m === 'a' ? 'b' : 'a')) }]);
  const r = await page.request.get('/', { maxRedirects: 0 });
  expect((r.headers()['location'] || '')).toContain('/login');
  await ctx.close();
});
