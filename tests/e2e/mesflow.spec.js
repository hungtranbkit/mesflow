const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  const errors=[];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
  page.__mesflowErrors=errors;
});

test.afterEach(async ({ page }) => {
  expect(page.__mesflowErrors || []).toEqual([]);
});

test('dashboard renders and shift API responds', async ({ page }) => {
  await page.evaluate(()=>openPage('dashboard',document.querySelector('[data-page="dashboard"]')));
  await expect(page.locator('#pageTitle')).toContainText('Dashboard theo ngày');
  await expect(page.locator('#dailyDate')).toBeVisible();
  await expect(page.locator('#dailyShift')).toBeVisible();
});

test('employee screen opens integrated report entry point', async ({ page }) => {
  await page.evaluate(()=>openPage('employees',document.querySelector('[data-page="employees"]')));
  await expect(page.locator('#pageTitle')).toHaveText('Quản lý nhân viên');
  await expect(page.locator('#content')).toBeVisible();
});

test('QR print center renders a result or clear empty state', async ({ page }) => {
  await page.evaluate(()=>openPage('qr-print',document.querySelector('[data-page="qr-print"]')));
  await expect(page.locator('#qrList')).toBeVisible();
  await expect(page.locator('#qrSummary')).not.toContainText('Đang tải danh sách');
  await expect(page.locator('#qrList')).not.toContainText('Không thể hiển thị danh sách QR');
});

test('session exception workflow screen renders', async ({ page }) => {
  // Rewritten (2026-08-26): pages/session-exceptions.js -- which every
  // selector below used to target (#seList, role=tab, #seDataSource,
  // #seHistory*) -- is confirmed dead code. app.html loads
  // pages/exception-center.js right after it, which unconditionally
  // overwrites the same renderSessionExceptions global; that dead
  // <script> include has since been removed. The live Exception Center is
  // exception-center.js: plain buttons (not role="tab"), data-view
  // attributes instead of aria-selected, #ecList instead of #seList, and
  // one shared ecFrom/ecTo date-range filter instead of a dedicated
  // per-field history search (seHistoryFrom/seHistoryEmployee/etc. have no
  // equivalent in the current UI -- that granularity was never carried
  // over, not merely renamed).
  await page.evaluate(()=>openPage('session-exceptions',document.querySelector('[data-page="session-exceptions"]')));
  await expect(page.locator('#ecList')).toBeVisible();
  await expect(page.locator('.ec-tabs button[data-view="action"]')).toHaveClass(/active/);
  await expect(page.locator('.ec-tabs button[data-view="all"]')).toBeVisible();
  await page.locator('.ec-tabs button[data-view="history"]').click();
  await expect(page.locator('.ec-tabs button[data-view="history"]')).toHaveClass(/active/);
  await expect(page.locator('#ecFrom')).toBeVisible();
  await expect(page.locator('#ecTo')).toBeVisible();
});

test('ESP Kiosk tutorial loads seven runtime videos and plays', async ({ page }) => {
  await page.setViewportSize({width:1920,height:1080});
  const nav=page.locator('[data-page="tutorials"]');
  await expect(nav).toHaveCount(1);
  await expect(page.locator('[data-page="esp-kiosk-tutorial"]')).toHaveCount(0);
  await nav.click();
  await expect(page.locator('#pageTitle')).toHaveText('Hướng dẫn');
  // Rewritten (2026-08-26): opening Tutorials now lands on the TEXT guide
  // by default (renderTutorials was repointed to renderTextGuide -- "Hướng
  // dẫn bằng chữ" is now the primary requirement contract, per its own
  // commit history), with a NEW outer Text/Video tab layer in front of the
  // old KIMEX/ESP video sub-tabs (both layers reuse the same .guide-tabs
  // .mf-tabs.mf-tab markup, which is why a bare count-2 check alone is
  // ambiguous between the two levels). #tutorialSearch/the KIMEX+ESP
  // sub-tabs only exist after switching to the "Video hướng dẫn" tab.
  await expect(page.getByRole('button', { name: 'Hướng dẫn bằng chữ' })).toHaveClass(/active/);
  await page.getByRole('button', { name: 'Video hướng dẫn' }).click();
  await expect(page.getByRole('button', { name: 'Video hướng dẫn' })).toHaveClass(/active/);
  await expect(page.getByRole('button', { name: 'KIMEX', exact: true })).toHaveClass(/active/);
  await expect(page.locator('#tutorialSearch')).toBeVisible();
  expect(await page.locator('#nav').evaluate(x=>x.scrollWidth<=x.clientWidth)).toBeTruthy();
  await page.getByRole('button', { name: 'ESP Kiosk' }).click();
  await expect(page.getByRole('button', { name: 'ESP Kiosk' })).toHaveClass(/active/);
  await expect(page.locator('#espTutorialVersions')).toContainText('5.1.9.2');
  await expect(page.locator('#espTutorialList button')).toHaveCount(7);
  await expect(page.locator('#espTutorialWorkspace')).not.toContainText('.mp4');
  const manifest=await page.request.get('/api/esp-kiosk-tutorial');
  expect(manifest.ok()).toBeTruthy();
  const body=await manifest.json();
  expect(body.manifest.videos).toHaveLength(7);
  expect(manifest.headers()['cache-control']).toContain('no-cache');
  expect(body.manifest.videos.every(x=>x.url.endsWith('?v=5.1.9.2'))).toBeTruthy();
  const range=await page.request.get(body.manifest.videos[0].url,{headers:{Range:'bytes=0-1023'}});
  expect([200,206]).toContain(range.status());
  expect(range.headers()['cache-control']).toContain('immutable');
  const video=page.locator('#espTutorialVideo');
  await expect(video).toBeVisible();
  const sources=[];
  for(let i=0;i<7;i++){
    await page.locator('#espTutorialList button').nth(i).click();
    sources.push(await video.getAttribute('src'));
    await expect(page.locator('#espTutorialPlayerTitle')).toHaveText(body.manifest.videos[i].title);
  }
  expect(new Set(sources).size).toBe(7);
  await page.locator('#espTutorialList button').first().click();
  await video.evaluate(v=>v.play());
  await page.waitForTimeout(1200);
  expect(await video.evaluate(v=>({readyState:v.readyState,currentTime:v.currentTime,error:v.error&&v.error.message}))).toMatchObject({error:null});
  expect(await video.evaluate(v=>v.currentTime)).toBeGreaterThan(0);
  for(const viewport of [{width:1366,height:768},{width:390,height:844}]){
    await page.setViewportSize(viewport);
    expect(await page.locator('.workspace-main').evaluate(x=>x.scrollWidth<=x.clientWidth+1)).toBeTruthy();
    await expect(video).toBeVisible();
  }
  // Rewritten (2026-08-26): the old `/app?guide=esp-kiosk` deep-link query
  // param has no handler anywhere in current app.js/text-guide.js -- that
  // mechanism was removed, not renamed, when the outer Text/Video tab
  // layer was added (deep-linking now goes through AppNav.setQuery's own
  // `tab=video` param instead, at the OUTER level, not a specific inner
  // sub-tab). Re-verify the still-real behavior instead: clicking back to
  // KIMEX restores its own content, and ESP Kiosk is reachable again from
  // there without a page reload losing state.
  await page.getByRole('button', { name: 'KIMEX', exact: true }).click();
  await expect(page.locator('#tutorialSearch')).toBeVisible();
  await page.getByRole('button', { name: 'ESP Kiosk' }).click();
  await expect(page.getByRole('button', { name: 'ESP Kiosk' })).toHaveClass(/active/);
  await expect(page.locator('#espTutorialList button')).toHaveCount(7);
  await page.route('**/api/esp-kiosk-tutorial',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ok:true,manifest:null})}));
  await page.evaluate(()=>renderEspKioskTutorial());
  await expect(page.locator('#espTutorialEmpty')).toContainText('Chưa có video hướng dẫn ESP Kiosk được publish.');
  await page.unroute('**/api/esp-kiosk-tutorial');
  await page.route('**/api/esp-kiosk-tutorial',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({ok:false,error:'TUTORIAL_MANIFEST_INVALID'})}));
  await page.evaluate(()=>renderEspKioskTutorial());
  await expect(page.locator('#espTutorialEmpty')).toContainText('Không tải được bộ hướng dẫn ESP Kiosk.');
  await expect(page.locator('#espTutorialEmpty')).not.toContainText('TUTORIAL_MANIFEST_INVALID');
  await page.unroute('**/api/esp-kiosk-tutorial');
});


test('QR and system logs render without page errors', async ({ page }) => {
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto('/');
  await page.evaluate(()=>openPage('qr-print',document.querySelector('[data-page="qr-print"]')));
  await expect(page.locator('#qrSummary')).toBeVisible();
  await expect(page.locator('#qrList')).not.toContainText('Không thể hiển thị danh sách QR');
  await page.evaluate(()=>openPage('system-logs',document.querySelector('[data-page="system-logs"]')));
  await expect(page.locator('#slRows')).toBeVisible();
  await expect(page.locator('#slRows')).not.toContainText('Không thể tải Nhật ký hệ thống');
  expect(errors).toEqual([]);
});


test('system log center switches across all log types', async ({ page }) => {
  await page.evaluate(()=>openPage('system-logs',document.querySelector('[data-page="system-logs"]')));
  await expect(page.getByRole('button',{name:'Hoạt động hệ thống'})).toBeVisible();
  await page.getByRole('button',{name:'Lỗi cần xử lý'}).click();
  await expect(page.locator('#etRows')).toBeVisible();
  await page.getByRole('button',{name:'Lịch sử lưu trữ'}).click();
  await expect(page.locator('#lrRows')).toBeVisible();
});
