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
