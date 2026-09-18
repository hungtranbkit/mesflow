# HOTFIX MESFlow — MF-DASH-MOBILE-20260918

## Task router

| Request key | Trạng thái | Owner / executor | Branch / baseline | Phạm vi |
|---|---|---|---|---|
| `MF-DASH-MOBILE-20260918` | TARGETED PASS — merge/build/deploy `.328` blocked by required full gate | Codex / `mes-codex-work` | `agent/codex/dashboard-mobile-tab-font-20260918` / live TEST `71.0.0.327` | Chỉ responsive layout/typography của hai tab Dashboard ngày, test và release TEST; không đổi Session management, API, data, nghiệp vụ, auth hoặc migration |

## Checkpoint

- Reuse worktree `/home/dell/workspace/mesflow/.worktrees/codex-dashboard-mobile-tab-font`; không tạo task/branch trùng.
- Commit checkpoint đã có khi tiếp nhận lại: `7e0abeb10e7c93a9bc78f5e7913b60ed128a0005`.
- Canonical checkout đang có WIP của agent khác; không reset, stash hoặc ghi đè.
- No-cache recheck cuối `2026-09-18T06:19:41Z`: `https://mesflow.net`, role `PRODUCTION_TEST`, version `71.0.0.327`, migration `0054_multi_open_session_per_employee`, commit API `unknown`. Live CSS SHA-256 `979d2d4b9bd712211d4bf8e180431c96cee2443b355d6292091568194df05243`; pending `.328` CSS SHA-256 `1723e168375b39e36b598f9a6481ba55bb07b1be7d5b60a043bdbb9b3a99681e`, nên live vẫn là `.327`, chưa phải `.328`.

## Root cause và thay đổi `.328`

- Timeline mobile đặt `min-width:720px` trực tiếp trong `.employee-day-row` và cho cả row `overflow-x:auto`; content-width của card vì vậy ảnh hưởng autosizing/layout thay vì chỉ cuộn thang giờ.
- Các rule `.op-identity.compact` và `b.row-title` thắng typography chung theo từng tab. Computed `.327` tại 390px: title Operation/People đều 13px, body People 13px, meta 12px; hierarchy không đúng yêu cầu.
- Rule legacy toàn trang `header{margin-bottom:22px}` áp nhầm vào `.op-card-head`; cộng grid gap 8px tạo đúng 30px khoảng trắng trước tiến độ.
- `.328` cô lập scroll vào `.employee-day-track-scroll`, đặt typography dùng chung cho hai tab: desktop title/body/meta = 13/14/11px và mobile = 16/14/12px; wrap metadata và `min-width:0`, đồng bộ padding/gap, giữ zoom và đặt `text-size-adjust:100%`. `.op-card-head` reset margin scoped Dashboard nên gap thực đo còn 8px. Không che lỗi bằng `overflow:hidden` ở card.

## Browser evidence

- Regression chính Chromium: 8/8 PASS; WebKit: 8/8 PASS, `--retries=0`, fixture không sửa data thật. Nhóm Dashboard/hierarchy/quantity Chromium mở rộng: 41/41 PASS.
- Viewport: 1920x1080, 1366x768, 414x896, 390x844, 375x812.
- Desktop cả hai tab: Operation title/body/meta 13/14/11px. Mobile cả hai tab: title/body/meta 16/14/12px. Root/card overflow false; timeline cuộn trong vùng riêng; progress width bằng body width; gap header→progress 8px.
- Bao phủ tên/mã Operation, Part, PO và nhân viên dài; 1 và >=2 session; OPEN/CLOSED; mở chi tiết session; giữ ngày khi đổi tab; refresh/sort; ca tối. WebKit là browser engine, không phải Safari thật trên iPhone hardware.
- Screenshot bền vững ngoài source tree:
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/before-71.0.0.327-chromium-dashboard-operation-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/before-71.0.0.327-chromium-dashboard-people-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/after-71.0.0.328-chromium-dashboard-operation-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/after-71.0.0.328-chromium-dashboard-people-390x844.png`

## Tests và gate

- Contract + timing boundary Python: 3/3 PASS.
- `node --check app/mesflow/web/static/app.js`, version sync, diff check: PASS.
- Project preflight: PASS (port 18280 warning vì local sandbox `.327` đang chạy, không phải failure).
- Assertion `test_variance_zero_wording_not_negative_countdown` là stale: nó khóa ba chuỗi inline đã bị helper `expectedTimingHtml(expectedTiming(...))` thay từ `.322`. Trước sửa: local và CI cùng fail. Sau sửa: giữ nguyên test ID, khóa invariant overrun không âm và Playwright chạy renderer thật tại 59/60/61 giây; targeted 1/1 PASS, không đổi công thức thời gian.
- Full required gate gần nhất: unit 321 pass/10 skip; static 744 pass/9 skip; critical PostgreSQL/API 44 pass/1 skip; integration 578 pass/2 skip; Playwright 538 pass/4 skip, 1 flaky, 7 fail. Năm failure Dashboard là selector `.employee-session-chips` stale từ refactor `.323`, và mismatch desktop 11/10 so với 13/11; đã sửa trong scope và targeted 41/41 PASS sau sửa.
- Blocker còn lại ngoài diff/task: `tests/e2e/part-block-primitive.spec.js::nút xoá Operation căn giữa chiều cao hàng, vùng bấm đủ lớn` fail cả hai lượt với lệch tâm `44.015625px` trên baseline UI; `network-resilience` offline simulation flaky (pass retry). Không sửa hai vùng ngoài Dashboard và không hạ/skip gate. Vì full required gate chưa xanh trên exact candidate nên không build/deploy.

## Scope / automation check

- Không thêm hook, cron, watcher, workflow, auto PR trigger, service, DB/schema, API, auth hoặc OCR vào build/test/EXE.
- Chỉ app static Dashboard, focused tests, version declarations và báo cáo task thay đổi. Không đụng Session management hotfix `.326`.

## Merge / deploy checkpoint

- Version source đã bump cache/release key sang `71.0.0.328`, nhưng chưa build artifact vì required gate chưa xanh.
- Commits: `.327` checkpoint `7e0abeb`; initial `.328` `b56b3b2`; timing regression `a6bd520`; stale navigation test `9c7132d`; current Operation-row tests `6fc648f`; final shared desktop/mobile typography `dfc6512`.
- Branch đã push tới `origin/agent/codex/dashboard-mobile-tab-font-20260918` at `dfc65123ab350cf7eb4343373745770c23d74c0c`. Không mở/merge PR vào `origin/main`: remote main `10ac299` là ancestor và candidate đang ahead 221 commit, nên merge sẽ kéo thay đổi ngoài scope/live lineage. Không force/rebase main cũ.
- Merge/deploy `.328`: BLOCKED_GATE; không force/bypass và không deploy source chưa merge.
- TEST hiện tiếp tục chạy exact `.327`/`7e0abeb` artifact, healthy; không redeploy/restart vì live đã có đúng artifact checkpoint và `.328` chưa đủ gate.

## Rollback placeholder

Không có migration. Previous exact artifact trước `.327`: image digest `127.0.0.1:5000/mesflow-app@sha256:5c609d495d3ab3d3934ceaecfaa474a02f83608174156a1a8176a931d759cd3f` (`71.0.0.326`). Nếu `.328` sau này được gate và deploy nhưng smoke fail, dùng artifact `.327` digest `sha256:aadba58d969634ae312de62067cd69dc148978c689247ddcf4e73122b864e694` và chỉ recreate app service; không restart PostgreSQL/nginx/service khác.

## DEV exception deploy 2026-09-18 07:09Z

- Owner-approved one-time DEV exception: deploy from clean hotfix branch despite full CI timeout and known pre-existing Part assertion; default gates remain unchanged and are reported honestly.
- Verified route: `dev.mesflow.net` Cloudflare tunnel ingress → `http://localhost:8310` → Docker project `mesflow-dev`, service/container `app`/`mesflow-dev-app`; compose file `/home/dell/workspace/mesflow-dev/compose.dev.yml`. Only `app` was recreated with `docker compose -p mesflow-dev ... up -d --no-deps app`; PostgreSQL container/volume and tunnel were untouched.
- Previous DEV: `mesflow-app:71.0.0.323`, image digest `sha256:958c456ea238cc080e451d559386c600aa3b9c47729ab8738166b5d6edf8f0a6`, DB container id `d8534c8c45352883f499b23f670940aa5832ec377ef2b4112e62404a112ee113`. Rollback: set `MESFLOW_IMAGE=mesflow-app:71.0.0.323` in `/home/dell/workspace/mesflow-dev/.env`, then run the same `up -d --no-deps app` command.
- Deployed immutable candidate `71.0.0.328`, source `42be6c7f7d1c933e7ccd02e065aedba94044afb0`, image digest `sha256:81616c9bdba8a188795084932baa0b5a4c35646785c5297ff057cfb503cf46dd`; migration head unchanged `0054_multi_open_session_per_employee`.
- HTTPS ready after deploy: version `71.0.0.328`, `ok:true`, app healthy. HTTPS `/static/ui.css` SHA-256 `1723e168375b39e36b598f9a6481ba55bb07b1be7d5b60a043bdbb9b3a99681e`, exactly equals source CSS.
- Container Playwright smoke with real DEV login and synthetic dashboard fixture: Chromium, 390x844, Operation and Nhân viên/Session tabs `2/2 PASS`, no body/document horizontal overflow; screenshots:
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/dev-71.0.0.328-dashboard-operation-390x844.png`
  - `/home/dell/workspace/mesflow/artifacts/evidence/MF-DASH-MOBILE-20260918/dev-71.0.0.328-dashboard-people-390x844.png`
  Safari/iPhone hardware chưa chạy.
- Full CI remains `cancelled` by the documented 20-minute workflow timeout; Part primitive fails identically on baseline/candidate (`44.015625px`) and remains out of scope. DEV deployment is complete under the owner exception; this does not authorize production/`mesflow.net` deployment.

## Recheck 2026-09-18 06:25Z — exact blocker, no redeploy

- No-cache `https://mesflow.net/api/system/ready` vẫn `ready`, role `PRODUCTION_TEST`, version `71.0.0.327`, commit API `unknown`; live CSS SHA-256 `979d2d4b9bd712211d4bf8e180431c96cee2443b355d6292091568194df05243`. Candidate source `.328` CSS hash vẫn `1723e168375b39e36b598f9a6481ba55bb07b1be7d5b60a043bdbb9b3a99681e`, chưa có artifact/promote.
- `gh run view 35314540641 --json ...` (không `--watch`): exact head `c5902fd487318786d8af697d2347ab30734b2cb2`, `PostgreSQL Docker Tests`, status `in_progress`, conclusion rỗng; chưa đủ điều kiện promote.
- `part-block-primitive` là fixture/mocked API, test file không đổi từ baseline. Đã thử chạy riêng đúng case `nút xoá Operation căn giữa...` với cùng Chromium/1366 trên deployed `.327` container; runner Chromium local/container đều crash GPU trước mở page (không phải assertion), nên không coi đó là bằng chứng pass/fail baseline. Existing full-gate evidence vẫn ghi assertion thật `offCentre=44.015625px` trên baseline UI. Candidate không có diff selector `.part-block`, `.op-row`, `.template-old-*`, `.po-*`; toàn bộ CSS hotfix mới đều scoped `body[data-page="dashboard"]` hoặc `.employee-day-track-scroll`, vì vậy không có đường rò selector Dashboard sang Part. Do đó blocker được phân loại pre-existing/out-of-scope, không sửa UI Part và không nới test.
- Evidence limitation được ghi rõ: chưa có ảnh before/after riêng cho Part-block; các ảnh Dashboard before/after hiện có giữ nguyên đường dẫn ở mục Browser evidence. Không claim DONE/deploy.
