# hp3 — Dashboard / Report / Exception / Session theo thang bo góc canonical

Lane phụ trên node HP. **Không merge, không deploy.** Nhánh giao cho session
`mesflow` trên Dell quyết định.

- Nhánh: `hp3/ui-dashboard-report-list-rounded`
- Gốc: `origin/integration/daily-dashboard-test` @ `eb3ee75` (sau khi rebase)
- Clone sạch riêng (`~/workspace/mesflow-hp3-lane`); stack test riêng
  `docker compose -p mesflow-hp3-lane`. Không đụng `~/workspace/mesflow-hp-lane`,
  không đụng runtime cũ.

---

## 0. Vì sao bản vá cũ phải viết lại

Bản vá đầu của lane này (trên gốc `95a29e6`) dùng `--radius-card` cho vỏ bảng
dày. Trong lúc đó `ui/design-system-enforcement` đã merge vào integration và
thay toàn bộ thang bo góc:

| bậc | giá trị | dùng cho |
|---|---|---|
| `--radius-surface` | 12px | khối nội dung **ngoài cùng**: card, list item, panel, section, vỏ bảng |
| `--radius-surface-row` | 8px | khối **lồng** bên trong một surface: row, subrow, ô inset |
| `--radius-control` | 8px | input, select, button, chip |
| `--radius-overlay` | 16px | modal / sheet (nổi trên mặt phẳng khác) |

`--radius-card` / `--radius-panel` / `--radius-row` **giữ nguyên giá trị nhưng
đổi vai**: nay chỉ phục vụ phần tử NHỎ (icon sidebar, thanh gantt, huy hiệu).
Dùng chúng cho một khối nội dung là sai chuẩn. Nên bản vá cũ được **viết lại**,
không vá chồng.

Đáng ghi lại vì nó sẽ lặp: bản vá cũ vẫn **xanh hết mọi bài test** sau rebase.
Guard Python `tests/test_ui_surface_radius_is_canonical.py` nhận diện surface
bằng HẬU TỐ selector (`-card|-panel|-section`); `.op-time-table`,
`.daily-op-table`, `.session-manage-row`, `.session-inbox-banner`,
`.session-accordion-item` không khớp hậu tố nào nên **không bài nào chạm tới**.
Đó chính là cách `--radius-card` ngồi yên trên một vỏ bảng mà không ai thấy.

---

## 1. Đã sửa

### Dải tab A/B/C — dùng chung primitive, không dựng lại

`.dashboard-tabs`/`.dashboard-tab` là bản dựng lại RIÊNG của `.mf-tabs` với sáu
giá trị viết cứng. Đo được, cùng vai trò, hai hình:

```
EC   : borderBottom=1px rgb(200,208,216) | padding=11px 15px | 13px | underline 3px
DASH : borderBottom=1px rgb(217,222,231) | padding=10px 14px | 14px | underline 2px
```

Nay markup composes `mf-tabs`/`mf-tab`; CSS chỉ còn phần RIÊNG của trang là
khoảng cách dọc. **Cố ý KHÔNG bo góc dải tab**: dạng chuẩn của `.mf-tabs` là
dải gạch chân phẳng, bo góc riêng cho Dashboard là đẻ ra bộ tab thứ tư. Lợi ích
đo được ở 390px: `.mf-tabs` cuộn ngang, dải cũ thì không — trước đây ba tab bị
ép xuống 3 dòng chữ.

### Surface lấy đúng bậc canonical

| Màn | Selector | Trước | Sau | Lý do |
|---|---|---|---|---|
| Dashboard A | `.op-time-table` | `--radius-card` | `--radius-surface-row` | vỏ bảng LỒNG trong `.content-panel` |
| Dashboard C | `.daily-op-table` | `--radius-card` | `--radius-surface-row` | idem |
| Dashboard B | `.employee-day-track` | `--radius-card` | `--radius-surface-row` | thanh lồng trong row ngày công |
| Dashboard | `.daily-shift-reference` | `--radius-panel` | `--radius-surface-row` | khối info lồng trong filter bar |
| Dashboard | `.daily-date-picker,.shift-picker` | `12px` + `--radius-panel` | `--radius-control` | là ô nhập |
| Dashboard | `.daily-kpi` | `13px` + `--radius-panel` | **xoá** | khai báo CHẾT (rule quét đã ép `--radius-surface`) |
| Session | `.session-accordion-item` | `--radius-panel,6px` | **xoá** | khai báo CHẾT (idem) |
| Session | `.session-manage-row` | `--radius-card` | `--radius-surface-row` | dòng danh sách lồng |
| Session | `.session-line` | `--radius-card` | `--radius-surface-row` | dòng timeline lồng |
| Session | `.session-inbox-banner` | `--radius-card` | `--radius-surface-row` | banner lồng |
| Session | `.session-exception-context` | `--radius-card` | `--radius-surface-row` | khối ngữ cảnh lồng |
| Session | `.session-edit-sections fieldset,.session-advanced` | `--radius-card` | `--radius-surface-row` | khối lồng trong sheet |
| Session | `.session-track i` | `4px` | `--radius-surface-row` | theo đúng `.employee-day-progress i` |
| Exception | `.se-summary article` | `--radius-card` | `--radius-surface` | thẻ tóm tắt cấp trang |
| Exception | `.se-queue,.se-detail` | `--radius-panel` | `--radius-surface` | hai panel chính |
| Exception | `.se-history-filters` | `--radius-card` | `--radius-surface-row` | khối lọc lồng |
| Exception | `.se-steps>div` | `--radius-card` | `--radius-surface-row` | bước lồng |
| Exception | `.se-modal-issue` | `--radius-panel` | `--radius-surface-row` | khối trong modal |
| Exception | `.se-modal-next` | `--radius-card` | `--radius-surface-row` | idem |
| Exception | `.se-detail-grid span` | `6px` | `--radius-surface-row` | ô chi tiết lồng |
| Exception | `.se-review-note` | `6px` | `--radius-surface-row` | ghi chú lồng |
| Exception | `.ec-recommend` | gạch `#d7dfe6` | `--border-subtle` | viền nhẹ theo token |
| Report | `.ba-changes-preview` | `--radius-panel` | `--radius-surface-row` | khối diff lồng trong thẻ |
| Report | `.ba-raw` | `--radius-panel` | `--radius-surface-row` | khối raw lồng trong thẻ |

Vỏ bảng lấy `--radius-surface-row` chứ không `--radius-surface`: REQ-UI-014 nói
`--radius-surface` là cho khối **ngoài cùng**, và REQ-UI-015(c) nói khối lồng /
inset dùng `--radius-surface-row`. `.op-time-table` nằm lọt trong thân
`.content-panel` (986px trong panel 1012px, còn padding hai bên) nên là khối
lồng. DÒNG bên trong vẫn phẳng — REQ-UI-015(b) cho phép, và `overflow:auto` sẵn
có lo việc cắt góc.

Sau bản vá, trong phạm vi hp3 **không còn** token cũ hay số cứng nào trên
surface, trừ một ngoại lệ cố ý: `.ec-status` (`3px`) là huy hiệu inline, thuộc
nhóm "phần tử nhỏ" mà thang không quản.

---

## 2. Bằng chứng

### Test
- Spec `tests/e2e/dashboard-list-surface-contract.spec.js` — **8 test, xanh**.
- Regression các màn liên quan: **96 test xanh**, gồm `card-surface-contract.spec.js`.
- Cổng static Python: **556 passed, 4 skipped** (gồm 5 bài guard mới của
  design-system).

### Bài test bịt lỗ guard
Bài thứ 8 đo **DOM thật** thay vì hậu tố selector: mọi mặt có sơn, rộng ≥200px
và cao ≥40px trên 6 trang phải lấy bo góc từ thang canonical. Nó **bắt ngay
trong lúc phát triển** hai chỗ tôi đã bỏ sót khi đọc CSS bằng mắt:

```
[Dashboard ngày — tab B] div.employee-day-track.shift-track -> 7px (420x42)
[Quản lý Session]        div.session-inbox-banner          -> 7px (1012x66)
```

Đây là lý do bài đó tồn tại: guard theo tên class không thấy chúng, và tôi cũng
không thấy.

### Negative proof (trên gốc mới)
Hoàn nguyên hai file nguồn về `eb3ee75`, giữ nguyên spec:

```
4 failed
  › dải tab Dashboard theo ngày dùng chung primitive với Trung tâm ngoại lệ
  › ba tab A/B/C thực sự mang class của primitive, không chỉ trông giống
  › vỏ bảng dày lồng trong panel lấy bậc khối-lồng, dòng bên trong vẫn phẳng
  › mọi surface trên 4 nhóm màn lấy bo góc từ thang canonical
4 passed
```

Đúng bốn bài mã hoá bản vá thì đỏ; bốn bài còn lại vẫn xanh — tức chúng không
rỗng.

### Ảnh
`reports/screenshots/hp3-dashboard-list-rounded/{before,after}/` — 1920/1366/390.
`before` chụp từ **chính `eb3ee75`** (checkout file nguồn của gốc), không phải
từ nhánh đã vá.

---

## 3. Requirement

`DESIGN.md` bị lệch khỏi REQ-UI-014 sau đợt design-system: §3.3 vẫn ghi thang
CŨ (`control 5px, row 5px, card 7px, panel 8px, overlay 9px`), §5.3 ghi "panel
radius 8px", §5.7 "input radius 4px", §5.9 "overlay radius 8px". Bản vá cập nhật
cả bốn chỗ trỏ về thang canonical và nói rõ REQ-UI-014 là nguồn sự thật,
`DESIGN.md` chỉ nhắc lại. Thêm §5.5b (tab dùng chung primitive) và bổ sung §5.5
(vỏ bảng lồng lấy bậc khối-lồng).

Không đổi hợp đồng: REQ-UI-013/014/015 giữ nguyên, đây là thi hành đúng điều đã
chốt.

---

## 4. Ngoài phạm vi — tìm thấy nhưng KHÔNG sửa

1. **Guard Python có lỗ theo thiết kế.** `_is_surface` bắt theo hậu tố
   `-card|-panel|-section`. Mở rộng sang `-table|-row|-item|-list|-banner|-tile`
   sẽ lộ thêm **11 selector ngoài phạm vi hp3** đang dùng token cũ hoặc số cứng:
   `.template-old-list,.template-old-editor`, `.template-flow-row`,
   `.nav-sub-item`, `.sidebar-sub-item`, `.login-card`, `.sc-prod-banner`,
   `.template-old-op-table` (12px và 6px), `.nav-menu-panel`,
   `.drawer-timeline-item`. Tôi **không** mở rộng guard dùng chung trong lane
   này: nó buộc phải migrate màn của lane khác. Đề nghị chủ design-system quyết.
   Trong lúc chờ, bài test DOM ở trên phủ 4 nhóm màn hp3.
2. **`.se-summary article` không nằm trong rule quét** trong khi
   `.catalog-summary article` / `.system-user-summary article` /
   `.employee-summary article` đều có. Tôi đặt token trực tiếp cho nó thay vì
   thêm vào rule quét — thêm vào rule quét sẽ ép luôn `border`/`background`/
   `box-shadow` `!important`, đổi nhiều hơn bo góc. Nên là quyết định của chủ
   design-system.
3. **`.table-wrap` (global primitive) đang `--radius-panel`.** Nó là vỏ bảng,
   đáng ra `--radius-surface`. Không sửa vì nó dùng chung toàn app → đổi là thay
   đổi thị giác toàn repo, vượt phạm vi 4 nhóm màn.
4. **`.dash-*` chết hẳn** (`.dash-hero`, `.dash-tabs`, `.dash-po-card`, …):
   không JS nào tham chiếu — là **bộ tab thứ ba** nằm chờ ai copy nhầm. Chưa xoá
   vì `.dash-metric` đang bị `card-surface-contract.spec.js` gọi tên.
5. **Hover trên dòng danh sách gần như không có** (chỉ `.ec-card`, lại viết cứng
   `#5f829b`). `DESIGN.md §5.5` yêu cầu "hover row nhẹ". Thêm hover là *thiết kế
   mới*, không phải thống nhất.
6. **`.ec-status` `3px`** — huy hiệu inline, thuộc nhóm phần tử nhỏ; để nguyên
   thay vì đổi bừa sang một bậc không dành cho nó.

## 5. Rollback

Revert commit. Chỉ đụng lớp trình bày: không đổi business logic, API, payload,
`role`/`aria-*` (spec khoá luôn điều đó).
