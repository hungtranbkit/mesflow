# Danh tính của một Operation

Trạng thái: đang hiệu lực · Cập nhật 2026-09-10

Tài liệu này trả lời một câu: **cái gì định danh một Operation?** Nó tồn tại vì
câu trả lời đã từng khác nhau tuỳ theo bạn hỏi lớp nào, và mỗi lần khác nhau
là một lần sản lượng ghi vào nhầm chỗ.

## Bốn khái niệm, không được lẫn

| Khái niệm | Là gì | Đổi được không |
|---|---|---|
| **Danh tính bất biến** | `operations.id` | Không bao giờ |
| **Khoá nghiệp vụ** | `operations.code` | Có — người dùng đổi được |
| **Khoá hiển thị** | display key `<part>-<code>` | Theo code/part |
| **Tem QR** | `operations.qr` | Xem "Đổi mã" bên dưới |

Mọi quan hệ nội bộ đi bằng `operations.id`, qua khoá ngoại thật. Không quan hệ
nào được suy ra từ mã. `docs`-level: `tests/integration/test_operation_identity_audit_2.py`
lấy danh sách bảng từ `pg_constraint` và chứng minh điều đó cho từng bảng.

## Uniqueness ở DB, tính đến hôm nay

```
operations_code_key  UNIQUE (code)   -- TOÀN CỤC, không phải theo Part
operations_qr_key    UNIQUE (qr)     -- TOÀN CỤC
```

Nghiệp vụ nói "hai Part được phép cùng có OP01". Schema **chưa** cho phép điều
đó. Khoảng cách được lấp ở lớp ứng dụng bằng `operation_code_suffix()`: lúc tạo
PO, mã Part được gấp vào mã Operation, nên `OP01` của PartA thành
`<PO>-PARTA-OP01`. Người dùng thấy đúng thứ họ mong đợi trên màn hình; thứ nằm
trong bảng thì không phải mã họ gõ.

Đây là **hiện thực chuyển tiếp, không phải ràng buộc nghiệp vụ.**

## Đổi mã Operation

`operations.qr` **cố ý không bị viết lại** khi mã đổi. Đó là một quyết định:
tem đã in đang dán ngoài xưởng, và bản chụp catalog trong kiosk offline, đều
mang payload cũ. Giữ nguyên `qr` là thứ giữ cho chúng tiếp tục trỏ đúng.

Hệ quả phải chặn: mã vừa được giải phóng không được cấp lại cho Operation khác
trong khi tem cũ vẫn đòi nó. Nếu cho, `WF|OP|<mã>` khớp `qr` của hàng cũ VÀ
`code` của hàng mới, resolver từ chối cả hai, và **hai Operation cùng lúc không
quét được ngay giữa ca**. Guard nằm ở `OperationRepository.create/update` và ở
đường nhập Excel (đường Excel ghi thẳng bằng SQL nên phải có bản của riêng nó).

## Giải một tem quét được

`app/mesflow/domain/qr_identity.py` là nơi DUY NHẤT làm việc này.

1. `WF|OPID|<id>` — danh tính bất biến, luôn giải ra duy nhất. Tem mới dùng
   dạng này.
2. `WF|OP|<mã>` — dạng cũ, vẫn phải đọc được. Khớp `qr` HOẶC `code`.
3. Có thể thu hẹp bằng ngữ cảnh Part/PO khi nơi gọi biết. Ngữ cảnh chỉ THU HẸP.
4. Ra nhiều hơn một → `AmbiguousOperationQR`. **Không bao giờ `LIMIT 1`.**

Thà bắt in lại một tem còn hơn ghi sản lượng vào nhầm công đoạn.

Cùng nguyên tắc, cùng module: `resolve_employee_id()` cho thẻ nhân viên.
`employee_no` và `qr` unique riêng lẻ nhưng không unique chéo nhau.

### Lỗi phải là LOẠI, không phải chuỗi

`AmbiguousOperationQR` / `AmbiguousEmployeeQR` kế thừa `ConflictError`, nên mọi
nơi đã bắt `ConflictError` chạy y như cũ. Nơi nào cần phân biệt thì kiểm loại
TRƯỚC. Không nơi nào được dò chuỗi tiếng Việt trong message để đoán ý nghĩa.

Mỗi đường quét phải biến nó thành thứ người dùng hiểu:

| Đường | Hợp đồng khi mơ hồ |
|---|---|
| kiosk v1 (web) | HTTP 409, `error_code` OP-002/EMP-002, kèm `action` |
| kiosk v2 (ESP) | HTTP 200, `accepted:false`, `AMBIGUOUS_QR`, **không bao giờ RETRY** |
| offline sync | giữ sự kiện, `reason_code` = `AMBIGUOUS_*_QR` |
| API web | HTTP 409 |

Riêng kiosk v2: tem trùng **không** tự hết theo thời gian, nên xếp nó vào
"thử lại đi" là bắt thiết bị quay vòng tới lúc hết lượt trong khi thứ duy nhất
chữa được là người in lại tem.

## Lớp Template

`template_operations.code` và `input_source_code` là **mã trần** — Operation
thật chưa tồn tại lúc soạn Template nên chưa có id để trỏ. Việc giải mã nguồn
thành id thật đi qua một hàm duy nhất, `resolve_template_source()`, và cả chỗ
kiểm lẫn chỗ tạo PO đều gọi đúng hàm đó (trước đây hai chỗ có hai luật khác
nhau, nên thứ được kiểm không phải thứ được tạo):

1. Trong Part của chính nó.
2. Cả Template, khi đúng một Part có mã đó — giữ cho Template cũ trỏ chéo Part.
3. Không có → lỗi.
4. Nhiều Part có mã đó → **lỗi mơ hồ**, không lấy Part đầu tiên.

## Lớp Excel

Cột `operation_id` trong workbook là **mã nghiệp vụ**, không phải `operations.id`
— tên cột đã đi vào file của khách nên không đổi được. Danh tính thật nằm ở
`operation_row_id`, thêm ở cuối. File cũ không có cột đó vẫn nhập được: bộ đọc
map theo tên cột.

Khi có `operation_row_id` thì nó đi trước, nhưng không được tin mù quáng — mã
khác, PO khác, hoặc id không còn tồn tại đều là lỗi tường minh. Import **không**
đổi mã Operation; đổi mã là việc của màn hình quản lý, nơi guard tem đang đứng.

## Lớp offline

Snapshot mang `id` cùng với `code`/`qr`. An toàn với firmware v1 vì
`esp-kiosk/esp/mesflow_app.cpp` phân tích JSON qua một
`DeserializationOption::Filter` liệt kê đích danh khoá nó giữ — khoá lạ bị vứt
ngay trong lúc phân tích. Firmware v2 không đọc snapshot này.

Đường phát lại nhận `operation_id`/`employee_id` khi payload có, và chỉ rơi về
giải theo chuỗi khi không có. Firmware chưa gửi id; server sẵn sàng trước.

---

# Checklist: khi nào được đổi sang `UNIQUE (part_id, code)`

**Mặc định là KHÔNG đổi.** Đổi ràng buộc chỉ để kiến trúc đẹp, trong khi
consumer chưa sẵn sàng, là cách chắc chắn để mất dữ liệu sản xuất. Cái giá của
việc chờ là một quy ước đặt mã hơi dài; cái giá của việc vội là sản lượng ghi
nhầm công đoạn.

Từng mục dưới đây phải TRUE **và có test chứng minh** trước khi bỏ
`operations_code_key`.

| # | Điều kiện | Trạng thái |
|---|---|---|
| 1 | Mọi quan hệ nội bộ đi bằng FK id, không mã | ✅ có test theo `pg_constraint` |
| 2 | Resolver QR từ chối ca mơ hồ ở mọi đường quét | ✅ v1/v2/offline/web đều có test |
| 3 | Đổi mã không làm đứt bảng nào | ✅ ma trận đổi tên |
| 4 | Template giải OP nguồn theo (Part, mã), mơ hồ là lỗi | ✅ |
| 5 | Excel định danh được bằng id thật | ✅ `operation_row_id` |
| 6 | Đối soát dò được ca mơ hồ đang tồn tại | ✅ `audit-integrity` |
| 7 | **Tem mới sinh ra theo id, không theo mã** | ❌ `create()`/`instantiate()` vẫn sinh `WF|OP|<mã>` |
| 8 | **Firmware v1 khớp được tem `WF|OPID|`** | ❌ nó `strcmp` đúng chuỗi với `qr` trong snapshot |
| 9 | **Firmware gửi `operation_id` trong sự kiện offline** | ❌ server nhận rồi, thiết bị chưa gửi |
| 10 | **File Excel của khách đã có `operation_row_id`** | ❌ chỉ file xuất từ bản này trở đi mới có |
| 11 | **Backfill: mọi tem đã in ngoài xưởng đọc được sau khi đổi** | ❌ chưa khảo sát |

Mục 7–9 phải đi **cùng một nhịp**: server sinh tem theo id, snapshot mang tem
theo id, firmware khớp được cả hai dạng. Làm lệch nhịp một bước là kiosk offline
không quét được tem mới in — đúng lúc mất mạng.

Mục 11 là mục duy nhất không giải được bằng code: phải biết ngoài xưởng đang
dán bao nhiêu tem dạng cũ, và có kế hoạch in lại, trước khi mã được phép trùng
nhau. Chừng nào mã còn unique toàn cục thì mọi tem cũ vẫn giải ra duy nhất;
ngày bỏ ràng buộc đó, mọi tem cũ có mã trùng trở thành không quét được cùng lúc.

Đường đi khi đủ điều kiện, theo thứ tự, mỗi bước một release:

1. Sinh tem mới theo id ở mọi đường tạo Operation (mục 7).
2. Firmware nhận cả hai dạng tem + gửi `operation_id` (mục 8, 9).
3. Chiến dịch in lại tem, theo dõi bằng `audit-integrity` (mục 11).
4. Chỉ khi đó: `DROP CONSTRAINT operations_code_key`, thêm
   `UNIQUE (part_id, code)`, và bỏ việc gấp mã trong `operation_code_suffix()`
   cho PO mới. Mã đã gấp của PO cũ vẫn hợp lệ, không cần backfill.

Migration ở bước 4 phải reversible: thêm unique mới TRƯỚC, xác nhận không vi
phạm, rồi mới bỏ cái cũ.
