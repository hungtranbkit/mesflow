"""Thứ gì quét vào mở được việc thì màn hình điều hành phải hiện được.

Bài này khoá HAI ĐẦU của một hợp đồng đã trôi ra xa nhau và gây bug P0
(2026-09-12): kiosk mở được session trên `STARTABLE_TYPES` (PRODUCTION + SETUP),
còn bảng task của Kiosk điều hành chỉ hiện PRODUCTION. Hậu quả không phải một
lỗi báo ra: nó IM LẶNG. Máy báo "Đã bắt đầu", `work_sessions` có hàng OPEN thật,
`SESSION_STARTED` chạy trên dòng hoạt động ngay cạnh -- và bảng task không có
dòng nào, còn KPI "session đang mở" đếm thiếu đúng ca đó (đo được: DB 2, KPI 1).

Các bài integration ở tests/integration/test_kiosk_scan_to_board_contract.py
chứng minh HÀNH VI đúng end-to-end. Bài này chứng minh hai tập hằng số không thể
lặng lẽ tách nhau lần nữa: sửa một bên mà quên bên kia là đỏ ở đây, không phải
đỏ ở xưởng.
"""
from __future__ import annotations

import pytest

from mesflow.domain.policy import (PRODUCTION_TYPE, SETUP_TYPE, STARTABLE_TYPES,
                                   is_startable_type)
from mesflow.web.kiosk_board import BOARD_TASK_TYPES

pytestmark = pytest.mark.static


def test_the_board_lists_exactly_what_the_kiosk_can_start():
    """Một dòng, nhưng đây CHÍNH LÀ bug: hai tập này từng khác nhau."""
    assert BOARD_TASK_TYPES == STARTABLE_TYPES, (
        'Màn hình điều hành và kiosk đang bất đồng về loại Operation. '
        'Mọi loại kiosk start được phải hiện được thành task, nếu không một ca '
        'làm việc có thật sẽ biến mất khỏi màn hình mà không có lỗi nào.'
    )


def test_setup_is_inside_the_contract_not_an_exception_to_it():
    """SETUP là ca thật đã làm lộ bug -- giữ nó tường minh trong bài kiểm."""
    assert SETUP_TYPE in STARTABLE_TYPES
    assert SETUP_TYPE in BOARD_TASK_TYPES
    assert PRODUCTION_TYPE in BOARD_TASK_TYPES


@pytest.mark.parametrize('operation_type', sorted(STARTABLE_TYPES))
def test_every_startable_type_is_a_type_the_board_can_show(operation_type):
    assert is_startable_type(operation_type)
    assert operation_type in BOARD_TASK_TYPES


def test_the_board_does_not_widen_beyond_what_can_be_started():
    """Mở rộng theo chiều ngược lại cũng sai: bảng task không được hiện thứ
    không ai start được ở kiosk -- đó là đưa cho xưởng một dòng việc ma."""
    assert not (BOARD_TASK_TYPES - STARTABLE_TYPES)


def test_the_daily_progress_default_is_still_production_only():
    """Mở rộng CHỈ dành cho màn hình điều hành.

    "Tiến độ theo Operation" của Dashboard theo ngày nói về bước có chỉ tiêu sản
    lượng, nên mặc định của daily_progress() phải giữ nguyên chỉ-sản-xuất. Nếu
    mặc định bị nới ra, sản lượng của OP phụ lọt vào tiến độ PO -- đúng họ lỗi
    mà domain/policy.py sinh ra để chặn.
    """
    import inspect

    from mesflow.db.repositories.analytics import DashboardRepository

    for method in (DashboardRepository.daily_progress, DashboardRepository.daily_dashboard):
        default = inspect.signature(method).parameters['operation_types'].default
        assert default is None, (
            f'{method.__name__}() mặc định phải là None (chỉ OP sản xuất); '
            'nới mặc định là đổi nghĩa của mọi màn hình đang gọi nó.'
        )
