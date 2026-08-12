const { test, expect } = require('@playwright/test');

test.beforeEach(async ({ page }) => {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
  await page.evaluate(() => openPage('templates', document.querySelector('[data-page="templates"]')));
  await expect(page.locator('#tplEditor')).toBeVisible();
});

test('template workspace is usable at required viewports', async ({ page }) => {
  for (const viewport of [
    { width: 1920, height: 1080, name: '1920' },
    { width: 1366, height: 768, name: '1366' },
    { width: 390, height: 844, name: '390' },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.locator('#tplNew')).toBeVisible();
    await expect(page.locator('#tplSearch')).toBeVisible();
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', viewport.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    await page.screenshot({ path: `runtime/template-after-${viewport.name}.png`, fullPage: true });
  }
});

test('template cycle time persists after save and reload', async ({ page }) => {
  const code = `TPL-E2E-${Date.now()}`;
  let templateId;
  try {
    const createdBody = await page.evaluate(async payload => { const r=await fetch('/api/templates',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});return {status:r.status,...await r.json()}; }, { code, name: 'Template kiểm tra thời gian', product: 'Sản phẩm E2E', version: '1.0', active: true });
    expect(createdBody.status, JSON.stringify(createdBody)).toBe(201);
    templateId = createdBody.id;
    const tree = await page.evaluate(async ({id,payload}) => { const r=await fetch(`/api/templates/${id}/tree`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});return {status:r.status,...await r.json()}; }, { id:templateId, payload:{
      parts: [{ key: 'part-e2e', code: 'P01', name: 'Part kiểm tra', sort_order: 0 }],
      operations: [{ part_key: 'part-e2e', code: 'OP01', name: 'Operation kiểm tra', sort_order: 0, standard_seconds_per_unit: 450 }],
      equipment: [],
    } });
    expect(tree.status, JSON.stringify(tree)).toBe(200);

    await page.evaluate(id => renderTemplates(id), templateId);
    await expect(page.locator('[data-cycle-value]')).toHaveValue('7.5');
    await expect(page.locator('[data-cycle-unit]')).toHaveValue('minute');
    for (const viewport of [
      { width: 1920, height: 1080, name: '1920' },
      { width: 1366, height: 768, name: '1366' },
      { width: 390, height: 844, name: '390' },
    ]) {
      await page.setViewportSize(viewport);
      await page.evaluate(() => closeMobileSidebar());
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
      await page.screenshot({ path: `runtime/template-populated-${viewport.name}.png`, fullPage: true });
    }
    await page.locator('[data-cycle-value]').fill('8.25');
    await page.locator('#tplSave').click();
    await expect(page.locator('#toast')).toContainText('Đã lưu Template');

    await page.reload();
    await expect(page.locator('#appLayout')).toBeVisible();
    await page.evaluate(id => renderTemplates(id), templateId);
    await expect(page.locator('[data-cycle-value]')).toHaveValue('8.25');
    await expect(page.locator('[data-cycle-unit]')).toHaveValue('minute');
  } finally {
    if (templateId) {
      const removed = await page.evaluate(async id => { const r=await fetch(`/api/templates/${id}`,{method:'DELETE'});return r.status; }, templateId);
      expect(removed).toBe(200);
    }
  }
});
