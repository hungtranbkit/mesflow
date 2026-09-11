# "Danh sách Template" — thẻ bo góc nhưng dính sát nhau (hotfix P1)

Lane hp3. Nhánh `hp3/ui-template-list-card-separation`, dựng từ
`origin/integration/daily-dashboard-test` @ `426b0c0`.

## Người dùng thấy gì

Màn **Quy trình sản xuất mẫu** (`/app?page=templates`), khối "Danh sách
Template": từng item đã bo góc, nhưng hai item liên tiếp DÍNH SÁT nhau — viền
dưới của thẻ trên chạm viền trên của thẻ dưới, cả danh sách đọc thành một khối
dài. Báo nhiều lần, kèm ảnh chụp trên iPhone (390px).

## Nguyên nhân — ĐO, không đoán

Computed style trên TEST, 6 item, cả 390/1366/1920px, **trước** bản vá:

| | 390 | 1366 | 1920 |
|---|---|---|---|
| `.template-old-list` `rowGap` | `0px` | `0px` | `0px` |
| khoảng hở bounding box giữa 2 thẻ liên tiếp (5 cặp) | `0` | `0` | `0` |
| `.template-old-card` radius / border / shadow | 12px / 1px rgb(200,208,216) / có | nt | nt |

Tức **hình khối thẻ đã đúng, thiếu đúng một thứ: separation**.

Cơ chế: rule quét theo hậu tố tên class ở cuối `ui.css`
(`.admin-body :where(.card,[class$="-card"],[class*="-card "],…)`) ép
`border:1px !important` + `--radius-surface` + `--shadow-card` lên bất cứ thứ
gì tên kết thúc bằng `-card` — `.template-old-card` lọt vào đó và **được cho
không** mặt thẻ. Nhưng `gap` thì rule quét không cho, và vỏ `.template-old-list`
vẫn giữ `gap:0` từ thời item còn là DÒNG ngăn nhau bằng `border-bottom` (hai
khai báo `border:0;border-bottom:1px solid #e2e7ed` vẫn nằm đó, đã chết vì bị
`!important` của rule quét ghi đè). Thẻ bo góc + `gap:0` = viền chạm viền.

## Bản vá

`app/mesflow/web/static/ui.css`, chỉ đụng separation:

* `.template-old-list{gap:0}` → `gap:var(--ui-space-2)` (8px, thang spacing
  canonical; đặc hơn `--ui-space-3` của `.op-card-list` vì đây là rail hẹp có
  `position:sticky` + `overflow:auto`, không phải danh sách ở vùng nội dung chính).
* Bỏ `border:0;border-bottom:1px solid #e2e7ed` đã chết trên `.template-old-card`
  — chúng là phần mô tả ý đồ "danh sách liền mạch" không còn đúng nữa.
  Computed style không đổi một pixel vì rule quét vẫn đang ghi đè bằng `!important`.
* Radius / viền / bóng / padding **giữ nguyên**.

Sau bản vá, cả ba viewport: `rowGap = 8px`, năm cặp thẻ đều hở `8px`. Chiều cao
danh sách 718.9 → 758.9px ở 390/1920 (+40px = 5 × 8px); ở 1366 không đổi (538px,
rail bị chặn bởi `max-height` và cuộn trong).

Ảnh: `reports/screenshots/hp3-template-list-separation/{before,after}/{390,1366,1920}.png`.

## Guard

`tests/e2e/template-list-card-separation.spec.js`, 6 item mock (yêu cầu ≥5),
ba viewport, **390px là acceptance chính**:

1. `.template-old-list` `rowGap > 0` — khoá NGUYÊN NHÂN.
2. Khoảng hở bounding box giữa mọi cặp thẻ liên tiếp `> 0` — khoá KẾT QUẢ
   (rowGap đúng vẫn có thể bị một `margin` âm hay `position` lạ kéo dính lại).
3. Thẻ vẫn giữ bo góc + viền khép kín bốn cạnh + bóng (REQ-UI-017) — chặn cách
   "sửa" bằng việc bỏ luôn mặt thẻ.
4. Bài thứ hai quét cả màn Template: không vỏ nào khác còn xếp thẻ dính nhau.

**Negative proof:** bỏ bản vá (`gap:0` trở lại), dựng lại image API, chạy
`--retries=0` → **cả hai bài đỏ**; bài quét chỉ ra đúng một thủ phạm
`content-panel-body.template-old-list [template-old-card -> template-old-card] gap=0.00px`.

## Audit cùng primitive trong màn Template

Quét runtime ở 390px mọi vỏ đang xếp ≥2 surface dạng thẻ (tên `-card`/`-block`/
`-item`, bo góc ≥8px, viền khép kín): trước bản vá đúng **một** thủ phạm là
`.template-old-list`; sau bản vá **không còn cái nào**. `.part-block` (khối Part
trong editor) tách nhau bằng `margin:var(--ui-space-3) 0`, không dính.

Không mở rộng ra ngoài màn này.

## Requirement impact: **NO**

Đây là lỗi CÀI ĐẶT của hợp đồng đã có, không phải thiếu hợp đồng. REQ-UI-017 đã
viết sẵn: *"the cards are SEPARATED by a vertical `gap` taken from the spacing
scale"*. Không thêm REQ mới. Đã cập nhật kèm batch:

* Traceability của REQ-UI-017 (EN + VI) thêm spec mới.
* `DESIGN.md` §5.5: ghi rõ `gap` là phần DỄ RƠI NHẤT của anatomy danh sách thẻ,
  vì rule quét hậu tố `-card` cho không ba phần còn lại (viền/bo góc/bóng) nên
  một danh sách sai vẫn "trông đã đúng chuẩn" — phải kiểm `gap` của VỎ bằng
  computed style.

## Gate

BASE = `origin/integration/daily-dashboard-test` @ `426b0c0`.

* Focused E2E (`--retries=0`, 8 file: guard mới + `template-ui`,
  `card-surface-contract`, `admin-list-card-consistency`,
  `dashboard-list-surface-contract`, `rework-queue-card-contract`,
  `part-block-primitive`, `row-text-hierarchy`): **56 passed, 1 failed**.
  Bài đỏ là `admin-list-card-consistency.spec.js:82 › Part/Operation primitive`
  — nó cần một PO CÓ THẬT trong DB (`[data-po-row]`), mà stack test dùng tmpfs
  và tên file này đứng đầu bảng chữ cái nên chạy trước mọi bài tạo dữ liệu.
  Kiểm chứng: seed một PO qua API rồi chạy lại chính file đó → **5 passed**.
  Phụ thuộc thứ tự dữ liệu của bài đó, không liên quan bản vá (diff chỉ chạm
  selector `.template-old-*`).
* Static/unit: `pytest -m 'static and not postgres'` → **573 passed, 7 skipped**.
* Thêm 7 file hợp đồng UI/Template chạy riêng (`test_ui_surface_radius_is_canonical`,
  `test_ui_design_tokens_single_source`, `test_admin_list_card_radius_contract`,
  `test_template_ui_v6555`, `test_template_part_ui_v6557`, `test_web_ui`,
  `test_operation_progress_ui_source`) → **44 passed, 1 skipped**
  (skip: `DESIGN.md` không được COPY vào image test — đã có sẵn, không phải mới).
