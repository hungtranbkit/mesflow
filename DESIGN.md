---
name: MESFlow Industrial Operations Design System
version: "1.1"
status: canonical
platform: web
sourceOfTruth: true
primaryViewport: "1920x1080"
requiredViewports:
  - "1366x768"
  - "390x844"
fontStack: "Inter, Arial, Helvetica, sans-serif"
colorTokens:
  neutral-0: "#ffffff"
  neutral-25: "#f8fafc"
  neutral-50: "#f3f5f7"
  neutral-100: "#e9edf1"
  neutral-200: "#d6dce3"
  neutral-300: "#b7c0ca"
  neutral-500: "#647180"
  neutral-700: "#344252"
  neutral-900: "#17212b"
  command-700: "#24455f"
  command-800: "#18364e"
  command-900: "#102b3f"
  action-600: "#23658b"
  action-700: "#1b5274"
  info-600: "#2563a6"
  success-600: "#177451"
  warning-600: "#a85f08"
  danger-600: "#c43232"
  offline-600: "#56616d"
semanticTokens:
  canvas: "{colorTokens.neutral-50}"
  surface: "{colorTokens.neutral-0}"
  surface-subtle: "{colorTokens.neutral-25}"
  text: "{colorTokens.neutral-900}"
  text-secondary: "{colorTokens.neutral-500}"
  border: "{colorTokens.neutral-200}"
  border-strong: "{colorTokens.neutral-300}"
  focus: "{colorTokens.action-600}"
  primary: "{colorTokens.command-800}"
  action: "{colorTokens.action-600}"
  status-info: "{colorTokens.info-600}"
  status-success: "{colorTokens.success-600}"
  status-warning: "{colorTokens.warning-600}"
  status-danger: "{colorTokens.danger-600}"
  status-offline: "{colorTokens.offline-600}"
spacing:
  0: "0"
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  5: "20px"
  6: "24px"
  8: "32px"
radius:
  control: "4px"
  panel: "6px"
  overlay: "8px"
  pill: "999px"
---

# MESFlow Industrial Operations Design System

`DESIGN.md` là **nguồn chuẩn duy nhất** cho giao diện MESFlow. Mọi màn hình mới hoặc lượt chỉnh UI phải đọc tài liệu này trước khi sửa source. Không tạo phong cách riêng theo trang; ngoại lệ chỉ được thêm vào tài liệu khi có lý do nghiệp vụ rõ ràng.

## 1. Creative North Star

**Bàn điều độ xưởng Industrial Soft-3D — rõ tầng thông tin, thấy ngoại lệ, ra quyết định.**

MESFlow là industrial operations console cho xưởng cơ khí, không phải landing page SaaS. Ngôn ngữ thị giác functional/Swiss kết hợp Industrial Soft-3D: bố cục theo lưới, thẳng hàng, chữ rõ, nền xám lạnh nhạt, bề mặt trắng và độ nổi khối nhẹ bằng border cùng shadow ngắn. Mỗi chi tiết phải giúp đọc dữ liệu, xác định ưu tiên hoặc thực hiện thao tác.

Thứ tự chú ý bắt buộc:

1. Sự cố, ngoại lệ hoặc việc cần can thiệp.
2. Trạng thái và tiến độ sản xuất.
3. Hành động chính trong ngữ cảnh.
4. Dữ liệu hỗ trợ và lịch sử.

## 2. Nguyên tắc bất biến

- Trung tính là mặc định; màu trạng thái chỉ mang ngữ nghĩa.
- Dùng phân cấp, vị trí, nhãn và độ đậm trước khi dùng màu.
- Không gradient tím/xanh, glassmorphism, nền blur hoặc hiệu ứng trang trí.
- Không card lồng card. Trong panel, dùng section, divider, row hoặc nền subtle.
- Không đặt icon trong ô vuông bo tròn lặp lại ở mọi tiêu đề.
- Không KPI khổng lồ; số liệu phải cân bằng với nhãn, đơn vị và ngữ cảnh.
- Không khoảng trắng kiểu marketing; khoảng trống phục vụ nhóm và nhịp quét.
- Không emoji làm icon hoặc tín hiệu trạng thái. Dùng SVG cùng một họ nét.
- Dùng elevation theo cấp Page → Section → Card → Row → Control; shadow phải ngắn, trung tính và không tạo cảm giác bóng bẩy.
- Không thay framework; triển khai bằng JavaScript/CSS hiện tại của MESFlow.

## 3. Token architecture

Triển khai theo ba tầng: **primitive → semantic → component**. Component chỉ tham chiếu semantic token; không hard-code màu khi token đã tồn tại.

### 3.1 Màu

| Vai trò | Token | Giá trị | Cách dùng |
|---|---|---:|---|
| Canvas | `--surface-canvas` | `#f3f5f7` | Nền workspace |
| Surface | `--surface-default` | `#ffffff` | Panel, form, table |
| Surface subtle | `--surface-subtle` | `#f8fafc` | Header bảng, row phụ |
| Text | `--text-primary` | `#17212b` | Nội dung chính |
| Text phụ | `--text-secondary` | `#647180` | Metadata, mô tả |
| Border | `--border-default` | `#d6dce3` | Viền và divider |
| Command | `--bg-command` | `#18364e` | Sidebar, vùng điều hành |
| Action | `--action-primary` | `#23658b` | CTA chính, link, focus |
| Info | `--status-info` | `#2563a6` | Thông tin trung tính |
| Success | `--status-success` | `#177451` | Hoàn tất, ổn định |
| Warning | `--status-warning` | `#a85f08` | Cần chú ý |
| Danger | `--status-danger` | `#c43232` | Lỗi, chậm, nguy hiểm |
| Offline | `--status-offline` | `#56616d` | Mất kết nối, không hoạt động |

Mỗi status phải có cặp nền nhạt + chữ/viền đậm và luôn kèm text hoặc icon; không truyền đạt bằng màu đơn độc. `Warning` không dùng làm accent trang trí. `Success` không dùng làm primary action.

Contrast tối thiểu: chữ thường 4.5:1, chữ lớn và glyph UI 3:1. Focus ring phải nhìn rõ trên cả nền trắng và command navy.

### 3.2 Typography

Font chuẩn là `Inter, Arial, Helvetica, sans-serif`. Inter được phép self-host với `font-display: swap`; hệ thống phải hoạt động đúng với fallback và không phụ thuộc Google Fonts. Tiếng Việt phải hiển thị đủ dấu.

| Role | Size / line-height | Weight | Dùng cho |
|---|---|---:|---|
| Page title | 24 / 30px | 700 | Một H1 mỗi màn hình |
| Section title | 18 / 24px | 650–700 | H2 cấp vùng |
| Panel title | 15 / 20px | 650 | Tiêu đề panel/table |
| Body | 14 / 20px | 400 | Nội dung, form |
| Data/table | 13 / 18px | 400–600 | Bảng mật độ cao |
| Label | 12 / 16px | 600 | Nhãn, column header |
| Caption | 11 / 15px | 500 | Metadata phụ; không dùng cho nội dung thiết yếu |

- Số liệu, thời gian, mã PO/Part/Operation dùng `font-variant-numeric: tabular-nums`.
- Đơn vị nhỏ hơn số một cấp nhưng không thấp hơn 11px.
- Không viết hoa đoạn dài. Uppercase chỉ dành cho eyebrow/group label ngắn, tracking `0.06em` tối đa.
- KPI mặc định 22–28px; tối đa 32px trong console. Không dùng display type 40px+.

### 3.3 Spacing, shape, border và elevation

- Spacing scale: `4, 8, 12, 16, 20, 24, 32px`; không tạo khoảng cách tùy ý.
- Workspace gutter: 24px ở 1920, 20px ở 1366, 12px ở mobile.
- Khoảng panel: 16px; padding panel: 16px desktop, 12px compact/mobile.
- Control radius 4px; panel 6px; overlay 8px; pill chỉ dành cho status/filter chip.
- Border mặc định 1px; divider dùng border thay cho card con. Border card phải rõ hơn nền trang.
- Radius chuẩn: control `5px`, row `5px`, card `7px`, panel `8px`, overlay `9px`.
- Row: `0 1px 2px rgba(16, 43, 63, .055)`; card: `0 2px 5px rgba(16, 43, 63, .085)`.
- Section: `0 4px 12px rgba(16, 43, 63, .11)`; PO/section quan trọng được phép dùng `0 7px 18px rgba(16, 43, 63, .14)`.
- Input/select dùng inset shadow nhẹ; button dùng shadow ngắn và chuyển sang inset shadow ở trạng thái pressed.
- Overlay: `0 14px 34px rgba(16, 43, 63, .22)`; không dùng glow, glass hoặc shadow có blur quá lớn.

### 3.4 Motion và layering

- Motion chỉ giải thích thay đổi trạng thái: hover/focus 120–160ms, popover/modal 160–220ms.
- Chỉ animate `opacity` và `transform`; không animate kích thước gây reflow.
- Không scroll reveal, parallax, pulse trang trí hoặc stagger danh sách trong console.
- Tôn trọng `prefers-reduced-motion: reduce`.
- Z-index chuẩn: content `0`, sticky `10`, dropdown `30`, scrim `40`, modal `50`, toast `60`.

## 4. Layout và responsive

### 4.1 Desktop chính — 1920×1080

- App shell gồm sidebar cố định 248px và workspace co giãn.
- Nội dung dùng toàn bộ chiều rộng hữu ích; không ép dashboard vào container marketing hẹp.
- Grid nền 12 cột, gutter 16px. Vùng quyết định chính phải nằm trong phần nhìn đầu tiên.
- Page header gọn: title/context bên trái; tối đa một primary action bên phải.
- KPI summary thường 4–6 cột, cao khoảng 76–96px; ưu tiên scan ngang.

### 4.2 Desktop tối thiểu — 1366×768

- Đây là viewport nghiệm thu bắt buộc, không phải trường hợp phụ.
- Sidebar được phép thu về 220–232px nếu cần; workspace gutter 20px.
- Không làm nhỏ chữ thiết yếu để nhét nội dung. Giảm gap/padding trước, sau đó chuyển grid 4→2 hoặc cho bảng cuộn ngang.
- Header, filter và hành động chính phải còn thấy/đạt được; không để vùng trang trí đẩy bảng xuống dưới fold.

### 4.3 Mobile — 390×844

- Mục tiêu là không vỡ và vẫn thao tác được, không cần giữ mật độ desktop.
- Navigation chuyển thành drawer/top control; không để sidebar chiếm màn hình theo chiều dọc.
- Layout một cột; filter/action wrap theo nhóm. Control nhập liệu cao tối thiểu 44px.
- Bảng nghiệp vụ rộng được cuộn ngang trong wrapper có dấu hiệu affordance; cột định danh đầu tiên có thể sticky nếu không che dữ liệu.
- Không có horizontal scroll ở cấp `body`.

## 5. Component contracts

### 5.1 App shell và navigation

- Sidebar command navy, logo chữ gọn; không cần logo tile lớn.
- Item cao 36–40px desktop, icon 18px + label. Active dùng nền sáng hơn, chữ trắng và indicator 3px; không chỉ đổi màu chữ.
- Group label 11px; giữ navigation chính nhất quán giữa các màn hình.
- Có skip link tới main content; tab order theo thứ tự nhìn.

### 5.2 Page header và toolbar

- H1 + một dòng context ngắn. Không bọc header trong hero card nếu không có nghiệp vụ riêng.
- Toolbar là một dải control phẳng; search nở rộng, filter theo độ dài nội dung, actions gom bên phải.
- Khi thiếu chỗ: wrap có trật tự hoặc đưa secondary action vào overflow; không thu nhỏ control tùy ý.
- Mỗi màn hình chỉ có một primary CTA tại cùng một thời điểm.

### 5.3 Panels và sections

- Panel: surface trắng, border 1px rõ, radius 8px, padding 16px, dùng section shadow chuẩn.
- Panel header dùng text/icon trực tiếp; icon không nằm trong decorative tile.
- Nội dung con phân nhóm bằng heading, divider hoặc `surface-subtle`, không lồng panel/card đồng cấp.
- Chỉ dùng side accent cho hàng ngoại lệ/được chọn, không trang trí toàn bộ panel.

### 5.4 KPI và status summary

- KPI gồm label, giá trị, đơn vị/context và optional delta/status. Không chỉ có một con số lớn.
- Giá trị 22–28px, tabular; màu chữ mặc định trung tính. Chỉ indicator hoặc status text mang màu.
- KPI không phải button trừ khi có affordance và trạng thái focus rõ.
- Nhóm KPI có cùng chiều cao và baseline; không dùng background nhiều màu cho từng ô.

### 5.5 Data tables và dense lists

- Table là mẫu mặc định cho dữ liệu nhiều cột; row card chỉ dùng khi mỗi record có quyết định phức tạp.
- Header cao 36–40px; row tiêu chuẩn 40–44px, row hai dòng 52–60px; cell padding ngang 10–12px.
- Text trái; số phải; trạng thái và action căn nhất quán. Header số cũng căn phải.
- Có sort indicator + `aria-sort`, hover row nhẹ, selected state rõ, empty/loading/error state nằm trong vùng table.
- Dữ liệu dài wrap có kiểm soát hoặc ellipsis kèm cách xem đầy đủ. Không cắt mất mã định danh quan trọng.
- Bulk action chỉ xuất hiện khi có selection và phải báo số mục đã chọn.

### 5.6 Buttons và icon actions

- Button cao 36px desktop; compact 32px chỉ cho toolbar dày và vẫn cần hit area hợp lý. Mobile tối thiểu 44px.
- Primary: command/action fill; secondary: surface + border; tertiary: text; danger tách khỏi primary.
- Icon 16/18/20px, cùng một họ SVG outline và stroke nhất quán. Icon-only bắt buộc có accessible name/tooltip.
- Disabled dùng thuộc tính semantic, giảm tương phản có kiểm soát và không nhận click.
- Loading action khóa submit lặp và giữ nguyên chiều rộng nút.

### 5.7 Forms

- Label luôn hiển thị; placeholder chỉ là ví dụ. Required/error/helper đặt gần field.
- Input/select cao 36px desktop, 44px mobile; radius 4px. Read-only khác disabled.
- Validate sau blur hoặc submit; lỗi nói rõ nguyên nhân và cách sửa. Khi submit lỗi, focus field lỗi đầu tiên.
- Form dài chia section bằng heading/divider, không dùng card lồng card.

### 5.8 Badges và operational states

- Badge/status chip cao 20–24px, label ngắn, radius pill; status nghiêm trọng kèm icon hoặc dot + text.
- Vocabulary thống nhất: `Thông tin`, `Đúng tiến độ/Hoàn tất`, `Cần chú ý`, `Làm ngay/Lỗi`, `Ngoại tuyến/Chờ` tùy ngữ cảnh nghiệp vụ.
- Không dùng red/green làm cặp phân biệt duy nhất. Trạng thái phải đọc được ở grayscale.

### 5.9 Modal, popover, toast

- Modal chỉ dùng cho tác vụ ngắn, cần giữ context; flow chính nên là page/panel.
- Modal width theo nội dung, tối đa 720px cho form phổ thông; có title, close, Escape và focus trap/restore.
- Scrim đen 48%; overlay radius 8px và shadow chuẩn duy nhất.
- Toast không thay thế lỗi inline, không cướp focus, dùng `aria-live="polite"`; action quan trọng không auto-dismiss quá nhanh.

### 5.10 Loading, empty và error states

- Trên 300ms phải có feedback. Skeleton giữ đúng khung để tránh layout shift; không shimmer mạnh.
- Empty state nói điều gì đang trống và bước tiếp theo, không dùng minh họa lớn trang trí.
- Error state nêu nguyên nhân nếu biết và cung cấp retry/recovery. Không để chart/table trống như thể không có dữ liệu.

## 6. Data visualization

- Chart chỉ dùng khi giúp thấy xu hướng, so sánh hoặc bottleneck nhanh hơn table.
- Xu hướng theo thời gian: line chart; so sánh/ranking: bar chart; tiến độ: bar/stacked bar; process flow chỉ dùng khi topology thực sự quan trọng.
- Không pie/donut trên 5 nhóm; không gauge trang trí; không 3D hoặc gradient fill.
- Gridline subtle, axis có đơn vị, tooltip có giá trị chính xác, legend sát chart.
- Không dựa vào màu: thêm line style, marker, label hoặc pattern. Luôn có summary text hoặc table dữ liệu thay thế.
- Dữ liệu realtime phải có timestamp “cập nhật lúc”, trạng thái stale/offline và khả năng pause nếu chuyển động liên tục.

## 7. Content và terminology

- Dùng tiếng Việt ngắn, trực tiếp, theo thuật ngữ nghiệp vụ hiện tại: Production Order, Part, Operation, WIP, Session khi chưa có từ thay thế đã thống nhất.
- Button bắt đầu bằng động từ: “Tạo PO”, “Lưu thay đổi”, “Nhận xử lý”.
- Nhãn trạng thái mô tả thực tế, không dùng câu marketing hoặc tuyên bố chưa có bằng chứng.
- Thời gian, số lượng và đơn vị dùng format Việt Nam nhất quán; không trộn format trong cùng màn hình.

## 8. Accessibility và thao tác

- Mục tiêu tối thiểu WCAG 2.1 AA cho contrast và keyboard interaction.
- Mọi chức năng dùng được bằng bàn phím; focus-visible 2px + offset 2px, không xóa outline nếu không có thay thế.
- Icon-only control có accessible name; image có alt phù hợp; heading không nhảy cấp.
- Color không là tín hiệu duy nhất. Live update dùng `aria-live` phù hợp và không làm mất focus/scroll.
- Desktop pointer target ưu tiên tối thiểu 32×32px; thao tác chính 36px. Mobile tối thiểu 44×44px, cách nhau ít nhất 8px.
- Modal có Escape, focus trap và trả focus về trigger; route/page change đưa focus hợp lý về main heading.

## 9. Governance và Definition of Done

Khi chỉnh bất kỳ màn hình nào:

1. Đọc `PRODUCT.md` và `DESIGN.md`; giữ nguyên nghiệp vụ/API/database nếu không được yêu cầu.
2. Dùng token hiện có; nếu thiếu token dùng chung, bổ sung vào đây trước khi thêm vào CSS.
3. Không tạo page-specific visual language. Ngoại lệ phải có lý do nghiệp vụ và không phá nguyên tắc bất biến.
4. Kiểm tra đủ normal, hover, active, focus-visible, disabled, loading, empty và error nếu component có các trạng thái đó.
5. Chạy local tại `http://127.0.0.1:8080` và kiểm tra bằng Playwright tại 1920×1080, 1366×768, 390×844.
6. Tiêu chí pass: không overflow body; nội dung chính và hành động reachable; không card lồng card; không màu/size/radius tùy ý; contrast đạt; keyboard dùng được; không thay đổi nghiệp vụ.

## 10. Explicit anti-patterns

- Gradient tím/xanh, glassmorphism, blur trang trí, neon hoặc glow.
- Radius lớn kiểu consumer (`12–24px`) trên panel/control phổ thông.
- Shadow quá lớn/đậm hoặc cùng một elevation cho mọi cấp; background màu cho từng KPI; status color phủ diện tích lớn.
- Card trong card, grid card thay cho table dữ liệu, hero section trong console.
- KPI 40px+, title oversized, khoảng trắng 48–96px không phục vụ phân nhóm.
- Icon tile bo tròn trước mọi heading; emoji làm icon; trộn nhiều icon family.
- Hard-coded hex/radius/spacing lặp lại trong component khi đã có token.
- Truncation không có cách xem đầy đủ; chart không có đơn vị/legend/fallback; refresh realtime không báo timestamp.
