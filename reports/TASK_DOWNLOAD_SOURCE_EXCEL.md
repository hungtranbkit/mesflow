# TASK DOWNLOAD-SOURCE-EXCEL — nút "Tải file Excel gốc" ở Template detail

**Status:** DONE — live TEST 71.0.0.300. Nút "⬇ Tải file Excel gốc" ở Template editor action bar; checksum tải==upload verified live.
**Reported:** user, 2026-09-13. "chưa thấy tính năng download file excel gốc."

## Hiện trạng
- Endpoint đã có + đã kiểm: `GET /api/templates/import-history/<id>/download` (tải nguyên bytes
  + tên file gốc; không generate/recalc/QR). Danh sách: `GET /api/templates/<tid>/import-history`.
- UI đã có LINK per-import "Tải file" trong bảng lịch sử nhập (`app.js` loadTemplateImportHistory),
  dùng đúng `x.id` (không hardcode). NHƯNG bị chôn trong bảng con -> user không thấy.

## Việc
- Thêm nút tiếng Việt **"Tải file Excel gốc"** DỄ THẤY ở thanh hành động Template detail
  (cạnh Lưu/Xóa), tách riêng với "Xuất Excel + QR".
- Click -> resolve import_id THẬT của Template đang chọn = lần nhập THÀNH CÔNG (outcome≠FAILED)
  GẦN NHẤT (KHÔNG hardcode 18), tải qua endpoint trên. Không có nguồn -> toast
  "Chưa có file Excel gốc", không nút chết.
- Giữ bảng lịch sử nhập hiển thị rõ file/lần nhập/kết quả per row (đã có).
- Tải nguyên file đã upload, không đụng QR/recalc. Giữ quyền (admin/manager) như endpoint.

## Kiểm
- Click nút -> trình duyệt tải đúng file; SHA khớp nguồn của Template.
- Deploy TEST (theo ủy quyền hotfix), báo nút nằm đâu + version live.

## Ghi chú phối hợp
- KHÔNG deploy nhánh chứa regression import298. Làm SAU hotfix Err522 (đã live 71.0.0.299).
