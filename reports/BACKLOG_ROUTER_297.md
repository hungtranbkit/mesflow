# Backlog Router/297 — trạng thái/owner/branch (2026-09-12)
Không tuyên bố done khi chưa có diff/commit.

| Task | Trạng thái | Owner | Branch/SHA | Ghi chú |
|---|---|---|---|---|
| EXCEL-QR-EMBED (QR vào ô QRCODE) | DONE (code+regression), full gate mesflow1 XANH; đang re-gate phía tôi cho release 297 | mesflow1 | agent/claude/router-marker-addedop @ 532b480 (đã push origin) | Verify file thật: QR neo đúng ô QRCODE, merged top-left, marker cleared, payload đúng. Fixture NEWARK khách KHÔNG có ô QRCODE (marker cho template tương lai). Đang build/deploy TEST 297. |
| IMPORT-A/B/C (dup blocking + drawing-optional + process-OP infer) | DONE, full gate XANH (222/637/44/568 + PW495/3flaky) — = release 298 sau 297 | mesflow1 | agent/claude/op-code-non-unique @ 6898fde | VI: 'Lỗi: OP trùng mã trong cùng một Part...' + sheet/Part/code/rows; no Template/PO; no auto-suffix. Across-Part OK. |
| IMPORT-B: drawing OPTIONAL | CHƯA CÓ DIFF | mesflow1 | (chưa) | Thiếu bản vẽ = hợp lệ, no warning, no PART-xx hiển thị. |
| IMPORT-C: process sheet no-OP => warn + 1 inferred OP | CHƯA CÓ DIFF | mesflow1 | (chưa) | Classifier phải review (không nuốt Part sheet thật). Ordinary no-OP = skip. |
| DRAWING-CODE persist+display (mig 0053) | DONE, full gate XANH (578 integ, +10) — = release 299 sau 298 | mesflow1 | agent/claude/part-drawing-code @ 2d2b50e (base 6898fde) | 2 cột nullable: template_parts.drawing_code (verbatim import) + parts.drawing_code (snapshot instantiate); non-retroactive NULL; 0052->0053, schema 72.0.12.0. TRAP: replace_tree xoá cột không mang -> test_luu_lai_template_khong_xoa_mat_ma_ban_ve; review kỹ ở 299. UI: Template detail sửa được 'Mã bản vẽ', PO detail read-only; /api/parts trả cột. |
| UI set (bỏ export PO list + Template list + Part card name>code + op-count centered) | mesflow1 đang làm (step 4), branch off 2d2b50e | mesflow1 | (sắp) | app.js ~983/1057 remove; giữ PO detail poExportRouter ~1140. |
| UI: Template list selected/focus + card gap | CHƯA CÓ DIFF | mesflow1 | (chưa) | ui.css ~528: gap:0 + border-bottom stuck; .active quá nhạt; thiếu :focus-visible. |
| UI: Part card name>code + op-count centered | CHƯA CÓ DIFF | mesflow1 | (chưa) | poPartCard ~1160 code·name -> name chính; op-count căn giữa (shared CSS). |

Live TEST: 71.0.0.296 (3696d47). Release 297 = CHỈ EXCEL-QR-EMBED (đang gate). Các mục còn lại sang 298+.
