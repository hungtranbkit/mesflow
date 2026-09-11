# visual-ui-audit — soát giao diện bằng mắt, có kỷ luật

**Dùng khi**: bất kỳ thay đổi nào chạm CSS, layout, hay cấu trúc DOM của
`app/mesflow/web/` — kể cả khi test hiện có đã xanh.

**Không dùng khi**: chỉ đổi chuỗi hiển thị, logic nghiệp vụ, hay backend không
đụng tới render.

---

## Vì sao skill này tồn tại

MESFlow đã qua **nhiều đợt audit UI thủ công** mà list/card giữa các màn vẫn
lệch nhau. Nguyên nhân không phải người làm ẩu. Mỗi lần đều là một lỗi mà
**test tự động không thể thấy, còn mắt người thấy ngay**:

| Sự cố có thật | Vì sao test bỏ sót |
|---|---|
| `.op-list-head` góc vuông chọc ra khỏi góc tròn của `.op-list` bao nó | Cả hai đều dùng token hợp lệ. Không có assertion nào so **góc trong với góc ngoài**. |
| Rule quét ép mọi thẻ về 7px trong khi CSS tại chỗ viết 12–14px | CSS "đúng cú pháp", token "đúng tên". Chênh lệch chỉ hiện ra **trên màn hình**. |
| `.mf-tabs{display:flex}` ghi đè `[hidden]`, bộ lọc lẽ ra ẩn thì luôn hiện | Spec `exception-center-mobile` lấy chính phần tử lỗi làm mốc → **hai lỗi bù nhau, test xanh**. |
| Trung tâm ngoại lệ trên 390px: 5 tab xếp thành cột cao 255px, nội dung chính nằm ở 876px | Mọi phần tử đều tồn tại, đều hiển thị, đều đúng token. Chỉ **bố cục** là sai. |

Điểm chung: **token đúng, DOM đúng, mắt sai.** Đó là khoảng trống skill này lấp.

Hệ quả thứ hai, đắt hơn: khi một bộ dò không bao giờ đỏ, nó **trông y hệt một hệ
thống sạch**. Trong dự án này đã gặp ba lần (điều kiện bất khả thi do ràng buộc
DB cấm; nhánh `CASE` chết; bài test im lặng khi token biến mất). Nên mọi guard
viết ra theo skill này **phải được chứng minh là biết đỏ** — xem bước 5.

---

## Pipeline — năm bước, theo thứ tự, không bỏ bước

### 1. Computed style audit (máy đọc)

Đọc `getComputedStyle` trên **phần tử thật trong trang đã tải**, không phải đọc
file CSS. File CSS nói ý định; computed style nói kết quả — và cả loạt lỗi ở
bảng trên chính là chỗ hai thứ đó khác nhau.

```bash
docker compose -f compose.test.yml -p <project> run --rm playwright \
  npx playwright test tests/e2e/visual-contract.spec.js --reporter=line
```

Bắt buộc kiểm, mỗi mục là một assertion riêng để thông báo nói đúng chỗ hỏng:

- **`gap`/`margin` giữa các item của một card-list > 0** — thẻ dính nhau thành
  một khối là lỗi hay gặp nhất khi ai đó gỡ `gap` để "cho gọn".
- **`border-radius` giải ra được thành px**, không phải chuỗi rỗng. Trỏ tới
  token đã bị xoá làm cả khai báo thành không hợp lệ, và CSS **không báo gì**.
- **`border` / `background` / `box-shadow` / `padding`** lấy từ token, không
  phải số viết cứng.
- **Không tràn**: `scrollWidth <= clientWidth + 1` cho mọi container ngang, và
  con không vượt biên cha.

### 2. Screenshot ở bốn viewport

`390` (điện thoại) · `768` (tablet) · `1366` (desktop chính của dự án, xem
REQ-UI-005) · `1920`.

Lưu vào `test-results/visual-audit/<màn>-<viewport>.png`, và **khẳng định kích
thước ảnh** — một ảnh 0 byte hay sai bề rộng nghĩa là bước chụp hỏng, và mọi
kết luận sau đó vô giá trị.

### 3. Agent PHẢI tự mở ảnh ra xem

**Đây là bước hay bị bỏ nhất, và bỏ nó là bỏ toàn bộ giá trị của skill.**

Lưu file rồi báo "đã chụp 12 ảnh" **không phải** là audit. Phải dùng công cụ
đọc ảnh, nhìn từng ảnh, và viết ra bằng lời mình thấy gì. Những lỗi ở bảng đầu
trang **không có assertion nào bắt được**; chúng chỉ lộ ra khi có người nhìn.

Nhìn theo thứ tự này, ghi lại từng mục:

1. Các thẻ trong một danh sách có **tách khối** rõ không, hay dính thành mảng?
2. Góc bo có **cùng một bậc** giữa các thẻ cùng loại không?
3. Chữ có bị **cắt / chồng / co về một cột hẹp** không?
4. Con có **tràn ra ngoài** cha không?
5. Ở 390px, card-list có bị biến thành **bảng liền mạch** không?
6. Dải tab có bị **ép xuống nhiều dòng / chồng lên nhau** không?
7. Timeline/gantt có **nhãn đè lên nhau** không?
8. Hành động (nút, menu) có **nằm đúng bên phải** và không bị cắt không?

### 4. Visual contract theo HỌ component

Không so "màn A với màn B". So **họ**: cùng một họ thì phải cùng một mặt, khác
họ thì được khác — và sự khác đó phải do **ngữ nghĩa**, không do màn hình.

| Họ | Hợp đồng |
|---|---|
| card-list item | `--radius-surface`, `gap > 0`, viền nhẹ, bóng nhẹ, nền sáng |
| khối lồng trong surface | `--radius-surface-row`, inset bằng thụt lề hoặc `border-left` |
| bảng dữ liệu dày | row **được phép phẳng**; vỏ ngoài **phải** `--radius-surface` |
| điều khiển (input/select/nút) | `--radius-control` |
| lớp phủ (modal/sheet/dropdown) | `--radius-overlay` |

Cùng một họ list ở **Dashboard / Template / Exception Center / Session / QR /
Admin** phải dùng **cùng primitive**. Nếu một màn phải khác, ghi lý do vào
danh sách ngoại lệ của guard — việc phải sửa test là **điểm dừng để cân nhắc**,
không phải thủ tục.

Chi tiết đầy đủ: `docs/MESFLOW_MASTER_REQUIREMENTS_VI.md` REQ-UI-013/014/015.

### 5. Negative proof

Một guard chưa từng đỏ thì chưa chứng minh được điều gì. Sau khi viết guard:

1. Cố ý phá đúng thứ nó canh (đổi một token về giá trị sai, gỡ `gap`, trả một
   selector về số cứng).
2. Chạy — **phải đỏ**, và thông báo phải nói đúng tên selector/token.
3. Hoàn nguyên — phải xanh lại.

Ghi cả ba bước vào commit message. Không có bước này thì guard chỉ là một dòng
xanh vô nghĩa.

---

## Checklist bắt buộc

Đánh dấu từng mục, không bỏ qua im lặng. Mục nào không áp dụng thì ghi **lý do**.

- [ ] Item của card-list **không dính nhau** (`gap`/`margin` > 0) khi họ là card-list
- [ ] `border-radius`, khoảng cách dọc, `padding`, `border`, `background`,
      `box-shadow` đều **lấy từ token**
- [ ] Chữ **không** chồng / bị cắt / co sập
- [ ] Con **không** tràn ra ngoài cha
- [ ] Ở mobile, card-list **không** biến thành bảng liền mạch
- [ ] Dải tab **không** bị ép hay chồng lên nhau
- [ ] Timeline/gantt **không** có nhãn đè nhau
- [ ] Cùng họ list ở Dashboard/Template/Exception/Session/QR/Admin dùng **cùng primitive**
- [ ] Vỏ ngoài bảng **có** bo góc; row bên trong **chỉ** bo nếu họ đó yêu cầu
- [ ] **Không** px viết cứng ngoài token
- [ ] Đã **tự mở từng ảnh ra xem** (bước 3), không chỉ lưu file
- [ ] Guard mới có **negative proof**

---

## Quy trình QA cho một thay đổi UI

```
functional  ->  DOM/style contract  ->  responsive screenshot audit  ->  visual review  ->  merge
```

Không bước nào được nhảy cóc, kể cả khi thay đổi "chỉ là CSS" — ba trong bốn sự
cố ở đầu trang đều là "chỉ là CSS".

---

## Bẫy đã biết trong repo này

- **`waitForTimeout` cố định gây đỏ giả** dưới `--retries=0` khi chạy cả suite
  (đỏ khi chạy chung, xanh khi chạy riêng). Dùng `expect(...).toBeVisible()`
  hoặc `waitForFunction`, đừng ngủ theo đồng hồ.
- **`%` trong `LIKE` của câu SQL có tham số** bị psycopg đọc thành placeholder và
  từ chối cả câu. Dùng `left()`/`strpos()` khi biểu thức được nhúng vào câu có
  tham số.
- **Test lấy phần tử lỗi làm mốc**: khi sửa lỗi đó, test sẽ đỏ — và cái đỏ ấy
  **đúng**. Đừng phân loại nhầm thành "bản vá làm hỏng test".
- **`loading="lazy"` làm hỏng chính phép chụp.** Playwright `fullPage: true`
  ghép ảnh chứ không thật sự cuộn qua từng đoạn, nên ảnh lazy nằm dưới màn hình
  đầu tiên chưa kịp tải. Lần chạy đầu của bộ test này chụp màn "In tem QR" ở
  390px ra **10 thẻ có mã QR và 16 thẻ trống trơn** — trông y hệt một lỗi sinh
  ảnh hàng loạt. Nó là giả tượng, và nguy hiểm theo **cả hai hướng**: báo nhầm
  lỗi không có, rồi dạy người soi quen bỏ qua ô trắng nên lần có ô trắng THẬT
  cũng bị bỏ qua. `settleLazyImages()` trong `tests/e2e/visual-contract.spec.js`
  cuộn hết trang và chờ mọi `document.images` xong trước khi chụp — dùng lại nó,
  đừng viết lại.
