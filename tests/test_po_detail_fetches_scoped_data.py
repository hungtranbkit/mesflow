"""Man chi tiet PO phai HOI dung du lieu cua PO, khong nap ca danh muc roi loc.

Nua backend cua lỗi nay co test integration rieng
(tests/integration/test_po_detail_operation_scope.py). Nua frontend nam trong
app.js, va neu chi sua backend thi man hinh van hong y nguyen -- no van goi
danh sach tong quat. Bai test nay khoa nua do ma khong can dung Playwright:
no doc thang ma nguon.

Vi sao dang doc ma nguon la du: cai can khang dinh la "loi goi API mang theo
pham vi PO", va do la mot su that tinh nam ngay trong chuoi URL.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.static

APP_JS = Path(__file__).resolve().parents[1] / 'app' / 'mesflow' / 'web' / 'static' / 'app.js'

#: Cac loi goi danh sach tong quat KHONG duoc dung o duong chi tiet PO nua.
UNSCOPED_CALLS = (
    "api('/api/operations?limit=1000')",
    "api('/api/parts?limit=1000')",
)


def _source() -> str:
    return APP_JS.read_text(encoding='utf-8')


def test_po_detail_no_longer_loads_the_whole_catalogue():
    source = _source()
    offenders = [call for call in UNSCOPED_CALLS if call in source]
    assert not offenders, (
        'app.js van nap toan bo danh muc roi loc o trinh duyet: ' + ', '.join(offenders) +
        ' -- voi bang operations qua 1000 dong thi Operation cua PO cu bi cat mat.')


def test_po_detail_asks_for_one_production_order():
    """Ca hai duong (mo chi tiet PO, va modal Start) deu phai truyen pham vi."""
    source = _source()
    scoped = re.findall(r'/api/(?:parts|operations)\?production_order_id=\$\{id\}', source)
    assert len(scoped) >= 4, (
        f'chi thay {len(scoped)} loi goi co pham vi PO; can ca parts lan operations '
        'o CA hai duong (openProductionOrder + startProductionOrder)')


def test_the_client_does_not_filter_by_po_again_after_asking_for_one_po():
    """Loc lai sau khi da hoi dung PO che mat viec da hoi dung.

    Neu mot ngay nao do ai do lam hong pham vi phia server, viec loc lai o
    client se giau lỗi di thay vi de no lo ra.
    """
    source = _source()
    # Chi soi khoi ve man chi tiet PO, khong soi ca file.
    start = source.find('window.openProductionOrder')
    assert start != -1, 'khong tim thay openProductionOrder -- cap nhat bai test'
    block = source[start:start + 4000]
    assert 'partData.items||[]).filter(x=>Number(x.production_order_id)' not in block
    assert 'opData.items||[]).filter(x=>Number(x.production_order_id)' not in block
