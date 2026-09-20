# MESFlow changelog — 65.x

Release notes for the 65.x line, previously 128 separate
`RELEASE_NOTES_V*.md` files in the repository root. Content is verbatim;
only the headings were merged and one level deeper.

**Newest first.** The 65.x line ended at 65.8.44.58; the current line is
71.x, whose releases are recorded as build manifests under `release/`
(`release/mesflow-<version>.json`) rather than as prose notes.

**A caveat worth knowing:** 15 of these files carried a stale version in
their own heading — most visibly 65.8.22 through 65.8.27, where nine
consecutive releases were all headed "v65.8.28". The filename digits were
the real, monotonic sequence, so the version shown below comes from the
filename and the heading's claim is noted inline. Do not treat a version
string inside an old note's prose as authoritative.


## 65.8.44.58

- Thêm OTA foundation cho ESP32-S3 kiosk: inventory, firmware artifact, check/download/event API.
- Firmware upload luôn ở trạng thái draft và SHA256 được tính phía server.
- Thêm migration 0027; chưa chạy trên production.

## 65.8.44.57

- Chuẩn hóa Compose contract để cùng file release có thể được kiểm tra với env profile khác nhau.
- `.env` vẫn là contract runtime được bảo vệ; các biến bí mật bắt buộc tiếp tục fail khi thiếu.
- Không thay đổi schema hoặc business logic.

## 65.8.44.32 — RBAC & Permission Matrix

### Added
- Role-based access control tables and additive Alembic migration `0025_rbac_permissions`.
- System roles: Admin, Manager, Supervisor, Operator, Viewer.
- Permission matrix by module/action.
- Sidebar hides tabs the logged-in role cannot view.
- Backend permission checks for user/role management and permission-aware compatibility for existing role decorators.
- System → Người dùng → Vai trò & phân quyền screen.
- Optional default role-account bootstrap via environment variables; disabled by default in production.

### Migration safety
- Does not delete/recreate/alter existing `users` rows.
- Does not touch passwords, PO, sessions, material-flow ledgers or PostgreSQL runtime data.
- Existing role strings are preserved.
- Admin is always full-access and cannot have permissions reduced.
- Downgrade drops only the three RBAC metadata tables.

## 65.8.44.25

- Fix nút **Dòng vật tư** trong chi tiết PO: modal trước đây dùng sai cấu trúc `.modal`/`.modal-backdrop`, khiến lớp backdrop che nội dung và người dùng bấm như không có phản hồi.
- Hoàn thiện Material Flow theo Operation: hiển thị cấu hình nguồn đầu vào, pool GOOD/REWORK, đã cấp/còn khả dụng, đầu vào đã nhận, sản lượng/phế/rework, các OP downstream, ledger hiện tại và lịch sử audit.
- API `/api/operations/<id>/material-flow` trả thêm `relation`, `downstream`, GOOD/REWORK consumption breakdown và thông tin Part/PO để UI giải thích đầy đủ luồng vật tư.
- Modal có loading/error/retry, đóng bằng backdrop/Escape, responsive cho Full HD và màn hình nhỏ.

## 65.8.44.24

- Thêm Playwright tutorial video Full HD 1920x1080.
- Thêm `npm run video:tutorial` để tự quay video tổng quan các màn hình chính.
- Tutorial chỉ đọc, không tạo/sửa/xóa dữ liệu sản xuất.
- Giữ cấu trúc gateway độc lập và bổ sung vhost `agent.mesflow.net` trong source gateway.
- Gói deploy sạch không mang theo runtime, secrets, node_modules hoặc build artifacts.

## 65.8.44.16

- Chuyển màn Quản lý Session sang danh sách accordion toàn chiều rộng.
- Hiển thị chi tiết session ngay dưới dòng được chọn và giữ nguyên action chỉnh sửa.
- Hiển thị thời lượng realtime cho session đang chạy.
- Giữ filter, session đang mở và vị trí cuộn khi làm mới dữ liệu.
- Cải thiện responsive và xử lý mã PO/Operation dài.

## 65.8.44.15

- Full Linux production deployment package.
- No application behavior or database schema changes.

## 65.8.44.11

- Thiết kế lại giao diện Sửa ca: người dùng nhập giờ HH:mm trực tiếp, không còn thấy start_minute/end_minute kiểu 480/720.
- Đổi Mục tiêu (phút) thành Giờ công mục tiêu (ví dụ 8 giờ), backend vẫn lưu target_minutes để tương thích dữ liệu cũ.
- Tự nhận biết ca qua nửa đêm từ giờ bắt đầu/kết thúc; không cần thao tác checkbox kỹ thuật.
- Khoảng thời gian hiển thị theo cột Loại / Từ / Đến / Ghi chú, responsive cho mobile.
- Giữ nguyên schema và API; không cần migration.

## 65.8.44.10

- Sửa màn Lịch làm việc: nhãn giờ của start_minute/end_minute cập nhật tức thời khi chỉnh số phút.
- Đổi Bắt đầu/Kết thúc ca sẽ đồng bộ mép đầu/cuối của các khoảng WORK thay vì để hai bộ thời gian lệch nhau.
- Ca qua nửa đêm tự quy đổi giờ kết thúc sang +1 ngày khi cần.
- Thêm khoảng mới dựa trên mốc kết thúc gần nhất thay vì luôn hard-code 08:00–12:00.
- Timeline Dashboard tiếp tục đọc trực tiếp intervals đã lưu, nên sau lưu/reload các mốc giờ phản ánh cấu hình mới.
- Đồng bộ version metadata lên 65.8.44.10.

## 65.8.44.9

- Gộp màn Điều hành PO vào Tổng quan sản xuất.
- Bỏ menu Điều hành PO riêng để tránh trùng với danh sách Operation.
- Khối Operation của Tổng quan nay hiển thị Priority, WIP, deadline, session, lý do và hành động đề xuất.
- Thêm filter PO, mức ưu tiên và sort ngay trên Tổng quan.
- Production Order có thể click để lọc nhanh toàn bộ OP.
- Bỏ ký hiệu xếp hạng #1/#2 gây hiểu nhầm; chỉ giữ trạng thái và Priority Score.
- Đồng bộ version 65.8.44.9.

## 65.8.44.8

- Fix PO Control KPI spacing: labels and values render on separate lines with clear visual hierarchy.
- Add explicit PO filter dropdown to reduce long Operation lists.
- Clicking a PO card synchronizes the PO filter; Clear resets both.
- Synchronize VERSION.txt, Python __version__, release.json and Docker image tag to 65.8.44.8.
- Add regression coverage for PO filter and version consistency.

## 65.8.44.7

### Điều hành PO / Operation Priority
- Thêm màn **Điều hành PO** trong nhóm Điều hành.
- Xếp hạng Operation theo deadline PO, độ lệch tiến độ sản phẩm so với kế hoạch thời gian, WIP đầu vào, session đang chạy và tồn rework.
- Trạng thái: `LÀM NGAY`, `CẦN CHÚ Ý`, `ĐÚNG TIẾN ĐỘ`, `CHỜ ĐẦU VÀO`, `HOÀN THÀNH`.
- Mỗi OP hiển thị Priority Score, lý do và hành động gợi ý; score chỉ là advisory, không tự thay đổi dữ liệu sản xuất.
- WIP ưu tiên lấy từ Material Flow Ledger; nếu chưa cấu hình flow thì ước tính từ predecessor; OP đầu chuỗi dùng lượng còn lại của PO.
- Drill-down theo PO, lọc trạng thái, tìm kiếm, sort theo ưu tiên/deadline/tiến độ/mã PO.
- Auto refresh 15 giây.

Không có migration DB mới.

## 65.8.44.6

### Dashboard theo ngày

- Đưa **Thời gian làm việc theo Operation** lên trên **Ngày công theo nhân viên**.
- Mỗi Operation hiển thị đồng thời:
  - Tiến độ thời gian: thời gian thực tế / thời gian định mức.
  - Tiến độ sản phẩm: sản phẩm đạt tổng / sản lượng kế hoạch.
- Hiển thị số lượng dạng `đã đạt / kế hoạch` kèm phần trăm.
- Gộp session đang chạy vào timeline ngày công; bỏ khối Session đang chạy riêng để tránh trùng lặp.
- Timeline nhân viên mặc định sort theo thời điểm bắt đầu session sớm nhất.
- Thêm lựa chọn sort `Tên nhân viên A → Z` để tìm người nhanh hơn.
- Session OPEN tiếp tục hiển thị realtime trên timeline và KPI "Đang làm việc" vẫn được giữ.

## 65.8.44.5

- Làm nổi bật bộ chọn Ca ngày / Ca tối trên Dashboard theo ngày.
- Tự nhận diện ca hiện tại theo giờ Asia/Ho_Chi_Minh khi mở/reload Dashboard.
- Ca tối qua nửa đêm tự gắn với ngày bắt đầu ca trước đó.
- Badge CA HIỆN TẠI và biểu tượng ngày/đêm đổi theo ca đang chọn.
- Người dùng vẫn có thể đổi ngày/ca thủ công để xem lịch sử.

## 65.8.44.4

- Hiển thị rõ Lỗi sửa được (Rework) và Phế trên Tổng quan sản xuất và Dashboard theo ngày.
- API overview/daily-progress trả `rework_qty` ở cấp tổng, PO, Operation và theo ngày.
- Kiosk web thêm nhắc trực tiếp tại màn nhập Đạt/Lỗi rằng có thể chọn `3 · CÓ LỖI FIX ĐƯỢC` ở bước xác nhận.
- Không thay đổi migration; tiếp tục dùng schema head `0022_rework_flow`.

## 65.8.44.3

- Kiosk web: các ô Số đạt, Số lỗi và Lỗi sửa được tự xóa giá trị mặc định `0` khi click/chạm/focus để nhập nhanh.
- Nếu rời ô khi chưa nhập gì, giá trị tự trở về `0`.
- Không thay đổi API, database migration hay logic Rework của v65.8.44.2.

## 65.8.44.2

- Web Kiosk: add reworkable defect flow matching ESP32 kiosk.
- Finish flow: enter good/defect -> 1 OK / 2 Edit / 3 Reworkable defect.
- Rework screen validates rework_qty <= defect_qty.
- Final confirmation: 1 OK / 2 Edit.
- Sends rework_qty to /api/kiosk-web/finish and shows real scrap = defect - rework.
- Keyboard shortcuts 1/2/3 work on confirmation screens.

## 65.8.44.1

### Hotfix: Overview blank after browser reload

- Fixed initial page bootstrap order.
- `app.js` no longer calls `renderOverview()` before `pages/overview.js` is loaded.
- Initial Overview navigation now runs after all page scripts are available.
- Keeps normal tab navigation and Overview 15-second refresh behavior unchanged.

## 65.8.44 — Rework flow

- Adds `rework_qty` as a subset of `defect_qty`; true scrap is derived as `defect_qty - rework_qty`.
- Session finish, supervisor edit and legacy ESP group-finish APIs accept `rework_qty` and enforce `0 <= rework_qty <= defect_qty`.
- Operation totals retain rework quantity; PO/session management screens show rework and derived scrap.
- Material-flow input can consume either `GOOD` output or `REWORK` output from the selected source operation.
- Template/PO Operation editors expose input source kind: **Đạt** / **Lỗi sửa được**.
- Input Consumption Ledger records `source_qty_kind`; normal and rework pools are allocated independently.
- Repair Operations can therefore use only the available rework pool of an upstream Operation.
- Database migration head: `0022_rework_flow`.

Kiosk companion firmware: ESP32 Kiosk v5.1.9 Rework.

## 65.8.43.7

- Security-relaxed ESP32 kiosk mode.
- Legacy kiosk execution APIs no longer reject requests because of kiosk token mismatch.
- Resolve kiosk by device_uuid/device_id and auto-bind unknown device identities as ACTIVE.
- Employee, operation, station and session business validation remains enabled.

## 65.8.43.6

- Fix ESP32 group start/finish `invalid kiosk token` when device identity headers are missing or stale.
- Kiosk auth still prefers device_uuid/device_id, then securely falls back to the SHA-256 kiosk token hash to resolve the ACTIVE identity.
- No ESP firmware update required.

## 65.8.43.5

- Fix ESP32 v5.x kiosk token verification when firmware sends stable `device_uuid` plus display `device_id`.
- Legacy kiosk auth now prefers `X-Device-UUID`/`device_uuid` and falls back to `X-Device-ID`/`device_id`.
- Apply the same identity resolution to group start, group finish, heartbeat and offline event sync.
- Add `/api/kiosk/connect` alias for ESP32 runtime bind flow.
- New binds prefer immutable `device_uuid` as the identity key.

## 65.8.43.4

- Kiosk telemetry compatibility: `/api/kiosk/events` accepts `client_event_id`/`device_id` from ESP firmware as aliases for `event_uuid`/`device_uuid`.
- Preserve legacy telemetry envelope fields inside `payload_json`.
- System Logs: Action Log and Error Trace details expand inline immediately below the selected row; selecting another row closes the previous detail.
- Keeps web/non-kiosk HTTPS behavior unchanged.

## 65.8.43.3

- Fix `/api/lookup` HTTP 500 when kiosk scan event payload is a Python dict.
- Serialize `kiosk_events.payload_json` with `json.dumps(...)` before psycopg execution.
- Prevents `ProgrammingError: cannot adapt type 'dict' using placeholder '%s'`.

## 65.8.43.2

### Kiosk HTTP compatibility

- Allow plain HTTP on port 80 for ESP32 device API routes:
  - `/api/kiosk/*`
  - `/api/station/*`
  - `/api/lookup`
  - `/api/session/group/*`
  - `/api/demo-codes`
- All other HTTP traffic still redirects to HTTPS.
- This avoids HTTP 301 responses for ESP32 firmware using `http://mesflow.net`.

## 65.8.43.1

- Fixed Dashboard theo ngày crash: `runningCard is not defined`.
- Added a scoped `runningCard` renderer for open sessions.
- Added regression coverage to ensure the renderer is declared before use.

## 65.8.43

- Thêm màn hình Tổng quan sản xuất cho trạng thái PO và OP.
- Đổi màn hình cũ thành Dashboard theo ngày, hỗ trợ chọn ngày và ca để xem lịch sử.
- Dashboard ngày truy vấn trực tiếp work_sessions theo khoảng ca nên lịch sử không mất khi sang ngày mới.

## 65.8.42

- Thêm màn hình Action Log, Error Trace và lịch sử Retention trong cùng trung tâm nhật ký.
- Thêm API xem, lọc, xử lý và mở lại Error Trace.
- Đồng bộ trạng thái Error Trace với Action Log liên quan.

## 65.8.41.4

- Fix HTTP 500 at `GET /api/system/action-logs`.
- Escape literal percent signs in parameterized psycopg SQL noise filters.
- Add regression contract test for the Action Log list query.

## 65.8.41.3

### QR API fetch_all hotfix

- Fix HTTP 500 on `GET /api/qr-labels`.
- Import `fetch_all` in `master_data.py`; the endpoint previously raised `NameError`.
- Add static regression test ensuring the route dependency is imported.

## 65.8.41.2

- Fix HTTP 500 from `GET /api/qr-labels?type=EMPLOYEE`.
- QR employee catalogue now depends only on stable core employee columns.
- Optional profile columns can no longer make the QR screen blank on upgraded databases.
- Added regression coverage for the employee QR SQL contract.

## 65.8.41.1

- Sửa QR Print Center không render sau khi API trả dữ liệu.
- Chuẩn hóa response QR và loại bỏ phụ thuộc DOM/global helper không ổn định.
- Tách Nhật ký hệ thống sang `pages/system-logs.js`.
- Sửa lỗi ReferenceError do dùng biến DOM tự sinh từ thuộc tính `id`.
- Thêm loading/error state và regression test cho QR/System Logs.

## 65.8.41

- Thêm popup Dòng vật tư trong chi tiết Operation.
- Hiển thị Nguồn → Đích → Session → số lượng → thời gian, tổng sản xuất/phân bổ/còn lại.
- Phân loại ledger RUNTIME, BACKFILL và ADMIN_EDIT.
- Thêm lịch sử UPDATE/DELETE ledger bằng PostgreSQL trigger.
- Chặn xóa Operation/Part/PO khi đã có Session hoặc ledger.
- Chặn đổi OP nguồn khi đã phát sinh tiêu thụ.
- Chặn giảm sản lượng nguồn thấp hơn lượng đã phân bổ.
- Chặn Excel Replace khi đã có dữ liệu thực thi; bảo vệ Merge khỏi đổi cấu trúc hoặc giảm nguồn sai.

## 65.8.40

- Tách API client, Session Exception Center và QR Print Center khỏi `app.js`.
- Thêm Playwright browser E2E chạy cùng PostgreSQL/Docker test suite.
- Thêm JUnit, HTML report, screenshot và trace khi browser test thất bại.

## 65.8.39.2

- Fix QR Print Center showing blank after successful `/api/qr-labels` request.
- Normalize supported API response shapes and QR field aliases.
- Render textual cards independently from QR image loading.
- Show visible load/render errors instead of leaving a blank area.
- Add result and selected-item counters.

## 65.8.39.1

- Sửa migration 0019 thất bại vì revision ID dài hơn `alembic_version.version_num VARCHAR(32)`.
- Migration 0019 mở rộng cột version lên `VARCHAR(128)` trước khi Alembic ghi revision mới.
- Bổ sung test tĩnh và PostgreSQL integration để ngăn lỗi revision quá dài tái diễn.
- Không đổi revision ID, không cần stamp thủ công và không làm mất dữ liệu.

## 65.8.39

### Automated backup restore verification

- Adds a PostgreSQL integration test that creates a real custom-format `pg_dump` backup.
- Restores the backup into a uniquely named isolated database without replacing the source test database.
- Verifies SHA-256 generation, backup manifest, a real MESFlow data marker, Alembic head, required tables, foreign keys, input-consumption ledger, and Error Trace schema.
- Always terminates restore connections and drops the temporary restore database, including on failure.
- The restore test is part of the standard PostgreSQL Docker/JUnit suite.

## 65.8.38 — Action Log / Error Trace Retention

- Thêm migration `0020_log_retention` với `error_traces` và lịch sử `log_retention_runs`.
- Ghi Error Trace riêng cho lỗi HTTP 500 hoặc exception chưa xử lý.
- Chính sách mặc định: SUCCESS 30 ngày, SLOW 90 ngày, lỗi đã xử lý 180 ngày, lỗi chưa xử lý và security 365 ngày.
- Error Trace đã xử lý 180 ngày, chưa xử lý 365 ngày.
- Xóa theo batch cấu hình, có preview/dry-run và API Admin.
- Thêm `scripts/cleanup-logs.sh` và trình cài cron hàng ngày.

## 65.8.37

- Removed the duplicate Daily Operation Tracking tab; Dashboard remains the single daily operations view.
- Added PostgreSQL operation input consumption ledger.
- Shared upstream availability is calculated across every downstream operation.
- Finish and supervisor edits lock the source operation and update ledger atomically.
- Added migration 0019 with backfill for existing closed downstream sessions.

## 65.8.36

- Thêm workflow Session Exception: NEW, IN_PROGRESS, RESOLVED, IGNORED.
- Thêm phân công, ghi chú, kết quả xử lý và thời gian/người xử lý.
- Hỗ trợ cập nhật hàng loạt và Audit Log.
- Migration 0018_session_exception_workflow.

## 65.8.35

- Thêm màn hình Danh sách QR Code phục vụ in hàng loạt.
- Hỗ trợ QR Nhân viên, Production Order, Part và Operation.
- Lọc theo loại, PO, từ khóa; chọn nhiều; khổ tem 50x30, 70x40, 90x55 và thẻ A4.
- QR SVG sinh nội bộ qua `/api/qr-image`, không phụ thuộc dịch vụ ngoài.

## 65.8.34

- Tích hợp báo cáo năng lực vào màn hình Nhân viên.
- Thêm nút Báo cáo trên từng dòng nhân viên.
- Báo cáo mở dạng popup, tự chọn nhân viên và mặc định 30 ngày.
- Thêm preset 7/30/90 ngày, lọc trạng thái và xuất CSV.
- Gỡ tab Năng lực nhân viên độc lập khỏi menu.

## 65.8.33.4

### Dashboard route contract test hotfix

- Sửa test `test_shift_dashboard_backend_contract` để kiểm tra đúng cách Flask ghép URL từ Blueprint `url_prefix=/api` và route `/dashboard/shift`.
- Không còn yêu cầu chuỗi literal `/api/dashboard/shift` phải xuất hiện nguyên vẹn trong `analytics.py`.
- Đồng bộ VERSION.txt, runtime version, release.json và compose image tag.

## 65.8.33.3

- Sửa Docker test image copy thiếu `release.json` và thư mục `nginx/`.
- Đồng bộ `VERSION.txt`, `app/mesflow/__init__.py`, `release.json` và image tag trong `compose.yml`.
- Cập nhật test Dashboard đọc đúng module lịch ca hiện tại `app/mesflow/core/working_calendar.py`.
- Loại bỏ các assertion image tag khóa cứng `mesflow-app:65.8.9.1`; test dùng version hiện hành.

## 65.8.33.2

- Đồng bộ runtime version với VERSION.txt.
- Dockerfile.test copy đầy đủ scripts và compose.yml cho static/regression tests.
- Cập nhật các test khóa cứng version cũ thành kiểm tra version hiện hành.
- Thay test Control Tower đã bị loại bỏ bằng contract Dashboard shift hiện tại.
- Cập nhật test PO Start và Template theo giao diện đang dùng.

## 65.8.33.1

### Docker test environment hotfix

- Adds `MESFLOW_ENV=test` and a dedicated `MESFLOW_SECRET_KEY` to the `tests` service in `compose.test.yml`.
- Keeps the test runner configuration consistent with `mesflow-test-api`.
- Adds an early guard in `scripts/test/run-all.sh` to refuse production mode and unsafe/missing test secrets.
- Fixes pytest collection failures raised by `mesflow.core.config` before unit tests start.

No database migration.

## 65.8.33 — Automated PostgreSQL/Docker Test Suite

- Added isolated `compose.test.yml` using PostgreSQL 17 tmpfs storage.
- Added migration, schema, API, night-shift, overlap and Session Exception Center integration tests.
- Added one-command runner that builds, executes and cleans all test containers.
- Added JUnit XML reports under `test-results/`.
- Added GitHub Actions workflow for automatic execution on push and pull request.

## 65.8.32 — Session Exception Center & Overlap Guard

### Added
- Session Exception Center under Điều hành.
- Detects overlapping employee sessions, sessions open over 12 hours, long zero-quantity sessions, missing station/device, and invalid time ranges.
- Summary by severity and filters for OPEN/CLOSED sessions.
- Quick navigation back to Session Management.

### Overlap enforcement
- Start session: rejects if the employee has any overlapping session.
- Finish session: validates the final [started_at, ended_at) interval before closing.
- Supervisor edit: rejects employee/time changes that overlap another session.
- Adjacent sessions are valid when one starts exactly when the previous session ends.

### API
- GET /api/session-exceptions?status=OPEN|CLOSED&employee_id=&limit=

No database migration is required.

## 65.8.31

- Đồng nhất màn hình Ca làm việc với các màn hình quản trị.
- Danh sách ca hiển thị dạng bảng, không còn form dài chiếm toàn trang.
- Thêm/Sửa ca mở bằng popup modal.
- Hiển thị rõ giờ làm, giờ nghỉ, ngày áp dụng, mục tiêu và trạng thái.
- Lưu theo từng thao tác chỉnh sửa; Dashboard vẫn dùng cấu hình ca từ database.

## 65.8.30

### Dashboard API theo ca

- Thêm `GET /api/dashboard/shift?shift_date=YYYY-MM-DD&shift_id=<id>`.
- Backend tự tính `range_start` và `range_end` từ cấu hình ca trong database.
- Ca qua nửa đêm được truy vấn trong một khoảng liên tục, ví dụ 18:00 ngày chọn đến 03:00 ngày hôm sau.
- Response gồm `context`, `items`, `sessions`, `activity` dùng chung một biên ca.
- Dashboard không còn gọi hai ngày rồi ghép session ở frontend.
- Sản lượng chỉ được gán cho ca chứa thời điểm báo cáo/kết thúc; thời gian session được cắt theo phần giao với các khoảng WORK.
- Các endpoint cũ `daily-progress` và `daily-sessions` vẫn tương thích, đồng thời nhận `shift_date` và `shift_id`.

## 65.8.29

- Đưa ca làm việc vào PostgreSQL (`work_shifts`, `work_shift_intervals`).
- Seed ca ngày và ca tối, hỗ trợ ca qua nửa đêm.
- API cấu hình ca dùng chung cho Dashboard và tính thời gian session.
- Giữ endpoint working-calendar cũ để tương thích.

## 65.8.28

- Dashboard hỗ trợ chọn Ca ngày và Ca tối.
- Ca tối mặc định: 18:00–22:00, nghỉ 22:00–23:00, 23:00–03:00 ngày hôm sau.
- Timeline ghép session qua nửa đêm bằng dữ liệu hai ngày, khử trùng session và đặt đúng trục 17:00–04:00.
- Session đang mở dừng hiển thị tại cuối cửa sổ làm việc tương ứng; giờ nghỉ không tính vào ngày công.

## 65.8.27

*(Original file `RELEASE_NOTES_V65827.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

- Căn thẳng mốc giờ và thanh session trên cùng trục 07:00–18:00.
- Mốc giờ dùng vị trí phần trăm theo thời gian thật, không chia đều theo số nhãn.
- Vạch dọc trong từng dòng dùng cùng tọa độ với header.
- Giữ nguyên nghỉ trưa, ngoài ca, khoảng hở và vạch thời gian hiện tại.

## 65.8.26.2

*(Original file `RELEASE_NOTES_V658262.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

- Add a dedicated Flask `HTTPException` handler.
- Return routing 404/405 directly without passing through the unexpected-error pipeline.
- Do not capture traceback or classify routing misses as system errors.
- Preserve `X-Trace-ID` for support correlation.

## 65.8.26.1

*(Original file `RELEASE_NOTES_V658261.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

- Preserve Flask/Werkzeug HTTP exceptions instead of converting 404/405 into HTTP 500.
- Return safe JSON for unknown routes with the original HTTP status and trace ID.
- Suppress common PHP/PHPUnit vulnerability-scanner 404 requests from Action Log by default.
- Hide historical scanner-noise entries from System Log list and statistics by default.
- Add `MESFLOW_ACTION_LOG_SCANNER_NOISE=1` to retain scanner probes when security investigation requires them.

## 65.8.26

*(Original file `RELEASE_NOTES_V65826.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

### Remove Admin Kiosk Link

- Removed the **Kiosk** launch item from the Admin/Điều hành sidebar.
- Kept **Trạm kiosk** management, health monitoring, action logs, and error handling.
- Kept the `/kiosk` runtime route and Web Kiosk files for devices that access the kiosk URL directly.
- No database migration.

## 65.8.25

*(Original file `RELEASE_NOTES_V65825.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

### Loại bỏ màn hình báo cáo Session theo Operation trùng lặp

- Gỡ mục **Báo cáo Session theo OP** khỏi menu Điều hành.
- Gỡ route và mã render giao diện `session-report`.
- Gỡ CSS chỉ dùng cho màn hình báo cáo cũ.
- Giữ **Quản lý Session** làm màn hình duy nhất để xem 50 OP gần nhất, lọc theo PO/Part/OP/công nhân, mở chi tiết session và chỉnh sửa.
- Giữ API `/api/reports/operation-sessions` để tương thích với QA Center hoặc client đang gọi trực tiếp.
- Không có migration database mới.

## 65.8.24

*(Original file `RELEASE_NOTES_V65824.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

- Chuyển màn hình chỉnh sửa Session sang popup modal thật.
- Modal không còn chiếm chỗ khi chưa chọn session.
- Hỗ trợ đóng bằng nút Đóng/Hủy, click nền ngoài và phím Escape.
- Khóa cuộn trang nền khi modal mở; tối ưu hiển thị mobile dạng bottom sheet.

## 65.8.23

*(Original file `RELEASE_NOTES_V65823.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

### Input quantity dependency requires source session

- An operation using `input_flow_enabled` cannot start until its input source operation has at least one work session.
- If the same source is also configured as `predecessor_operation_id`, source completion is not required; an actual source session start is required instead.
- Finishing a downstream session with positive quantity now returns a clear message when the source has not reported output yet.
- Kiosk returns `DEP-409` for missing source session and `QTY-409` for missing/insufficient source quantity.
- No database migration is required.

## 65.8.22

*(Original file `RELEASE_NOTES_V65822.md`; its heading read `v65.8.28` — a copy-paste carry-over, corrected here from the filename.)*

- Tách từng session đúng vị trí trên timeline theo nhân viên.
- Mặc định ca ngày 08:00-12:00 và 13:00-17:00.
- Đánh dấu nghỉ trưa, ngoài ca và vạch thời gian hiện tại.
- Session kéo qua nghỉ trưa được tách thành hai đoạn, không tính thời gian nghỉ.
- Session đang mở không kéo dài qua 12:00 hoặc 17:00; cảnh báo session chưa đóng sau cuối ca.
- Đánh dấu khoảng hở từ 15 phút; khoảng hở từ 45 phút dùng cảnh báo mạnh hơn.

## 65.8.21

- Thiết kế lại Dashboard ngày công theo nhân viên.
- Mỗi nhân viên chỉ hiển thị một dòng, tổng hợp toàn bộ session trong ngày.
- Hiển thị tổng giờ làm so với mục tiêu 8 giờ, thời gian còn lại hoặc vượt giờ.
- Ghép các session/Operation thành nhiều đoạn trên timeline 24 giờ.
- Hiển thị số session, session đang chạy, các OP đã làm và tổng sản lượng đạt/lỗi.

## 65.8.20.1

- Fix `fmtDuration is not defined` in Quản lý Session.
- Promote duration formatter to a shared JavaScript helper.
- Remove the Dashboard-only duplicate formatter.

## 65.8.20

*(Original file `RELEASE_NOTES_V65820.md`; its heading read `v65.8.20.1` — a copy-paste carry-over, corrected here from the filename.)*

### Quản lý Session theo Operation gần nhất

- Màn hình mặc định chỉ tải tối đa 50 Operation có hoạt động gần nhất.
- Operation có session OPEN được ưu tiên lên đầu.
- Có thể lọc theo PO, Part, Operation, công nhân và chỉ OP đang chạy.
- Bấm Operation để tải riêng danh sách session của Operation đó.
- Chọn session trong phần chi tiết để chỉnh sửa bằng luồng audit hiện có.
- Sau khi lưu, danh sách Operation và chi tiết session tự làm mới.
- Giảm đáng kể số lượng session phải render khi mở màn hình.

Không có migration mới.

## 65.8.19

- Thêm màn hình Quản lý Session.
- Lọc phân cấp theo PO, Part, Operation, công nhân, trạng thái và khoảng ngày.
- Cho phép chỉnh công nhân, OP, trạm, thời gian bắt đầu/kết thúc, trạng thái, sản lượng và ghi chú.
- Bắt buộc nhập lý do chỉnh sửa.
- Cập nhật tổng sản lượng OP trong cùng transaction khi sửa hoặc chuyển session.
- Ghi Audit Log và Action Log với dữ liệu trước/sau.

## 65.8.18.2

### Hotfix Nhật ký hệ thống

- Sửa lỗi JavaScript `ReferenceError: card is not defined` khi mở màn hình Nhật ký hệ thống.
- Thêm helper `systemLogStatCard()` riêng để render các thẻ thống kê 24 giờ.
- Không thay đổi schema database và không có migration mới.

## 65.8.18.1

*(Original file `RELEASE_NOTES_V658181.md`; its heading read `v65.8.18.2` — a copy-paste carry-over, corrected here from the filename.)*

### Deploy and KPI hotfix

- Fixed Alembic 0016 down_revision to reference actual revision `0015`.
- Fixed `/api/kpi/operations` PostgreSQL GROUP BY using `po.id`.
- No additional schema changes beyond migration 0016.

## 65.8.18 — Action Log & Error Trace

- Global `X-Trace-ID` for request correlation.
- Logs user/kiosk action, API, status, duration, sanitized request/response and context.
- Stores full server traceback for unhandled errors while client receives a safe message.
- New Admin screen **Nhật ký hệ thống** with filters, detail and incident resolution notes.
- Passwords, tokens, authorization, cookies and secrets are masked.
- Migration `0016_action_error_logs` creates indexed `action_logs`.

## 65.8.17

- Hoàn thiện quản lý trạm kiosk: đăng ký/bind, heartbeat, online/offline, action timeline, lỗi và xử lý lỗi.
- Tương thích API ESP/SQLite cũ: `/api/kiosk/bind`, `/api/station/heartbeat`, `/api/station/events/sync`.
- Không bắt buộc cập nhật firmware ESP cũ.

## 65.8.16.1

- Validate normalized Template Part codes on tree save and again before PO instantiation.
- Return structured `DUPLICATE_PART_CODE_IN_TEMPLATE` / `EMPTY_PART_CODE` errors instead of raw PostgreSQL exceptions.
- Add `GET /api/templates/{template_id}/validate` for Admin UI and QA Center.
- Correct duplicate Part codes in `DEMO-E10-LAP-RAP` and `DEMO-E10-FULL` seed sources.
- Keep PO cloning inside one database transaction; validation occurs before the PO insert.
- Hide database exception details from API clients while retaining server-side exception logs.

## 65.8.16

### Báo cáo năng lực nhân viên
- Chọn từng nhân viên và lọc theo ngày/trạng thái session.
- KPI session, giờ làm, sản lượng, SP/giờ, tỷ lệ đạt/lỗi.
- Hiệu suất so với thời gian chuẩn của Operation.
- Phân tích năng lực riêng theo từng Operation.
- Cảnh báo chưa đủ dữ liệu trước khi xếp loại tham khảo.
- Danh sách chi tiết session và xuất CSV.

Không có migration database mới.

## 65.8.15

- Thêm màn hình Báo cáo Session theo Operation.
- Lọc theo OP, khoảng ngày và trạng thái session.
- Tổng hợp user đã chạy OP: số session, thời gian, sản lượng, lần hoạt động cuối.
- Danh sách chi tiết từng session và xuất CSV.
- Không cần migration database.

## 65.8.14

*(Original file `RELEASE_NOTES_V65814.md`; its heading read `v65.8.15` — a copy-paste carry-over, corrected here from the filename.)*

- Thêm bảng thời gian làm việc tổng hợp theo Operation trên Dashboard.
- Tổng hợp thời gian từ mọi Work Session trong ngày, có cắt theo biên ngày.
- So sánh thời gian thực tế với định mức = planned_quantity × standard_seconds_per_unit.
- Hiển thị nhanh/chậm, số session, người làm, sản lượng đạt/lỗi.
- Giữ nguyên timeline chi tiết theo từng nhân viên/session.
- Không có migration database mới.

## 65.8.13.1

### Hotfix
- Sửa API `/api/dashboard/daily-sessions` dùng sai cột `employees.code`.
- Dùng đúng `employees.employee_no AS employee_code`.
- Không thay đổi schema hoặc dữ liệu.

## 65.8.13

*(Original file `RELEASE_NOTES_V65813.md`; its heading read `v65.8.13.1` — a copy-paste carry-over, corrected here from the filename.)*

- Thêm auto-login dành riêng cho giai đoạn test, vẫn giữ trang đăng nhập.
- Auto-login thực hiện phía server, không đưa mật khẩu admin xuống trình duyệt.
- Thêm API `/api/dashboard/daily-sessions` trả từng Work Session theo ngày.
- Khôi phục thanh thời gian 00:00–24:00 trên Dashboard.
- Mỗi thanh tương ứng một nhân viên/session, hiển thị PO, Operation, bắt đầu, kết thúc, thời lượng, đạt và lỗi.
- Session đang mở tự cập nhật thời lượng mỗi 10 giây.

Trước khi production: `MESFLOW_TEST_AUTO_LOGIN=0`.

## 65.8.12

- Thêm Hệ thống → Người dùng.
- Admin tạo tài khoản, đổi vai trò, khóa/mở khóa.
- Admin reset mật khẩu và tùy chọn bắt đổi mật khẩu.
- Người dùng tự đổi mật khẩu với mật khẩu hiện tại.
- Ghi Audit Log cho các thay đổi tài khoản và mật khẩu.

## 65.8.11

- Dashboard được rút gọn thành màn hình điều hành theo ngày.
- Chỉ hiển thị OP có phát sinh session/cập nhật trong ngày.
- Tách danh sách Operation số lượng lớn sang màn hình Theo dõi OP theo ngày.
- Có lọc ngày, trạng thái và tìm kiếm.
- Ưu tiên OP đang chạy, OP có lỗi và cập nhật sản lượng mới nhất.

## 65.8.10.1

*(Original file `RELEASE_NOTES_V658101.md`; its heading read `v65.8.11` — a copy-paste carry-over, corrected here from the filename.)*

### Hotfix Tiến trình

- Sửa PostgreSQL `GroupingError` tại API `/api/production-schedule`.
- Thêm `src.id` vào `GROUP BY` để các trường của Operation nguồn (`src.code`, `src.name`, `src.done_qty`) được chọn hợp lệ.
- Không thay đổi cấu trúc response, công thức Material Flow hoặc giao diện Gantt.
- Không cần migration database.

## 65.8.10

*(Original file `RELEASE_NOTES_V65810.md`; its heading read `v65.8.11` — a copy-paste carry-over, corrected here from the filename.)*

- Hoàn thiện màn hình Tiến trình với Gantt dùng chung trục thời gian theo PO.
- Hiển thị kế hoạch/thực tế, trạng thái, tiến độ và session đang chạy theo Operation.
- Thêm bộ lọc PO và tự cập nhật mỗi 15 giây.
- Thêm Material Flow: OP nguồn, số lượng đã cấp, đã tiêu thụ, còn khả dụng và cảnh báo thiếu đầu vào.
- Không có migration database mới.

## 65.8.9.2

- Tách Hoạt động gần đây thành hai sự kiện độc lập: Bắt đầu session và Nhập sản lượng.
- Hiển thị nhân viên, PO, Operation, số đạt, số lỗi và thời gian theo Asia/Ho_Chi_Minh.
- Một session đã hoàn tất sẽ xuất hiện hai dòng: thời điểm bắt đầu và thời điểm báo sản lượng.

## 65.8.9.1

- Fix Control Tower kiosk health not updating.
- Web Kiosk Demo now sends heartbeat immediately, on screen state changes, and every 30 seconds.
- Dashboard includes active kiosk identities that have never sent heartbeat and marks them Offline.
- Hardware kiosk heartbeat remains token-protected.

## 65.8.9

*(Original file `RELEASE_NOTES_V6589.md`; its heading read `v65.8.9.1` — a copy-paste carry-over, corrected here from the filename.)*

### Scanner error codes
- Kiosk displays a stable error code, message and corrective action.
- Standard codes include SCN-001/002/003/004, EMP-001, OP-001, PO-001, SES-409, QTY-409, NET-001 and SYS-500.
- API responses preserve `error_code` and `action` so ESP/web kiosks can show the same guidance.

### Timezone consistency
- Database connections run in UTC.
- Web UI and kiosk clock explicitly render `Asia/Ho_Chi_Minh` (UTC+7), independent of browser/server timezone.
- `datetime-local` PO schedule values are interpreted as Ho Chi Minh City time and converted to UTC before sending.
- Docker services receive `TZ=Asia/Ho_Chi_Minh`; PostgreSQL client timezone remains UTC.

## 65.8.8

### Sửa tạo PO từ màn hình Production Order

- Thêm API riêng `/api/templates/available-for-po` trả danh sách Template active cùng số Part và Operation.
- Form **Tạo PO từ Template** ở màn hình Production Order và Control Tower dùng chung API này.
- Dropdown tự chọn Template hoàn thiện đầu tiên, hiển thị mã, tên, version, số Part và số OP.
- Có fallback về API danh sách Template cũ nếu backend chưa tải route mới.

### Template demo dễ chạy hơn

- Nâng bộ demo lên `DEMO-2.0`.
- Nút **Nạp Template demo** cập nhật lại cả Template demo cũ thay vì bỏ qua.
- Không tự tạo phụ thuộc thời gian giữa tất cả Operation khi sinh PO.
- Chỉ giữ 11 quan hệ giới hạn số lượng trên ba Template demo để kiểm thử Material Flow.
- Các Operation còn lại có thể chạy độc lập trong demo.

Không có migration database mới. PO demo đã tạo từ phiên bản cũ không tự thay đổi; dùng Force Delete rồi tạo lại từ Template demo `DEMO-2.0` để nhận cấu hình mới.

## 65.8.7

### Tạo Production Order từ Template

- Production Order mới bắt buộc chọn Template nguồn.
- Khi tạo PO, hệ thống sao chép toàn bộ Part, Operation, thời gian chuẩn, thiết bị, phụ thuộc tuần tự và quan hệ dòng vật liệu từ Template.
- PO lưu `source_template_id`, mã Template và version Template để truy vết.
- Sau khi sao chép, PO là bản độc lập và có thể override mà không sửa Template.
- API tạo PO rỗng bị khóa; POST `/api/production-orders` chỉ chấp nhận khi có `template_id`.
- Import Operation không còn tự sinh PO rỗng; PO phải được tạo từ Template trước.
- Sau khi tạo thành công, giao diện tự mở PO mới và hiển thị số Part/Operation đã sao chép.
- PO ở trạng thái PLANNED có nút Start PO; sau Start, Operation xuất hiện trong Kiosk Demo và PO xuất hiện trên Control Tower.

### Database

- Migration `0015_po_template_source`.

## 65.8.6

### Start Production Order

- Thêm API `POST /api/production-orders/{id}/start`.
- Thêm nút Start PO tại danh sách, chi tiết và PO sắp triển khai trên Control Tower.
- PO chuyển sang `IN_PROGRESS` sau khi Start và xuất hiện ở vùng điều hành Dashboard.
- Kiosk Demo chỉ tải Operation thuộc PO `IN_PROGRESS`.
- Quét hoặc Start Session với OP của PO chưa Start sẽ bị từ chối.
- Không có migration database mới.

## 65.8.5

### Control Tower hoàn chỉnh

- Dashboard được tổ chức theo 3 tầng: nhìn nhanh tình trạng xưởng, hàng đợi cần can thiệp và drill-down PO/Operation.
- KPI realtime: đầu ra/yield hôm nay, tiến độ PO active, session, nhân viên, kiosk và cảnh báo nghiêm trọng.
- Biểu đồ nhịp sản xuất 7 ngày từ dữ liệu Work Session.
- Bảng sức khỏe PO phân loại: quá hạn, trễ kế hoạch, thiếu người, thiếu định mức, đúng kế hoạch và đang chuẩn bị.
- Hàng đợi cảnh báo ưu tiên và nút mở trực tiếp PO liên quan.
- Phát hiện bottleneck theo thời gian session và WIP chờ giữa OP nguồn/OP đích.
- Sức khỏe kiosk: online/offline, hàng đợi, lỗi và heartbeat gần nhất.
- Quick actions: tạo PO, mở tiến trình, mở kiosk, refresh và bật/tắt auto-refresh.
- Không có migration database mới.

## 65.8.4

- Đổi thao tác **Chi tiết/Quản lý Part / OP** thành **Mở**.
- Nút **Mở** đi vào không gian quản lý PO: thông tin tổng quan, Part và Operation.
- Nút **Sửa** chỉ thay đổi thông tin chung của PO.
- Tạo PO mới xong tự động mở PO để tiếp tục thêm Part/Operation.
- Sửa PO từ danh sách quay lại danh sách; sửa khi đang mở PO giữ nguyên PO đang làm việc.
- Đồng bộ mọi nút Mở PO trên Dashboard về cùng một hàm và sửa lỗi gọi nhầm hàm.

## 65.8.3

- Thêm Force Delete Production Order dành cho giai đoạn test.
- Yêu cầu nhập lại chính xác mã PO và xác nhận hai lần.
- Xóa trong một transaction các session, QC, điều chỉnh, penalty, kiosk event và idempotency liên quan trước khi xóa PO.
- Có thể tắt khi production bằng `MESFLOW_ENABLE_FORCE_DELETE_PO=0`.

## 65.8.2

- Chuyển menu sang sidebar dọc bên trái.
- Có nút thu gọn/mở rộng sidebar và lưu trạng thái trên trình duyệt.
- Trên màn hình nhỏ sidebar ẩn hoàn toàn và mở bằng nút menu.
- Giữ các nhóm chức năng đã tinh gọn ở v65.8.1.

## 65.8.1

- Gom menu thành 5 nhóm dropdown theo nhu cầu sử dụng.
- Giữ Tổng quan là nút truy cập nhanh.
- Tạm ẩn các màn hình chưa hoàn thiện: Sales Order, Work Sessions, QC, Kiosk Events, KPI, Thông báo, Monitoring và Audit Logs.
- Giữ nguyên code/API của các màn hình ẩn để có thể bật lại sau.
- Thêm lối mở Kiosk trực tiếp từ nhóm Điều hành.

## 65.8.0

- Sửa lỗi Dashboard `fmt is not defined` bằng helper định dạng ngày giờ dùng chung.
- Sắp xếp lại menu theo luồng nghiệp vụ: Tổng quan, Kế hoạch sản xuất, Điều hành sản xuất, Danh mục, Phân tích & cảnh báo, Hệ thống.
- Loại bỏ nhóm menu mơ hồ “Quản trị dữ liệu”.

## 65.7.9

- Hoàn thiện tab Tổng quan để luôn có nội dung hữu ích.
- Bổ sung PO sắp triển khai theo trạng thái DRAFT, PLANNED, RELEASED.
- Bổ sung hoạt động gần đây từ Work Session, QC và Kiosk Event.
- KPI PO hiển thị thêm số PO chờ bắt đầu và tạm dừng.
- Thêm lối tắt mở danh sách PO và chi tiết PO.
- Giữ nguyên Dashboard realtime, session, cảnh báo và cây tiến trình.

## 65.7.8

- Thêm 3 Template demo E10GRE/SMR10GRE từ file GO ROUTER của người dùng.
- Mỗi Operation demo có thời gian chuẩn ước tính để thử Dashboard/timeline.
- Thêm nút Nạp Template demo và Xóa demo; chỉ xóa Template có dấu demo, không xóa PO.
- Tách rõ thao tác PO: Quản lý Part/OP và Sửa thông tin.
- Sửa nút Sửa PO bằng event binding, cập nhật đúng màn hình sau khi lưu.

## 65.7.7

- Material flow: user-configurable source Operation across Parts in the same PO.
- Output good quantity of source limits consumable quantity of target Operation.
- Optional defect quantity consumption.
- Kiosk finish rejects quantity exceeding available input.
- PO Operation editor can override cycle time, equipment, status, dependencies, and material-flow settings.
- Template stores default material-flow settings and copies them when creating a PO.

## 65.7.6

- Chuẩn hóa vòng đời PO: DRAFT, PLANNED, RELEASED, IN_PROGRESS, PAUSED, COMPLETED, CANCELLED.
- Dashboard chỉ hiển thị PO RELEASED/IN_PROGRESS/PAUSED.
- Tự chuyển PO sang IN_PROGRESS khi session đầu tiên bắt đầu.
- Tự hoàn thành PO khi toàn bộ Operation hoàn thành.
- Thêm phụ thuộc Operation kiểu Finish-to-Start và lag phút.
- Thêm màn hình Tiến trình timeline PO → Part → Operation.

## 65.7.5.4

- Thu gọn nút xóa Operation trong Template thành nút icon vuông.
- Thanh thời gian Dashboard tăng mỗi giây và hiện đồng hồ giây.
- Dừng bộ đếm trong giờ nghỉ và ngoài ca theo Working Calendar.
- Phần trăm thời gian hiển thị 1 chữ số thập phân để thấy chuyển động realtime.

## 65.7.5.3

### Single planned quantity source

- `production_orders.planned_quantity` is now the only production target.
- Removed duplicated `plan_qty` columns from runtime and template operations.
- Dashboard, kiosk, KPI, completion logic, Excel import/export and Template instantiation all read the PO target.
- Migration 0012 recovers missing PO quantities from legacy operation values before dropping duplicate columns.

## 65.7.5.1

### Deploy fix

- Shorten Alembic revision `0010_template_part_drawing_po_schedule` to `0010`.
- Prevent `alembic_version.version_num VARCHAR(32)` truncation during upgrade.
- Keep migration chain `0009_working_calendar -> 0010`.
- Synchronize runtime, release metadata, schema version, and Docker image tag to 65.7.5.1.

## 65.7.5

- Dashboard bỏ thanh tiến độ sản lượng trong cây PO.
- Sản lượng hiển thị dạng đạt / kế hoạch kèm phần trăm.
- Giữ duy nhất thanh thời gian đã trôi / thời gian định lượng.
- Thanh thời gian và phần trăm cập nhật mỗi giây từ mốc elapsed server, có trừ lịch nghỉ.
- Chỉ hiển thị số lỗi khi lỗi lớn hơn 0.

## 65.7.4

- Ẩn trường/cột thứ tự trong giao diện Template; hệ thống vẫn giữ thứ tự nội bộ theo vị trí.
- Upload bản vẽ cho từng Template Part, lưu trong runtime/uploads và sao chép sang Part khi tạo PO.
- Production Order có thời gian bắt đầu dự kiến và kết thúc dự kiến.
- Bổ sung migration 0010_template_part_drawing_po_schedule.

## 65.7.3

- Working Calendar Phase 1.
- Cấu hình ca làm và nghỉ trưa.
- Trừ thời gian nghỉ khỏi session, kỳ vọng sản lượng, thanh tiến độ và cảnh báo.

## 65.7.2

- Thêm thanh thời gian đã trôi so với thời gian định lượng trên session đang chạy.
- Hiển thị song song tiến độ thời gian và tiến độ sản lượng.
- Màu xanh bình thường, vàng từ 85%, đỏ từ 110% định mức.
- Thanh thời gian cập nhật mỗi giây, snapshot dữ liệu vẫn cập nhật mỗi 10 giây.
- Hiển thị thanh thời gian trong cây PO → Part → Operation.

## 65.7.1

- Thêm thời gian chuẩn cho mỗi Operation trong Template.
- Hỗ trợ nhập theo giây/sản phẩm hoặc phút/sản phẩm.
- Lưu chuẩn nội bộ bằng giây/sản phẩm để tránh sai số.
- Sao chép thời gian chuẩn sang Operation khi tạo Production Order.
- Dashboard hiển thị thời gian kế hoạch và sản lượng kỳ vọng của session.
- Cảnh báo session chậm tốc độ theo thời gian chuẩn.
- Excel Template hỗ trợ cycle_time_value và cycle_time_unit.

Công thức: thời gian kế hoạch Operation = số lượng kế hoạch × thời gian chuẩn mỗi sản phẩm. Sản lượng kỳ vọng của session = thời gian đã chạy / thời gian chuẩn mỗi sản phẩm.

## 65.7.0

- Rà soát tương thích SQL psycopg3.
- Sửa ký tự phần trăm trong truy vấn cảnh báo Dashboard.
- Không truyền tuple rỗng vào cursor.execute() cho câu SQL không có tham số.
- Đồng bộ version runtime và Docker image tag.

## 65.6.9

- Dashboard điều hành realtime bằng snapshot polling 10 giây.
- Bảng session đang chạy và thời gian vận hành.
- Cây PO → Part → Operation với sản lượng và người đang làm.
- Cảnh báo ngoại lệ tính động: kiosk offline, session chạy lâu, PO trễ/sắp trễ, tỷ lệ lỗi cao.
- Không thay đổi database và không cần migration.

## 65.6.8.2

- Bỏ tiêu đề dashboard lặp lại.
- Giữ panel Demo Kiosk ổn định, không ép focus scanner khi đang thao tác.
- Tạm dừng auto-reset khi Demo đang mở.
- Giữ lựa chọn nhân viên và Operation khi tải lại danh sách demo.

## 65.6.8.1 — Deploy consistency fix

- Đồng bộ image tag Compose với runtime/version: 65.6.8.1.
- Sửa preflight/backup dùng đúng thư mục PostgreSQL `runtime/postgres-v65`.
- Preflight báo rõ khi thiếu certificate Nginx thay vì để container nginx khởi động thất bại.
- Thêm `pytest.ini` để test tìm đúng package trong thư mục `app`.
- Loại bỏ cache Python/pytest khỏi gói phát hành.

## 65.6.8

- Khôi phục Dashboard theo bố cục trung tâm điều hành của bản SQLite.
- Thẻ KPI, bộ lọc, tab PO/session/hoạt động và thanh tiến độ trực quan.
- Không thay đổi database hoặc API.

## 65.6.7.3

- Sửa lỗi `Object of type datetime is not JSON serializable` khi quét Operation.
- Chuẩn hóa response kiosk sang JSON-safe trước khi lưu JSONB và trả API.
- Hỗ trợ datetime/date/time, Decimal, UUID và cấu trúc lồng nhau.
- Không cần migration database.

## 65.6.7.2

- Sửa lỗi Web Kiosk khi quét Operation: psycopg không thể adapt Python dict vào cột JSONB.
- Dùng `Jsonb(response)` khi ghi bảng `kiosk_idempotency` cho cả START và FINISH.
- Không cần migration database.

## 65.6.7.1

Hotfix lỗi API dữ liệu demo kiosk truy vấn các cột không tồn tại `parts.position` và `operations.position`.

- Đổi sắp xếp sang `parts.sort_order` và `operations.sort_order`.
- Thêm `parts.id` làm thứ tự phụ để kết quả ổn định.
- Không thay đổi database và không cần migration.

## 65.6.7

- Ẩn tab Part và Operation khỏi menu chính.
- Tích hợp Part và Operation vào màn hình chi tiết Production Order.
- Thêm/sửa/xóa Part và Operation trong đúng ngữ cảnh PO.
- Chuyển nút nhập/xuất Excel Operation về màn hình Production Order.

## 65.6.6

- Thêm bảng Demo QR trên trang `/kiosk`.
- Lấy danh sách nhân viên hoạt động và Operation trực tiếp từ PostgreSQL.
- Nút Quét thẻ/Quét Operation gọi cùng luồng API với máy quét USB.
- Hỗ trợ copy QR và tải lại dữ liệu demo.

## 65.6.5.1

- Fix `NameError: fetch_all is not defined` in employee list statistics.
- No database migration required.

## 65.6.5

- Import Template trực tiếp từ file GO ROUTER nhiều sheet.
- Mỗi sheet được chuyển thành một Part; các dòng `OPERATION #` được chuyển thành Operation.
- Vẫn tương thích định dạng chuẩn 3 sheet Template/Parts/Operations.
- Migration 0007 đưa 26 nhân viên từ seed SQLite sang PostgreSQL, chỉ thêm mã còn thiếu.

## 65.6.4

- Thêm trang kiosk web tại `/kiosk`.
- Hỗ trợ quét QR nhân viên `WF|EMP|...`.
- Hỗ trợ quét QR Operation `WF|OP|...`.
- Bắt đầu Work Session và kết thúc bằng số lượng đạt/lỗi.
- Tự nhận diện phiên đang mở khi quét lại thẻ nhân viên.

## 65.6.3

- Khôi phục màn hình quản lý nhân viên theo giao diện SQLite.
- Bổ sung hồ sơ nhân viên mở rộng bằng migration PostgreSQL an toàn.
- Thêm lọc theo bộ phận, trạng thái và tìm kiếm toàn bộ thông tin.
- Hiển thị tổng session và tổng sản phẩm đạt theo nhân viên.
- Giữ QR chuẩn `WF|EMP|<MÃ NHÂN VIÊN>`.

## 65.6.2

- Chuyển tính năng Import/Export Operation Excel từ giao diện SQLite sang PostgreSQL.
- Xuất workbook Operations + Huong_dan.
- Nhập chế độ Gộp hoặc Thay toàn bộ.
- Hỗ trợ bảng Operations và file quy trình nhiều sheet.
- Tự tạo PO/Part còn thiếu khi nhập.

## 65.6.0 — Phase 1 SQLite UI Restoration

- Khôi phục khung giao diện kiểu SQLite: header trên, thanh điều hướng ngang, panel/bảng/modal cổ điển.
- Giữ nguyên API và backend PostgreSQL.
- Không thêm nghiệp vụ mới.
- Áp dụng đồng nhất cho Dashboard, Master Data, Production Order, Template và các trang dữ liệu hiện có.

## 65.5.8

- Khôi phục giao diện thêm Template dạng modal như bản cũ.
- Giữ nút + Thêm Template trên thanh công cụ.
- Sau khi tạo thành công, tự mở form Thêm Part.
- Giữ nút + Thêm Part trực tiếp trên từng Template.

## 65.5.7

- Thêm nút **+ Thêm Part** hiển thị trực tiếp trên từng Template.
- Sau khi tạo Template, mở ngay form tạo Part.
- Form Part lưu vào `template_parts` thông qua `PUT /api/templates/<id>/tree` và giữ nguyên Operation/Equipment hiện có.
- Kiểm tra trùng mã Part và trường bắt buộc.

## 65.5.6

### Template creation UI
- Added a permanently visible "Tạo Template mới" form on the Template page.
- The form sends POST /api/templates with code, name, product, version and active status.
- After successful creation, the list reloads and the Template structure builder opens automatically.
- Existing edit, delete, structure builder and instantiate-to-PO actions remain available.
- Added explicit loading and error states to the create button.

## 65.5.5 — Template CRUD UI

- Hoàn thiện màn danh sách Template: tìm kiếm, thêm, sửa, xóa và trạng thái sử dụng.
- Hoàn thiện Template Builder cho Part, Operation và thiết bị chung.
- Thêm cảnh báo khi xóa Part đang chứa Operation và khi đóng cấu trúc chưa lưu.
- Chọn thiết bị từ Master Data thay cho nhập Equipment ID thủ công.
- Thêm kiểm tra mã Part trùng, dữ liệu bắt buộc, số lượng âm và thiết bị trùng.
- Thêm form đầy đủ để tạo Production Order từ Template: Sales Order, số lượng, ưu tiên, hạn giao và ghi chú.
- Bổ sung validation phía backend cho thông tin Template và cây cấu trúc.

## 65.5.4 — Production Order UI

- Thêm màn Production Order chuyên dụng.
- Nút + Thêm PO rõ ràng.
- Form chọn Sales Order, sản phẩm, kế hoạch, trạng thái, ưu tiên, hạn giao và ghi chú.
- Sửa, xóa và tìm kiếm PO.

## 65.5.3 — Template Builder

- Thêm nút + Thêm Template.
- Form tạo/sửa Template.
- Thiết kế Part, Operation, thiết bị.
- Lưu cây Template.
- Tạo Production Order từ Template.

## 65.5.2 — Admin Route Fix

- Thêm `/admin` và `/admin/`.
- Chưa đăng nhập sẽ chuyển tới `/login?next=/admin`.
- Sau đăng nhập quay lại giao diện quản trị.
- `/dashboard` và `/admin` đều dùng Web UI tại `/app`.
- Thêm `/api/system/ui-routes`.

## 65.5.1 — Admin Login Reset Fix

- Thêm CLI `python -m mesflow.cli reset-admin`.
- Thêm script `scripts/reset-admin-password.sh`.
- Reset/upsert admin trong PostgreSQL, bật lại `active=true`.
- Không tự reset mật khẩu ở mỗi lần deploy.
- Thêm `/api/system/auth-health`.

## 65.5.0 — Web UI Foundation

- Login UI
- Dashboard UI
- Master Data CRUD UI
- Execution, KPI, Events, Notifications, Audit and Monitoring views
- PostgreSQL native backend unchanged

## 65.4.2 — Alembic psycopg v3 hotfix

- Giữ DATABASE_URL dạng `postgresql://` cho ứng dụng psycopg v3.
- Alembic tự chuyển nội bộ sang `postgresql+psycopg://`.
- Không còn yêu cầu package `psycopg2`.
- Dùng `create_engine()` trực tiếp, tránh SQLAlchemy tự chọn dialect psycopg2.
