"""Hướng dẫn bằng chữ -- content data contract.

Backs the new "Hướng dẫn" text guide (app/mesflow/web/static/pages/text-guide.js)
that renders app/mesflow/web/static/guides/user-guide.vi.json. Kept separate
from source-string checks on the .js/.css so a content edit alone (the most
common future change) doesn't also require touching a JS-source test.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = ROOT / 'app/mesflow/web/static/guides/user-guide.vi.json'

EXPECTED_TOC = [
    ('getting-started', 'Bắt đầu sử dụng'),
    ('overview', 'Tổng quan sản xuất'),
    ('dashboard', 'Dashboard theo ngày'),
    ('template', 'Template'),
    ('production-order', 'Production Order'),
    ('part-operation', 'Part và Operation'),
    ('kiosk', 'Kiosk'),
    ('work-session', 'Work Session'),
    ('operation-progress', 'Tiến độ theo Operation'),
    ('exceptions', 'Ngoại lệ sản xuất'),
    ('production-trace', 'Production Trace'),
    ('gantt-material-flow', 'Gantt & Material Flow'),
    ('employees', 'Nhân viên'),
    ('qr-code', 'QR Code'),
    ('equipment', 'Thiết bị'),
    ('users-permissions', 'Người dùng & phân quyền'),
    ('working-calendar', 'Lịch làm việc'),
    ('excel-import-export', 'Import / Export Excel'),
    ('troubleshooting', 'Xử lý lỗi thường gặp'),
    ('recommended-workflow', 'Quy trình sử dụng MESFlow đề xuất'),
]
KNOWN_BLOCK_TYPES = {'h3', 'p', 'note', 'example', 'diagram', 'list', 'steps', 'table'}


def _load():
    return json.loads(GUIDE_PATH.read_text(encoding='utf-8'))


def test_guide_json_is_valid_and_matches_expected_toc():
    data = _load()
    assert data.get('version')
    ids = [(s['id'], s['title'].split('. ', 1)[-1]) for s in data['sections']]
    assert ids == EXPECTED_TOC, ids


def test_every_section_has_real_content_and_keywords():
    data = _load()
    for s in data['sections']:
        assert s.get('keywords'), s['id']
        blocks = s.get('content') or []
        assert blocks, s['id']
        for block in blocks:
            assert block.get('type') in KNOWN_BLOCK_TYPES, (s['id'], block)
            if block['type'] in ('list', 'steps'):
                assert block.get('items'), (s['id'], block)
            elif block['type'] == 'table':
                assert block.get('headers') and block.get('rows'), (s['id'], block)
            else:
                assert block.get('text'), (s['id'], block)


def test_excel_workbook_never_described_as_direct_po_import():
    """Regression guard: Excel quy trình must always route through Template,
    matching the fix already shipped on fix/template-excel-import-location --
    the guide must not re-teach the bug this session already fixed."""
    data = _load()
    for s in data['sections']:
        for block in s.get('content') or []:
            text = ' '.join(filter(None, [block.get('text'), *(block.get('items') or [])]))
            lowered = text.lower()
            if 'excel' in lowered and 'production order' in lowered:
                assert 'trực tiếp' not in lowered or 'không' in lowered, (s['id'], text)
    template = next(s for s in data['sections'] if s['id'] == 'template')
    excel_text = json.dumps(template['content'], ensure_ascii=False)
    assert 'Import vào Template' in excel_text
    assert 'Tạo Production Order' in excel_text


def test_kiosk_section_reflects_real_error_catalog():
    """The error codes/messages quoted here must stay in sync with
    kiosk.js's ERROR_HELP -- spot-check a couple of the real ones."""
    data = _load()
    kiosk = next(s for s in data['sections'] if s['id'] == 'kiosk')
    kiosk_js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
    assert "'SES-409'" in kiosk_js  # sanity: the code this section describes still exists
    text = json.dumps(kiosk['content'], ensure_ascii=False)
    assert 'Work Session' in text
    assert 'Đã có Session đang mở' in text
