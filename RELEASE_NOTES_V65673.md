# MESFlow v65.6.7.3

- Sửa lỗi `Object of type datetime is not JSON serializable` khi quét Operation.
- Chuẩn hóa response kiosk sang JSON-safe trước khi lưu JSONB và trả API.
- Hỗ trợ datetime/date/time, Decimal, UUID và cấu trúc lồng nhau.
- Không cần migration database.
