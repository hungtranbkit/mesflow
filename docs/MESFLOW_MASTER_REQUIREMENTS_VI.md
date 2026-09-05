# MESFlow — Yêu Cầu Tổng (Bản Tiếng Việt, Tự Đầy Đủ, Độc Lập Với Agent)

Phiên bản nguồn đối chiếu: `71.0.0.221` (bản gốc tiếng Anh
`docs/MESFLOW_MASTER_REQUIREMENTS.md`, viết 2026-09-04) · Bản dịch
tiếng Việt này viết: 2026-09-05 · Nguồn sự thật (source of truth) để
sinh testcase QC, dành cho agent/LLM chỉ đọc tiếng Việt.

## 0. Cách dùng tài liệu này (đọc mục này trước)

**Tài liệu này tự đầy đủ (self-contained).** Nó được viết để một agent
QC hoặc LLM **không có quyền truy cập mã nguồn MESFlow, không có
quyền truy cập hệ thống MESFlow đang chạy, và không nhớ bất kỳ hội
thoại nào trước đó** vẫn có thể chỉ đọc riêng file này và sinh ra một
bộ testcase đầy đủ, hợp lệ cho toàn hệ thống. Mọi thông tin một testcase
cần — tên field, công thức, mã lỗi, quy tắc chuyển trạng thái chính
xác, dữ liệu mẫu — đều được viết ra đầy đủ ngay bên dưới, không tham
chiếu kiểu "xem mã nguồn" hay "hành vi hiện tại". Nếu bạn thấy một
yêu cầu vẫn ghi "xem implementation" hoặc không tự đầy đủ, đó là lỗi
của tài liệu này — hãy gắn cờ (flag), không được đoán và tự suy diễn.

**Đây là bản dịch/biên soạn tiếng Việt song hành với bản gốc tiếng
Anh** `docs/MESFLOW_MASTER_REQUIREMENTS.md`. Hai file giữ **cùng một bộ
ID** (`REQ-*`, `BR-*`, `NFR-*`, `REQ-UI-*`) — không tạo ID mới, không
đánh số lại. Khi hai bản có mâu thuẫn về nội dung diễn giải (không
phải ID), bản tiếng Anh là bản gốc kỹ thuật (được viết trực tiếp từ đọc
mã nguồn); bản tiếng Việt này là bản diễn giải đầy đủ ý nghĩa cho agent
chỉ đọc được tiếng Việt — nếu phát hiện sai khác, coi đó là lỗi cần báo
cáo (§21), không tự ý sửa một bên mà không đối chiếu bên kia.

**File đồng hành**: `docs/MESFLOW_QC_AGENT_TESTCASE_INPUT.md` là ghi
chú bàn giao ngắn cho agent chuẩn bị sinh testcase (bản tiếng Anh) —
đọc tài liệu này trước, file đó đọc sau.

**Bản đồ tài liệu** (giữ đúng thứ tự và số phần như bản gốc):
- **Phần A (§1–§14)**: đặc tả tham chiếu — danh mục module, ma trận
  RBAC, entity, state machine, luồng kiosk, vòng đời session, công
  thức KPI, quy tắc ngoại lệ (exception), schema import/export, danh
  mục lỗi, ma trận môi trường, persona/dữ liệu mẫu QC, tiêu chí NFR,
  giới hạn đã biết. Đọc các mục này trước — mọi phần sau chỉ trỏ lại
  đây thay vì lặp lại.
- **Phần B (§15)**: yêu cầu chức năng (`REQ-*`), mỗi khối một yêu cầu,
  mọi field đều điền đầy đủ hoặc ghi rõ N/A kèm lý do một dòng.
- **Phần C (§16)**: quy tắc nghiệp vụ (`BR-*`).
- **Phần D (§17)**: yêu cầu UI/UX.
- **Phần E (§18)**: hành trình người dùng đầu-cuối (end-to-end journey).
- **Phần F (§19)**: ma trận truy vết (traceability) đối chiếu với bộ
  test tự động hiện có.
- **Phần G (§20)**: hướng dẫn sinh testcase QC và schema output bắt
  buộc.
- **Phần H (§21)**: các khoảng trống/câu hỏi mở đã biết, tách riêng để
  không bị nhầm là hành vi đã đặc tả.

**Tính ổn định của ID yêu cầu**: ID giữ nguyên qua các phiên bản tài
liệu — một khi đã gán, ID không bao giờ được dùng lại cho một yêu cầu
khác, kể cả khi yêu cầu đó sau này bị loại bỏ (sẽ đánh dấu
`DEPRECATED` tại chỗ, không xóa và cấp lại số).

---

# PHẦN A — Đặc Tả Tham Chiếu

## 1. Phạm vi & thuật ngữ

### 1.1 MESFlow là gì

MESFlow là hệ thống điều hành và giám sát sản xuất (production
execution & monitoring) cho một xưởng cơ khí. Hệ thống theo dõi công
việc từ một Lệnh sản xuất (Production Order) đã phát hành xuống tới
từng phiên làm việc (Work Session) có tính giờ của từng công nhân trên
sàn xưởng, hiển thị các ngoại lệ (exception) và điểm nghẽn WIP
(work-in-progress), và báo cáo năng suất nhân viên. Đây là web app
render phía server (Flask/Jinja + JavaScript thuần) trên nền
PostgreSQL. Viewport desktop mục tiêu chính: 1366×768; **ngôn ngữ giao
diện là tiếng Việt xuyên suốt**.

### 1.2 Đối tượng người dùng và vai trò (role)

MESFlow có **đúng 6 role** — không có role nào khác. (Một tài liệu sản
phẩm cũ chỉ nhắc tới 3 role; tài liệu đó đã lỗi thời — danh sách dưới
đây là danh sách hiện hành, đã xác minh.)

| Mã role | Tên tiếng Việt | Đối tượng thực tế điển hình |
|---|---|---|
| `super_admin` | Super Admin / IT | Nhân sự IT/vận hành bảo trì chính hệ thống (health, chẩn đoán, restart dịch vụ) |
| `admin` | Quản trị viên | Quản trị viên nghiệp vụ toàn quyền |
| `manager` | Quản lý | Quản lý sản xuất — cấu hình dữ liệu nghiệp vụ, role nghiệp vụ có phạm vi quyền rộng nhất |
| `supervisor` | Quản đốc | Giám sát sàn xưởng — vận hành session, ngoại lệ, kiosk hàng ngày |
| `operator` | Vận hành | Công nhân sàn xưởng — chỉ xem trong app quản trị; công việc thật thực hiện qua Kiosk |
| `viewer` | Chỉ xem | Chỉ đọc trên hầu hết màn hình nghiệp vụ |

**Không có** role "QA Inspector", "Maintenance" hay "Kiosk User". Một
persona/tài khoản tên `maintenance` hay `kiosk01` trong dữ liệu seed
luôn thuộc một trong 6 role trên (thường là `operator`) — username
không phải là role.

### 1.3 Phân cấp dữ liệu

```
Sales Order (tùy chọn)
  └─ Production Order (PO — Lệnh sản xuất)
       └─ Part (Chi tiết/bộ phận)          (thuộc đúng 1 PO)
            └─ Operation (Công đoạn)        (thuộc đúng 1 Part)
                 └─ Work Session (Phiên làm việc — 1 nhân viên, 1 khoảng thời gian, 1 Operation)
                      ├─ QC Inspection (Kiểm tra chất lượng, tùy chọn)
                      ├─ Operation Adjustment (nhật ký sửa số lượng)
                      └─ Quantity Movement (sổ cái GOOD / DEFECT / REPAIRABLE)

Template (Mẫu quy trình) → khởi tạo (instantiate) thành một PO hoàn toàn mới với Part+Operation
  (một PO KHÔNG BAO GIỜ được tạo trực tiếp — chỉ được tạo bằng cách khởi tạo từ Template)

Employee (Nhân viên) — entity độc lập, được Work Session tham chiếu
Station / thiết bị Kiosk — entity độc lập, được Work Session tham chiếu
Exception (Ngoại lệ) — HAI hệ thống độc lập, không được nhầm lẫn:
  - session_exception_reviews  (hệ cũ, màn hình Quản lý Session)
  - exception_records          ("Trung tâm ngoại lệ" — hệ chính)
```

### 1.4 Bảng thuật ngữ (mọi thuật ngữ dùng ở nơi khác trong tài liệu)

| Thuật ngữ | Định nghĩa |
|---|---|
| **PO** | Production Order — Lệnh sản xuất — một lượt sản xuất một `product`, với `planned_quantity` (số lượng kế hoạch) đơn vị. |
| **Part** | Một chi tiết/bộ phận con thuộc 1 PO; có thể kèm file bản vẽ (`drawing_path`). |
| **Operation** | Một bước quy trình thuộc 1 Part — đơn vị mà công nhân quét/thao tác tại kiosk. |
| **Work Session** | Một phiên làm việc có tính giờ của 1 nhân viên trên 1 Operation. Đơn vị dữ liệu sản xuất nguyên tử (atomic). Chỉ có `status` = `OPEN` hoặc `CLOSED`. |
| **good_qty** | Số lượng sản phẩm đạt. Số nguyên, luôn ≥ 0. |
| **defect_qty** | Số lượng sản phẩm lỗi/NG. Số nguyên, luôn ≥ 0. |
| **rework_qty** | Trong `defect_qty`, bao nhiêu cái có thể sửa được (repairable). Số nguyên, luôn ≥ 0, luôn ≤ `defect_qty` cùng session. |
| **quantity_confirmed** | Boolean. `TRUE` sau bất kỳ lần finish thật của operator hoặc bất kỳ lần admin/supervisor sửa (correction). Chỉ `FALSE` ngay sau khi auto-close, cho tới khi có người sửa xác nhận lại. |
| **excluded_from_reports** | Boolean. Khi `TRUE`, số liệu của session này bị loại khỏi mọi tổng hợp KPI/tiến độ/phát hiện ngoại lệ, nhưng bản ghi không bao giờ bị xóa và trạng thái `OPEN`/`CLOSED` của nó không đổi. |
| **Reportable session** (session được tính vào báo cáo) | Bộ lọc dùng chung cho mọi truy vấn KPI/báo cáo/phát hiện ngoại lệ: `status = 'CLOSED' AND excluded_from_reports = FALSE`. |
| **Input flow / material flow** (dòng vật tư) | Một Operation có thể được cấu hình để lấy trần nguyên liệu từ sản lượng của một Operation "nguồn" phía trên (loại GOOD hoặc REWORK). Xem công thức §8 và REQ-SESS-004/005. |
| **Auto-close** (tự động đóng) | Job chạy theo lịch, ép đóng một Work Session còn `OPEN` quá giờ kết thúc ca (shift) + thời gian ân hạn (grace period). Là luồng mã riêng biệt so với finish thủ công — xem §6. |
| **Kiosk v1** | Giao diện kiosk chạy trên trình duyệt (`/kiosk`, `/api/kiosk-web/*`). Dùng để test thủ công/demo trên trình duyệt. |
| **Kiosk v2** | Giao thức phần cứng ESP32 thật (`/api/kiosk/v2/*`), xác thực theo thiết bị, kiến trúc event-sourced. Đây là thứ phần cứng sàn xưởng thật giao tiếp. Xem §5. |
| **Trung tâm ngoại lệ (Exception Center)** | Bảng `exception_records` — bản ghi sự cố bền vững, khử trùng lặp theo `fingerprint`, có mức độ nghiêm trọng (severity) và vòng đời thật. Hệ thống ngoại lệ chính. |
| **Session Exceptions (hệ cũ)** | Bảng `session_exception_reviews` — luồng review theo từng session đơn giản hơn, cũ hơn, vẫn đang chạy trên màn hình Quản lý Session. |
| **Persona (chỉ dùng để test)** | `?persona=admin|manager|supervisor|operator|viewer` trên route autologin — **chỉ dùng để kiểm thử**, không bao giờ là khái niệm của môi trường production thật. Xem §11.4/§12.2. |
| **Trường PII** | Field chứa dữ liệu cá nhân của một người thật (số CMND/CCCD, địa chỉ, số điện thoại, v.v.) — xem entity employee ở §4.5 để có danh sách chính xác. |

---

## 2. Danh mục module & bản đồ điều hướng (navigation)

Đây là **sidebar điều hướng chính xác, hiện hành** (nguồn: định nghĩa
nav-menu của chính app), kèm `page` id nội bộ của từng màn hình, mã
quyền (permission) yêu cầu, và nhóm nav chứa nó. Một role không có
quyền được liệt kê sẽ **không thấy** mục sidebar đó — không hiển thị ở
dạng mờ/disable, mà biến mất hoàn toàn.

| Nhóm nav | Nhãn trang (tiếng Việt) | `page` id | Quyền yêu cầu | Ghi chú |
|---|---|---|---|---|
| *(cấp cao nhất)* | Tổng quan sản xuất | `overview` | `overview.view` | Trang đích sau khi đăng nhập |
| *(cấp cao nhất)* | Dashboard theo ngày | `dashboard` | `dashboard.view` | |
| Kế hoạch | Production Order | `production-orders` | `po.view` | |
| Kế hoạch | Template | `templates` | `template.view` | |
| Điều hành | Quản lý Session | `session-management` | `session.view` | "50 OP gần nhất, xem session, lọc và chỉnh sửa" |
| Điều hành | Trung tâm ngoại lệ | `session-exceptions` | `exceptions.view` | Exception Center |
| Điều hành | Production Trace | `production-trace` | `session.view` | Dòng thời gian: PO, Session, số lượng, thay đổi |
| Điều hành | Nhật ký nghiệp vụ | `business-audit` | `business_audit.view` | Ai thay đổi gì/khi nào/vì sao |
| Điều hành | Gantt & Material Flow | `production-schedule` | `material_flow.view` | |
| Điều hành | Trạm kiosk | `kiosk-management` | `kiosk.view` | Đăng ký/health/log thiết bị |
| Điều hành | Báo cáo năng suất nhân viên | `employee-productivity` | `session.view` | KPI: % hoàn thành trung bình theo từng nhân viên |
| Điều hành | Nhật ký ứng dụng | `system-logs` | `logs.view` | Action log, trace lỗi API |
| Danh mục | Nhân viên | `employees` | `employees.view` | Hồ sơ nhân viên + QR |
| Danh mục | Danh sách QR Code | `qr-print` | `qr.view` | Lọc/chọn/in hàng loạt nhãn QR |
| Danh mục | Thiết bị | `equipment` | `equipment.view` | |
| Quản trị | Người dùng | `users` | `users.view` | Tài khoản, role, mật khẩu |
| Quản trị | Lịch làm việc | `working-calendar` | `calendar.view` | Ca làm và thời gian nghỉ |
| Hệ thống *(chỉ super_admin)* | Tổng quan hệ thống | `system-overview` | — (chỉ kiểm tra role) | Health App/DB/QA Center/Deploy Agent |
| Hệ thống *(chỉ super_admin)* | Lỗi hệ thống | `system-errors` | — | Lỗi HTTP 500, lỗi DB, dịch vụ không khỏe — khác với ngoại lệ session |
| Hệ thống *(chỉ super_admin)* | Nhật ký | `system-logs-it` | — | Log MESFlow/DB/QA Center/Deploy Agent |
| Hệ thống *(chỉ super_admin)* | Dịch vụ | `system-services` | — | Health + restart, gate bằng allowlist |
| Hệ thống *(chỉ super_admin)* | Chẩn đoán | `system-diagnostics` | — | Kiểm tra DB/migration/QA Center/Deploy Agent |
| Hệ thống *(chỉ super_admin)* | Nhật ký quản trị | `system-audit` | — | Ai cấp quyền Super Admin, ai restart dịch vụ, khi nào |
| *(cấp cao nhất)* | Hướng dẫn | `tutorials` | — (chỉ cần `login_required`) | Hướng dẫn văn bản + video, gồm cả tab con ESP Kiosk |

**Quy tắc truy cập** (chính xác, lấy nguyên văn từ hàm gate của app):
`canOpenPage(page)` = nếu `page` là 1 trong 6 trang "Hệ thống" ở trên,
chỉ cho phép khi role của session **đúng chữ là** `super_admin`
(**không bao giờ** thỏa mãn bởi `admin`); còn lại thì cho phép khi
session có mã quyền của trang đó, hoặc trang không yêu cầu quyền nào
(`tutorials`).

**Các trang tồn tại nhưng không có trong sidebar** (mở qua hành động
trực tiếp, không qua click nav): chi tiết/sửa PO, editor cây Template,
drawer chi tiết Session, drawer chi tiết Exception, modal sửa User,
modal sửa/tạo Employee, editor ca của Lịch làm việc. Các trang này kế
thừa cùng quyền với trang cha (parent list page) của chúng.

**Các trang không thuộc app quản trị**: `/login` (public), `/kiosk`
(giao diện web Kiosk v1, có mô hình xác thực riêng — xem §5),
`/api/kiosk/v2/*` (Kiosk v2, xác thực bằng token thiết bị, không có
giao diện trình duyệt riêng).

---

## 3. Ma trận Role/Permission (chi tiết)

### 3.1 Danh mục quyền đầy đủ

40 mã quyền. `module`/`page`/`action` là field metadata hiển thị trên
màn hình Người dùng & Phân quyền, không phải là điều kiện kiểm tra
truy cập riêng.

| Mã | Module (tiếng Việt) | Hành động | Page id |
|---|---|---|---|
| `overview.view` | Tổng quan | view | overview |
| `dashboard.view` | Dashboard | view | dashboard |
| `po.view` | Production Order | view | production-orders |
| `po.edit` | Production Order | edit | production-orders |
| `template.view` | Template | view | templates |
| `template.edit` | Template | edit | templates |
| `session.view` | Session | view | session-management |
| `session.edit` | Session | edit | session-management |
| `exceptions.view` | Session bất thường | view | session-exceptions |
| `exceptions.resolve` | Session bất thường | edit | session-exceptions |
| `material_flow.view` | Gantt & Material Flow | view | production-schedule |
| `material_flow.edit` | Gantt & Material Flow | edit | production-schedule |
| `kiosk.view` | Trạm kiosk | view | kiosk-management |
| `kiosk.manage` | Trạm kiosk | edit | kiosk-management |
| `ota.view` | ESP Kiosk OTA | view | esp-ota |
| `ota.firmware.manage` | ESP Kiosk OTA | edit | esp-ota |
| `ota.deploy` | ESP Kiosk OTA | deploy | esp-ota |
| `ota.control` | ESP Kiosk OTA | control | esp-ota |
| `ota.approve_stage` | ESP Kiosk OTA | approve | esp-ota |
| `ota.emergency_stop` | ESP Kiosk OTA | emergency | esp-ota |
| `ota.manage_policy` | ESP Kiosk OTA | policy | esp-ota |
| `ota.manage_global_switch` | ESP Kiosk OTA | global | esp-ota |
| `logs.view` | Nhật ký hệ thống | view | system-logs |
| `logs.manage` | Nhật ký hệ thống | edit | system-logs |
| `employees.view` | Nhân viên | view | employees |
| `employees.edit` | Nhân viên | edit | employees |
| `qr.view` | QR Code | view | qr-print |
| `equipment.view` | Thiết bị | view | equipment |
| `equipment.edit` | Thiết bị | edit | equipment |
| `users.view` | Người dùng | view | users |
| `users.manage` | Người dùng | edit | users |
| `roles.manage` | Phân quyền | admin | users |
| `calendar.view` | Lịch làm việc | view | working-calendar |
| `calendar.edit` | Lịch làm việc | edit | working-calendar |
| `business_audit.view` | Nhật ký nghiệp vụ | view | business-audit |
| `operations.view` | Operations Center | view | operations-center |
| `system_logs.view` | Nhật ký hệ thống (kỹ thuật) | view | operations-center |
| `diagnostics.run` | Chẩn đoán | edit | operations-center |
| `deploy.view` | Deploy | view | operations-center |
| `deploy.execute` | Deploy | admin | operations-center |

### 3.2 Ma trận cấp quyền (role → quyền, chính xác, hiện hành)

`✓` = được cấp. `admin` và `super_admin` **ngoài ra còn bỏ qua toàn bộ
bảng này** đối với các quyền nghiệp vụ thông thường (xem §3.3) — cột
`admin` bên dưới là nội dung thô của bảng cấp quyền, thực chất không
còn ý nghĩa vì có cơ chế bypass, chỉ hiển thị ở đây cho đầy đủ/phục vụ
audit.

| Quyền | admin* | manager | supervisor | operator | viewer |
|---|:---:|:---:|:---:|:---:|:---:|
| overview.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| dashboard.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| po.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| po.edit | ✓ | ✓ | | | |
| template.view | ✓ | ✓ | | | ✓ |
| template.edit | ✓ | ✓ | | | |
| session.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| session.edit | ✓ | ✓ | ✓ | | |
| exceptions.view | ✓ | ✓ | ✓ | | ✓ |
| exceptions.resolve | ✓ | ✓ | ✓ | | |
| material_flow.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| material_flow.edit | ✓ | ✓ | ✓ | | |
| kiosk.view | ✓ | ✓ | ✓ | ✓ | |
| kiosk.manage | ✓ | ✓ | ✓ | | |
| ota.view | ✓ | ✓ | ✓ | | |
| ota.firmware.manage | ✓ | ✓ | | | |
| ota.deploy | ✓ | ✓ | | | |
| ota.control | ✓ | ✓ | | | |
| ota.approve_stage | ✓ | ✓ | | | |
| ota.emergency_stop | ✓ | | | | |
| ota.manage_policy | ✓ | ✓ | | | |
| ota.manage_global_switch | ✓ | | | | |
| logs.view | ✓ | ✓ | | | |
| logs.manage | ✓ | | | | |
| employees.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| employees.edit | ✓ | ✓ | | | |
| qr.view | ✓ | ✓ | ✓ | ✓ | ✓ |
| equipment.view | ✓ | ✓ | ✓ | | ✓ |
| equipment.edit | ✓ | ✓ | | | |
| users.view | ✓ | | | | |
| users.manage | ✓ | | | | |
| roles.manage | ✓ | | | | |
| calendar.view | ✓ | ✓ | ✓ | | ✓ |
| calendar.edit | ✓ | ✓ | | | |
| business_audit.view | | ✓ | ✓ | | |
| operations.view | | ✓ | | | |
| system_logs.view | | ✓ | | | |
| deploy.view | | ✓ | | | |

*Cột `admin` ở trên là bảng cấp quyền thô; §3.3 giải thích vì sao nó
không ảnh hưởng tới hành vi thực tế.

### 3.3 Quy tắc thực thi (chính xác, không mơ hồ)

1. **Bypass của `admin`**: `role == 'admin'` (hoặc `super_admin`, đối
   với quyền nghiệp vụ thông thường) → mọi kiểm tra quyền trả về
   `True` ngay lập tức, bất kể bảng §3.2 nói gì. Hệ quả: sửa dòng của
   `admin` qua `PUT /api/roles/admin/permissions` được API chấp nhận
   nhưng **không có tác dụng** — server âm thầm ép bộ quyền của
   `admin` trở lại "mọi quyền" ngay trong cùng lệnh gọi đó.
2. **`super_admin` và System Console**: 6 trang "Hệ thống" (§2) và API
   của chúng (`GET/POST /api/system-health/*`) kiểm tra **chuỗi role
   đúng nghĩa đen của session** — chỉ thỏa khi là `super_admin`,
   **không bao giờ** thỏa bởi `admin`, dù `admin` có cơ chế bypass
   quyền nghiệp vụ ở trên. Một session `admin` gọi API System Console
   sẽ nhận `403 FORBIDDEN`.
3. **Fail-closed (mặc định từ chối)**: nếu bản thân việc tra cứu quyền
   bị lỗi (ví dụ bảng metadata RBAC không truy cập được), kết quả kiểm
   tra là `False` (từ chối), không bao giờ là `True`.
4. **Response chuẩn khi thiếu quyền** (bất kỳ role nào, bất kỳ route
   nào bị gate): `HTTP 403`, body
   `{"ok": false, "error": "FORBIDDEN", "permission": "<code>", "message": "Bạn không có quyền thực hiện thao tác này"}`.
5. **Không có session**: `HTTP 401`, `{"ok": false, "error": "AUTH_REQUIRED"}`.
6. **Session hết hạn**: `HTTP 401`,
   `{"ok": false, "error": "SESSION_EXPIRED", "reason": "<idle|absolute>", "message": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."}`.

### 3.4 Ngoại lệ có chủ đích, khác quy tắc chung theo tiền tố route

Một số route cụ thể **cố ý hẹp hơn** hoặc **rộng hơn** so với quy tắc
chung mà bảng §3.1 gợi ý theo tiền tố URL. Đây là hành vi thật, hiện
hành, đã xác nhận — kiểm thử từng cái một cách tường minh, đây chính
xác là loại lỗi mà một test dựa-trên-tiền-tố ngây thơ sẽ sai:

| Route | Quy tắc chung sẽ nói | Quy tắc thực tế |
|---|---|---|
| `DELETE /api/production-orders/<id>/force` | `po.edit` (admin+manager) | **Chỉ admin** |
| `POST /api/production-orders/<id>/start` | `po.edit` (admin+manager) | **admin + manager + supervisor** |
| `POST /api/templates/demo/seed`, `DELETE /api/templates/demo` | `template.edit` (admin+manager) | **Chỉ admin** |
| `GET /api/templates/<id>/export-workbook` | Giới hạn theo `template.view` | **admin + manager + viewer** (chỉ đọc, mở rộng) |

### 3.5 Quy tắc thời gian session/xác thực

| Quy tắc | Giá trị |
|---|---|
| Timeout session do không hoạt động (idle) | 60 phút không hoạt động (cấu hình được, mặc định 60) |
| Trần tuyệt đối của session | 12 giờ kể từ lúc đăng nhập, bất kể có hoạt động hay không (cấu hình được, mặc định 12) |
| Timeout idle chế độ Kiosk | 15 phút (ngắn hơn đăng nhập văn phòng thường, vì rủi ro thiết bị dùng chung) |

---

## 4. Entity nghiệp vụ — định nghĩa field và quan hệ

Kiểu dữ liệu là kiểu PostgreSQL thật đã khai báo. `NN` = NOT NULL.
`FK→X` = khóa ngoại tới bảng X. `def` = giá trị mặc định nếu bỏ trống.

### 4.1 `production_orders` (PO)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| code | text | NN, unique |
| sales_order_id | bigint | FK→sales_orders, nullable, ON DELETE SET NULL |
| product | text | NN |
| planned_quantity | int | NN, def 0, **phải > 0 khi tạo** |
| status | text | NN, def `PLANNED`, enum: `DRAFT, PLANNED, RELEASED, IN_PROGRESS, PAUSED, COMPLETED, CANCELLED` |
| priority | text | NN, def `NORMAL`, enum: `LOW, NORMAL, HIGH, URGENT` |
| due_date | date | nullable |
| planned_start_at / planned_end_at | timestamptz | nullable; nếu cả 2 đều có, end phải sau start nghiêm ngặt |
| notes | text | NN, def `''` |
| created_at / updated_at | timestamptz | NN |

Quan hệ: có nhiều `parts`, có nhiều `operations` (FK denormalize, cũng
truy cập được qua part), tùy chọn thuộc về một `sales_order`.

### 4.2 `parts` (Chi tiết/bộ phận)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| production_order_id | bigint | NN, FK→production_orders, ON DELETE CASCADE |
| code | text | NN, unique **trong cùng 1 PO** (`UNIQUE(production_order_id, code)`) |
| name | text | NN |
| drawing_path | text | NN, def `''` |
| sort_order | int | NN, def 0 |
| active | bool | NN, def true |
| created_at / updated_at | timestamptz | NN |

### 4.3 `operations` (Công đoạn)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| production_order_id | bigint | NN, FK→production_orders, CASCADE |
| part_id | bigint | NN, FK→parts, CASCADE |
| equipment_id | bigint | FK→equipment, nullable, ON DELETE SET NULL |
| code | text | NN, **unique toàn cục** (không chỉ trong phạm vi PO) |
| name | text | NN |
| plan_qty | int | NN, def 0 |
| done_qty | int | NN, def 0 — **được tính toán, người dùng không ghi trực tiếp** (xem §5.2) |
| defect_qty | int | NN, def 0 — được tính toán |
| rework_qty | int | NN, def 0 — được tính toán (thêm bởi migration `0022_rework_flow`) |
| status | text | NN, def `PLANNED` — được tính toán, xem state machine §6.2 |
| sort_order | int | NN, def 0 |
| qr | text | NN, unique |
| standard_seconds_per_unit | numeric(12,3) | NN, def 0 — dùng trong công thức năng suất, §8 |
| repair_cycle_time_seconds_per_unit | numeric(12,3) | NN, def 0 |
| predecessor_operation_id | bigint | nullable — quan hệ phụ thuộc thuần thời gian/thứ tự, xem §4.9 |
| dependency_type | text | NN, def `FS` (Finish-to-Start) |
| lag_minutes | int | NN, def 0 |
| planned_start_at / planned_end_at | timestamptz | nullable |
| input_flow_enabled | bool | NN, def false |
| input_source_operation_id | bigint | nullable — Operation nguồn phía trên mà Operation này lấy vật tư |
| input_source_kind | text | NN, def `GOOD`, enum `GOOD, REWORK` — lấy loại sản lượng nào từ nguồn |
| defects_consume_input | bool | NN, def true |
| created_at / updated_at | timestamptz | NN |

### 4.4 `work_sessions` (Phiên làm việc)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| employee_id | bigint | NN, FK→employees, ON DELETE RESTRICT |
| operation_id | bigint | NN, FK→operations, ON DELETE RESTRICT |
| station_id | bigint | FK→stations, nullable, ON DELETE SET NULL |
| device_uuid | text | NN, def `''` |
| status | text | NN, def `OPEN`, enum: **chỉ** `OPEN, CLOSED` — **không bao giờ có giá trị nào khác** |
| started_at | timestamptz | NN, def now |
| ended_at | timestamptz | nullable (set khi đóng) |
| good_qty / defect_qty | int | NN, def 0, luôn được clamp ≥ 0 khi ghi |
| rework_qty | int | NN, def 0, luôn ≤ defect_qty cùng dòng |
| note | text | NN, def `''` |
| start_request_id | text | NN, **unique** — khóa idempotency cho lệnh gọi start |
| finish_request_id | text | unique, nullable — khóa idempotency cho lệnh gọi finish |
| close_reason | text | NN, def `''` — `'AUTO_SHIFT_END'` khi auto-close, rỗng nếu finish thủ công |
| closed_by_system | bool | NN, def false — chỉ `TRUE` khi auto-close |
| shift_boundary_used_at | timestamptz | nullable — mốc giờ kết thúc ca đã dùng, nếu bị auto-close |
| started_at_trusted / ended_at_trusted | bool | NN, def false — timestamp có đến từ đồng hồ thiết bị offline đã xác thực hay không |
| quantity_confirmed | bool | NN, def **true** — xem §1.4/§6.4 |
| excluded_from_reports | bool | NN, def false |
| exclusion_reason | text | NN, def `''` |
| excluded_by | text | NN, def `''` |
| excluded_at | timestamptz | nullable |
| created_at / updated_at | timestamptz | NN |

**Ràng buộc DB-enforced**: `CREATE UNIQUE INDEX ON work_sessions(employee_id) WHERE status='OPEN'`
— một nhân viên chỉ có thể có **tối đa một session `OPEN` tại một thời
điểm**, được ép ở mức database, không chỉ ở logic ứng dụng.

### 4.5 `employees` (Nhân viên)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| employee_no | text | NN, unique, **luôn viết hoa khi ghi** |
| name | text | NN |
| department | text | NN, def `''` |
| position | text | NN, def `''` |
| employment_status | text | NN, def `'Đang làm'` (văn bản tự do, nhưng chuỗi đúng nghĩa `'Đã nghỉ'` là giá trị đặc biệt duy nhất khiến `active` đổi) |
| active | bool | NN, def true — **được tính toán**: `active = (employment_status != 'Đã nghỉ')`, không được set trực tiếp độc lập |
| qr | text | NN, unique |
| birth_date, identity_issue_date, start_date, end_date | date | nullable — chuỗi rỗng khi ghi được ép thành `NULL` |
| hometown, phone, identity_number, current_address, contract_1, contract_2 | text | NN, def `''` — các field PII |
| created_at / updated_at | timestamptz | NN |

### 4.6 `stations` (Trạm/thiết bị)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| code | text | NN, unique |
| name | text | NN |
| workshop, production_line | text | NN, def `''` |
| active | bool | NN, def true |

### 4.7 `users` (Tài khoản)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| username | text | NN, unique |
| display_name | text | NN |
| password_hash | text | NN — không API nào trả về giá trị này |
| role | text | NN — một trong 6 mã ở §1.2 |
| active | bool | NN, def true |
| must_change_password | bool | NN, def false |
| created_at / updated_at | timestamptz | NN |

### 4.8 `exception_records` (Trung tâm ngoại lệ)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| exception_type | text | NN — một trong 7 loại ở §9.1 |
| severity | text | NN, enum `CRITICAL, HIGH, MEDIUM, LOW` |
| status | text | NN, def `OPEN`, enum `OPEN, ACKNOWLEDGED, RESOLVED, AUTO_IGNORED, MANUAL_IGNORED` |
| entity_type, entity_id | text/bigint | NN — nguồn gây ra ngoại lệ |
| employee_id, production_order_id, part_id, operation_id, session_id | bigint | FK nullable, `ON DELETE SET NULL` |
| title, message, recommended_action | text | NN |
| fingerprint | text | NN — xem BR-015 về quy tắc unique |
| metadata_json | jsonb | NN, def `{}` |
| condition_active | bool | NN, def true |
| occurrence_no | int | NN, def 1, > 0 |
| row_version | int | NN, def 1, > 0 — version cho optimistic-concurrency |
| detected_at | timestamptz | NN |
| acknowledged_at, resolved_at, ignored_at | timestamptz | nullable |
| acknowledged_by, resolved_by | bigint | FK→users, nullable |
| auto_ignore_reason, auto_ignored_at | text/timestamptz | nullable |

**Ràng buộc DB-enforced**: `CREATE UNIQUE INDEX ON exception_records(fingerprint) WHERE status IN ('OPEN','ACKNOWLEDGED')`
— tối đa một bản ghi **đang active** cho mỗi fingerprint; một điều kiện
đã resolved/ignored xảy ra lại sẽ tạo bản ghi mới (occurrence mới),
không bao giờ hồi sinh bản ghi cũ.

### 4.9 `session_exception_reviews` (Session Exceptions — hệ cũ)

| Field | Kiểu | Ràng buộc |
|---|---|---|
| id | bigint | PK |
| session_id | bigint | NN, FK→work_sessions, CASCADE |
| exception_code | text(40) | NN |
| exception_fingerprint | text(120) | NN |
| workflow_status | text(20) | NN, def `NEW`, enum `NEW, IN_PROGRESS, RESOLVED, IGNORED` |
| resolution | text(40) | NN, def `''` |
| note | text | NN, def `''` |
| assigned_to, started_by, resolved_by | text(120) | NN, def `''` |
| started_at, resolved_at | timestamptz | nullable |

Unique trên `(session_id, exception_fingerprint)`.

### 4.10 Các bảng phụ trợ khác (chỉ nêu field liên quan tới dữ liệu test)

- **`qc_inspections`**: `session_id` (FK), `operation_id` (FK),
  `inspector_user_id` (FK→users), `status` (`OPEN`/`COMPLETED`),
  `good_qty`, `defect_qty`, `defect_reason`.
- **`operation_adjustments`**: `session_id`, `operation_id`,
  `old_good_qty`/`new_good_qty`, `old_defect_qty`/`new_defect_qty`,
  `old_rework_qty`/`new_rework_qty`, `reason` (NN), `adjusted_by` (FK→users).
- **`penalty_tickets`**: `employee_id`, `operation_id` (nullable),
  `session_id` (nullable), `points`, `reason`, `status`, `issued_by`.
- **`templates` / `template_parts` / `template_operations`**: có cấu
  trúc giống `production_orders`/`parts`/`operations` trừ các field
  runtime (`done_qty`, v.v.), cộng thêm `templates.version` (text, def
  `'1.0'`) và `templates.source_workbook`.
- **`work_shifts`** (ca làm việc): `code` (unique), `name`, `timezone`
  (def `Asia/Ho_Chi_Minh`), `anchor_start`/`anchor_end` (time),
  `cross_midnight` (bool — ca qua đêm), `target_minutes` (int, def
  480), `working_weekdays` (mảng smallint, 0=Thứ Hai..6=Chủ Nhật, def
  `[0,1,2,3,4,5]`), `active` (bool).
- **`work_shift_intervals`**: `shift_id` (FK), `interval_type`
  (`WORK`/`BREAK`), `start_minute`/`end_minute` (int, phút tương đối
  theo ca, ràng buộc `end > start` bằng CHECK constraint), `label`.
- **`kiosk_identities`**: `device_uuid` (unique), `device_name`,
  `station_id` (FK, nullable), `status` (def `PENDING`), `token_hash`,
  `firmware_version`, `last_ip`, `last_seen_at`.

---

## 5. State machine (máy trạng thái)

### 5.1 Work Session (Phiên làm việc)

```
                    start()
                      │
                      ▼
                   [OPEN]  ─────────────────┐
                      │                     │
       finish()       │      auto-close (job hệ thống,
   (hành động thật     │      hết giờ ca + ân hạn, chỉ
    của operator)      │      áp dụng khi vẫn còn OPEN)
                      ▼                     ▼
                  [CLOSED]              [CLOSED]
           close_reason=''         close_reason='AUTO_SHIFT_END'
           closed_by_system=FALSE  closed_by_system=TRUE
           quantity_confirmed=TRUE quantity_confirmed=FALSE
```

**Không có** chuyển trạng thái nào từ `CLOSED` về lại `OPEN` ở bất kỳ
đâu trong hệ thống — không tồn tại hành động "mở lại" (reopen). Nếu
một kế hoạch test yêu cầu mở lại một session đã đóng, đó là đang test
một tính năng không tồn tại (đánh dấu là khoảng trống — SPEC-GAP,
không được giả định nó phải hoạt động).

Hai cờ boolean độc lập, đặt chồng lên trên `status`, thay đổi bởi các
hành động riêng biệt, không phải là các state bổ sung:
- `quantity_confirmed`: chỉ bị đặt `FALSE` bởi auto-close; được đặt
  lại `TRUE` bởi bất kỳ lần sửa nào của supervisor/admin (`adjust()`
  hoặc `edit_session()`).
- `excluded_from_reports`: được đặt `TRUE`/`FALSE` bởi hành động
  exclude/restore tường minh, mỗi hành động yêu cầu lý do (reason)
  không rỗng; không bao giờ làm thay đổi `status`.

### 5.2 Trạng thái Operation (hoàn toàn được tính toán — tính lại sau
mỗi thay đổi session liên quan; chỉ `CANCELLED` được set bởi hành động
người dùng trực tiếp)

Đánh giá theo đúng thứ tự này, khớp điều kiện đầu tiên sẽ dừng:

| # | Điều kiện | Trạng thái kết quả |
|---|---|---|
| 1 | trạng thái hiện tại đã là `CANCELLED` | `CANCELLED` (dính vĩnh viễn) |
| 2 | có bất kỳ session nào của Operation này đang `OPEN` | `IN_PROGRESS` |
| 3 | trạng thái hiện tại là `COMPLETED` và không còn session nào tính vào báo cáo | `COMPLETED` (giữ nguyên kể cả khi mọi lịch sử đã bị loại trừ) |
| 4 | `plan_qty > 0` và `good_qty ≥ plan_qty` | `COMPLETED` |
| 5 | trạng thái hiện tại là `PAUSED` | `PAUSED` (dính — không đổi qua các lần reconcile thông thường phát sinh từ hoạt động không liên quan khác trên cùng PO) |
| 6 | có ít nhất một session tính vào báo cáo | `IN_PROGRESS` |
| 7 | trạng thái hiện tại là một trong `DRAFT, PLANNED, RELEASED, READY` | không đổi |
| 8 | *(mặc định, không khớp điều kiện nào ở trên)* | `PLANNED` |

Hành động người dùng tường minh: `POST /operations/<id>/cancel` →
`CANCELLED`. Bị từ chối (`409`) nếu Operation đã `COMPLETED` (phải
dùng luồng rework riêng) hoặc có bất kỳ session `OPEN` nào (phải đóng
trước).

### 5.3 Trạng thái Production Order (PO)

Enum: `DRAFT, PLANNED, RELEASED, IN_PROGRESS, PAUSED, COMPLETED, CANCELLED`.

Chuyển trạng thái **duy nhất** được ép trong mã nguồn là **Start**:
`POST /production-orders/<id>/start`
- Yêu cầu PO có ≥ 1 Operation (nếu không → `409`, "PO chưa có
  Operation. Hãy thêm Operation trước khi Start.").
- Bị từ chối nếu trạng thái hiện tại là `COMPLETED` hoặc `CANCELLED`
  ("PO đã hoàn thành hoặc đã hủy nên không thể Start").
- **Idempotent**: nếu đã `IN_PROGRESS`, trả về thành công với
  `already_started: true` (không phải lỗi).
- Khi thành công: `status → IN_PROGRESS`.

Mọi thay đổi trạng thái khác đi qua một PATCH tổng quát chỉ kiểm tra
việc giá trị có thuộc enum hay không — **không có** đồ thị chuyển
trạng thái nào khác được ép trong mã (ví dụ một PATCH trực tiếp
`PLANNED → COMPLETED` không bị chặn bởi mã nguồn). Coi bất kỳ quy tắc
chuyển trạng thái chặt hơn nào là chưa xác nhận (xem khoảng trống ở
§21) trừ khi kiểm thử chứng minh điều ngược lại.

### 5.4 Bản ghi Trung tâm ngoại lệ (`exception_records`)

```
   phát hiện fingerprint mới (chưa có bản ghi active nào) → [OPEN]
                                │
              ┌─────────────────┼─────────────────┐
         acknowledge()      resolve()          ignore()
        (xác nhận đã biết)  (xử lý xong)       (bỏ qua)
              │                 │                  │
              ▼                 ▼                  ▼
       [ACKNOWLEDGED]      [RESOLVED]        [MANUAL_IGNORED]
              │
     ┌────────┴────────┐
  resolve()          ignore()
     │                  │
     ▼                  ▼
 [RESOLVED]      [MANUAL_IGNORED]
```

Chỉ `OPEN`/`ACKNOWLEDGED` là "active". `[AUTO_IGNORED]` là trạng thái
kết thúc do hệ thống tự đặt (điều kiện kích hoạt chưa được ghi chép
đầy đủ — xem khoảng trống §21). Mọi chuyển trạng thái yêu cầu caller
gửi kèm `row_version` hiện tại của bản ghi (`expected_version`) — một
version cũ/không khớp sẽ bị từ chối, không bao giờ được áp dụng âm
thầm.

### 5.5 Session Exception (hệ cũ, `session_exception_reviews`)

`NEW → IN_PROGRESS → RESOLVED`, hoặc `→ IGNORED` từ `NEW` hoặc
`IN_PROGRESS` (enum 4 giá trị đơn giản qua CHECK constraint; không xác
nhận có thứ tự ép buộc nào khác ngoài bản thân constraint).

---

## 6. Vòng đời Session — chi tiết đầy đủ

### 6.1 Start (Bắt đầu)

`POST /work-sessions/start` (web) hoặc sự kiện quét `OP` của Kiosk v2
(§7). Đầu vào: `employee_id`, `operation_id`, `station_id` (tùy
chọn), `device_uuid` (tùy chọn), `request_id` (bắt buộc, khóa
idempotency), `occurred_at` (tùy chọn, timestamp offline đáng tin
cậy).

Điều kiện tiên quyết được kiểm tra, theo thứ tự:
1. Nhân viên tồn tại và `active = TRUE` (nếu không → `RepositoryError`, "employee inactive or missing").
2. PO của Operation mục tiêu đang `IN_PROGRESS` (nếu không → `409`, "PO {code} chưa Start hoặc đang tạm dừng").
3. Nếu Operation bật `input_flow_enabled`: Operation nguồn phía trên
   phải **đã có ít nhất một session từng được start** — không nhất
   thiết phải đã finish (nếu không → `409`, "OP nguồn {code} chưa bắt
   đầu session. Phải start session OP nguồn trước khi start {code}.").
4. Nếu tồn tại một predecessor thuần thời gian/thứ tự (và không đồng
   thời là input source): Operation predecessor chỉ cần tồn tại (được
   kiểm tra, nhưng việc hoàn thành không bắt buộc bởi riêng điều kiện
   này).
5. Kiểm tra sẵn sàng điều phối (dispatch readiness, dựa trên WIP) —
   nếu không thể thao tác được, `409` nêu rõ lý do và số lượng WIP
   hiện tại.
6. Nhân viên **không được có session `OPEN` nào khác** (unique index
   ép ở DB) — nếu không → `409`, "employee already has an open
   session."
7. Không có khoảng thời gian trùng (overlap) với bất kỳ session nào
   khác của cùng nhân viên.

Khi thành công: tạo dòng `work_sessions` mới, `status=OPEN`. Trạng
thái Operation tính lại theo §5.2. Một dòng audit (`SESSION_STARTED`)
và một domain event được ghi trong cùng transaction.

Gọi lại với đúng `request_id` trả về response **gốc** không đổi
(`idempotent_replay: true`), không bao giờ tạo session thứ hai.

### 6.2 Finish (Kết thúc)

`POST /work-sessions/<id>/finish`. Đầu vào: `request_id` (bắt buộc),
`good_qty`, `defect_qty`, `rework_qty` (tất cả tùy chọn, mặc định 0),
`note` (tùy chọn), `occurred_at` (tùy chọn).

Kiểm tra hợp lệ:
- `good_qty`, `defect_qty`, `rework_qty` được clamp về ≥ 0 (giá trị
  âm được âm thầm làm tròn về 0, không bao giờ bị từ chối như một
  lỗi).
- `rework_qty > defect_qty` → `ValueError` ("rework_qty cannot exceed
  defect_qty").
- Session phải đang `OPEN` (nếu không → `409`, "session already
  closed").
- Kiểm tra sẵn có vật tư/dòng vật tư (input-flow) — xem công thức §8;
  vi phạm → `409` nêu rõ số lượng chính xác còn lại.
- Không có khoảng thời gian trùng cho cùng nhân viên (kiểm tra giống
  start).

Khi thành công: `status → CLOSED`, `quantity_confirmed → TRUE`,
`close_reason` giữ nguyên `''`, `closed_by_system` giữ nguyên
`FALSE`. Một hoặc nhiều dòng `quantity_movements` được ghi
(`GOOD`/`DEFECT`/`REPAIRABLE`). Trạng thái Operation tính lại. Dòng
audit `SESSION_FINISHED` + domain event(s) được ghi trong cùng
transaction.

Một finish với `good=0, defect=0` sau khi session mở > 4 giờ **không
phải là lỗi** — được cho phép, và được Trung tâm ngoại lệ gắn cờ riêng
(`ZERO_QUANTITY_LONG`, §9.1).

### 6.3 Finish hàng loạt (batch)

`POST /session/group/finish` — một mảng cặp `(session_id, data)`.
**Batch atomic thật sự**: một transaction DB dùng chung cho cả mảng —
phần tử đầu tiên thất bại sẽ rollback toàn bộ mảng, không bao giờ commit
một phần (một số session đóng, số khác thì không).

### 6.4 Auto-close (tự động đóng)

Chạy theo job đã lên lịch (`shift_session_reconciliation`), chỉ áp
dụng cho session còn `OPEN` quá giờ kết thúc ca + thời gian ân hạn
(grace period) cấu hình được (mặc định: xem §11 ma trận môi trường để
biết chính xác các biến môi trường).

- Mặc định an toàn khi rollout: `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=0`,
  `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=1` — một deploy mới cài đặt cron
  nhưng **chưa thực sự** đóng session thật cho tới khi cả hai được bật
  tường minh.
- Giữ nguyên `good_qty`/`defect_qty`/`rework_qty` mà session đã có —
  không bao giờ tự bịa ra một con số.
- Đặt `close_reason='AUTO_SHIFT_END'`, `closed_by_system=TRUE`,
  `shift_boundary_used_at`, `quantity_confirmed=FALSE`.
- Bắn domain event `SESSION_AUTO_CLOSED` (loại event **khác** với
  `SESSION_FINISHED` — không bao giờ ngụy trang thành finish thủ
  công).
- Idempotent + an toàn với đồng thời: một advisory lock theo từng
  session tuần tự hóa các lần chạy đồng thời; nếu session không còn
  `OPEN` vào thời điểm lấy được lock (đã được finish thủ công, hoặc đã
  bị auto-close bởi một lần chạy đồng thời nhanh hơn), lệnh gọi là
  no-op đã được ghi chép, không phải lỗi.
- Áp dụng cùng kiểm tra overlap và sổ cái input-flow như finish thủ
  công.

### 6.5 Correction (sửa số lượng bởi supervisor/admin)

`POST /supervisor/sessions/<id>/adjust`. Role: admin, manager,
supervisor. Yêu cầu `reason` không rỗng (nếu không → `ValueError`,
"reason required"). Hoạt động trên cả session `OPEN` lẫn `CLOSED`.
Luôn đặt `quantity_confirmed = TRUE` bất kể giá trị trước đó — một
sửa đổi của con người **chính là** sự xác nhận. Ghi một dòng audit
`operation_adjustments` (cũ/mới cho good/defect/rework) và một domain
event `VALUE_CHANGED`. Cùng quy tắc `rework ≤ defect` như finish.

### 6.6 Sửa toàn bộ (full edit)

`PATCH /supervisor/sessions/<id>`. Role: admin, manager, supervisor.
Hỗ trợ optimistic concurrency: caller có thể gửi kèm
`expected_updated_at` — một giá trị cũ (ai đó đã sửa trước) sẽ bị từ
chối, không bao giờ bị ghi đè âm thầm.

### 6.7 Chuyển Operation ("giao nhầm Operation")

`POST /supervisor/sessions/<id>/transfer-operation`. Role: admin,
manager, supervisor. Gán lại `operation_id` của một session. Được ghi
audit với Operation trước/sau. Cả tiến độ/trạng thái của Operation cũ
và mới đều được tính lại (§5.2).

### 6.8 Loại trừ / khôi phục ("Loại khỏi báo cáo")

`POST /supervisor/sessions/<id>/exclude` và `.../restore`. Role:
admin, manager, supervisor. Cả hai đều yêu cầu `reason` không rỗng.
Exclude bị từ chối nếu đã bị loại trừ (`409`, "Session đã được loại
khỏi báo cáo"); restore bị từ chối nếu hiện không bị loại trừ (`409`,
"Session hiện không bị loại khỏi báo cáo"). Cả hai không bao giờ xóa
dòng hay đổi `status`. Mỗi hành động ghi domain event riêng
(`SESSION_EXCLUDED` / `SESSION_RESTORED`).

---

## 7. Luồng Kiosk — đầu-cuối, mọi nhánh

### 7.1 Kiosk v1 (chạy trên trình duyệt, `/kiosk`, `/api/kiosk-web/*`)

Không có xác thực bằng token thiết bị — một luồng nhẹ hơn, hướng tới
trình duyệt, dành cho demo/kiểm thử thủ công trên bất kỳ trình duyệt
nào có thể truy cập app.

| Bước | Endpoint | Đầu vào | Thành công | Thất bại |
|---|---|---|---|---|
| 1. Quét | `POST /api/kiosk-web/scan` | `{qr}` | Xác định được nhân viên hoặc operation theo QR | `qr` rỗng → `400 QR_REQUIRED`, `error_code: SCN-001`, thông báo "Chưa nhận được mã quét", gợi ý `action` "Kiểm tra nguồn và dây máy quét, rồi quét lại." |
| 2. Start | `POST /api/kiosk-web/start` | đã xác định nhân viên+operation | Cùng quy tắc §6.1 | Cùng lỗi §6.1 |
| 3. Finish | `POST /api/kiosk-web/finish/<session_id>` | số lượng | Cùng quy tắc §6.2 | Cùng lỗi §6.2 |

### 7.2 Kiosk v2 (giao thức phần cứng ESP32, `/api/kiosk/v2/*`)

Xác thực theo thiết bị (token riêng từng thiết bị), kiến trúc
event-sourced: mỗi thiết bị có một dòng "projection" phía server riêng,
theo dõi trạng thái UI ngắn hạn của chính nó, hoàn toàn tách biệt với
trạng thái `work_sessions` bền vững phía server.

**Định dạng QR trên dây (wire format)**: `WF|EMP|<key>` hoặc
`WF|OP|<key>`. Bất kỳ định dạng nào khác sẽ không parse được
(`kind=None`) và bị từ chối.

**Các trạng thái thiết bị**: `WAIT_EMPLOYEE` (chờ nhân viên),
`WAIT_OPERATION` (chờ operation), `QUANTITY_INPUT` (nhập số lượng),
`SESSION_ACTIVE` (chỉ còn tiếp cận được qua đường cũ, không thuộc
luồng bình thường), `DEVICE_DISABLED` (thiết bị bị vô hiệu),
`MAINTENANCE` (bảo trì).

**Bảng chuyển trạng thái đầy đủ**:

| Trạng thái hiện tại | Sự kiện | Kết quả | Ghi chú |
|---|---|---|---|
| `WAIT_EMPLOYEE` | `SCAN` (kind=EMP), nhân viên không có session mở | → `WAIT_OPERATION` | Danh tính + tên nhân viên được lưu vào projection |
| `WAIT_EMPLOYEE` | `SCAN` (kind=EMP), nhân viên **đã có** session mở | → `QUANTITY_INPUT` | Trực tiếp — thiết bị vào thẳng màn nhập số lượng cho session đã mở, không qua màn xác nhận trung gian |
| `WAIT_EMPLOYEE` | `SCAN` (kind=OP) | bị từ chối | `STATE_INVALID_TRANSITION`, "Cần quét thẻ nhân viên" |
| `WAIT_EMPLOYEE`/`WAIT_OPERATION`/bất kỳ | `SCAN`, QR không parse được (kind=None) | bị từ chối | `STATE_INVALID_TRANSITION`, "Không thể quét mã ở trạng thái này" |
| `WAIT_OPERATION` | `SCAN` (kind=OP), PO của Operation đó đang `IN_PROGRESS` | → `WAIT_EMPLOYEE` | Một Work Session thật được tạo phía server (áp dụng đầy đủ quy tắc §6.1); **thiết bị** ngay lập tức reset về `WAIT_EMPLOYEE` để công nhân tiếp theo dùng được ngay — bản thân session vẫn `OPEN` phía server bất kể trạng thái thiết bị |
| `WAIT_OPERATION` | `SCAN` (kind=OP), PO **chưa** `IN_PROGRESS` | bị từ chối | `OPERATION_NOT_WORKABLE`, nêu tên mã PO |
| `WAIT_OPERATION` | `SCAN` (kind=EMP) | bị từ chối | `STATE_INVALID_TRANSITION`, "Cần quét mã công đoạn" |
| bất kỳ | `FINISH_REQUESTED` | → luồng nhập số lượng | |
| bất kỳ | `QUANTITY_SUBMITTED` | session finish (theo quy tắc §6.2) | |
| bất kỳ | `CANCEL_REQUESTED` | reset về `WAIT_EMPLOYEE` | |
| `DEVICE_DISABLED` / `MAINTENANCE` | **bất kỳ** sự kiện nào | bị từ chối | `DEVICE_NOT_ALLOWED`, "Thiết bị chưa được phép" — chặn cứng bất kể loại sự kiện |

**Idempotency**: mỗi sự kiện được khóa theo `(device_id, event_id)` —
một sự kiện bị gọi lại/trùng lặp (ví dụ thiết bị offline replay một
sự kiện đang xếp hàng) sẽ không bị áp dụng hai lần.

**Hành vi offline**: một thiết bị có `time_quality='synced'` có thể
gửi `occurred_at` đáng tin cậy; server chỉ chấp nhận nếu nó không tạo
ra một session bất khả thi (ví dụ `ended_at` đáng tin cậy tại hoặc
trước `started_at` sẽ được server tự động chuyển về dùng giờ server
thay vì ghi một session có thời lượng âm).

---

## 8. Công thức năng suất/KPI — toán học chính xác

**Phạm vi báo cáo**: `GET /reports/employee-productivity` và chi tiết
của nó (`/{employee_id}`) cùng wallboard Kiosk công khai
(`/api/wallboard/employee-productivity`) đều đọc **cùng một** truy
vấn nền — chúng không bao giờ được phép lệch nhau.

**Bộ lọc dân số (population filter)**: `work_sessions.status = 'CLOSED' AND ended_at IS NOT NULL AND excluded_from_reports = FALSE`.
**Không bao giờ** bao gồm session `OPEN` hay bất kỳ trạng thái
"đang làm real-time" nào — đã xác nhận: response không bao giờ chứa
số lượng session đang chạy hay field "đang làm việc" nào.

**Bộ lọc ngày**: theo `ended_at` (ngày nghiệp vụ, theo timezone của
site — mặc định `Asia/Ho_Chi_Minh`), **không phải** `started_at`. Một
session bắt đầu một ngày dương lịch và kết thúc ngày hôm sau được tính
vào ngày nó **kết thúc**.

**Phần trăm hoàn thành theo từng session**:
```
expected_seconds (giây kỳ vọng) = operations.standard_seconds_per_unit × (good_qty + defect_qty)
actual_seconds (giây thực tế)   = EXTRACT(EPOCH FROM (ended_at − started_at))
completion_percent (% hoàn thành) = expected_seconds / actual_seconds × 100
```
- Nếu `standard_seconds_per_unit = 0` (chưa cấu hình) hoặc
  `actual_seconds = 0`: `completion_percent = NULL` — **không bao
  giờ** là `0`. UI hiển thị đây là "Không đủ dữ liệu", không phải điểm
  0%.
- **Không có trần trên (no upper clamp)** — một session hoàn thành
  nhanh hơn thời gian chuẩn có thể hợp lệ hiển thị > 100% (ví dụ
  120%), và giá trị này được tính nguyên vẹn vào mọi số trung bình
  phía sau.

**productivity_percent theo từng nhân viên** (hiển thị làm điểm số của
dòng họ): `AVG(completion_percent)` trên các session của chính nhân
viên đó trong khoảng thời gian, chỉ tính những session có
`completion_percent IS NOT NULL` (các session có completion `NULL`
được đếm riêng vào `completed_invalid_sessions`, không được đưa vào
trung bình, không bị coi là 0).

**Trung bình tổng hợp toàn bộ nhân viên** (`avg_employee_productivity_percent`):
là trung bình **của từng productivity_percent đã tính sẵn của mỗi
nhân viên** — nghĩa là mỗi nhân viên được tính ngang nhau bất kể họ có
bao nhiêu session. Đây **không phải** là trung bình toàn cục có trọng
số theo số session.

**Nhân viên không có session hợp lệ nào trong khoảng thời gian**:
**không xuất hiện** trong báo cáo — không bao giờ hiển thị như một
dòng `0%`. Một nhân viên mà toàn bộ session trong khoảng thời gian đều
đang `OPEN` cũng hoàn toàn vô hình với báo cáo này (bộ lọc dân số loại
`OPEN` ngay từ đầu).

**Tổng cộng của summary**: `total_good_qty` và `total_defect_qty` là
tổng cộng thuần túy của `good_qty`/`defect_qty` trên toàn bộ dòng nhân
viên đã tính cho báo cáo (đã sửa 2026-09-04 — trước đó 2 field này
luôn là `0` do một lỗi thật đã được ship; nay đã đúng).

**Riêng cho Wallboard**: hỗ trợ khoảng ngày cố định hoặc
tháng-đến-hiện-tại động, lọc theo phòng ban, sắp xếp/số dòng mỗi
trang/chu kỳ lật trang tự động cấu hình được; một lệnh gọi kiểu
"Xem trước" (Preview) không bao giờ được phép làm thay đổi cấu hình
wallboard đã publish; trả về **toàn bộ** danh sách đã lọc (client tự
phân trang, không phải server phân trang).

---

## 9. Quy tắc ngoại lệ (Exception)

### 9.1 Trung tâm ngoại lệ — 7 điều kiện phát hiện

Mỗi dòng dưới đây được đánh giá liên tục (khi reconcile), và **loại
trừ** mọi session có `excluded_from_reports = TRUE` khỏi việc kích
hoạt (đã sửa 2026-08-28 — việc loại trừ này ban đầu chưa áp dụng và
gây nhiễu false-positive cho các session mà một supervisor đã chủ
động bỏ qua từ trước).

| exception_type | Mức độ (severity) | Điều kiện kích hoạt | Hành động khuyến nghị (hiển thị cho người dùng) |
|---|---|---|---|
| `LONG_OPEN_SESSION` | HIGH | Session `status='OPEN'` và `started_at` cách đây hơn 12 giờ | "Kiểm tra Session và xác nhận trạng thái." |
| `ZERO_QUANTITY_LONG` | MEDIUM | Session `status='CLOSED'`, thời lượng > 4 giờ, và `good_qty + defect_qty = 0` | "Đối chiếu sản lượng và xác nhận hoặc sửa Session." |
| `MISSING_STATION` | LOW | `station_id IS NULL` và `device_uuid = ''` | "Xác nhận nguồn thao tác của Session." |
| `INVALID_DURATION` | CRITICAL | `ended_at IS NOT NULL AND ended_at < started_at` | "Mở Session, kiểm tra bằng chứng và sửa qua quy trình hiện có." |
| `OPERATION_COMPLETED_SESSION_OPEN` | HIGH | Session `status='OPEN'` trong khi Operation của nó `status='COMPLETED'` | "Kiểm tra Session trước khi xác nhận trạng thái Operation." |
| `EMPLOYEE_SESSION_CONFLICT` | CRITICAL | Hai session của cùng nhân viên có khoảng thời gian trùng nhau | "Kiểm tra cả hai Session và bằng chứng kiosk." |
| `SESSION_PAST_SHIFT_END` | MEDIUM | Session `status='OPEN'`, `started_at` của nó rơi vào một ca mà giờ kết thúc + thời gian ân hạn đã qua, và ranh giới ca có áp dụng (một session bắt đầu vào khoảng trống không có ca nào active sẽ bị bỏ qua ở đây — vẫn được `LONG_OPEN_SESSION` bao phủ nếu chạy quá 12h) | "Kết thúc Session thủ công, hoặc chờ hệ thống tự động đóng ca." |

`fingerprint` của mỗi bản ghi được sinh ra = `"<exception_type>:SESSION:<session_id>"`.

### 9.2 Session Exceptions hệ cũ (`session_exception_reviews`)

Được tạo riêng cho màn hình Quản lý Session cũ hơn. Áp dụng cùng bộ
lọc dân số (`excluded_from_reports=FALSE`). Vòng đời: §5.5. Mã/
fingerprint theo phạm vi session, không phải cùng giá trị với danh
sách `exception_type` ở §9.1 (không được nhầm lẫn mã của hai hệ
thống).

---

## 10. Schema và kiểm tra hợp lệ import/export

Import/export file Excel cho Template và Operation
(`GET /export.xlsx`, `POST /import`, `export-workbook`/`import` theo
từng template). Role: admin + manager (export-workbook viewer cũng đọc
được).

**Yêu cầu dòng Operation** (theo dòng, "Sheet Operations"):
- Mỗi dòng cần có hoặc `operation_id`, **hoặc** đầy đủ ngữ cảnh (mã PO
  + Part + tên Operation) — thiếu 1 trong 2 → lỗi theo số dòng:
  `"Dòng {N}: thiếu ..."` nêu rõ chính xác field nào.
- `done_qty`, `defect_qty`, `status` bị **từ chối thẳng** nếu xuất
  hiện với giá trị sẽ làm thay đổi chúng — đây là dữ liệu do production
  tự tính, không bao giờ import được:
  `"Dòng {N}: done, defect và status là dữ liệu production tự tính; hãy sửa Session nguồn rồi reconcile."`
- Trùng `operation_id` trong cùng 1 file → bị từ chối:
  `"Dòng {N}: trùng operation_id {code}."`
- Nếu `planned_quantity` của PO mục tiêu đã khác với giá trị trong
  file → bị từ chối hoàn toàn (không âm thầm ghi đè):
  `"PO {code} có số lượng kế hoạch {current}, nhưng file có {file_value}"`.
- Di chuyển một Operation sang PO/Part khác qua Excel bị từ chối một
  khi Operation đó đã có bất kỳ dòng sổ cái tiêu thụ vật tư nào:
  `"Operation {code} đã có Ledger nên không thể chuyển PO/Part bằng Excel."`

**Import cả workbook template** (sheet `Parts` + `Operations`):
- Sheet `Parts` không được rỗng (`"Sheet Parts chưa có dữ liệu."`);
  mỗi dòng Part cần cả mã và tên.
- Tham chiếu Part của mỗi dòng Operation phải tồn tại trong sheet
  `Parts` — kiểm tra tham chiếu chéo giữa các sheet, không phải kiểm
  tra độc lập từng sheet (`"Operations dòng {N}: Part {code} không tồn
  tại."`).
- Mỗi dòng Operation cần có tên (`"Operations dòng {N}: thiếu tên
  Operation."`).

**Thay thế cây Template** (`PUT /templates/<id>/tree`): bị từ chối
một khi các Operation đã khởi tạo (instantiate) của template đó đã có
bất kỳ Session hoặc dòng sổ cái tiêu thụ vật tư nào — phải dùng Merge
thay thế, hoặc tạo PO mới.

---

## 11. Danh mục lỗi / hành vi lỗi chuẩn

### 11.1 Ánh xạ trạng thái HTTP chuẩn → ý nghĩa (áp dụng toàn hệ thống)

| Status | Ý nghĩa | Cấu trúc body |
|---|---|---|
| 200 | Thành công | `{"ok": true, ...}` |
| 400 | Yêu cầu sai / lỗi kiểm tra hợp lệ | `{"ok": false, "error": "<CODE>", "message": "<thông báo tiếng Việt>"}` |
| 401 | Không có session / session hết hạn | `{"ok": false, "error": "AUTH_REQUIRED"}` hoặc `{"error": "SESSION_EXPIRED", "reason": "idle"|"absolute"}` |
| 403 | Đã xác thực nhưng không có quyền | `{"ok": false, "error": "FORBIDDEN", "permission": "<code>", "message": "..."}` |
| 404 | Không tìm thấy entity/route | `{"ok": false, "error": "NOT_FOUND", "message": "Đường dẫn không tồn tại."}` |
| 409 | Xung đột / bị từ chối theo quy tắc nghiệp vụ (ví dụ đã đóng, trùng lịch, thiếu vật tư đầu vào) | `{"ok": false, "error": "CONFLICT"}` hoặc mã lỗi cụ thể, `message` nêu rõ lý do chính xác |
| 500 | Lỗi server không mong đợi | Body lỗi tổng quát; được ghi vào Action/Error log, không bao giờ lộ stack trace thô cho client |

### 11.2 Các mã lỗi cụ thể đã biết

| Mã | Ở đâu | Ý nghĩa |
|---|---|---|
| `AUTO_LOGIN_DISABLED_PRODUCTION` | `/api/auth/test-auto-login` | Gọi khi `MESFLOW_ENV=production` mà không có override tường minh — xem §11.4 |
| `AUTO_LOGIN_DISABLED` | như trên | Feature flag tự nó đang tắt |
| `AUTO_LOGIN_INVALID_PERSONA` | như trên | `persona` không thuộc 5 giá trị cho phép |
| `AUTO_LOGIN_USER_NOT_FOUND` | như trên | Username đã cấu hình/theo persona không có tài khoản active |
| `INVALID_CREDENTIALS` | `/api/auth/login` | Sai username hoặc password, hoặc tài khoản không active — cùng một thông báo cho cả 3 trường hợp (không bao giờ tiết lộ là trường hợp nào) |
| `QR_REQUIRED` (`error_code: SCN-001`) | Quét Kiosk v1 | Payload QR rỗng |
| `STATE_INVALID_TRANSITION` | Kiosk v2 | Sự kiện không khớp trạng thái hiện tại của thiết bị — xem bảng §7.2 |
| `OPERATION_NOT_WORKABLE` | Kiosk v2 | PO của Operation mục tiêu không phải `IN_PROGRESS` |
| `EMPLOYEE_NOT_FOUND` / `OPERATION_NOT_FOUND` | Kiosk v2 | QR parse được nhưng không có bản ghi khớp |
| `DEVICE_NOT_ALLOWED` | Kiosk v2 | Thiết bị bị vô hiệu/đang bảo trì, hoặc không được ủy quyền |
| `SESSION_NOT_OPEN` | Kiosk v2 | Kỳ vọng một session đang mở, nhưng không có/đã đóng |

---

## 12. Ma trận môi trường

| | DEV (sandbox nội bộ) | DEMO | PRODTEST | Production thật |
|---|---|---|---|---|
| `MESFLOW_ENV` | `local` hoặc `test` | `production` | `production` | chưa xác nhận |
| Autologin bật được chỉ với `MESFLOW_TEST_AUTO_LOGIN=1`? | **Có** | Không — cần override bên dưới | Không — cần override bên dưới | Không bao giờ được bật |
| Flag bổ sung cần thiết | không | `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` | tương tự | — |
| Cơ chế seed dữ liệu | `python -m mesflow.tutorial_data seed` | như trên (namespace theo tiền tố, idempotent) | như trên | — |
| URL điển hình | `http://127.0.0.1:18280` (sandbox QA cách ly) | `http://127.0.0.1:8081` | `https://prod.mesflow.net` / `127.0.0.1:8299` | chưa xác nhận tại thời điểm viết |
| Video hướng dẫn có mount volume bền vững? | có | không (nằm trên layer ephemeral của container — mất khi container bị recreate trừ khi đã sao lưu trước) | có (đã sửa 2026-09-04 — trước đó thiếu mount hoàn toàn) | chưa xác nhận |

**Sự thật quan trọng, không hiển nhiên**: `MESFLOW_ENV=production`
**không** có nghĩa là "đây là hệ thống nghiệp vụ thật đang chạy live"
— đây là giá trị compose mặc định cho mọi tầng dùng chung (bao gồm cả
DEMO và PRODTEST), thực chất hoạt động như một công tắc "chạy ở chế độ
cookie bảo mật/hardened" hơn là một tín hiệu định danh máy chủ. Không
bao giờ suy luận "đây là production thật" chỉ từ `MESFLOW_ENV`.

### 12.1 Autologin (`MESFLOW_TEST_AUTO_LOGIN`) — đặc tả đầy đủ

- Mặc định **tắt** ở mọi nơi.
- Bị từ chối cứng bất cứ khi nào `MESFLOW_ENV=production` trừ khi
  `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` **cũng** được set tường
  minh (một cờ opt-in độc lập thứ hai — không bao giờ chỉ thỏa mãn bởi
  cờ đầu tiên). App ghi cảnh báo bảo mật lúc khởi động và ở mỗi lần
  thử bị từ chối.
- Khi bật: `POST /api/auth/test-auto-login` khởi tạo một session thật
  (cùng lệnh gọi phía server mà đăng nhập bằng mật khẩu dùng) cho một
  tài khoản cấu hình phía server (`MESFLOW_TEST_AUTO_LOGIN_USERNAME`,
  mặc định `admin`), hoặc một `persona` tường minh — xem §12.2.
- `GET /login?noauto=1` luôn render form mật khẩu thật và không bao
  giờ tự kích hoạt, bất kể giá trị flag — nút đăng xuất của chính app
  đã tự thêm tham số này để tránh vòng lặp đăng xuất→autologin.
- Coverage đăng nhập bằng mật khẩu thật luôn được giữ như một nhóm test
  riêng biệt, và không bao giờ được coi là đã được thay thế bởi
  coverage của autologin.

### 12.2 Chuyển nhanh persona (tiện ích kiểm thử RBAC)

`POST /api/auth/test-auto-login` với body/query `persona=<role>` —
các giá trị cho phép **chính xác là**: `admin`, `manager`,
`supervisor`, `operator`, `viewer` (không bao giờ có `super_admin`,
cố tình loại khỏi chuyển nhanh). Được ánh xạ tới tài khoản có
**username đúng bằng** tên persona (mọi môi trường triển khai thật đều
seed một tài khoản chuẩn cho mỗi role, đặt tên theo chính role đó —
quy ước này được phụ thuộc vào, không phải ngẫu nhiên). Cùng cơ chế
bảo vệ như §12.1 — không bao giờ dùng được ở production thật. Giá trị
không nhận diện được → `400 AUTO_LOGIN_INVALID_PERSONA`, body kèm danh
sách cho phép; không có session nào được tạo.

---

## 13. Persona dữ liệu test QC và bộ dữ liệu mẫu

Dùng đúng các giá trị dưới đây khi một testcase cần dữ liệu cụ thể mà
không có chỗ nào khác nêu ra — điều này loại bỏ nhu cầu tự bịa hoặc
phải hỏi lại.

### 13.1 Persona đăng nhập chuẩn (qua chuyển persona autologin, §12.2)

| Persona | Username | Role | Dùng cho |
|---|---|---|---|
| Admin | `admin` | admin | Baseline toàn quyền; mọi REQ nói "admin" |
| Manager | `manager` | manager | Kiểm thử cấu hình nghiệp vụ phạm vi rộng nhất |
| Supervisor | `supervisor` | supervisor | Kiểm thử vận hành sàn xưởng (session, ngoại lệ, kiosk) |
| Operator | `operator` | operator | Kiểm thử ranh giới chỉ-xem-trong-app-quản-trị |
| Viewer | `viewer` | viewer | Kiểm thử ranh giới chỉ đọc |

Phương án dự phòng đăng nhập bằng mật khẩu (khi autologin tắt hoặc cần
test đăng nhập thật): `MESFLOW_ADMIN_USERNAME`/`MESFLOW_ADMIN_PASSWORD`
từ cấu hình riêng của môi trường đích — không bao giờ hardcode mật
khẩu vào một testcase; tham chiếu nó như một secret của môi trường.

### 13.2 Bộ dữ liệu mẫu Production Order

```
Template: TPL-DEMO-01 "Khung kim loại", version 1.0
  Part P-DEMO-01 "Khung chính"
    Operation OP-DEMO-01-CUT   "Cắt phôi"     standard_seconds_per_unit=60
    Operation OP-DEMO-01-BEND  "Uốn"          standard_seconds_per_unit=90, predecessor=OP-DEMO-01-CUT
    Operation OP-DEMO-01-WELD  "Hàn"          standard_seconds_per_unit=120, predecessor=OP-DEMO-01-BEND,
                                                input_flow_enabled=true, input_source=OP-DEMO-01-BEND, input_source_kind=GOOD
    Operation OP-DEMO-01-QC    "Kiểm tra"     standard_seconds_per_unit=30, predecessor=OP-DEMO-01-WELD

PO đã khởi tạo: PO-DEMO-001, product "Khung kim loại", planned_quantity=100, status=PLANNED
```

Dùng `TPL-DEMO-01` → khởi tạo → `PO-DEMO-001` cho mọi journey cần "một
PO"; Start nó (`status → IN_PROGRESS`) trước bất kỳ testcase cấp
session nào.

### 13.3 Nhân viên mẫu (cũng là tài khoản dùng để chuyển persona, §13.1 —
cùng một dòng DB, dùng cho 2 mục đích)

```
EMP-DEMO-01, tên "Nguyễn Văn A", phòng ban "Sản xuất", employment_status "Đang làm" (active=true)
EMP-DEMO-02, tên "Trần Thị B",   phòng ban "QC",       employment_status "Đang làm" (active=true)
EMP-DEMO-03, tên "Lê Văn C",     phòng ban "Sản xuất", employment_status "Đã nghỉ"  (active=false — dùng cho testcase âm REQ-EMP-003 về nhân viên đã nghỉ)
```

### 13.4 Dữ liệu session mẫu bao phủ mọi trường hợp biên của công thức KPI (§8)

| Session | std sec/đơn vị của Operation | good | defect | thời lượng | completion_percent |
|---|---|---|---|---|---|
| A | 60 | 10 | 0 | 20 phút (1200s) | `(60×10)/1200×100 = 50%` |
| B | 60 | 14 | 0 | 20 phút | `(60×14)/1200×100 = 70%` |
| C | 60 | 10 | 0 | 500s | `600/500×100 = 120%` (không clamp — phải hiển thị nguyên vẹn) |
| D | 0 (chưa cấu hình) | 5 | 0 | 10 phút | `NULL` — "Không đủ dữ liệu," không phải 0 |
| E | 60 | 0 | 0 | 5 giờ (>4h) | phép tính vẫn hợp lệ, nhưng **cũng** kích hoạt `ZERO_QUANTITY_LONG` (§9.1) |

Lấy trung bình A+B của một nhân viên trong một ngày → `(50+70)/2 =
60%` — đây là ví dụ mẫu mực để xác minh quy tắc tính trung bình ở §8.

**Định hướng dữ liệu tutorial/demo realistic (bổ sung của bản dịch
này, khớp JOURNEY-009 ở §18)**: khi sinh bộ dữ liệu cho video hướng
dẫn/demo, năng suất trung bình toàn hệ thống nên nằm quanh **~85%**,
với phân bố tự nhiên (không phải một giá trị đồng đều giả tạo) —
nghĩa là phải có cả session dưới 85% lẫn trên 85%, một số ít session
>100% (chính đáng theo công thức, không có trần), không phải toàn bộ
sát đúng 85.0%. Phần lớn thời lượng session nên rơi vào khoảng 4–8
giờ (một ca làm việc điển hình), giờ bắt đầu/kết thúc hợp lý theo ca
thật (không bắt đầu lúc nửa đêm trừ khi đó là ca đêm `cross_midnight`
thật). Khi báo cáo bộ dữ liệu demo, luôn nêu **mean, median, min, max**
thực tế đã sinh ra — không chỉ nêu con số mục tiêu.

### 13.5 Dữ liệu mẫu kích hoạt ngoại lệ (§9.1, mỗi dòng một điều kiện)

- Một session `OPEN`, `started_at` = hiện tại − 13 giờ → `LONG_OPEN_SESSION`.
- Một session `CLOSED`, thời lượng 5 giờ, `good=defect=0` → `ZERO_QUANTITY_LONG`.
- Một session có `station_id=NULL, device_uuid=''` → `MISSING_STATION`.
- Một session có `ended_at` đặt sớm hơn `started_at` 1 phút (chỉ tiếp
  cận được qua thao tác dữ liệu trực tiếp, không phải một đường API
  bình thường — hữu ích để test chính bộ phát hiện) → `INVALID_DURATION`.
- Hai session của cùng `employee_id` có khoảng `[started_at, ended_at)`
  trùng nhau → `EMPLOYEE_SESSION_CONFLICT`.

---

## 14. Tiêu chí chấp nhận phi chức năng (NFR — chỉ những gì kiểm thử được)

Mỗi dòng dưới đây được diễn đạt thành một khẳng định cụ thể, kiểm tra
được — không dùng từ mơ hồ, chưa định lượng kiểu "hợp lý", "nhanh",
"thân thiện người dùng" ở bất kỳ đâu trong tài liệu này; nếu bạn thấy
một từ như vậy, đó là lỗi.

| ID | Tiêu chí |
|---|---|
| NFR-001 | Gọi lại một yêu cầu giống hệt có khóa idempotency (cùng `request_id`) trả về đúng nguyên văn body response gốc kèm `idempotent_replay: true`, và tạo **0** dòng database mới. |
| NFR-002 | Hai lệnh gọi `start()`/`finish()`/`adjust()` đồng thời chạm vào các Operation thuộc **cùng một** Production Order không bao giờ deadlock — lock của dòng PO luôn được lấy trước, theo thứ tự cố định, trước bất kỳ lock nào khác trong cùng lệnh gọi. |
| NFR-003 | Một thay đổi trạng thái (start/finish/adjust/exclude/restore session, start PO, cancel Operation, acknowledge/resolve/ignore ngoại lệ) và dòng audit-log tương ứng của nó luôn được commit trong cùng một database transaction — sau bất kỳ lệnh gọi thành công nào, tồn tại đúng một dòng audit khớp; sau bất kỳ lệnh gọi thất bại/rollback nào, tồn tại 0 dòng. |
| NFR-004 | Cookie session: `HttpOnly` và `SameSite=Lax` trên mọi response, luôn luôn. Cờ `Secure` xuất hiện trên mọi response trừ traffic HTTP trực tiếp tới localhost hoặc mạng nội bộ tin cậy, được loại trừ tường minh phục vụ QA. |
| NFR-005 | Một kiểm tra quyền không thể hoàn tất (dữ liệu RBAC không khả dụng) trả về "từ chối" (`403`), không bao giờ "cho phép." |
| NFR-006 | `GET /api/system/ready` phản hồi trong cửa sổ health-check của chính pipeline deploy (18 lần thử × 10 giây = 180 giây kể từ lúc container khởi động) với `ok: true` trước khi một lần deploy được coi là thành công — đây là hợp đồng (contract) chính xác mà bản thân công cụ deploy kiểm tra. |
| NFR-007 | Một container báo "healthy" ở mức nền tảng (platform) **không** tự nó đủ làm bằng chứng app đang phục vụ đúng — cần một kiểm tra trực tiếp riêng biệt, `GET /api/system/ready` trả về `ok:true` (một trường hợp thật đã quan sát: một container không cấu hình `HEALTHCHECK` nào vẫn báo trạng thái đang chạy). |
| NFR-008 | Không có SLA thời gian tải trang/phản hồi bằng số nào tồn tại trong hệ thống này tại thời điểm viết — không được khẳng định một con số; xem khoảng trống §21. |
| NFR-009 | Coverage test trình duyệt tự động trong codebase này chỉ chạy trên Chromium qua Playwright — không có coverage tự động cho Firefox/Safari; không được giả định đã xác minh tương thích đa trình duyệt. |
| NFR-010 | Viewport desktop chính được hỗ trợ/kiểm thử là chính xác 1366×768; các viewport bổ sung có coverage tự động: 1920×1080 và 390×844 (mobile). Kiểm tra responsive của bất kỳ trang mới nào nên bao phủ tối thiểu 3 viewport này.

---

# PHẦN B — Yêu Cầu Chức Năng

Khóa field cho mỗi khối bên dưới: **Mô-đun**, **Mục đích**, **Đối
tượng thực hiện**, **Điều kiện tiên quyết**, **Đầu vào**, **Kích hoạt
bởi**, **Luồng chính**, **Kết quả mong đợi**, **Chuyển trạng thái**,
**Kiểm tra hợp lệ**, **Lỗi**, **Ranh giới**, **Quyền**, **Đồng thời**,
**Nhật ký kiểm toán**, **Liên quan**, **Độ ưu tiên**, **Khía cạnh kiểm
thử**. Field ghi `N/A` luôn kèm lý do một dòng. Công thức/bảng được
trích dẫn dạng "§N" đều nằm ở Phần A phía trên, trong cùng file này —
không bao giờ ở bên ngoài.

## 15.1 Xác thực & Session (`REQ-AUTH-*`)

### REQ-AUTH-001 — Đăng nhập bằng mật khẩu thật

- **Mô-đun**: Xác thực (Authentication)
- **Mục đích**: Cho phép chủ tài khoản thật thiết lập một session đã xác thực.
- **Đối tượng thực hiện**: bất kỳ tài khoản nào, thuộc 1 trong 6 role (§1.2), `active=true`.
- **Điều kiện tiên quyết**: tồn tại một tài khoản với username/password đã biết và đang active.
- **Đầu vào**: `{username, password}`, cả hai đều là chuỗi không rỗng.
- **Kích hoạt bởi**: `POST /api/auth/login`.
- **Luồng chính**: 1) server tra `users` theo `username`. 2) xác minh `password` với `password_hash`. 3) nếu khớp, tạo session mang `user_id/username/role`. 4) trả về object user kèm `permissions` đã tính (§3.2/§3.3).
- **Kết quả mong đợi**: `200 {"ok":true,"user":{"id","username","role","must_change_password","permissions":[...]}}`; một cookie session được set (`HttpOnly`, `SameSite=Lax`, `Secure` theo NFR-004).
- **Chuyển trạng thái**: không có session → session active (bộ đếm idle/absolute bắt đầu, §3.5).
- **Kiểm tra hợp lệ**: cả 2 field bắt buộc; không có ràng buộc định dạng nào khác ngoài không rỗng.
- **Lỗi**: sai password, username không tồn tại, hoặc tài khoản `active=false` → **giống hệt nhau** `401 {"error":"INVALID_CREDENTIALS"}` cho cả 3 trường hợp (không bao giờ tiết lộ là trường hợp nào).
- **Ranh giới**: password rỗng so với password đúng có độ dài 1 — cả hai đều đi qua cùng đường so sánh hash, không xử lý đặc biệt riêng.
- **Quyền**: N/A — endpoint này không có gate quyền, nó thiết lập danh tính mà các quyền sau này sẽ được kiểm tra dựa trên đó.
- **Đồng thời**: N/A — kiểm tra stateless theo từng request.
- **Nhật ký kiểm toán**: ghi `LOGIN_SUCCESS` hoặc `LOGIN_FAILED` (kèm `reason: invalid_credentials|inactive`) vào audit trail ở mọi lần thử; password gửi lên không bao giờ được log dưới bất kỳ hình thức nào.
- **Liên quan**: BR-901 (xem §16).
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative, boundary (field rỗng).

### REQ-AUTH-002 — Đăng xuất

- **Mô-đun**: Xác thực
- **Mục đích**: Kết thúc session hiện tại theo yêu cầu.
- **Đối tượng thực hiện**: bất kỳ trạng thái session nào, kể cả không có session.
- **Điều kiện tiên quyết**: không có.
- **Đầu vào**: không.
- **Kích hoạt bởi**: `POST /api/auth/logout`.
- **Luồng chính**: 1) server xóa session vô điều kiện.
- **Kết quả mong đợi**: `200 {"ok":true}` bất kể trước đó có session hay không.
- **Chuyển trạng thái**: session active → không có session (hoặc no-op nếu đã không có sẵn).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: không có — lệnh gọi này không thể thất bại.
- **Ranh giới**: gọi 2 lần liên tiếp vẫn an toàn (lần thứ 2 là no-op).
- **Quyền**: N/A — gọi được dù có hay không có session.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A (chưa xác nhận có dòng audit riêng cho logout).
- **Liên quan**: REQ-AUTH-001, BR-902 (chống vòng lặp logout, §16).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive.

### REQ-AUTH-003 — Kiểm tra trạng thái session

- **Mô-đun**: Xác thực
- **Mục đích**: Cho phép frontend xác định session hiện tại có hợp lệ hay không và thuộc về ai.
- **Đối tượng thực hiện**: bất kỳ.
- **Điều kiện tiên quyết**: không có.
- **Đầu vào**: không (dựa vào cookie session).
- **Kích hoạt bởi**: `GET /api/auth/me`.
- **Luồng chính**: 1) kiểm tra session hợp lệ (hết hạn idle/absolute, §3.5). 2) nếu hợp lệ, tra user và trả về role+permissions.
- **Kết quả mong đợi**: `200 {"ok":true,"user":{...}}` khi hợp lệ.
- **Chuyển trạng thái**: N/A (chỉ đọc).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: không có session → `401 {"error":"AUTH_REQUIRED"}`; session hết hạn → `401 {"error":"SESSION_EXPIRED","reason":"idle"|"absolute"}` (session cũng bị xóa như một hệ quả phụ của việc phát hiện hết hạn).
- **Ranh giới**: request đến đúng vào ranh giới timeout idle — implementation xử lý bằng so sánh wall-clock tại thời điểm request, không phải một lượt quét theo lịch riêng; test cả "1 giây trước" và "1 giây sau" ranh giới idle.
- **Quyền**: N/A.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: REQ-AUTH-001.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary.

### REQ-AUTH-004 — Autologin (chỉ dùng để test)

- **Mô-đun**: Xác thực (chỉ dùng để test)
- **Mục đích**: Cho phép QA/Playwright bỏ qua form mật khẩu ở môi trường không phải production. **Không bao giờ là yêu cầu của production.**
- **Đối tượng thực hiện**: 1 trong 5 role không phải super_admin qua persona (§12.2), hoặc tài khoản mặc định đã cấu hình sẵn.
- **Điều kiện tiên quyết**: `MESFLOW_TEST_AUTO_LOGIN=1`; nếu `MESFLOW_ENV=production`, phải thêm `MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1` (§12.1).
- **Đầu vào**: `{persona}` tùy chọn trong JSON body hoặc query string.
- **Kích hoạt bởi**: `POST /api/auth/test-auto-login`.
- **Luồng chính**: 1) kiểm tra bảo vệ (§12.1). 2) nếu có `persona`, xác thực theo allowlist 5 giá trị và ánh xạ tới username cùng tên. 3) nếu không, dùng `MESFLOW_TEST_AUTO_LOGIN_USERNAME` (mặc định `admin`). 4) tra user active đó và khởi tạo session thật y hệt REQ-AUTH-001.
- **Kết quả mong đợi**: cùng cấu trúc response thành công như REQ-AUTH-001.
- **Chuyển trạng thái**: không có session → session active.
- **Kiểm tra hợp lệ**: `persona`, nếu có, phải đúng 1 trong `admin|manager|supervisor|operator|viewer`.
- **Lỗi**: guard fail → `403 AUTO_LOGIN_DISABLED_PRODUCTION` hoặc `403 AUTO_LOGIN_DISABLED`; persona không hợp lệ → `400 AUTO_LOGIN_INVALID_PERSONA` (response kèm danh sách cho phép); username đã ánh xạ không có tài khoản active → `503 AUTO_LOGIN_USER_NOT_FOUND`.
- **Ranh giới**: giá trị persona chỉ khác về hoa/thường (ví dụ `Admin`) — implementation viết thường trước khi so khớp, nên trường hợp này phải thành công, không thất bại.
- **Quyền**: N/A (route này bỏ qua mật khẩu, nhưng không bỏ qua guard môi trường — xem §12.1; `super_admin` không bao giờ tiếp cận được qua persona).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A cho route cụ thể này (khác với REQ-AUTH-001); server có ghi cảnh báo bảo mật lúc boot và mỗi lần thử khi tổ hợp rủi ro được cấu hình trên môi trường gắn cờ `production`.
- **Liên quan**: BR-903/904/905 (§16).
- **Độ ưu tiên**: P0 cho guard/case âm (một lỗi ở đây là một hồi quy bảo mật thật), P2 cho happy path tự nó (tiện ích test, không phải giá trị nghiệp vụ).
- **Khía cạnh kiểm thử**: positive, negative, boundary (phân biệt hoa/thường), RBAC (allowlist persona).

### REQ-AUTH-005 — Đăng xuất không lặp vòng vào lại autologin

- **Mô-đun**: Xác thực (chỉ dùng để test)
- **Mục đích**: Đảm bảo hành động đăng xuất chủ động vẫn tiếp cận được/nhìn thấy được ngay cả khi autologin đang bật.
- **Đối tượng thực hiện**: bất kỳ.
- **Điều kiện tiên quyết**: `MESFLOW_TEST_AUTO_LOGIN=1` và guard đã thỏa (autologin thực sự đang active).
- **Đầu vào**: không.
- **Kích hoạt bởi**: `GET /login?noauto=1`.
- **Luồng chính**: 1) server render trang login với cờ tự-kích-hoạt bị ép tắt chỉ cho lần render này, bất kể giá trị flag toàn cục.
- **Kết quả mong đợi**: HTML render với `data-test-auto-login="0"`; script phía client không tự gửi POST autologin.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: không có.
- **Ranh giới**: `GET /login` (không có query param) trên cùng môi trường vẫn phải hiện `data-test-auto-login="1"` và tự kích hoạt — đây là case đối chứng chứng minh override là thật, không phải một thay đổi toàn cục.
- **Quyền**: N/A.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: REQ-AUTH-004, BR-902.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative (case đối chứng).

## 15.2 Dashboard / Tổng quan (`REQ-DASH-*`)

### REQ-DASH-001 — Trang Tổng quan và Dashboard tải được cho mọi role đã xác thực

- **Mô-đun**: Dashboard
- **Mục đích**: Cho mọi role một màn hình xem tình trạng sản xuất tổng quát (số lượng/tiến độ PO, tổng số lượng) mà không cần điều hướng tới màn chi tiết trước.
- **Đối tượng thực hiện**: bất kỳ role nào có `overview.view`/`dashboard.view` — theo §3.2, đây là **cả 6 role** cho cả 2 quyền.
- **Điều kiện tiên quyết**: session đã xác thực.
- **Đầu vào**: không có gì cho view cơ bản; filter PO/status/sort tùy chọn (xem REQ-DASH-002).
- **Kích hoạt bởi**: điều hướng tới trang `overview` hoặc `dashboard` (§2), hoặc gọi trực tiếp `GET /api/dashboard/overview` / `/api/dashboard/control-tower`.
- **Luồng chính**: 1) client gọi các panel tổng hợp một cách độc lập (`/api/dashboard/summary`, `/production-orders`, `/active-sessions`, `/daily-progress`, `/daily-sessions`, `/shift`, `/recent-activity`). 2) mỗi panel tự render phần của mình.
- **Kết quả mong đợi**: các thẻ KPI cho PO đang chạy / Kế hoạch / Đạt / NG tổng / Phế / Còn lại / Chờ sửa (bộ thẻ đã xác minh trên hệ thống thật); mỗi panel tự đổ dữ liệu độc lập.
- **Chuyển trạng thái**: N/A (chỉ đọc).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: một endpoint của một panel bị lỗi không được phép làm cả trang lỗi 500 — mỗi panel được fetch và render độc lập.
- **Ranh giới**: hệ thống không có PO nào → mọi thẻ KPI hiện 0, không phải trạng thái lỗi.
- **Quyền**: chỉ `login_required` ở mức route; quyền thực chất được thực thi qua việc mục nav có hiển thị hay không (§2) — truy cập API trực tiếp mà không có quyền dường như **không** bị chặn riêng ngoài việc session hợp lệ (xác minh tường minh điều này như một testcase, vì đây là một khác biệt thật, kiểm thử được giữa "ẩn ở nav" và "bị chặn ở API").
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A (view chỉ đọc).
- **Liên quan**: REQ-DASH-002.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, empty-state, RBAC (hiển thị nav theo role).

### REQ-DASH-002 — Lọc theo tầng (cascading) và bảo vệ chống response cũ (stale)

- **Mô-đun**: Dashboard / Quản lý Session (mẫu dùng chung)
- **Mục đích**: Chọn filter PO/Part phải thu hẹp dropdown con chỉ còn con của đúng cha đó, và một thay đổi filter không bao giờ được phép render một response cũ hơn lựa chọn mới nhất của người dùng.
- **Đối tượng thực hiện**: bất kỳ role nào có quyền xem màn hình đang lọc.
- **Điều kiện tiên quyết**: có ít nhất 2 PO với Part/Operation khác nhau, để việc cascading quan sát được.
- **Đầu vào**: query param `po`, `part`, `operation`, `status`, `sort` (tùy màn hình).
- **Kích hoạt bởi**: thay đổi bất kỳ control filter nào.
- **Luồng chính**: 1) chọn một PO thu hẹp dropdown Part chỉ còn Part của đúng PO đó (và Part thu hẹp Operation tương tự). 2) một tổ hợp không tương thích có sẵn trong URL khi load trang được chuẩn hóa lại, không để nguyên trạng thái không nhất quán. 3) mỗi lần đổi filter gửi một request mới.
- **Kết quả mong đợi**: danh sách/bảng đã lọc chỉ phản ánh đúng tổ hợp filter hiện tại.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: N/A.
- **Ranh giới**: đổi filter PO nhanh 2 lần liên tiếp (response đầu chậm không được phép ghi đè response thứ hai nhanh hơn khi nó về sau) — đây là yêu cầu **thật, đã được test riêng**, không phải giả định.
- **Quyền**: kế thừa quyền của màn hình chủ.
- **Đồng thời**: cần bảo vệ chống race ở phía client — một response cho request đã bị thay thế phải bị bỏ qua, không được render.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: BR-016 (§16).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, boundary, concurrency (race).

## 15.3 Production Order (`REQ-PO-*`)

### REQ-PO-001 — Tạo PO chỉ bằng cách khởi tạo từ Template

- **Mô-đun**: Production Order
- **Mục đích**: Mọi PO phải bắt nguồn từ một Template đã hợp lệ, không bao giờ là một bản ghi trống tự tay dựng lên.
- **Đối tượng thực hiện**: admin, manager (`template.edit` — khởi tạo là hành động cần quyền edit template).
- **Điều kiện tiên quyết**: tồn tại một Template active với ≥1 Part/Operation.
- **Đầu vào**: `{template_id}` cộng bất kỳ override cấp PO nào form khởi tạo cho phép (ví dụ `planned_quantity`).
- **Kích hoạt bởi**: `POST /templates/<template_id>/instantiate`.
- **Luồng chính**: 1) copy các Part của template thành dòng `parts` mới gắn với dòng `production_orders` mới. 2) copy các Operation của template thành dòng `operations` mới, giữ nguyên quan hệ phụ thuộc/dòng vật tư đã ánh xạ lại theo ID mới. 3) PO mới nhận `code` mới, `status=PLANNED` (hoặc `DRAFT`), `planned_quantity` theo giá trị đưa vào.
- **Kết quả mong đợi**: `200` kèm id/code PO mới; một `GET` sau đó trên PO này cho thấy mọi Part/Operation đã copy đúng cấu trúc như Template nguồn.
- **Chuyển trạng thái**: (chưa có PO) → PO tồn tại, `status=PLANNED`.
- **Kiểm tra hợp lệ**: `planned_quantity`, nếu override, phải `> 0`.
- **Lỗi**: **gọi trực tiếp** `POST /api/production-orders` (bỏ qua instantiate) bị từ chối thẳng: `ValueError`, "Production Order phải được tạo từ Template để sao chép Part và Operation" — phải test tường minh như case âm, đây không chỉ là chưa được tài liệu hóa, mà thực sự bị chủ động từ chối.
- **Ranh giới**: khởi tạo cùng một Template hai lần phải cho ra hai PO độc lập, không xung đột — giá trị `code` của Operation phải được sinh khác nhau cho mỗi lần khởi tạo (unique toàn cục, §4.3).
- **Quyền**: admin, manager (`template.edit`); supervisor/operator/viewer → `403`.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A là một hành động audit riêng biệt so với tạo PO tổng quát (xác minh có tồn tại, không giả định là không có).
- **Liên quan**: REQ-TPL-001..004, REQ-PART-001.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative (từ chối tạo trực tiếp), RBAC.

### REQ-PO-002 — Start một Production Order

- **Mô-đun**: Production Order
- **Mục đích**: Phát hành một PO đã chuẩn bị xuống sàn xưởng, làm cho các Operation của nó thao tác được tại kiosk.
- **Đối tượng thực hiện**: admin, manager, **supervisor** (mở rộng hơn bộ role chung của `po.edit` — §3.4).
- **Điều kiện tiên quyết**: PO tồn tại, `status` không phải `COMPLETED`/`CANCELLED`, và có ≥1 Operation.
- **Đầu vào**: PO id trong URL, không có body.
- **Kích hoạt bởi**: `POST /production-orders/<id>/start`.
- **Luồng chính**: 1) lock dòng PO. 2) nếu đã `IN_PROGRESS`, trả về thành công ngay (idempotent). 3) nếu `COMPLETED`/`CANCELLED`, từ chối. 4) nếu 0 Operation, từ chối. 5) ngược lại đặt `status=IN_PROGRESS`, ghi domain event `PO_STARTED`.
- **Kết quả mong đợi**: `200 {"ok":true,"item":{...,"status":"IN_PROGRESS"},"operation_count":N,"already_started":false}` (hoặc `true` với case lặp lại idempotent).
- **Chuyển trạng thái**: `DRAFT|PLANNED|RELEASED|PAUSED → IN_PROGRESS`.
- **Kiểm tra hợp lệ**: N/A ngoài các điều kiện tiên quyết ở trên.
- **Lỗi**: PO `COMPLETED`/`CANCELLED` → `409`, "PO đã hoàn thành hoặc đã hủy nên không thể Start"; 0 Operation → `409`, "PO chưa có Operation. Hãy thêm Operation trước khi Start."
- **Ranh giới**: đúng 1 Operation (số lượng tối thiểu khác 0) phải thành công; đúng 0 phải thất bại với thông báo cụ thể ở trên.
- **Quyền**: admin, manager, supervisor thành công; operator, viewer → `403`.
- **Đồng thời**: hai lệnh gọi Start đồng thời trên cùng PO — lệnh thứ hai thấy trạng thái đã `IN_PROGRESS` dưới cùng row lock và đi theo nhánh thành công idempotent, không bao giờ là lỗi race condition.
- **Nhật ký kiểm toán**: domain event `PO_STARTED` kèm `previous_status` và `status` mới trong metadata.
- **Liên quan**: REQ-SESS-001 (Operation chỉ start được khi PO đã `IN_PROGRESS`).
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC, concurrency, chuyển trạng thái.

### REQ-PO-003 — Sửa một Production Order

- **Mô-đun**: Production Order
- **Mục đích**: Cập nhật metadata của PO (status, priority, ngày tháng, ghi chú) sau khi tạo.
- **Đối tượng thực hiện**: admin, manager.
- **Điều kiện tiên quyết**: PO tồn tại.
- **Đầu vào**: bất kỳ tập con nào của `{status, priority, due_date, planned_start_at, planned_end_at, notes, product, code}`.
- **Kích hoạt bởi**: `PATCH /production-orders/<id>`.
- **Luồng chính**: 1) chuẩn hóa/kiểm tra hợp lệ mọi field gửi lên. 2) áp dụng cập nhật.
- **Kết quả mong đợi**: `200` kèm dòng PO đã cập nhật.
- **Chuyển trạng thái**: bất kỳ `status` nào được gửi, nếu hợp lệ — xem ghi chú §5.3 rằng không có đồ thị chuyển trạng thái nào khác được ép ngoài việc thuộc enum.
- **Kiểm tra hợp lệ**: `status` ∈ `{DRAFT,PLANNED,RELEASED,IN_PROGRESS,PAUSED,COMPLETED,CANCELLED}`; `priority` ∈ `{LOW,NORMAL,HIGH,URGENT}`; nếu cả `planned_start_at`/`planned_end_at` đều có, end phải sau start nghiêm ngặt; `code`/`product`, nếu có, phải không rỗng.
- **Lỗi**: giá trị ngoài enum → `ValueError` dạng `400` nêu tên field tiếng Việt ("Trạng thái PO không hợp lệ" / "Mức ưu tiên PO không hợp lệ"); `planned_end_at ≤ planned_start_at` → "Thời gian kết thúc dự kiến phải sau thời gian bắt đầu".
- **Ranh giới**: `planned_end_at` bằng chính xác `planned_start_at` phải bị từ chối (phải sau nghiêm ngặt, không phải "tại hoặc sau").
- **Quyền**: chỉ admin, manager; supervisor/operator/viewer → `403`.
- **Đồng thời**: chưa xác nhận N/A (không quan sát thấy field optimistic-lock nào trên PATCH cụ thể này, khác với sửa session — coi sự vắng mặt này là một sự thật thật sự, kiểm thử được, không phải một thiếu sót của tài liệu).
- **Nhật ký kiểm toán**: chưa xác nhận riêng biệt (xác minh có tồn tại một dòng audit cập nhật entity tổng quát).
- **Liên quan**: REQ-PO-002.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC.

### REQ-PO-004 — Xóa một Production Order (bảo vệ lịch sử)

- **Mô-đun**: Production Order
- **Mục đích**: Ngăn việc phá hủy lịch sử sản xuất thật qua thao tác xóa thông thường.
- **Đối tượng thực hiện**: admin, manager cho xóa có bảo vệ; **chỉ admin** cho biến thể force.
- **Điều kiện tiên quyết**: PO tồn tại.
- **Đầu vào**: PO id.
- **Kích hoạt bởi**: `DELETE /production-orders/<id>` (có bảo vệ) hoặc `DELETE /production-orders/<id>/force` (bỏ qua bảo vệ).
- **Luồng chính (có bảo vệ)**: 1) kiểm tra có bất kỳ session, dòng sổ cái tiêu thụ vật tư, sản lượng khác 0, sự kiện kiosk, adjustment, hay QC inspection nào dưới các Operation của PO này. 2) nếu có, từ chối và nêu rõ loại nào tìm thấy. 3) nếu không, xóa.
- **Kết quả mong đợi (có bảo vệ, không có lịch sử)**: `200`, PO cùng Part/Operation của nó bị xóa (cascade).
- **Chuyển trạng thái**: PO tồn tại → PO không còn tồn tại.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: có bất kỳ lịch sử nào → `409`, "Không thể xóa Production Order vì đã có production history: {các loại tìm thấy}." — thông báo nêu chính xác loại nào (ví dụ "Session, sản lượng").
- **Ranh giới**: một PO có đúng 1 session `CLOSED` (lịch sử tối thiểu khác 0) phải bị từ chối bởi đường có bảo vệ.
- **Quyền**: xóa có bảo vệ: admin, manager. **Xóa force: chỉ admin** — manager phải nhận `403` ở đường force dù manager dùng được đường có bảo vệ (quy tắc hẹp hơn đã xác nhận tường minh ở §3.4).
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận riêng biệt cho delete/force-delete (xác minh).
- **Liên quan**: REQ-PART-002 (cùng hình dạng bảo vệ, thấp hơn 1 cấp).
- **Độ ưu tiên**: P0 (ranh giới role của force-delete là một quy tắc bảo mật thật, từng bị hỏng — rủi ro hồi quy cao).
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC (cụ thể: manager phải thất bại ở force-delete).

## 15.4 Part & Bản vẽ (`REQ-PART-*`)

### REQ-PART-001 — Part thuộc đúng một PO

- **Mô-đun**: Part
- **Mục đích**: Ép buộc phân cấp sở hữu PO→Part.
- **Đối tượng thực hiện**: admin, manager (tạo/sửa); mọi role có quyền xem (đọc).
- **Điều kiện tiên quyết**: một PO tồn tại.
- **Đầu vào**: `{production_order_id, code, name, drawing_path?, sort_order?, active?}`.
- **Kích hoạt bởi**: `POST /<resource=parts>` (tạo resource tổng quát) hoặc như một phần của khởi tạo template (REQ-PO-001).
- **Luồng chính**: 1) `production_order_id` bắt buộc và phải tham chiếu tới một PO tồn tại. 2) `code` phải unique **trong phạm vi PO đó** (không phải toàn cục).
- **Kết quả mong đợi**: `200` kèm dòng Part mới.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: tổ hợp `code`+`production_order_id` unique (`UNIQUE(production_order_id, code)`); `name` bắt buộc.
- **Lỗi**: trùng `(production_order_id, code)` → lỗi xung đột từ DB (unique-violation).
- **Ranh giới**: **cùng** giá trị `code` dùng ở hai PO **khác nhau** phải cùng thành công (uniqueness theo phạm vi từng PO, không phải toàn cục — đây là hành vi **ngược lại chính xác** so với `code` của Operation, vốn unique toàn cục — test tường minh sự đối lập này).
- **Quyền**: admin, manager ghi; mọi role có `template.view`/xem PO đọc nó như một phần của chi tiết PO.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A.
- **Liên quan**: REQ-PO-001, REQ-PART-002, REQ-TPL-003 (upload bản vẽ).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary (đối lập unique theo-PO vs. toàn cục).

### REQ-PART-002 — Xóa một Part (bảo vệ lịch sử)

- **Mô-đun**: Part
- **Mục đích**: Ngăn phá hủy lịch sử sản xuất, thấp hơn bảo vệ ở cấp PO một bậc.
- **Đối tượng thực hiện**: admin, manager.
- **Điều kiện tiên quyết**: Part tồn tại.
- **Đầu vào**: Part id.
- **Kích hoạt bởi**: `DELETE /<resource=parts>/<id>`.
- **Luồng chính**: 1) tổng hợp trên mọi Operation thuộc Part này: số session, dòng sổ cái, sản lượng khác 0, sự kiện kiosk, adjustment, QC inspection. 2) từ chối nếu có, nêu rõ loại nào; nếu không thì xóa.
- **Kết quả mong đợi**: `200` khi thành công (không có lịch sử); Part cùng Operation của nó bị xóa (cascade).
- **Chuyển trạng thái**: Part tồn tại → không còn tồn tại.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: có lịch sử ở bất kỳ Operation con nào → `409`, "Không thể xóa Part vì đã có production history: {các loại tìm thấy}."
- **Ranh giới**: một Part có 2 Operation, chỉ một cái có lịch sử, vẫn phải bị từ chối (tổng hợp trên toàn bộ Operation con, không phải theo từng Operation).
- **Quyền**: admin, manager; supervisor/operator/viewer → `403`.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A.
- **Liên quan**: REQ-PO-004 (cùng hình dạng bảo vệ).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary.

### REQ-PART-003 — Upload file bản vẽ

- **Mô-đun**: Part / Template
- **Mục đích**: Đính kèm bản vẽ kỹ thuật vào một Part của template, lan truyền tới mọi PO tương lai được khởi tạo từ nó.
- **Đối tượng thực hiện**: admin, manager.
- **Điều kiện tiên quyết**: Part của template tồn tại.
- **Đầu vào**: upload file multipart + `template_part_id` đích.
- **Kích hoạt bởi**: `POST /template-parts/upload-drawing`.
- **Luồng chính**: 1) nhận file, lưu trữ, ghi đường dẫn vào `drawing_path` của Part template.
- **Kết quả mong đợi**: `200` kèm đường dẫn/tham chiếu đã lưu.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: ràng buộc loại/kích thước file — chưa xác nhận trong lượt này (xem khoảng trống §21; test thận trọng với ảnh/PDF thật và gắn cờ nếu hệ thống chấp nhận thứ gì đó bất ngờ).
- **Lỗi**: chưa xác nhận N/A ngoài lỗi upload tổng quát.
- **Ranh giới**: chưa xác nhận N/A (có trần kích thước file toàn hệ thống, `MESFLOW_MAX_UPLOAD_BYTES`, mặc định ~200MB — test gần ranh giới đó nếu cần độ chính xác).
- **Quyền**: admin, manager; role khác → `403`.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A.
- **Liên quan**: REQ-PART-001.
- **Độ ưu tiên**: P2.
- **Khía cạnh kiểm thử**: positive, negative, boundary (kích thước file).

## 15.5 Template / Quy trình (`REQ-TPL-*`)

### REQ-TPL-001 — Xem và sửa cây Template

- **Mô-đun**: Template
- **Mục đích**: Định nghĩa cấu trúc Part→Operation tái sử dụng được, mà một PO được khởi tạo từ đó.
- **Đối tượng thực hiện**: xem — bất kỳ role đã xác thực nào (`template.view`, admin/manager/viewer nắm giữ); sửa — admin, manager.
- **Điều kiện tiên quyết**: Template tồn tại.
- **Đầu vào (sửa)**: payload thay thế toàn bộ cây — danh sách Part có thứ tự, mỗi Part có Operation có thứ tự và field của chúng (§4.3 trừ field chỉ-dùng-runtime).
- **Kích hoạt bởi**: `GET /templates/<id>/tree` (xem), `PUT /templates/<id>/tree` (thay thế).
- **Luồng chính (thay thế)**: 1) kiểm tra template này đã từng được khởi tạo thành PO mà Operation của nó hiện có lịch sử Session hay sổ cái chưa. 2) nếu có, từ chối. 3) nếu không, thay thế toàn bộ cây trong một transaction.
- **Kết quả mong đợi**: `200` kèm cây mới khi thành công.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: cấu trúc — xem REQ-TPL-003 (endpoint validate riêng).
- **Lỗi**: có lịch sử trên Operation của PO đã khởi tạo → `409`, "Không thể Replace cấu trúc Operation khi đã có Session hoặc Ledger dòng vật tư. Hãy dùng Merge hoặc tạo PO mới."
- **Ranh giới**: một Template đã được khởi tạo nhưng PO kết quả của nó **chưa có** session nào vẫn phải cho phép Replace (bảo vệ dựa trên lịch sử thật, không phải trên "đã từng được khởi tạo hay chưa").
- **Quyền**: xem: mọi role có `template.view`; sửa: chỉ admin, manager.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A.
- **Liên quan**: REQ-PO-001, REQ-TPL-002/003/004.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC.

### REQ-TPL-002 — Validate một Template

- **Mô-đun**: Template
- **Mục đích**: Phát hiện vấn đề cấu trúc (ví dụ chu trình phụ thuộc) trước khi khởi tạo.
- **Đối tượng thực hiện**: bất kỳ role nào có `template.view`.
- **Điều kiện tiên quyết**: Template tồn tại.
- **Đầu vào**: Template id.
- **Kích hoạt bởi**: `GET /templates/<id>/validate`.
- **Luồng chính**: 1) duyệt đồ thị phụ thuộc Operation (liên kết predecessor + input-source) tìm chu trình/tham chiếu treo. 2) trả về pass/fail kèm chi tiết.
- **Kết quả mong đợi**: `200` kèm object kết quả validate (danh sách lỗi, rỗng nếu hợp lệ).
- **Chuyển trạng thái**: N/A (kiểm tra chỉ đọc).
- **Kiểm tra hợp lệ**: N/A (đây CHÍNH LÀ việc kiểm tra).
- **Lỗi**: N/A — luôn `200`, *nội dung body* báo hiệu tính hợp lệ, không phải HTTP status.
- **Ranh giới**: một template có chu trình phụ thuộc 2 nút (`A→B→A`) phải fail validate; một chuỗi thẳng bất kỳ độ dài nào phải pass.
- **Quyền**: mọi role có `template.view`.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: REQ-TPL-004.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative (case chu trình), boundary.

### REQ-TPL-003 — Khởi tạo một Template thành PO

- Đã được bao phủ đầy đủ ở REQ-PO-001 (khởi tạo chính là đường tạo PO — không nhân đôi testcase, tham chiếu chéo tới REQ-PO-001).

### REQ-TPL-004 — Seed/xóa template demo (chỉ admin)

- **Mô-đun**: Template
- **Mục đích**: Cho phép quản trị viên seed hoặc xóa dữ liệu template demo/tutorial.
- **Đối tượng thực hiện**: **chỉ admin** (§3.4 — hẹp hơn `template.edit` thông thường mà manager cũng có).
- **Điều kiện tiên quyết**: không có cho seed; dữ liệu demo phải tồn tại để wipe có tác dụng.
- **Đầu vào**: không.
- **Kích hoạt bởi**: `POST /templates/demo/seed`, `DELETE /templates/demo`.
- **Luồng chính**: 1) seed chèn một bộ Template/Part/Operation demo đã biết (đặt namespace theo tiền tố); wipe xóa đúng bộ đã namespace đó.
- **Kết quả mong đợi**: `200` khi thành công.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: chưa xác nhận N/A ngoài ranh giới quyền bên dưới.
- **Ranh giới**: gọi seed 2 lần không được tạo trùng lặp (idempotent theo thiết kế — cùng quy ước `tutorial_data.py` dùng ở nơi khác trong hệ thống, §12).
- **Quyền**: **chỉ admin** — manager, dù nắm `template.edit`, phải nhận `403` ở đây (quy tắc đã xác nhận cụ thể, từng bị hỏng trước đây — rủi ro hồi quy cao).
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A.
- **Liên quan**: §12 (quy ước môi trường/seed), REQ-TPL-001.
- **Độ ưu tiên**: P0 (rủi ro hồi quy ranh giới RBAC).
- **Khía cạnh kiểm thử**: positive, RBAC (cụ thể: manager phải thất bại), boundary (idempotency).

### REQ-TPL-005 — Import/export Excel cho Template/Operation

- **Mô-đun**: Template / Import-Export
- **Mục đích**: Round-trip dữ liệu Operation qua workbook Excel.
- **Đối tượng thực hiện**: export: admin, manager, **viewer** (mở rộng, chỉ đọc — §3.4); import: chỉ admin, manager.
- **Điều kiện tiên quyết**: với import, một workbook đúng định dạng theo schema §10.
- **Đầu vào**: export — không có (Template id trong URL); import — file Excel multipart.
- **Kích hoạt bởi**: `GET /export.xlsx`, `export-workbook` theo từng template; `POST /import`, `import` theo từng template.
- **Luồng chính**: xem đầy đủ §10 cho mọi quy tắc theo dòng.
- **Kết quả mong đợi**: export — file `.xlsx` tải về được; import — `200` kèm tóm tắt số dòng áp dụng, hoặc `400` nêu rõ dòng/cột đầu tiên thất bại.
- **Chuyển trạng thái**: import có thể di chuyển Operation giữa PO/Part (§10), tùy thuộc bảo vệ sổ cái.
- **Kiểm tra hợp lệ**: bộ quy tắc đầy đủ ở §10 — field bắt buộc, từ chối done/defect/status, từ chối trùng `operation_id`, từ chối xung đột planned-quantity, di chuyển PO/Part được bảo vệ bởi sổ cái.
- **Lỗi**: mọi quy tắc kiểm tra hợp lệ ở §10 có thông báo tiếng Việt chính xác riêng — dùng nguyên văn các thông báo đó trong assertion của case âm, không dùng "import failed" chung chung.
- **Ranh giới**: một workbook có đúng 1 dòng không hợp lệ giữa nhiều dòng hợp lệ — xác nhận toàn bộ import bị từ chối (transactional), không áp dụng một phần (xác minh đây thực sự là transactional; nếu bằng chứng không kết luận được, gắn cờ là câu hỏi mở thay vì khẳng định theo hướng nào).
- **Quyền**: export: admin/manager/viewer; import: chỉ admin/manager; export-workbook thêm cả viewer.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt.
- **Liên quan**: §10 (phụ lục schema đầy đủ).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative (mọi quy tắc §10), boundary, RBAC.

## 15.6 Nhân viên (`REQ-EMP-*`)

### REQ-EMP-001 — Tạo/sửa một Nhân viên

- **Mô-đun**: Nhân viên
- **Mục đích**: Duy trì danh sách nhân viên mà session kiosk được ghi nhận dựa vào.
- **Đối tượng thực hiện**: admin, manager.
- **Điều kiện tiên quyết**: không có cho tạo.
- **Đầu vào**: `{employee_no, name, department?, position?, employment_status?, qr, birth_date?, hometown?, phone?, identity_number?, identity_issue_date?, current_address?, start_date?, end_date?, contract_1?, contract_2?}` — danh sách field đầy đủ ở §4.5.
- **Kích hoạt bởi**: `POST /<resource=employees>` (tạo), `PATCH /<resource=employees>/<id>` (sửa).
- **Luồng chính**: 1) `employee_no` tự động viết hoa. 2) `employment_status` mặc định `"Đang làm"` nếu bỏ trống. 3) `active` được tính toán, không nhận trực tiếp làm đầu vào: `active = (employment_status != "Đã nghỉ")`. 4) field ngày dạng chuỗi rỗng được ép về `NULL`.
- **Kết quả mong đợi**: `200` kèm dòng đã lưu, `active` phản ánh giá trị đã tính.
- **Chuyển trạng thái**: N/A (không phải entity có state ngoài active/inactive).
- **Kiểm tra hợp lệ**: `employee_no` và `qr` unique; các field khác là văn bản tự do.
- **Lỗi**: trùng `employee_no`/`qr` → xung đột.
- **Ranh giới**: gửi trực tiếp `active: false` trong khi `employment_status` vẫn `"Đang làm"` — quy tắc tính toán phải thắng, tức `active` vẫn ra `true` bất kể field `active` trực tiếp gửi lên (đây là một bẫy thật, kiểm thử được cụ thể).
- **Quyền**: admin, manager ghi; mọi role có `employees.view` (cả 6 role, §3.2) đọc.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt.
- **Liên quan**: REQ-SESS-001 (nhân viên inactive không start được session).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary (bẫy active-được-tính), RBAC.

### REQ-EMP-002 — Nhân viên inactive không start được session

- **Mô-đun**: Nhân viên / Session
- **Mục đích**: Chặn việc ghi nhận công việc dưới tên một nhân viên đã nghỉ việc.
- **Đối tượng thực hiện**: hệ thống tự thực thi, kích hoạt bởi bất kỳ hành động start nào từ kiosk/web.
- **Điều kiện tiên quyết**: một nhân viên có `active=false` (tức `employment_status="Đã nghỉ"`).
- **Đầu vào**: `employee_id` của nhân viên inactive, trong lệnh gọi start session.
- **Kích hoạt bởi**: `POST /work-sessions/start` (hoặc đường quét OP tương đương của Kiosk v2).
- **Luồng chính**: 1) tra nhân viên kiểm tra `active` trước khi tiếp tục. 2) từ chối ngay lập tức, trước khi bất kỳ kiểm tra phía Operation nào chạy.
- **Kết quả mong đợi**: bị từ chối, không tạo dòng session nào.
- **Chuyển trạng thái**: không có (bị chặn trước khi có bất kỳ thay đổi trạng thái nào).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: `RepositoryError`, "employee inactive or missing" (cùng thông báo dù nhân viên inactive hay id đơn giản không tồn tại — không tiết lộ là trường hợp nào).
- **Ranh giới**: một nhân viên vừa bị đổi `employment_status` thành `"Đã nghỉ"` giữa lúc đang có session `OPEN` — start một session **mới** bị chặn, nhưng session đang mở hiện có không bị đụng tới bởi kiểm tra này (không tự động bị đóng).
- **Quyền**: N/A (quy tắc hệ thống, không phải kiểm tra role).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A cho bản thân việc từ chối.
- **Liên quan**: REQ-SESS-001, REQ-EMP-001.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: negative, boundary.

### REQ-EMP-003 — Sinh/in nhãn QR

- **Mô-đun**: Nhân viên / QR
- **Mục đích**: Tạo danh tính QR để in, phục vụ quét tại kiosk.
- **Đối tượng thực hiện**: mọi role có `qr.view` (cả 6 role, §3.2).
- **Điều kiện tiên quyết**: nhân viên tồn tại.
- **Đầu vào**: filter/lựa chọn nhân viên nào cần in.
- **Kích hoạt bởi**: `GET /qr-labels`, `GET /qr-image`.
- **Luồng chính**: 1) sinh payload QR cho mỗi nhân viên theo dạng `WF|EMP|<key>` (định dạng dây §7.2 — cùng định dạng Kiosk v2 parse). 2) render thành nhãn in được.
- **Kết quả mong đợi**: `200` kèm dữ liệu nhãn/ảnh.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: chưa xác nhận N/A.
- **Ranh giới**: một nhân viên không có giá trị `qr` — xác nhận liệu điều này có khả thi không, khi `qr` là `NOT NULL unique` ở mức schema (§4.5) — có khả năng luôn được điền lúc tạo; test rằng luồng tạo thực sự ép điều này chứ không phải chỉ giả định.
- **Quyền**: cả 6 role (`qr.view` được cấp toàn bộ, §3.2).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: §7.2 (định dạng dây QR).
- **Độ ưu tiên**: P2.
- **Khía cạnh kiểm thử**: positive, boundary.

## 15.7 Phiên làm việc (`REQ-SESS-*`)

Chi tiết quy tắc nghiệp vụ đầy đủ nằm ở §6 (Vòng đời Session) và §5.1
(state machine) — mỗi yêu cầu dưới đây là điểm-vào (entry point) để
sinh testcase từ chi tiết đó, không phải bản sao của nó.

### REQ-SESS-001 — Start một session

- **Mô-đun**: Session
- **Mục đích**: Bắt đầu công việc có tính giờ, quy trách nhiệm được, của một nhân viên trên một Operation.
- **Đối tượng thực hiện**: hệ thống kích hoạt bởi Kiosk (v1/v2) hoặc một caller web đã xác thực có năng lực start session (lệnh gọi kiosk dùng xác thực thiết bị/token, không phải role — xem §7).
- **Điều kiện tiên quyết**: danh sách đầy đủ ở §6.1 (nhân viên active, PO `IN_PROGRESS`, nguồn dòng vật tư đã start nếu áp dụng, predecessor tồn tại nếu áp dụng, sẵn sàng điều phối, nhân viên không có session `OPEN` nào khác, không trùng thời gian).
- **Đầu vào**: `{employee_id, operation_id, station_id?, device_uuid?, request_id, occurred_at?}`.
- **Kích hoạt bởi**: `POST /work-sessions/start`, hoặc quét `OP` của Kiosk v2 khi đang ở trạng thái `WAIT_OPERATION` (§7.2).
- **Luồng chính**: §6.1, các bước 1–7 theo đúng thứ tự — test case âm của từng điều kiện tiên quyết độc lập, không chỉ happy path đầy đủ.
- **Kết quả mong đợi**: dòng `work_sessions` mới, `status=OPEN`; trạng thái Operation tính lại theo §5.2 (thường → `IN_PROGRESS`).
- **Chuyển trạng thái**: (chưa có session) → `OPEN`; trạng thái Operation theo quy tắc #2 ở §5.2.
- **Kiểm tra hợp lệ**: `request_id` bắt buộc và không rỗng.
- **Lỗi**: xem danh sách có thứ tự ở §6.1 — mỗi điều kiện tiên quyết có thông báo chính xác riêng, đã tái hiện ở đó.
- **Ranh giới**: một nhân viên **đã có đúng một** session `OPEN` cố start thêm session thứ hai — phải thất bại (unique index ép ở DB theo §4.4, không chỉ logic ứng dụng — xác minh bằng cách thử bypass kiểm tra ứng dụng nếu test harness cho phép truy cập DB trực tiếp, để xác nhận chính bản thân ràng buộc DB, không chỉ kiểm tra ở mức app).
- **Quyền**: N/A tại chính lệnh gọi này (kiosk dùng xác thực thiết bị); route web tương đương yêu cầu session đã xác thực.
- **Đồng thời**: gọi lại đúng `request_id` → cùng response, `idempotent_replay:true`, 0 dòng mới (NFR-001). Hai lệnh start đồng thời cho cùng nhân viên — unique index của DB đảm bảo chỉ một cái thắng.
- **Nhật ký kiểm toán**: dòng audit `SESSION_STARTED` + domain event, cùng transaction với việc insert.
- **Liên quan**: §6.1, §5.1, REQ-EMP-002, REQ-PO-002.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative (mọi điều kiện tiên quyết), boundary, concurrency, idempotency, chuyển trạng thái.

### REQ-SESS-002 — Finish một session

- **Mô-đun**: Session
- **Mục đích**: Đóng một khối công việc kèm số liệu đạt/lỗi/sửa cuối cùng.
- **Đối tượng thực hiện**: giống REQ-SESS-001 (thiết bị kiosk hoặc caller web đã xác thực).
- **Điều kiện tiên quyết**: session mục tiêu tồn tại và đang `OPEN`.
- **Đầu vào**: `{request_id, good_qty?, defect_qty?, rework_qty?, note?, occurred_at?}`.
- **Kích hoạt bởi**: `POST /work-sessions/<id>/finish`, hoặc sự kiện `QUANTITY_SUBMITTED` của Kiosk v2.
- **Luồng chính**: đầy đủ ở §6.2.
- **Kết quả mong đợi**: `status=CLOSED`, `quantity_confirmed=TRUE`, số liệu được ghi nhận; trạng thái Operation tính lại.
- **Chuyển trạng thái**: `OPEN → CLOSED` (đường thủ công, nhánh trái §5.1).
- **Kiểm tra hợp lệ**: số liệu được clamp ≥0; `rework_qty ≤ defect_qty` (nếu không → `ValueError`).
- **Lỗi**: session đã `CLOSED` → `409`, "session already closed"; thiếu vật tư dòng vào → `409` nêu rõ số lượng còn lại chính xác (công thức §8, tham chiếu chéo trong §6.2); trùng thời gian → bị từ chối.
- **Ranh giới**: `rework_qty` bằng chính xác `defect_qty` phải thành công; `rework_qty = defect_qty + 1` phải thất bại.
- **Quyền**: N/A tại chính lệnh gọi này (xem REQ-SESS-001).
- **Đồng thời**: cùng đảm bảo idempotency theo `request_id` như start.
- **Nhật ký kiểm toán**: dòng audit `SESSION_FINISHED` + một domain event cho mỗi loại quantity-movement được ghi, cùng transaction.
- **Liên quan**: §6.2, BR-005/BR-006 (quy tắc số lượng), REQ-EXC-001 (`ZERO_QUANTITY_LONG` nếu 0/0 sau >4h).
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative, boundary, concurrency, idempotency, chuyển trạng thái.

### REQ-SESS-003 — Finish hàng loạt (atomic)

- **Mô-đun**: Session
- **Mục đích**: Đóng nhiều session như một thao tác tất-cả-hoặc-không-gì.
- **Đối tượng thực hiện**: cùng caller như finish.
- **Điều kiện tiên quyết**: mọi session mục tiêu hiện đang `OPEN`.
- **Đầu vào**: mảng cặp `(session_id, data)`, mỗi cặp có hình dạng như đầu vào của REQ-SESS-002.
- **Kích hoạt bởi**: `POST /session/group/finish`.
- **Luồng chính**: §6.3 — một transaction dùng chung cho cả mảng.
- **Kết quả mong đợi**: mảng response từng phần tử theo đúng thứ tự đầu vào, tất cả đều thành công.
- **Chuyển trạng thái**: mọi session mục tiêu `OPEN → CLOSED` cùng lúc, hoặc không cái nào.
- **Kiểm tra hợp lệ**: cùng quy tắc từng phần tử như REQ-SESS-002.
- **Lỗi**: **phần tử đầu tiên thất bại rollback toàn bộ batch** — một batch 5 phần tử mà phần tử 3 fail phải để cả 5 session vẫn `OPEN`, không phải 2 đóng + 3 treo.
- **Ranh giới**: batch đúng 1 phần tử hành xử y hệt một lệnh finish đơn; mảng rỗng — xác nhận hành vi (có thể là no-op `200`, xác minh thay vì giả định).
- **Quyền**: N/A tại chính lệnh gọi này.
- **Đồng thời**: cả batch là một transaction — không thể có race commit-một-phần theo cấu trúc.
- **Nhật ký kiểm toán**: một `SESSION_FINISHED` (+ movement event) cho mỗi phần tử đóng thành công, trong cùng transaction.
- **Liên quan**: REQ-SESS-002.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative (chứng minh rollback), boundary.

### REQ-SESS-004 — Sửa số lượng bởi supervisor (adjust)

- **Mô-đun**: Session
- **Mục đích**: Cho phép supervisor/admin sửa số liệu sai sau khi sự việc đã xảy ra, kèm lý do bắt buộc và audit trail đầy đủ.
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: session tồn tại (có thể `OPEN` hoặc `CLOSED`).
- **Đầu vào**: `{good_qty?, defect_qty?, rework_qty?, reason, request_id?}` — `reason` **bắt buộc**.
- **Kích hoạt bởi**: `POST /supervisor/sessions/<id>/adjust`.
- **Luồng chính**: đầy đủ ở §6.5.
- **Kết quả mong đợi**: `200` kèm bản ghi adjustment (cũ/mới cho mỗi field số lượng) và session đã cập nhật.
- **Chuyển trạng thái**: `quantity_confirmed → TRUE` vô điều kiện (bất kể giá trị trước đó) — đây là hiệu ứng trạng thái chính của hành động này, khác với bản thân `status`.
- **Kiểm tra hợp lệ**: `reason` không rỗng (nếu không → `ValueError`, "reason required"); `rework_qty ≤ defect_qty` (cùng quy tắc như finish).
- **Lỗi**: reason rỗng → `ValueError`; rework vượt quá → `ValueError`.
- **Ranh giới**: sửa một session **auto-close, chưa xác nhận** (`quantity_confirmed=FALSE`) là trường hợp thực tế chính yếu mà tính năng này tồn tại để xử lý — xác nhận nó chuyển thành `TRUE` sau đó (đường xử lý case `AUTO_CLOSED_UNCONFIRMED` ở §6.4/§9.1).
- **Quyền**: admin, manager, supervisor; operator, viewer → `403`.
- **Đồng thời**: `request_id` tùy chọn cho cùng đảm bảo idempotent-replay như start/finish.
- **Nhật ký kiểm toán**: dòng `operation_adjustments` (cũ/mới cho good/defect/rework, `reason`, `adjusted_by`) + domain event `VALUE_CHANGED`, cùng transaction.
- **Liên quan**: §6.5, §6.4 (hành trình auto-close→sửa), REQ-SESS-002.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC, chuyển trạng thái (cờ confirmed), audit.

### REQ-SESS-005 — Sửa toàn bộ session (optimistic concurrency)

- **Mô-đun**: Session
- **Mục đích**: Sửa phạm vi rộng hơn adjust-chỉ-số-lượng, có bảo vệ chống ghi đè cũ (stale write).
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: session tồn tại.
- **Đầu vào**: các field session sửa được + `expected_updated_at` tùy chọn.
- **Kích hoạt bởi**: `PATCH /supervisor/sessions/<id>`.
- **Luồng chính**: §6.6.
- **Kết quả mong đợi**: `200` kèm session đã cập nhật khi thành công.
- **Chuyển trạng thái**: bất kỳ field nào đã đổi.
- **Kiểm tra hợp lệ**: nếu `expected_updated_at` được gửi và không khớp `updated_at` thực tế hiện tại của dòng, từ chối.
- **Lỗi**: không khớp → xung đột (ai đó đã sửa trước) — **không được** âm thầm ghi đè.
- **Ranh giới**: hai supervisor cùng load một session, một người lưu trước, lưu của người thứ hai (với `expected_updated_at` giờ đã cũ) phải bị từ chối, không được âm thầm áp dụng đè lên lưu đầu.
- **Quyền**: admin, manager, supervisor; operator, viewer → `403`.
- **Đồng thời**: đây là cơ chế đồng thời chính cần test — một race 2-actor thật, không phải một request bị retry bởi 1 actor.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt so với hình dạng audit của `adjust` — xác minh chính xác tên hành động audit mà route cụ thể này ghi.
- **Liên quan**: §6.6, REQ-SESS-004.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC, concurrency.

### REQ-SESS-006 — Chuyển Operation ("giao nhầm Operation")

- **Mô-đun**: Session
- **Mục đích**: Sửa một session bị lỡ ghi nhận nhầm Operation.
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: session tồn tại; Operation đích tồn tại.
- **Đầu vào**: `{new_operation_id, reason?}`.
- **Kích hoạt bởi**: `POST /supervisor/sessions/<id>/transfer-operation`.
- **Luồng chính**: §6.7 — gán lại `operation_id`, tính lại trạng thái cả Operation cũ lẫn mới.
- **Kết quả mong đợi**: `200` với session giờ trỏ tới Operation mới.
- **Chuyển trạng thái**: `operation_id` của session đổi; `status` của cả Operation cũ và mới tính lại theo §5.2.
- **Kiểm tra hợp lệ**: chưa xác nhận N/A ngoài việc Operation đích tồn tại.
- **Lỗi**: chưa xác nhận N/A riêng biệt.
- **Ranh giới**: chuyển sang **chính Operation** nó đang thuộc về — xác nhận đây là no-op vô hại hay bị từ chối tường minh (xác minh thay vì giả định theo hướng nào).
- **Quyền**: admin, manager, supervisor; operator, viewer → `403`.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: ghi lại Operation trước/sau trên dòng audit.
- **Liên quan**: §6.7, JOURNEY (§18) "giao nhầm Operation."
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC, audit.

### REQ-SESS-007 — Loại trừ / khôi phục một session khỏi báo cáo

- **Mô-đun**: Session
- **Mục đích**: Cho phép supervisor đánh dấu dữ liệu của một session là không-tính (ví dụ quét trùng/test) mà không xóa nó.
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: exclude — session chưa bị loại trừ; restore — session hiện đang bị loại trừ.
- **Đầu vào**: `{reason}` — bắt buộc cho cả hai chiều.
- **Kích hoạt bởi**: `POST /supervisor/sessions/<id>/exclude`, `.../restore`.
- **Luồng chính**: §6.8.
- **Kết quả mong đợi**: `200`; `excluded_from_reports` đảo giá trị; `status` của session không đổi, dòng không bao giờ bị xóa.
- **Chuyển trạng thái**: `excluded_from_reports: FALSE→TRUE` (exclude) hoặc `TRUE→FALSE` (restore); độc lập với `status`.
- **Kiểm tra hợp lệ**: `reason` bắt buộc cho cả hai chiều.
- **Lỗi**: exclude một session đã bị loại trừ → `409`, "Session đã được loại khỏi báo cáo"; restore một session chưa bị loại trừ → `409`, "Session hiện không bị loại khỏi báo cáo".
- **Ranh giới**: exclude → restore → exclude lại theo trình tự phải mỗi lần đều thành công (không có khóa một-chiều vĩnh viễn).
- **Quyền**: admin, manager, supervisor; operator, viewer → `403`.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: domain event `SESSION_EXCLUDED`/`SESSION_RESTORED` kèm lý do.
- **Liên quan**: §6.8, BR-010 (§16), REQ-PROD-001 (session bị loại trừ biến mất khỏi KPI).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative (exclude/restore kép), boundary, RBAC, audit.

## 15.8 Kiosk (`REQ-KIOSK-*`)

Luồng làm việc đầu-cuối đầy đủ với mọi nhánh nằm ở §7 — các yêu cầu
dưới đây là điểm-vào để sinh testcase từ đó.

### REQ-KIOSK-001 — Kiosk v1 quét/start/finish (trình duyệt)

- **Mô-đun**: Kiosk v1
- **Mục đích**: Luồng kiosk trên trình duyệt, thân thiện cho thủ công/demo.
- **Đối tượng thực hiện**: không kiểm tra role — luồng thiết bị hướng trình duyệt, không xác thực (§7.1).
- **Điều kiện tiên quyết**: tồn tại giá trị QR nhân viên/Operation hợp lệ.
- **Đầu vào**: `{qr}` mỗi lần quét; đầu vào start/finish giống hệt REQ-SESS-001/002.
- **Kích hoạt bởi**: `POST /api/kiosk-web/scan`, `/start`, `/finish/<id>`.
- **Luồng chính**: bảng 3 bước ở §7.1.
- **Kết quả mong đợi**: cùng kết quả vòng đời session như route web session, tiếp cận qua các endpoint hình dạng kiosk.
- **Chuyển trạng thái**: giống hệt REQ-SESS-001/002.
- **Kiểm tra hợp lệ**: `qr` bắt buộc và không rỗng cho scan.
- **Lỗi**: `qr` rỗng → `400 QR_REQUIRED`, `error_code SCN-001`, "Chưa nhận được mã quét", gợi ý hành động "Kiểm tra nguồn và dây máy quét, rồi quét lại."; mọi lỗi phía sau giống hệt REQ-SESS-001/002.
- **Ranh giới**: giống REQ-SESS-001/002 (đây là cùng logic nghiệp vụ, tiếp cận qua một cửa khác).
- **Quyền**: N/A (không gate role trên luồng này).
- **Đồng thời**: cùng đảm bảo idempotency như REQ-SESS-001/002.
- **Nhật ký kiểm toán**: giống REQ-SESS-001/002.
- **Liên quan**: §7.1, REQ-SESS-001/002.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative, boundary.

### REQ-KIOSK-002 — State machine thiết bị Kiosk v2 (giao thức ESP32)

- **Mô-đun**: Kiosk v2
- **Mục đích**: Giao thức kiosk hướng phần cứng thật, một thiết bị dùng chung phục vụ tuần tự nhiều nhân viên.
- **Đối tượng thực hiện**: thiết bị đã xác thực (token riêng từng thiết bị), không phải role người dùng.
- **Điều kiện tiên quyết**: thiết bị đã đăng ký và không ở `DEVICE_DISABLED`/`MAINTENANCE`.
- **Đầu vào**: các sự kiện — `SCAN {raw}`, `FINISH_REQUESTED`, `QUANTITY_SUBMITTED {...}`, `CANCEL_REQUESTED`, mỗi cái mang một `event_id` riêng.
- **Kích hoạt bởi**: `POST /api/kiosk/v2/events`.
- **Luồng chính**: bảng chuyển trạng thái đầy đủ ở §7.2 — mỗi dòng phải là một testcase riêng, cả chuyển trạng thái được phép lẫn việc từ chối đã liệt kê tường minh của nó.
- **Kết quả mong đợi**: trạng thái projection thiết bị mới + (nếu áp dụng) một session thật được tạo/finish theo quy tắc REQ-SESS-001/002.
- **Chuyển trạng thái**: toàn bộ bảng ở §7.2.
- **Kiểm tra hợp lệ**: QR phải parse được thành `WF|EMP|<key>` hoặc `WF|OP|<key>` (§7.2); bất kỳ gì khác → không parse được, bị từ chối.
- **Lỗi**: `STATE_INVALID_TRANSITION`, `OPERATION_NOT_WORKABLE`, `EMPLOYEE_NOT_FOUND`, `OPERATION_NOT_FOUND`, `DEVICE_NOT_ALLOWED`, `SESSION_NOT_OPEN` — mỗi cái có điều kiện kích hoạt riêng ở §7.2/§11.2.
- **Ranh giới**: một lần quét `EMP` cho một nhân viên đang có session mở **trên một thiết bị khác** với thiết bị đang quét — quy tắc resolve-tươi-mới (§7.2) nghĩa là nó vẫn phải đi tới `QUANTITY_INPUT` trên **thiết bị này**, chứng minh trạng thái thiết bị là theo-từng-thiết-bị, không dính theo-nhân-viên.
- **Quyền**: N/A (xác thực bằng token thiết bị, không theo role).
- **Đồng thời**: idempotent theo `(device_id, event_id)` — một sự kiện trùng/gọi lại không được áp dụng hai lần.
- **Nhật ký kiểm toán**: mỗi hành động scan/session thành công ghi dòng sự kiện kiosk `SCAN_EMPLOYEE`/`SCAN_OPERATION`/v.v. riêng.
- **Liên quan**: §7.2 đầy đủ, REQ-SESS-001/002.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative (mọi dòng bị từ chối), boundary, concurrency, chuyển trạng thái (mọi dòng bảng).

### REQ-KIOSK-003 — Tính đúng đắn của kiosk dùng chung (nhiều nhân viên nối tiếp)

- **Mô-đun**: Kiosk v2
- **Mục đích**: Chứng minh một thiết bị kiosk vật lý có thể phục vụ nhân viên A, rồi B, rồi C theo trình tự, mỗi lần quét thẻ sau đó của một nhân viên chỉ resolve tới đúng session mở của họ, không bao giờ tới session của nhân viên khác hay trạng thái thiết bị còn sót lại từ trước.
- **Đối tượng thực hiện**: thiết bị (nhiều nhân viên dùng lần lượt).
- **Điều kiện tiên quyết**: nhân viên A, B, C đều tồn tại và active; có ít nhất một Operation thao tác được.
- **Đầu vào**: chuỗi quét tuần tự: A(EMP)→A(OP, start một session)→B(EMP)→B(OP, start một session)→C(EMP)→C(OP, start một session).
- **Kích hoạt bởi**: chuỗi lệnh gọi `POST /api/kiosk/v2/events` trên **cùng một** `device_id`.
- **Luồng chính**: sau mỗi lần quét OP của một nhân viên, thiết bị reset về `WAIT_EMPLOYEE` (§7.2) — lượt quét ngay sau đó được đánh giá hoàn toàn mới dựa trên bất kỳ nhân viên nào vừa quét, không bao giờ bị ảnh hưởng bởi session còn mở của nhân viên trước.
- **Kết quả mong đợi**: tồn tại 3 session `OPEN` độc lập (mỗi nhân viên một cái), tất cả trên cùng `device_uuid`/`station_id`; lần quét `EMP` sau đó của mỗi nhân viên trên cùng thiết bị này set `employee_id`/`work_session_id` của thiết bị thành **đúng session của chính họ**, không bao giờ là session của nhân viên khác.
- **Chuyển trạng thái**: thiết bị luân chuyển `WAIT_EMPLOYEE → WAIT_OPERATION → WAIT_EMPLOYEE` 3 lần liên tiếp, mỗi lần một nhân viên.
- **Kiểm tra hợp lệ**: N/A ngoài REQ-KIOSK-002.
- **Lỗi**: N/A (đây là case dương, từng bị hỏng trước đây — một hồi quy ở đây sẽ khiến hiện sai `SESSION_EMPLOYEE_MISMATCH` hoặc tương tự, theo đúng sự cố lịch sử mà quy tắc này đã được sửa để khắc phục).
- **Ranh giới**: B quét thẻ trong khi session của A vẫn còn mở trên cùng thiết bị chính là case từng-bị-hỏng — phải thành công gọn gàng.
- **Quyền**: N/A.
- **Đồng thời**: N/A (tuần tự do bản chất một máy quét vật lý).
- **Nhật ký kiểm toán**: 3 chuỗi sự kiện `SCAN_EMPLOYEE`/`SCAN_OPERATION` độc lập.
- **Liên quan**: §7.2, REQ-KIOSK-002. Đây là kịch bản demo **bắt buộc phải có** "chuyển qua nhiều nhân viên" cho video hướng dẫn.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, boundary (case hồi quy lịch sử cụ thể).

### REQ-KIOSK-004 — Wallboard năng suất nhân viên tại Kiosk

- **Mô-đun**: Kiosk / Năng suất nhân viên
- **Mục đích**: Màn hình TV sàn xưởng hiển thị năng suất nhân viên đã xếp hạng, làm mới liên tục, không cần đăng nhập (công khai trong mạng tin cậy).
- **Đối tượng thực hiện**: không xác thực (cố ý — đây là một màn hình sàn xưởng).
- **Điều kiện tiên quyết**: tồn tại một cấu hình wallboard đã publish (hoặc dùng mặc định); có session tính vào báo cáo trong khoảng thời gian.
- **Đầu vào**: không có từ người xem; cấu hình được set riêng bởi admin/manager (`POST /reports/employee-productivity/wallboard-config`).
- **Kích hoạt bởi**: `GET /api/wallboard/employee-productivity`, và trang `/kiosk/employee-productivity`.
- **Luồng chính**: đọc đúng truy vấn của công thức §8 — danh sách nhân viên đã xếp hạng, sort/cột/số dòng mỗi trang/chu kỳ tự lật trang cấu hình được.
- **Kết quả mong đợi**: cùng con số với báo cáo Năng suất nhân viên đã xác thực cho cùng khoảng ngày (REQ-PROD-001) — không bao giờ được lệch nhau.
- **Chuyển trạng thái**: N/A (chỉ đọc).
- **Kiểm tra hợp lệ**: N/A cho đường đọc.
- **Lỗi**: chưa xác nhận N/A.
- **Ranh giới**: một "Preview" của một thay đổi cấu hình chưa publish **không được phép** làm thay đổi những gì wallboard công khai hiện đang hiển thị (yêu cầu đã xác nhận, đã test riêng cụ thể).
- **Quyền**: **không yêu cầu xác thực** cho chính endpoint dữ liệu — đây là cố ý, không phải lỗi; không gắn cờ đây là lỗ hổng bảo mật nếu chưa xác nhận đây không phải thiết kế có chủ đích (đúng là có chủ đích, theo xác nhận trực tiếp từ mã nguồn).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A (chỉ đọc).
- **Liên quan**: §8 (công thức KPI), REQ-PROD-001, REQ-KIOSK-003 (demo nhiều-nhân-viên-nối-tiếp mà wallboard này nên phản ánh được sau đó).
- **Độ ưu tiên**: P0 — đây chính là chủ đề chương video hướng dẫn **bắt buộc** "Kiosk năng suất nhân viên".
- **Khía cạnh kiểm thử**: positive, boundary (preview không làm thay đổi dữ liệu thật), truy cập không xác thực (xác nhận là có chủ đích).

## 15.9 Ca làm việc / Auto-close (`REQ-SHIFT-*`)

Chi tiết đầy đủ ở §6.4 và schema `work_shifts`/`work_shift_intervals`
ở §4.10 — các yêu cầu dưới đây là điểm-vào để sinh testcase.

### REQ-SHIFT-001 — Định nghĩa ca và sửa khoảng thời gian (interval)

- **Mô-đun**: Lịch làm việc
- **Mục đích**: Định nghĩa cấu trúc khoảng WORK/BREAK của từng ca, kể cả ca qua đêm (cross-midnight).
- **Đối tượng thực hiện**: xem — mọi role có `calendar.view` (admin/manager/supervisor/viewer); sửa — admin, manager.
- **Điều kiện tiên quyết**: không có.
- **Đầu vào**: `{code, name, anchor_start, anchor_end, cross_midnight, target_minutes, working_weekdays[], intervals:[{interval_type, start_minute, end_minute, label}]}`.
- **Kích hoạt bởi**: `GET/PUT /settings/work-shifts`.
- **Luồng chính**: interval là phút tương đối theo ca, không phải wall-clock; ca `cross_midnight=true` (ví dụ ca `NIGHT` đã seed 18:00–03:00) vượt quá phút 1440.
- **Kết quả mong đợi**: `200` kèm định nghĩa ca đã lưu.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: mỗi interval `end_minute > start_minute` (CHECK constraint của DB); `interval_type` ∈ `{WORK, BREAK}`.
- **Lỗi**: interval vi phạm `end > start` → bị từ chối.
- **Ranh giới**: hai interval chồng lấn thời gian trong cùng một ca, và một khoảng trống giữa 2 interval — cả hai đều là case thật, được xử lý khác nhau mà chính editor ca trên UI đã validate (cảnh báo với gap, báo lỗi với overlap theo đúng logic validate của editor) — test cả hai.
- **Quyền**: admin, manager ghi; admin/manager/supervisor/viewer đọc.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt.
- **Liên quan**: §4.10, REQ-SHIFT-002.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary (overlap vs. gap), RBAC.

### REQ-SHIFT-002 — Auto-close một session quá giờ kết thúc ca + ân hạn

- **Mô-đun**: Session / Ca làm việc
- **Mục đích**: Ép đóng các session bị bỏ quên quá giờ kết thúc ca, không tự bịa dữ liệu hay ngụy trang thành finish thủ công.
- **Đối tượng thực hiện**: job hệ thống (`shift_session_reconciliation`), không do người dùng kích hoạt.
- **Điều kiện tiên quyết**: `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1` và `MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN=0` (cả hai đều bắt buộc — mặc định an toàn khi rollout để tắt tính năng này, §6.4); một session đang `OPEN` và giờ kết thúc ca đã resolve của nó + thời gian ân hạn đã trôi qua.
- **Đầu vào**: không có (do hệ thống điều khiển; tự tính `shift_end_at` cho từng session từ dữ liệu ca/interval ở §4.10).
- **Kích hoạt bởi**: lần chạy job theo lịch (không phải một lệnh API mà test có thể gọi trực tiếp theo cùng cách — test qua chính entry point của job, hoặc bằng cách tua nhanh đồng hồ của fixture, theo khả năng của test harness).
- **Luồng chính**: đầy đủ ở §6.4.
- **Kết quả mong đợi**: session `CLOSED`, số liệu giữ nguyên như trước, `close_reason='AUTO_SHIFT_END'`, `closed_by_system=TRUE`, `quantity_confirmed=FALSE`.
- **Chuyển trạng thái**: `OPEN → CLOSED` qua nhánh auto-close của §5.1 (khác với nhánh finish thủ công).
- **Kiểm tra hợp lệ**: `shift_end_at` phải sau `started_at` của session một cách nghiêm ngặt (nếu không job raise lỗi thay vì ghi một khoảng thời gian bất khả thi — đây là guard nhất quán nội bộ, không phải kiểm tra hợp lệ hướng người dùng).
- **Lỗi**: trùng thời gian với session khác của cùng nhân viên → bị từ chối, giống như finish thủ công.
- **Ranh giới**: một session được operator finish thủ công đúng vào đúng thời điểm job reconciliation lẽ ra sẽ auto-close nó — advisory lock của job + kiểm tra lại `status != OPEN` làm cho đây là một no-op an toàn cho job (§6.4), không bao giờ là đóng-hai-lần hay lỗi.
- **Quyền**: N/A (chỉ hệ thống).
- **Đồng thời**: advisory lock theo từng session; các lần chạy reconciliation đồng thời không bao giờ được đóng trùng cùng một session.
- **Nhật ký kiểm toán**: domain event `SESSION_AUTO_CLOSED` (loại khác `SESSION_FINISHED`) + dòng audit.
- **Liên quan**: §6.4, REQ-SESS-004 (bước sửa theo sau), REQ-EXC-002 (`SESSION_PAST_SHIFT_END` khi vẫn còn mở).
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, boundary, concurrency, chuyển trạng thái, audit. Đây là **kịch bản lỗi vận hành bắt buộc phải có trong video hướng dẫn**: "quên nhập sản lượng khi kết thúc" / "session vượt giờ kết thúc ca."

## 15.10 Xử lý Ngoại lệ (`REQ-EXC-*`)

Bảng điều kiện phát hiện đầy đủ ở §9.1; vòng đời ở §5.4/§5.5.

### REQ-EXC-001 — Trung tâm ngoại lệ: phát hiện

- **Mô-đun**: Trung tâm ngoại lệ
- **Mục đích**: Tự động phát hiện 7 điều kiện bất thường đã biết thành bản ghi bền vững, khử trùng lặp.
- **Đối tượng thực hiện**: hệ thống kích hoạt; xem bởi mọi role có `exceptions.view` (admin/manager/supervisor/viewer).
- **Điều kiện tiên quyết**: một trong 7 điều kiện kích hoạt ở §9.1 đúng cho một session/Operation tính vào báo cáo.
- **Đầu vào**: không có (reconcile liên tục).
- **Kích hoạt bởi**: chu kỳ reconciliation (nền) hoặc `GET /exceptions` (danh sách, phản ánh trạng thái vừa phát hiện + đã ghi nhận trước đó).
- **Luồng chính**: bảng điều kiện ở §9.1, mỗi cái tạo `fingerprint = "<type>:SESSION:<session_id>"`.
- **Kết quả mong đợi**: một dòng `exception_records` mới cho mỗi điều kiện mới phát hiện, `status=OPEN`.
- **Chuyển trạng thái**: (chưa có bản ghi) → `OPEN` (§5.4).
- **Kiểm tra hợp lệ**: N/A (phát hiện là suy diễn thuần túy).
- **Lỗi**: N/A (phát hiện không thể tự lỗi với một session hợp lệ; một session đã bị loại trừ qua `excluded_from_reports` không bao giờ kích hoạt phát hiện — đã fix tường minh ở §9.1).
- **Ranh giới**: một session ở **đúng** 12h00m00s mở — xác nhận "hơn 12 giờ" của `LONG_OPEN_SESSION` có phải là `>` nghiêm ngặt hay không (session ở đúng 12:00:00 CHƯA được phép kích hoạt) — test chính xác ranh giới, không giả định.
- **Quyền**: xem: admin/manager/supervisor/viewer (`exceptions.view`); operator hoàn toàn không có quyền này.
- **Đồng thời**: N/A (phát hiện idempotent theo fingerprint — chạy lại reconciliation không bao giờ tạo bản ghi active trùng lặp cho cùng một điều kiện).
- **Nhật ký kiểm toán**: `exception_history` có dòng append-only cho chính việc phát hiện.
- **Liên quan**: §9.1, REQ-EXC-002/003.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive (cả 7 điều kiện), boundary (biên ngưỡng), RBAC.

### REQ-EXC-002 — Trung tâm ngoại lệ: acknowledge / resolve / ignore

- **Mô-đun**: Trung tâm ngoại lệ
- **Mục đích**: Luồng xử lý (triage) do con người thực hiện cho một ngoại lệ đã phát hiện.
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: tồn tại một bản ghi ngoại lệ `OPEN` (hoặc, với resolve/ignore, `ACKNOWLEDGED`).
- **Đầu vào**: `{expected_version, reason?}`.
- **Kích hoạt bởi**: `POST /exceptions/<id>/acknowledge`, `/resolve`, `/ignore`.
- **Luồng chính**: sơ đồ chuyển trạng thái ở §5.4; kiểm tra version so với `row_version`.
- **Kết quả mong đợi**: `200` kèm bản ghi đã cập nhật (`status`, `row_version` tăng).
- **Chuyển trạng thái**: `OPEN→ACKNOWLEDGED`, `OPEN|ACKNOWLEDGED→RESOLVED`, `OPEN|ACKNOWLEDGED→MANUAL_IGNORED`.
- **Kiểm tra hợp lệ**: `expected_version` phải khớp `row_version` hiện tại của bản ghi.
- **Lỗi**: version không khớp → bị từ chối (ai đó đã xử lý trước rồi) — một case optimistic-concurrency thật, kiểm thử được, không phải lý thuyết.
- **Ranh giới**: cố `resolve` một bản ghi đã `RESOLVED` — phải bị từ chối (không được chấp nhận theo kiểu idempotent) vì đây là trạng thái kết thúc và version đã dịch chuyển rồi.
- **Quyền**: admin, manager, supervisor; operator, viewer → `403`.
- **Đồng thời**: hai supervisor đua nhau acknowledge cùng một ngoại lệ — kiểm tra version đảm bảo chỉ người đầu tiên thành công.
- **Nhật ký kiểm toán**: dòng `exception_history` cho mỗi lần chuyển trạng thái (append-only).
- **Liên quan**: §5.4, REQ-EXC-003 (sửa session ngay trong luồng này).
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC, concurrency.

### REQ-EXC-003 — Sửa một session trực tiếp từ ngoại lệ của nó

- **Mô-đun**: Trung tâm ngoại lệ
- **Mục đích**: Cho phép supervisor sửa session gốc mà không cần rời khỏi màn chi tiết ngoại lệ.
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: bản ghi ngoại lệ tham chiếu tới một session thật.
- **Đầu vào**: cùng hình dạng như REQ-SESS-004/005 (đây mở cùng luồng sửa, chỉ khác là theo ngữ cảnh từ ngoại lệ).
- **Kích hoạt bởi**: `POST /session-exceptions/<id>/correct-session`.
- **Luồng chính**: áp dụng quy tắc của REQ-SESS-004/005; modal/drawer **không** tự đóng khi lưu (yêu cầu UI ở §17) để người dùng thấy trạng thái trước/sau.
- **Kết quả mong đợi**: session được sửa đúng như REQ-SESS-004 mô tả; bản thân ngoại lệ không tự động resolve chỉ bởi hành động này (vẫn cần một lệnh gọi `resolve` tường minh riêng — xác minh điều này đúng thay vì giả định).
- **Chuyển trạng thái**: phía session theo REQ-SESS-004; phía ngoại lệ không đổi trừ khi được resolve riêng.
- **Kiểm tra hợp lệ**: giống REQ-SESS-004.
- **Lỗi**: giống REQ-SESS-004.
- **Ranh giới**: giống REQ-SESS-004.
- **Quyền**: admin, manager, supervisor.
- **Đồng thời**: giống REQ-SESS-004.
- **Nhật ký kiểm toán**: giống REQ-SESS-004, cộng thêm lịch sử của bản thân ngoại lệ nếu sau đó được resolve riêng.
- **Liên quan**: REQ-SESS-004, REQ-EXC-002, JOURNEY §18 (zero-qty → ngoại lệ → resolve).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, boundary, RBAC.

### REQ-EXC-004 — Luồng Session Exceptions hệ cũ

- **Mô-đun**: Quản lý Session (ngoại lệ hệ cũ)
- **Mục đích**: Luồng review theo từng session cũ hơn, đơn giản hơn, vẫn còn chạy trên Quản lý Session.
- **Đối tượng thực hiện**: admin, manager, supervisor.
- **Điều kiện tiên quyết**: tồn tại một bản ghi `session_exception_reviews`.
- **Đầu vào**: chuyển `{status}`.
- **Kích hoạt bởi**: `PATCH /session-exceptions/workflow`.
- **Luồng chính**: §5.5 — `NEW→IN_PROGRESS→RESOLVED`, hoặc `→IGNORED` từ 1 trong 2 cái đó.
- **Kết quả mong đợi**: `200` kèm dòng review đã cập nhật.
- **Chuyển trạng thái**: enum 4 giá trị của §5.5.
- **Kiểm tra hợp lệ**: `status` phải là 1 trong 4 giá trị enum (CHECK constraint của DB).
- **Lỗi**: giá trị status không hợp lệ → bị từ chối.
- **Ranh giới**: chuyển thẳng `NEW→RESOLVED` (bỏ qua `IN_PROGRESS`) — xác nhận điều này có được cho phép không (bản thân CHECK constraint không cấm điều này; không xác nhận có thứ tự ép buộc nào khác trong mã — test và ghi lại hành vi thực tế thay vì giả định theo hướng nào).
- **Quyền**: admin, manager, supervisor; operator, viewer → `403`.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt so với `exception_history` của Trung tâm ngoại lệ.
- **Liên quan**: §5.5, §4.9 — đây là một **hệ thống riêng biệt** so với REQ-EXC-001..003, không được lẫn lộn mã/fingerprint của chúng.
- **Độ ưu tiên**: P2 (hệ cũ, vẫn đang chạy nhưng Trung tâm ngoại lệ mới là chính).
- **Khía cạnh kiểm thử**: positive, negative, boundary, RBAC.

## 15.11 Năng suất Nhân viên / KPI (`REQ-PROD-*`)

Công thức chính xác ở §8 — các yêu cầu dưới đây là điểm-vào để sinh testcase.

### REQ-PROD-001 — Báo cáo Năng suất nhân viên

- **Mô-đun**: Năng suất nhân viên
- **Mục đích**: Xếp hạng/báo cáo phần trăm hoàn thành trung bình của từng nhân viên trong một khoảng ngày.
- **Đối tượng thực hiện**: mọi role có `session.view` (cả 6 role đều có `session.view` theo §3.2 — xác minh cụ thể ánh xạ quyền này vì mục nav tự nó dùng `session.view`, không phải một mã `productivity.view` riêng).
- **Điều kiện tiên quyết**: có session `CLOSED`, không bị loại trừ, trong khoảng đã yêu cầu.
- **Đầu vào**: `{from, to, employee_id?, department?, team?, limit?}`.
- **Kích hoạt bởi**: `GET /reports/employee-productivity`, `/reports/employee-productivity/<employee_id>` (chi tiết).
- **Luồng chính**: đầy đủ công thức §8.
- **Kết quả mong đợi**: danh sách nhân viên đã xếp hạng kèm `completed_sessions`, `completed_valid_sessions`, `completed_invalid_sessions`, `productivity_percent`, `good_qty`/`defect_qty`, cộng một khối `summary` (`employee_count`, `completed_sessions`, `avg_employee_productivity_percent`, `total_good_qty`, `total_defect_qty`, `top_employee`).
- **Chuyển trạng thái**: N/A (chỉ đọc).
- **Kiểm tra hợp lệ**: `from`/`to` phải là ngày hợp lệ.
- **Lỗi**: chưa xác nhận N/A cho chính đường đọc.
- **Ranh giới**: một nhân viên mà toàn bộ session trong khoảng đều `OPEN`, hoặc toàn bộ session đều `excluded_from_reports=TRUE` — không được xuất hiện trong danh sách, không bao giờ là dòng `0%` (§8).
- **Quyền**: cả 6 role (qua `session.view`).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A (chỉ đọc).
- **Liên quan**: §8 đầy đủ, bảng dữ liệu mẫu §13.4 (fixture test sẵn dùng cho mọi case biên của công thức), REQ-KIOSK-004.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, boundary (mọi case biên của §8), empty-state.

### REQ-PROD-002 — Cấu hình publish Wallboard

- **Mô-đun**: Năng suất nhân viên / Kiosk
- **Mục đích**: Cho phép admin/manager cấu hình những gì Kiosk wallboard công khai hiển thị.
- **Đối tượng thực hiện**: admin, manager (publish); mọi role có `session.view` (lấy cấu hình hiện tại).
- **Điều kiện tiên quyết**: không có.
- **Đầu vào**: `{mode: fixed|dynamic, from?, to?, department?, sort, employees_per_page, auto_page_flip_seconds, columns[]}`.
- **Kích hoạt bởi**: `GET/POST /reports/employee-productivity/wallboard-config`.
- **Luồng chính**: cấu hình đã kiểm tra hợp lệ được lưu; wallboard công khai (REQ-KIOSK-004) đọc nó mỗi lần làm mới.
- **Kết quả mong đợi**: `200` kèm cấu hình đã lưu.
- **Chuyển trạng thái**: N/A (đây là cấu hình, không phải entity có vòng đời).
- **Kiểm tra hợp lệ**: `mode=fixed` yêu cầu cả `from` và `to`; `from` không được sau `to`; `sort` phải là giá trị đã biết; `employees_per_page` và `auto_page_flip_seconds` trong khoảng hợp lệ; `columns` phải là tên cột đã biết.
- **Lỗi**: mỗi lỗi kiểm tra hợp lệ có sự từ chối riêng cụ thể (fixed-mode-thiếu-ngày, from-sau-to, sort-không-xác-định, page-size-ngoài-khoảng, employees_per_page-không-hợp-lệ, columns-không-hợp-lệ, auto_page_flip_seconds-không-hợp-lệ) — 7 case âm riêng biệt, tất cả đã xác nhận độc lập là tồn tại.
- **Ranh giới**: `employees_per_page` tại đúng giá trị min/max.
- **Quyền**: publish: chỉ admin, manager (supervisor/operator/viewer → `403`, đã xác nhận cụ thể với viewer); đọc: rộng hơn.
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt.
- **Liên quan**: REQ-KIOSK-004, REQ-PROD-001.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative (cả 7 case kiểm tra hợp lệ), boundary, RBAC.

## 15.12 Tìm kiếm / Lọc / Phân trang (`REQ-SEARCH-*`)

### REQ-SEARCH-001 — Response danh sách có giới hạn

- **Mô-đun**: Xuyên suốt (cross-cutting)
- **Mục đích**: Ngăn response toàn bảng không giới hạn.
- **Đối tượng thực hiện**: mọi role đọc một endpoint danh sách.
- **Điều kiện tiên quyết**: có nhiều dòng hơn giới hạn mặc định/tối đa.
- **Đầu vào**: param `limit` tùy chọn, tùy màn hình.
- **Kích hoạt bởi**: bất kỳ `GET` danh sách nào (ví dụ `GET /work-sessions`, limit mặc định 200; `GET /reports/employee-productivity`, limit mặc định 1000).
- **Luồng chính**: server giới hạn số dòng trả về ở một mặc định cố định trừ khi có yêu cầu `limit` nhỏ hơn.
- **Kết quả mong đợi**: số dòng response ≤ mặc định/tối đa đã tài liệu hóa của endpoint.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: `limit`, nếu có, được clamp về một khoảng hợp lý (xác minh chính xác min/max theo từng endpoint thay vì giả định một hằng số chung).
- **Lỗi**: chưa xác nhận N/A.
- **Ranh giới**: yêu cầu `limit` vượt xa mức tối đa — xác nhận nó bị clamp xuống, không được tôn trọng theo đúng nghĩa đen (một lỗ hổng thật tiềm ẩn nếu không bị clamp — test tường minh).
- **Quyền**: kế thừa quyền của endpoint chủ.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: REQ-PROD-001.
- **Độ ưu tiên**: P2.
- **Khía cạnh kiểm thử**: positive, boundary.

## 15.13 Hướng dẫn / Trợ giúp (`REQ-TUT-*`)

### REQ-TUT-001 — Manifest hướng dẫn và phục vụ video

- **Mô-đun**: Hướng dẫn (Tutorial)
- **Mục đích**: Phục vụ thư viện video hướng dẫn chỉ cho người dùng đã xác thực, có bảo vệ chống path-traversal.
- **Đối tượng thực hiện**: mọi role đã xác thực (không có mã quyền riêng — chỉ cần `login_required`).
- **Điều kiện tiên quyết**: tồn tại một `manifest.json` và các file video nó tham chiếu, nằm dưới thư mục tutorial đã cấu hình.
- **Đầu vào**: không có cho manifest; đoạn đường dẫn `filename` cho một video cụ thể.
- **Kích hoạt bởi**: `GET /api/tutorials`, `GET /tutorials/<filename>`.
- **Luồng chính**: 1) yêu cầu session hợp lệ. 2) đọc manifest. 3) lọc `items` chỉ giữ những cái có `file` resolve tới một file thật, tồn tại, **nằm bên trong** thư mục gốc — mục nào trỏ ra ngoài gốc (`..`, đường dẫn tuyệt đối) bị âm thầm loại bỏ, không bao giờ được phục vụ.
- **Kết quả mong đợi**: `200` kèm manifest đã lọc; một file video hợp lệ stream với `Content-Type: video/mp4` và `Content-Length` chính xác.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: kiểm tra chứa-trong-phạm-vi (path containment) trên mọi giá trị `file`.
- **Lỗi**: không có session → `401`; `filename` nằm ngoài gốc, hoặc không tồn tại → `404`.
- **Ranh giới**: một mục manifest có `file: "../../etc/passwd"` hoặc đường dẫn tuyệt đối — phải bị loại khỏi danh sách trả về, và một request trực tiếp tới nó phải `404`, không được phục vụ bất kỳ thứ gì.
- **Quyền**: chỉ `login_required`, không có quyền chi tiết hơn — mọi role đã xác thực đều truy cập được mọi video đã publish.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: §2 (mục nav), toàn bộ danh sách chương là một **artifact sống**, không đặc tả theo ID cố định ở đây — xem §21 về lỗi lịch sử cụ thể "15 so với 14" và yêu cầu regression-test của nó.
- **Độ ưu tiên**: P0 (bảo vệ path-traversal là một ranh giới bảo mật thật).
- **Khía cạnh kiểm thử**: positive, negative (path traversal), boundary, empty-state (0 video đã publish).

## 15.14 Quản trị / Hệ thống (`REQ-SYS-*`)

### REQ-SYS-001 — Quản lý Người dùng & Phân quyền

- **Mô-đun**: Người dùng & Phân quyền
- **Mục đích**: Quản lý tài khoản và role được gán; quản lý mỗi role cấp những quyền nào.
- **Đối tượng thực hiện**: xem: `users.view` (chỉ admin, theo bảng cấp quyền §3.2 — lưu ý điều này hẹp hơn hầu hết quyền view khác); quản lý: `users.manage`/`roles.manage` (chỉ admin).
- **Điều kiện tiên quyết**: không có cho list; user/role đích tồn tại cho sửa.
- **Đầu vào**: tạo — `{username, display_name, password, role}`; sửa — tập con của cùng field; cập nhật quyền role — `{permission_codes[]}`.
- **Kích hoạt bởi**: `GET/POST /users`, `PATCH /users/<id>`, `POST /users/<id>/reset-password`, `GET /roles`, `PUT /roles/<role_code>/permissions`.
- **Luồng chính**: CRUD tiêu chuẩn, cộng case đặc biệt ở quy tắc 1 §3.3 (sửa quyền của `admin` không có tác dụng).
- **Kết quả mong đợi**: `200` kèm (các) dòng bị ảnh hưởng.
- **Chuyển trạng thái**: N/A (không phải entity có vòng đời).
- **Kiểm tra hợp lệ**: `role` phải là 1 trong 6 mã hợp lệ; mọi mã trong payload cập nhật quyền phải tồn tại trong danh mục (§3.1) — mã không xác định → `ValueError`, "Unknown permissions: {codes}".
- **Lỗi**: mã role/quyền không xác định → bị từ chối; xem §11.
- **Ranh giới**: gửi `role_code=admin` tới `PUT /roles/admin/permissions` với danh sách quyền đã bị thu hẹp rõ rệt — phải bị âm thầm ghi đè trở lại thành bộ đầy đủ (quy tắc 1 §3.3 — một no-op thật, kiểm thử được cụ thể).
- **Quyền**: chỉ admin cho mọi lệnh ghi trong module này; `users.view` cho list (chỉ admin theo bảng cấp quyền).
- **Đồng thời**: chưa xác nhận N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt (xác minh có tồn tại một dòng audit thay đổi user/role).
- **Liên quan**: §3 đầy đủ (ma trận RBAC).
- **Độ ưu tiên**: P0 (tự-quản-lý RBAC — một lỗi ở đây có thể lan sang mọi kiểm tra quyền khác).
- **Khía cạnh kiểm thử**: positive, negative, boundary (no-op dòng admin), RBAC.

### REQ-SYS-002 — Tự đổi mật khẩu

- **Mô-đun**: Người dùng & Phân quyền
- **Mục đích**: Cho phép bất kỳ người dùng đã đăng nhập nào tự đổi mật khẩu của chính mình.
- **Đối tượng thực hiện**: mọi role đã xác thực.
- **Điều kiện tiên quyết**: session đã xác thực.
- **Đầu vào**: `{current_password, new_password}`.
- **Kích hoạt bởi**: `POST /auth/change-password`.
- **Luồng chính**: 1) xác minh `current_password` với hash của chính caller. 2) nếu đúng, hash và lưu `new_password`; luôn tác động lên **tài khoản của chính caller**, không bao giờ dùng param `user_id`.
- **Kết quả mong đợi**: `200` khi thành công.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: quy tắc độ mạnh mật khẩu (quy tắc chính xác chưa xác nhận đầy đủ trong lượt này — xem khoảng trống §21; test với một mật khẩu rõ ràng yếu và ghi lại hành vi thực tế thay vì giả định một policy cụ thể).
- **Lỗi**: `current_password` sai → bị từ chối.
- **Ranh giới**: chưa xác nhận N/A ngoài khoảng trống về độ mạnh mật khẩu ở trên.
- **Quyền**: mọi role đã xác thực — đây là self-service, không bị gate theo quyền ngoài việc có session.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: chưa xác nhận N/A riêng biệt.
- **Liên quan**: REQ-SYS-001.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, negative, boundary.

### REQ-SYS-003 — System Console (chỉ Super Admin)

- **Mô-đun**: System Console
- **Mục đích**: Khu vực health/chẩn đoán/điều khiển dịch vụ kỹ thuật, hoàn toàn tách biệt với quản trị nghiệp vụ thông thường.
- **Đối tượng thực hiện**: **chỉ super_admin** — không bao giờ là `admin`, dù `admin` có cơ chế bypass quyền nghiệp vụ ở nơi khác (quy tắc 2 §3.3).
- **Điều kiện tiên quyết**: session `super_admin`.
- **Đầu vào**: tùy màn hình (id dịch vụ cho restart, tên component cho chạy chẩn đoán, v.v.).
- **Kích hoạt bởi**: `GET/POST /api/system-health/errors|services|diagnostics|audit`, `POST /api/system-health/services/<id>/restart`, `POST /api/system-health/diagnostics/<component>`.
- **Luồng chính**: kiểm tra chuỗi role, không phải kiểm tra bảng quyền (quy tắc 2 §3.3) — kiểm tra đúng nghĩa đen `session.role == 'super_admin'`.
- **Kết quả mong đợi**: `200` kèm dữ liệu kỹ thuật/kết quả hành động được yêu cầu cho `super_admin`.
- **Chuyển trạng thái**: hành động restart dịch vụ làm thay đổi trạng thái chạy của dịch vụ đích (ngoài phạm vi mô hình dữ liệu của tài liệu này — coi đây là hành động hạ tầng, không phải chuyển trạng thái entity nghiệp vụ MESFlow).
- **Kiểm tra hợp lệ**: chưa xác nhận N/A ngoài kiểm tra role.
- **Lỗi**: bất kỳ role nào khác `super_admin`, **kể cả `admin`**, → `403`, "Chỉ Super Admin mới có quyền truy cập khu vực Hệ thống."
- **Ranh giới**: một session `admin` (không phải `super_admin`) là case biên then chốt — phải bị từ chối dù `admin` có bypass toàn diện ở mọi nơi khác trong hệ thống (ngoại lệ tường minh ở §3.3).
- **Quyền**: chỉ đúng chuỗi role `super_admin`.
- **Đồng thời**: chưa xác nhận N/A cho phạm vi tài liệu này.
- **Nhật ký kiểm toán**: trang/API `system-audit` tồn tại chuyên biệt để hiển thị ai đã làm gì ở đây — audit trail tự tham chiếu cho chính module này.
- **Liên quan**: §2 (mục nav), quy tắc 2 §3.3.
- **Độ ưu tiên**: P0 (đây là ranh giới nhạy cảm bảo mật nhất toàn hệ thống — rò rỉ ở đây nghĩa là một admin thường có thể restart dịch vụ production).
- **Khía cạnh kiểm thử**: positive, negative (ranh giới admin-phải-thất-bại — testcase RBAC quan trọng nhất toàn hệ thống), RBAC.

## 15.15 Nhật ký / Lịch sử (`REQ-AUDIT-*`)

### REQ-AUDIT-001 — Action log & error trace (chỉ admin)

- **Mô-đun**: Nhật ký hệ thống
- **Mục đích**: Log kỹ thuật action/lỗi, tách biệt với audit nghiệp vụ và với System Console.
- **Đối tượng thực hiện**: **chỉ admin** (gate bởi `roles.manage`, decorator `@admin_required` ở §3.4 — hẹp hơn hầu hết cặp admin+manager khác ở nơi khác).
- **Điều kiện tiên quyết**: tồn tại các dòng log.
- **Đầu vào**: param filter (khoảng ngày, đã xử lý/chưa xử lý, v.v.).
- **Kích hoạt bởi**: `GET /action-logs`, `/error-traces`, `/log-retention/*`.
- **Luồng chính**: list/chi tiết/resolve đã lọc tiêu chuẩn.
- **Kết quả mong đợi**: `200` kèm danh sách log đã lọc.
- **Chuyển trạng thái**: một dòng log có thể được đánh dấu đã xử lý.
- **Kiểm tra hợp lệ**: chưa xác nhận N/A ngoài việc parse filter.
- **Lỗi**: chưa xác nhận N/A riêng biệt.
- **Ranh giới**: chưa xác nhận N/A.
- **Quyền**: **chỉ admin** — manager, dù nắm nhiều quyền tương đương admin ở nơi khác, **không** được cấp `logs.manage`/truy cập màn hình cụ thể này theo bảng cấp quyền §3.2 (manager chỉ nắm `logs.view`, ánh xạ tới một màn hình *khác*, hẹp hơn, hiển thị trên nav — xác minh chính xác ranh giới giữa `logs.view` và khu vực action-log/error-trace chỉ-admin này khi thiết kế test, vì bảng cấp quyền cho thấy `manager: logs.view` nhưng decorator route của yêu cầu này là `@admin_required`; đây là một điểm tinh tế đáng có một test ranh giới riêng thay vì giả định nhất quán).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: đây **chính là** hệ thống audit/log.
- **Liên quan**: §3.2, REQ-SYS-003 (một hệ thống liên quan nhưng khác, khu vực log cấp hệ thống còn hạn chế hơn nữa).
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, RBAC (ranh giới admin vs. manager — xác minh chính xác).

### REQ-AUDIT-002 — Nhật ký nghiệp vụ (Business Audit Trail)

- **Mô-đun**: Nhật ký nghiệp vụ
- **Mục đích**: Dấu vết "ai thay đổi gì, khi nào, vì sao" dễ đọc, xuyên suốt các thay đổi PO/Session/số lượng/ngoại lệ.
- **Đối tượng thực hiện**: `business_audit.view` — do manager, supervisor nắm giữ (không trực tiếp admin trong bảng cấp quyền, dù cơ chế bypass của admin khiến nó truy cập được trên thực tế — §3.2/§3.3).
- **Điều kiện tiên quyết**: đã có thay đổi nghiệp vụ xảy ra.
- **Đầu vào**: param filter (loại entity, khoảng ngày, người thực hiện).
- **Kích hoạt bởi**: `GET /audit-logs`.
- **Luồng chính**: đọc chính các dòng audit mà mọi hành động thay đổi trạng thái trong tài liệu này ghi (REQ-PO-*, REQ-SESS-*, REQ-EXC-* đều tham chiếu tới đây).
- **Kết quả mong đợi**: `200` kèm danh sách thay đổi dễ đọc, đã lọc.
- **Chuyển trạng thái**: N/A (chỉ đọc).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: chưa xác nhận N/A.
- **Ranh giới**: chưa xác nhận N/A.
- **Quyền**: manager, supervisor (và admin qua bypass); operator không có, viewer không có (theo bảng cấp quyền §3.2 — cả hai đều không được liệt kê cho `business_audit.view`).
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: đây CHÍNH LÀ view audit.
- **Liên quan**: mọi field **Nhật ký kiểm toán** trên các yêu cầu khác của Phần B đều đổ vào màn hình này.
- **Độ ưu tiên**: P1.
- **Khía cạnh kiểm thử**: positive, RBAC.

## 15.16 Hành vi API xuyên suốt (`REQ-API-*`)

### REQ-API-001 — Idempotency (chống áp dụng trùng)

- **Mô-đun**: Xuyên suốt
- **Mục đích**: Đảm bảo một lệnh ghi bị gọi lại (mạng chập chờn, kiosk retry) không bao giờ bị áp dụng hai lần.
- **Đối tượng thực hiện**: bất kỳ caller nào của một endpoint có khóa idempotency (start, finish, group-finish, adjust).
- **Điều kiện tiên quyết**: một `request_id` giống hệt đã được xử lý thành công một lần trước đó.
- **Đầu vào**: payload giống hệt bao gồm cùng `request_id`.
- **Kích hoạt bởi**: bất kỳ cái nào trong REQ-SESS-001/002/003/004.
- **Luồng chính**: server nhận diện `request_id` trong `kiosk_idempotency`, trả về response gốc đã lưu thay vì xử lý lại.
- **Kết quả mong đợi**: body response giống hệt lần gọi đầu, kèm thêm `idempotent_replay: true`.
- **Chuyển trạng thái**: không có gì ở lần gọi lại (đã áp dụng ở lần gọi đầu).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: N/A — đây tự nó là một cơ chế ngăn lỗi.
- **Ranh giới**: cùng `request_id` được dùng lại với payload **khác** — xác nhận server trả về đúng response gốc đã lưu (bỏ qua payload mới) thay vì báo lỗi hoặc áp dụng payload mới (xác minh hành vi chính xác, đây là một case biên có ý nghĩa).
- **Quyền**: N/A (độc lập với kiểm tra quyền).
- **Đồng thời**: đây chính xác là cơ chế an toàn đồng thời (NFR-001).
- **Nhật ký kiểm toán**: không có dòng audit trùng lặp khi replay.
- **Liên quan**: NFR-001, REQ-SESS-001/002.
- **Độ ưu tiên**: P0.
- **Khía cạnh kiểm thử**: positive, boundary (case payload không khớp), concurrency.

### REQ-API-002 — Thứ tự lock-PO-trước (chống deadlock)

- **Mô-đun**: Xuyên suốt
- **Mục đích**: Ngăn deadlock khi ghi đồng thời chạm vào các Operation của cùng một PO.
- **Đối tượng thực hiện**: bất kỳ cặp lệnh gọi start/finish/adjust/auto-close đồng thời nào dưới cùng một PO.
- **Điều kiện tiên quyết**: hai hoặc nhiều lệnh gọi đồng thời nhắm vào các Operation khác nhau dưới cùng một PO.
- **Đầu vào**: N/A (đây là một đảm bảo implementation nội bộ, kiểm thử qua đồng thời, không phải đầu vào của một request đơn).
- **Kích hoạt bởi**: load test đồng thời gửi các lệnh start/finish đồng thời qua nhiều Operation của một PO.
- **Luồng chính**: mọi đường ghi đều lock dòng PO **trước tiên**, trước bất kỳ lock dòng nào khác, theo một thứ tự cố định.
- **Kết quả mong đợi**: mọi lệnh gọi cuối cùng đều hoàn tất (tuần tự hóa, không deadlock); không có lệnh nào timeout do xung đột thứ tự lock.
- **Chuyển trạng thái**: N/A (đây là một đảm bảo phi chức năng về *cách* các chuyển trạng thái xảy ra dưới tải).
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: một lỗi deadlock xuất hiện dưới tải đồng thời sẽ là một **hồi quy (regression)** của đảm bảo này.
- **Ranh giới**: trường hợp xấu nhất thực tế — nhiều kiosk cùng chạm vào nhiều Operation của *cùng* một PO cùng lúc (thời điểm đầu ca bận rộn) — chính xác là kịch bản tính năng này tồn tại để giữ đúng.
- **Quyền**: N/A.
- **Đồng thời**: đây **chính là** yêu cầu về đồng thời (NFR-002).
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: NFR-002.
- **Độ ưu tiên**: P0 (quan trọng cho ổn định production, không chỉ là điểm cộng).
- **Khía cạnh kiểm thử**: concurrency (load test).

### REQ-API-003 — Hợp đồng Health/Readiness

- **Mô-đun**: Xuyên suốt / Deploy
- **Mục đích**: Cho công cụ deploy và QA một tín hiệu liveness+readiness đáng tin cậy, không cần xác thực.
- **Đối tượng thực hiện**: không xác thực (script deploy, giám sát).
- **Điều kiện tiên quyết**: tiến trình app đang chạy.
- **Đầu vào**: không có.
- **Kích hoạt bởi**: `GET /api/system/ready`, `GET /api/system/version`.
- **Luồng chính**: `/ready` kiểm tra kết nối DB và báo cáo `version`, `commit`, `migration_head`, `server_role`, `db_ok`, `schema_version`; `/version` chỉ trả field xác định từ mã nguồn.
- **Kết quả mong đợi**: `200 {"ok": true, "status": "ready", ...}` khi khỏe.
- **Chuyển trạng thái**: N/A.
- **Kiểm tra hợp lệ**: N/A.
- **Lỗi**: DB không truy cập được → `ok:false`/status chưa ready (cấu trúc chính xác: xác minh với hợp đồng thật đang chạy thay vì giả định).
- **Ranh giới**: N/A.
- **Quyền**: **không xác thực theo chủ đích** — không gắn cờ đây là lỗ hổng bảo mật.
- **Đồng thời**: N/A.
- **Nhật ký kiểm toán**: N/A.
- **Liên quan**: NFR-006/007/008. **Lưu ý quan trọng**: field của `/api/system/version` không bao giờ định danh *máy chủ vật lý nào* đã trả lời — không dùng nó để kết luận hai endpoint là "cùng một server" (một điều tra thật, đã xác nhận trong lịch sử hệ thống này từng phát hiện hai host thực sự khác nhau báo JSON version giống hệt nhau từng byte).
- **Độ ưu tiên**: P0 (quan trọng cho pipeline deploy).
- **Khía cạnh kiểm thử**: positive, negative (case DB down).

---

# PHẦN C — Quy Tắc Nghiệp Vụ (Business Rules)

Đánh số độc lập `BR-###`; một `REQ-*` có thể trích dẫn một hoặc nhiều rule.

| ID | Quy tắc | Kiểm thử được như |
|---|---|---|
| BR-001 | Role `admin` bỏ qua toàn bộ bảng quyền đối với các quyền nghiệp vụ thông thường — luôn được phép. | Case biên REQ-SYS-001 |
| BR-002 | `super_admin` được thừa hưởng cơ chế bypass nghiệp vụ của `admin` nhưng truy cập System Console đòi hỏi đúng chuỗi role, không bao giờ thỏa mãn bởi `admin`. | REQ-SYS-003 |
| BR-003 | Một nhân viên chỉ được có **tối đa một session `OPEN`** tại một thời điểm — ép ở mức DB, không chỉ ở mức app. | Case biên REQ-SESS-001 |
| BR-004 | Một Operation phía dưới có bật input-flow không thể `start()` cho tới khi Operation nguồn phía trên đã có **ít nhất một session được start** (không nhất thiết đã finish). | REQ-SESS-001 |
| BR-005 | `qty=0` khi finish không bao giờ bị từ chối; nếu session đã mở > 4h, nó bị gắn cờ `ZERO_QUANTITY_LONG` để review, không bị chặn. | REQ-SESS-002, REQ-EXC-001 |
| BR-006 | `rework_qty` không bao giờ được vượt quá `defect_qty`, ép cả khi finish lẫn adjust. | Case biên REQ-SESS-002/004 |
| BR-007 | Một session `CLOSED` **không bao giờ** bị xóa, kể cả khi bị loại khỏi báo cáo — lịch sử/audit là vĩnh viễn; "loại trừ" chỉ làm nó ngừng tính vào tổng hợp. | REQ-SESS-007 |
| BR-008 | Auto-close là một vòng đời riêng biệt, không phải finish thủ công ngụy trang — phân biệt được sau này qua `close_reason`/`closed_by_system`, và bắn một domain event khác. | REQ-SHIFT-002 |
| BR-009 | Một session bị auto-close có `quantity_confirmed=FALSE` cho tới khi một sửa đổi của con người xác nhận lại; bất kỳ sửa đổi nào cũng luôn đặt lại thành `TRUE`. | REQ-SHIFT-002, REQ-SESS-004 |
| BR-010 | "Loại khỏi báo cáo" chỉ ảnh hưởng tới **tổng hợp**; bản thân trạng thái của session và sự hiện diện của nó trong lịch sử/audit không đổi. | REQ-SESS-007 |
| BR-011 | Ràng buộc dòng vật tư/input-flow: một Operation đích không thể tiêu thụ nhiều hơn số lượng GOOD (hoặc REWORK, theo `input_source_kind` đã cấu hình) từ nguồn của nó so với `source.produced − đã_phân_bổ_ở_chỗ_khác`. | REQ-SESS-002 (finish, kiểm tra vật tư) |
| BR-012 | Phụ thuộc Operation là hai quan hệ độc lập: một **predecessor** thuần thời gian/thứ tự (chỉ cần tồn tại) và một **input source** số lượng (phải có session đã start) — cùng một Operation có thể là cả hai, khi đó chỉ quy tắc input-source chặt hơn được áp dụng. | REQ-SESS-001 |
| BR-013 | Sửa toàn bộ session hỗ trợ optimistic concurrency qua `expected_updated_at` — một sửa đổi cũ bị từ chối, không bao giờ âm thầm bị ghi đè. | REQ-SESS-005 |
| BR-014 | Xóa PO/Part bị từ chối bất cứ khi nào có bất kỳ Operation con nào có lịch sử sản xuất thật, nêu rõ (các) loại tìm thấy. | REQ-PO-004, REQ-PART-002 |
| BR-015 | `fingerprint` của một bản ghi Trung tâm ngoại lệ là duy nhất **trong khi đang active**; cùng điều kiện xảy ra lại sau khi một bản ghi trước đó đã resolved/ignored sẽ tạo một bản ghi mới, không bao giờ hồi sinh bản ghi cũ. | REQ-EXC-001 |
| BR-016 | Một request UI cũ, đã bị thay thế không bao giờ được phép ghi đè kết quả render của một request mới hơn. | REQ-DASH-002 |
| BR-017 | Toán học timezone/ca luôn tính theo phút-tương-đối-theo-ca so với timezone của site, không bao giờ trừ wall-clock ngây thơ — bắt buộc cho ca qua đêm (cross-midnight). | REQ-SHIFT-001 |
| BR-018 | Truy vấn KPI/báo cáo/phát hiện ngoại lệ dùng chung một điều kiện lọc (`status='CLOSED' AND NOT excluded_from_reports`) thay vì mỗi cái tự viết riêng. | REQ-PROD-001, REQ-EXC-001 |
| BR-901 | Mọi lần thử đăng nhập (thành công hay thất bại) đều ghi một dòng audit trail (`LOGIN_SUCCESS`/`LOGIN_FAILED`); password gửi lên không bao giờ được log dưới bất kỳ hình thức nào, bất kể kết quả. | REQ-AUTH-001 |
| BR-902 | Một lần đăng xuất chủ động không bao giờ được phép bật ngay lại thành một session đã xác thực kể cả khi autologin đang bật — nút đăng xuất của chính app luôn tự thêm `?noauto=1`. | REQ-AUTH-002/005 |
| BR-903 | Autologin yêu cầu `MESFLOW_ENV != production`, **hoặc** cả điều kiện đó không thỏa **và** một cờ thứ hai tường minh (`MESFLOW_TEST_AUTO_LOGIN_ALLOW_PRODUCTION=1`) — không bao giờ chỉ thỏa mãn bởi cờ cơ bản trên một môi trường gắn cờ production. | REQ-AUTH-004 |
| BR-904 | Chuyển nhanh persona ánh xạ tới một username **đúng bằng đúng nghĩa đen** tên persona, từ một allowlist 5 giá trị cố định — không bao giờ là một username tùy ý, không bao giờ là `super_admin`. | REQ-AUTH-004 |
| BR-905 | Một lần thử autologin bị từ chối (guard fail) luôn tới được luồng audit/log dưới dạng cảnh báo bảo mật, cả lúc khởi động tiến trình (nếu tổ hợp rủi ro được cấu hình) lẫn ở mỗi lần thử bị từ chối riêng lẻ. | REQ-AUTH-004 |

---

# PHẦN D — Yêu Cầu Chấp Nhận UI/UX

Chỉ giới hạn ở **hành vi mà một agent QC có thể kiểm tra máy móc được**
— không đánh giá chủ quan kiểu pixel-perfect.

| ID | Yêu cầu |
|---|---|
| REQ-UI-001 | Mọi checkbox/radio trên cùng một form phải render với chiều rộng/chiều cao đã tính (px) giống hệt mọi checkbox/radio khác trên cùng form đó. |
| REQ-UI-002 | Một field mà giá trị luôn ngầm định đúng theo quy tắc nghiệp vụ hiện tại thì không được hiển thị như một tùy chọn bật/tắt được — không để lại bề mặt cấu hình chết. |
| REQ-UI-003 | Trang đăng nhập luôn hiển thị bố cục chia đôi màn hình cố định: panel thương hiệu/ngữ cảnh (bên trái) với tagline sản phẩm và footer version, và form đăng nhập (bên phải) — hiện diện bất kể trạng thái autologin. |
| REQ-UI-004 | Một role không có quyền `.view` của một trang (§2/§3.3) sẽ không hiển thị mục sidebar của trang đó — biến mất hẳn, không phải bị mờ/disable. |
| REQ-UI-005 | Viewport desktop chính được hỗ trợ là chính xác 1366×768 — mọi QA về layout phải bao gồm đúng độ phân giải này. |
| REQ-UI-006 | Ma trận breakpoint responsive tối thiểu cho bất kỳ kiểm tra "không bị vỡ" ở cấp trang nào: 1920×1080, 1366×768, 390×844 (mobile). |
| REQ-UI-007 | Tương tác modal/drawer để sửa exception/session không tự đóng khi lưu — người dùng phải thấy trạng thái trước/sau đã lưu rồi tự đóng. |
| REQ-UI-008 | Các phần tử sticky (ví dụ header nhóm PO của Production Schedule) không được nhân đôi khi cuộn và phải xếp lớp đúng thứ tự z-index. |
| REQ-UI-009 | Trạng thái filter và vị trí cuộn phải giữ nguyên qua một lần làm mới dữ liệu — một lần refresh không bao giờ được phép âm thầm reset filter của người dùng hay nhảy cuộn về đầu trang. |
| REQ-UI-010 | Trạng thái rỗng hiển thị thông báo tiếng Việt tường minh (ví dụ "Không có Session hoàn thành trong khoảng ngày đã chọn") thay vì một khung trống. |
| REQ-UI-011 | Bất kỳ hành động tự động bất đồng bộ nào (ví dụ POST của autologin) đều phải hiện văn bản trạng thái tường minh trong lúc chờ, không phải một khoảng chờ im lặng không nhãn. |
| REQ-UI-012 | Ngôn ngữ giao diện là tiếng Việt xuyên suốt app quản trị — một chuỗi tiếng Anh trong label/lỗi/toast hướng người dùng là một lỗi. |

**Không bao phủ / không khẳng định**: audit khả năng tiếp cận
(accessibility) về điều hướng bàn phím/thứ tự focus, gắn nhãn cho
screen-reader, tỷ lệ tương phản màu — không có tiêu chuẩn
accessibility chính thức nào được xác nhận cho hệ thống này (khoảng
trống §21); coi mọi thứ ngoài "nhãn phân biệt được với giá trị, không
chỉ dựa vào màu sắc" là khám phá (exploratory), không phải pass/fail.

---

# PHẦN E — Hành Trình Người Dùng Đầu-Cuối (End-to-End Journey)

Mỗi journey chuyển đổi trực tiếp được thành một testcase E2E dùng
schema ở §20. Mọi giá trị tham chiếu đều lấy được từ dữ liệu mẫu §13.

### JOURNEY-001 — Admin dựng một PO từ Template tới khi một Operation được thao tác

1. Admin đăng nhập (REQ-AUTH-001). **Kỳ vọng**: vào trang `overview`, sidebar đầy đủ (§2).
2. Admin mở `TPL-DEMO-01` (§13.2), xác nhận cây của nó (REQ-TPL-001). **Kỳ vọng**: `GET /templates/<id>/validate` (REQ-TPL-002) không báo lỗi.
3. Admin khởi tạo nó (REQ-PO-001). **Kỳ vọng**: PO mới `PO-DEMO-001` tồn tại, `status=PLANNED`, Part/Operation đã copy.
4. Supervisor Start PO (REQ-PO-002). **Kỳ vọng**: `status→IN_PROGRESS`; mọi Operation con trở nên thao tác được tại kiosk.
5. Nhân viên `EMP-DEMO-01` (active) quét vào qua Kiosk v2, start `OP-DEMO-01-CUT` (REQ-SESS-001/REQ-KIOSK-002). **Kỳ vọng**: Operation `→IN_PROGRESS` (quy tắc 2 §5.2).
6. Nhân viên finish với `good_qty=10` (REQ-SESS-002). **Kỳ vọng**: session `CLOSED`, `quantity_confirmed=TRUE`; nếu `good_qty ≥ plan_qty`, Operation `→COMPLETED`.
7. Dashboard được làm mới (REQ-DASH-001). **Kỳ vọng**: số liệu tiến độ PO phản ánh session vừa đóng.

### JOURNEY-002 — Kiosk dùng chung nhiều nhân viên nối tiếp (kịch bản tutorial bắt buộc)

1. Thiết bị Kiosk v2 ở `WAIT_EMPLOYEE`. Nhân viên A quét → `WAIT_OPERATION` → quét `OP-DEMO-01-CUT` → session start, thiết bị reset về `WAIT_EMPLOYEE` (REQ-KIOSK-002/003).
2. Nhân viên B quét ngay sau đó (session của A vẫn `OPEN`) → resolve hoàn toàn mới, `WAIT_OPERATION` → quét một Operation khác → session của chính B start, thiết bị reset lại.
3. Nhân viên C lặp lại tương tự. **Kỳ vọng**: tồn tại 3 session `OPEN` độc lập; lần quét lại sau đó của mỗi nhân viên trên cùng thiết bị này resolve về đúng session của họ, không bao giờ của người khác (bằng chứng cốt lõi của REQ-KIOSK-003).
4. Mỗi nhân viên lần lượt finish session của mình với số lượng đạt/lỗi khác nhau.
5. Mở báo cáo Năng suất nhân viên / Kiosk wallboard (REQ-PROD-001/REQ-KIOSK-004). **Kỳ vọng**: cả 3 nhân viên xuất hiện với số liệu đúng, độc lập.

### JOURNEY-003 — Quên nhập sản lượng → auto-close → admin xử lý

1. Operator start một session, không bao giờ finish nó (hết ca trong khi vẫn `OPEN`).
2. Hết giờ ca + thời gian ân hạn trôi qua; job reconciliation chạy (REQ-SHIFT-002). **Kỳ vọng**: session tự đóng, giữ nguyên số lượng đã có, `close_reason='AUTO_SHIFT_END'`, `quantity_confirmed=FALSE`.
3. Trung tâm ngoại lệ hiện nó ra (`SESSION_PAST_SHIFT_END` khi còn mở, hoặc `ZERO_QUANTITY_LONG` khi đã đóng nếu áp dụng — REQ-EXC-001).
4. Supervisor mở session, sửa đúng số lượng thật qua adjust kèm lý do (REQ-SESS-004). **Kỳ vọng**: `quantity_confirmed→TRUE`; có dòng audit + event `VALUE_CHANGED`; tiến độ Operation/PO reconcile đúng.

### JOURNEY-004 — Giao nhầm Operation → sửa/reassign → audit/báo cáo đúng

1. Một session bị lỡ start nhầm Operation.
2. Supervisor dùng transfer-operation (REQ-SESS-006). **Kỳ vọng**: session giờ thuộc đúng Operation; tiến độ cả Operation cũ lẫn mới đều reconcile (§5.2); audit ghi lại trước/sau.
3. Báo cáo của cả hai Operation phản ánh đúng sự sửa đổi — phần đóng góp của session di chuyển, không bao giờ nhân đôi.

### JOURNEY-005 — Session sai → loại trừ (exclude) → không ảnh hưởng báo cáo

1. Một session được xác định là rác (quét trùng/dữ liệu test).
2. Supervisor exclude nó kèm lý do (REQ-SESS-007/BR-010). **Kỳ vọng**: vẫn còn trong lịch sử, `excluded_from_reports=TRUE`; tiến độ Operation/PO, KPI, và phát hiện ngoại lệ đều ngừng tính nó.
3. Restore kèm lý do đảo ngược lại. **Kỳ vọng**: được tính lại từ lần reconcile tiếp theo trở đi.

### JOURNEY-006 — Ngoại lệ sản lượng 0/NG → Trung tâm ngoại lệ → resolve/xác nhận

1. Một session đóng 0/0 sau khi mở >4h. **Kỳ vọng**: `ZERO_QUANTITY_LONG` (MEDIUM) xuất hiện ở Trung tâm ngoại lệ (REQ-EXC-001).
2. Supervisor acknowledge nó (`OPEN→ACKNOWLEDGED`, REQ-EXC-002).
3. Supervisor sửa session trực tiếp từ chi tiết ngoại lệ (REQ-EXC-003).
4. Supervisor resolve ngoại lệ (`→RESOLVED`). **Kỳ vọng**: không còn "active" nữa (BR-015); một lần xảy ra lại mới sẽ mở một bản ghi mới, không bao giờ mở lại bản ghi này.

### JOURNEY-007 — Năng suất Nhân viên: dữ liệu session → KPI/bảng/wallboard phải khớp nhau

1. Seed 5 session mẫu ở §13.4 cho một nhân viên, bao phủ mọi case biên của công thức KPI.
2. `GET /reports/employee-productivity` (REQ-PROD-001). **Kỳ vọng**: số `completed_sessions`, trung bình `productivity_percent`, đúng chính xác theo công thức §8.
3. Vào chi tiết của nhân viên đó. **Kỳ vọng**: mọi session liệt kê khớp 1:1 với số đếm của summary.
4. So sánh với Kiosk wallboard (REQ-KIOSK-004) cho cùng khoảng/filter. **Kỳ vọng**: cùng số liệu nền, chỉ khác về cách trình bày/phân trang.

### JOURNEY-008 — RBAC theo từng persona

1. Dùng chuyển persona autologin (§12.2, chỉ trên sandbox không phải production), đăng nhập lần lượt từng role admin/manager/supervisor/operator/viewer.
2. Với mỗi role, thử mọi hành động ranh giới của từng module ở Phần B (ví dụ `operator` thử Start PO phải thành công theo quy tắc mở rộng ở §3.4; `viewer` thử bất kỳ route `.edit`/`.manage` nào phải `403`).
3. **Kỳ vọng**: mọi ranh giới trong bảng cấp quyền §3.2 (cộng các ngoại lệ §3.4) đều đúng chính xác, cả ở API (`403` kèm đúng mã `permission`) lẫn trên UI (mục nav biến mất, §3.3).

### JOURNEY-009 — Đi qua bộ dữ liệu sản xuất nhiều ngày, realistic (chuẩn tutorial)

1. Seed một bộ dữ liệu trải dài ≥5 ngày làm việc, ≥10 nhân viên, ≥3 PO, với thời lượng session phân bố theo định hướng hình dạng ở §13.4 (phần lớn 4–8h, phân bố năng suất tự nhiên trung bình quanh ~85%, không phải một giá trị đồng đều).
2. Đi qua lần lượt Dashboard → Quản lý Session → Năng suất nhân viên → Trung tâm ngoại lệ. **Kỳ vọng**: cùng số liệu nền nhất quán trên cả 4 màn hình cho cùng khoảng ngày (không có màn hình nào hiện một tổng PO/nhân viên/số lượng mâu thuẫn với màn khác).
3. Thể hiện tối thiểu mỗi loại một lần: một session hoàn thành bình thường, một session `OPEN` (đang thực hiện), một session bị auto-close, một session đã được sửa/adjust, và một bản ghi Trung tâm ngoại lệ đang active. **Kỳ vọng**: mỗi cái phân biệt được về mặt hình ảnh và số liệu trên màn hình liên quan.

---

# PHẦN F — Ma Trận Truy Vết (Traceability Matrix)

Chú giải: **A** = đã có coverage tự động (pytest/Playwright) tại thời
điểm viết, **P** = một phần, **—** = chưa tìm thấy coverage tự động.

| Nhóm yêu cầu | Coverage tự động hiện có (tên file) | Trạng thái |
|---|---|---|
| REQ-AUTH-001..003 (đăng nhập/session thật) | `tests/e2e/tutorial-video.spec.js` (mật khẩu thật), `test_local_8080_login_contract.py`, `test_internal_qa_login_contract.py` | A |
| REQ-AUTH-004/005 (autologin) | `tests/test_autologin_guard_unit.py`, `tests/integration/test_autologin_persona.py`, `tests/test_v6584431_production_hardening.py` | A |
| Ma trận RBAC §3 | `tests/integration/test_permission_matrix.py`, `test_super_admin_system_console.py`/`_unit.py`, `test_rbac_self_heal.py` | A (ở mức ma trận); bảng theo-từng-route đầy đủ của tài liệu này rộng hơn bất kỳ file test đơn lẻ nào hiện có |
| REQ-DASH-* | `tests/e2e/overview-and-calendar.spec.js`, `overview-production-summary.spec.js`, `dashboard-employee-timeline.spec.js` | A |
| REQ-PO-*, REQ-PART-*, REQ-TPL-* | `tests/e2e/catalog-crud.spec.js`, `catalog-visual.spec.js`, `template-ui.spec.js`; `test_p1_audit_2026_08_28.py`, `test_production_state_integrity.py`, `test_production_consistency_p1.py` | A (P cho quy tắc chuyển trạng thái PO ngoài enum, khoảng trống §5.3) |
| REQ-EMP-* | `tests/e2e/catalog-crud.spec.js` | P — chưa có file test riêng cho vòng đời nhân viên |
| REQ-SESS-* | `test_session_lifecycle_state_machine_property.py`, `test_session_lifecycle_observability_phase13.py`, `test_session_overlap_and_exceptions.py`, `test_shift_session_lifecycle.py`, `test_write_path_po_lock_contention.py`, `tests/e2e/session-management-*.spec.js` (3 file) | A |
| REQ-KIOSK-001 (v1) | chỉ gián tiếp, qua `tests/e2e/mesflow.spec.js` | P |
| REQ-KIOSK-002/003 (v2) | `test_kiosk_v2_bootstrap_environment.py`, `test_kiosk_v2_disabled_identity_rejection.py`, `test_kiosk_v2_heartbeat_liveness.py`, `test_kiosk_v2_p0_device_authorization.py`, `test_kiosk_v2_reset_projection_safety.py`, `test_kiosk_v2_shared_terminal.py`, `test_legacy_kiosk_security_phase10.py`, `test_kiosk_offline_sync.py`, `test_offline_sync_concurrency_blocker6.py`, `test_offline_burst_gate14.py`, `test_offline_trusted_timestamp_phase7.py`, `test_kiosk_rebind_security_blocker2.py`, `test_kiosk_lookup_po_status.py` | A — module được test nhiều nhất hệ thống |
| REQ-KIOSK-004 (wallboard) | `test_employee_productivity_wallboard.py` (23 case), `tests/e2e/employee-productivity-wallboard.spec.js` | A |
| REQ-SHIFT-* | `test_shift_dashboard.py`, `test_shift_session_lifecycle.py`, `test_scheduling_time_p2.py`, `test_daily_progress_day_state_semantics.py` | A |
| REQ-EXC-* | `test_v67_exception_center.py`, `test_session_exception_workflow.py`, `test_session_exception_resolution_modal.py`, `test_session_audit_phase14.py`, `tests/e2e/exception-center-v67.spec.js`, `session-exception-detail-drawer.spec.js` | A |
| REQ-PROD-* | `tests/integration/test_employee_productivity.py` (14 case), `test_employee_productivity_wallboard.py` (23 case) | A |
| REQ-TPL-005 (import/export) | chưa tìm thấy file pytest riêng | — |
| REQ-SEARCH-* | `tests/e2e/session-management-dependent-filters.spec.js`, `production-schedule-sticky.spec.js` | A (cho đúng 2 màn hình đó) |
| REQ-TUT-* | `tests/e2e/tutorial-*.spec.js` (3 file), 5 file `test_v6584*.py` | A |
| REQ-SYS-001/002 | họ file `test_v69_system_health.py` | P |
| REQ-SYS-003 (System Console) | `test_super_admin_system_console.py`/`_unit.py` | A |
| REQ-AUDIT-* | `test_v66_session_service.py`, `test_v72_audit_operations_separation.py`, `test_v74_audit_presentation.py`, `tests/e2e/audit-operations-v72.spec.js`, `business-audit-v74.spec.js` | A |
| REQ-API-001/002 | `test_write_path_po_lock_contention.py`, các test offline-sync ở trên | A |
| REQ-API-003 | `test_postgres_schema.py`, `test_migration_matrix_blocker7.py`, `test_deploy_rollback_migration_aware.py`, `test_api_contract.py` | A |
| Phần D (UI/UX) | `tests/e2e/*-visual.spec.js` (catalog, system, ops), `mobile-navigation.spec.js`, `back-navigation.spec.js` | P |
| Phần A §14 (NFR) | concurrency/idempotency: A; security/CSRF, hỗ trợ trình duyệt, SLA hiệu năng: — | P |

---

# PHẦN G — Hướng Dẫn Sinh Testcase QC

## 20.1 Schema output bắt buộc

Mỗi testcase được sinh ra **bắt buộc** dùng đúng cấu trúc này (tên
field khớp §20's schema tiếng Việt bên dưới, xem chi tiết đầy đủ ở
cuối tài liệu, mục "Schema testcase tiếng Việt"):

```
TC-ID | Requirement ID | Priority | Type | Preconditions | Test Data |
Steps | Expected Result | Postconditions | Environment | Role |
Automation Candidate
```

- **TC-ID**: định dạng `TC-<REQ_ID>-<số thứ tự 2 chữ số>`, ví dụ
  `TC-SESS-001-01`.
- **Requirement ID**: đúng một ID từ Phần B/C/D (`REQ-*`/`BR-*`), có
  thể liệt kê nhiều nếu case bao phủ nhiều rule liên quan.
- **Priority**: kế thừa từ field **Độ ưu tiên** của yêu cầu (xem §20.3
  về ngoại lệ).
- **Type**: một trong `positive`, `negative`, `boundary`, `RBAC`,
  `concurrency`, `idempotency`, `state-transition`, `audit`,
  `empty-state`, `responsive` — lấy từ field **Khía cạnh kiểm thử**
  của yêu cầu nguồn.
- **Preconditions**: trạng thái dữ liệu/hệ thống cụ thể cần có trước
  khi chạy — luôn dùng dữ liệu mẫu ở §13 khi có thể, không mô tả mơ hồ.
- **Test Data**: giá trị cụ thể, đầy đủ — không tham chiếu "dữ liệu
  hiện có" mà không nêu rõ giá trị.
- **Steps**: các bước tuần tự, mỗi bước một hành động rõ ràng (gọi API
  gì, click gì).
- **Expected Result**: khẳng định chính xác, đối chiếu trực tiếp với
  field **Kết quả mong đợi**/**Lỗi**/**Chuyển trạng thái** của yêu cầu
  nguồn — không diễn giải lỏng lẻo.
- **Postconditions**: trạng thái dữ liệu sau khi case chạy xong (để
  dọn dẹp hoặc để case tiếp theo dựa vào).
- **Environment**: một trong DEV/DEMO/PRODTEST theo §12 (không bao giờ
  chạy case có tác dụng phụ trên production thật).
- **Role**: persona cụ thể từ §13.1, không phải "một người dùng nào
  đó".
- **Automation Candidate**: `Có` hoặc `Không`, kèm framework gợi ý nếu
  `Có` (pytest / Playwright).

## 20.2 Quy tắc sinh — một yêu cầu → nhiều testcase

Với mỗi yêu cầu, sinh tối thiểu:
1. **Positive** — happy path chính xác như **Luồng chính**/**Kết quả
   mong đợi** mô tả.
2. **Negative** — mỗi nhánh trong **Lỗi** là một case riêng, không
   gộp.
3. **Boundary** — mỗi câu trong field **Ranh giới** là (các) case
   riêng.
4. **RBAC** — chỉ khi **Quyền** liệt kê nhiều hơn 1 role hoặc có ngoại
   lệ ở §3.4 — mỗi role được phép và mỗi role bị `403` là case riêng.
5. **Idempotency** — chỉ cho các yêu cầu liên quan tới REQ-API-001
   (start/finish/adjust/group-finish).
6. **Concurrency/idempotency** — chỉ cho các yêu cầu mà field **Đồng
   thời** khác `N/A` — không tự bịa case đồng thời cho yêu cầu rõ ràng
   không có.
7. **Recovery (khôi phục)** — với bất kỳ yêu cầu mô tả một điều kiện
   lỗi có đường xử lý đã tài liệu hóa (auto-close→sửa, phát hiện ngoại
   lệ→acknowledge/resolve), một case đi qua toàn bộ chuỗi
   lỗi→khôi phục, không chỉ riêng phần lỗi.
8. **Responsive** — chỉ cho các yêu cầu UI/UX ở Phần D — dùng ma trận
   3 viewport từ REQ-UI-006.

## 20.3 Kế thừa độ ưu tiên

Dùng **Độ ưu tiên** tự thân của yêu cầu làm mặc định cho mỗi case
sinh ra; một case có thể được nâng (không bao giờ hạ) nếu nó bao phủ
cụ thể một ranh giới nhạy cảm về bảo mật/toàn vẹn dữ liệu (ví dụ một
case âm RBAC cho một yêu cầu P1 mà ranh giới của nó lại đúng là phân
biệt `admin`-với-`super_admin` nên được coi là P0).

## 20.4 Kiểm tra tự-đầy-đủ (làm điều này trước khi chốt bất kỳ testcase nào)

Trước khi chốt một testcase đã sinh, xác nhận mọi giá trị trong "Test
Data" và "Steps" đều hoặc (a) lấy nguyên văn từ dữ liệu mẫu/persona ở
§13, hoặc (b) được đặc tả đầy đủ tại chỗ, không có tham chiếu chưa
giải quyết kiểu "dữ liệu hiện tại" hay "một bản ghi đã có" — nếu một
testcase không thể được đặc tả đầy đủ mà không cần hỏi lại, đó là tín
hiệu tài liệu này đang thiếu điều gì đó; không được tự bịa câu trả
lời, hãy ghi lại thành một khoảng trống (theo định dạng ở §21).

---

# PHẦN H — Khoảng Trống / Câu Hỏi Mở Đã Biết

Tách riêng khỏi hành vi bình thường của Phần A–G — không có gì ở đây
được coi là hành vi đã đặc tả cho việc sinh testcase; mỗi mục hoặc là
một sự thật thật sự chưa xác minh được (`SPEC-GAP`) hoặc một quyết
định chỉ con người mới quyết được (`OPEN-QUESTION`).

| ID | Khoảng trống |
|---|---|
| SPEC-GAP-001 | Việc mọi trang có role quyền hạn thấp có nhất quán *ẩn* (thay vì hiện-rồi-403) các control sửa hay không chưa được audit từng trang một — §3.3 nói rõ `403` ở mức API là tín hiệu có thẩm quyền, sự hiện diện của nút bấm thì không. |
| SPEC-GAP-002 | Không có đồ thị chuyển trạng thái Production Order nào chặt hơn ngoài việc thuộc enum + hành động Start đã được xác nhận (§5.3) — liệu bản thân UI có tự hạn chế thêm, ví dụ chặn `PAUSED→COMPLETED` trực tiếp hay không, thì chưa xác minh. |
| SPEC-GAP-003 | Thuật toán giải quyết ranh giới ca chính xác cho một timestamp rơi vào khoảng trống giữa các ca, hoặc trong một cửa sổ qua-nửa-đêm mơ hồ, đã được tóm tắt (§4.10/§6.4) nhưng chưa được lần theo từng dòng một cách kiệt cùng. |
| SPEC-GAP-004 | Không tìm thấy đường mã nào cho "mở lại một session đã CLOSED". Không được giả định tính năng này tồn tại; nếu được yêu cầu test nó, hãy gắn cờ thay vì đoán. |
| SPEC-GAP-005 | `exception_records.status='AUTO_IGNORED'` — điều kiện/kích hoạt chính xác để hệ thống (không phải con người) tự động ignore một ngoại lệ chưa được lần tới tận nguồn. |
| SPEC-GAP-006 | Chưa xác nhận có cơ chế CSRF-token nào tồn tại. Có thể đây là chủ đích (SameSite=Lax + frontend cùng origin) hoặc là một khoảng trống thật — cần một security review riêng, không đoán theo hướng nào trong tài liệu này. |
| SPEC-GAP-007 | Không có tuyên bố nào về trình duyệt được hỗ trợ trong hệ thống. Coverage e2e tự động chỉ chạy Chromium qua Playwright. Không được khẳng định tương thích đa trình duyệt. |
| SPEC-GAP-008 | Không có mục tiêu hiệu năng/SLA bằng số nào được tài liệu hóa ở bất kỳ đâu trong hệ thống. `MESFLOW_ACTION_LOG_SLOW_MS` là một ngưỡng log nội bộ, không phải mục tiêu hướng người dùng — không được nhầm lẫn hai cái này. |
| SPEC-GAP-009 | Không tìm thấy file test tự động riêng cho các quy tắc kiểm tra hợp lệ import/export Excel (§10/REQ-TPL-005) — các quy tắc này được tài liệu hóa từ đọc mã trực tiếp, không phải từ một test đang pass sẵn xác nhận từng quy tắc. |
| SPEC-GAP-010 | Policy độ mạnh mật khẩu cho REQ-SYS-002 (tự đổi) và tạo tài khoản chưa được xác nhận đầy đủ — test với một mật khẩu cố tình yếu và ghi lại hành vi thực tế. |
| SPEC-GAP-011 | Liệu một import Excel có một dòng không hợp lệ giữa nhiều dòng hợp lệ có hoàn toàn transactional (tất-cả-hoặc-không-gì) hay áp dụng một phần các dòng hợp lệ trước khi gặp dòng không hợp lệ thì chưa được xác nhận dứt khoát. |
| SPEC-GAP-012 | Ranh giới chính xác giữa `logs.view` (manager nắm giữ) và màn hình action-log/error-trace `@admin_required` (REQ-AUDIT-001) cần một test ranh giới riêng — bảng cấp quyền và decorator route có vẻ mô tả hai thứ khác nhau dưới các tên gần giống nhau. |
| OPEN-QUESTION-001 | Server gốc thật sự đứng sau `mesflow.net` công khai thật, tại nhiều thời điểm trong lịch sử vận hành hệ thống này, thực sự mơ hồ/chưa xác nhận được từ môi trường dev nội bộ — bất kỳ kế hoạch test nào giả định một môi trường cụ thể là "production thật" nên xác nhận lại danh tính đó qua một kiểm tra trực tiếp, xác định (không phải một ánh xạ tên miền giả định) trước khi chạy bất cứ gì nhắm vào nó. |
| OPEN-QUESTION-002 | Liệu System Console (nhóm nav "Hệ thống" ở §2, chỉ super_admin) và Business Audit Trail (REQ-AUDIT-002) có được coi là trong phạm vi của hệ thống coverage video-tutorial hay không là một quyết định sản phẩm, không phải một sự thật tài liệu này có thể tự giải quyết — gắn cờ ở đây, không giả định theo hướng nào. |

---

## 21. Tự kiểm tra tính tự-đầy-đủ

**Câu hỏi đặt ra cho tài liệu này**: *nếu chỉ đưa
`docs/MESFLOW_MASTER_REQUIREMENTS_VI.md` này cho một agent QA không có
quyền truy cập mã nguồn MESFlow, không có hệ thống đang chạy, và không
nhớ hội thoại này, agent đó có sinh được testcase hợp lệ mà không cần
đọc mã hay hỏi lại không?*

**Trả lời**: Có, với các ngoại lệ tường minh đã liệt kê ở Phần H, vốn
được cố tình gọi tên ra chứ không giấu đi. Mọi yêu cầu chức năng ở
Phần B đều mang theo hình dạng đầu vào cụ thể, quy tắc kiểm tra hợp lệ
chính xác, thông báo lỗi/mã lỗi chính xác, và hoặc một chuyển trạng
thái cụ thể hoặc một `N/A` tường minh kèm lý do. Field "Ranh giới" và
"Quyền" của mọi yêu cầu đều trỏ tới dữ liệu test thật, có tên, ở §13
thay vì một "người dùng nào đó" trừu tượng. 14 phụ lục của Phần A chứa
mọi công thức, enum, schema bảng, và sơ đồ luồng mà một yêu cầu tham
chiếu tới — một agent không bao giờ cần rời khỏi file này để giải
quyết một trích dẫn kiểu "§8" hay "§13.4," vì các mục đó nằm trong
cùng tài liệu này. Ở nơi tài liệu này tự nó không chắc chắn (Phần H),
sự không chắc chắn đó chính là output cố ý, đúng đắn — một agent gặp
một `SPEC-GAP` nên sinh một testcase *kiểm tra và ghi lại* hành vi
thực tế thay vì khẳng định một kỳ vọng đã đoán, đúng như §20.4 hướng
dẫn.

---

## 22. Schema testcase tiếng Việt (bắt buộc, dùng khi sinh testcase từ tài liệu này)

Đây là schema **chính thức bằng tiếng Việt**, tương đương 1:1 với
schema ở §20.1 (dùng tên field tiếng Anh cho tương thích công cụ) —
khi bàn giao testcase cho một agent/công cụ chỉ hiểu tiếng Việt, dùng
đúng thứ tự và tên cột này:

| # | Tên cột | Ý nghĩa |
|---|---|---|
| 1 | **TC-ID** | Mã testcase, định dạng `TC-<REQ_ID>-<STT 2 chữ số>` |
| 2 | **Requirement ID** | ID yêu cầu nguồn (`REQ-*`/`BR-*`/`NFR-*`), có thể nhiều ID |
| 3 | **Priority (Độ ưu tiên)** | P0/P1/P2, kế thừa từ yêu cầu nguồn (§20.3) |
| 4 | **Type (Loại)** | positive / negative / boundary / RBAC / concurrency / idempotency / state-transition / audit / empty-state / responsive |
| 5 | **Preconditions (Điều kiện tiên quyết)** | Trạng thái dữ liệu/hệ thống cụ thể cần có trước khi chạy, dùng dữ liệu mẫu §13 |
| 6 | **Test Data (Dữ liệu test)** | Giá trị cụ thể, đầy đủ, không mơ hồ |
| 7 | **Steps (Các bước)** | Danh sách bước tuần tự, mỗi bước một hành động |
| 8 | **Expected Result (Kết quả mong đợi)** | Khẳng định chính xác, đối chiếu trực tiếp với yêu cầu nguồn |
| 9 | **Postconditions (Điều kiện sau)** | Trạng thái dữ liệu sau khi case chạy xong |
| 10 | **Environment (Môi trường)** | DEV / DEMO / PRODTEST (không bao giờ production thật, §12) |
| 11 | **Role (Vai trò)** | Persona cụ thể từ §13.1 |
| 12 | **Automation Candidate (Ứng viên tự động hóa)** | Có/Không + framework gợi ý (pytest/Playwright) nếu Có |

**Ví dụ minh họa (không phải testcase thật, chỉ để minh họa cấu
trúc)**:

```
TC-ID: TC-SESS-001-03
Requirement ID: REQ-SESS-001
Priority: P0
Type: negative
Preconditions: Nhân viên EMP-DEMO-01 (§13.3) đã có 1 session OPEN
  trên OP-DEMO-01-CUT (§13.2).
Test Data: employee_id=EMP-DEMO-01, operation_id=OP-DEMO-01-BEND,
  request_id="tc-sess-001-03-req1".
Steps:
  1. Gọi POST /work-sessions/start với Test Data ở trên.
Expected Result: HTTP 409, thông báo "employee already has an open
  session"; không có dòng work_sessions mới được tạo.
Postconditions: Session gốc của EMP-DEMO-01 trên OP-DEMO-01-CUT vẫn
  OPEN, không đổi.
Environment: DEV
Role: N/A (lệnh gọi hệ thống, không qua role người dùng)
Automation Candidate: Có — pytest (test_session_lifecycle_state_machine_property.py)
```
