# Mobile Kiosk — quét QR bằng camera điện thoại

Trang kiosk quen thuộc (`/kiosk`), mở trên điện thoại, dùng camera thay cho máy
quét USB. **Luồng nghiệp vụ không đổi**: quét thẻ nhân viên → quét công đoạn →
Bắt đầu / Kết thúc → nhập sản lượng. Cùng API, cùng session, cùng luật.

Máy kiosk cố định với máy quét USB/GM65 và thiết bị ESP v2 **không bị đụng tới**.

---

## 1. Năm bước để thử trên iPhone

Cần hai màn hình: điện thoại để quét, và một máy tính đã đăng nhập để HIỆN mã QR.
(Nếu xưởng đã in tem QR thì bỏ qua máy tính, quét thẳng trên tem.)

1. **Máy tính** — đăng nhập MESFlow, mở `https://mesflow.net/app?page=qr-print`.
   Chọn loại **Nhân viên**, tìm một nhân viên đang hoạt động → màn hình hiện mã
   QR của thẻ. Để nguyên đó.
2. **iPhone** — mở **Safari**, vào `https://mesflow.net/kiosk`.
   Phải là `https://`; camera không chạy trên `http://`.
3. Bấm **“Camera điện thoại”** ở góc trên bên phải → Safari hỏi quyền → chọn
   **Cho phép**. Camera sau của máy sẽ mở ra, có khung vuông ở giữa.
4. Đưa khung vuông vào mã QR **nhân viên** trên màn hình máy tính. Khung nháy
   xanh + có tiếng bíp là đã đọc được; màn hình chuyển sang **QUÉT CÔNG ĐOẠN**.
   Trên máy tính, đổi loại QR sang **Operation**, chọn một công đoạn thuộc PO
   đang chạy, rồi quét tiếp.
5. Máy báo **ĐÃ BẮT ĐẦU**. Muốn kết thúc thì quét lại **thẻ nhân viên** đó — màn
   nhập sản lượng hiện ra kèm **bàn phím số lớn**; nhập Đạt / Lỗi / Lỗi sửa được
   rồi **XÁC NHẬN**.

> **Chỉ dùng dữ liệu TEST.** Mọi thao tác ở trên ghi vào cơ sở dữ liệu của môi
> trường đang mở. Hãy chọn nhân viên và PO của môi trường TEST, không dùng dữ
> liệu thật.

**Thêm vào màn hình chính (tuỳ chọn).** Safari → nút Chia sẻ → *Thêm vào MH
chính*. Mở từ biểu tượng đó sẽ chạy toàn màn hình, không có thanh địa chỉ.

---

## 2. Khi có trục trặc

| Hiện tượng | Nguyên nhân và cách xử lý |
|---|---|
| Không thấy nút “Camera điện thoại” | Trang đang mở bằng `http://`, hoặc trình duyệt không hỗ trợ camera. Mở lại bằng `https://`. Nút được ẩn có chủ đích: một nút bấm vào là báo lỗi thì thà đừng có. |
| “Bạn đã từ chối quyền camera…” | iPhone: **Cài đặt › Safari › Camera › Hỏi** (hoặc Cho phép), rồi tải lại trang. |
| “Camera đang được ứng dụng khác sử dụng” | Đóng app đang giữ camera (Camera, Zoom, FaceTime…) rồi bật lại. |
| Camera mở nhưng không đọc được mã | Đưa gần hơn cho mã chiếm khoảng nửa khung; tránh chói và bóng màn hình; lau ống kính. Mã in mờ hoặc nhàu thì in lại. |
| Quét một lần mà chạy hai lần | Không xảy ra: cùng một mã bị chặn trong 1,8 giây. Mã **khác** thì được nhận ngay. |
| “Mất kết nối mạng — chưa gửi được mã” | Điện thoại rớt Wi-Fi. Hệ thống **không** tự gửi lại và **không** xếp hàng chờ (xem mục 4). Có mạng lại thì quét lại. |
| Quét xong không thấy tên, phải tắt camera mới thấy | **Đã sửa từ 71.0.0.308.** Kể từ bản đó, ngay sau mỗi lần quét một thẻ kết quả hiện lên chính lớp camera (`Đã quét: …`, tên, bước tiếp theo) và camera vẫn mở. Nếu vẫn phải tắt camera mới thấy thì tab đang chạy bản cũ — chờ ~30 giây để kiosk tự nạp lại, hoặc kéo xuống để tải lại trang. |
| Quét thành công mà không nghe tiếng nào | Kiểm tra công tắc gạt Chuông/Im lặng ở cạnh iPhone và mức âm lượng. iOS chỉ cho phát tiếng sau khi người dùng **chạm**, nên tiếng bíp chỉ hoạt động từ lần bấm “Camera điện thoại” trở đi — nếu chưa từng bấm nút đó trong lần mở trang này thì chưa có tiếng. |

---

## 3. Giới hạn đã biết trên iOS

Không phải lỗi — là giới hạn của WebKit, và đã được tính từ đầu:

- **Không có `BarcodeDetector`.** Mọi trình duyệt trên iOS đều là WebKit, nên
  việc giải mã do thư viện JavaScript (`jsQR`) làm. Thư viện chỉ được tải khi bật
  camera, lần đầu mất thêm khoảng một giây.
- **Không rung.** `navigator.vibrate` không có trên iOS. Báo đã đọc được mã dựa
  vào **khung nháy xanh** và **tiếng bíp**.
- **Tiếng bíp cần một cú chạm.** iOS chỉ cho phát âm thanh sau một thao tác của
  người dùng; cú chạm bật camera chính là thao tác đó. Máy đang ở chế độ im lặng
  thì không có tiếng.
- **Không chạy nền.** Chuyển sang app khác hoặc khoá máy là camera tắt; quay lại
  trang thì tự mở lại.
- **Bắt buộc HTTPS.**

---

## 4. Mất mạng: vì sao KHÔNG xếp hàng chờ gửi

Quyết định có chủ đích của V1.

Một lần **quét** chỉ là tra cứu, gửi lại bao nhiêu lần cũng vô hại — nên không có
gì để xếp hàng. **Bắt đầu / Kết thúc** thì máy chủ đã chống trùng thật (bảng
`kiosk_idempotency`, khoá theo `request_id`), nên gửi lại **không** tạo hai bản
ghi.

Nhưng “không tạo hai bản ghi” chưa phải là “đúng”. Một lệnh *Bắt đầu* bị giữ
trong hàng đợi rồi bắn đi mười lăm phút sau vẫn tạo ra một session có **giờ bắt
đầu sai** — dữ liệu sai mà không ai biết, tệ hơn hẳn một lỗi hiện ra trên màn
hình để người đứng máy xử lý ngay.

Vì vậy V1: mất mạng thì **nói thẳng**, không giữ, không tự gửi. Có mạng lại thì
quét lại. Một hàng đợi ngoại tuyến đúng nghĩa cần dấu thời gian do thiết bị ghi
và máy chủ chấp nhận giờ đó — đó là việc riêng, không phải việc của V1.

---

## 5. Ghi chú kỹ thuật

- **Camera là NGUỒN QUÉT, không phải kiosk thứ hai.** `static/kiosk-camera.js`
  giải mã rồi phát sự kiện `kiosk:camera-scan`; `kiosk.js` đưa chuỗi đó vào đúng
  `scan()` mà máy quét USB dùng, tức vẫn đi qua `/api/kiosk-web/scan`. Module
  camera không gọi API nào và không biết luật nghiệp vụ nào.
- **Kết quả quét đi NGƯỢC lại cũng bằng sự kiện.** `kiosk.js` phát
  `kiosk:scan-result` mang đúng nội dung màn bên dưới đang hiện (loại mã, tên,
  bước tiếp theo); lớp camera nghe và vẽ thẻ kết quả. Ranh giới giữ nguyên cả
  hai chiều: camera không hỏi máy chủ, `kiosk.js` không biết có lớp camera.
- **Thẻ kết quả không thể che vùng ngắm QR.** Nó là một phần tử flex
  (`order:-1`) chứ không phải lớp phủ tuyệt đối — flex không cho hai phần tử
  chiếm cùng một chỗ. Bài kiểm đo diện tích giao nhau = 0 ở cả 390×844 và
  844×390.
- **Tiếng bíp trên iOS.** `AudioContext` được tạo VÀ phát một đoạn đệm 1 mẫu im
  lặng ngay trong cú chạm nút camera — `resume()` một mình không đủ để WebKit mở
  khoá. Tiếng thành công cao (1180 Hz, ~0,12 s), tiếng lỗi thấp và đôi (300 và
  220 Hz): khác CAO ĐỘ chứ không khác to/nhỏ, vì tai đeo chống ồn chỉ phân biệt
  được cao/thấp. Tiếng chỉ kêu sau khi máy chủ đã trả lời, không kêu lúc vừa
  giải mã.
- **Không có khung hình nào rời khỏi máy.** Chỉ chuỗi đã giải mã được gửi đi.
- **Không có service worker**, để không đánh nhau với cơ chế tự nạp lại theo
  phiên bản của kiosk.
- **Thư viện nhúng kèm**: `static/vendor/jsqr-1.4.0.js` (Apache-2.0) — nguồn gốc
  và SHA-256 ở `static/vendor/README.md`.
- Hợp đồng đầy đủ: **REQ-KIOSK-016** trong `docs/MESFLOW_MASTER_REQUIREMENTS_VI.md`.
