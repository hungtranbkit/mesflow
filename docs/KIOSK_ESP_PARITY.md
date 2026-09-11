# Kiosk web ↔ ESP v2 — bảng đối chiếu state / màn hình / phím

Nguồn đối chiếu: `esp-kiosk/esp/mesflow_app.cpp` (firmware v5.3.x — repo
`/home/dell/workspace/mesflow/esp-kiosk`, KHÔNG nằm trong repo này). Mọi dòng
dưới đây đọc từ mã firmware, không suy ra từ ảnh chụp màn hình.

Neo trong firmware:

| Thứ | Vị trí |
|---|---|
| `enum class UiState` | `mesflow_app.cpp:382` |
| Chuyển state theo số nhập | `handleSerialLine`, `mesflow_app.cpp:5321-5375` |
| Phím bàn phím | `handleKeypadKey`, `mesflow_app.cpp:5904-5981` |
| Màn "CÓ LỖI SỬA ĐƯỢC?" | `drawAskRework`, `mesflow_app.cpp` |
| Về màn chờ thẻ sau khi xong | `resetForNextWorker` → `setUi(UiState::READY)` |
| Vẽ hai nút hành động dưới màn | `drawFooterTwoActions(left, right)`, `mesflow_app.cpp:1386` |

---

## 1. Luồng kết thúc session — trạng thái

| ESP v2 `UiState` | Màn hình web (`#screen-*`) | Điều kiện rời state |
|---|---|---|
| `INPUT_GOOD` — "SẢN PHẨM ĐẠT" | `quantity-good` | nhập số → `INPUT_DEFECT` |
| `INPUT_DEFECT` — "SẢN PHẨM LỖI" | `quantity-defect` | **NG = 0** → bỏ qua hỏi, `rework=0`, sang xác nhận · **NG > 0** → `ASK_REWORK` |
| `ASK_REWORK` — "CÓ LỖI SỬA ĐƯỢC?" | `ask-rework` | xem bảng phím §2 |
| `INPUT_REWORK` — "LỖI SỬA ĐƯỢC" | `quantity-rework` | hợp lệ → xác nhận; không hợp lệ → ở lại |
| `CONFIRM_QTY` — "XÁC NHẬN" | `finish-confirm` | xác nhận → gửi; quay lại → màn trước |
| `FINISH_SUCCESS` | `finished` | tự động về màn chờ thẻ sau vài giây |
| `READY` — chờ quét thẻ | `ready` | — |

**NG = 0 bỏ qua `ASK_REWORK`**: firmware làm đúng như vậy
(`mesflow_app.cpp:5327-5336`), web cũng vậy. Không có bước vô nghĩa nào.

---

## 2. Phím — và chỗ web CỐ Ý khác firmware

## 2.0 Vị trí nút trên màn hình — `*` bên TRÁI, `#` bên PHẢI

Đây là phần **bố cục**, tách khỏi phần ngữ nghĩa phím ở §2.1–2.3. Người đứng
máy dùng bàn phím cứng và nhớ **vị trí**, không đọc lại chữ mỗi lần bấm; hai
thiết bị đảo chỗ hai nút là mời bấm nhầm.

Firmware chỉ có **một** đường vẽ hàng nút: `drawFooterTwoActions(left, right)`
(`mesflow_app.cpp:1386`) — vẽ `left` vào nửa trái, `right` vào nửa phải. Mọi
lời gọi trong firmware đều theo đúng một khuôn:

| Màn ESP | Trái | Phải |
|---|---|---|
| `WAIT_OPERATION` | `* HỦY` | — |
| bắt đầu công đoạn | `* QUAY LẠI` | `# BẮT ĐẦU` |
| kết thúc công đoạn | `* HỦY` | `# KẾT THÚC` |
| nhập số (`drawQtyInput`) | `* XÓA` | `# TIẾP` |
| `ASK_REWORK` | `* QUAY LẠI` | — |
| `CONFIRM_QTY` | `* QUAY LẠI` | `# XÁC NHẬN` |
| `FINISH_RETRY` | `* QUAY LẠI` | `# THỬ LẠI` |

**Quy tắc rút ra: ô "lùi/huỷ" luôn bên trái, ô "tiến/xác nhận" luôn bên phải.
Không có ngoại lệ nào trong firmware.**

Kiosk web phải theo đúng quy tắc đó trên **mọi** màn nhập liệu. Cách khoá
trong web không dựa vào thứ tự DOM (thứ tự DOM từng xếp ngược đúng ở màn
`XÁC NHẬN`), mà dựa vào **slot**:

| Attribute | Ý nghĩa | CSS |
|---|---|---|
| `data-action-slot="back"` | ô lùi/huỷ | `order:1` → luôn bên trái |
| `data-action-slot="confirm"` | ô tiến/xác nhận (`#`) | `order:2` → luôn bên phải |

Áp cho cả hai primitive bố cục đang dùng: `.actions` (các màn nhập số) và
`.choice-grid` (màn hỏi lỗi sửa được, màn xác nhận) — nên thêm màn mới cũng
không phải nhớ lại quy tắc, chỉ cần gắn đúng slot.

> **Từng sai ở đâu**: `#screen-finish-confirm` xếp `#finish-confirm-ok`
> (`# XÁC NHẬN`) TRƯỚC `#finish-confirm-edit` (`* QUAY LẠI`) trong markup, mà
> `.choice-grid` đặt phần tử theo đúng thứ tự DOM → web hiện `#` bên trái,
> ngược hẳn ESP. Sửa bằng cách đổi thứ tự DOM **và** gắn slot; bài test đo toạ
> độ thật (`tests/e2e/kiosk-esp-parity.spec.js`, nhóm "Ô XÁC NHẬN nằm bên
> phải") đỏ ngay nếu ai xếp ngược lại, kể cả khi markup trông vẫn hợp lý.

**Chỗ web còn khác về bố cục** (có chủ ý, không phải nợ):

| Chỗ | ESP | Web | Lý do |
|---|---|---|---|
| nhãn `*`/`#` ở màn nhập số | in ngay trên footer | nút ghi `QUAY LẠI` / `TIẾP TỤC`, không in ký tự | web có chuột/cảm ứng nên nhãn chữ đọc nhanh hơn ký tự; vị trí vẫn đúng quy tắc |
| `*` ở màn `SẢN PHẨM ĐẠT` | `XÓA` (xoá lùi) | **chưa gán phím** — nút `HỦY` chỉ bấm được | màn đầu luồng không có màn trước để quay lại; xoá lùi đã có `Backspace` (§2.1). Nút `HỦY` vẫn nằm đúng ô trái. |
| `ASK_REWORK` | hai dòng option dọc | hai nút cạnh nhau | màn web rộng hơn nhiều; ô "tiếp tục" (`#`) vẫn nằm bên phải |

---


### 2.1 Màn nhập số (đạt / lỗi / lỗi sửa được)

| Phím | ESP v2 | Web Kiosk | Khớp |
|---|---|---|---|
| `0`–`9` | nhập chữ số | ô `<input type=number>` | ✅ |
| `*` | xoá lùi một chữ số | quay lại màn trước | ⚠️ khác |
| `#` | xác nhận giá trị đang nhập | xác nhận → màn kế tiếp | ✅ |
| `Enter` | (bàn phím ESP không có) | như `#` | ➕ web thêm |

`*`: bàn phím vật lý của ESP không có phím xoá nào khác nên `*` phải là
backspace. Bàn phím web có sẵn Backspace/Delete cho việc đó, nên `*` được dùng
cho chức năng mà web thiếu hơn: quay lại màn trước. Ý nghĩa "huỷ bước hiện tại"
vẫn giữ.

### 2.2 Màn "CÓ LỖI SỬA ĐƯỢC?" — **khác biệt lớn nhất**

| Phím | ESP v2 (firmware hiện tại) | Web Kiosk (desired UX đã chốt) |
|---|---|---|
| `1` | **KHÔNG, XONG** → `rework=0`, sang xác nhận | **CÓ, NHẬP SỐ** → sang màn nhập |
| `2` | **CÓ, NHẬP SỐ** → sang `INPUT_REWORK` | **TIẾP TỤC, KHÔNG CÓ** → `rework=0` |
| `#` | không gán (chỉ ghi log nhắc) | tiếp tục, không nhập |
| `Enter` | — | như `#` |
| `*` | quay lại `INPUT_DEFECT` | quay lại `quantity-defect` ✅ |

> **Hai phím 1 và 2 đang ĐẢO NHAU giữa hai thiết bị.**
>
> Firmware: `drawAskRework()` vẽ `1 KHÔNG, XONG` / `2 CÓ, NHẬP SỐ`, và
> `handleKeypadKey` ghi log `"Chon 1 KHONG hoac 2 CO LOI SUA DUOC"`.
>
> Chủ sản phẩm đã chốt desired UX là `1 = Có`, `2/# = Tiếp tục`, và yêu cầu
> **không copy mù firmware**. Web làm theo desired UX; firmware **chưa** đổi
> trong lane này.
>
> **Rủi ro vận hành khi hai thiết bị còn lệch**: một người quen bấm `1` trên
> ESP để nói "không có lỗi sửa được", khi sang web bấm `1` sẽ mở màn nhập số.
> Không mất dữ liệu (còn màn xác nhận ở sau), nhưng gây bấm nhầm.
>
> **Đề xuất cho firmware** (chưa làm, cần quyết định riêng): đổi `drawAskRework`
> thành `1 CÓ, NHẬP SỐ` / `2 TIẾP TỤC` và đảo hai nhánh trong `handleSerialLine`.
> Backward-compatible với thiết bị cũ: ASK_REWORK là màn hình cục bộ, không có
> giao thức nào giữa thiết bị và server phụ thuộc vào việc phím nào là "có" —
> payload gửi đi vẫn là `rework_qty` đã chốt. Nên đổi firmware chỉ ảnh hưởng
> người đứng trước máy, không ảnh hưởng server hay thiết bị chưa cập nhật.

### 2.3 Màn xác nhận

| Phím | ESP v2 | Web Kiosk | Khớp |
|---|---|---|---|
| `1` hoặc `#` | gửi | gửi | ✅ |
| `2` hoặc `*` | quay lại (`INPUT_REWORK` nếu `rework>0`, không thì `INPUT_DEFECT`) | như vậy | ✅ |
| `Enter` | — | như `#` | ➕ web thêm |

---

## 3. Khoảng hợp lệ của "lỗi sửa được"

| | ESP v2 | Web Kiosk |
|---|---|---|
| Chặn trên | `rework > defect` → từ chối, ở lại màn | như vậy ✅ |
| Chặn dưới | `rework <= 0` → **từ chối** | **chấp nhận 0** ⚠️ |

Web nhận `0..NG` theo yêu cầu đã chốt. Lý do nghiệp vụ: người vừa bấm "CÓ" rồi
nhận ra không có cái nào sửa được thì phải đi tiếp được; ở ESP họ phải bấm `*`
quay lại rồi chọn lại. Nhập `0` cho kết quả **giống hệt** chọn "tiếp tục" —
bảng xác nhận không hiện dòng "Sửa được 0 / Phế = NG".

Chặn trên còn được lặp lại ở **server**: `WorkSessionRepository._finish_within`
ném `ValueError('rework_qty cannot exceed defect_qty')`. Giao diện chỉ là lớp
đầu; dữ liệu sai không vào được DB kể cả khi gọi thẳng API.

---

## 4. Sản lượng — không cộng nhầm, không đếm hai lần

`POST /api/kiosk-web/finish/<session_id>` gửi ba số **tách bạch**:
`good_qty`, `defect_qty`, `rework_qty` (`app/mesflow/web/kiosk.py`).

`rework_qty` nghĩa là **"trong số NG này, bao nhiêu cái có thể sửa"** — nó đi
vào **hàng chờ sửa**, KHÔNG được cộng vào `good_qty` tại thời điểm khai báo.
Số sửa được chỉ credit về sản lượng đạt của OP nguồn **sau khi** có người thật
sự sửa xong và ghi nhận qua `ReworkQueueRepository.resolve()` — chính đường đó
mới tăng `good_qty` và ghi `rework_ledger`.

Nếu giao diện tự cộng `rework` vào `good` lúc kết thúc session thì cùng một sản
phẩm được tính đạt hai lần: một lần ở đây, một lần khi resolve. Web **không**
làm vậy; màn xác nhận hiện `Đạt / NG tổng / Sửa được / Phế` như bốn số riêng.

---

## 5. Sau khi gửi xong

| | ESP v2 | Web Kiosk |
|---|---|---|
| Màn hình sau khi gửi | `FINISH_SUCCESS`, giữ vài giây | `finished`, giữ 3 giây |
| Sau đó | `resetForNextWorker()` → `clearRuntimeSelection()` → `READY` | `reset()` → xoá employee/session/input → `ready` |

Cả hai **không đứng lại ở màn kết quả**. Web `reset()` xoá `employee`,
`openSession`, `pendingFinish`, cả ba ô số và mọi dòng lỗi trước khi về `ready`
— không có state cũ nào sống sót sang người tiếp theo.

---

## 5b. Gửi thất bại — tự thử lại hay để người bấm?

| | ESP v2 | Kiosk web |
|---|---|---|
| Lỗi **tạm thời** | giữ giao dịch ở dạng *pending* và **tự gửi lại nền** mỗi `PENDING_RETRY_MS = 10s` (`mesflow_app.cpp:6136`), không phiền người đứng máy | lớp mạng tự thử lại (lane network-resilience) |
| Lỗi **dai dẳng** | màn `FINISH_RETRY` — "CHƯA GỬI ĐƯỢC", `#` thử lại, `*` quay lại | ô lỗi "CHƯA GỬI ĐƯỢC" + nút Thử lại |

Nói cách khác, ESP **luôn** làm cả hai: tự chữa lỗi chớp nhoáng, và chỉ gọi
người khi thật sự không đi tiếp được. Nút thủ công ở web vì thế có nghĩa đúng
như `FINISH_RETRY`: dành cho lỗi dai dẳng, không phải cho mọi lỗi.

An toàn của việc tự thử lại nằm ở `request_id`: nó sinh **một lần** khi vào
luồng (`kiosk.js`), không sinh lại mỗi lần gửi, nên mọi lần thử lại mang cùng
một id và backend khử trùng qua `kiosk_idempotency`. Có bài test khoá đúng
điều này; đổi sang sinh id mỗi lần gửi là bài test đỏ ngay.

---

## 6. Tóm tắt khác biệt

| # | Chỗ khác | Bên nào | Lý do |
|---|---|---|---|
| 1 | `1`/`2` ở màn hỏi lỗi sửa được đảo nhau | firmware khác desired | chủ sản phẩm chốt desired UX; firmware chưa đổi — xem đề xuất §2.2 |
| 2 | `#`/`Enter` = tiếp tục ở màn hỏi | web thêm | ESP để trống phím này, nên thêm không đụng gì |
| 3 | `rework = 0` được chấp nhận | web rộng hơn | tránh kẹt màn hình; kết quả giống "tiếp tục" |
| 4 | `*` = quay lại thay vì xoá lùi ở màn nhập số | web khác | bàn phím web đã có Backspace |
| 5 | `Enter` ở mọi màn | web thêm | bàn phím web có, bàn phím ESP không |
| 6 | `*` chưa gán ở màn `SẢN PHẨM ĐẠT` | web hẹp hơn | không có màn trước để quay lại; xem §2.0 |

Khác biệt 2–5 là **web rộng hơn** ở chỗ ESP không dùng tới, không đổi ngữ nghĩa.
Chỉ khác biệt **1** là hai thiết bị nói ngược nhau và cần quyết định về firmware.
