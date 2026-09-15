"""Con số "Session cần xử lý" và Inbox ngoại lệ phải là MỘT nguồn.

Lỗi thật trên TEST 2026-09-15: Quản lý session báo "1 session cần xử lý", bấm
"Xem ngay" thì Trung tâm ngoại lệ trống trơn.

Gốc rễ là hệ thống có HAI bộ luật phát hiện ngoại lệ chạy song song:

* phép chiếu ĐỘNG -- analytics.py::session_exceptions(), tính lại bằng SQL mỗi
  lần đọc, từ vựng NEW/IN_PROGRESS/RESOLVED/IGNORED. Banner đọc cái này.
* bảng VẬT CHẤT HOÁ -- exception_records + reconcile(), từ vựng OPEN/
  ACKNOWLEDGED/RESOLVED/AUTO_IGNORED/MANUAL_IGNORED. Trung tâm ngoại lệ (thứ
  thực sự được nạp, xem app.html) vẽ từ cái này.

Migration 0054 cho phép một nhân viên giữ nhiều session mở trên các Operation
KHÁC nhau. Nó sửa luật chồng-thời-gian ở bản vật chất hoá (thêm
`b.operation_id=a.operation_id`) nhưng bỏ sót bản động -- nên việc hợp lệ của
một người trông hai máy bị bản động kêu là OVERLAP/CRITICAL, còn bản kia im
lặng đúng. Banner đếm một đằng, màn hình vẽ một nẻo.

Những bài dưới đây giữ bất biến đó ở mức NGUỒN, nên chúng đỏ ngay cả trên máy
không có cơ sở dữ liệu -- và đỏ đúng lúc ai đó lại thêm một bộ luật thứ hai.
"""
from pathlib import Path
import re

ROOT = Path(__file__).parents[1]
APP_JS = (ROOT / 'app/mesflow/web/static/app.js').read_text(encoding='utf-8')
CENTER_JS = (ROOT / 'app/mesflow/web/static/pages/exception-center.js').read_text(encoding='utf-8')
ANALYTICS = (ROOT / 'app/mesflow/db/repositories/analytics.py').read_text(encoding='utf-8')
EXCEPTIONS_REPO = (ROOT / 'app/mesflow/db/repositories/exceptions.py').read_text(encoding='utf-8')
EXCEPTIONS_WEB = (ROOT / 'app/mesflow/web/exceptions.py').read_text(encoding='utf-8')


def _banner_block() -> str:
    """Đúng khối nạp banner "Session cần xử lý", không phải ô HTML cùng tên.

    `smInboxBanner` xuất hiện cả trong khung HTML của trang; khối cần xét là
    khối `if(!returnContext){ ... }` gọi API rồi đổ vào ô đó.
    """
    start = APP_JS.index('if(!returnContext){')
    end = APP_JS.index("el('smInboxBanner').innerHTML=''});", start)
    return APP_JS[start:end]


def test_banner_reads_the_same_endpoint_the_cta_lands_on():
    """(3) Cùng endpoint, cùng từ vựng view -- không phải hai read model."""
    block = _banner_block()
    assert '/api/exceptions?view=action' in block, 'banner phải đọc nguồn canonical'
    assert 'session-exceptions?view=inbox' not in block, (
        'banner không được quay lại phép chiếu động -- đó chính là lỗi cũ')
    # Trung tâm ngoại lệ mở ở đúng view này.
    assert "view:'action'" in CENTER_JS or "view: 'action'" in CENTER_JS


def test_actionable_view_excludes_resolved_and_every_ignored_status():
    """(2) RESOLVED / MANUAL_IGNORED / AUTO_IGNORED không nằm trong việc cần làm."""
    mapping = re.search(r"statuses=\{([^}]*)\}\.get\(view\)", EXCEPTIONS_WEB)
    assert mapping, 'không tìm thấy bảng view -> statuses của /api/exceptions'
    action = re.search(r"'action':\[([^\]]*)\]", mapping.group(1)).group(1)
    assert 'OPEN' in action and 'ACKNOWLEDGED' in action
    for dead in ('RESOLVED', 'AUTO_IGNORED', 'MANUAL_IGNORED'):
        assert dead not in action, f'{dead} không phải việc cần xử lý'


def test_badge_counts_sessions_from_the_rows_the_inbox_will_draw():
    """(1) count > 0 kéo theo Inbox có dòng: đếm trên chính danh sách đó."""
    block = _banner_block()
    assert 'd.items' in block, 'phải đếm trên items của chính câu trả lời đó'
    assert 'new Set' in block, 'đếm SESSION chứ không đếm dòng ngoại lệ'


def test_reconcile_runs_before_the_count_is_trusted():
    """(4) Không có chuyện đếm ra số từ một lần dò cũ."""
    handler = EXCEPTIONS_WEB[EXCEPTIONS_WEB.index("@bp.get('/exceptions')"):]
    handler = handler[:handler.index('@bp.get', 10)]
    assert 'reconcile(' in handler, '/api/exceptions phải reconcile trước khi trả lời'


def test_both_overlap_rules_agree_that_conflict_means_same_operation():
    """Bản sao luật còn lại không được lệch khỏi 0054 một lần nữa."""
    assert 'b.operation_id=a.operation_id' in EXCEPTIONS_REPO
    overlap = ANALYTICS[ANALYTICS.index('overlap_flags AS ('):ANALYTICS.index('), flags AS (')]
    assert 'b.operation_id=a.operation_id' in overlap, (
        'phép chiếu động vẫn coi mọi chồng giờ là xung đột -- 0054 cho phép '
        'một người giữ nhiều session trên các Operation khác nhau')


def test_multi_open_migration_is_the_reason_both_rules_must_match():
    migration = ROOT / 'app/migrations/versions/0054_multi_open_session_per_employee.py'
    assert migration.exists()
