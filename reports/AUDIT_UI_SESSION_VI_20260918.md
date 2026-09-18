# AUDIT UI-SESSION-VI-20260918

## Phạm vi và mốc so sánh

- Repo/worktree: `/home/dell/workspace/mesflow/.worktrees/codex-ui-session-vi`
- Branch: `agent/codex/ui-session-vi-20260918`
- Base thực tế và `HEAD` trước commit: `7e0abeb10e7c93a9bc78f5e7913b60ed128a0005`
- Base đã chứa hotfix mobile `DASHBOARD-MOBILE-TAB-FONT-20260918`; task này không sửa CSS của hotfix đó.
- Diff source/assertion trước khi thêm hai test mới và báo cáo: 52 file tracked, `374 insertions(+), 374 deletions(-)`. Sau lượt biên tập ngữ nghĩa, diff cuối gồm 57 file, `735 insertions(+), 392 deletions(-)` (phần tăng thêm chủ yếu là report và hai test mới). Thay đổi ứng dụng chỉ là copy hiển thị; không có migration hay bump version.
- Không merge, deploy, restart server hoặc ghi dữ liệu live. Integration/E2E dùng compose project cô lập `codex-ui-session-vi` và fixture DB riêng.

## Inventory bề mặt hiển thị

| Bề mặt | Vị trí chính | Trạng thái | Bằng chứng |
|---|---|---|---|
| Navigation, tiêu đề, hint | `web/static/app.js` | PASS | Menu “Quản lý phiên làm việc”; hint audit/trace/system đã đổi; Chromium nav test pass. |
| Dashboard tab Operation | `web/static/app.js`, `pages/daily-dashboard-kiosk.js` | PASS | Nhãn đếm/card dùng “phiên làm việc”; ảnh 390/428/768/1366; Chromium và WebKit pass. |
| Dashboard tab Nhân viên/timeline | cùng các file trên | PASS | Tab, metadata, timeline, empty/error copy đã đổi; kiểm tra font/overflow và click tab pass ở 4 viewport, 1 và 2 phiên fixture. |
| Quản lý, bộ lọc, drawer chỉnh sửa/chi tiết | `web/static/app.js`, `pages/session-detail.js` | PASS | Label, aria-label, modal, empty/error copy đã đổi; smoke/filter/detail test pass. |
| Ngoại lệ | `pages/session-exceptions.js`, `pages/exception-center.js`, `web/exceptions.py` | PASS | Card, modal, toast, validation, aria/title và fallback flow pass. |
| Audit/trace/rework/material/PO/overview | `domain/audit_presentation.py`, các page JS và repository liên quan | PASS | Copy trình bày và event title đã đổi; category/event/API key giữ nguyên; test audit/trace/rework liên quan pass. |
| Năng suất và wallboard | `pages/employee-productivity.js`, `wallboard-employee-productivity.js` | PASS | Heading/KPI/filter/empty copy và source contract test pass. |
| Kiosk web/mobile | `web/kiosk.py`, `static/kiosk.js`, repository/service | PASS | Copy action/error đã đổi; kiosk scan-board integration pass. Kiosk native/ESP không có source UI tiếng Việt thuộc task này. |
| Tooltip/aria/title/toast/validation/loading/error/empty | JS page, repository/service/web literals | PASS trong source quản lý | Scanner và test copy mới kiểm tra các cụm rủi ro; các thông báo nghiệp vụ được dịch, selector/ID/data-* không đổi. |
| Hướng dẫn/tutorial | `guides/user-guide.vi.json`, `tutorial_data.py` | PASS | Nội dung hiển thị và dữ liệu tutorial tổng hợp đổi copy; keyword tìm kiếm kỹ thuật vẫn giữ alias `session`; 23 test guide/tutorial pass. Không sửa note/dữ liệu người dùng. |
| In/export | `web/excel_io.py`, CSV/Excel paths | PASS có chủ đích | Thông báo người dùng được dịch. Header/field máy như `session_id`, query và contract export giữ nguyên. Không tìm thấy template in nào có label Session cần đổi. |
| Phiên đăng nhập/cookie | `core/session_policy.py`, `web/auth.py`, Flask `session` | LOẠI TRỪ KỸ THUẬT | Không phải phiên sản xuất và không đổi. |
| Ảnh before/after | `test-results/ui-session-vi-{operation,people}-{390,428,768,1366}.png` | BLOCKED một phần | Có ảnh “after” cho cả hai tab/4 viewport. Không tạo cặp “before” trong lượt rename này vì base runner chưa được chụp trước khi sửa; không gọi đây là bằng chứng before/after đầy đủ. |

## Review diff và hợp đồng kỹ thuật

Đã review theo từng file/hunk so với base. Một lượt thay tự động ban đầu đã bị audit bắt được vì từng chạm identifier/class trong template JS và các khóa Python `session`/category. Các hunk đó đã được hoàn tác, sau đó thay lại từng literal hiển thị. Trạng thái cuối:

- Không đổi tên biến/hàm, ID/class/data-*, selector, import, route/URL/query, endpoint, payload/response key, enum/status, error-code, DB/migration, storage/cookie/cache key, event/audit ID hoặc CSV/API machine header.
- `PY_AST_NON_STRING_STRUCTURE: PASS`: cấu trúc AST Python ngoài string không đổi.
- `PY_MACHINE_STRING_CONSTANTS: PASS`: tập literal hợp đồng máy được bảo toàn.
- So sánh URL/API literal, `id`/`class`/`data-*` và các tham chiếu ARIA (`aria-labelledby`/`aria-describedby`/`aria-controls`): PASS trên 24 file JS. `aria-label` dạng copy được biên tập có chủ đích; event/error code viết hoa vẫn nguyên vẹn.
- `git diff --check`: PASS.
- Không có CSS/layout hunk trong task rename; hotfix font/card mobile ở base được giữ nguyên.

### Coupling được phát hiện và giữ nguyên

`app/mesflow/db/repositories/execution.py:181,552-553` còn các câu nội bộ chứa `session`; `app/mesflow/web/kiosk.py:47` phân loại lỗi bằng substring tương ứng. Đây là coupling control-flow giữa producer/consumer. Task không đổi các chuỗi này để tránh sửa logic; action/copy mà UI kiosk hiển thị đã được Việt hóa ở lớp presentation. Tương tự, `app/mesflow/web/kiosk_v2.py:343` giữ literal tiếng Anh `already has an open session` vì là classifier nội bộ.

## Các match `session` còn lại

Không coi số match thô là lỗi. Các match còn lại được phân loại:

1. Identifier và dữ liệu: `session_id`, `sessions`, `openSession`, property `.session`, sort key `session`, schema/table `work_sessions`.
2. Hợp đồng: route `/session/...`, query key `session`, API response key `session`, audit category/event `SESSION_*`, CSV/export field `session_id`.
3. Phiên đăng nhập: Flask `session`, cookie/session policy và auth comments.
4. Comment/docstring kỹ thuật và test name: không hiển thị cho người dùng.
5. Alias tìm kiếm guide: keyword `session` được giữ để người dùng vẫn tìm được tài liệu bằng thuật ngữ cũ.
6. Ba thông báo repository nội bộ nói trên: giữ vì classifier đọc exact substring; presentation kiosk đã dịch.

Không sửa dữ liệu người dùng, note, lịch sử audit có sẵn hoặc dữ liệu live.

## Biên tập ngữ nghĩa theo ngữ cảnh

Không dùng phép thay từ máy móc. “Phiên làm việc” chỉ tên bản ghi sản xuất; “trường hợp bất thường” chỉ một cảnh báo/bản ghi cần xử lý; “phiên đăng nhập” chỉ phiên xác thực. Bảng dưới ghi các cụm đại diện đã đối chiếu từ base đến câu hoàn chỉnh cuối cùng:

| Original tại base | Câu tiếng Việt hoàn chỉnh | Vị trí/ngữ cảnh |
|---|---|---|
| `Quản lý Session` | `Quản lý phiên làm việc` | `web/static/app.js` — menu, danh từ chỉ màn hình quản lý. |
| `B · Nhân viên / Session` | `B · Nhân viên / phiên làm việc` | `web/static/app.js` — tab Dashboard. |
| `${count} session · ${open} đang chạy` | `${count} phiên làm việc · ${open} đang chạy` | Dashboard Operation — số đếm động, giữ nguyên interpolation. |
| `${count} session · ${open} chưa đóng` | `${count} phiên làm việc · ${open} chưa đóng` | Dashboard nhân viên — metadata timeline, giữ nghĩa số phiên chưa kết thúc. |
| `Session theo bộ lọc` | `Phiên làm việc theo bộ lọc` | Quản lý phiên làm việc — tiêu đề danh sách. |
| `Session Detail` / `Session ID` | `Chi tiết phiên làm việc` / `Mã phiên làm việc` | Drawer/modal — tên màn hình và nhãn field. |
| `Trung tâm ngoại lệ` / `Session exception` | `Các phiên làm việc bất thường` | Menu/page title — danh từ chỉ đúng đối tượng sản xuất cần rà soát. |
| `Danh sách ngoại lệ` | `Danh sách phiên làm việc bất thường` | Heading danh sách trên trang xử lý. |
| `Không có ngoại lệ trong nhóm này` | `Không có phiên làm việc bất thường trong nhóm này` | Empty state. |
| `${total} ngoại lệ` | `${total} trường hợp bất thường` | Số đếm động — đếm bản ghi cảnh báo, không khẳng định là số phiên duy nhất. |
| `Xử lý ngoại lệ phiên làm việc` | `Xử lý phiên làm việc bất thường` | Permission, drawer aria-label và audit title. |
| `Ngoại lệ này không gắn với một Session...` | `Trường hợp bất thường này không gắn với một phiên làm việc cụ thể...` | Validation/toast — phân biệt bản ghi cảnh báo với phiên sản xuất. |
| `Session bắt đầu` / `Session kết thúc` | `Bắt đầu phiên làm việc` / `Kết thúc phiên làm việc` | Event title/timeline — động từ đứng trước đối tượng. |
| `Session tự động đóng ca` | `Phiên làm việc đã được hệ thống đóng khi hết ca` | Audit/trace event — nêu rõ tác nhân và thời điểm. |
| `Chưa session nào chốt số` | `Chưa có phiên làm việc nào chốt số` | Dashboard KPI/card — câu phủ định tự nhiên, không đổi trạng thái xác nhận. |
| `ngoại lệ Session` trong mô tả Lỗi hệ thống | `phiên làm việc bất thường` | System Console — vẫn tách NG sản phẩm, bất thường nghiệp vụ và lỗi hệ thống. |
| `login session` | `phiên đăng nhập` | Hướng dẫn xác thực — không dùng “phiên làm việc”; Flask session/cookie/key vẫn giữ nguyên kỹ thuật. |

Các nút dùng động từ + đối tượng (`Mở phiên làm việc`, `Sửa phiên làm việc`, `Nhận và mở phiên làm việc`); các trạng thái `chưa nhập sản lượng`, `chưa xác nhận`, `đã xử lý`, `đã bỏ qua` tiếp tục là các khái niệm riêng, không gộp thành một nhãn chung.

## Rủi ro và bằng chứng

| Rủi ro | Kết luận | Bằng chứng/biện pháp |
|---|---|---|
| Replace toàn cục làm đổi identifier/contract | Đã phát hiện và sửa | Hoàn tác toàn bộ draft không an toàn; AST/machine-string/URL/attribute checks pass. |
| Chuỗi vừa đổi bị logic đọc bằng text/innerText/getByText | Không thấy coupling trong diff cuối | Dò `innerText`, `textContent`, regex, selectors và automation; chỉ cập nhật assertion nhãn. Các assertion hành vi và selector không bị xóa/skip. |
| Backend error text là contract ngầm | Có ở 3 substring classifier | Giữ nguyên producer/consumer như mục coupling; không đổi logic. |
| Nhãn dài gây tràn/tăng font | Không tái hiện | Chromium + WebKit tại 390/428/768/1366; kiểm tra computed font, bounding boxes, root overflow, click hai tab. |
| Network endpoint/payload/status đổi | Không thấy trong structural diff và integration | Endpoint/key/status code không đổi; 90 integration tests pass. Capture packet before/after cùng fixture: BLOCKED vì không có baseline capture trước thay đổi; không tuyên bố đã so packet byte-for-byte. |
| E2E cũ dùng selector DOM đã lỗi thời | BLOCKED ở nhóm test cũ | Base `7e0abeb` không có `.employee-session-chips`/`.employee-day-summary`, nhưng các test cũ vẫn tìm chúng. Không sửa assertion hành vi để che lỗi; thêm coverage trên DOM hiện hành. |
| Reporter Playwright ghi artifact | Cảnh báo, không chặn test | Reporter cảnh báo output HTML trùng `test-results`; test vẫn chạy và ảnh PNG tồn tại. Không sửa hạ tầng trong hotfix copy. |

## Lệnh và kết quả thực chạy

```text
python3 -m compileall -q app/mesflow
PASS

node --check <toàn bộ JS app/page thay đổi và ui-session-vi-copy.spec.js>
PASS

python3 -m json.tool app/mesflow/web/static/guides/user-guide.vi.json
PASS

pytest -q <19 file source/unit liên quan>
109 passed in 0.53s

pytest -q tests/test_v6584439_tutorial_dataset.py tests/test_v6584447_tutorial_cleanup_fk.py tests/test_text_guide_content.py tests/test_ui_session_vi_copy.py
23 passed in 0.14s

docker compose -p codex-ui-session-vi -f compose.test.yml run --rm test pytest -q <9 integration files về lifecycle/overlap/exception/audit/productivity/dashboard/kiosk>
90 passed in 12.69s

docker compose -p codex-ui-session-vi -f compose.test.yml run --rm test pytest -q <trace/system-console/copy/audit unit>
35 passed in 3.15s

Playwright Chromium, nhóm rộng ban đầu
30 passed, 13 failed, 1 skipped (5.2m)
13 fail gồm 11 selector/count Dashboard cũ không tồn tại ngay tại base và 2 expected copy ngoại lệ đã cập nhật rồi pass.

Playwright Chromium, nhóm thứ hai
27 passed, 5 failed, 1 skipped
4 fail fixture ca rỗng của test mới và 1 expected copy; fixture/assertion copy đã sửa.

Playwright Chromium, rerun mục đã sửa
5 passed (10.6s)

Playwright WebKit, ui-session-vi-copy.spec.js, 390/428/768/1366
4 passed (22.5s)

Host pytest cho test cần Flask/psycopg
BLOCKED lúc collect do host thiếu dependency; cùng test chạy trong container: 35 passed.
```

### Gate bổ sung sau biên tập ngữ nghĩa

```text
pytest -q <11 file copy/guide/tutorial/source liên quan>
78 passed in 0.61s

docker compose -p codex-ui-session-vi -f compose.test.yml run --rm tests pytest -q <9 file lifecycle/exception/audit/copy>
62 passed in 6.68s

Playwright Chromium: exception center + drawer + copy/layout
13 passed; 4 test copy/layout ban đầu fail vì locator test khớp cả body và menu button (strict-mode), không phải lỗi UI.
Sau khi định vị đúng menu button: 4 passed (10.8s) tại 390/428/768/1366.

Playwright WebKit: copy/layout + tiêu đề dài
4 passed (23.1s) tại 390/428/768/1366.

Gate cuối sau chỉnh câu audit động
43 source/unit passed; 9 integration passed; `git diff --check` PASS.
```

Một lượt Chromium trước đó dùng image Playwright chưa rebuild nên còn assertion tiêu đề cũ; sau khi rebuild image cô lập, 13 test exception/drawer đã pass. Hai lỗi test-runner này được ghi riêng, không tính là regression ứng dụng và không bị che bằng skip/xfail.

Coverage integration thực chạy bao gồm start/finish, nhập sản lượng, overlap/đa phiên, auto-close, ngoại lệ, chỉnh sửa/report, productivity và kiosk scan board trên DB fixture cô lập. Không có test bị xóa hoặc skip thêm.

## Checkpoint kết luận

- Files cuối: 57 file so với base, gồm source, assertion copy, 2 test mới và báo cáo này; không có CSS/migration/version hunk.
- Logic affected: **NO trong diff cuối**; chỉ literal trình bày và assertion copy. Coupling nội bộ đã nhận diện được giữ nguyên.
- Technical contracts: không đổi theo AST/machine-string/URL/attribute audit; packet capture before/after là BLOCKED như đã nêu.
- Tests actual: unit/source, integration, Chromium và WebKit có kết quả thực chạy ở trên; nhóm E2E selector cũ vẫn BLOCKED và được ghi rõ.
- Next: commit riêng trên branch hiện tại. Không merge/deploy/restart theo phạm vi lượt này.
