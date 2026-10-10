const {test, expect} = require('@playwright/test');

for (const viewport of [{width:1366,height:768},{width:390,height:844},{width:320,height:568}]) {
  test(`anonymous root support and secure login entry ${viewport.width}`, async ({browser, baseURL}) => {
    const context = await browser.newContext({viewport, baseURL});
    const page = await context.newPage();
    const errors = [], api = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) api.push(request.url()); });
    const response = await page.goto('/');
    expect(response.status()).toBe(200);
    await expect(page).toHaveURL(/\/$/);
    const launcher = page.getByRole('button',{name:'Hỏi MESFlow',exact:true});
    await expect(launcher).toBeVisible();
    await launcher.focus(); await page.keyboard.press('Enter');
    const panel = page.getByRole('dialog',{name:'Hỗ trợ MESFlow'});
    await expect(panel).toBeVisible();
    await expect(page.getByRole('button',{name:'Đóng hỗ trợ'})).toBeFocused();
    const expected = ['lệnh sản xuất (PO)','quét thẻ nhân viên trước','đối chiếu thời gian','phiên đang mở','một file Excel','dữ liệu mẫu cố định','quy trình thực tế','theo quyền'];
    const buttons = panel.locator('#support-topics button');
    for (let index=0; index<expected.length; index++) {
      await buttons.nth(index).click();
      await expect(panel.locator('.support-message').last()).toContainText(expected[index]);
    }
    const input = page.getByLabel('Câu hỏi của bạn');
    for (const [question, answer] of [['xuat excel','một file Excel'],['quet the QR','quét thẻ nhân viên trước'],['giá bao nhiêu?','chưa được công bố'],['contact email','chưa được công bố'],['<img src=x onerror=alert(1)>','chưa có thông tin']]) {
      await input.fill(question); await input.press('Enter');
      await expect(panel.locator('.support-message').last()).toContainText(answer);
    }
    expect(await panel.locator('img').count()).toBe(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    const box = await panel.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0); expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.y+box.height).toBeLessThanOrEqual(viewport.height);
    await input.press('Escape'); await expect(panel).toBeHidden(); await expect(launcher).toBeFocused();
    await launcher.click(); await expect(panel.locator('.support-message.user').last()).toContainText('<img');
    await page.reload(); await expect(panel).toBeHidden();
    await launcher.click(); await expect(panel.locator('.support-message')).toHaveCount(1);
    expect(api).toEqual([]); expect(errors).toEqual([]);
    await panel.getByRole('link',{name:'Dùng thử demo',exact:true}).click();
    await expect(page).toHaveURL(/\/demo$/); await expect(page.getByText('DEMO MODE',{exact:true})).toBeVisible();
    await page.goto('/');
    await page.getByRole('link',{name:'Đăng nhập',exact:true}).first().click();
    await expect(page).toHaveURL(/\/login\?noauto=1$/);
    await expect(page.locator('input[type="password"]')).toBeVisible();
    const protectedApp = await context.request.get('/app', {maxRedirects:0});
    expect(protectedApp.status()).toBe(302);
    expect(protectedApp.headers().location).toBe('/login');
    await context.close();
  });
}
