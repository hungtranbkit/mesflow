const {test:base, expect, chromium, webkit} = require('@playwright/test');
const test=base.extend({
  supportEngine:['chromium',{option:true}],
  page:async({supportEngine,baseURL},use)=>{
    const browser=await ({chromium,webkit})[supportEngine].launch();
    const context=await browser.newContext({baseURL,viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    try { await use(await context.newPage()); } finally { await browser.close(); }
  }
});

async function login(page) {
  const response = await page.request.post('/api/auth/test-auto-login');
  expect(response.ok()).toBeTruthy();
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible();
}

for (const browserName of ['chromium','webkit']) {
 test.describe(`authenticated support ${browserName}`,()=>{
  test.use({supportEngine:browserName});
  test('launcher across screens, instant FAQ, explicit private AI and mobile layout',async({page})=>{
    const errors=[],calls=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/support/chat',route=>{
      calls.push({body:route.request().postDataJSON(),cookie:route.request().headers().cookie});
      return route.fulfill({json:{mode:'gateway',topic_ids:['qr','excel'],answer:'Quét thẻ và QR, sau đó xuất Excel.'}});
    });
    await login(page);
    const launch=page.locator('#support-launch'),panel=page.locator('#support-panel');
    for(const screen of ['overview','production-orders','employee-productivity']) {
      await page.goto(`/app?page=${screen}`);
      await expect(launch).toBeVisible();
      await expect(launch).toBeInViewport({ratio:1});
      await launch.tap();await expect(panel).toBeVisible();
      await page.locator('#support-close').tap();
    }
    await launch.tap();
    await expect(panel.getByRole('link',{name:'Tạo báo cáo',exact:true})).toHaveAttribute('href','/reports');
    const ms=await page.evaluate(()=>{
      const start=performance.now();document.querySelector('#support-question').value='Xuất báo cáo năng suất từng nhân viên';
      document.querySelector('#support-form').requestSubmit();return performance.now()-start;
    });
    expect(ms).toBeLessThan(500);
    await expect(panel.locator('.support-message').last()).toContainText('một file Excel');
    expect(calls).toEqual([]);
    await page.locator('#support-question').fill('Quét QR và xuất Excel');
    await page.locator('#support-form button').tap();
    await expect(panel.locator('.support-message').last()).toContainText('FAQ ·');
    await expect(page.locator('#support-ai')).toBeInViewport({ratio:1});
    expect(calls).toEqual([]);
    await page.locator('#support-ai').tap();
    await expect(panel.locator('.support-message').last()).toContainText('AI · Giải thích');
    expect(calls).toEqual([{body:{topics:['qr','excel'],intent:'guide',consent:true},cookie:undefined}]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
    const box=await panel.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x+box.width).toBeLessThanOrEqual(390);expect(box.y+box.height).toBeLessThanOrEqual(844);
    await page.locator('#support-close').tap();await expect(panel).toBeHidden();await expect(launch).toBeFocused();
    expect((await page.request.get('/api/auth/me')).status()).toBe(200);
    expect(errors).toEqual([]);
  });
  test('helper outage keeps launcher and recovery links usable',async({page})=>{
    await login(page);
    await page.route('**/support/assistant.js',route=>route.abort());
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.reload();await page.locator('#support-launch').tap();
    await expect(page.locator('#support-status')).toContainText('tạm gián đoạn');
    await expect(page.locator('#support-question')).toBeDisabled();
    await expect(page.locator('#support-panel a[href="/reports"]')).toBeVisible();
    await page.locator('#support-close').tap();await expect(page.locator('#support-launch')).toBeVisible();
    expect(errors).toEqual([]);
  });
 });
}

test('anonymous app stays protected',async({page})=>{
  const response=await page.request.get('/app',{maxRedirects:0});
  expect(response.status()).toBe(302);expect(response.headers().location).toBe('/login');
  await page.goto('/login?noauto=1');
  expect((await page.request.get('/api/auth/me')).status()).toBe(401);
  await expect(page.locator('#support-launch')).toHaveCount(0);
});
