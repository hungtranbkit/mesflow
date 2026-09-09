"""SETUP là công đoạn hỗ trợ độc lập, KHÔNG phải điều kiện tiên quyết.

Quyết định nghiệp vụ (2026-09-09, do người dùng chốt): một OP sản xuất LUÔN bắt
đầu được, dù OP setup liên quan chưa chạy. SETUP chỉ là một Operation hỗ trợ
gắn với OP chính; nó ghi nhận CÔNG (thời gian lao động vẫn tính) nhưng không
ghi nhận sản lượng, không vào WIP, không vào điều kiện hoàn thành.

Trước đó hệ thống coi setup là tiên quyết: kiosk trả 409 SETUP_REQUIRED, giao
diện nói "Yêu cầu setup máy trước khi sản xuất" và "Sản xuất đang bị chặn", có
cả khái niệm hết hạn setup và nút reset. Toàn bộ đã gỡ.

Bài test này canh chừng chiều NGƯỢC LẠI: ngăn một thay đổi sau này vô tình dựng
lại ngữ nghĩa cũ. Nó kiểm chữ vì chữ chính là thứ người vận hành đọc, và vì một
lần trượt về wording cũ là dấu hiệu đầu tiên cho thấy ai đó đang nghĩ lại theo
mô hình tiên quyết.

Chú thích được phép nhắc tới ngữ nghĩa cũ -- ghi lại vì sao đã bỏ là điều nên
làm. Chỉ chuỗi hiển thị và mã lỗi mới bị cấm.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Chữ của mô hình tiên quyết cũ. Xuất hiện lại nghĩa là ngữ nghĩa đã trượt về.
FORBIDDEN_WORDING = (
    'Yêu cầu setup máy trước khi sản xuất',
    'Sản xuất đang bị chặn',
    'Yêu cầu setup lại',
    'Cần setup trước',
    'setup chưa hoàn tất nên không thể bắt đầu',
)

#: Mã lỗi/khoá của mô hình cũ. Chúng nằm trong giao thức nên nguy hiểm hơn chữ.
FORBIDDEN_CODES = ('SETUP_REQUIRED', 'setup_expiry', 'setup_expires_at', 'requires_setup_before_start')

SCAN = (
    'app/mesflow/web/static/app.js',
    'app/mesflow/web/static/ui.css',
    'app/mesflow/web/kiosk.py',
    'app/mesflow/web/kiosk_v2.py',
    'app/mesflow/web/execution.py',
    'app/mesflow/db/repositories/production_state.py',
    'app/mesflow/db/repositories/setup_ops.py',
)


def _code_only(path: pathlib.Path) -> str:
    """Bỏ chú thích. Ghi lại bài học không được tính là vi phạm."""
    lines = []
    for line in path.read_text(encoding='utf-8').split('\n'):
        stripped = line.lstrip()
        if stripped.startswith(('#', '//', '*', '/*')):
            continue
        lines.append(line)
    return '\n'.join(lines)


@pytest.mark.parametrize('phrase', FORBIDDEN_WORDING)
def test_old_prerequisite_wording_is_gone(phrase):
    offenders = [rel for rel in SCAN
                 if (ROOT / rel).exists() and phrase.lower() in _code_only(ROOT / rel).lower()]
    assert not offenders, (
        f'{phrase!r} là chữ của mô hình "setup là tiên quyết" đã bỏ: {offenders}')


@pytest.mark.parametrize('code', FORBIDDEN_CODES)
def test_old_prerequisite_codes_are_gone(code):
    offenders = [rel for rel in SCAN
                 if (ROOT / rel).exists() and code in _code_only(ROOT / rel)]
    assert not offenders, f'{code!r} thuộc giao thức cũ, đã gỡ: {offenders}'


def test_current_wording_is_the_neutral_one():
    """Chữ đang dùng phải nói về LIÊN QUAN, không nói về bắt buộc."""
    app = (ROOT / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    assert 'Có OP setup liên quan' in app, 'mất chữ trung tính hiện dùng cho trạng thái có setup'
    assert 'Không có OP setup liên quan' in app, 'mất chữ trung tính cho trạng thái không setup'


def test_starting_an_operation_never_consults_setup_state():
    """Guard bắt đầu session không được đọc trạng thái setup.

    Đây mới là bất biến thật; chữ chỉ là biểu hiện. lock_startable_operation()
    là cửa duy nhất cho mọi đường bắt đầu (kiosk v1/v2, API, đồng bộ offline),
    nên chỉ cần canh đúng chỗ này.
    """
    source = _code_only(ROOT / 'app/mesflow/db/repositories/production_state.py')
    start = source.index('def lock_startable_operation')
    end = source.find('\ndef ', start + 10)
    body = source[start:end if end > 0 else len(source)]
    for needle in ('requires_setup', 'setup_completed_at', 'setup_completed_session_id'):
        assert needle not in body, (
            f'{needle} xuất hiện trong guard bắt đầu -- setup lại thành tiên quyết')


def test_setup_operations_are_support_type_not_production():
    """SETUP phải là OP hỗ trợ theo policy chung, không đếm vào sản lượng."""
    from mesflow.domain.policy import is_production, is_support

    assert is_support('SETUP')
    assert not is_production('SETUP')
