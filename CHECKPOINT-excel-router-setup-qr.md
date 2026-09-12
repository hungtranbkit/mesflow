# CHECKPOINT — Excel Router: auto SETUP OP + export QR

**Ghi lúc:** 2026-09-12, trước khi tắt nguồn máy Dell.
**Trạng thái:** DANG DỞ — backend xong phần lớn, **chưa chạy test nào**.

## Toạ độ

| | |
|---|---|
| Worktree | `/home/dell/workspace/mesflow/.worktrees/claude-excel-router-setup` |
| Branch | `agent/claude/excel-router-setup-qr` |
| Base | `4307bab` = `origin/integration/daily-dashboard-test` (release 71.0.0.294) |
| WIP commit | xem `git log -1` trên branch (commit "wip(excel-router)") |
| File mẫu | `~/Downloads/Lộ trình sản xuất NEWARK ARM CHAIR .xlsx` (44 sheet, 112 OP) |

## Audit đã xong (KHÔNG cần làm lại)

Cơ chế SETUP **đã có sẵn đầy đủ** — tái sử dụng, tuyệt đối không dựng cái thứ hai:

- `app/mesflow/domain/policy.py` — `SETUP_TYPE`, `SUPPORT_TYPES`, `LABELLED_TYPES`
  (SETUP **có** in tem QR), `STARTABLE_TYPES`, các mảnh SQL `type_is_sql(...)`.
- `app/mesflow/db/repositories/setup_ops.py` — `SETUP_QR_PREFIX='WF|OPID|'`,
  `setup_qr_for(id)`, `SETUP_CODE_SUFFIX='-SU'`, `_create_setup_row()`.
- `app/mesflow/domain/qr_identity.py` — `printable_qr_payload_sql()` là nơi DUY NHẤT
  trả lời "tem mới được mang payload nào" (đã xử lý mã mơ hồ). Export dùng hàm này.
- Migration `0047_setup_operations` đã có `operations.parent_operation_id`,
  `requires_setup`, `expected_setup_minutes`, `setup_note`, `setup_completed_at`,
  và `template_operations.requires_setup/expected_setup_minutes/setup_note`.
- `master_data.py` (~dòng 688) đã clone OP SETUP khi instantiate PO từ Template.
- `production_orders.source_template_id` (migration 0015) + kho file nhập
  `template_import_blobs/events` (migration 0046) ⇒ export round-trip lấy lại được
  workbook gốc.

**Layout workbook** (đã dump từ file thật): mỗi sheet = 1 Part; block bắt đầu ở ô
A = `OPERATION # NN- TÊN`; nhãn `Thời gian Setup ( phút )` nằm ở dòng +2 (cột L),
**giá trị ở dòng +3 cùng cột**; `Thời gian gia công / sản phẩm (s)` nhãn +5, giá trị +6.
Cột A:M có chữ, **cột N trở đi trống** → làn QR.

## Đã làm

### `app/mesflow/web/excel_io.py`
- `_deaccent()`, `_block_labeled_number()`, `SETUP_MINUTES_LABELS`,
  `CYCLE_SECONDS_LABELS`, `BLANK_NUMBER_PLACEHOLDERS`.
  Đọc số theo **neo nhãn trong phạm vi một block** (không hardcode L10/L11).
  Âm / chữ vô nghĩa → `ValueError` có sheet+dòng. `-`, `x`, `n/a`… = 0 (file thật dùng
  `-` để nói "không có setup").
- `_parse_go_router_template()`:
  - gom `starts` trước để biết **biên block**;
  - phát `requires_setup`, `expected_setup_minutes`, `_setup_declared`,
    `standard_seconds_per_unit`;
  - **khử trùng mã OP trong cùng Part** bằng hậu tố `-2` (workbook thật đánh trùng
    `OPERATION # 02` — đúng sự cố TPL-6126, 10 chỗ) + đẩy `warnings`;
  - trả thêm `warnings`.
- Mới: `_preview_payload()`, `_selection_key()`, `_apply_selection()`,
  `_parse_uploaded_router()`, endpoint **`POST /api/templates/preview-workbook`**
  (không ghi CSDL).
- `import_template_workbook()`: đọc `selection` (JSON trong multipart), áp
  `_apply_selection`, file khai báo setup thì **file là nguồn sự thật** cho
  `requires_setup`/`expected_setup_minutes`; trả `setup_count`, `warnings`,
  `dropped_setups`.
- Import `SETUP_CODE_SUFFIX` từ `setup_ops` + `import json`.

### `app/mesflow/web/router_export.py` (MỚI)
`GET /api/production-orders/<id>/router.xlsx` và `/router-labels`.
Mở lại workbook gốc từ kho rồi **đóng thêm QR**; không còn gốc thì dựng workbook
tương đương. Làn QR = cột đầu tiên sau ô có chữ xa nhất (`_qr_lane_column`) ⇒ không
đè chữ. QR PNG native size (không nội suy), `box_size` sàn 3. Nhãn "QR OP" / "QR Setup".
Tên file UTF-8 theo RFC 5987.

### Khác
- `app/mesflow/web/app.py` — đăng ký `router_export_bp`.
- `requirements.txt` — **thêm `Pillow==11.3.0`** (openpyxl bắt buộc có Pillow mới
  nhúng được ảnh). ⇒ **cần build lại image**.
- `app/mesflow/web/static/app.js` — `importTemplateExcel()` đổi thành
  chọn file → `showTemplateImportPreview()` → xác nhận. Checkbox OP mặc định tick;
  OP Setup mặc định tick khi phút > 0; bỏ tick OP cha thì setup **tắt + khoá**
  (không tạo được setup mồ côi); tick lại cha thì setup về mặc định trừ khi người
  dùng đã tự sửa (`setupTouched`).
- `app/mesflow/web/static/ui.css` — style `.tpl-preview-*` (card rời, bo góc, có gap;
  tên chính / mã phụ; tag `SETUP`).

## Đã kiểm bằng tay (chưa phải test tự động)

Chạy parser trên file thật trong image app:
- 44 Part, 112 Operation, **47 OP có setup > 0**.
- `Chân ghế A - Trái` OP01 setup=20 ✓, OP02 setup=0 → không tạo ✓,
  `HÀN ROBOT - Hàn vòng đệm` OP01 setup=120 ✓ (khớp mô tả của user).
- Trùng mã: 10 → **0** sau khử trùng, mỗi ca một dòng warning.
- QR: PNG hợp lệ (magic bytes), 75×75 px, làn QR = cột 14 (N) > cột dữ liệu cuối 13 (M).

Lệnh đã dùng để kiểm (cần image có Pillow):
```bash
SD=/tmp/claude-1000/-home-dell-workspace/bb3b69b0-de60-4509-9092-13771adabb68/scratchpad
docker build -t mesflow-router-qr-test:latest -f $SD/Dockerfile.pillow $SD
docker run --rm --entrypoint python \
  -e DATABASE_URL='postgresql://x:x@127.0.0.1:5432/x' -e MESFLOW_SECRET_KEY='t' \
  -v $SD/wb:/wb -v $PWD:/src:ro mesflow-router-qr-test:latest /wb/parsecheck.py
```
(Scratchpad `/tmp/...` **mất sau reboot** — `$SD/wb/router.xlsx` copy lại từ
`~/Downloads/`, `Dockerfile.pillow` chỉ là `FROM 127.0.0.1:5000/mesflow-app:71.0.0.294`
+ `pip install Pillow==11.3.0 pytest`.)

## CÒN DANG DỞ

1. **Nút Export chưa gắn vào UI.** Đang dừng đúng ở đây: cần thêm nút
   "Xuất Excel Router (QR)" vào `po-detail-actions` trong `app.js` (~dòng 1101,
   cạnh `poEdit`/`poAddPart`), trỏ tới
   `/api/production-orders/${po.id}/router.xlsx`. **Không đưa vào Kiosk.**
2. **Chưa có test nào** (yêu cầu D):
   - `tests/test_excel_router_setup_parser.py` — 20→tạo, 120→tạo, 0/trống→không,
     âm/chữ→ValueError, placeholder `-`→không, nhiều block/sheet, khử trùng mã,
     nhập lại không sinh trùng.
   - `tests/test_router_export_qr.py` — PNG hợp lệ + **decode lại đúng payload**,
     làn QR > cột dữ liệu cuối, chỉ có QR Setup khi thật sự có setup liên kết,
     không trùng/mơ hồ payload, content-type + tên file UTF-8.
   - integration (cần DB): parent link đúng, SETUP bị loại khỏi metric sản xuất,
     `expected_setup_minutes` giữ nguyên, không có setup mồ côi qua API.
   - Playwright: checkbox setup xuất hiện + mặc định tick; bỏ tick cha → setup khoá.
   - Regression: file KHÔNG có setup vẫn nhập như cũ; kiosk/public security không đổi.
3. **Requirement docs (impact = YES)**: chưa cập nhật
   `docs/MESFLOW_MASTER_REQUIREMENTS.md` (EN) + `_VI.md` + bảng truy vết.
4. Chưa rebase lại lên integration mới nhất; chưa push bản hoàn chỉnh.

## Blocker / rủi ro cần nhớ

- **Pillow là dependency MỚI** → image test/app phải build lại, nếu không
  `router_export` sẽ `ImportError` khi nhúng ảnh. Đây là "migration note" phải báo
  cho session mesflow.
- Docker address pool trên máy này đã cạn → **không dựng stack lane mới**; dùng
  image sẵn có + `--network host` (xem memory `mesflow-ui-verify-without-new-stack`).
- Playwright trên host này không chạy được (GPU/zygote); phải chạy trong image
  `mesflow-*-playwright` với `--network host --ipc=host`.
- `_apply_selection` mới chỉ áp cho nhánh **go_router**; nhánh workbook chuẩn
  (3 sheet Template/Parts/Operations) chưa nhận `selection` — cần quyết định có
  mở rộng không.
- Quyết định ngữ nghĩa đã chọn: block khai báo setup (kể cả = 0) thì **file thắng**
  cấu hình trên web; block không có nhãn setup thì **giữ** cấu hình cũ (PRESERVED).

## Lệnh tiếp tục sau reboot

```bash
cd /home/dell/workspace/mesflow/.worktrees/claude-excel-router-setup
cat CHECKPOINT-excel-router-setup-qr.md
git log --oneline -3
git status --short
# rồi làm tiếp mục "CÒN DANG DỞ" số 1 -> 2 -> 3 -> 4
```

## Lưu ý bàn giao

Tính năng này có một **thay đổi hành vi** cần nói rõ khi handoff: workbook đánh
trùng số Operation trong cùng một Part trước đây bị **từ chối cả file**; nay được
nhập với mã tách `-2` kèm cảnh báo hiện trên màn xem trước. Chỉ những file TRƯỚC
ĐÂY BỊ TỪ CHỐI mới đổi kết quả — file đang nhập được không đổi mã.
