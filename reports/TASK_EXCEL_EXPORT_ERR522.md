# TASK EXCEL-EXPORT-ERR522 — exported router .xlsx shows Err:522 in many cells

**Status:** DONE — live TEST 71.0.0.300 (commit e2162be5d9b3). LibreOffice: 0 error cells on real PO6126 export (was 1199).
Branch `integration/qr-missing-marker-warn` (live-297 base + 298 QR-warn + this fix).

## ROOT CAUSE (confirmed with LibreOffice + raw XML on the real PO 6126 file)
- Export cũ: openpyxl `load_workbook(...)` + `wb.save()`. openpyxl khi save **XOÁ
  cached `<v>`** của mọi ô công thức (đo: export 0/135 cached; nguồn 34/34) và ghi
  `<calcPr fullCalcOnLoad="1" iterate="0" ...>` (nguồn chỉ `calcId`). => mở file =
  **ép full recalc, iterative TẮT**.
- Biểu mẫu NEWARK có sẵn **84 ô công thức tự tham chiếu** (vd `A14=$A$14`, nhãn
  block-2+ `=$A$9`). Vô hại khi có cached value + không recalc (Excel/LO hiện giá
  trị cache). Ép recalc với iterate=0 => **Err:522 vòng tham chiếu** (LibreOffice
  đếm **1199 ô lỗi** trên export cũ; **0** trên file nguồn).
- => Không phải lỗi QR, không phải lỗi template. Là openpyxl reserialize phá calc
  fidelity. Self-ref là dữ liệu của khách -> KHÔNG sửa.

## FIX (đúng hướng user chốt: giữ nguyên file input, chỉ chèn QR)
`_compute_qr_placements()` chỉ ĐỌC workbook để đo hình học (không save).
`_graft_qr_into_workbook()` vá OOXML tối thiểu trên **bytes gốc**: thêm PNG vào
`xl/media`, nối `<xdr:oneCellAnchor>` vào drawing của sheet (dùng drawing sẵn có
hoặc tạo mới), thêm image rels + content-type khi cần. KHÔNG load/save openpyxl,
KHÔNG xoá text QRCODE, KHÔNG đụng cell/formula/cache/format/layout.

## EVIDENCE (real PO 6126 source, LibreOffice recalc)
| file | LibreOffice error cells |
|---|---|
| nguồn khách | 0 |
| **graft mới** | **0** |
| export cũ (openpyxl) | 1199 |
Zip-diff graft vs nguồn: 215 part identical, **0 part nội dung đổi**; chỉ +2 PNG,
2 drawing (+rels) đổi. Regression: tests/test_router_export_preserves_source_bytes.py
(4 test: byte-preserve nội dung, calcPr không đổi/không fullCalcOnLoad + cached
value còn nguyên, chỉ thêm media/drawing, file NONE-mode vẫn xuất).

## Status trước-fix (rollback point)
Live TEST trước hotfix: **71.0.0.298** commit `1feb28615a87` (đã deploy, QR-warn).

**Reported:** user P0, 2026-09-13. "file excel xuất ra có qr rồi, mà nội dung lỗi" — hàng loạt ô `Err:522`.
QR vị trí đã đúng (fixed in 71.0.0.298); nội dung file hỏng.

## Root-cause mechanism (structurally confirmed; recalc confirmation pending)
`_stamp_source_workbook` mở workbook gốc bằng openpyxl (NOT data_only) rồi `wb.save()`.
openpyxl khi save:
- **XÓA hết cached `<v>`** của mọi ô công thức (đo trên export PO6126: 0/135 cached; nguồn: 34/34 cached).
- Ghi `<calcPr fullCalcOnLoad="1" iterate="0" iterateCount="100" iterateDelta="0.0001">`
  (nguồn chỉ có `<calcPr calcId="191029"/>` — không ép recalc, không iterate).

=> Khi mở file xuất, app buộc **full recalc** với **iterative calc TẮT**. Template NEWARK có
(giả thuyết) circular references vốn dựa vào cached value / iterative; recalc lại với iterate=0
=> `Err:522` (circular) lan khắp file.

## Cần chứng minh trước khi sửa
1. soffice headless recalc export_6126.xlsx -> xác nhận Err:522 và LIỆT KÊ đúng sheet/ô/formula.
2. Phân loại circular: (a) hợp lệ (iterative có chủ đích) / (b) do openpyxl mất cached + ép recalc /
   (c) do block-clone/translate formula của chính stamping tạo self-reference.

## Ràng buộc fix (user chốt)
- Bảo toàn dữ liệu, tên/mã bản vẽ, số lượng/thời gian, công thức hợp lệ, định dạng.
- KHÔNG che bằng IFERROR, KHÔNG thay công thức bằng rỗng/0.
- Nếu phải xuất value cho ô ngoài/cached: phải chứng minh giá trị đúng, không mất dữ liệu.
- Giữ luật đã chốt: thiếu ô QRCODE chỉ CẢNH BÁO, vẫn xuất.
- Regression bắt bug thật: export -> mở/recalc -> không Err:522/#REF/#VALUE, so dữ liệu với nguồn,
  QR vẫn nằm ô QRCODE và quét đúng.

## Deploy authorization
User cho phép hotfix bỏ full docker-test/Playwright gate; chỉ syntax/build tối thiểu + reproduce +
deploy TEST + health + tải lại kiểm nội dung/QR. Ghi SHA/version trước-sau + điểm rollback.
KHÔNG deploy nhánh chứa regression import298.
