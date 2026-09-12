# Fixture nhị phân cho test

## `router-newark-arm-chair.xlsx`

Chính file **Lộ trình sản xuất NEWARK ARM CHAIR** mà xưởng đang dùng, giữ nguyên
bytes (1,9 MB, 44 sheet, 112 Operation, 47 chỗ có thời gian setup, 10 chỗ đánh
trùng số Operation trong cùng một Part).

**Tại sao phải là file thật, không phải file dựng bằng openpyxl.** Hợp đồng của
tính năng xuất tờ router là *giữ nguyên biểu mẫu của khách*: merge, độ rộng cột,
chiều cao dòng, logo/ảnh, khung in, công thức tính giờ. Một workbook dựng bằng
openpyxl trong test không có thứ nào trong số đó, nên nó không thể chứng minh
được điều cần chứng minh. Ba lỗi thật đã bị bắt đúng bằng file này và **không**
bị các workbook dựng tay bắt được:

1. mọi tem rơi xuống sheet phụ vì mã Operation thật mang tiền tố PO còn chỉ mục
   block khoá theo hậu tố — tổng số tem vẫn đủ nên phép đếm không thấy gì;
2. dấu `-` trong ô "Thời gian Setup" (cách xưởng viết "không có") làm cả file
   44 sheet bị từ chối;
3. số Operation đánh trùng trong cùng một Part (sự cố TPL-6126).

Dùng ở `tests/test_router_export_real_workbook.py` và
`tests/integration/test_router_setup_import_export.py`.

Đây là dữ liệu sản xuất thật của khách (mã bản vẽ, mã PO 6126). Không dùng file
này ngoài phạm vi test, và không đưa ra ngoài repo.
