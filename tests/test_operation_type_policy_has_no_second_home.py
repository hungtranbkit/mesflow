"""Không còn nơi nào tự phân loại Operation ngoài mesflow.domain.policy.

Đây là bài kiểm chứng của B2. Các bài integration chứng minh HÀNH VI đúng ở
từng màn; bài này chứng minh không còn BẢN CHÉP nào để trôi ra xa nhau lần nữa.
Một bản chép không sai ngay -- nó sai vào lần sau, khi ai đó sửa policy và quên
mất còn một chỗ khác.

Chỉ soi chuỗi THẬT SỰ chạy: comment và docstring bị loại qua AST, nên tài liệu
vẫn được phép nhắc tới ``operation_type='SETUP'`` để giải thích.

Cố ý KHÔNG kiểm: cột sinh ``is_rework_op``. Firmware đang đọc nó trong payload
kiosk và đổi hợp đồng thiết bị nằm ngoài phạm vi; sự tương đương của nó với
policy đã được khoá riêng ở
tests/integration/test_operation_type_contract.py.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.static

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app' / 'mesflow'
POLICY = APP / 'domain' / 'policy.py'
JS_POLICY = APP / 'web' / 'static' / 'op-policy.js'

#: COALESCE(...operation_type,'PRODUCTION') viết tay -- phần mặc-định-là-sản-xuất
#: mới là chỗ dễ quên, và nó có tên rồi: policy.type_value_sql().
HANDWRITTEN_COALESCE = re.compile(r"COALESCE\(\s*[\w.]*operation_type\s*,\s*'PRODUCTION'\s*\)", re.I)
#: So sánh loại bằng literal trong SQL -- policy.type_is_sql()/type_in_sql().
HANDWRITTEN_TYPE_COMPARE = re.compile(r"operation_type\s*(=|<>|!=|\bIN\b)\s*\(?\s*'(PRODUCTION|SETUP|REWORK)'", re.I)


def _executed_strings(path: Path) -> list[tuple[int, str]]:
    """Mọi chuỗi trong file TRỪ docstring: đây là thứ thật sự chạy."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, 'body', None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            found.append((node.lineno, node.value))
        elif isinstance(node, ast.JoinedStr):
            text = ''.join(v.value for v in node.values
                           if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if text:
                found.append((node.lineno, text))
    return found


def _python_sources():
    for path in sorted(APP.rglob('*.py')):
        if path == POLICY or '__pycache__' in path.parts:
            continue
        yield path


def test_no_module_hand_writes_the_production_default_in_sql():
    offenders = []
    for path in _python_sources():
        for lineno, text in _executed_strings(path):
            if HANDWRITTEN_COALESCE.search(text):
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}')
    assert not offenders, (
        'COALESCE(operation_type,\'PRODUCTION\') viết tay -- dùng '
        'mesflow.domain.policy.type_value_sql() thay vì chép: ' + ', '.join(offenders))


def test_no_module_compares_the_operation_type_against_a_literal_in_sql():
    offenders = []
    for path in _python_sources():
        for lineno, text in _executed_strings(path):
            if HANDWRITTEN_TYPE_COMPARE.search(text):
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}')
    assert not offenders, (
        'so sánh operation_type với literal trong SQL -- dùng policy.type_is_sql() / '
        'type_in_sql() / production_only_sql(): ' + ', '.join(offenders))


def test_nobody_slices_the_policy_sql_string_to_drop_a_table_alias():
    """production_only_sql('') đã tự xử alias rỗng.

    Ba module từng cắt chuỗi kết quả của nó để bỏ dấu chấm thừa. Một mẹo chuỗi
    chép ba lần, hỏng lặng lẽ nếu ai đó đổi một ký tự trong policy.
    """
    offenders = [str(p.relative_to(ROOT)) for p in _python_sources()
                 if re.search(r"production_only_sql\(\s*''\s*\)\s*\[", p.read_text(encoding='utf-8'))]
    assert not offenders, offenders


def test_the_business_critical_consumers_import_the_policy():
    """Danh sách chốt: mỗi module quyết định sản-xuất/hỗ-trợ phải lấy từ policy."""
    required = [
        'db/repositories/analytics.py', 'db/repositories/execution.py',
        'db/repositories/production_state.py', 'db/repositories/rework.py',
        'db/repositories/setup_ops.py', 'db/repositories/master_data.py',
        'db/repositories/offline_sync.py', 'services/integrity_audit_service.py',
        'services/production_trace_service.py', 'web/excel_io.py', 'web/master_data.py',
        'web/kiosk.py',
    ]
    missing = [name for name in required
               if 'mesflow.domain.policy' not in (APP / name).read_text(encoding='utf-8')]
    assert not missing, f'các module này quyết định loại Operation mà không qua policy: {missing}'


# ------------------------------------------------------------------- phía JS

def test_no_browser_module_hand_writes_the_operation_type_test():
    """Trình duyệt không import được Python, nên nó có op-policy.js -- MỘT bản."""
    offenders = []
    static = APP / 'web' / 'static'
    for path in sorted(static.rglob('*.js')):
        if path == JS_POLICY:
            continue
        for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            code = line.split('//', 1)[0]
            if re.search(r"operation_type[^\n]{0,40}(===|==|!==|!=)\s*'(PRODUCTION|SETUP|REWORK)'", code) \
                    or re.search(r"operation_type\s*(\|\||\?\?)\s*'PRODUCTION'", code):
                offenders.append(f'{path.relative_to(ROOT)}:{lineno}')
    assert not offenders, (
        'JS tự kiểm loại Operation -- dùng OpPolicy (static/op-policy.js): ' + ', '.join(offenders))


def test_the_browser_policy_names_the_same_types_as_the_python_policy():
    import sys
    sys.path.insert(0, str(ROOT / 'app'))
    from mesflow.domain.policy import PRODUCTION_TYPE, REWORK_TYPE, SETUP_TYPE

    source = JS_POLICY.read_text(encoding='utf-8')
    for name, value in (('PRODUCTION', PRODUCTION_TYPE), ('SETUP', SETUP_TYPE), ('REWORK', REWORK_TYPE)):
        assert re.search(rf"var {name} = '{value}';", source), \
            f'op-policy.js không khớp policy cho {name}={value}'


def test_every_page_that_uses_the_browser_policy_actually_loads_it():
    templates = APP / 'web' / 'templates'
    users = {p.name for p in sorted((APP / 'web' / 'static').rglob('*.js'))
             if p != JS_POLICY and 'OpPolicy.' in p.read_text(encoding='utf-8')}
    assert users, 'không còn ai dùng OpPolicy -- gỡ module hoặc sửa bài test này'
    loaded = ' '.join(p.read_text(encoding='utf-8') for p in templates.glob('*.html'))
    assert '/static/op-policy.js' in loaded, 'op-policy.js không được nạp ở bất kỳ trang nào'
