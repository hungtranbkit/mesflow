"""Trạng thái PO và loại Operation chỉ được định nghĩa ở MỘT nơi.

Bối cảnh (2026-09-09). 'ACTIVE' không phải trạng thái PO hợp lệ -- tập thật là
DRAFT / PLANNED / RELEASED / IN_PROGRESS / PAUSED / COMPLETED / CANCELLED. Nó
xuất hiện trong scheduling.RUNNABLE_PO_STATUSES như một giá trị thừa vô hại
(không bao giờ khớp), rồi được chép sang bảy câu truy vấn ở analytics.py dưới
dạng ('IN_PROGRESS','ACTIVE','PAUSED').

Ở analytics thì nó không còn vô hại: bản chép ĐỔI CHỖ 'RELEASED' bằng 'ACTIVE'.
Một PO vừa được phát hành có trạng thái RELEASED nên không khớp bộ lọc nào, và
đơn giản là biến mất khỏi dashboard, tháp điều khiển, báo cáo tiến độ và cảnh
báo trễ hạn. Không có lỗi, không có dòng log -- chỉ là không thấy.

Đó là lý do bài test này kiểm NGUỒN chứ không kiểm hành vi: hành vi sai ở đây
trông y hệt "chưa có dữ liệu", nên không bài test hành vi nào bắt được nó một
cách đáng tin. Còn "có chuỗi 'ACTIVE' trong bộ lọc trạng thái PO" thì kiểm được
dứt khoát.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.static

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def _code_only(source: str) -> str:
    """Bỏ chú thích và docstring trước khi quét.

    Chú thích nhắc tới 'ACTIVE' để GIẢI THÍCH vì sao nó sai không phải là một
    bộ lọc. Quét cả chú thích thì bài test tự cấm việc ghi lại bài học -- đúng
    thứ ta muốn giữ.

    CHỈ bỏ dòng bắt đầu bằng '#'. Không đụng chuỗi ba nháy: các câu SQL của
    repository nằm trong đó, bỏ chúng đi là bỏ luôn thứ cần quét (đã dính một
    lần: bài test hoá ra không tìm thấy bộ lọc nào).
    """
    return '\n'.join(line for line in source.split('\n')
                      if not line.lstrip().startswith('#'))


def test_policy_module_matches_the_repository_allowed_statuses():
    """policy.ALL_PO_STATUSES phải khớp tập mà repository thực sự cho phép."""
    from mesflow.domain.policy import ALL_PO_STATUSES

    source = _read('app/mesflow/db/repositories/master_data.py')
    match = re.search(r"allowed_statuses\s*=\s*\{([^}]*)\}", source)
    assert match, 'không tìm thấy allowed_statuses trong master_data.py'
    declared = {s.strip().strip("'\"") for s in match.group(1).split(',') if s.strip()}
    assert declared == set(ALL_PO_STATUSES), (
        f'lệch nhau: repository={sorted(declared)} policy={sorted(ALL_PO_STATUSES)}')


def test_no_module_filters_production_orders_by_a_nonexistent_status():
    """Không file nào được lọc PO theo một trạng thái không tồn tại."""
    from mesflow.domain.policy import ALL_PO_STATUSES

    offenders = []
    for rel in ('app/mesflow/db/repositories/analytics.py',
                'app/mesflow/db/repositories/scheduling.py',
                'app/mesflow/db/repositories/production_state.py',
                'app/mesflow/web/master_data.py'):
        source = _code_only(_read(rel))
        # Bắt các bộ lọc dạng ('A','B','C') đứng cạnh status của PO.
        for match in re.finditer(r"(?:po\.status|production_orders?\.status|\bstatus)\s+IN\s+\(([^)]*)\)",
                                 source, re.IGNORECASE):
            values = {v.strip().strip("'\"").upper() for v in match.group(1).split(',') if v.strip()}
            # Chỉ xét bộ lọc viết bằng LITERAL. Placeholder (%s) và mảnh f-string
            # ({RUNNABLE_PO_PH}) lấy giá trị từ chính policy lúc chạy, nên nội
            # dung của chúng đã được các bài test khác trong file này khoá.
            if not values or not all(re.fullmatch(r'[A-Z_]+', v) for v in values):
                continue
            unknown = values - set(ALL_PO_STATUSES)
            if unknown:
                offenders.append(f'{rel}: {sorted(unknown)} trong {sorted(values)}')
    assert not offenders, 'lọc PO theo trạng thái không tồn tại:\n  ' + '\n  '.join(offenders)


def test_dashboard_filters_include_released():
    """RELEASED là PO đã phát hành -- dashboard bắt buộc phải thấy nó."""
    source = _code_only(_read('app/mesflow/db/repositories/analytics.py'))
    filters = re.findall(r"po\.status\s+IN\s+\(([^)]*)\)", source, re.IGNORECASE)
    assert filters, 'không tìm thấy bộ lọc trạng thái PO nào ở analytics.py'
    missing = [f for f in filters if 'RELEASED' not in f.upper()]
    assert not missing, (
        'bộ lọc dashboard bỏ sót RELEASED nên PO vừa phát hành không hiện ra:\n  '
        + '\n  '.join(missing))


def test_scheduling_does_not_keep_its_own_copy_of_the_status_sets():
    """Chép tay là cách 'ACTIVE' lan từ file này sang file khác."""
    source = _code_only(_read('app/mesflow/db/repositories/scheduling.py'))
    assert 'from mesflow.domain.policy import' in source, (
        'scheduling.py phải lấy tập trạng thái từ policy, không khai báo lại')
    assert "'ACTIVE'" not in source, "scheduling.py không được nhắc lại trạng thái PO ma 'ACTIVE'"


def test_operation_type_policy_answers_consistently():
    """Chỉ PRODUCTION mới tính vào sản lượng; None là dữ liệu cũ, vẫn sản xuất."""
    from mesflow.domain.policy import is_production, is_support, SUPPORT_TYPES

    assert is_production('PRODUCTION')
    assert is_production(None), 'cột thêm sau, dữ liệu cũ để trống đều là OP sản xuất'
    assert is_production('')
    assert is_production('production'), 'không phân biệt hoa thường'
    for support in SUPPORT_TYPES:
        assert is_support(support), support
        assert not is_production(support), support


def test_production_sql_fragment_matches_the_python_answer():
    """Mảnh SQL và hàm Python phải nói cùng một điều, nếu không lại lệch tiếp."""
    from mesflow.domain.policy import production_only_sql, support_only_sql

    assert "COALESCE(o.operation_type,'PRODUCTION')='PRODUCTION'" == production_only_sql('o')
    assert "COALESCE(x.operation_type,'PRODUCTION')<>'PRODUCTION'" == support_only_sql('x')


def test_po_status_sql_refuses_a_status_that_does_not_exist():
    """Hàm sinh SQL phải là chỗ chặn cuối, không phải chỗ tin tưởng mù."""
    from mesflow.domain.policy import po_status_sql

    assert po_status_sql(frozenset({'RELEASED', 'IN_PROGRESS'})) == "('IN_PROGRESS','RELEASED')"
    with pytest.raises(ValueError, match='không tồn tại'):
        po_status_sql(frozenset({'ACTIVE'}))


# --- Loại Operation: cấm chép lại bộ lọc ---------------------------------

#: Mọi file được phép nhắc tới operation_type. File nào KHÔNG có trong danh
#: sách này mà tự viết bộ lọc thì bài test dưới sẽ đỏ -- đó là cách ngăn bản
#: chép thứ hai ra đời, chứ không phải cách liệt kê cho đủ.
POLICY_MODULE = 'app/mesflow/domain/policy.py'

OPERATION_TYPE_CONSUMERS = (
    'app/mesflow/db/repositories/analytics.py',
    'app/mesflow/db/repositories/rework.py',
    'app/mesflow/db/repositories/production_state.py',
    'app/mesflow/db/repositories/execution.py',
    'app/mesflow/db/repositories/setup_ops.py',
    'app/mesflow/web/excel_io.py',
    'app/mesflow/web/master_data.py',
    'app/mesflow/services/integrity_audit_service.py',
    'app/mesflow/services/production_trace_service.py',
)


def test_no_consumer_writes_its_own_operation_type_filter():
    """Bộ lọc loại Operation chỉ được sinh ra từ policy.

    Đây là bài test có giá trị nhất trong file: nó không kiểm hành vi hiện tại
    (hành vi đang đúng), nó ngăn bản chép TIẾP THEO. Mỗi lần một module tự viết
    lại COALESCE(operation_type,...) là một lần có thể quên, và quên ở đây
    nghĩa là sản lượng của OP phụ lọt vào tiến độ PO -- không lỗi, không log,
    chỉ là số sai.
    """
    offenders = []
    for rel in OPERATION_TYPE_CONSUMERS:
        source = _code_only(_read(rel))
        for match in re.finditer(r"COALESCE\(\w*\.?operation_type,'PRODUCTION'\)\s*(?:=|<>|!=|IN)", source):
            line = source[:match.start()].count('\n') + 1
            offenders.append(f'{rel}:{line}')
    assert not offenders, (
        'bộ lọc operation_type viết tay -- phải dùng policy.production_only_sql / '
        'support_only_sql / type_in_sql:\n  ' + '\n  '.join(offenders))


def test_every_consumer_actually_imports_the_policy():
    """Dùng policy, không phải chỉ tránh viết chuỗi."""
    missing = [rel for rel in OPERATION_TYPE_CONSUMERS
               if 'mesflow.domain.policy' not in _read(rel)]
    assert not missing, ('file có nhắc operation_type nhưng không nhập policy:\n  '
                         + '\n  '.join(missing))


def test_no_module_hardcodes_a_support_type_name():
    """'SETUP' / 'REWORK' viết cứng cũng là một bản chép.

    Chỉ soi các so sánh trong Python (== 'SETUP'), không soi SQL: một vài câu
    truy vấn tra riêng bảng SETUP theo parent_operation_id, ở đó tên loại là
    một phần của câu hỏi chứ không phải một bộ lọc chính sách.
    """
    offenders = []
    for rel in OPERATION_TYPE_CONSUMERS:
        source = _code_only(_read(rel))
        for match in re.finditer(r"operation_type'?\]?\s*(?:==|!=)\s*'(SETUP|REWORK|PRODUCTION)'", source):
            line = source[:match.start()].count('\n') + 1
            offenders.append(f'{rel}:{line} -> {match.group(0)}')
    assert not offenders, (
        'so sánh loại Operation viết tay -- dùng policy.is_production / is_setup / '
        'is_rework:\n  ' + '\n  '.join(offenders))


def test_labelled_types_exclude_the_rework_bench():
    """Bàn SỬA HÀNG không được in tem: kiosk từ chối mở session trên nó."""
    from mesflow.domain.policy import LABELLED_TYPES, REWORK_TYPE, SETUP_TYPE, PRODUCTION_TYPE

    assert PRODUCTION_TYPE in LABELLED_TYPES
    assert SETUP_TYPE in LABELLED_TYPES, 'quét tem SETUP là cách duy nhất ghi nhận chuẩn bị máy'
    assert REWORK_TYPE not in LABELLED_TYPES, (
        'in tem cho bàn sửa hàng là đưa cho xưởng một QR mà kiosk không nhận')


def test_type_in_sql_refuses_an_unknown_type():
    from mesflow.domain.policy import type_in_sql

    assert type_in_sql(frozenset({'SETUP'}), 'o') == \
        "COALESCE(o.operation_type,'PRODUCTION') IN ('SETUP')"
    with pytest.raises(ValueError, match='không tồn tại'):
        type_in_sql(frozenset({'ASSEMBLY'}), 'o')


def test_every_policy_name_used_in_sql_is_actually_imported():
    """Tên policy nhúng trong f-string SQL phải có trong scope của file.

    compile() KHÔNG bắt được lỗi này -- một cái tên chưa import trong f-string
    chỉ nổ lúc CHẠY, dưới dạng NameError, và Flask biến nó thành HTTP 500. Đã
    xảy ra: quét SETUP_TYPE vào bốn câu truy vấn của setup_ops.py nhưng quên
    thêm nó vào dòng import; 22 bài integration đỏ, và phải mất một vòng gate
    đầy đủ mới thấy.

    Bài test này chạy trong một giây và bắt đúng lớp lỗi đó.
    """
    import ast

    policy_names = {
        'SETUP_TYPE', 'REWORK_TYPE', 'PRODUCTION_TYPE',
        'PRODUCTION_ONLY_O', 'PRODUCTION_ONLY_BARE', 'SUPPORT_ONLY_O',
        'LABELLED_ONLY_O', 'IS_SETUP_O',
    }
    offenders = []
    for rel in OPERATION_TYPE_CONSUMERS:
        tree = ast.parse(_read(rel))
        bound = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bound.add(alias.asname or alias.name.split('.')[0])
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound.add(node.name)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for value in node.values:
                    if isinstance(value, ast.FormattedValue):
                        for sub in ast.walk(value.value):
                            if isinstance(sub, ast.Name):
                                used.add(sub.id)
        missing = sorted((used & policy_names) - bound)
        if missing:
            offenders.append(f'{rel}: {missing}')
    assert not offenders, ('tên policy dùng trong f-string nhưng chưa import '
                           '(sẽ là NameError -> HTTP 500 lúc chạy):\n  '
                           + '\n  '.join(offenders))
