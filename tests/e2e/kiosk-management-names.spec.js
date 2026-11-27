const { test, expect } = require('@playwright/test');

const MACHINE_1 = 'fc0c33a9-2f76-424f-a256-217699b57712';
const MACHINE_2 = '0f2d2ad3-06d7-417f-a1e7-da3d2457db39';

async function boot(page) {
  const state = {
    writes: [],
    kiosks: [
      { id: 1, device_uuid: MACHINE_1, display_number: 1, device_name: 'Máy 1', status: 'ACTIVE', station_id: 11, station_code: '111', online: true, ui_state: 'READY', firmware_version: '5.6.6', last_ip: '192.168.1.254' },
      { id: 2, device_uuid: MACHINE_2, display_number: 2, device_name: 'Máy 2', status: 'ACTIVE', station_id: 11, station_code: '111', online: false },
      { id: 3, device_uuid: 'WEB-DEMO-OLD-01', display_number: null, device_name: 'Trình duyệt xưởng', status: 'ACTIVE', online: false },
      { id: 4, device_uuid: 'unapproved-legacy-01', display_number: null, device_name: 'Máy chưa duyệt', status: 'PENDING', online: false, enrollment_code: 'ABC123' },
      { id: 5, device_uuid: 'legacy-machine-100', display_number: 100, device_name: 'Máy dự phòng', status: 'ACTIVE', online: false },
    ],
  };
  await page.route('**/api/kiosk-management/overview', route => route.fulfill({ json: {
    ok: true, summary: { identity_count: 5, pending_count: 1, online_count: 1 },
    generation: { generation_id: 'test-generation', cluster_id: 'TEST' }, kiosks: state.kiosks,
  } }));
  await page.route(/\/api\/kiosk-management\/[^/]+\/events\?/, route => route.fulfill({ json: { ok: true, items: [] } }));
  await page.route(/\/api\/kiosk-management\/\d+\/name$/, route => {
    const request = route.request(), payload = request.postDataJSON();
    state.writes.push({ method: request.method(), body: payload });
    const kiosk = state.kiosks.find(k => String(k.id) === request.url().split('/').at(-2));
    kiosk.device_name = payload.device_name;
    return route.fulfill({ json: { ok: true, changed: true, item: { id: kiosk.id, device_uuid: kiosk.device_uuid, device_name: kiosk.device_name } } });
  });
  const login = await page.request.post('/api/auth/test-auto-login');
  expect(login.ok()).toBe(true);
  await page.goto('/app?page=kiosk-management');
  await expect(page.locator('.kiosk-card')).toHaveCount(5);
  return state;
}

test('stable identifiers, rename-only request, validation and timeline stay consistent', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const state = await boot(page);
  const first = page.locator(`[data-device="${MACHINE_1}"].kiosk-card`);
  await expect(first.locator('.kiosk-device-label')).toHaveText('Máy 1 · 01');
  await expect(page.locator(`[data-device="${MACHINE_2}"].kiosk-card .kiosk-device-label`)).toHaveText('Máy 2 · 02');
  await expect(page.locator('[data-device="WEB-DEMO-OLD-01"].kiosk-card .kiosk-device-label')).toHaveText('Trình duyệt xưởng');
  await expect(page.locator('[data-device="unapproved-legacy-01"].kiosk-card .kiosk-device-label')).toHaveText('Máy chưa duyệt');
  await expect(page.locator('[data-device="legacy-machine-100"].kiosk-card .kiosk-device-label')).toHaveText('Máy dự phòng · 100');
  const technical = first.locator('.kiosk-identity-details');
  await expect(technical.locator('small')).toBeHidden();
  await technical.locator('summary').click();
  await expect(technical.locator('small')).toContainText(MACHINE_1);
  await expect(technical.locator('small')).toBeVisible();
  await expect(page.locator('#kmDetail')).toContainText('Chọn một kiosk');
  await technical.locator('summary').click();

  await first.getByRole('button', { name: 'Đổi tên', exact: true }).click();
  await expect(page.locator('#kmDetail')).toContainText('Chọn một kiosk');
  await expect(page.getByRole('dialog')).toContainText('Mã máy: 01');
  await expect(page.getByLabel('Tên kiosk', { exact: true })).toBeFocused();
  await page.locator('#knName').fill('ế'.repeat(22));
  await page.locator('#knSave').click();
  await expect(page.locator('#knError')).toBeVisible();
  expect(state.writes).toHaveLength(0);
  await page.locator('#knName').fill('  Máy cắt 1  ');
  await page.locator('#knName').press('Enter');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(first.locator('.kiosk-device-label')).toHaveText('Máy cắt 1 · 01');
  expect(state.writes).toEqual([{ method: 'PATCH', body: { device_name: 'Máy cắt 1' } }]);
  expect(state.kiosks[0]).toMatchObject({ device_uuid: MACHINE_1, status: 'ACTIVE', station_id: 11 });
  await first.click();
  await expect(page.locator('#kmDetail h2')).toContainText('Máy cắt 1 · 01');

  state.kiosks.reverse();
  await page.locator('#kmReload').click();
  await expect(first.locator('.kiosk-device-label')).toHaveText('Máy cắt 1 · 01');
  const search = page.locator('#kmSearch');
  if (!(await search.isVisible())) await page.locator('details').filter({ has: search }).locator('summary').click();
  await search.fill('01');
  await expect(page.locator('.kiosk-card')).toHaveCount(1);
  await expect(page.locator('.kiosk-device-label')).toHaveText('Máy cắt 1 · 01');
  await search.fill('0002');
  await expect(page.locator('.kiosk-card')).toHaveCount(1);
  await expect(page.locator('.kiosk-device-label')).toHaveText('Máy 2 · 02');
  await search.fill('100');
  await expect(page.locator('.kiosk-card')).toHaveCount(1);
  await expect(page.locator('.kiosk-device-label')).toHaveText('Máy dự phòng · 100');
  await search.fill('111');
  await expect(page.locator('.kiosk-card')).toHaveCount(2);
  await search.fill('Máy 2');
  await expect(page.locator('.kiosk-card')).toHaveCount(1);
  expect(errors).toEqual([]);
});

test('missing and invalid numbers do not fabricate an identifier', async ({ page }) => {
  const state = await boot(page);
  const label = page.locator(`[data-device="${MACHINE_1}"].kiosk-card .kiosk-device-label`);
  for (const value of [null, 0, -1, '2', 2.5, 2147483648]) {
    state.kiosks[0].display_number = value;
    await page.locator('#kmReload').click();
    await expect(label).toHaveText('Máy 1');
  }
  state.kiosks[0].display_number = 2147483647;
  await page.locator('#kmReload').click();
  await expect(label).toHaveText('Máy 1 · 2147483647');
});

for (const [width, height] of [[1920, 1080], [1366, 768], [768, 1024], [390, 844]]) {
  test(`name and short ID fit the kiosk list and rename dialog at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height });
    await boot(page);
    await expect(page.locator('.kiosk-device-label').first()).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`kiosk-names-${width}.png`), fullPage: true });
    await page.locator('[data-rename-kiosk="2"]').click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('dialog')).toContainText('Mã máy: 02');
    await expect(page.getByLabel('Tên kiosk', { exact: true })).toHaveValue('Máy 2');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`kiosk-name-dialog-${width}.png`), fullPage: true });
    await page.locator('#knCancel').click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
}
