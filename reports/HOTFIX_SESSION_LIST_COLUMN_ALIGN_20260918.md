# HOTFIX MESFlow — SESSION-LIST-COLUMN-ALIGN-20260918

## Task router

| Task | Trạng thái | Owner | Branch/base | Phạm vi |
|---|---|---|---|---|
| SESSION-LIST-COLUMN-ALIGN-20260918 | DEPLOY PASS — TEST | Codex (`mes-codex-work`) | `agent/codex/session-list-column-align-20260918`; hotfix `3cb37cf`; release `565c790` | Chỉ layout danh sách Quản lý Session + regression Playwright; không đổi API/data/nghiệp vụ/migration |

## Root cause và sửa chữa

- Runtime đang chạy khi bắt đầu: `https://mesflow.net`, `PRODUCTION_TEST`, version `71.0.0.325`, commit `f5263a9dfdae`, migration `0054_multi_open_session_per_employee`.
- Mỗi `.session-accordion-trigger` là một CSS Grid riêng. Track trạng thái cuối dùng `auto`, nên dòng có badge `Chưa xác nhận số liệu` dành nhiều chỗ hơn và làm bốn track `fr` phía trước co lại khác các dòng chỉ có một badge.
- Track desktop được khai báo một lần bằng `--session-row-columns`; cả năm cột dùng track có kích thước xác định, không còn content-sized `auto` theo từng dòng.
- Cột trạng thái wrap từng badge trong chính cột. Tablet reflow thành hai cột + một hàng trạng thái; mobile thành một cột. Text dài ở các cột nội dung vẫn dùng `min-width:0` và ellipsis hiện có.

## Evidence checkpoint

- Docker sandbox riêng `mesflow-session-align` tại `http://127.0.0.1:19087`: health PASS, DB/migration PASS.
- Playwright container riêng `mesflow-session-align-e2e`: **7 passed**, `--retries=0`.
- Targeted Python: **10 passed** (`test_v71_ui_foundation.py`, `test_session_management_dependent_filters.py`); preflight/version verify PASS.
- Required aggregate `COMPOSE_PROJECT_NAME=mesflow-session-align-full ./scripts/projectflow/test.sh` không chạy được vì fixture gitignored `runtime/tutorials` trả `mkdir: Permission denied` ngay sau version verify. Không sửa quyền/hạ tầng ngoài scope; vì vậy không merge `main` và không claim full CI PASS.
- Fixture bao phủ OPEN/CLOSED, 1 badge, 2 badge, excluded badge, tên/PO/Part/Operation dài, chưa nhập sản lượng và rework.
- Bounding boxes tại 1366/1920/2048: start-x của từng cột giữa 24 dòng sai số `<=1px`; kiểm tra không overlap và không overflow PASS.
- Reflow + overflow tại 768/390 PASS.
- Screenshot (gitignored test artifact):
  - `test-results/session-management-1366x768.png`
  - `test-results/session-management-1920x1080.png`
  - `test-results/session-management-2048x1152.png`
  - `test-results/session-management-768x1024.png`
  - `test-results/session-management-390x844.png`

## Release / deploy checkpoint

- Git fetch qua SSH mặc định bị chặn bởi `/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf` sai owner/permission; baseline được neo trực tiếp theo commit/version public TEST và local ref đã có. Không sửa cấu hình hệ thống.
- Fetch tiếp theo dùng `/home/dell/.ssh/config` hợp lệ, giữ nguyên host-key verification; không sửa/hạ SSH security và không force-push.
- Ngay trước promote, `https://mesflow.net/api/system/ready` vẫn là `71.0.0.325`, commit `f5263a9dfdae`, role `PRODUCTION_TEST`, migration `0054_multi_open_session_per_employee`; không có release agent khác để ghi đè.
- Release `71.0.0.326`; source/cache-key commit `565c790868b6`; image digest `sha256:5c609d495d3ab3d3934ceaecfaa474a02f83608174156a1a8176a931d759cd3f`; bundle transfer checksum `88a4638f72ccd937464be2e94a6034b9083d90b1cab7164bf213bf9968810e9c`.
- Deploy TEST qua `scripts/deploy-remote-test.sh 71.0.0.326`: PASS. Chỉ app được recreate; DB/nginx không restart; migration head không đổi.
- Public smoke: ready/version PASS; `/login` 200; HTML trỏ `/static/ui.css?v=71.0.0.326`; CSS 200 và chứa `--session-row-columns`; `/app` 302 về login; `/api/employees` 401 khi anonymous.
- Public URL: `https://mesflow.net` — version `71.0.0.326`, commit `565c790868b6`, role `PRODUCTION_TEST`.
- Branch đã push không force: `origin/agent/codex/session-list-column-align-20260918`; chưa merge `main` do aggregate gate bị chặn như trên.

## Rollback

Hotfix không có migration. Rollback target là release `71.0.0.325`, digest `sha256:ceceeaa40bbe826504dbd1b25ce5f5454b1d62c9c3bae977eee5f632a22f263a`. Chạy lại `scripts/deploy-remote-test.sh 71.0.0.325`, hoặc đặt `MESFLOW_IMAGE` của remote TEST về digest này rồi chỉ recreate service app bằng `docker compose --env-file .env up -d --no-deps mesflow`. Không restart PostgreSQL/nginx/service khác.
