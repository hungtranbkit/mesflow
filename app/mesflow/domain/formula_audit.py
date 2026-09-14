"""Bắt công thức Excel bị copy mà quên bỏ khoá dòng ($L$11).

VÌ SAO CÓ FILE NÀY. Mỗi block OPERATION cao 12 dòng và ô tổng của nó phải cộng
thời gian Setup CỦA CHÍNH BLOCK ĐÓ:

    M74 = $I$4*L74/3600 + L71/60      <- 71 = 74-3, đúng dòng Setup của block

Khi người soạn copy ô tổng của block đầu xuống block dưới mà tham chiếu bị khoá
dòng, phần Setup không trôi theo:

    M86 = $I$4*L86/3600 + L$11/60     <- vẫn là Setup của block ĐẦU TIÊN (dòng 11)

Ô vẫn ra một con số trông hợp lý, nên không ai thấy. Trên file NEWARK ARM CHAIR
thật có 4 ô như vậy; 2 trong số đó đang lệch 15 phút mỗi ô, 2 ô còn lại chỉ
đúng nhờ MAY MẮN -- hai ô Setup liên quan tình cờ cùng bằng 0. Sửa một trong hai
ô Setup đó là số nhảy sai ngay, vẫn không có cảnh báo nào.

KHÔNG BẮT BỪA. Điều kiện duy nhất để báo là: tham chiếu Setup trong công thức
TRỎ VÀO Ô KHÁC với ô Setup của chính block đang xét. Cùng file đó có 12 ô viết
`$L$11` hoàn toàn hợp lệ -- chúng nằm ở block bắt đầu dòng 8, nơi L11 CHÍNH LÀ
ô Setup của nó. Vì so theo ô chứ không theo hình dạng chuỗi, 12 ô ấy im lặng đi
qua, kể cả khi chúng khoá `$`.

Đây là CHẨN ĐOÁN cho người dùng sửa file nguồn. Không tự sửa workbook, không
đụng số nghiệp vụ: MESFlow vẫn đọc ô Setup đúng của từng block như trước.
"""
from __future__ import annotations

import re

#: Số hạng Setup trong ô tổng: '+ L71/60', '+ L$11/60', '+ $L$11/60'.
#: Chia 60 vì ô Setup ghi bằng PHÚT còn ô tổng tính bằng GIỜ.
_SETUP_TERM = re.compile(r'\+\s*(\$?)([A-Z]{1,3})(\$?)(\d+)\s*/\s*60')
_CELL = re.compile(r'^([A-Z]{1,3})(\d+)$')

#: Công thức trỏ sang sheet khác ('Chân ghế A'!L11) là chuyện khác hẳn -- có
#: thể cố ý -- và ngoài phạm vi bản vá này. Bỏ qua, không đoán.
_CROSS_SHEET = re.compile(r"[!']")

SEVERITY_ERROR = 'ERROR'
SEVERITY_WARNING = 'POTENTIAL_ERROR'


def _split(cell):
    m = _CELL.match(str(cell or '').strip().upper())
    return (m.group(1), int(m.group(2))) if m else (None, None)


def audit_total_formula(*, sheet, block_start, block_end, total_cell, formula,
                        setup_cell, value_at):
    """Một block, một kết luận. None = không có gì để báo.

    `value_at(cell)` trả giá trị số của ô (workbook data_only) hoặc None; chỉ
    dùng để phân biệt "đang sai kết quả" với "công thức sai nhưng chưa lệch".
    Detector không cần nó để phát hiện lỗi, nên value_at hỏng cũng không làm
    mất finding -- chỉ làm nó thành cảnh báo nhẹ hơn.
    """
    text = str(formula or '').strip()
    if not text.startswith('=') or not setup_cell or not total_cell:
        return None
    m = _SETUP_TERM.search(text)
    if not m:
        return None
    # Cắt đúng đoạn khớp để xét dấu '!' -- '=$I$4*L86/3600+L$11/60' không có,
    # còn "+'Chân ghế A'!L11/60" thì có, và ta không đụng vào loại đó.
    if _CROSS_SHEET.search(text[max(0, m.start() - 40):m.end()]):
        return None
    ref_col, ref_row = m.group(2), int(m.group(4))
    own_col, own_row = _split(setup_cell)
    if own_col is None:
        return None
    if (ref_col, ref_row) == (own_col, own_row):
        return None                        # đúng ô Setup của block -- PASS.

    ref_cell = f'{ref_col}{ref_row}'
    ref_value = value_at(ref_cell)
    own_value = value_at(setup_cell)
    used = float(ref_value) if isinstance(ref_value, (int, float)) else None
    correct = float(own_value) if isinstance(own_value, (int, float)) else None
    # Chênh do CHỈ số hạng Setup gây ra: hai công thức khác nhau đúng một số
    # hạng, nên hiệu của chúng là hiệu của hai ô Setup, đổi phút ra giây.
    delta_seconds = None
    if used is not None and correct is not None:
        delta_seconds = (correct - used) * 60.0
    if delta_seconds is None:
        # Không đọc được giá trị: công thức vẫn sai cấu trúc, cứ báo, nhưng
        # không dám khẳng định là đang lệch.
        severity = SEVERITY_WARNING
    elif abs(delta_seconds) >= 1.0:
        severity = SEVERITY_ERROR
    else:
        severity = SEVERITY_WARNING
    return {
        'kind': 'ABSOLUTE_SETUP_REF_FROM_OTHER_BLOCK',
        'severity': severity,
        'sheet': sheet,
        'row_start': block_start,
        'row_end': block_end,
        'cell': total_cell,
        'formula': text,
        'suspect_ref': m.group(0).strip(),
        'suspect_cell': ref_cell,
        'expected_cell': setup_cell,
        'suspect_value': used,
        'expected_value': correct,
        'delta_seconds': delta_seconds,
        # Ô đang bị trỏ nằm ngoài block: dấu hiệu chắc chắn của copy-paste,
        # nói ra để người đọc biết vì sao hệ thống dám kết luận.
        'ref_outside_block': not (block_start <= ref_row <= (block_end or block_start)),
    }


def message_vi(issue):
    """Một câu người dùng đọc được, dùng chung cho preview, import và log."""
    where = f"Sheet '{issue['sheet']}' block dòng {issue['row_start']}–{issue['row_end']}, ô {issue['cell']}"
    what = (f"công thức lấy Thời gian Setup ở {issue['suspect_cell']} "
            f"(block khác) thay vì {issue['expected_cell']} của chính block này")
    if issue['delta_seconds'] is None:
        impact = 'chưa đọc được giá trị hai ô nên không tính được chênh lệch'
    elif abs(issue['delta_seconds']) >= 1.0:
        impact = (f"đang tính SAI: Setup {issue['suspect_value']} phút thay vì "
                  f"{issue['expected_value']} phút, lệch "
                  f"{abs(issue['delta_seconds']) / 60:.0f} phút cho công đoạn này")
    else:
        impact = ('hiện chưa lệch vì hai ô Setup tình cờ bằng nhau '
                  f"({issue['expected_value']} phút) — sửa một trong hai ô là sai ngay")
    return f'{where}: {what}; {impact}. Sửa công thức trong file Excel rồi nhập/phân tích lại.'
