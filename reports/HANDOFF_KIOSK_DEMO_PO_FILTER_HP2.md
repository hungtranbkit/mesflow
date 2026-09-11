# Handoff — hp2 · Kiosk demo: lọc theo Production Order (REQ-KIOSK-012)

**Nhánh**: `hp2/kiosk-demo-po-filter` · **nền**: `origin/integration/daily-dashboard-test`
**Lane hp2 KHÔNG merge, KHÔNG deploy.** Bản này chờ chủ nhánh integration gộp.

## Việc xưởng báo

Màn "Mô phỏng quét QR" của Kiosk web có quá nhiều Operation nên không tìm nổi.
Nguyên nhân thật nằm dưới lớp giao diện: bảng này đổ công đoạn của **mọi** PO
đang chạy vào một `<select>` phẳng rồi cắt ở `LIMIT 500`. Đầu danh sách thì
không tìm được, còn phần sau chỗ cắt thì **không có đường nào chạm tới**.

## Đã làm

| Chỗ | Thay đổi |
|---|---|
| `app/mesflow/web/kiosk.py` | `GET /api/kiosk-web/demo-data` nhận `po_id`, `q`, `include`; trả thêm `production_orders[]`, `production_orders_total`, `operations_total`, và `po_id` trên từng dòng Operation. |
| `app/mesflow/web/templates/kiosk.html` | Thêm ô chọn PO + ô tìm công đoạn (đặt TRƯỚC danh sách), số kết quả, và khối empty state. |
| `app/mesflow/web/static/kiosk.js` | Gửi phạm vi xuống server; nhớ PO đang chọn; bỏ phản hồi của request đã bị thay chỗ. |
| `app/mesflow/web/static/kiosk.css` | `.demo-scope`, `.demo-list-head`, `.demo-count`, `.demo-empty`; 390px không tràn ngang. |

**Phạm vi cắt ở SQL, không cắt ở trình duyệt.** Đây là phần quan trọng nhất:
lọc lại một mảng đã bị `LIMIT` cắt sẵn ngay trong trình duyệt thì phần đuôi vẫn
vĩnh viễn không tới được — giao diện đẹp hơn mà lỗi còn nguyên. Phạm vi khoá
bằng `production_orders.id` (khoá chính), không bằng `po.code` — code là chuỗi
người nhập, có thể trùng hoặc bị sửa.

## Điều cố ý làm ngược với phản xạ thông thường

- **PO đang chạy mà chưa có công đoạn nào vẫn nằm trong danh sách chọn**
  (`LEFT JOIN`, `operation_count = 0`). Giấu nó đi thì người dùng chỉ thấy PO
  của mình biến mất mà không hiểu vì sao.
- **`po_id` sai định dạng → `400`, không im lặng bỏ qua.** Bỏ qua nó nghĩa là
  bày công đoạn của mọi lệnh lên một màn hình đang tưởng mình chỉ hiện một lệnh.
  Phía client tự lọc `po_id` rác trước khi gửi nên panel không vì thế mà hỏng.
- **`po_id` trỏ vào PO không còn chạy → giữ nguyên phạm vi và nói thẳng**, không
  rơi về "Tất cả PO".
- **Sau khi người dùng tự chọn PO, không gì được đổi phạm vi nữa** — URL cũng
  không, nhịp làm mới nền 10s cũng không.
- **Số kết quả nói thật khi bị cắt**: `operations_total` đếm *trước* `LIMIT`, nên
  giao diện hiện `500/2025` thay vì lặng lẽ cắt đuôi.

## Không đụng vào

Luồng quét/bắt đầu/kết thúc session (`/api/kiosk-web/scan|start|finish`) và
thiết bị ESP v2 (`kiosk_v2.py`) **không có thay đổi nào**. Bảng mô phỏng là code
path riêng: máy thật gõ thẳng vào ô nhận mã, không gọi `demo-data`.
`@login_required` giữ nguyên — dữ liệu này mang QR thẻ nhân viên, tức credential;
có bài test khoá việc thêm tham số lọc không mở ra cửa nào bỏ qua đăng nhập.

## Tài liệu

- `docs/MESFLOW_MASTER_REQUIREMENTS.md` §15.8 — REQ-KIOSK-012 (EN) + dòng truy vết.
- `docs/MESFLOW_MASTER_REQUIREMENTS_VI.md` §15.8 — REQ-KIOSK-012 (VI) + dòng truy vết.
- `docs/qc/API_MAP.yaml` — dòng `demo-data`: thêm query params, và sửa
  `roles: none` → `any_authenticated` (đã sai từ bản vá 2026-09-09).

## Kiểm thử

- `tests/integration/test_kiosk_demo_po_filter.py` — 18 bài.
- `tests/e2e/kiosk-demo-po-filter.spec.js` — 18 bài.

Bài quan trọng nhất là `test_operation_past_the_global_cap_is_reachable_by_po_scope`
(45 PO × 45 OP = 2025 dòng, vượt hẳn trần 500) và bài e2e tương ứng *"phạm vi đi
xuống server, không lọc lại trong trình duyệt"*: cả hai ĐỎ nếu ai đó chuyển việc
lọc về phía client.

Gate chạy trên stack lane hp2 (`docker compose -p mesflow-hp2 -f compose.test.yml`),
**sau khi rebase lên `0ea03df`**:

- pytest toàn bộ: **1261 passed, 16 skipped, 1 xfailed** (xfail có sẵn, thuộc lane Rework).
- Playwright toàn bộ `tests/e2e`, `--retries=0`: **400 passed, 4 skipped, 0 failed**.

Lưu ý cho người chạy lại: phải chạy `scripts/test/generate-esp-tutorial-fixture.sh`
(hoặc `scripts/test/docker-test.sh`, nó tự gọi) TRƯỚC khi `compose.test.yml` lên,
nếu không bài `mesflow.spec.js › ESP Kiosk tutorial loads seven runtime videos`
sẽ đỏ vì thiếu fixture — lỗi môi trường, không phải hồi quy. Máy này không có
ffmpeg nên fixture được dựng qua `Dockerfile.esp-tutorial-fixture`; sau đó bài
đó xanh.

## Còn nợ, cố ý không làm trong lane này

`docs/MESFLOW_MASTER_REQUIREMENTS.md` (EN) **thiếu hẳn REQ-KIOSK-010 và
REQ-KIOSK-011** — hai mục này chỉ có ở bản VI. Lỗ đó đã có sẵn trên integration
trước lane hp2 và thuộc về hai lane sinh ra chúng, nên không lấp ở đây để tránh
viết hộ nội dung của người khác. `API_MAP.yaml` cũng còn ghi `roles: none` cho
`/api/kiosk-web/scan|start|finish` trong khi thực tế là `@production_client_required`
— cùng lý do, không sửa lấn sang.
