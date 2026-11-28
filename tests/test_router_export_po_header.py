"""Router export must print the Production Order's own PO number and quantity."""
from io import BytesIO
import re
import zipfile
from pathlib import Path

import pytest
from openpyxl import load_workbook

from mesflow.db.repositories.master_data import operation_code_suffix
from mesflow.domain.qr_identity import parse_operation_qr
from mesflow.web.excel_io import _parse_go_router_template
from mesflow.web import router_export

pytest.importorskip('PIL', reason='Pillow is required for router QR export')

SOURCE = Path(__file__).resolve().parent / 'fixtures/router-newark-arm-chair.xlsx'


def test_export_stamps_current_po_number_and_quantity_on_template_source(monkeypatch):
    """A PO instantiated from a template may have code/qty unlike its source.

    The imported workbook is PO 6126 / qty 110. Simulate a separate valid PO
    instantiated from that template as 6391 / qty 105, then exercise the same
    build function used by the authenticated router.xlsx endpoint.
    """
    source_bytes = SOURCE.read_bytes()
    parsed = _parse_go_router_template(
        load_workbook(BytesIO(source_bytes), data_only=True), SOURCE.name)
    target = next(op for op in parsed['operations']
                  if op['code'] == 'KM-967-232006L-01-OP01')
    part_code = next(part['code'] for part in parsed['parts']
                     if part['key'] == target['part_key'])
    po_code = '6391 - NEWARK SIDE CHAIR ( GHẾ KHÔNG TAY )'
    po = {'id': 6391, 'code': po_code, 'product': 'NEWARK SIDE CHAIR',
          'planned_quantity': 105, 'source_template_id': 7}
    op_id = 83001
    rows = [{
        'id': op_id,
        'code': f"{po['code']}-{operation_code_suffix(part_code, target['code'])}",
        'name': target['name'],
        'sort_order': target['sort_order'],
        'standard_seconds_per_unit': target['standard_seconds_per_unit'],
        'requires_setup': False,
        'expected_setup_minutes': target['expected_setup_minutes'],
        'part_id': 1,
        'part_code': part_code,
        'part_name': target['_excel_sheet'],
        'part_sort': 0,
        'op_qr': f"WF|OP|{po['code']}-{operation_code_suffix(part_code, target['code'])}",
        'setup_id': None,
        'setup_code': None,
        'setup_name': None,
        'setup_minutes': None,
        'setup_qr': None,
    }]
    monkeypatch.setattr(router_export, 'fetch_one', lambda *_args, **_kwargs: po)
    monkeypatch.setattr(router_export, '_load_po_operations', lambda _po_id: rows)
    monkeypatch.setattr(router_export, '_archived_source', lambda _template_id, **_kwargs: {
        'data': source_bytes,
        'filename': SOURCE.name,
        'sha256': 'a' * 64,
        'import_id': 1,
        'imported_at': 'fixture',
        'outcome': 'CREATED',
    })

    exported_po, output_bytes, placed, _source = router_export.build_router_workbook(6391)
    workbook = load_workbook(BytesIO(output_bytes), data_only=True)
    first_sheet = workbook[workbook.sheetnames[0]]

    assert exported_po['code'] == po_code
    assert first_sheet['C2'].value == po_code
    assert first_sheet['C3'].value == 105
    assert len(placed) == 1
    assert placed[0]['payload'] == rows[0]['op_qr']
    assert 'GHẾ KHÔNG TAY' in placed[0]['payload']
    assert parse_operation_qr(placed[0]['payload']) == ('OP', rows[0]['code'])
    assert target['name'] in ('CẮT LASER', 'LÀM NGUỘI', 'XOẮN CHÂN GHẾ')


def test_archived_source_does_not_join_an_import_after_po_creation(monkeypatch, tmp_path):
    from datetime import datetime, timezone

    old_path = tmp_path / 'old-router.xlsx'
    new_path = tmp_path / 'new-router.xlsx'
    old_path.write_bytes(b'old workbook revision')
    new_path.write_bytes(b'new workbook revision')
    po_created = datetime(2026, 11, 20, tzinfo=timezone.utc)
    events = [
        {'id': 2, 'outcome': 'REPLACED', 'created_at': datetime(2026, 11, 27, tzinfo=timezone.utc),
         'original_filename': 'new-router.xlsx', 'sha256': 'b' * 64},
        {'id': 1, 'outcome': 'CREATED', 'created_at': datetime(2026, 11, 19, tzinfo=timezone.utc),
         'original_filename': 'old-router.xlsx', 'sha256': 'a' * 64},
    ]

    class ImportArchive:
        def list(self, **_kwargs):
            return events

        def file_for(self, import_id):
            path = old_path if import_id == 1 else new_path
            return {'storage_path': str(path), 'original_filename': path.name}

    monkeypatch.setattr(router_export, 'TemplateImportRepository', ImportArchive)
    selected = router_export._archived_source(7, as_of=po_created)

    assert selected['data'] == b'old workbook revision'
    assert selected['import_id'] == 1


def test_export_can_fill_empty_po_header_cells_without_full_workbook_resave():
    source_bytes = SOURCE.read_bytes()
    source = zipfile.ZipFile(BytesIO(source_bytes))
    out = BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as edited:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                xml = content.decode('utf-8')
                for coord in ('C2', 'C3'):
                    pattern = re.compile(
                        r'<c r="%s"([^>]*?)(?:/>|>.*?</c>)' % coord, re.S)
                    match = pattern.search(xml)
                    assert match, f'fixture is missing {coord}'
                    xml = xml[:match.start()] + f'<c r="{coord}"{match.group(1)}/>' + xml[match.end():]
                content = xml.encode('utf-8')
            edited.writestr(item, content)

    po = {'code': '6391 - NEWARK SIDE CHAIR ( GHẾ KHÔNG TAY )',
          'planned_quantity': 105}
    updates = router_export._router_header_cell_updates(out.getvalue(), po)
    exported = router_export._graft_qr_into_workbook(
        out.getvalue(), [], cell_updates=updates)
    workbook = load_workbook(BytesIO(exported), data_only=True)
    first_sheet = workbook[workbook.sheetnames[0]]

    assert first_sheet['C2'].value == po['code']
    assert first_sheet['C3'].value == 105
