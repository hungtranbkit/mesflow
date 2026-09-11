"""Mỗi yêu cầu trong phần thân phải có ít nhất một dòng ở ma trận truy vết §19.

BÀI TEST NÀY KHÔNG KIỂM HÀNH VI. Nó ngăn một loại thiếu sót đã xảy ra HAI LẦN
trong cùng một batch TEST (2026-09-11):

  * REQ-QR-001 được thêm vào §15.6 mà không có dòng nào ở bảng §19;
  * REQ-PO-005 của lane khác, y hệt.

Hai lần trong một batch thì không còn là bất cẩn cá nhân. Nó là hệ quả của việc
yêu cầu và bảng truy vết nằm cách nhau hơn 800 dòng trong cùng một file: người
thêm yêu cầu đọc §15, và không có gì nhắc họ rằng §19 tồn tại.

Vì sao thiếu sót này đắt hơn vẻ ngoài: một yêu cầu vắng mặt ở §19 KHÔNG hiện ra
là "chưa có coverage" -- nó không hiện ra chút nào. QA đọc ma trận để biết chỗ
nào cần viết test; một dòng không tồn tại thì không ai đi tìm, và yêu cầu đó
lặng lẽ không bao giờ được kiểm. Trạng thái "—" (chưa có test) là một câu trả
lời hợp lệ và hữu ích; vắng mặt thì không.

Bài test chấp nhận đúng những cách viết mà ma trận đang dùng thật -- khoảng
(`REQ-AUTH-001..003`), liệt kê (`REQ-SYS-001/002`), và ký tự đại diện theo nhóm
(`REQ-EMP-*`) -- nên nó không ép ai phải liệt kê từng mã một.
"""
from __future__ import annotations

import re
from pathlib import Path

DOC = Path(__file__).resolve().parents[1] / 'docs' / 'MESFLOW_MASTER_REQUIREMENTS_VI.md'

#: Tiêu đề yêu cầu trong phần thân, ví dụ "### REQ-QR-001 — ...".
BODY_HEADING = re.compile(r'^###\s+(REQ-[A-Z]+-[0-9]+)', re.MULTILINE)

#: Yêu cầu UI/UX ở Phần D được khai bằng DÒNG BẢNG (`| REQ-UI-006 | mô tả |`)
#: chứ không phải tiêu đề. Chúng vẫn là yêu cầu đã khai báo.
TABLE_DECLARATION = re.compile(r'^\|\s*(REQ-[A-Z]+-[0-9]+)\s*\|', re.MULTILINE)

#: Nơi ma trận bắt đầu.
MATRIX_MARKER = 'Ma Trận Truy Vết'


def _split_document(text: str) -> tuple[str, str]:
    """Tách (phần thân, CHỈ bảng ma trận).

    Vùng ma trận phải dừng ở phần kế tiếp. Bản đầu của bài test này lấy mọi thứ
    sau mốc, nên nó nuốt luôn PHẦN G -- nơi văn bản hướng dẫn có nhắc
    `REQ-UI-006` như một ví dụ -- rồi báo đó là "ma trận trỏ tới yêu cầu không
    tồn tại". Một lời nhắc trong văn xuôi không phải một dòng khai coverage.
    """
    index = text.find(MATRIX_MARKER)
    assert index > 0, f'không tìm thấy mốc {MATRIX_MARKER!r} -- ma trận §19 đã bị đổi tên hay gỡ?'
    rest = text[index:]
    end = rest.find('\n# PHẦN', 1)
    matrix = rest if end < 0 else rest[:end]
    return text[:index], matrix


def _covered_ids(matrix: str) -> set[str]:
    """Bung mọi cách viết trong ma trận thành một tập mã cụ thể.

    Ký tự đại diện được trả về ở dạng ``REQ-EMP-*`` và so khớp riêng bên dưới,
    vì nó phủ những mã chưa tồn tại vào lúc ai đó viết dòng ấy -- đó là chủ ý,
    không phải cẩu thả.
    """
    covered: set[str] = set()
    for prefix in re.findall(r'\b(REQ-[A-Z]+)-\*', matrix):
        covered.add(f'{prefix}-*')
    # Khoảng: REQ-AUTH-001..003
    for prefix, start, end in re.findall(r'\b(REQ-[A-Z]+)-([0-9]+)\.\.([0-9]+)', matrix):
        width = len(start)
        for number in range(int(start), int(end) + 1):
            covered.add(f'{prefix}-{number:0{width}d}')
    # Liệt kê: REQ-SYS-001/002 hoặc REQ-DASH-003/004/005
    for match in re.finditer(r'\b(REQ-[A-Z]+)-([0-9]+(?:/[0-9]+)+)', matrix):
        prefix = match.group(1)
        for number in match.group(2).split('/'):
            covered.add(f'{prefix}-{number}')
    # Mã đơn lẻ
    for single in re.findall(r'\b(REQ-[A-Z]+-[0-9]+)\b', matrix):
        covered.add(single)
    return covered


def test_every_requirement_in_the_body_has_a_row_in_the_traceability_matrix():
    text = DOC.read_text(encoding='utf-8')
    body, matrix = _split_document(text)

    declared = sorted(set(BODY_HEADING.findall(body)) | set(TABLE_DECLARATION.findall(body)))
    assert declared, 'không đọc được mã yêu cầu nào từ phần thân -- regex đã lệch khỏi tài liệu?'

    covered = _covered_ids(matrix)
    missing = [req for req in declared
               if req not in covered and f"{req.rsplit('-', 1)[0]}-*" not in covered]

    assert not missing, (
        'Các yêu cầu sau có trong phần thân nhưng KHÔNG có dòng nào ở ma trận truy vết §19:\n  '
        + '\n  '.join(missing)
        + '\n\nThêm một dòng cho mỗi mã vào bảng ở PHẦN F. Trạng thái "—" (chưa có '
          'coverage tự động) là câu trả lời hợp lệ -- điều không chấp nhận được là '
          'vắng mặt, vì khi đó QA không biết yêu cầu này tồn tại để đi tìm test cho nó.')


def test_the_matrix_does_not_cite_requirements_that_no_longer_exist():
    """Chiều ngược lại: ma trận không được trỏ tới yêu cầu đã bị gỡ.

    Một dòng trỏ tới mã không còn tồn tại cũng nói dối, chỉ theo hướng khác --
    nó khiến bảng trông phủ rộng hơn thực tế.
    """
    text = DOC.read_text(encoding='utf-8')
    body, matrix = _split_document(text)

    declared = set(BODY_HEADING.findall(body)) | set(TABLE_DECLARATION.findall(body))
    declared_prefixes = {req.rsplit('-', 1)[0] for req in declared}

    stale = sorted({
        cited for cited in _covered_ids(matrix)
        if not cited.endswith('-*') and cited not in declared
    })
    # Ký tự đại diện chỉ hợp lệ khi nhóm đó thật sự có yêu cầu nào.
    stale += sorted({
        cited for cited in _covered_ids(matrix)
        if cited.endswith('-*') and cited[:-2] not in declared_prefixes
    })

    assert not stale, (
        'Ma trận §19 trỏ tới các mã không có trong phần thân:\n  ' + '\n  '.join(stale)
        + '\nGỡ dòng đó, hoặc sửa lại mã cho đúng.')
