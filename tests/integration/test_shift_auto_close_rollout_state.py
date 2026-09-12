"""Audit P0/P1: vì sao session vẫn OPEN qua đêm dù code auto-close đã có.

Bộ bài có sẵn (test_shift_session_lifecycle.py) chứng minh CƠ CHẾ đóng ca
chạy đúng -- nhưng MỌI bài trong đó đều gọi `reconcile(dry_run=False)`, tức
chúng bỏ qua đúng hai công tắc quyết định việc auto-close có xảy ra thật hay
không trên một môi trường thật:

    MESFLOW_SHIFT_AUTO_CLOSE_ENABLED   mặc định "0"
    MESFLOW_SHIFT_AUTO_CLOSE_DRY_RUN   mặc định "1"

Với mặc định đó, `reconcile-shift-sessions` TÌM RA ứng viên rồi KHÔNG đóng
gì cả. Không có bài test nào khoá điều này, nên "code đã có" và "session
thật sự được đóng" là hai chuyện khác nhau mà không ai thấy.

Bộ bài này khoá cả hai phía, cộng hai lỗ hổng phát hiện khi audit:
  * session bắt đầu trong khe NO_ACTIVE_SHIFT thì KHÔNG BAO GIỜ là ứng viên
    -- không có fallback "hết ngày thì đóng";
  * `scheduled_job_health` là thứ DUY NHẤT phân biệt được "scheduler đang
    chạy" với "chỉ có code": nó ở UNKNOWN/NULL cho tới khi job thật sự chạy.
"""
from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from mesflow.core.config import settings as live_settings
from mesflow.core.working_calendar import resolve_shift_window_for_datetime
from mesflow.db.connection import fetch_all
from mesflow.services import shift_session_service as sss
from mesflow.services.shift_session_service import ShiftSessionReconciliationService

pytestmark = pytest.mark.postgres

HCM = ZoneInfo('Asia/Ho_Chi_Minh')

# Mặc định đang được ghi trong docs/operations/SHIFT_AUTO_CLOSE_ROLLOUT.md.
# Viết thẳng ra đây để nếu ai đó đổi mặc định thì bài này đỏ và buộc phải
# cập nhật runbook cùng lúc -- chứ không phải đổi lặng lẽ một bên.
DEFAULT_ENABLED = False
DEFAULT_DRY_RUN = True


def _open_session(db, g, started_at: datetime, request_id: str, **qty) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO work_sessions(employee_id,operation_id,station_id,status,started_at,
                                         start_request_id,good_qty,defect_qty,rework_qty)
               VALUES(%s,%s,%s,'OPEN',%s,%s,%s,%s,%s) RETURNING id""",
            (g['employee_id'], g['operation_id'], g['station_id'], started_at, request_id,
             int(qty.get('good', 0)), int(qty.get('defect', 0)), int(qty.get('rework', 0))),
        )
        return cur.fetchone()['id']


def _row(db, session_id: int):
    with db.cursor() as cur:
        cur.execute('SELECT * FROM work_sessions WHERE id=%s', (session_id,))
        return cur.fetchone()


def _flags(monkeypatch, *, enabled: bool, dry_run: bool):
    """Settings là frozen dataclass và các field được tính LÚC IMPORT, nên
    đặt os.environ trong test không có tác dụng gì. Thay nguyên object trên
    chính module đang đọc nó."""
    monkeypatch.setattr(
        sss, 'settings',
        dataclasses.replace(live_settings, shift_auto_close_enabled=enabled,
                            shift_auto_close_dry_run=dry_run),
    )


def _mine(results, session_id):
    """find_candidates() quét MỌI session OPEN trong DB, kể cả của bài khác."""
    return [r for r in results if r['session_id'] == session_id]


# --- 1. Nguyên nhân gốc: mặc định sản xuất làm job thành no-op ------------

def test_compiled_in_defaults_are_auto_close_off():
    """Mặc định của chính Settings, không phải của môi trường test này."""
    import os
    assert os.environ.get('MESFLOW_SHIFT_AUTO_CLOSE_ENABLED') in (None, '', '0'), \
        'môi trường test đang bật cờ -- bài dưới sẽ nói dối về mặc định sản xuất'
    assert live_settings.shift_auto_close_enabled is DEFAULT_ENABLED
    assert live_settings.shift_auto_close_dry_run is DEFAULT_DRY_RUN


def test_default_flags_find_the_stale_session_but_never_close_it(db, seeded_factory, monkeypatch):
    """ĐÂY là lý do sáng ra session vẫn OPEN: job chạy, thấy đúng ứng viên,
    rồi không làm gì. Không có lỗi, không có cảnh báo -- chỉ WOULD_CLOSE."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)          # DAY 08:00-17:00
    sid = _open_session(db, g, started_at, f'DEF-{g["suffix"]}')
    _flags(monkeypatch, enabled=DEFAULT_ENABLED, dry_run=DEFAULT_DRY_RUN)

    now = datetime(2026, 8, 11, 9, 0, tzinfo=HCM)                   # hôm sau
    results = _mine(ShiftSessionReconciliationService().reconcile(now=now, correlation_id='audit-default'), sid)

    assert len(results) == 1, 'session quá hạn phải được TÌM RA'
    assert results[0]['action'] == 'WOULD_CLOSE'
    assert results[0]['shift_code'] == 'DAY'
    assert _row(db, sid)['status'] == 'OPEN', \
        'với cờ mặc định, session KHÔNG được đóng -- đúng thiết kế rollout, và đúng triệu chứng người dùng thấy'


def test_enabled_alone_is_still_not_enough_dry_run_must_also_be_off(db, seeded_factory, monkeypatch):
    """Hai công tắc độc lập: ENABLED=1 một mình vẫn không đóng gì."""
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 16, 0, tzinfo=HCM), f'EN-{g["suffix"]}')
    _flags(monkeypatch, enabled=True, dry_run=True)
    now = datetime(2026, 8, 11, 9, 0, tzinfo=HCM)
    results = _mine(ShiftSessionReconciliationService().reconcile(now=now, correlation_id='audit-enabled-only'), sid)
    assert results[0]['action'] == 'WOULD_CLOSE'
    assert _row(db, sid)['status'] == 'OPEN'


# --- 2. Khi BẬT đủ hai cờ thì đóng đúng ----------------------------------

def test_enabled_and_live_closes_at_shift_boundary_without_inventing_quantity(db, seeded_factory, monkeypatch):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'LIVE-{g["suffix"]}', good=7, defect=2, rework=1)
    window = resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc))
    assert window is not None and window[0]['code'] == 'DAY'
    shift_end = window[2]

    _flags(monkeypatch, enabled=True, dry_run=False)
    now = datetime(2026, 8, 11, 9, 0, tzinfo=HCM)
    results = _mine(ShiftSessionReconciliationService().reconcile(now=now, correlation_id='audit-live'), sid)
    assert results[0]['action'] == 'CLOSED'

    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    assert row['close_reason'] == 'AUTO_SHIFT_END'
    assert row['closed_by_system'] is True
    assert row['ended_at'] == shift_end
    assert row['shift_boundary_used_at'] == shift_end
    # Không tự bịa số: giữ NGUYÊN những gì session đã có.
    assert (row['good_qty'], row['defect_qty'], row['rework_qty']) == (7, 2, 1)
    # ...và phải gắn cờ "cần người bổ sung/xác nhận số liệu", không im lặng coi là xong.
    assert row['quantity_confirmed'] is False
    # Không sinh một chuyển động số lượng giả nào cho lần đóng này.
    moves = fetch_all("SELECT * FROM quantity_movements WHERE session_id=%s AND source='AUTO_SHIFT_CLOSE'", (sid,))
    assert moves == [], f'auto-close bịa ra chuyển động số lượng: {moves}'


def test_auto_closed_duration_does_not_run_overnight(db, seeded_factory, monkeypatch):
    """Báo cáo/dashboard: session đóng ở RANH GIỚI CA, không phải ở "lúc job
    tình cờ chạy" -- nếu không, một session bỏ quên 3 ngày sẽ báo 72 giờ."""
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 16, 0, tzinfo=HCM)
    sid = _open_session(db, g, started_at, f'DUR-{g["suffix"]}')
    _flags(monkeypatch, enabled=True, dry_run=False)
    # Job chạy 3 NGÀY sau -- vẫn phải đóng ở 17:00 ngày 10.
    ShiftSessionReconciliationService().reconcile(
        now=datetime(2026, 8, 13, 9, 0, tzinfo=HCM), correlation_id='audit-duration')

    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    assert row['ended_at'].astimezone(HCM).isoformat(timespec='minutes') == '2026-08-10T17:00+07:00'
    duration = row['ended_at'] - row['started_at']
    assert duration == timedelta(hours=1), f'duration {duration} kéo qua đêm'


# --- 3. Không đóng nhầm session còn đang chạy -----------------------------

def test_session_still_inside_its_own_shift_is_not_touched(db, seeded_factory, monkeypatch):
    g = seeded_factory
    started_at = datetime(2026, 8, 10, 9, 0, tzinfo=HCM)            # trong ca DAY
    sid = _open_session(db, g, started_at, f'TODAY-{g["suffix"]}')
    _flags(monkeypatch, enabled=True, dry_run=False)
    now = datetime(2026, 8, 10, 11, 0, tzinfo=HCM)                  # vẫn trong ca
    assert _mine(ShiftSessionReconciliationService().reconcile(now=now, correlation_id='audit-today'), sid) == []
    assert _row(db, sid)['status'] == 'OPEN'


def test_grace_window_is_respected_before_closing(db, seeded_factory, monkeypatch):
    """Ngay sau 17:00 chưa đóng -- công nhân quét kết thúc muộn vài phút là
    chuyện thật. Chỉ sau grace (mặc định 15 phút) mới thành ứng viên."""
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 16, 0, tzinfo=HCM), f'GRACE-{g["suffix"]}')
    _flags(monkeypatch, enabled=True, dry_run=False)
    svc = ShiftSessionReconciliationService()
    assert _mine(svc.reconcile(now=datetime(2026, 8, 10, 17, 5, tzinfo=HCM), correlation_id='audit-grace-in'), sid) == []
    assert _row(db, sid)['status'] == 'OPEN'
    assert _mine(svc.reconcile(now=datetime(2026, 8, 10, 17, 20, tzinfo=HCM), correlation_id='audit-grace-out'), sid) != []
    assert _row(db, sid)['status'] == 'CLOSED'


# --- 4. Lỗ hổng: khe NO_ACTIVE_SHIFT không có fallback hết ngày -----------

GAP_STARTS = [
    ('khe chiều 17:00-18:00', datetime(2026, 8, 10, 17, 30, tzinfo=HCM)),
    ('khe đêm 00:00-08:00', datetime(2026, 8, 10, 2, 0, tzinfo=HCM)),
]


@pytest.mark.parametrize('label,started_at', GAP_STARTS)
def test_gap_start_really_has_no_shift_to_close_against(label, started_at):
    """Tiền đề của cả nhóm bài dưới: cấu hình ca thật (DAY 08:00-17:00,
    NIGHT 18:00-00:00) để HỞ hai khe. Nếu ai đó cấu hình lại cho kín thì
    bài này đỏ trước, và fallback bên dưới không còn lý do tồn tại."""
    assert resolve_shift_window_for_datetime(started_at.astimezone(timezone.utc)) is None, \
        f'{label} không còn là khe trống -- cấu hình ca đã đổi, đọc lại nhóm bài này'


@pytest.mark.parametrize('label,started_at', GAP_STARTS)
def test_gap_session_is_never_closed_when_day_end_fallback_is_off(
        db, seeded_factory, monkeypatch, label, started_at):
    """Hành vi TRƯỚC bản vá, giữ lại làm bằng chứng hồi quy: không có
    fallback thì session trong khe ở OPEN vĩnh viễn kể cả khi hai công tắc
    auto-close đã bật đủ."""
    g = seeded_factory
    sid = _open_session(db, g, started_at, f'GAPOFF-{g["suffix"]}')
    monkeypatch.setattr(sss, 'settings', dataclasses.replace(
        live_settings, shift_auto_close_enabled=True, shift_auto_close_dry_run=False,
        session_day_end_fallback_enabled=False))
    # Một TUẦN sau vẫn không phải ứng viên.
    results = _mine(ShiftSessionReconciliationService().reconcile(
        now=datetime(2026, 8, 17, 9, 0, tzinfo=HCM), correlation_id='audit-gap-off'), sid)
    assert results == [], f'{label}: có ứng viên dù fallback đã tắt'
    assert _row(db, sid)['status'] == 'OPEN'


@pytest.mark.parametrize('label,started_at', GAP_STARTS)
def test_gap_session_closes_at_day_end_with_fallback_on(
        db, seeded_factory, monkeypatch, label, started_at):
    """Bản vá: đóng ở 24:00 của NGÀY session bắt đầu -- ranh giới xác định
    được duy nhất còn lại -- và đánh dấu AUTO_DAY_END để phân biệt được với
    một lần đóng theo ranh giới ca thật."""
    g = seeded_factory
    sid = _open_session(db, g, started_at, f'GAPON-{g["suffix"]}', good=4, defect=1)
    _flags(monkeypatch, enabled=True, dry_run=False)
    results = _mine(ShiftSessionReconciliationService().reconcile(
        now=datetime(2026, 8, 17, 9, 0, tzinfo=HCM), correlation_id='audit-gap-on'), sid)

    assert len(results) == 1, f'{label}: fallback không tìm ra session'
    assert results[0]['action'] == 'CLOSED'
    assert results[0]['boundary_kind'] == 'DAY_END'
    assert results[0]['shift_code'] == 'NO_ACTIVE_SHIFT'

    row = _row(db, sid)
    assert row['status'] == 'CLOSED'
    assert row['close_reason'] == 'AUTO_DAY_END'
    assert row['closed_by_system'] is True
    assert row['quantity_confirmed'] is False, 'phải chờ admin bổ sung/xác nhận số liệu'
    # 24:00 ngày 10/08 = 00:00 ngày 11/08 giờ VN.
    assert row['ended_at'].astimezone(HCM).isoformat(timespec='minutes') == '2026-08-11T00:00+07:00'
    assert row['ended_at'] > row['started_at']
    # Không suy đoán good/NG.
    assert (row['good_qty'], row['defect_qty'], row['rework_qty']) == (4, 1, 0)
    assert fetch_all("SELECT 1 FROM quantity_movements WHERE session_id=%s AND source='AUTO_SHIFT_CLOSE'", (sid,)) == []


def test_day_end_fallback_is_deterministic_and_idempotent(db, seeded_factory, monkeypatch):
    """Chạy lại vòng reconcile không được đổi ended_at -- ranh giới tính từ
    chính started_at, không phải từ "lúc job chạy"."""
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 17, 30, tzinfo=HCM), f'IDEM-{g["suffix"]}')
    _flags(monkeypatch, enabled=True, dry_run=False)
    svc = ShiftSessionReconciliationService()
    svc.reconcile(now=datetime(2026, 8, 12, 9, 0, tzinfo=HCM), correlation_id='audit-idem-1')
    first = _row(db, sid)['ended_at']
    # Vòng thứ hai, MUỘN HƠN NHIỀU: session đã CLOSED nên không còn là ứng viên.
    again = _mine(svc.reconcile(now=datetime(2026, 8, 20, 9, 0, tzinfo=HCM), correlation_id='audit-idem-2'), sid)
    assert again == []
    assert _row(db, sid)['ended_at'] == first


def test_day_end_auto_close_still_surfaces_as_auto_closed_unconfirmed(db, seeded_factory, monkeypatch):
    """Điều kiện của exception là (closed_by_system AND NOT
    quantity_confirmed), KHÔNG phải close_reason -- nên close_reason mới
    không được làm session rơi khỏi hàng chờ xác nhận của admin."""
    g = seeded_factory
    sid = _open_session(db, g, datetime(2026, 8, 10, 17, 30, tzinfo=HCM), f'EXC-{g["suffix"]}')
    _flags(monkeypatch, enabled=True, dry_run=False)
    ShiftSessionReconciliationService().reconcile(
        now=datetime(2026, 8, 12, 9, 0, tzinfo=HCM), correlation_id='audit-exc')
    rows = fetch_all(
        """SELECT close_reason,closed_by_system,quantity_confirmed FROM work_sessions WHERE id=%s""", (sid,))
    assert rows[0]['close_reason'] == 'AUTO_DAY_END'
    assert rows[0]['closed_by_system'] is True and rows[0]['quantity_confirmed'] is False


# --- 5. Phân biệt "code đã có" với "scheduler đang chạy" ------------------

def test_scheduled_job_health_is_the_only_signal_that_the_job_actually_ran():
    """`shift_session_reconciliation` chỉ có last_started_at khi job THẬT SỰ
    chạy (cron gọi CLI). Một môi trường có đủ code nhưng không cài cron sẽ
    để hàng này ở UNKNOWN/NULL mãi mãi -- đó là thứ phải kiểm trên TEST để
    biết scheduler có sống hay không, không phải đọc code."""
    rows = {r['job_name']: r for r in fetch_all(
        'SELECT job_name,last_started_at,last_status,expected_interval_seconds FROM scheduled_job_health')}
    assert 'shift_session_reconciliation' in rows, \
        'migration 0040 phải seed hàng này, nếu không Health Center không bao giờ báo được NEVER_RUN'
    row = rows['shift_session_reconciliation']
    assert row['expected_interval_seconds'] == 60
    # Không khẳng định đã chạy hay chưa (phụ thuộc thứ tự bài trong suite) --
    # khẳng định INVARIANT: chưa chạy lần nào thì trạng thái phải nói đúng thế.
    if row['last_started_at'] is None:
        assert row['last_status'] in ('UNKNOWN', 'NEVER_RUN'), \
            f"job chưa từng chạy mà báo {row['last_status']} -- Health Center sẽ xanh giả"
