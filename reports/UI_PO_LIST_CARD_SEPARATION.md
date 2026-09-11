# P1 UI — Danh sách Production Order: bảng dính liền → THẺ tách rời

Lane phụ. **Không merge, không deploy từ lane này.** Bàn giao cho session `mesflow`.

- Nhánh: `fix/po-list-card-layout-p0`
- Gốc: `origin/integration/daily-dashboard-test` @ `c9a4322` (71.0.0.287)
- Route đụng tới: `/app?page=production-orders` (`renderProductionOrders()` trong `app.js`)

## Trước khi sửa (đo được, không phải phỏng đoán)

`#poList` dựng `<div class="table-wrap"><table>`, mỗi PO là một `<tr class="po-row">`:

- các PO **dính thành một khối dài**, chỉ ngăn nhau bằng `border-bottom` chạy xuyên suốt;
- ở **390px** `.table-wrap` mọc thanh cuộn NGANG — Trạng thái / Ưu tiên / Bắt đầu /
  Kết thúc / Thao tác **nằm ngoài vùng nhìn**, phải kéo ngang mới thấy (ảnh
  `po-list-before-390.png`: chỉ còn Mã PO / Template / Sản phẩm);
- ở 1366px cột "Thao tác" cũng bị cắt khỏi mép phải.

## Sau khi sửa

Mỗi PO là một `<article class="po-card">`:

- **Hình khối** (viền đóng 4 cạnh, nền riêng, shadow, bo `--radius-surface` = 12px) do
  rule quét `[class$="-card"]` ở `ui.css` §838 cấp — khối CSS mới **không** viết lại
  `border-radius`/`background`, vì rule quét dùng `!important` nên viết lại là viết
  vào chỗ chết.
- **Gap dọc thật** `var(--ui-space-3)` giữa hai thẻ liền nhau (không phải border).
- **Phân cấp**: mã PO 16px/800 là tiêu đề chính, tên sản phẩm ngay dưới; Kế hoạch /
  Template nguồn / Ưu tiên / Bắt đầu / Kết thúc là metadata phụ (`--ui-fs-meta` cho
  nhãn, `--ui-fs-body` cho giá trị); thao tác gọn ở góc, tối đa một primary theo
  trạng thái + menu `…`.
- **Bố cục**: desktop `"head head" / "meta actions"` — cho thao tác một hàng riêng
  làm mỗi thẻ cao thêm ~48px mà không thêm thông tin nào. ≤900px thao tác xuống
  hàng riêng; ≤520px thẻ về một cột, metadata 2 cột, primary giãn full-width.
- **390px**: `documentElement.scrollWidth - innerWidth = 0`, `#poList` không còn
  thanh cuộn ngang, mọi thông tin đọc được tại chỗ.

Business logic giữ nguyên: `draw()`/`applyFilters()`/`load()` không đổi, lọc theo
`#poSearch`/`#poStatus`, `data-po-row` (bấm cả thẻ mở PO), `data-po-menu`,
`data-po-start`, `role="link"`/`tabindex="0"`, RBAC và deep-link `?po_id=` như cũ.

**Mọi biến thể trạng thái dùng CHUNG một renderer** — DRAFT / PLANNED / RELEASED /
IN_PROGRESS / PAUSED / COMPLETED / CANCELLED đều là thẻ, kể cả trạng thái không có
nút primary và PO cũ không có template nguồn. Fixture của bài E2E phủ đủ cả 7.

**Chưa làm, có lý do:** "tiến độ" không hiển thị được trên màn này vì
`/api/production-orders` (`ProductionOrderRepository.selectable_columns`) **không trả
về** sản lượng/tiến độ. Thêm nó cần một query mới cho danh sách — đó là thay đổi
business logic, ngoài phạm vi bản vá hình thức này. Tiến độ theo PO hiện có ở
Tổng quan sản xuất (`/api/dashboard/production-orders`).

## Ảnh before/after

`reports/po-list-card/` (không commit vào repo — PNG, giữ tại lane):
`po-list-{before,after}-{390,1366,1920}.png`, cùng một fixture 7 PO.

## Hợp đồng

| Bài | Đo gì |
|---|---|
| `tests/e2e/po-list-card-contract.spec.js` | computed style, 390/1366/1920: gap dọc giữa **hai thẻ liền nhau > 0**; viền đủ 4 cạnh + nền + shadow; bo góc thuộc thang canonical đọc từ `:root` lúc chạy (không px cứng) và đúng bậc `--radius-surface`; 390px không tràn ngang, không còn `<table>`/`.table-wrap`; lọc trạng thái vẫn ra thẻ |
| `tests/test_po_list_is_card_list.py` | static: `renderProductionOrders()` không dựng lại markup bảng; giữ đủ hook click/menu; `.po-card-list` có gap thật; `.po-card` **không** tự viết `border-radius`; REQ-UI-022 có ở cả EN và VI, mỗi bản đúng một định nghĩa |

**Negative proof (chạy tay, từng cái một, đều đỏ đúng bài):**

| Phá | Bài đỏ |
|---|---|
| `.po-card-list{gap:0}` | E2E "khoảng cách dọc thật" (3 viewport) + static gap |
| `.po-card{border-radius:var(--radius-row)}` | E2E "bo góc canonical": `5px, ngoài thang canonical 12px/8px` |
| dựng lại `<table>` trong `#poList` | E2E: không tìm thấy `.po-card` |
| `.po-card{border-radius:12px}` | static "giá trị chết" |
| xoá REQ-UI-022 khỏi bản VI | static "đúng một lần trong bản VI, đang có 0" |

## Gate

- **Focused E2E** (`--retries=0`): `po-list-card-contract`, `po-action-menu`,
  `back-navigation`, `admin-list-card-consistency`, `network-resilience`
  → **33 passed, 1 failed**.
  Bài đỏ duy nhất là `admin-list-card-consistency.spec.js:82 › Part/Operation
  primitive` — **đỏ y hệt trên baseline `c9a4322` chưa có thay đổi nào** (đã chạy
  lại để xác nhận): nó cần PO thật trong DB, còn stack test dựng mới có DB rỗng.
  Không phải hồi quy của bản vá này.
- **Static** (`pytest -m 'static and not postgres'`, có mount `docs/`):
  **579 passed, 7 skipped** — BASE `c9a4322` là 573 passed; +6 là file static mới.
  7 skip đều do môi trường (ffmpeg, docs/PROJECT.yaml không nằm trong image test).

## Requirement

**REQ-UI-022** — thêm vào **cả** `docs/MESFLOW_MASTER_REQUIREMENTS.md` (EN) và
`..._VI.md`, mỗi bản một định nghĩa + một dòng ma trận truy vết trỏ sang
`po-list-card-contract.spec.js`. ID đã quét **toàn bộ `refs/remotes/origin`**
trước khi lấy (cao nhất đang dùng ở mọi nhánh: REQ-UI-021 trên
`fix/production-trace-default-po-hp1`), nên 022 không va.

Bản áp dụng cụ thể của REQ-UI-017 (danh sách nhiều-dữ-kiện là danh sách thẻ) cho
danh sách PO.

## Đụng chạm tới bài có sẵn

Markup đổi nên ba file spec đang trỏ vào `<tr>/<td>/.table-wrap` phải đổi selector
(nội dung hợp đồng giữ nguyên):

- `tests/e2e/po-action-menu.spec.js` — `tr` → `.po-card`, `.table-wrap` → `.po-card-list`
- `tests/e2e/back-navigation.spec.js` — 3 chỗ `tbody tr > td` → `.po-card .po-card-identity`
- `tests/e2e/tutorial-detailed.spec.js` — `#poList table` → `#poList .po-card`

`.po-row` trong `ui.css` (3 rule) đã gỡ cùng lúc với bảng — không còn selector nào dùng.
