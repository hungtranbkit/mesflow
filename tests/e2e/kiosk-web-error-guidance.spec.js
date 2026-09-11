// Web kiosk: the operator must be told the thing they can actually act on.
//
// kiosk.js shields workers from raw backend text through workerError(). That
// shaping used to be keyed ONLY on the HTTP status, and api() overwrote
// error.action with whatever it returned — so the ERROR_HELP table, which is
// keyed by error_code, never reached the screen for an API error. Both
// ambiguous-QR cases came out as the generic 409 line:
//
//   "Công đoạn này hiện không thể bắt đầu. Kiểm tra trạng thái PO/Operation…"
//
// For a duplicated employee badge that is not just vague, it names the wrong
// object entirely, and the only useful instruction — reprint the label — was
// never shown. Ambiguity must fail loudly and usefully, never be guessed at
// (operation identity: code is display-only and may repeat across Parts).
const { test, expect } = require('@playwright/test');

// Exactly what app/mesflow/web/kiosk.py returns for these two cases.
const AMBIGUOUS_OP = {
  ok: false, error: 'AMBIGUOUS_QR', error_code: 'OP-002',
  message: 'Mã QR "WF|OP|CUT" trỏ tới 2 Operation ở các Part khác nhau',
  action: 'In lại tem QR cho Operation này (tem mới dùng mã theo id), hoặc chọn Operation trên màn hình quản lý.',
};
const AMBIGUOUS_EMP = {
  ok: false, error: 'AMBIGUOUS_QR', error_code: 'EMP-002',
  message: 'Thẻ này trỏ tới 2 nhân viên',
  action: 'Sửa mã QR của các nhân viên bị trùng trong Danh mục rồi in lại thẻ.',
};
const UNSUPPORTED = {
  ok: false, error: 'UNSUPPORTED_QR', error_code: 'SCN-002',
  message: 'Sai định dạng QR',
  action: 'QR hợp lệ phải bắt đầu bằng WF|EMP|, WF|OP| hoặc WF|OPID|.',
};

async function openKiosk(page) {
  await page.goto('/login');
  await page.request.post('/api/auth/test-auto-login');
  await page.goto('/kiosk');
  await expect(page.locator('#screen-ready')).toHaveClass(/active/);
}

/** Types the code the way a keyboard-wedge scanner does, then Enter. */
async function scanReturning(page, status, payload, code) {
  await page.route('**/api/kiosk-web/scan', r => r.fulfill({ status, json: payload }));
  await page.keyboard.type(code, { delay: 2 });
  await page.keyboard.press('Enter');
  await expect(page.locator('#screen-error')).toHaveClass(/active/, { timeout: 10000 });
  return (await page.locator('#screen-error').textContent()).replace(/\s+/g, ' ').trim();
}

test('ambiguous Operation label: tell the operator to reprint the label', async ({ page }) => {
  await openKiosk(page);
  const shown = await scanReturning(page, 409, AMBIGUOUS_OP, 'WF|OP|CUT');
  expect(shown).toContain('OP-002');
  expect(shown).toMatch(/in lại tem/i);
  // Must not send them chasing PO state — the PO is not the problem.
  expect(shown).not.toMatch(/trạng thái PO/i);
});

test('ambiguous employee badge: name the badge, not the Operation', async ({ page }) => {
  await openKiosk(page);
  const shown = await scanReturning(page, 409, AMBIGUOUS_EMP, 'WF|EMP|X');
  expect(shown).toContain('EMP-002');
  expect(shown).toMatch(/thẻ/i);
  expect(shown).toMatch(/Danh mục|in lại thẻ/i);
  expect(shown).not.toMatch(/Công đoạn này hiện không thể bắt đầu/i);
});

test('unsupported QR: say which prefixes are valid', async ({ page }) => {
  await openKiosk(page);
  const shown = await scanReturning(page, 400, UNSUPPORTED, 'HELLO-WORLD');
  expect(shown).toContain('SCN-002');
  expect(shown).toMatch(/WF\|EMP\||WF\|OP\|/);
});

test('auth failures still override the code-specific path', async ({ page }) => {
  // 401/403 stay first: a terminal with no token can do nothing at the screen,
  // so "ask an admin" outranks any per-code hint.
  await openKiosk(page);
  const shown = await scanReturning(page, 401,
    { ok: false, error: 'AUTH_REQUIRED', message: 'Authentication or kiosk token required' }, 'WF|EMP|NV001');
  expect(shown).toMatch(/chưa được cấp quyền|token/i);
});
