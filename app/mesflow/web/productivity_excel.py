from __future__ import annotations

from io import BytesIO
from typing import Any, Iterable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

EXPORT_HEADERS = [
    "STT", "Mã NV", "Nhân viên", "Bộ phận", "Nhóm",
    "Phiên hoàn tất", "Phiên hợp lệ", "Năng suất TB (%)",
    "Sản lượng đạt", "Lỗi", "Tổng thời gian", "NV xác nhận",
]

SORT_FIELDS = {
    "employee_name": "employee_name",
    "employee": "employee_name",
    "session": "completed_sessions",
    "completed_sessions": "completed_sessions",
    "productivity": "productivity_percent",
    "productivity_percent": "productivity_percent",
    "good_qty": "good_qty",
    "output": "good_qty",
    "worked_seconds": "worked_seconds",
    "time": "worked_seconds",
}


def filter_and_sort_employee_rows(
    employees: Iterable[dict[str, Any]],
    *,
    search: str = "",
    department: str = "",
    sort_key: str = "productivity_percent",
    sort_dir: str = "desc",
) -> list[dict[str, Any]]:
    query = (search or "").strip().casefold()
    department = (department or "").strip()
    rows: list[dict[str, Any]] = []
    for raw in employees:
        row = dict(raw)
        if department and str(row.get("department") or "") != department:
            continue
        if query:
            haystack = f"{row.get('employee_name') or ''} {row.get('employee_code') or ''}".casefold()
            if query not in haystack:
                continue
        rows.append(row)

    field = SORT_FIELDS.get(sort_key, "productivity_percent")
    reverse = str(sort_dir).lower() != "asc"
    if field == "employee_name":
        rows.sort(
            key=lambda row: (
                str(row.get("employee_name") or "").casefold(),
                str(row.get("employee_code") or "").casefold(),
            ),
            reverse=reverse,
        )
        return rows

    present = [row for row in rows if row.get(field) is not None]
    missing = [row for row in rows if row.get(field) is None]
    present.sort(
        key=lambda row: (
            float(row.get(field) or 0),
            str(row.get("employee_code") or "").casefold(),
        ),
        reverse=reverse,
    )
    return present + missing


def _duration_days(seconds: Any) -> float:
    try:
        return max(float(seconds or 0), 0.0) / 86400.0
    except (TypeError, ValueError):
        return 0.0


def build_employee_productivity_xlsx(
    report: dict[str, Any],
    *,
    search: str = "",
    department: str = "",
    sort_key: str = "productivity_percent",
    sort_dir: str = "desc",
) -> BytesIO:
    rows = filter_and_sort_employee_rows(
        report.get("employees") or [],
        search=search,
        department=department,
        sort_key=sort_key,
        sort_dir=sort_dir,
    )
    scores = [float(row["productivity_percent"]) for row in rows if row.get("productivity_percent") is not None]
    filtered_avg = (sum(scores) / len(scores)) if scores else None
    summary = report.get("summary") or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "Năng suất nhân viên"
    ws.sheet_view.showGridLines = False
    last_col = len(EXPORT_HEADERS)
    last_letter = get_column_letter(last_col)

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws["A1"] = "BÁO CÁO NĂNG SUẤT NHÂN VIÊN"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 26

    filters = [
        f"Từ ngày: {summary.get('from') or '—'}",
        f"Đến ngày: {summary.get('to') or '—'}",
        f"Bộ phận: {department or 'Tất cả'}",
        f"Tìm nhân viên: {search.strip() or 'Tất cả'}",
        f"Năng suất TB theo bộ lọc: {filtered_avg:.1f}%" if filtered_avg is not None else "Năng suất TB theo bộ lọc: —",
    ]
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws["A2"] = " | ".join(filters)
    ws["A2"].font = Font(size=10)
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center")

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_col)
    ws["A3"] = 'In bảng này và để nhân viên ký/xác nhận tại cột "NV xác nhận".'
    ws["A3"].font = Font(italic=True, size=10)
    ws["A3"].alignment = Alignment(horizontal="left", vertical="center")

    header_row = 4
    thin = Side(style="thin", color="B8C2CC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    for col, header in enumerate(EXPORT_HEADERS, 1):
        cell = ws.cell(header_row, col, header)
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = border
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[header_row].height = 28

    for index, item in enumerate(rows, 1):
        row_idx = header_row + index
        pct = item.get("productivity_percent")
        values = [
            index,
            item.get("employee_code") or "",
            item.get("employee_name") or "",
            item.get("department") or "",
            item.get("team") or "",
            int(item.get("completed_sessions") or 0),
            int(item.get("completed_valid_sessions") or 0),
            (float(pct) / 100.0) if pct is not None else None,
            int(item.get("good_qty") or 0),
            int(item.get("defect_qty") or 0),
            _duration_days(item.get("worked_seconds")),
            "",
        ]
        for col, value in enumerate(values, 1):
            cell = ws.cell(row_idx, col, value)
            cell.border = border
            cell.alignment = Alignment(
                horizontal="left" if col in (2, 3, 4, 5, 12) else "center",
                vertical="center",
                wrap_text=col in (3, 4, 5, 12),
            )
        ws.cell(row_idx, 8).number_format = "0.0%"
        ws.cell(row_idx, 11).number_format = "[h]:mm"
        ws.row_dimensions[row_idx].height = 30

    last_row = max(header_row, header_row + len(rows))
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A{header_row}:{last_letter}{last_row}"
    ws.print_area = f"A1:{last_letter}{last_row}"
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.45
    ws.page_margins.bottom = 0.45
    ws.oddFooter.center.text = "Trang &[Page]/&[Pages]"

    widths = [6, 13, 24, 18, 16, 13, 13, 15, 15, 11, 16, 22]
    for col, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = width

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream
