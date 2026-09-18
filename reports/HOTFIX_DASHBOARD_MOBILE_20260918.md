# HOTFIX MESFlow — MF-DASH-MOBILE-20260918

## Task router

| Request key | Trạng thái | Owner / executor | Branch / baseline | Phạm vi |
|---|---|---|---|---|
| `MF-DASH-MOBILE-20260918` | LOCAL PASS — merge/deploy `.328` blocked by required baseline gate | Codex / `mes-codex-work` | `agent/codex/dashboard-mobile-tab-font-20260918` / live TEST `71.0.0.327` | Chỉ responsive layout/typography của hai tab Dashboard ngày, test và release TEST; không đổi Session management, API, data, nghiệp vụ, auth hoặc migration |

## Checkpoint

- Reuse worktree `/home/dell/workspace/mesflow/.worktrees/codex-dashboard-mobile-tab-font`; không tạo task/branch trùng.
- Commit checkpoint đã có khi tiếp nhận lại: `7e0abeb10e7c93a9bc78f5e7913b60ed128a0005`.
- Canonical checkout đang có WIP của agent khác; không reset, stash hoặc ghi đè.
- Live khi tiếp tục task: `https://mesflow.net`, role `PRODUCTION_TEST`, version `71.0.0.327`, migration `0054_multi_open_session_per_employee`. API cũ trả commit `unknown`, nhưng remote image và artifact local cùng digest `sha256:aadba58d969634ae312de62067cd69dc148978c689247ddcf4e73122b864e694`; CSS/JS live giống source `7e0abeb` từng byte.

## Root cause và thay đổi `.328`

- Timeline mobile đặt `min-width:720px` trực tiếp trong `.employee-day-row` và cho cả row `overflow-x:auto`; content-width của card vì vậy ảnh hưởng autosizing/layout thay vì chỉ cuộn thang giờ.
- Các rule `.op-identity.compact` và `b.row-title` thắng typography chung theo từng tab. Computed `.327` tại 390px: title Operation/People đều 13px, body People 13px, meta 12px; hierarchy không đúng yêu cầu.
- Rule legacy toàn trang `header{margin-bottom:22px}` áp nhầm vào `.op-card-head`; cộng grid gap 8px tạo đúng 30px khoảng trắng trước tiến độ.
- `.328` cô lập scroll vào `.employee-day-track-scroll`, đặt typography dùng chung mobile title/body/meta = 16/14/12px, wrap metadata và `min-width:0`, đồng bộ padding/gap, giữ zoom và đặt `text-size-adjust:100%`. `.op-card-head` reset margin scoped Dashboard nên gap thực đo còn 8px. Không che lỗi bằng `overflow:hidden` ở card.

## Browser evidence

- Chromium: 7/7 PASS; WebKit: 7/7 PASS, `--retries=0`, fixture không sửa data thật.
- Viewport: 1920x1080, 1366x768, 414x896, 390x844, 375x812.
- Mobile cả hai tab: title 16px, body 14px, meta 12px; root/card overflow false; timeline cuộn trong vùng riêng; progress width bằng body width; gap header→progress 8px.
- Bao phủ tên/mã Operation, Part, PO và nhân viên dài; 1 và >=2 session; OPEN/CLOSED; mở chi tiết session; giữ ngày khi đổi tab; refresh/sort; ca tối. WebKit là browser engine, không phải Safari thật trên iPhone hardware.
- Screenshot bền vững ngoài source tree:
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/before-71.0.0.327-chromium-dashboard-operation-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/before-71.0.0.327-chromium-dashboard-people-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/after-71.0.0.328-chromium-dashboard-operation-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/after-71.0.0.328-chromium-dashboard-people-390x844.png`

## Tests và gate

- `python3 -m pytest -q tests/test_dashboard_mobile_tab_layout_contract.py`: 2/2 PASS.
- `node --check app/mesflow/web/static/app.js`, version sync, diff check: PASS.
- Project preflight: PASS (port 18280 warning vì local sandbox `.327` đang chạy, không phải failure).
- Full required test gate chạy trong compose project riêng: unit 321 pass/10 skip; static 744 pass/9 skip; critical PostgreSQL/API 44 pass/1 skip; integration 577 pass/2 skip/**1 fail**.
- Failure có sẵn ngoài diff hotfix: `tests/integration/test_operation_time_progress.py::test_variance_zero_wording_not_negative_countdown` vẫn tìm chuỗi inline cũ, trong khi baseline `.327` đã refactor sang `expectedTimingHtml(expectedTiming(...))`. Không sửa business-time logic hoặc làm yếu test trong hotfix mobile.

## Scope / automation check

- Không thêm hook, cron, watcher, workflow, auto PR trigger, service, DB/schema, API, auth hoặc OCR vào build/test/EXE.
- Chỉ app static Dashboard, focused tests, version declarations và báo cáo task thay đổi. Không đụng Session management hotfix `.326`.

## Merge / deploy checkpoint

- Version source đã bump cache/release key sang `71.0.0.328`, nhưng chưa build artifact vì required gate chưa xanh.
- Commits: checkpoint `.327` `7e0abeb10e7c93a9bc78f5e7913b60ed128a0005`; completion `.328` `b56b3b2df324efd112c6d10c8584cd8dd5b7c432`.
- Branch đã push tới `origin/agent/codex/dashboard-mobile-tab-font-20260918`. Không mở/merge PR vào `origin/main`: remote main `10ac299` đang thấp hơn lineage live 215 commit, nên PR sẽ kéo thay đổi ngoài scope; local required gate cũng đang đỏ như trên.
- Merge/deploy `.328`: BLOCKED_GATE; không force/bypass và không deploy source chưa merge.
- TEST hiện tiếp tục chạy exact `.327`/`7e0abeb` artifact, healthy; không redeploy/restart vì live đã có đúng artifact checkpoint và `.328` chưa đủ gate.

## Rollback placeholder

Không có migration. Previous exact artifact trước `.327`: image digest `127.0.0.1:5000/mesflow-app@sha256:5c609d495d3ab3d3934ceaecfaa474a02f83608174156a1a8176a931d759cd3f` (`71.0.0.326`). Nếu `.328` sau này được gate và deploy nhưng smoke fail, dùng artifact `.327` digest `sha256:aadba58d969634ae312de62067cd69dc148978c689247ddcf4e73122b864e694` và chỉ recreate app service; không restart PostgreSQL/nginx/service khác.
