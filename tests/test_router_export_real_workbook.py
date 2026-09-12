"""Xuất tờ router phải là chính file gốc đã nhập, không phải file dựng lại.

Bài này chạy trên **file thật** (`tests/fixtures/router-newark-arm-chair.xlsx`,
44 sheet của xưởng) chứ không phải workbook dựng bằng openpyxl, vì thứ cần
chứng minh là *giữ nguyên biểu mẫu của khách*: merge, độ rộng cột, chiều cao
dòng, ảnh/logo, khung in, công thức. Một workbook dựng tay không có thứ nào
trong số đó nên không chứng minh được gì.

Ba lỗi thật đã bị bắt đúng bằng file này và không bị workbook dựng tay bắt:
mọi tem rơi xuống sheet phụ (mã OP thật mang tiền tố PO), dấu '-' trong ô thời
gian setup làm cả file bị từ chối, và số Operation đánh trùng trong cùng Part.
"""
import re
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook

from mesflow.web.excel_io import _parse_go_router_template
from mesflow.web.router_export import (
    QR_OP_LABEL, QR_SETUP_LABEL, _stamp_source_workbook)
from mesflow.db.repositories.master_data import operation_code_suffix

pytest.importorskip('PIL', reason='Pillow là dependency của tính năng xuất QR')

FIXTURE = Path(__file__).resolve().parent / 'fixtures/router-newark-arm-chair.xlsx'
PO = {'id': 1, 'code': 'PO-NEWARK', 'product': 'NEWARK ARM CHAIR',
      'planned_quantity': 110, 'source_template_id': 7}


@pytest.fixture(scope='module')
def source_bytes():
    assert FIXTURE.is_file(), f'thiếu fixture {FIXTURE}'
    return FIXTURE.read_bytes()


@pytest.fixture(scope='module')
def parsed(source_bytes):
    return _parse_go_router_template(load_workbook(BytesIO(source_bytes), data_only=True),
                                     FIXTURE.name)


@pytest.fixture(scope='module')
def rows(parsed):
    """Operation "thật" như CSDL sẽ có: mã mang tiền tố PO, SETUP khi phút > 0."""
    part_code_by_key = {p['key']: p['code'] for p in parsed['parts']}
    part_index = {p['key']: i for i, p in enumerate(parsed['parts'])}
    built = []
    next_id = 1000
    for op in parsed['operations']:
        part_code = part_code_by_key[op['part_key']]
        suffix = operation_code_suffix(part_code, op['code'])
        next_id += 1
        op_id = next_id
        setup_id = None
        if op['requires_setup']:
            next_id += 1
            setup_id = next_id
        built.append({
            'id': op_id, 'code': f"{PO['code']}-{suffix}", 'name': op['name'],
            'sort_order': op['sort_order'],
            'standard_seconds_per_unit': op['standard_seconds_per_unit'],
            'requires_setup': op['requires_setup'],
            'expected_setup_minutes': op['expected_setup_minutes'],
            'part_id': part_index[op['part_key']], 'part_code': part_code,
            'part_name': op['_excel_sheet'], 'part_sort': part_index[op['part_key']],
            'op_qr': f'WF|OPID|{op_id}',
            'setup_id': setup_id,
            'setup_code': f"{PO['code']}-{suffix}-SU" if setup_id else None,
            'setup_name': f"Setup {op['name']}" if setup_id else None,
            'setup_minutes': op['expected_setup_minutes'],
            'setup_qr': f'WF|OPID|{setup_id}' if setup_id else None,
        })
    return built


@pytest.fixture(scope='module')
def exported(source_bytes, rows):
    wb, placed, matched, unmatched = _stamp_source_workbook(source_bytes, PO, rows)
    buffer = BytesIO(); wb.save(buffer); buffer.seek(0)
    return load_workbook(buffer), placed, matched, unmatched


# --- file thật vào đúng như mong đợi --------------------------------------

def test_file_that_shop_uses_parses_completely(parsed):
    assert len(parsed['parts']) == 44
    assert len(parsed['operations']) == 112
    assert sum(1 for op in parsed['operations'] if op['requires_setup']) == 47
    # 10 chỗ đánh trùng SỐ OP gốc -- nhập đủ cả 112, số gốc giữ nguyên, mã nội
    # bộ sinh duy nhất, và người dùng được báo từng chỗ.
    duplicates = [n for n in parsed['notes'] if n['kind'] == 'DUPLICATE_SOURCE_OP_NO']
    assert len(duplicates) == 10
    codes = [op['code'] for op in parsed['operations']]
    assert len(codes) == len(set(codes)), 'mã nội bộ phải duy nhất'


def test_setup_values_from_the_real_sheets(parsed):
    by_code = {op['code']: op for op in parsed['operations']}
    # Đúng những con số user mô tả trên file của họ.
    assert by_code['KM-967-232006L-01-OP01']['expected_setup_minutes'] == 20
    assert by_code['KM-967-232006L-01-OP02']['requires_setup'] is False
    assert by_code['KM-504539877-B4-2-OP01']['expected_setup_minutes'] == 120


# --- xuất = file gốc + tem, không phải file dựng lại ----------------------

def test_every_source_sheet_survives_the_export(source_bytes, exported):
    """Không mất sheet nào, không đổi tên sheet nào."""
    original = load_workbook(BytesIO(source_bytes))
    workbook, _, _, unmatched = exported
    assert unmatched == [], 'file gốc phải khớp được MỌI Operation'
    # Không sheet nào bị thêm vào: xuất ra đúng bằng danh sách sheet của file gốc.
    assert workbook.sheetnames == original.sheetnames


def test_original_images_and_text_survive(source_bytes, exported):
    """Logo/ảnh của khách còn nguyên, và mọi ô có chữ giữ đúng giá trị cũ."""
    original = load_workbook(BytesIO(source_bytes))
    workbook, placed, _, _ = exported
    labels = {QR_OP_LABEL, QR_SETUP_LABEL}
    for name in original.sheetnames:
        before, after = original[name], workbook[name]
        assert len(after._images) >= len(before._images), f'{name}: mất ảnh gốc'
        for row in before.iter_rows():
            for cell in row:
                if cell.value in (None, ''):
                    continue
                assert after[cell.coordinate].value == cell.value, (
                    f'{name}!{cell.coordinate} bị ghi đè')
        # Chữ duy nhất được thêm vào là hai nhãn tem.
        added = {c.value for r in after.iter_rows() for c in r if c.value not in (None, '')}
        original_values = {c.value for r in before.iter_rows() for c in r
                           if c.value not in (None, '')}
        assert (added - original_values) <= labels


def test_qr_lane_never_covers_data_on_any_sheet(source_bytes, exported, parsed):
    """Trên MỌI sheet có tem, tem phải neo sau ô có chữ xa nhất của sheet đó.

    Đo bằng chính neo của drawing sau khi đã lưu và mở lại -- tức đúng thứ Excel
    dùng để đặt ảnh khi in. (Lưu xong, openpyxl chuyển neo chuỗi của ta thành
    đối tượng anchor, nên cả ảnh gốc lẫn tem đều đọc qua ``_from.col``.)
    """
    original = load_workbook(BytesIO(source_bytes))
    workbook, placed, _, _ = exported
    per_sheet = {}
    for item in placed:
        per_sheet[item['sheet']] = per_sheet.get(item['sheet'], 0) + 1
    sheets_with_operations = {op['_excel_sheet'] for op in parsed['operations']}
    assert len(sheets_with_operations) == 43

    def columns(ws):
        found = []
        for image in ws._images:
            marker = getattr(getattr(image, 'anchor', None), '_from', None)
            if marker is not None:
                found.append(marker.col + 1)
        return found

    for name in sheets_with_operations:
        ws = workbook[name]
        rightmost_data = max(
            (c.column for row in ws.iter_rows() for c in row if c.value not in (None, '')),
            default=0)
        beyond = [c for c in columns(ws) if c > rightmost_data]
        assert len(beyond) == per_sheet[name], (
            f'{name}: {per_sheet[name]} tem đã đóng nhưng chỉ {len(beyond)} nằm ngoài '
            f'vùng dữ liệu (tới cột {rightmost_data}) -- có tem đang chồng lên chữ')
        # Ảnh gốc của khách vẫn ở đúng chỗ cũ.
        assert sorted(columns(original[name])) == sorted(
            c for c in columns(ws) if c <= rightmost_data)


def test_sheet_without_any_operation_block_is_left_untouched(source_bytes, exported, parsed):
    """Sheet không có block nào ('SƠN TĨNH ĐIỆN') phải được giữ y nguyên.

    Nó vẫn là một tờ trong biểu mẫu của khách, chỉ là không có công đoạn nào để
    gắn tem. Sửa nó -- kể cả chỉ đặt lại khổ in -- là đụng vào thứ không cần.
    """
    original = load_workbook(BytesIO(source_bytes))
    workbook, placed, _, _ = exported
    untouched = set(original.sheetnames) - {op['_excel_sheet'] for op in parsed['operations']}
    assert untouched == {'SƠN TĨNH ĐIỆN'}
    for name in untouched:
        assert not any(item['sheet'] == name for item in placed)
        assert len(workbook[name]._images) == len(original[name]._images)


def test_labels_land_on_the_block_of_their_own_operation(parsed, rows, exported):
    """Tem của một Operation phải nằm trên ĐÚNG sheet chứa block của nó.

    Đếm đủ số tem không chứng minh được gì: lỗi thật là cả 159 tem rơi xuống
    một sheet phụ mà tổng số vẫn đúng.
    """
    workbook, placed, matched, _ = exported
    assert matched == len(rows)
    sheet_of_operation = {}
    part_code_by_key = {p['key']: p['code'] for p in parsed['parts']}
    for op in parsed['operations']:
        suffix = operation_code_suffix(part_code_by_key[op['part_key']], op['code'])
        sheet_of_operation[f"{PO['code']}-{suffix}"] = op['_excel_sheet']
    by_id = {row['id']: row for row in rows}
    setup_parent = {row['setup_id']: row for row in rows if row['setup_id']}
    for item in placed:
        row = by_id.get(item['operation_id']) or setup_parent[item['operation_id']]
        assert item['sheet'] == sheet_of_operation[row['code']], (
            f"tem của {row['code']} nằm nhầm sheet {item['sheet']}")


def test_setup_label_only_where_a_setup_operation_exists(rows, exported):
    _, placed, _, _ = exported
    setup_ids = {row['setup_id'] for row in rows if row['setup_id']}
    assert len(setup_ids) == 47
    assert {i['operation_id'] for i in placed if i['kind'] == 'SETUP'} == setup_ids
    assert {i['operation_id'] for i in placed if i['kind'] == 'OP'} == {
        row['id'] for row in rows}
    assert len(placed) == 112 + 47


def test_every_payload_is_the_canonical_operation_id(rows, exported):
    _, placed, _, _ = exported
    payloads = [item['payload'] for item in placed]
    assert len(payloads) == len(set(payloads)), 'hai tem cùng payload'
    for item in placed:
        assert re.fullmatch(r'WF\|OPID\|\d+', item['payload']), item['payload']
        assert item['payload'] == f"WF|OPID|{item['operation_id']}"


def test_two_sheets_sharing_an_operation_name_get_different_labels(parsed, rows, exported):
    """'CẮT LASER' xuất hiện ở nhiều Part -- tuyệt đối không dùng chung id."""
    _, placed, _, _ = exported
    by_name = {}
    for row in rows:
        by_name.setdefault(row['name'], []).append(row['id'])
    repeated = {name: ids for name, ids in by_name.items() if len(ids) > 1}
    assert repeated, 'file thật phải có công đoạn trùng tên giữa các Part'
    payload_of = {i['operation_id']: i['payload'] for i in placed}
    for name, ids in repeated.items():
        payloads = {payload_of[i] for i in ids}
        assert len(payloads) == len(ids), f'{name}: tem bị dùng chung'


# --- HỢP ĐỒNG TRUNG THỰC: chỉ drawing được phép khác ----------------------

def _sheet_fingerprint(ws):
    """Mọi thuộc tính phải giữ nguyên, gom thành một thứ so sánh được."""
    return {
        'cells': {c.coordinate: c.value for r in ws.iter_rows() for c in r
                  if c.value not in (None, '')},
        'merged': sorted(str(r) for r in ws.merged_cells.ranges),
        'column_widths': {k: v.width for k, v in ws.column_dimensions.items()},
        'column_hidden': {k: v.hidden for k, v in ws.column_dimensions.items()},
        'row_heights': {k: v.height for k, v in ws.row_dimensions.items()},
        'freeze_panes': ws.freeze_panes,
        'auto_filter': ws.auto_filter.ref,
        'sheet_state': ws.sheet_state,
        'print_area': ws.print_area,
        'page_setup': (ws.page_setup.orientation, ws.page_setup.paperSize,
                       ws.page_setup.scale, ws.page_setup.fitToWidth,
                       ws.page_setup.fitToHeight),
        'page_margins': (ws.page_margins.left, ws.page_margins.right,
                         ws.page_margins.top, ws.page_margins.bottom),
        'fit_to_page': ws.sheet_properties.pageSetUpPr.fitToPage,
        'print_titles': ws.print_titles,
        'styles': {c.coordinate: (c.font.name, c.font.sz, c.font.b, c.font.i,
                                  c.alignment.horizontal, c.alignment.vertical,
                                  c.number_format, c.fill.fgColor.rgb if c.fill else None,
                                  # Viền ô: hôm nay KHÔNG thể đổi vì đường xuất chỉ
                                  # add_image() và không chạm cell nào -- nhưng khung kẻ
                                  # là thứ người ta nhìn thấy đầu tiên trên tờ giấy in,
                                  # nên khoá luôn cho thay đổi về sau.
                                  (c.border.left.style, c.border.right.style,
                                   c.border.top.style, c.border.bottom.style))
                   for r in ws.iter_rows() for c in r if c.value not in (None, '')},
    }


def test_export_differs_from_source_ONLY_by_added_qr_drawings(source_bytes, exported, rows):
    """Hồi quy trung thực: so từng thuộc tính của MỌI sheet, source vs export.

    Đây là bài mà một bản "xuất lại cho đẹp" sẽ trượt ngay: chỉ cần đổi một bề
    rộng cột, một khổ in, một ô chữ, hay đảo thứ tự sheet là đỏ.
    """
    original = load_workbook(BytesIO(source_bytes))
    workbook, placed, _, _ = exported

    # Danh sách VÀ thứ tự sheet giữ nguyên tuyệt đối.
    assert workbook.sheetnames == original.sheetnames

    for name in original.sheetnames:
        before = _sheet_fingerprint(original[name])
        after = _sheet_fingerprint(workbook[name])
        for key in before:
            assert after[key] == before[key], f'{name}: thuộc tính {key} bị đổi'

    # Khác biệt DUY NHẤT: số drawing tăng đúng bằng số tem đã đóng.
    added = sum(len(workbook[n]._images) - len(original[n]._images)
                for n in original.sheetnames)
    assert added == len(placed) == 112 + 47
    for name in original.sheetnames:
        assert len(workbook[name]._images) >= len(original[name]._images), (
            f'{name}: mất ảnh gốc')


def test_formulas_survive_the_export(source_bytes, exported):
    """data_only=False khi mở: công thức tính giờ của xưởng phải còn nguyên."""
    original = load_workbook(BytesIO(source_bytes))
    workbook, _, _, _ = exported
    formulas = 0
    for name in original.sheetnames:
        for row in original[name].iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith('='):
                    formulas += 1
                    assert workbook[name][cell.coordinate].value == cell.value, (
                        f'{name}!{cell.coordinate}: công thức bị mất')
    assert formulas > 0, 'file mẫu phải có công thức thì bài này mới có nghĩa'
