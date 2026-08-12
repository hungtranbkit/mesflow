# MESFlow v65.5.0 — Phase 5 Production Ready

PostgreSQL-native production package. Không có SQLite, adapter hay mirror.

## Phase 5 bổ sung

- Nginx reverse proxy nội bộ và security headers.
- Readiness, monitoring và database statistics APIs.
- Alembic migration `0005_production_ops`.
- Preflight trước deploy.
- Backup `pg_dump` có manifest, SHA-256, uploads archive và retention.
- Restore có backup trước khi thay database và regression test sau restore.
- Regression test toàn Phase 1–4.
- Deployment history và deployment ID.
- Backup cron installer.
- Graceful shutdown và health checks cho cả ba container.

## Cài/nâng cấp

Giữ `.env` và `runtime/`, giải nén source vào `/opt/mesflow-v65`, sau đó:

```bash
cd /opt/mesflow-v65
bash scripts/start.sh
```

Truy cập thử nghiệm:

```text
http://SERVER_IP:18080
```

## Kiểm tra

```bash
bash scripts/regression-test.sh
curl -s http://127.0.0.1:18080/api/system/monitoring
```

## Backup và restore

```bash
bash scripts/backup.sh
bash scripts/restore.sh runtime/backups/mesflow_v65_YYYYMMDD_HHMMSS.dump
```

## Tự backup hằng ngày

```bash
bash scripts/install-backup-cron.sh
```

## Cutover từ v64

Phase 5 chưa tự động thay domain production. Chạy v65 song song ở port 18080, hoàn tất regression và test kiosk thực tế trước. Sau đó đổi upstream nginx/domain từ v64 sang v65.

## v65.8.5 Control Tower

Dashboard Tổng quan hiện là trung tâm điều hành realtime: KPI theo ngày, sức khỏe PO, bottleneck/WIP, session, cảnh báo và tình trạng kiosk. Dữ liệu tự làm mới mỗi 10 giây và có thể tắt auto-refresh khi cần phân tích.
## v65.8.6 Start Production Order

- Thêm nút **Start PO** tại danh sách PO, chi tiết PO và Control Tower.
- PO chỉ vào vùng điều hành của Dashboard sau khi chuyển sang `IN_PROGRESS`.
- Kiosk Demo chỉ tải Operation chưa hoàn thành thuộc PO đã Start.
- API Start Session từ chối Operation nếu PO chưa Start hoặc đang tạm dừng.
- Start PO yêu cầu PO có ít nhất một Operation.


## v65.8.7 PO bắt buộc tạo từ Template

Luồng chuẩn:

1. Mở **Kế hoạch → Production Order**.
2. Chọn **Tạo PO từ Template**.
3. Chọn Template nguồn; hệ thống hiển thị số Part và Operation.
4. Nhập mã PO, số lượng và lịch dự kiến.
5. Hệ thống sao chép cấu trúc Template thành dữ liệu riêng của PO.
6. Kiểm tra/override PO rồi bấm **Start PO**.
7. PO xuất hiện trên Control Tower; Kiosk Demo tải các Operation của PO đang chạy.

Migration mới: `0015_po_template_source`.

## PostgreSQL/Docker automated tests (v65.8.33)

Run the complete isolated suite with:

```bash
./scripts/test/docker-test.sh
```

The runner builds a disposable PostgreSQL 17 database in tmpfs, migrates to the current Alembic head, starts MESFlow, executes unit and integration tests, writes JUnit XML files to `test-results/`, and removes containers/volumes on exit.

Keep containers after a failed run for investigation:

```bash
./scripts/test/docker-test-keep.sh
./scripts/test/test-status.sh
```


## Kiểm tra restore backup tự động

Chạy riêng bài kiểm tra backup/restore PostgreSQL trong database tạm, không thay thế database nguồn:

```bash
./scripts/test/restore-backup-test.sh
```

Bài test tạo `pg_dump` dạng custom, sinh manifest và SHA-256, restore vào database tên ngẫu nhiên, đối chiếu dữ liệu marker, Alembic head, bảng/foreign key quan trọng rồi tự xóa database restore. Bài này cũng nằm trong `./scripts/test/docker-test.sh` và GitHub Actions hàng tuần.

## Frontend modules và Playwright (v65.8.40)

Frontend đang được tách dần khỏi `app.js`:

- `app/mesflow/web/static/core/api.js`
- `app/mesflow/web/static/pages/session-exceptions.js`
- `app/mesflow/web/static/pages/qr-print.js`

Chạy toàn bộ Python/PostgreSQL và browser E2E:

```bash
./scripts/test/docker-test.sh
```

Playwright tạo báo cáo tại `test-results/playwright.xml` và `test-results/playwright-report/`.
