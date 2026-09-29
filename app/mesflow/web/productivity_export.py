"""Data behind the employee-productivity Excel export AND the print view.

One place turns the request's filters into: the filtered + sorted summary
rows (exactly what the screen lists), and each of those employees' sessions
-- from ONE bulk session query, grouped in memory (no per-employee query).
Excel (productivity_excel.py) and print (templates/
employee_productivity_print.html) both render this, so they can never
disagree with each other or with the screen.
"""
from __future__ import annotations

from typing import Any, Mapping

from mesflow.db.repositories.base import NotFoundError
from mesflow.web.productivity_excel import filter_and_sort_employee_rows


def parse_filters(args: Mapping[str, Any]) -> dict[str, Any]:
    """The report's query parameters, as the screen sends them.

    `employee_id` narrows everything to one employee; it must belong to the
    set the other filters produce (checked in load_export_data), otherwise
    a crafted id could print an employee outside the manager's filter.
    """
    raw_employee = str(args.get('employee_id') or '').strip()
    if raw_employee and not raw_employee.isdigit():
        raise ValueError('employee_id không hợp lệ')
    return {
        'from': args.get('from') or None,
        'to': args.get('to') or None,
        'employee_id': int(raw_employee) if raw_employee else None,
        'department': args.get('department') or None,
        'team': args.get('team') or None,
        'search': args.get('search') or '',
        'sort': args.get('sort') or 'productivity_percent',
        'dir': args.get('dir') or 'desc',
    }


def group_sessions(employees: list[dict[str, Any]], sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{employee, sessions}] in the employees' (summary) order; each
    employee's sessions by start time. Sessions of employees outside the
    list are dropped."""
    buckets: dict[Any, list[dict[str, Any]]] = {row.get('employee_id'): [] for row in employees}
    for session in sessions:
        bucket = buckets.get(session.get('employee_id'))
        if bucket is not None:
            bucket.append(dict(session))
    for bucket in buckets.values():
        bucket.sort(key=lambda s: (str(s.get('started_at') or ''), s.get('session_id') or 0))
    return [{'employee': row, 'sessions': buckets[row.get('employee_id')]} for row in employees]


def load_export_data(filters: dict[str, Any], repo) -> dict[str, Any]:
    """Two queries total, whatever the number of employees."""
    report = repo.employee_productivity(
        filters['from'], filters['to'], filters['employee_id'],
        filters['department'], filters['team'], 5000)
    employees = filter_and_sort_employee_rows(
        report.get('employees') or [],
        search=filters['search'],
        department=filters['department'] or '',
        sort_key=filters['sort'],
        sort_dir=filters['dir'],
    )
    if filters['employee_id'] is not None and not any(
            row.get('employee_id') == filters['employee_id'] for row in employees):
        raise NotFoundError('Nhân viên không nằm trong bộ lọc hiện tại')
    detail = repo.employee_productivity_sessions(
        filters['from'], filters['to'], filters['employee_id'],
        filters['department'], filters['team'])
    summary = report.get('summary') or {}
    return {
        'report': report,
        'employees': employees,
        'groups': group_sessions(employees, detail.get('sessions') or []),
        'truncated': bool(detail.get('truncated')),
        'filters': filters,
        'date_from': summary.get('from') or filters['from'],
        'date_to': summary.get('to') or filters['to'],
    }
