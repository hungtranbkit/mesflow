"""Tổng thời gian gia công dự kiến của một Template: SỐ TỪ FILE và SỐ MESFLOW TỰ TÍNH.

CÔNG THỨC LẤY TỪ CHÍNH FILE CỦA KHÁCH, KHÔNG SUY DIỄN. Ô tổng trong biểu mẫu
GO ROUTER (cột M của mỗi block) mang đúng công thức Excel này -- đọc được bằng
openpyxl với ``data_only=False`` trên tests/fixtures/router-newark-arm-chair.xlsx,
block đầu của sheet 'Tay ghế - Trái':

    M14 = $I$4*L14/3600 + L11/60

với ``I4`` = SỐ LƯỢNG của tờ (110), ``L14`` = thời gian gia công mỗi sản phẩm
(70 giây), ``L11`` = thời gian Setup (15 PHÚT). Kết quả 2,3889 -- đơn vị GIỜ, đúng
như nhãn "Tổng thời gian gia công dự kiến ( giờ )". Quy về giây:

    total_seconds = qty * cycle_seconds_per_unit + setup_minutes * 60

Ba điều quan trọng, vì cả ba đều là chỗ dễ sai:

* Setup cộng MỘT LẦN cho cả lô, không nhân với qty. Công thức của khách chia
  ``L11/60`` (phút -> giờ) tách hẳn khỏi số nhân theo sản lượng.
* Chỉ nhân qty MỘT LẦN. ``standard_seconds_per_unit`` đã là "mỗi sản phẩm".
* Đơn vị mỗi thành phần khác nhau ngay trong một ô: cycle tính bằng GIÂY, setup
  bằng PHÚT, tổng bằng GIỜ. Ở đây mọi thứ quy về GIÂY và chỉ đổi khi hiển thị.

SỐ NGUỒN thì đã được nhập sẵn: `_block_labeled_time` đọc ô tổng đó lúc import và
lưu vào ``template_operations.expected_total_seconds`` (migration 0052). Trước bản
vá này chưa có chỗ nào ĐỌC nó ra -- router_import.py:236 đã ghi thẳng điều đó
("Được LƯU làm số liệu nguồn nhưng chưa có [nơi dùng]").

VÌ SAO PHẢI GIỮ CẢ HAI SỐ, KHÔNG CHỌN MỘT. Đối chiếu trên file thật 44 sheet /
112 block cho thấy chúng LỆCH NHAU THẬT, và chỗ lệch có ý nghĩa:

    Excel  (tổng 112 ô)                    1.111.110 s = 308,64 h
    MESFlow tính lại                       1.006.610 s = 279,61 h
    lệch                                    -104.500 s = -29,03 h  (-9,4%)

107/112 block khớp chính xác. Cả 5 block lệch đều nằm ở đúng một chỗ: công thức
Excel của riêng chúng có thêm MỘT HỆ SỐ, viết thẳng trong công thức và không nằm
trong bất kỳ ô nào:

    'Lắp ráp sau khi sơn'!M14 = $I$4*L14*10/3600 + L11/60     <- nhân 10
    'Lắp ráp sau khi sơn'!M38 = $I$4*L38*10/3600 + L35/60     <- nhân 10
    'Đóng gói'!M14            = $I$4*L14*2/3600  + L11/60     <- nhân 2

Đó là số lượng chi tiết trên mỗi sản phẩm (BOM). Trình đọc file chỉ thấy giá trị
các ô (cycle, setup, qty) chứ không thấy hệ số nằm trong công thức, nên MESFlow
KHÔNG THỂ tự tính ra con số của khách ở những block ấy. Vì vậy:

  * số NGUỒN là số của khách, dùng để đối chiếu và để tin;
  * số TÍNH LẠI là số theo dữ liệu MESFlow đang thực sự nắm;
  * ĐỘ LỆCH chính là thứ đáng xem -- nó chỉ ra đúng những công đoạn có hệ số BOM
    mà hệ thống chưa mô hình hoá. Che nó đi bằng cách chỉ hiện một số là bỏ mất
    tín hiệu duy nhất cho biết dữ liệu còn thiếu gì.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

#: Dưới ngưỡng này coi như khớp. Ô tổng của khách là số thực đã làm tròn khi
#: hiển thị (2,3889 giờ), nên vài giây chênh do dấu phẩy động không phải sai
#: lệch dữ liệu. Lấy số lớn hơn giữa 60 giây và 0,5% -- 0,5% một mình thì quá
#: chặt với Template nhỏ, 60 giây một mình thì quá lỏng với Template lớn.
TOLERANCE_SECONDS = 60.0
TOLERANCE_RATIO = 0.005


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def operation_expected_seconds(quantity: Any, cycle_seconds_per_unit: Any,
                               setup_minutes: Any) -> float:
    """Thời gian dự kiến của MỘT công đoạn, theo đúng công thức trong file khách.

    Setup cộng một lần cho cả lô; cycle nhân đúng một lần với sản lượng.
    """
    return _number(quantity) * _number(cycle_seconds_per_unit) + _number(setup_minutes) * 60.0


def summarize(parts: Iterable[Mapping[str, Any]],
              operations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Gộp hai con số cho một Template, kèm độ lệch.

    `parts` cần `id` và `planned_quantity`; `operations` cần `part_id`,
    `standard_seconds_per_unit`, `expected_setup_minutes` và (nếu có)
    `expected_total_seconds` -- đúng các cột `SELECT *` của template_operations
    đã trả về.

    Sản lượng lấy theo PART, không theo PO: biểu mẫu ghi SỐ LƯỢNG trên từng tờ
    (`$I$4`), và một Part dùng nhiều lần trên một sản phẩm có số lượng riêng.
    """
    quantity_by_part = {p.get('id'): _number(p.get('planned_quantity')) for p in parts}

    calculated = 0.0
    source = 0.0
    source_count = 0
    total_count = 0
    offenders: list[dict[str, Any]] = []
    for op in operations:
        total_count += 1
        own = operation_expected_seconds(
            quantity_by_part.get(op.get('part_id')),
            op.get('standard_seconds_per_unit'),
            op.get('expected_setup_minutes'))
        calculated += own
        raw = op.get('expected_total_seconds')
        if raw is None:
            continue
        own_source = _number(raw)
        source += own_source
        source_count += 1
        # CHẨN ĐOÁN, không phải sửa số. Nếu ô tổng của khách lớn hơn số ta tính
        # đúng một BỘI SỐ NGUYÊN, thì phần thiếu là số lượng chi tiết trên mỗi
        # sản phẩm -- hệ số nằm trong công thức Excel và không có trong ô nào,
        # nên ta không đọc được nó, chỉ suy ra được. Nói ra hệ số ấy biến "chênh
        # 29 giờ" thành "5 công đoạn có hệ số x2/x4/x10", tức là một việc làm
        # được. Cố ý KHÔNG nhân nó vào `calculated`: làm thế thì hai số luôn
        # bằng nhau và mất sạch tín hiệu cho biết dữ liệu còn thiếu.
        if abs(own - own_source) <= 1.0 or own <= 0:
            continue
        factor = own_source / own
        rounded = round(factor)
        offenders.append({
            'code': op.get('code') or '',
            'name': op.get('name') or '',
            'calculated_seconds': round(own, 3),
            'source_seconds': round(own_source, 3),
            'delta_seconds': round(own - own_source, 3),
            'implied_multiplier': rounded if rounded >= 2 and abs(factor - rounded) <= 0.01 else None,
            # VỊ TRÍ TRÊN TỜ GIẤY (migration 0053). Không có nó, người dùng cầm
            # mã Operation rồi phải dò tay 44 sheet. Có thể là None với Template
            # nhập trước 0053 -- màn hình khi đó chỉ bỏ phần vị trí đi.
            'sheet': op.get('source_sheet') or None,
            'row_start': op.get('source_row_start'),
            'row_end': op.get('source_row_end'),
            'cell': op.get('expected_total_cell') or None,
            'formula': op.get('expected_total_formula') or None,
        })

    has_source = source_count > 0
    delta = (calculated - source) if has_source else 0.0
    tolerance = max(TOLERANCE_SECONDS, source * TOLERANCE_RATIO)
    return {
        'calculated_seconds': round(calculated, 3),
        'source_seconds': round(source, 3) if has_source else None,
        'delta_seconds': round(delta, 3) if has_source else None,
        'has_source': has_source,
        # Số công đoạn thực sự mang số nguồn. Một Template nhập từ biểu mẫu cũ
        # (hoặc dựng tay trên web) có thể có 0, hoặc chỉ một phần -- và "một
        # phần" là ca dễ hiểu nhầm nhất, nên nói rõ ra thay vì để người đọc
        # tưởng tổng nguồn phủ hết mọi công đoạn.
        'source_operation_count': source_count,
        'operation_count': total_count,
        'source_is_partial': has_source and source_count < total_count,
        'tolerance_seconds': round(tolerance, 3),
        'mismatch': bool(has_source and abs(delta) > tolerance),
        # Chỉ những công đoạn thực sự lệch, kèm hệ số suy ra được. Cắt ở 20 để
        # một Template hỏng nặng không biến phản hồi API thành một bãi dữ liệu.
        'mismatch_operations': sorted(
            offenders, key=lambda o: abs(o['source_seconds'] - o['calculated_seconds']),
            reverse=True)[:20],
        'mismatch_operation_count': len(offenders),
    }
