# Hotfix UI — "Tiến trình sản xuất" (Gantt) trên điện thoại: bộ lọc là công cụ, Gantt là nội dung

Lane phụ. **Không merge, không deploy từ lane này.** Bàn giao cho session `mesflow`.

- Nhánh: `hp3/mobile-gantt-filter-toolbar`
- Gốc: `origin/integration/daily-dashboard-test` @ `629c341`
- Route đụng tới: `/app?page=production-schedule` (`renderProductionSchedule()` trong `app.js`)
- Yêu cầu mới: **REQ-UI-023** (EN + VI + traceability đã cập nhật)

## Báo lỗi từ người dùng

> "scroll qua vùng filter không chạy tự nhiên"
> "filter đang fixed/sticky quá cao làm viewport bên dưới rất ngắn"

## Nguyên nhân gốc — đo trên DOM thật, không suy đoán

Đo bằng Playwright ở ba viewport, `getBoundingClientRect()` + `getComputedStyle()`:

| | 390x844 | 375x667 | 320x568 |
|---|---|---|---|
| `.schedule-sticky-toolbar` cao | **444.8px** | **444.8px** | **646.6px** |
| `--schedule-toolbar-height` | 445px | 445px | 647px |
| `.schedule-po-head` ghim ở `top` | 513px | 513px | **715px** (màn cao 568!) |
| `.schedule-po-head` cao | 179.3px | 179.3px | 226.5px |
| Còn lại cho nội dung sau khi cuộn | 174.9px (20.7%) | 33.8px (**5.1%**) | **−314.2px** |

Ba thứ chồng lên nhau:

1. **Thẻ `<div class="schedule-sticky-toolbar">` trong `app.js` mãi tới sau
   `.schedule-legend` mới đóng.** Nên nó bọc CẢ ba khối — `.ui-filter-bar` +
   `.schedule-summary` (4 thẻ KPI) + `.schedule-legend` — và cả cụm đó
   `position:sticky;top:68px`. Ở 320px lưới KPI `repeat(auto-fit,minmax(170px,1fr))`
   không đủ chỗ cho 2 cột nên 4 thẻ xếp dọc: riêng khối KPI đã 395.6px.
2. **Chính chiều cao đó được JS bơm vào `--schedule-toolbar-height`**
   (`syncStickyOffset()` đọc `stickyToolbar.offsetHeight`), mà biến đó là `top`
   sticky của `.schedule-po-head`. Ở 320x568 header PO bị ghim ở y=715 trên một
   màn cao 568 — tức **nằm ngoài màn hình**, và phần còn lại cho Gantt là số ÂM.
3. **`.schedule-po-head` lại sticky tiếp**, cao 179px ở 390px: lưới một cột cộng
   dòng `:after` "Kéo ngang timeline để xem đầy đủ →" — một gợi ý đọc-một-lần
   nhưng chiếm chỗ THƯỜNG TRỰC vì nó nằm trong vùng sticky.

## KHÔNG phải nguyên nhân — đã loại bằng đo

- **Không có listener nào chặn cuộn.** `grep` toàn bộ `app.js` / `core/*.js` /
  `pages/*.js`: màn này không đăng ký `touchstart` / `touchmove` / `wheel` /
  `pointermove` nào; mọi `preventDefault()` trong file đều nằm trong
  `form.onsubmit` hoặc `keydown` của phím Enter/Space/Escape.
- **`touch-action` là `auto`** ở `.schedule-sticky-toolbar`, `.gantt-wrap` và
  mọi tầng cha (chỉ `button,a,input,select,textarea` có `touch-action:manipulation`,
  đúng mục đích).
- **`.gantt-wrap` không lồng cuộn dọc**: `scrollHeight === clientHeight` (217 === 217).

Vuốt dọc VẪN cuộn trang từ trước hotfix. Nó "không chạy tự nhiên" vì thứ nằm
dưới ngón tay là một khối sticky cao gần bằng màn hình: trang cuộn mà mắt không
thấy gì đổi. Đây là lý do bản vá đi vào CÁI GÌ ĐƯỢC Ở LẠI STICKY, không phải đi
vá `touch-action` hay px lẻ.

## Cách sửa

Mobile-first, ngưỡng `<=700px` — đúng ngưỡng `FILTER_COLLAPSE_MQ` mà
`core/ui.js` đã dùng để gập bộ lọc, để hai thứ không nói hai chuyện khác nhau.

**Ở `<=700px`, chỉ MỘT hàng 49px ở lại sticky** (`.schedule-compact-bar`):

- nút `Bộ lọc` kèm huy hiệu số bộ lọc đang bật,
- một dòng tóm tắt xưởng (`3/8 PO chạy · 40 OP · 2 trễ/nguy cơ`, hoặc
  `Đang lọc · 2/8 PO · 15 OP`) — sinh từ **cùng** mảng `cached` mà 4 thẻ KPI
  đang dùng, không gọi thêm API,
- nút `↻` cập nhật.

**Khối lọc chi tiết mở thành TẤM `position:fixed`.** `fixed` không phải chi tiết
ngẫu nhiên: nó là thứ giữ `offsetHeight` của thanh sticky KHÔNG đổi khi tấm mở
ra, nên `--schedule-toolbar-height` tự đúng mà không phải cộng trừ px bằng tay ở
hai chỗ. Tấm có nút `Đóng` rõ ràng, tự cuộn bên trong
(`overflow:auto;overscroll-behavior:contain`), `max-height` dùng `svh` (có
`vh` làm fallback) và luôn chừa 72px cuối màn hình để vẫn thấy danh sách bên
dưới đổi theo lựa chọn. Tấm **tự đóng sau khi chọn xong** một giá trị lọc /
`Mở tất cả` / `Thu gọn` / `↻`; gõ vào ô **Tìm nhanh thì KHÔNG đóng** (nếu không
mỗi ký tự lại đóng mất ô đang gõ).

**Bộ lọc trong tấm không gập thêm lần nữa.** `MFUI.filterBar()` bọc các ô trong
`<details class="ui-filter-disclosure">` và `core/ui.js` gập nó ở `<=700px`;
bên trong tấm thì đó là hai lần bấm cho cùng một việc. Đặt `open=true` +
`dataset.userToggled='1'` ngay sau `innerHTML` (trước microtask của
MutationObserver bên `core/ui.js`) và ẩn `<summary>` bằng CSS trong tấm.

**Header PO gọn lại**: hai hàng thay vì ba khối xếp dọc, và dấu `▾` được đặt chỗ
rõ ràng ở cột 3. Trước đó `▾` là một `::after` viết cho header FLEX
(`flex:0 0 auto`) nhưng header này là GRID, nên nó tự rơi xuống **một hàng
riêng cao 17.16px**. Dòng gợi ý "Kéo ngang timeline" chuyển từ `:after` của
header sticky sang `<p class="gantt-scroll-hint">` thật nằm ngoài vùng sticky —
đọc một lần rồi cuộn đi mất.

**Cử chỉ**: `.gantt-wrap` thêm `overscroll-behavior:contain auto` — chặn
overscroll NGANG lan ra cử chỉ Back của iOS, vẫn để trục dọc nối tiếp lên trang.

**Desktop (>700px) không đổi**: `.schedule-compact-bar` `display:none`, khối lọc
chi tiết nằm trong dòng chảy `position:static` đúng như trước.

## Sau khi sửa — đo lại cùng cách

| | 390x844 | 375x667 | 320x568 |
|---|---|---|---|
| `.schedule-sticky-toolbar` cao | 444.8 → **49px** | 444.8 → **49px** | 646.6 → **49px** |
| `--schedule-toolbar-height` | **49px** (khớp chiều cao thật) | 49px | 49px |
| `.schedule-po-head` ghim ở `top` | 513 → **117px** | 513 → **117px** | 715 → **117px** |
| `.schedule-po-head` cao | 179.3 → **77.3px** | 179.3 → **77.3px** | 226.5 → **77.3px** |
| Còn lại dưới chrome sticky cấp trang | 331.2px (39.2%) → **727px (86.1%)** | 154.2px (23.1%) → **550px (82.5%)** | −146.6px → **451px (79.4%)** |
| Còn lại dưới CẢ header PO | 174.9px (20.7%) → **649.7px (77.0%)** | 33.8px (5.1%) → **472.7px (70.9%)** | −314.2px → **373.7px (65.8%)** |
| Tấm lọc mở che | **77.6%** | **71.7%** | **66.7%** |
| Tấm mở → thanh sticky vẫn | 49px | 49px | 49px |
| `documentElement` tràn ngang | 0px | 0px | 0px |

## Business logic giữ nguyên

`render()` / `scheduleSummary()` / `load()` không đổi cách tính; lọc theo
`#schedulePoFilter` / `#scheduleSearch` / `#scheduleStatus`, `Mở tất cả` /
`Thu gọn`, tự làm mới 15s (giữ vị trí cuộn), trạng thái URL `?po=/?q=/?opstate=`,
`MFUI.refreshError`, RBAC — tất cả như cũ.

## Hợp đồng

`tests/e2e/schedule-mobile-scroll-contract.spec.js` — 14 bài, 390x844 / 375x667 /
320x568 + desktop 1366 / 1920:

| Bài | Đo gì |
|---|---|
| thanh lọc sticky gọn một hàng | `position:sticky`, cao 44–60px, khối chi tiết không nằm trong dòng chảy, `--schedule-toolbar-height` khớp chiều cao THẬT (±1.5px), còn >=70% viewport dưới chrome sticky sau khi cuộn |
| vuốt dọc bắt đầu TRÊN thanh lọc | cử chỉ **chạm thật** (`Input.dispatchTouchEvent`) + con lăn + kéo con trỏ đều làm `window.scrollY` tăng đủ quãng; control vẫn bấm được sau đó |
| tấm lọc | `position:fixed`, che <=86% màn, còn >=24px thấy nội dung dưới, ruột tự cuộn + `overscroll-behavior:contain`, có nút Đóng, tự đóng sau khi chọn, huy hiệu số bộ lọc đúng, mở tấm không làm thanh sticky cao lên, đóng xong viewport vẫn >=70% |
| chart | vuốt ngang làm `scrollLeft` tăng; vuốt dọc trong chart đi tiếp thành cuộn trang; chart không có thanh cuộn dọc riêng; trang không tràn ngang |
| desktop 1366 / 1920 | không có hàng gọn, mọi ô lọc + KPI + chú giải hiện sẵn trong dòng chảy (`position:static`), header PO vẫn sticky và ghim đúng `header + thanh lọc`, không tràn ngang |

**Negative proof** — revert `app.js` + `ui.css` về bản gốc, chạy lại ở 390x844
(`--retries=0`): **3/4 bài mobile ĐỎ** —
`KHÔNG CÓ .schedule-toolbar-detail -- markup cũ`,
`cuộn bằng con lăn trên thanh lọc bị chặn @390x844`,
và `#scheduleFilterTrigger` không tồn tại nên bài về tấm lọc timeout.
Chạy đủ ba viewport thì 7 bài đỏ.

## Bài test có sẵn phải sửa theo (đổi contract, đúng dự tính)

- `tests/e2e/helpers/filters.js` — `openFilters()` biết mở tấm trước
  (`[data-filter-sheet-trigger]`), rồi mới tới `<details>` bên trong. Một chỗ
  duy nhất, đúng lý do helper này tồn tại.
- `tests/e2e/production-progressive-disclosure.spec.js` — file này giữ một BẢN
  CHÉP TAY của `openFilters` chỉ biết `<details>`, nên nó "mở bộ lọc" thành công
  rồi để `#scheduleSearch` / `#scheduleExpandAll` nằm trong tấm đang đóng và
  chết ở `locator.click` chứ không ở điều nó định kiểm. Đã bỏ bản chép tay,
  dùng helper chung, và gọi `openFilters()` trước MỖI lần bấm nút toolbar (vì
  tấm tự đóng sau mỗi thao tác — đó là chủ ý).

## Kết quả chạy

Trên nền `origin/integration/daily-dashboard-test` @ `b35f27b` (71.0.0.290), chạy
NỐI TIẾP (không chạy pytest song song với Playwright trên cùng một API/DB — chạy
chồng lên nhau cho ra 71 bài đỏ giả và 4 bài flaky, đã kiểm lại: chạy riêng thì
sạch):

- pytest toàn bộ: **1273 passed, 18 skipped, 1 xfailed, 0 failed**.
- Playwright toàn bộ: **438 passed, 1 failed, 2 flaky, 4 skipped**.
  - Bài đỏ duy nhất: `mesflow.spec.js › ESP Kiosk tutorial loads seven runtime
    videos and plays` — **lỗi môi trường đã biết**: fixture video ESP phải được
    dựng trên host (cần `ffmpeg`) TRƯỚC khi `compose.test.yml` khởi động. Không
    liên quan màn này.
  - 2 bài flaky: `rework-queue-card-contract.spec.js` (@390, @1920) — xanh ở
    lần chạy lại, và chạy RIÊNG với `--retries=0` thì **4/4 xanh**. Màn Hàng chờ
    sửa, không đụng tới thay đổi này.
- Nhóm bài liên quan trực tiếp, chạy `--retries=0` (không cho retry che flaky):
  `admin-list-card-consistency`, `dashboard-list-surface-contract`,
  `production-progressive-disclosure`, `schedule-mobile-layout`,
  `schedule-mobile-scroll-contract`, `production-schedule-sticky`, `gantt-shell`,
  `filter-disclosure` — **86 passed, 0 failed**.

### Một flaky có sẵn phải vá theo (test-only)

Ba helper điều hướng (`schedule-mobile-layout`, `production-progressive-disclosure`,
`dashboard-list-surface-contract`) làm `goto('/login')` rồi `goto('/app?page=…')`
ngay, không đợi `/login` tự chuyển hướng xong. Đó là flaky
`Navigation ... is interrupted by another navigation` mà
`production-schedule-sticky.spec.js` đã ghi lại từ 2026-09-09 và đã tự vá bằng
`waitForURL(/\/app/)`. Từ **71.0.0.290** (đăng nhập sống trên điện thoại: cookie
có `Max-Age`, idle 14 ngày) phiên sống dai hơn nên `/login` chuyển hướng đều đặn
hơn, và cú race đó nổ **ở mọi lần chạy** khi `--retries=0`, không còn lác đác.
Đã áp đúng một dòng vá mà repo tự đặt ra cho cả ba file. Không đụng mã sản phẩm,
không liên quan REQ-UI-023 — chỉ là thứ chặn ngang việc xác minh lane này.

## Ảnh before/after

`reports/screenshots/hp3-schedule-mobile-toolbar/`:
`before/{390x844,375x667,320x568}.png`,
`after/{390x844,375x667,320x568}.png`,
`after/{...}-sheet-open.png` (tấm lọc đang mở).
