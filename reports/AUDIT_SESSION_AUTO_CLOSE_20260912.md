# Audit P0/P1 — Session không tự kết thúc khi hết ca/hết ngày

Lane phụ. **Không merge, không deploy từ lane này.** Bàn giao cho session `mesflow`.

- Nhánh: `hp3/audit-shift-auto-close`
- Gốc: `origin/integration/daily-dashboard-test` @ `4307bab` (71.0.0.294)
- Ngày audit: 2026-09-12
- Yêu cầu mới: **REQ-SHIFT-003** (EN + VI + traceability đã cập nhật)

---

## 1. Kết luận: vì sao sáng nay session vẫn OPEN

**Không phải lỗi logic. Code auto-close đúng và đầy đủ — nhưng KHÔNG CÓ GÌ GỌI NÓ.**

Hai nguyên nhân độc lập, cả hai đều đủ để một mình gây ra triệu chứng:

### Nguyên nhân A (chính) — scheduler chưa bao giờ được cài trên TEST

MESFlow **không có scheduler trong tiến trình**. Đã kiểm, không phải suy đoán:

- `requirements.txt` chỉ có Flask / waitress / psycopg / alembic / SQLAlchemy /
  Werkzeug / openpyxl / qrcode — **không APScheduler, không celery**.
- `grep -rniE "apscheduler|celery|BackgroundScheduler|schedule\.every|threading\.Timer|asyncio\.create_task" app/`
  → **0 kết quả**.
- Người gọi `ShiftSessionReconciliationService` trong TOÀN BỘ app chỉ có đúng
  một chỗ: `mesflow.cli.reconcile_shift_sessions`. Không có route HTTP nào
  chạy nó như một tác dụng phụ (khác hẳn `reconcile-exceptions`, thứ VẪN chạy
  kèm `GET /api/exceptions`).
- `Dockerfile` `ENTRYPOINT ["mesflow-entrypoint"]`; `scripts/docker-entrypoint.sh`
  không khởi động cron.

Nên trigger duy nhất là **host cron → `docker compose exec <app> python -m mesflow.cli reconcile-shift-sessions`**
(`scripts/install-reconcile-cron.sh`, `* * * * *`).

Và đây là lỗ hổng:

| Deploy path | Target | Cài + verify cron? |
|---|---|---|
| `scripts/deploy.sh` | `prodtest`, `production` | **CÓ** — gọi `install-reconcile-cron.sh`, `install-log-retention-cron.sh`, rồi `verify-scheduler-cron.sh` và coi exit≠0 là deploy fail |
| `scripts/deploy-remote-test.sh` | **backend thật của mesflow.net** | **KHÔNG — không có một dòng nào** |

`grep -n "cron\|reconcile\|scheduler\|verify-scheduler" scripts/deploy-remote-test.sh`
→ **0 kết quả** trên 195 dòng.

`scripts/verify-scheduler-cron.sh` được viết ra chính xác để trạng thái
"code có, CLI có, cron thiếu, scheduler không bao giờ chạy" là bất khả thi —
nhưng nó chưa bao giờ được nối vào đường deploy của mesflow.net.

**Hệ quả:** trên TEST, `reconcile-shift-sessions` chưa từng chạy lần nào, nên
không session nào từng được auto-close, bất kể cấu hình cờ.

### Nguyên nhân B (độc lập) — hai công tắc rollout mặc định TẮT

```
MESFLOW_SHIFT_AUTO_CLOSE_ENABLED   mặc định "0"
MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN   mặc định "1"
```

Đây là **chủ ý** (`docs/operations/SHIFT_AUTO_CLOSE_ROLLOUT.md` — rollout phải
dry-run trước). Với mặc định đó, job tìm ra đúng ứng viên rồi ghi `WOULD_CLOSE`
và **không đóng gì cả**. Không lỗi, không cảnh báo.

Không một file nào trong repo — `.env.example`, `compose.yml`, `compose.test.yml`,
bất kỳ script deploy nào — từng đặt `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1`.
Chỉ có `install-reconcile-cron.sh` **in ra lời nhắc** rằng người vận hành phải
tự đặt. Không có dấu vết nào cho thấy bước 6 của runbook đã từng được chạy.

Đo trong container của lane (cùng image, cùng code 294):

```
timezone_name            = Asia/Ho_Chi_Minh
auto_close_enabled       = False      <-- mặc định
auto_close_dry_run       = True       <-- mặc định
auto_close_grace_min     = 15
past_shift_end_grace_min = 10
```

### Nguyên nhân C (lỗ hổng thứ ba, phát hiện khi audit)

Cấu hình ca thật **không phủ hết 24 giờ**: `DAY 08:00–17:00`, `NIGHT 18:00–00:00`
→ hở `17:00–18:00` và `00:00–08:00`. `find_candidates()` có
`if window is None: continue`, tức session bắt đầu trong khe đó **không bao giờ
là ứng viên**, và **không có fallback hết ngày**. Nó ở OPEN vĩnh viễn kể cả khi
A và B đã được khắc phục. Đã khoá bằng test trước khi vá.

---

## 2. Cơ chế hiện có (mục 1) — code ĐÃ ĐÚNG

| Thành phần | Vị trí | Vai trò |
|---|---|---|
| Quét ứng viên | `services/shift_session_service.py` → `find_candidates()` | mọi session `OPEN` mà ca CỦA CHÍNH NÓ (ca tại `started_at`, không phải "ca hôm nay") đã kết thúc quá grace |
| Đóng một session | `db/repositories/execution.py` → `auto_close_for_shift_end()` | vòng đời RIÊNG, không phải `finish(good_qty=0)` ngụy trang |
| Cờ rollout | `core/config.py` | `ENABLED` / `DRY_RUN` / `GRACE_MINUTES` |
| Entry point | `mesflow.cli reconcile-shift-sessions` (+ `--dry-run`/`--live` đè env) | |
| Cài lịch | `scripts/install-reconcile-cron.sh` (`* * * * *`) | host cron, idempotent |
| Kiểm lịch | `scripts/verify-scheduler-cron.sh` | chứng minh cron THẬT SỰ có trong crontab |
| Quan sát | `scheduled_job_health` (migration 0040/0041) → `/api/system-health` | `NEVER_RUN`/`MISSED`/`FAILED` |
| Audit dữ liệu | `mesflow audit-sessions [--json]` | chỉ đọc, không sửa gì |
| Ngoại lệ sớm | `SESSION_PAST_SHIFT_END` (grace 10') | cảnh báo TRƯỚC khi auto-close hành động |
| Ngoại lệ sau | `AUTO_CLOSED_UNCONFIRMED` | chờ người xác nhận số liệu |

`auto_close_for_shift_end()` đặt: `status='CLOSED'`, `ended_at = shift_end_at`
(**ranh giới ca, KHÔNG phải "bây giờ"**), `close_reason='AUTO_SHIFT_END'`,
`closed_by_system=TRUE`, `shift_boundary_used_at`, `quantity_confirmed=FALSE`;
giữ nguyên `good/defect/rework`; ghi audit + domain event `SESSION_AUTO_CLOSED`;
advisory lock theo `session_id` nên idempotent và an toàn khi chạy song song.

**Không có gì phải sửa trong logic này.** Vấn đề nằm hoàn toàn ở vận hành.

---

## 3. Trigger thật (mục 2)

- cron/systemd/background/request-driven? → **host cron, và CHỈ host cron.**
- Có chạy trên TEST mesflow.net không? → **Không có bằng chứng nào cho thấy có,
  và đường deploy của chính host đó không cài cron.**

Giới hạn của lane này, nói rõ: prodtest (`/home/dell/deploy/mesflow-prodtest`)
**không nằm trên máy HP** (`id dell` → no such user; thư mục không tồn tại;
`ssh dell@127.0.0.1` → host key verification failed). Host thật của mesflow.net
chỉ deploy được bằng `deploy-remote-test.sh` với credential không có trong lane
này. Nên **không kiểm được crontab của TEST trực tiếp từ đây.**

Kiểm được, và đã kiểm:

```
$ curl https://mesflow.net/api/system/ready
{"version":"71.0.0.294","commit":"4307bab2204e","server_role":"PRODUCTION_TEST",
 "migration_head":"0050_user_session_epoch","ok":true,
 "timezone":{"business_timezone":"Asia/Ho_Chi_Minh","database_timezone":"UTC",
             "host_timezone":"Asia/Ho_Chi_Minh"}}
```

→ TEST đang chạy **đúng code mới nhất** (294 = tip của integration) và
**migration đã lên head**. Nên đây **không** phải "thiếu code" hay "thiếu schema".

`/api/system-health` (thứ trả về `JOBS` + `SESSION_LIFECYCLE`) trả `401
AUTH_REQUIRED`; lane này không có credential TEST và tôi không thử đoán.

### Hai lệnh mesflow cần chạy trên TEST để chốt

```
crontab -l | grep reconcile-shift-sessions      # dự đoán: KHÔNG có dòng nào
sh scripts/verify-scheduler-cron.sh             # dự đoán: MISSING, exit 1
```

Và bằng chứng phía DB, không phụ thuộc host:

```sql
SELECT job_name,last_started_at,last_success_at,last_status
  FROM scheduled_job_health WHERE job_name='shift_session_reconciliation';
```

`last_started_at IS NULL` + `last_status='UNKNOWN'` ⇒ **job chưa chạy lần nào**.
Đã xác nhận cơ chế này hoạt động đúng trong lane: hàng đó khởi đầu là
`UNKNOWN/NULL`, và chỉ sau **một** lần chạy CLI thủ công mới thành
`SUCCESS` + có `last_started_at`.

---

## 4. Config TEST/release (mục 3)

| Câu hỏi | Trả lời |
|---|---|
| auto-close enabled? | **Không** — mặc định `0`, không file nào trong repo đặt thành `1` |
| dry-run? | **Có** — mặc định `1` |
| timezone | `Asia/Ho_Chi_Minh` (business + host), DB `UTC`. Đúng. `/api/system/ready` của TEST xác nhận. |
| shift end lấy từ đâu | bảng `work_shifts` + `work_shift_intervals`, qua `resolve_shift_window_for_datetime()`; fallback biên dịch sẵn `DEFAULT_SHIFTS` **chỉ** khi bảng chưa tồn tại |
| grace | auto-close `15'`; exception `SESSION_PAST_SHIFT_END` `10'` (cố ý ngắn hơn để người thấy trước) |
| không có shift thì fallback hết ngày? | **TRƯỚC audit: KHÔNG.** `window is None → continue`. Đây là nguyên nhân C. **Sau bản vá: CÓ** (REQ-SHIFT-003). |

---

## 5. Dữ liệu OPEN qua đêm (mục 4) — giới hạn quyền đọc

- DB của TEST mesflow.net: **không truy cập được từ lane này** (không SSH, không
  credential). Không đụng tới.
- DB `mesflow-postgres` local (`/opt/mesflow`, container `mesflow-app`): đang chạy
  **71.0.0.46**, một bản **trước khi tính năng auto-close tồn tại** — container
  không có `shift_session_service.py` và không có lệnh CLI reconcile nào. Không
  dùng làm bằng chứng cho triệu chứng hôm nay, và **không sửa gì**.
- DB của lane (test, tmpfs): `audit-sessions` chạy sạch, 0 OPEN — dữ liệu tổng hợp,
  không phản ánh xưởng thật.

Công cụ để mesflow chạy trên TEST khi có quyền, **chỉ đọc**:

```
docker compose exec <app> python -m mesflow.cli audit-sessions --json > pre-rollout-audit.json
```

Nó trả về đúng các nhóm cần cho mục 4: `OPEN`, `PAST_SHIFT_END`, `OPEN_OVER_12H`,
`CROSS_DAY`, `EMPLOYEE_OVERLAP`, `IMPOSSIBLE_DURATION`, ... kèm `started_at` và
ranh giới ca đã resolve cho từng dòng.

---

## 6. Test tái hiện (mục 5) — `tests/integration/test_shift_auto_close_rollout_state.py`

16 bài, chạy trên PostgreSQL thật. Bộ bài có sẵn
(`test_shift_session_lifecycle.py`) chứng minh CƠ CHẾ đúng — nhưng **mọi bài
trong đó đều gọi `reconcile(dry_run=False)`**, tức bỏ qua đúng hai công tắc
quyết định. Không bài nào khoá điều đó. Đó là lý do "code đã có" và "session
thật sự được đóng" là hai chuyện khác nhau mà không ai thấy.

| Bài | Khoá gì |
|---|---|
| `compiled_in_defaults_are_auto_close_off` | mặc định sản xuất đúng là OFF/DRY_RUN (đỏ nếu ai đó đổi mặc định mà không cập nhật runbook) |
| `default_flags_find_the_stale_session_but_never_close_it` | **chính triệu chứng**: tìm ra ứng viên, `WOULD_CLOSE`, session vẫn `OPEN` |
| `enabled_alone_is_still_not_enough_dry_run_must_also_be_off` | hai công tắc độc lập |
| `enabled_and_live_closes_at_shift_boundary_without_inventing_quantity` | đóng đúng ranh giới; `good/defect/rework` giữ nguyên; `quantity_confirmed=FALSE`; **không sinh `quantity_movements` giả** |
| `auto_closed_duration_does_not_run_overnight` | job chạy trễ **3 ngày** vẫn đóng ở 17:00 hôm đó → duration 1 giờ, không phải 72 giờ |
| `session_still_inside_its_own_shift_is_not_touched` | session hôm nay không bị đóng nhầm |
| `grace_window_is_respected_before_closing` | 17:05 chưa đóng, 17:20 mới đóng |
| `gap_start_really_has_no_shift_to_close_against` ×2 | tiền đề: khe `17:00–18:00` và `00:00–08:00` có thật |
| `gap_session_is_never_closed_when_day_end_fallback_is_off` ×2 | hành vi CŨ, giữ làm bằng chứng hồi quy |
| `gap_session_closes_at_day_end_with_fallback_on` ×2 | bản vá: đóng ở `24:00` ngày bắt đầu, `close_reason='AUTO_DAY_END'` |
| `day_end_fallback_is_deterministic_and_idempotent` | chạy lại không đổi `ended_at` |
| `day_end_auto_close_still_surfaces_as_auto_closed_unconfirmed` | close_reason mới không làm session rơi khỏi hàng chờ xác nhận |
| `scheduled_job_health_is_the_only_signal_that_the_job_actually_ran` | phân biệt "code có" với "scheduler chạy" |

---

## 7. Bản vá (mục 6) — an toàn, không tự bật gì

### 7.1 `scripts/deploy-remote-test.sh` nay cài + verify cron

Thêm đúng bước mà `deploy.sh` đã có: `install-reconcile-cron.sh`,
`install-log-retention-cron.sh`, rồi `verify-scheduler-cron.sh`, và in cảnh báo
rõ ràng nếu không verify được.

**Cài cron KHÔNG tự đóng session nào**: `ENABLED` vẫn `0`, `DRY_RUN` vẫn `1`.
Nó chỉ làm job **chạy**, để `scheduled_job_health` thôi báo `NEVER_RUN` và để
một chu kỳ dry-run trở nên quan sát được — đúng bước 3–5 của runbook. Việc bật
cờ vẫn là hành động riêng, có chủ ý, của người vận hành.

Cố ý **không** fail cứng: mô hình tài khoản của host này khác các target của
`deploy.sh`. Cron cài hỏng phải kêu to, nhưng không được bỏ dở một lần deploy
ứng dụng đã thành công.

### 7.2 REQ-SHIFT-003 — fallback hết ngày cho session không thuộc ca nào

- Ranh giới: **`24:00` giờ địa phương của NGÀY session bắt đầu**, rồi cùng grace.
  Tính **chỉ** từ `started_at`, không bao giờ từ "lúc job chạy" → deterministic,
  và chạy lại cho ra đúng cùng `ended_at` (idempotent).
- `close_reason='AUTO_DAY_END'` (`close_reason` là TEXT tự do, không constraint —
  không cần migration). Đã kiểm: **không có SQL/JS nào lọc theo literal
  `'AUTO_SHIFT_END'`**, chỉ có comment và dữ liệu seed tutorial.
- Điều kiện của exception `AUTO_CLOSED_UNCONFIRMED` là
  `closed_by_system AND NOT quantity_confirmed` — **không** phải `close_reason` —
  nên session đóng theo ngày vẫn nổi lên đúng chỗ cho admin bổ sung số liệu.
  **Không suy đoán good/NG**, đúng yêu cầu.
- Cờ riêng `MESFLOW_SESSION_DAY_END_FALLBACK_ENABLED` (mặc định `1`), chỉ có
  hiệu lực khi hai công tắc auto-close đã bật → môi trường chưa rollout không
  bị ảnh hưởng một chút nào. Đặt `0` là về đúng hành vi cũ.
- `auto_close_for_shift_end()` nhận thêm `close_reason='AUTO_SHIFT_END'` làm
  **mặc định** → mọi lời gọi cũ không đổi một bit nào.

### 7.3 Việc KHÔNG làm, và vì sao

**Không bật `MESFLOW_SHIFT_AUTO_CLOSE_ENABLED=1` ở bất kỳ đâu.** Runbook bắt
buộc `audit-sessions` làm baseline → dry-run một chu kỳ → kiểm tay 3–5 ứng viên
→ mới `DRY_RUN=0`. Bật thẳng trên một xưởng đang có tồn đọng session cũ sẽ
auto-close hàng loạt dữ liệu lịch sử chưa ai rà — đúng thứ rollout safety sinh
ra để chặn. Đây là quyết định vận hành của `mesflow`, không phải của lane audit.

---

## 8. Dashboard/report (mục 7)

- **Duration không kéo qua đêm**: `ended_at = ranh giới`, không phải `now()`.
  Khoá bằng `auto_closed_duration_does_not_run_overnight` (job trễ 3 ngày →
  duration vẫn 1 giờ).
- **Không phá báo cáo**: `AUTO_CLOSED_UNCONFIRMED` bắt theo
  `closed_by_system AND NOT quantity_confirmed`, không theo `close_reason` →
  giá trị mới an toàn. Đã sửa một comment SQL lỗi thời trong `analytics.py` cho
  khớp.
- **Timezone**: `Asia/Ho_Chi_Minh` cho business/host, `UTC` trong DB;
  `resolve_shift_window_for_datetime` từ chối datetime naive
  (`raise ValueError('naive datetime is not allowed in shift logic')`);
  fallback hết ngày đi qua `business_date`/`business_datetime_utc` nên tôn trọng
  đúng site timezone. TEST tự báo đúng bộ ba này.

---

## 9. Kết quả chạy

- pytest toàn bộ (chạy RIÊNG, không song song Playwright):
  **1318 passed, 18 skipped, 1 xfailed, 0 failed**.
- Bộ bài mới: **16/16 passed**.
- `xfailed` là lỗi nghiệp vụ `rework_qty` có sẵn, thuộc lane Rework, không liên
  quan.

---

## 10. Việc còn lại cho `mesflow` (theo thứ tự)

1. Trên host TEST: `crontab -l | grep reconcile-shift-sessions` và
   `sh scripts/verify-scheduler-cron.sh`. Ghi lại kết quả — đó là bằng chứng
   cuối cùng cho nguyên nhân A.
2. `mesflow audit-sessions --json > pre-rollout-audit.json` (chỉ đọc) — baseline
   thật của bao nhiêu session đang tồn đọng.
3. Cài cron (deploy lại bằng `deploy-remote-test.sh` đã vá, hoặc chạy tay
   `install-reconcile-cron.sh`). Xác nhận `scheduled_job_health` bắt đầu có
   `last_started_at`.
4. `ENABLED=1, DRY_RUN=1` → đọc `runtime/shift-reconcile.log` ít nhất một chu kỳ,
   kiểm tay 3–5 ứng viên `WOULD_CLOSE`.
5. Chỉ khi đó mới `DRY_RUN=0`.
6. Sau 24h: `audit-sessions` lại, so với baseline.
