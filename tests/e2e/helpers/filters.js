// Helper dùng chung cho bộ lọc gập lại trên mobile.
//
// Từ 2026-09-10, MFUI.filterBar() bọc các ô lọc trong một <details> và GẬP nó
// lại ở <=700px (xem core/ui.js). Playwright chỉ thao tác được với phần tử
// đang hiển thị, nên mọi spec chạm ô lọc ở viewport hẹp phải mở nó trước.
//
// Đặt ở đây thay vì chép vào từng spec: nếu ngưỡng hay cách gập đổi lần nữa,
// chỉ sửa một chỗ. Đó cũng là lý do hàm này TỰ dò trạng thái thay vì bắt spec
// truyền viewport vào -- spec không cần biết ngưỡng là bao nhiêu.
async function openFilters(page) {
  // Từ REQ-UI-023, "Tiến trình sản xuất" ở <=700px không giữ khối lọc trong
  // dòng chảy nữa: nó nằm trong một tấm mở từ nút [data-filter-sheet-trigger]
  // trên thanh sticky 48px. Ô lọc chỉ tồn tại trong DOM khi tấm đã mở, nên
  // phải mở tấm TRƯỚC rồi mới xét tới <details> bộ lọc bên trong.
  const sheet = page.locator('[data-filter-sheet-trigger]').first();
  if (await sheet.count() && await sheet.isVisible()) {
    if ((await sheet.getAttribute('aria-expanded')) !== 'true') {
      await sheet.click();
      await page.waitForFunction(
        () => document.querySelector('[data-filter-sheet-trigger]')
                ?.getAttribute('aria-expanded') === 'true',
        null, { timeout: 5000 });
    }
  }
  const summary = page.locator('.ui-filter-summary').first();
  if (!(await summary.count())) return false;          // trang không dùng filterBar
  if (!(await summary.isVisible())) return false;      // màn rộng: không gập
  const disclosure = page.locator('.ui-filter-disclosure').first();
  if (await disclosure.evaluate(node => node.open)) return true;
  await summary.click();
  await page.waitForFunction(
    () => document.querySelector('.ui-filter-disclosure')?.open === true,
    null, { timeout: 5000 });
  return true;
}

module.exports = { openFilters };
