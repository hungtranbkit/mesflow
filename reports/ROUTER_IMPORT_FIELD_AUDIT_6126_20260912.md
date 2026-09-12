# Audit file Router thật — bản đồ field USED / DERIVED / UNUSED / RUNTIME

PO 6126 · `Lộ trình sản xuất NEWARK ARM CHAIR .xlsx` · 2026-09-12

Nguồn: `tests/fixtures/router-newark-arm-chair.xlsx` (chính file
`Lộ trình sản xuất NEWARK ARM CHAIR .xlsx` của xưởng, giữ nguyên bytes).
Mọi con số dưới đây đọc trực tiếp từ file, không lấy từ mô tả.

## Tổng quan đã kiểm chứng

| | |
|---|---|
| Sheet (đều visible) | 44 |
| OP block (`OPERATION # nn`) | 112 |
| Ảnh nhúng | 85, trải trên **cả 44** sheet |
| `PO NUMBER` | `6126` — giống nhau trên 44/44 sheet |
| `QTY` | `110` — giống nhau trên 44/44 sheet |
| `LOẠI ĐƠN HÀNG` | `SẢN XUẤT HÀNG LOẠT` — 44/44 |
| `SỐ LƯỢNG` (theo sheet) | **32 sheet = 110 · 11 sheet = 220 · 1 sheet = 440** |
| Metadata `J1` | `Mã số: SX-1/BM1 / Lần ban hành: 1 / Ngày BH: 7/9/2026` — 44/44 |
| `CHÚ Ý` | trống ở toàn bộ file |

## Bản đồ field

### A. ĐANG DÙNG (parser hiện tại đọc và lưu)

| Field trong file | Ô | Vào đâu |
|---|---|---|
| `MÃ BẢN VẼ` | `C5` | `template_parts.code` |
| `TÊN BẢN VẼ` / tên sheet | `C4` / sheet title | `template_parts.name` |
| `PO NUMBER` | `C2` | chỉ dùng đặt tên Template (`TPL-6126`) |
| `QTY` | `C3` | trả về trong payload parse, **không lưu** |
| `OPERATION # nn - <tên>` | cột A | `template_operations.code` + `.name` |
| `Thời gian Setup ( phút )` | nhãn cột L, số ở dòng dưới | `requires_setup` + `expected_setup_minutes` |
| `Thời gian gia công / sản phẩm (s)` | nhãn cột L, số ở dòng dưới | `standard_seconds_per_unit` |

### B. CÓ TRONG FILE NHƯNG PARSER ĐANG BỎ QUA — cần xử lý

| Field | Ô | Giá trị thật | Ghi chú |
|---|---|---|---|
| `SỐ LƯỢNG` theo sheet | `I4` | 110 / 220 / 440 | **Không phải bản sao của QTY.** Là bội số BOM 1×/2×/4× — số lượng Part phải làm. Bỏ qua là mất định mức. |
| `LOẠI ĐƠN HÀNG` | `G4` | `SẢN XUẤT HÀNG LOẠT` | Loại đơn hàng. Chưa có field trong model. |
| `Tổng thời gian gia công dự kiến ( giờ )` | nhãn cột M | có ở 112/112 block | **Không phải field thừa** — xem mục D. |
| Metadata biểu mẫu | `J1` | `SX-1/BM1`, ban hành 1, 7/9/2026 | Mã số/phiên bản biểu mẫu. Thuộc audit/source metadata. |
| `Part Number ( Mã bản vẽ )` theo block | cột B trong block | **27/112 block để trống** | Chủ yếu công đoạn xử lý (LÀM NGUỘI...). Trống thì kế thừa Part của sheet — không phải lỗi. |
| `CHÚ Ý` | `B6`/`C6` | trống toàn file | Phải nhận field để file sau có ghi chú thì không rơi. |
| `HÌNH ẢNH` | vùng `J2` | 85 ảnh / 44 sheet | Ảnh tham chiếu Part. Chưa gắn được vào `template_parts`. |
| Số OP gốc (`nn`) | trong tiêu đề | có trùng — xem mục C | Hiện bị gộp vào mã sinh ra, không lưu riêng. |

### C. Số OP trùng trong cùng sheet — 10 trường hợp

Đây **không** phải lỗi nhập liệu. Là hai công đoạn khác nhau mang cùng số:

| Sheet | Số | Hai công đoạn |
|---|---|---|
| Thanh la khung ngồi phía trước | 02 | CHAMFER LỖ · LÀM NGUỘI |
| Thanh tựa lưng ghế | 02 | CHAMFER LỖ · LÀM NGUỘI |
| Tay ghế - Trái | 03 | LÀM NGUỘI · CHẤN BƯỚC 1 |
| Tay ghế - Trái | 07 | UỐN XOẮN TAY GHẾ · CHẤN |
| Tay ghế - Phải | 03 | LÀM NGUỘI · CHẤN BƯỚC 1 |
| Tay ghế - Phải | 07 | UỐN XOẮN TAY GHẾ · CHẤN |
| V kết nối tay ghế phía trước | 03 | LÀM NGUỘI · CHẤN |
| V kết nối tay ghế phía sau | 03 | LÀM NGUỘI · CHẤN |
| Móc khóa | 03 | LÀM NGUỘI · CHẤN |
| Chốt tay ghế | 01 | TIỆN BƯỚC 1 · TIỆN BƯỚC 2 |

Hệ quả: danh tính canonical là `operation.id`; mã nội bộ được sinh duy nhất;
**số OP gốc + tiêu đề gốc + thứ tự phải được giữ nguyên như dữ liệu nguồn.**

### D. Thời gian — nhãn và đơn vị

Toàn file chỉ dùng ba nhãn, và **đơn vị nằm trong nhãn**:

```
Thời gian Setup ( phút )               -> phút
Thời gian gia công / sản phẩm (s)      -> giây
Tổng thời gian gia công dự kiến ( giờ ) -> giờ
```

Vì vậy parser phải đọc đơn vị TỪ NHÃN, không đóng cứng giây.

`Thời gian Setup` — trạng thái thô có ba loại, và `-` khác `0`:

| Trạng thái | Số block |
|---|---|
| `> 0` (tạo OP SETUP) | **47** |
| `= 0` | 59 |
| chữ `-` (xưởng ghi "không có") | **6** |

Cả `0` và `-` đều không tạo OP SETUP, nhưng trạng thái thô phải giữ lại: `-` là
"không áp dụng", `0` là "có khai báo và bằng không".

**Kiểm chứng công thức** `total_hours = setup_phút/60 + sheet_qty × cycle_giây/3600`:

| Kết quả | Số block |
|---|---|
| Khớp | **101** |
| Lệch | **5** |
| Không kiểm được (setup là `-`) | 6 |

Năm ca lệch — và chúng lệch **có chủ đích**, vì tổng giờ đang mã hoá số lần thực
hiện riêng, khác số lượng của sheet:

| Sheet · OP | cycle | total (giờ) | work units suy ra | so với QTY 110 |
|---|---|---|---|---|
| Lắp ráp sau khi sơn · 01 ĐÓNG ECU VÀO NAN GỖ | 40s | 12.2222 | **1100** | ×10 |
| Lắp ráp sau khi sơn · 02 RÚT RIVET NẮP CHỤP | 40s | 4.8889 | **440** | ×4 |
| Lắp ráp sau khi sơn · 03 BẮT BULONG RÁP NAN GỖ | 40s | 12.2222 | **1100** | ×10 |
| Lắp ráp sau khi sơn · 04 BẮT VÍT RÁP TAY GHẾ | 50s | 3.0556 | **220** | ×2 |
| Đóng gói · 01 DÁN THÙNG CARTON | 60s | 3.6667 | **220** | ×2 |

⇒ **Không được suy `total` rồi bỏ field.** `Tổng thời gian` là nguồn sự thật cho
thời gian kế hoạch; `planned_work_units = (total − setup) / cycle` chỉ là field
**suy ra**, để hiển thị/lưu riêng, **không** ghi đè số lượng Part.

### E. Sheet đặc biệt

| Sheet | Tình trạng |
|---|---|
| `LÀM NGUỘI VÀ SỬ LÝ HOÀN THIỆN` | không có `TÊN`/`MÃ BẢN VẼ` — sheet mức quy trình |
| `SƠN TĨNH ĐIỆN` | không có mã bản vẽ **và không có OP block nào** |
| `Kiểm tra  sau khi sơn ` | không có `TÊN`/`MÃ BẢN VẼ` |
| `Đóng gói` | không có `TÊN`/`MÃ BẢN VẼ` (nhưng CÓ OP block) |

Bốn sheet này hiện vẫn thành Part với mã tự sinh `PART-nn`. Phải nêu rõ ở màn xem
trước là sheet mức quy trình, và `SƠN TĨNH ĐIỆN` phải có cảnh báo "không có công
đoạn nào" — không tự bịa OP.

### F. Field vận hành — CÓ Ý NGHĨA nhưng không import giá trị ban đầu

`Ngày/Tháng/Năm`, `SETUP`, `Nhân viên Setup`, `Thời gian gia công`, `Tổng cộng`,
`Hàng đạt`, `Hàng lỗi`, `Tổng số lượng sản xuất`, `Nhân viên SX`, `Nhân viên QC`,
`XÁC NHẬN CỦA GIÁM ĐỐC SẢN XUẤT`.

Trong file này tất cả đang trống (trừ các ô định mức thời gian). MESFlow thu thập
chúng qua Session/QC/duyệt, nên **không** tạo dữ liệu actual giả khi import. Nếu
file tương lai có số thật thì phải có chế độ import lịch sử riêng, không lặng lẽ
đổ vào `work_sessions`.

## Khoảng trống so với model hiện tại

| Cần lưu | Model hiện có? |
|---|---|
| Part planned quantity (110/220/440) | **chưa** — `template_parts` không có cột số lượng |
| Order type | **chưa** |
| Total expected machining time | **chưa** |
| `source_op_no` + tiêu đề gốc | **chưa** — số OP đang bị gộp vào mã |
| Trạng thái setup thô (`-` vs `0`) | **chưa** |
| Metadata biểu mẫu (`SX-1/BM1`...) | một phần — kho file nhập giữ nguyên bytes |
| Ảnh tham chiếu Part | `template_parts.drawing_path` có, nhưng import không trích ảnh nhúng |

**Đã lấp bằng migration 0052** (`0052_router_source_semantics`):
`template_parts.planned_quantity` / `parts.planned_quantity`,
`source_op_no`, `source_title`, `expected_total_seconds`, `setup_source_raw`
(trên cả `template_operations` và `operations`), `templates.order_type`,
`templates.source_document_meta`, `production_orders.order_type`, và bảng nối
`template_source_workbooks` (blob ↔ Template).

Còn lại chưa map (hiển thị ở mục "Thông tin Excel có nhưng MESFlow chưa dùng"):
metadata biểu mẫu J1, ô CHÚ Ý, và ảnh tham chiếu Part — cả ba vẫn nằm nguyên
trong file nguồn đã lưu, không mất.

## PO creation on import — ĐÃ LÀM

Nhập file có `PO NUMBER` nay tạo luôn PO. Kết quả thật trên file này:

```
Template TPL-6126 + Production Order 6126
44 Part · 112 Operation · 47 OP Setup · 110 sản phẩm
parts.planned_quantity: 32 Part = 110 · 11 Part = 220 · 1 Part = 440
operations: 112/112 có source_op_no, source_title, expected_total_seconds
```

Ba quy tắc:
- **nhập lại ĐÚNG file** (khớp sha256 của bytes) → no-op sạch, không báo lỗi,
  kể cả khi PO đã tồn tại;
- **PO đã tồn tại** → dừng, nói rõ, không ghi đè dữ liệu vận hành;
- **trùng mã Template, nội dung khác** → đòi xác nhận, và màn xem trước nói có
  bao nhiêu PO đã dựng từ Template đó.

Một Operation SETUP không có `source_op_no` của riêng nó — đúng ngữ nghĩa: nó
sinh ra từ OP cha, không phải từ một block riêng trên giấy.
