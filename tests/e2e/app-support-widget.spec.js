const {test, expect} = require('@playwright/test');

test('signed-in app keeps the support launcher across screens and omits session credentials', async ({page}) => {
  const failures = [];
  const calls = [];
  page.on('pageerror', error => failures.push(error.message));
  await page.route('**/support/chat', route => {
    calls.push({body:route.request().postDataJSON(), cookie:route.request().headers().cookie});
    return route.fulfill({json:{mode:'gateway_cached',topic_ids:['excel']}});
  });

  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app?page=overview');
  await expect(page.locator('#appLayout')).toBeVisible();
  const launcher = page.getByRole('button',{name:'Hỏi MESFlow',exact:true});
  const reportLink = page.getByRole('link',{name:'Tạo báo cáo',exact:true});
  await expect(launcher).toBeVisible();

  for (const screen of ['overview','production-orders','employee-productivity']) {
    await page.goto(`/app?page=${screen}`);
    await expect(page.locator('#appLayout')).toBeVisible();
    await expect(launcher).toBeVisible();
  }

  await launcher.click();
  const panel = page.getByRole('dialog',{name:'Hỗ trợ MESFlow'});
  await expect(panel).toBeVisible();
  await expect(reportLink).toHaveAttribute('href','/reports');
  await panel.getByRole('button',{name:'Excel',exact:true}).click();
  await expect(panel.locator('.support-message').last()).toContainText('một file Excel');
  expect(calls).toEqual([{body:{topics:['excel']},cookie:undefined}]);

  await page.setViewportSize({width:390,height:844});
  await expect(panel).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const box = await panel.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(390);
  expect(box.y + box.height).toBeLessThanOrEqual(844);
  await panel.getByRole('button',{name:'Đóng'}).click();
  await expect(panel).toBeHidden();
  await expect(launcher).toBeFocused();
  await expect(page.locator('#content')).toBeVisible();
  expect(failures).toEqual([]);
});

