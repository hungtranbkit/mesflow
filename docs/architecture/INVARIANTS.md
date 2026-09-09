# Bất biến nghiệp vụ của MESFlow

Tài liệu này ghi lại những quyết định đã chốt và những bất biến mà mọi đường ghi
phải giữ. Mục đích rất cụ thể: **để người sửa sau không vô tình đảo ngược một
quyết định nghiệp vụ chỉ vì code không nói ra nó.**

Mỗi mục dưới đây tương ứng với một lỗi đã xảy ra thật. Cái giá của việc không
viết ra chúng đã trả rồi.

---

## 1. Định danh Operation

**`operations.id` là danh tính. `operations.code` thì không.**

`code` chỉ unique **trong phạm vi một Part**. Hai Part khác nhau trong cùng một
PO hoàn toàn có thể cùng có `OP01` — đó là chuyện bình thường ở xưởng, và
Template editor cho phép.

Hệ quả bắt buộc:

- QR mới dùng `WF|OPID|<id>`. QR cũ `WF|OP|<code>` vẫn phải đọc được vì tem đã
  in và đang dán ngoài xưởng.
- Khi một `code` khớp **nhiều** Operation, bộ giải mã phải **TỪ CHỐI**, không
  được `LIMIT 1` rồi đoán. Đoán sai nghĩa là công nhân bấm vào một Operation
  khác Operation trên tem, và không ai biết.
- `display_key` là nhãn hiển thị có kèm Part, sinh ra để đọc. Nó **không phải
  khoá** — đừng tra cứu theo nó.

Lỗi đã xảy ra: `instantiate()` nối cấu hình dòng vật tư theo `code` toàn cục, nên
OP của Part B hút nguyên liệu từ OP cùng mã của Part A (sửa ở 71.0.0.262).

---

## 2. Loại Operation

Nguồn sự thật: `mesflow/domain/policy.py`.

| Loại | Ghi nhận CÔNG | Ghi nhận SẢN LƯỢNG | Vào WIP / tiến độ / điều kiện hoàn thành |
|---|---|---|---|
| `PRODUCTION` | có | có | có |
| `SETUP` | có | **không** | **không** |
| `REWORK` | có | **không** | **không** |

`operation_type` là cột thêm sau. `NULL` và chuỗi rỗng đều là `PRODUCTION` —
dữ liệu cũ có trước cột này và tất cả đều là OP sản xuất.

Hệ quả bắt buộc:

- Mọi rollup sản lượng phải lọc `PRODUCTION`. Quên một chỗ là sản lượng của OP
  phụ lọt vào tiến độ PO, hoặc `operation_count` phình ra khiến PO **không bao
  giờ** đạt `COMPLETED`.
- Không được chuyển một session **có sản lượng** sang OP phụ: số đó sẽ biến mất
  khỏi mọi báo cáo mà không để lại dấu vết. Guard nằm ở tầng service
  (`transfer_operation`), không phải ở giao diện — kiosk, API và Excel đều đi
  qua đó.
- Export Excel chỉ xuất OP sản xuất. OP phụ xuất ra rồi import ngược lại sẽ
  được dựng thành `PRODUCTION` không có cha, và CHECK biconditional
  `ck_operations_setup_has_parent` cho qua vì cả hai vế đều sai.

---

## 3. SETUP — ngữ nghĩa cuối cùng

**SETUP KHÔNG phải điều kiện tiên quyết.** Quyết định của người dùng,
2026-09-09.

- Một OP sản xuất **luôn** bắt đầu được, kể cả khi OP setup liên quan chưa chạy.
- SETUP là một Operation hỗ trợ độc lập, gắn với OP chính qua
  `parent_operation_id`. Nó có tem QR riêng và chạy trên đúng luồng
  quét / bắt đầu / kết thúc mà kiosk đã có — **không sửa firmware ESP**.
- `setup_note` là một trường văn bản dài, không phải checklist. Quy trình chi
  tiết nằm trên tờ A4 ở máy; kiosk chỉ điều khiển TRẠNG THÁI.
- Không có khái niệm hết hạn setup, không có nút reset, không có mã lỗi
  `SETUP_REQUIRED`.
- Chữ dùng trên giao diện: *"Có OP setup liên quan"* / *"Không có OP setup liên
  quan"*. Đừng quay lại *"Yêu cầu setup máy trước khi sản xuất"* — đó là mô
  hình cũ.

Canh chừng: `tests/test_setup_semantics_wording.py`.

---

## 4. Số lượng và sửa hàng

Luồng chuẩn, đọc từ trái sang phải:

```
Mục tiêu 100
  -> đạt 92 + chờ sửa 8
  -> sửa được 6 + phế 2
  -> OP nguồn: đạt 98, chờ sửa 0, phế 2 — VẪN IN_PROGRESS
  -> làm thêm 2 đạt
  -> COMPLETED
```

Bất biến:

- **Session nguồn là chủ sở hữu duy nhất của con số.** Session sửa hàng ghi
  nhận CÔNG (ai sửa, khi nào, ở bàn nào) và mang số lượng **bằng 0**. Nếu nó
  cũng mang số thì hai dòng cùng mô tả một sản phẩm vật lý, và mọi báo cáo quên
  lọc `is_rework_op` sẽ đếm hai lần.
- `rework_qty + scrap_qty <= defect_qty` — có CHECK ở CSDL. Đường sửa số liệu
  phải chặn TRƯỚC bằng thông báo tiếng Việt, không để CSDL ném ra HTTP 500.
- `rework_ledger` là bản ghi bất biến của từng lần xử lý; `work_sessions` chỉ
  là số cộng dồn. Khi hai bên lệch nhau, lấy số **cao hơn** làm chuẩn:
  một lệnh sửa số liệu không được phép làm sản phẩm đã sửa quay lại hàng chờ để
  được credit lần thứ hai.
- Lỗi chưa xử lý **không** tự thành phế. Phế chỉ sinh ra khi có người bấm.
- Hoàn thành xét theo `good_qty >= target_qty` của **OP sản xuất**. Sản xuất
  vượt là được phép.

---

## 5. Vòng đời Session và dòng vật tư

Một dòng `operation_input_consumptions` là phần đầu vào mà **một** session đang
giữ, rút từ OP nguồn của Operation mà session đó thuộc về.

1. `target_operation_id` **luôn** bằng `operation_id` hiện tại của session.
2. Dòng chỉ tồn tại khi session còn tính vào báo cáo (`CLOSED` và không bị
   loại). Session không đóng góp gì thì không được giữ hàng của ai.
3. `source_operation_id` luôn là `input_source_operation_id` đang cấu hình của
   Operation đích.

Tổng đã phân bổ trên một OP nguồn **không** nối sang `work_sessions` khi cộng.
Đó là lý do vi phạm (2) không lộ ra ở bất kỳ báo cáo nào — hàng bị giữ im lặng.

Vì vậy:

- `exclude_session()` phải **nhả** dòng; `restore_session()` **cấp lại**, và
  nếu OP nguồn không còn đủ thì **từ chối rõ ràng** thay vì phân bổ vượt.
- `transfer_operation()` phải **rebind** dòng sang Operation mới, hoặc từ chối
  nếu nguồn của Operation mới không đủ hàng.

Canh chừng: `tests/integration/test_session_lifecycle_invariants.py`.

---

## 6. Thứ tự khoá

**Khoá `FOR UPDATE` trên dòng `production_orders` cha phải là khoá dòng ĐẦU
TIÊN mà bất kỳ transaction ghi nào lấy.**

Một transaction luôn lấy khoá cha chung trước mọi khoá con thì không thể nằm
trong vòng chờ qua nó — đồ thị chờ sụp thành một hàng đợi.

Helper: `lock_production_order_for_operation_first()`. Mọi đường ghi chạm
Operation / Session / Part đều phải gọi nó trước tiên. Ba đường từng đi ngược
chiều (`rework.resolve`, `OperationRepository.update`, `cancel_operation`) đã
sửa ở 71.0.0.261.

---

## 7. Vòng đời sự kiện kiosk offline

```
PROCESSING -> accepted | duplicate | retryable | rejected
```

- `retryable` **không** phải trạng thái cuối. Máy chủ giữ dòng kèm lý do và
  `attempt_count`; thiết bị nhận `transient` — đúng thứ firmware hiện tại đã
  hiểu là *"giữ lại, gửi lại"*. **Không đổi ESP.**
- Đụng độ trạng thái (`ConflictError`) là **tạm thời**: OP nguồn chưa có hàng,
  Operation chưa được phép bắt đầu. Chúng có thể đúng lại. Trước đây chúng bị
  ghi `rejected` nên thiết bị bỏ luôn, và một ca làm việc có thật biến mất.
- Dữ liệu sai vĩnh viễn (`ValueError` / `NotFoundError`) thì `rejected` ngay:
  thời gian không chữa được.
- Quá `MAX_RETRY_ATTEMPTS` thì chuyển `rejected` với
  `reason_code='RETRY_EXHAUSTED'` — dừng, nhưng dừng một cách **nhìn thấy
  được**.
- Phân loại cố ý nghiêng về *"thử lại được"*: đoán sai theo hướng đó chỉ tốn
  vài lần gửi lại; đoán sai theo hướng kia thì mất dữ liệu sản xuất.

---

## 8. Trạng thái Production Order

Tập hợp lệ: `DRAFT`, `PLANNED`, `RELEASED`, `IN_PROGRESS`, `PAUSED`,
`COMPLETED`, `CANCELLED`. Nguồn sự thật: `mesflow/domain/policy.py`.

**`ACTIVE` không phải trạng thái PO.** Nó từng nằm trong một tập chép tay như
một giá trị thừa vô hại, rồi được chép sang bảy câu truy vấn dashboard dưới
dạng `('IN_PROGRESS','ACTIVE','PAUSED')` — nơi nó **thay chỗ** cho `RELEASED`.
Hậu quả: PO vừa phát hành đơn giản là không hiện ra, không lỗi, không log.

- `RUNNABLE_PO_STATUSES` = `{RELEASED, IN_PROGRESS}` — được bắt đầu session mới.
  `PAUSED` cố ý không nằm trong đây.
- `OPEN_PO_STATUSES` = `{RELEASED, IN_PROGRESS, PAUSED}` — thứ dashboard phải
  nhìn thấy.

Canh chừng: `tests/test_po_status_policy_is_single_sourced.py`.

---

## 9. Đối soát

`mesflow audit-integrity [--json]` — **chỉ đọc, không bao giờ tự sửa.**

21 kiểm tra, trong đó bảy kiểm tra thêm 2026-09-09 nhắm đúng những bất biến ở
trên. Điểm chung của chúng: khi vi phạm, hệ thống **không** báo lỗi — số chỉ
đơn giản là sai, hoặc dữ liệu chỉ đơn giản là không hiện ra. Đó là lý do chúng
cần một lệnh đối soát chủ động chứ không thể trông vào việc người dùng phát
hiện.

Nên chạy sau mỗi đợt chaos/load/soak, và sau mỗi lần khôi phục dữ liệu.
