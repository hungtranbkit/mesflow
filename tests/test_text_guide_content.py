"""Hướng dẫn bằng chữ -- content + requirement coverage contract.

The text guide is not only reference documentation.  It is the human-readable
contract for user-facing MESFlow behaviour: a page added to the supported
sidebar must have guide coverage before the change is considered complete.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = ROOT / 'app/mesflow/web/static/guides/user-guide.vi.json'

EXPECTED_TOC = [
    ('getting-started', 'Bắt đầu sử dụng'),
    ('requirement-coverage', 'Phạm vi & xác nhận requirement'),
    ('overview', 'Tổng quan sản xuất'),
    ('dashboard', 'Dashboard theo ngày'),
    ('template', 'Template'),
    ('production-order', 'Production Order'),
    ('part-operation', 'Part và Operation'),
    ('kiosk', 'Kiosk cho công nhân'),
    ('work-session', 'Work Session & Quản lý Session'),
    ('operation-progress', 'Tiến độ theo Operation'),
    ('exceptions', 'Trung tâm ngoại lệ'),
    ('production-trace', 'Production Trace'),
    ('business-audit', 'Nhật ký nghiệp vụ'),
    ('gantt-material-flow', 'Gantt & Material Flow'),
    ('kiosk-management', 'Quản lý trạm Kiosk'),
    ('system-logs', 'Nhật ký ứng dụng'),
    ('employees', 'Nhân viên'),
    ('qr-code', 'QR Code'),
    ('equipment', 'Thiết bị'),
    ('users-permissions', 'Người dùng & phân quyền'),
    ('working-calendar', 'Lịch làm việc'),
    ('excel-import-export', 'Import / Export Excel'),
    ('troubleshooting', 'Xử lý lỗi thường gặp'),
    ('recommended-workflow', 'Quy trình sử dụng MESFlow đề xuất'),
    ('employee-productivity', 'Báo cáo năng suất nhân viên'),
]
KNOWN_BLOCK_TYPES = {'h3', 'p', 'note', 'example', 'diagram', 'list', 'steps', 'table'}

# Supported sidebar pages must resolve to one explicit text-guide requirement
# section.  `tutorials` is intentionally excluded: it is the guide itself.
MENU_PAGE_TO_GUIDE = {
    'overview': 'overview',
    'dashboard': 'dashboard',
    'production-orders': 'production-order',
    'templates': 'template',
    'session-management': 'work-session',
    'session-exceptions': 'exceptions',
    'production-trace': 'production-trace',
    'business-audit': 'business-audit',
    'production-schedule': 'gantt-material-flow',
    'kiosk-management': 'kiosk-management',
    'employee-productivity': 'employee-productivity',
    'system-logs': 'system-logs',
    'employees': 'employees',
    'qr-print': 'qr-code',
    'equipment': 'equipment',
    'users': 'users-permissions',
    'working-calendar': 'working-calendar',
}


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


def test_every_user_facing_sidebar_page_has_requirement_guide_coverage():
    """Adding/removing a supported sidebar page must trigger a guide review.

    We deliberately inspect only `const menu` rather than every `openPage`
    branch.  Internal/debug/backend-supported pages are not automatically a
    user requirement just because a renderer/API happens to exist.
    """
    app_js = (ROOT / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
    menu_chunk = app_js.split('const menu=[', 1)[1].split('const nav=', 1)[0]
    menu_pages = set(re.findall(r"page:'([^']+)'", menu_chunk))
    menu_pages.discard('tutorials')

    assert menu_pages == set(MENU_PAGE_TO_GUIDE), (
        'Sidebar changed: review the requirement guide and update '
        f'MENU_PAGE_TO_GUIDE. menu={sorted(menu_pages)} '
        f'mapped={sorted(MENU_PAGE_TO_GUIDE)}'
    )

    guide_ids = {s['id'] for s in _load()['sections']}
    missing = {
        page: section_id
        for page, section_id in MENU_PAGE_TO_GUIDE.items()
        if section_id not in guide_ids
    }
    assert not missing, f'User-facing pages without guide requirement coverage: {missing}'


def test_requirement_coverage_section_states_the_contract():
    data = _load()
    section = next(s for s in data['sections'] if s['id'] == 'requirement-coverage')
    text = json.dumps(section['content'], ensure_ascii=False).lower()
    assert 'user-facing' in text
    assert 'requirement' in text
    assert 'qa' in text
    assert 'ui' in text


def test_excel_workbook_never_described_as_direct_po_import():
    """Excel quy trình must always route through Template, never direct PO."""
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
    """Quoted kiosk behaviour must stay anchored to the real error catalog."""
    data = _load()
    kiosk = next(s for s in data['sections'] if s['id'] == 'kiosk')
    kiosk_js = (ROOT / 'app/mesflow/web/static/kiosk.js').read_text(encoding='utf-8')
    assert "'SES-409'" in kiosk_js
    text = json.dumps(kiosk['content'], ensure_ascii=False)
    assert 'Work Session' in text
    assert 'Đã có Session đang mở' in text
