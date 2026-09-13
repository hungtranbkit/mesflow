# Thư viện bên thứ ba được nhúng kèm

Xưởng chạy máy kiosk trong mạng nội bộ và có lúc mất Internet, nên KHÔNG bao
giờ nạp script từ CDN: thư viện nào cần thì nằm sẵn trong repo, phục vụ từ
chính máy chủ MESFlow.

## jsqr-1.4.0.js

| | |
|---|---|
| Gói | `jsqr@1.4.0` (npm) |
| Giấy phép | Apache-2.0 |
| Nguồn | https://github.com/cozmo/jsQR |
| Tệp gốc | `package/dist/jsQR.js` trong tarball npm |
| Tarball | `https://registry.npmjs.org/jsqr/-/jsqr-1.4.0.tgz` (shasum `8efb8d0a7cc6863cb6d95116b9069123ce9eb2d1`) |
| SHA-256 của tệp này | `bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859` |

Đã đối chiếu: bản trên jsDelivr và bản trong tarball npm GIỐNG NHAU từng byte.

**Vì sao cần.** Safari trên iPhone không có `BarcodeDetector` (Chrome trên iOS
cũng dùng WebKit nên cũng không). Mà iPhone chính là thiết bị đích của Mobile
Kiosk. Không có bộ giải mã QR bằng JavaScript thì camera trên iPhone chỉ hiện
hình chứ không đọc được mã.

**Chỉ nạp khi thật sự cần.** Tệp này nặng ~250 KB, nên nó được nạp ĐỘNG, và chỉ
khi cả hai điều sau đúng: người dùng vừa bật camera, và trình duyệt không có
`BarcodeDetector`. Máy kiosk cố định dùng máy quét USB/GM65 không bao giờ chạm
tới nó. Xem `static/kiosk-camera.js`.

**Cập nhật thế nào.** Tải lại từ tarball npm, đối chiếu SHA-256, cập nhật bảng
trên. Không sửa tay nội dung tệp: nó là bản dựng của thư viện gốc.
