# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- Chủ xưởng và giám đốc cần nắm nhanh tình trạng sản xuất và các vấn đề cần can thiệp.
- Quản đốc cần theo dõi tiến độ, điều hành công việc và xử lý ngoại lệ tại xưởng.
- Nhân viên vận hành sử dụng luồng kiosk để nhận diện, bắt đầu và hoàn tất công việc, đồng thời ghi nhận sản lượng và lỗi.
- Quản trị viên quản lý dữ liệu, người dùng, thiết bị và vận hành hệ thống.

## Product Purpose

MESFlow là hệ thống điều hành sản xuất dành cho xưởng cơ khí. Sản phẩm giúp các vai trò trong xưởng nhìn nhanh và hiểu ngay tình trạng sản xuất, ưu tiên tiến độ, ngoại lệ và những việc cần xử lý. Thành công là khi người dùng có thể ra quyết định vận hành từ dữ liệu dày mà không bị rối hoặc phải dò tìm thông tin quan trọng.

## Positioning

Vị thế khác biệt so với bảng tính hoặc các hệ thống MES khác chưa được xác nhận; đây là một quyết định sản phẩm còn mở.

## Operating Context

- Môi trường sử dụng chính là xưởng cơ khí.
- Luồng điều hành gồm Production Order, Part, Operation, ca làm việc, tiến độ, WIP, bottleneck, session sản xuất, ngoại lệ và cảnh báo.
- Nhân viên vận hành dùng kiosk và mã QR để quét thẻ nhân viên, chọn Operation, bắt đầu hoặc hoàn tất công việc, ghi nhận số đạt, số lỗi và số sửa được.
- Chủ xưởng, giám đốc, quản đốc và quản trị viên sử dụng giao diện quản trị với dashboard tổng quan, báo cáo, quản lý dữ liệu và tình trạng kiosk.
- Giao diện phải dùng tốt trên màn hình 1366x768.

## Capabilities and Constraints

- Giao diện và thuật ngữ sản phẩm hiện dùng tiếng Việt.
- Hệ thống là ứng dụng web phía máy chủ với Flask/Jinja và JavaScript/CSS, dùng PostgreSQL và được triển khai bằng Docker với Nginx.
- Có phân quyền cho các vai trò `admin`, `manager` và `supervisor`; kiosk phục vụ luồng vận hành tại xưởng.
- Production Order được tạo từ Template và phải được Start trước khi đi vào luồng điều hành và kiosk.
- Các số liệu và nhãn phải tách biệt rõ ràng; dữ liệu dày nhưng phải dễ quét và không gây rối.
- Ưu tiên hiển thị tiến độ, ngoại lệ và hành động cần xử lý.

## Brand Commitments

- Tên sản phẩm: MESFlow.
- Giữ phong cách công nghiệp, rõ ràng và đáng tin cậy.
- Không biến giao diện vận hành thành landing page hoặc sản phẩm SaaS mang tính quảng cáo.
- Hạn chế card lồng card và màu sắc không mang ý nghĩa.

## Evidence on Hand

- Giao diện quản trị hiện có: `app/mesflow/web/templates/app.html`, `app/mesflow/web/static/ui.css` và các renderer trong `app/mesflow/web/static/pages/`.
- Giao diện kiosk hiện có: `app/mesflow/web/templates/kiosk.html`, `app/mesflow/web/static/kiosk.css` và `app/mesflow/web/static/kiosk.js`.
- Luồng, API và mô hình dữ liệu sản xuất hiện có trong `app/mesflow/web/`, `app/mesflow/db/repositories/` và `app/migrations/versions/`.
- Hợp đồng kiểm thử sản phẩm hiện có trong `tests/` và `tests/e2e/`.
- Chưa có bằng chứng đã xác nhận về khách hàng, testimonial, benchmark, chứng nhận hoặc tuyên bố thương mại; công việc tương lai không được tự tạo các nội dung này.

## Product Principles

1. Tình trạng sản xuất và việc cần xử lý phải nhận ra ngay từ lần quét đầu tiên.
2. Tiến độ và ngoại lệ quan trọng hơn trang trí hoặc nội dung quảng bá.
3. Mật độ thông tin cao phải đi cùng phân cấp rõ, nhãn và số liệu tách bạch.
4. Mọi màu sắc và thành phần giao diện phải có vai trò vận hành rõ ràng.
5. Trải nghiệm phải phù hợp với thực tế sử dụng tại xưởng và màn hình 1366x768.

## Accessibility & Inclusion

Chưa có tiêu chuẩn tuân thủ hoặc nhu cầu hỗ trợ tiếp cận chuyên biệt được xác nhận. Tuy vậy, khả năng đọc nhanh, phân biệt rõ nhãn với số liệu và không dựa vào màu sắc trang trí là các yêu cầu sản phẩm đã được xác nhận.
