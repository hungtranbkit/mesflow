const { chromium } = require('@playwright/test');
const fs = require('fs');

(async()=>{
  const baseURL=process.env.MESFLOW_BASE_URL||'http://127.0.0.1:8080';
  const username=process.env.MESFLOW_TUTORIAL_USERNAME||'admin';
  const password=process.env.MESFLOW_TUTORIAL_PASSWORD||'';
  const out=process.env.MESFLOW_TUTORIAL_AUTH_STATE||'tutorial-auth-state.json';
  if(!password) throw new Error('Thiếu MESFLOW_TUTORIAL_PASSWORD');

  const browser=await chromium.launch({headless:true});
  // A real page navigation is required for the login itself: the backend
  // sets the session cookie Secure (see WORKSHOP_COOKIE_SECURE), and only
  // the browser's own network stack treats 127.0.0.1/localhost as a
  // potentially-trustworthy origin for that Secure cookie over a plain
  // http:// target -- any local/demo recording target, not just
  // production over HTTPS. The verification step below deliberately does
  // NOT use context.request or page.request: both are Playwright's
  // separate, lighter API-request client, which does not get that
  // trustworthy-origin treatment either -- the cookie was captured but
  // silently never sent back on that client's own follow-up request,
  // reproduced live 2026-09-03 even from a real page-based login. An
  // in-page fetch() (page.evaluate) goes through the real browser
  // network stack instead, the same one the login form's own fetch() and
  // every subsequent openPage() XHR already relies on all through the
  // actual video recording.
  const page=await browser.newPage({baseURL});

  let last='';
  for(let attempt=1;attempt<=8;attempt++){
    // ?noauto=1 forces the real password form even when the target has
    // MESFLOW_TEST_AUTO_LOGIN=1 (e.g. demo/prodtest since 2026-09-04) --
    // without it, data-test-auto-login="1"'s client-side auto-submit races
    // this script's own fill()/click() and detaches #username mid-navigation
    // (page.fill times out waiting for a locator that just got swept away by
    // the client's own autologin redirect to /app). See REQ-AUTH-005 /
    // docs/MESFLOW_MASTER_REQUIREMENTS.md -- ?noauto=1 always renders the
    // real form regardless of the flag, so this is safe on every target,
    // autologin-enabled or not, and this script always wants the REAL
    // password login for the recorded video regardless.
    await page.goto('/login?noauto=1');
    await page.fill('#username',username);
    await page.fill('#password',password);
    const [response]=await Promise.all([
      page.waitForResponse(r=>r.url().includes('/api/auth/login'),{timeout:15000}),
      page.click('button[type="submit"]'),
    ]);
    const text=await response.text().catch(()=>'');
    last=`HTTP ${response.status()} ${text.slice(0,300)}`;
    if(response.ok()){
      const meOk=await page.evaluate(()=>fetch('/api/auth/me',{credentials:'same-origin'}).then(r=>r.ok).catch(()=>false));
      if(!meOk) throw new Error('Login thành công nhưng /api/auth/me lỗi (fetch trong trang thất bại)');
      await page.context().storageState({path:out});
      console.log(`[AUTH] Đăng nhập một lần thành công; đã lưu phiên dùng chung: ${out}`);
      await browser.close();
      return;
    }
    if(response.status()===429){
      const waitMs=Math.min(60000,5000*attempt);
      console.log(`[AUTH] Hệ thống giới hạn đăng nhập tạm thời; chờ ${Math.round(waitMs/1000)} giây rồi thử lại (${attempt}/8).`);
      await new Promise(r=>setTimeout(r,waitMs));
      continue;
    }
    throw new Error(`Login tutorial thất bại: ${last}`);
  }
  throw new Error(`Không đăng nhập được sau khi chờ giới hạn đăng nhập: ${last}`);
})().catch(e=>{console.error(e.stack||e);process.exit(1);});
