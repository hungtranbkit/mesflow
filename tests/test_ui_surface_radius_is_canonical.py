"""Cùng một loại surface phải có cùng hình khối, và điều đó được MÁY giữ.

Vì sao bài test này tồn tại: MESFlow đã qua nhiều đợt audit UI thủ công mà
list/card giữa các màn vẫn lệch nhau -- chỗ bo tròn, chỗ vuông. Nguyên nhân đo
được (2026-09-11), không phải phỏng đoán:

  * ``.card,.panel`` được BỐN rule khác nhau đặt bo góc: 14px, var(--radius-panel),
    và hai rule ``!important``. Giá trị thắng phụ thuộc thứ tự và !important.
  * Đã tồn tại một rule quét ``.admin-body :where(.card,[class$="-card"],...)``
    dùng ``!important`` -- tức cơ chế cưỡng chế CÓ SẴN -- nhưng nó ép về
    ``--radius-card`` = 7px, trong khi mọi tác giả đều viết 12-14px tại chỗ.
    Nên người sửa một màn thấy mình viết 14px, chạy lên ra 7px, rồi thêm một
    rule nữa. Vòng lặp đó là thứ sinh ra sự lệch.

Bài test khoá hai điều, và chỉ hai điều:

  1. Thang bo góc là CANONICAL: chỉ ba bậc surface/surface-row/control được
     dùng cho surface, không ai được đẻ thêm bậc bằng số cứng.
  2. Một surface KHÔNG được tự đặt bo góc. Hình khối đến từ rule quét chung.

Cố tình để một màn quay về vuông, hoặc đặt một radius riêng -> đỏ, và thông báo
nói đúng tên selector.
"""
from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / 'app' / 'mesflow' / 'web' / 'static' / 'ui.css'

#: Ba bậc canonical. Thêm bậc thứ tư là một quyết định thiết kế, không phải
#: một dòng CSS -- nên nó phải đi qua việc sửa chính bài test này.
CANONICAL_TOKENS = {
    '--radius-surface',       # card, list item, panel, section, vỏ bảng
    '--radius-surface-row',   # khối lồng bên trong một surface
    '--radius-control',       # input, select, button, chip
}

#: Lớp phủ (modal/sheet) là một BẬC RIÊNG hợp lệ, không phải khối nội dung: nó
#: nổi trên mặt phẳng khác nên được mềm hơn một chút. Có token riêng từ trước.
OVERLAY_TOKEN = '--radius-overlay'
OVERLAY_SELECTOR = re.compile(r'modal|-sheet\b', re.IGNORECASE)

#: Tên cũ, còn dùng cho phần tử NHỎ (icon sidebar, thanh gantt, huy hiệu).
#: Không cấm, nhưng không được xuất hiện trên một surface nội dung.
LEGACY_TOKENS = {'--radius-card', '--radius-panel', '--radius-row'}

#: Hình dạng chủ ý, không phải bậc thang: viên thuốc, hình tròn, góc phẳng,
#: và bo một phía (dropdown dính mép, sheet trượt từ dưới lên).
INTENTIONAL_SHAPES = re.compile(r'^(999px|50%|0|0!important|[0-9.]+px [0-9.]+px 0 0|0 0 [0-9.]+px [0-9.]+px)$')

RULE = re.compile(r'([^{}]+)\{([^{}]*)\}')
COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)

#: Một selector là "surface" khi PHẦN TỬ CUỐI của nó đặt tên cho một khối nội
#: dung. Xét phần tử cuối chứ không phải cả chuỗi: `.ct-tree-panel input` nói về
#: một ô nhập nằm TRONG panel, không phải về panel.
#: Là danh sách hậu tố chứ không phải danh sách tên -- một màn mới thêm
#: `.foo-card` tự nằm trong tầm, không ai phải nhớ cập nhật gì.
SURFACE_SUFFIX = re.compile(r'(-card|-panel|-section)$|^\.(card|panel)$')


def _is_surface(selector: str) -> bool:
    for one in selector.split(','):
        last = re.split(r'[ >+~]', one.strip())[-1]
        last = re.sub(r'[:.\[][^.]*$', '', last) if last.startswith('.') and (':' in last) else last
        if SURFACE_SUFFIX.search(last.strip()):
            return True
    return False

#: Ngoại lệ CÓ CHỦ ĐÍCH, mỗi dòng kèm lý do. Danh sách này phải ngắn; nó dài ra
#: là dấu hiệu thang bậc chưa mô tả đúng thực tế, không phải cớ để thêm ngoại lệ.
ALLOWED_SELF_RADIUS = {
    # Trang đăng nhập không nằm trong .admin-body nên rule quét không với tới;
    # nó cũng cố ý mềm hơn phần quản trị.
    '.login-card': 'trang đăng nhập, ngoài .admin-body',
    '.login-card input,.modal input,.modal select,.modal textarea': 'điều khiển trang đăng nhập',
    '.login-card button,.primary': 'điều khiển trang đăng nhập',
    # Bo một phía: dính vào mép trên/dưới của phần tử khác.
    '.nav-menu-panel': 'dropdown dính mép dưới thanh nav, chỉ bo hai góc dưới',
    '.sl-inline-box': 'khối inline dính mép dưới hàng, chỉ bo hai góc dưới',
    '.session-edit-card': 'sheet trượt lên từ đáy trên màn nhỏ, chỉ bo hai góc trên',
    '.shift-edit-card': 'sheet trượt lên từ đáy trên màn nhỏ, chỉ bo hai góc trên',
    '.employee-report-modal': 'sheet trượt lên từ đáy trên màn nhỏ, chỉ bo hai góc trên',
    # Bảng nằm sát mép trong panel: bo góc sẽ hở viền.
    '.content-panel-body>.table-wrap': 'bảng nằm sát mép trong panel, cố ý phẳng',
}


def _rules():
    css = COMMENT.sub('', CSS.read_text(encoding='utf-8'))
    for match in RULE.finditer(css):
        yield match.group(1).strip(), match.group(2)


def _radius_of(body: str) -> str | None:
    found = re.search(r'border-radius:\s*([^;}]+)', body)
    return found.group(1).strip() if found else None


def test_the_canonical_radius_scale_is_defined_exactly_once():
    css = CSS.read_text(encoding='utf-8')
    for token in CANONICAL_TOKENS:
        declarations = re.findall(rf'{re.escape(token)}\s*:', css)
        assert len(declarations) == 1, (
            f'{token} được định nghĩa {len(declarations)} lần -- thang bậc phải có '
            'đúng một nguồn sự thật')


def test_no_surface_invents_its_own_radius_value():
    """Surface phải lấy giá trị TỪ THANG, không được tự đặt số.

    Khai báo `border-radius:var(--radius-surface)` là ĐÚNG -- nhiều surface nằm
    ngoài tầm rule quét nên buộc phải tự khai. Thứ bị cấm là tự phát minh một
    con số: đó là cách bậc thứ tư, thứ năm ra đời và hai màn cùng loại lệch nhau.
    """
    offenders = []
    for selector, body in _rules():
        radius = _radius_of(body)
        if radius is None:
            continue
        if selector in ALLOWED_SELF_RADIUS or selector.startswith('@'):
            continue
        if not _is_surface(selector):
            continue
        # Rule quét chung chính là nơi được phép đặt.
        if ':where(' in selector and '!important' in body:
            continue
        if INTENTIONAL_SHAPES.match(radius):
            continue
        if 'var(--radius-' in radius:
            continue          # lấy từ thang -- bậc nào là việc của bài test kia
        offenders.append(f'{selector[:80]}  ->  border-radius: {radius}')

    assert not offenders, (
        'Các surface sau tự đặt một con số bo góc thay vì dùng thang canonical:\n  '
        + '\n  '.join(offenders)
        + '\n\nDùng var(--radius-surface) cho khối ngoài, var(--radius-surface-row) '
          'cho khối lồng. Nếu màn này thật sự phải khác, thêm vào ALLOWED_SELF_RADIUS '
          'kèm LÝ DO -- việc phải sửa bài test là điểm dừng để cân nhắc, không phải '
          'thủ tục.')


def test_surfaces_never_use_the_legacy_small_element_tokens():
    """--radius-card/panel/overlay giờ phục vụ phần tử NHỎ, không phải khối nội dung.

    Dùng chúng cho một surface là cách sự lệch quay lại: hai màn cùng loại sẽ
    lấy hai bậc khác nhau mà không ai thấy sai ở chỗ nào.
    """
    offenders = []
    for selector, body in _rules():
        radius = _radius_of(body)
        if radius is None or selector.startswith('@'):
            continue
        if selector in ALLOWED_SELF_RADIUS:
            continue
        if not _is_surface(selector):
            continue
        if OVERLAY_SELECTOR.search(selector) and OVERLAY_TOKEN in radius:
            continue          # modal/sheet: bậc riêng, hợp lệ
        for legacy in LEGACY_TOKENS:
            if legacy in radius:
                offenders.append(f'{selector[:70]}  ->  {radius}')
    assert not offenders, (
        'Surface đang dùng token của phần tử nhỏ:\n  ' + '\n  '.join(offenders)
        + '\n\nDùng --radius-surface (khối ngoài) hoặc --radius-surface-row (khối lồng).')


def test_the_shared_enforcement_rule_still_targets_the_canonical_token():
    """Rule quét là điểm cưỡng chế duy nhất -- nó trỏ sai thì cả hệ trôi theo.

    Đây đúng là thứ đã xảy ra: rule tồn tại, chạy đúng, nhưng ép về bậc của
    phần tử nhỏ, nên mọi thẻ ra 7px trong khi tác giả viết 14px.
    """
    css = COMMENT.sub('', CSS.read_text(encoding='utf-8'))
    sweep = re.search(r'\.admin-body :where\(\.card,\[class\$="-card"\][^{]*\{([^}]*)\}', css)
    assert sweep, 'không tìm thấy rule quét surface -- nó bị đổi tên hay gỡ?'
    body = sweep.group(1)
    assert 'border-radius:var(--radius-surface)!important' in body.replace(' ', ''), (
        'rule quét không còn trỏ vào --radius-surface:\n  ' + body[:200])


def test_only_a_real_overlay_may_use_the_overlay_tier():
    """--radius-overlay chỉ dành cho thứ NỔI trên mặt phẳng khác.

    Lỗ này nằm đúng giữa hai bài trên và đã để lọt 9 phần tử: chúng khai token
    TƯỜNG MINH nên không đi qua rule quét (bài "không tự đặt số" bỏ qua), mà
    cũng không phải số cứng (bài "không dùng token phần tử nhỏ" cũng bỏ qua).

    Cách chúng lọt vào cũng đáng ghi lại, vì nó sẽ lặp: `.kiosk-btn` từng là
    `border-radius:8px` viết cứng; một lane trước đổi nó sang
    `var(--radius-overlay)` để qua bài lint token, và chọn `overlay` CHỈ VÌ giá
    trị lúc đó khớp 9px -- không vì ngữ nghĩa. Đến khi bậc overlay được nâng lên
    16px cho modal, chín phần tử không-modal đi ké. Chọn token theo giá trị
    trùng thay vì theo nghĩa là một lỗi im lặng cho tới lần đổi giá trị kế tiếp.

    Nên bài này kiểm NGỮ NGHĨA chứ không kiểm giá trị: tên selector phải nói nó
    là lớp phủ.
    """
    overlay_like = re.compile(r'modal|sheet|overlay|dropdown|menu|popover|tooltip|backdrop',
                              re.IGNORECASE)
    # Lớp phủ mà TÊN không tự nói ra. Danh sách phải ngắn: một tên mới đặt đúng
    # thì không cần có mặt ở đây.
    overlay_by_name = {'.shift-edit-card', '#shiftEditor>.shift-edit-card'}
    offenders = []
    for selector, body in _rules():
        radius = _radius_of(body)
        if radius is None or '--radius-overlay' not in radius:
            continue
        if selector.startswith('@'):
            continue
        # Đủ khi MỌI phần trong danh sách selector đều là lớp phủ; một cái không
        # phải là đã kéo cả nhóm đi theo.
        parts = [p.strip() for p in selector.split(',') if p.strip()]
        if parts and all(overlay_like.search(p) or p in overlay_by_name for p in parts):
            continue
        offenders.append(f'{selector[:80]}  ->  {radius}')

    assert not offenders, (
        'Các selector sau dùng bậc lớp phủ nhưng không phải lớp phủ:\n  '
        + '\n  '.join(offenders)
        + '\n\nChọn bậc theo NGHĨA, không theo giá trị nào đang khớp: nút -> '
          '--radius-control, khối nội dung -> --radius-surface, khối lồng -> '
          '--radius-surface-row. Chỉ modal/sheet/dropdown mới là --radius-overlay.')
