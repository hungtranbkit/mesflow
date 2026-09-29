"""Excel năng suất -- "Chi tiết từng nhân viên" (hotfix 2026-09-29).

One row per session behind the summary report, same filters, same
per-session score; the summary export itself must not change.
"""
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook

from mesflow.web.productivity_excel import (
    DETAIL_HEADERS,
    DETAIL_SHEET,
    DETAIL_SUMMARY_SHEET,
    EXPORT_HEADERS,
    build_employee_productivity_detail_xlsx,
    build_employee_productivity_xlsx,
    detail_rows_for_employees,
    session_status_note,
)

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc


def _employee(emp_id, code, name, dept, sessions, valid, pct, good, defect, seconds):
    return {"employee_id": emp_id, "employee_code": code, "employee_name": name, "department": dept, "team": "",
            "completed_sessions": sessions, "completed_valid_sessions": valid, "completed_invalid_sessions": sessions - valid,
            "repair_sessions": 0, "productivity_percent": pct, "good_qty": good, "defect_qty": defect,
            "worked_seconds": seconds}


def _session(sid, emp_id, code, name, dept, op, start, end, good, defect, std, pct, **extra):
    actual = (end - start).total_seconds()
    row = {"session_id": sid, "employee_id": emp_id, "employee_code": code, "employee_name": name, "department": dept,
           "team": "", "status": "CLOSED", "started_at": start, "ended_at": end, "work_date": date(2026, 9, end.day),
           "actual_seconds": actual, "standard_seconds_per_unit": std, "expected_seconds": std * (good + defect),
           "good_qty": good, "defect_qty": defect, "po_code": "PO-1", "part_code": "P-1", "part_name": "Thân",
           "operation_code": op, "operation_name": f"Công đoạn {op}", "station_code": "ST1",
           "closed_by_system": False, "quantity_confirmed": True, "close_reason": None, "note": None,
           "is_repair": False, "operation_type": "PRODUCTION", "completion_percent": pct}
    row.update(extra)
    return row


def _fixture():
    t = lambda d, h, m=0: datetime(2026, 9, d, h, m, tzinfo=UTC)
    # An (NV01): 3 sessions, TWO on the same OP10 -> each must be its own row.
    # 01:00Z = 08:00 Asia/Ho_Chi_Minh.
    sessions = [
        _session(11, 1, "NV01", "An", "May", "OP10", t(2, 1), t(2, 2), 24, 0, 120, 80.0),
        _session(12, 1, "NV01", "An", "May", "OP10", t(2, 3), t(2, 4), 36, 0, 100, 100.0),
        _session(13, 1, "NV01", "An", "May", "OP20", t(3, 1), t(3, 1, 30), 0, 0, 0, None),
        # Bình (NV02): one scored session, auto-closed without a confirmed quantity.
        _session(21, 2, "NV02", "Bình", "May", "OP10", t(2, 5), t(2, 6), 45, 5, 60, 83.33,
                 closed_by_system=True, quantity_confirmed=False, close_reason="Hết ca"),
        # Cường (NV03) is in another department -> filtered out.
        _session(31, 3, "NV03", "Cường", "Kho", "OP90", t(2, 1), t(2, 2), 10, 0, 360, 100.0),
    ]
    employees = [
        _employee(1, "NV01", "An", "May", 3, 2, 90.0, 60, 0, 9000),
        _employee(2, "NV02", "Bình", "May", 1, 1, 83.33, 45, 5, 3600),
        _employee(3, "NV03", "Cường", "Kho", 1, 1, 100.0, 10, 0, 3600),
    ]
    report = {"summary": {"from": "2026-09-01", "to": "2026-09-29"}, "employees": employees}
    return report, {"from": "2026-09-01", "to": "2026-09-29", "sessions": sessions, "truncated": False}


def _book(**kw):
    report, detail = _fixture()
    stream = build_employee_productivity_detail_xlsx(report, detail, **kw)
    return load_workbook(BytesIO(stream.getvalue()))


def _data_rows(ws, first=5):
    return [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)] for r in range(first, ws.max_row + 1)
            if ws.cell(r, 1).value is not None]


def test_detail_sheet_has_required_columns_and_one_row_per_session():
    wb = _book(department="May", sort_key="productivity_percent", sort_dir="desc")
    assert wb.sheetnames == [DETAIL_SHEET, DETAIL_SUMMARY_SHEET]
    ws = wb[DETAIL_SHEET]
    assert [ws.cell(4, c).value for c in range(1, len(DETAIL_HEADERS) + 1)] == DETAIL_HEADERS
    for required in ("Mã NV", "Nhân viên", "Ngày", "PO", "Part", "Mã OP", "Operation", "Bắt đầu", "Kết thúc",
                     "Thời gian thực tế", "Sản lượng đạt", "Thời gian định mức", "% năng suất",
                     "Trạng thái / ghi chú", "NV xác nhận"):
        assert required in DETAIL_HEADERS
    rows = _data_rows(ws)
    col = {h: i for i, h in enumerate(DETAIL_HEADERS)}
    # Department filter drops NV03; order follows the summary sort
    # (An 90.0 before Bình 83.33); within An by start time; OP10 twice.
    assert [r[col["Mã phiên"]] for r in rows] == [11, 12, 13, 21]
    assert [r[col["Mã OP"]] for r in rows[:2]] == ["OP10", "OP10"]
    assert rows[0][col["Part"]] == "P-1 · Thân"
    # Local wall-clock time (08:00 ICT), stored as a real Excel datetime.
    assert rows[0][col["Bắt đầu"]] == datetime(2026, 9, 2, 8, 0)
    assert rows[0][col["Thời gian thực tế"]] == timedelta(hours=1)
    assert rows[0][col["Thời gian định mức"]] == timedelta(seconds=2880)
    assert rows[0][col["% năng suất"]] == 0.8
    assert rows[2][col["% năng suất"]] is None
    assert rows[0][col["NV xác nhận"]] is None  # signature column, left blank
    assert "Tìm nhân viên: Tất cả" in ws["A2"].value and "Bộ phận: May" in ws["A2"].value
    assert "2 nhân viên · 4 phiên" in ws["A2"].value


def test_detail_sheet_is_usable_freeze_filter_and_formats():
    ws = _book()[DETAIL_SHEET]
    assert ws.freeze_panes == "D5"
    assert ws.auto_filter.ref == f"A4:T{4 + 5}"
    assert ws["J5"].number_format == "dd/mm/yyyy hh:mm"
    assert ws["L5"].number_format == "[h]:mm:ss"
    assert ws["P5"].number_format == "[h]:mm:ss"
    assert ws["Q5"].number_format == "0.0%"
    assert ws["E5"].number_format == "dd/mm/yyyy"
    assert ws.column_dimensions["R"].width >= 30


def test_search_filter_matches_the_summary_screen_filter():
    rows = _data_rows(_book(search="bình")[DETAIL_SHEET])
    assert {r[1] for r in rows} == {"NV02"}


def test_detail_percent_reconciles_with_summary_percent():
    """Summary productivity_percent = AVG of the non-empty per-session %."""
    report, detail = _fixture()
    rows = detail_rows_for_employees(report["employees"], detail["sessions"])
    for emp in report["employees"]:
        mine = [r for r in rows if r["employee_id"] == emp["employee_id"]]
        assert len(mine) == emp["completed_sessions"]
        scored = [r["completion_percent"] for r in mine if r["completion_percent"] is not None]
        assert len(scored) == emp["completed_valid_sessions"]
        assert round(sum(scored) / len(scored), 2) == emp["productivity_percent"]
        assert sum(r["good_qty"] for r in mine) == emp["good_qty"]


def test_tong_hop_sheet_is_the_unchanged_summary_sheet():
    report, _ = _fixture()
    kw = dict(search="", department="May", sort_key="productivity_percent", sort_dir="desc")
    summary = load_workbook(BytesIO(build_employee_productivity_xlsx(report, **kw).getvalue()))["Năng suất nhân viên"]
    tong_hop = _book(**kw)[DETAIL_SUMMARY_SHEET]
    assert [tong_hop.cell(4, c).value for c in range(1, len(EXPORT_HEADERS) + 1)] == EXPORT_HEADERS
    grid = lambda ws: [[ws.cell(r, c).value for c in range(1, 13)] for r in range(1, ws.max_row + 1)]
    assert grid(tong_hop) == grid(summary)
    assert tong_hop.freeze_panes == summary.freeze_panes == "A5"


def test_status_note_uses_existing_session_flags_only():
    report, detail = _fixture()
    by_id = {s["session_id"]: s for s in detail["sessions"]}
    assert session_status_note(by_id[11]) == "Tính năng suất"
    assert session_status_note(by_id[13]) == "Thiếu định mức · không tính năng suất"
    assert session_status_note(by_id[21]) == "Tính năng suất · Hệ thống tự đóng · Chưa xác nhận sản lượng · Hết ca"
    assert session_status_note({**by_id[13], "is_repair": True}) == "Ca sửa hàng · không có định mức"
    no_output = {**by_id[11], "completion_percent": None, "good_qty": 0, "defect_qty": 0}
    assert session_status_note(no_output) == "Không có sản lượng · không tính năng suất"


def test_truncation_is_announced_in_the_sheet():
    report, detail = _fixture()
    detail["truncated"] = True
    ws = load_workbook(BytesIO(build_employee_productivity_detail_xlsx(report, detail).getvalue()))[DETAIL_SHEET]
    assert "CẢNH BÁO" in ws["A3"].value


def test_route_offers_detail_mode_without_changing_summary_default():
    src = (ROOT / "app/mesflow/web/analytics.py").read_text(encoding="utf-8")
    route = src.split("@bp.get('/reports/employee-productivity/export.xlsx')", 1)[1].split("@bp.get(", 1)[0]
    assert "@login_required" in route  # same access rule as the summary export
    assert "mode=(request.args.get('mode') or 'summary')" in route
    assert "if mode not in ('summary','detail'): raise ValueError" in route
    assert "repo.employee_productivity_sessions(" in route
    assert "build_employee_productivity_xlsx(report,**options)" in route
    assert "nang-suat-nhan-vien-chi-tiet" in route


def test_repository_detail_uses_the_same_scope_and_score_as_the_summary():
    src = (ROOT / "app/mesflow/db/repositories/analytics.py").read_text(encoding="utf-8")
    agg = src.split("    def employee_productivity(self", 1)[1].split("\n    def ", 1)[0]
    det = src.split("    def employee_productivity_sessions(self", 1)[1].split("\n    def ", 1)[0]
    for body in (agg, det):
        assert "self._productivity_scope(date_from,date_to,employee_id,department,team)" in body
        assert "{self._SESSION_COMPLETION_PERCENT_SQL} completion_percent" in body
    assert "fetch_all(" in det and det.count("fetch_all(") == 1  # one query, no N+1


def test_frontend_export_menu_offers_summary_and_detail():
    js = (ROOT / "app/mesflow/web/static/pages/employee-productivity.js").read_text(encoding="utf-8")
    assert 'id="epExport"' in js and 'aria-haspopup="menu"' in js
    assert "MFUI.rowMenu(e.currentTarget, [" in js
    assert "'Tổng hợp theo nhân viên', onSelect: () => exportExcel('summary')" in js
    assert "'Chi tiết từng nhân viên (từng phiên làm việc)', onSelect: () => exportExcel('detail')" in js
    assert "if (mode === 'detail') q.set('mode', 'detail');" in js
