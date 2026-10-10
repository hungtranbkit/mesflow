"""build_report(): validated request -> authorized dataset -> rendered file.

The single entry point for the HTTP routes and for any future caller (e.g.
the chatbot's validated report intent): it never accepts SQL, only a
dataset key plus typed filters, and it applies the same permission rule as
the UI before touching data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from mesflow.reporting.datasets import DATASETS, ReportDocument, build_document, can_access
from mesflow.reporting import pdf as pdf_engine
from mesflow.reporting.pdf import PdfEngineUnavailable, render_html, render_pdf
from mesflow.reporting.schema import ReportValidationError, parse_report_request
from mesflow.reporting.xlsx import render_xlsx, xlsxwriter_available

MIMETYPES = {
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'pdf': 'application/pdf',
    'html': 'text/html',  # Flask appends '; charset=utf-8'
}


class UnknownDataset(LookupError):
    pass


class ReportForbidden(PermissionError):
    def __init__(self, permission: str):
        super().__init__(permission)
        self.permission = permission


@dataclass
class RenderedReport:
    content: bytes
    mimetype: str
    filename: str
    engine: str
    document: ReportDocument


def capabilities() -> dict[str, Any]:
    pdf_ok, pdf_reason = pdf_engine.pdf_status()
    return {
        'xlsx': {'available': True, 'engine': 'xlsxwriter' if xlsxwriter_available() else 'openpyxl-fallback'},
        'pdf': {'available': pdf_ok, 'engine': 'weasyprint' if pdf_ok else None, 'detail': pdf_reason},
        'html': {'available': True, 'engine': 'jinja2'},
    }


def _filename(doc: ReportDocument, fmt: str) -> str:
    stem = f"mesflow_{doc.dataset}_{doc.metadata.get('date_from') or 'from'}_{doc.metadata.get('date_to') or 'to'}"
    return re.sub(r'[^A-Za-z0-9_.-]', '-', stem) + f'.{fmt}'


def build_report(dataset: str, args: Mapping[str, Any], *, repo, role: str, has_permission: Callable[[str], bool],
                 generated_by: str, timezone_name: str, now=None) -> RenderedReport:
    spec = DATASETS.get(dataset)
    if spec is None:
        raise UnknownDataset(dataset)
    if not can_access(spec, role, has_permission):
        raise ReportForbidden(spec.permission)
    req = parse_report_request(dataset, args, allowed_filters=spec.filters, sort_keys=spec.sort_keys)
    doc = build_document(req, repo, generated_by=generated_by, timezone_name=timezone_name, now=now)
    if req.format == 'xlsx':
        content, engine = render_xlsx(doc, timezone_name=timezone_name)
    elif req.format == 'pdf':
        content, engine = render_pdf(doc, timezone_name=timezone_name), 'weasyprint'
    else:
        content, engine = render_html(doc, timezone_name=timezone_name, html_mode=True).encode('utf-8'), 'html'
    return RenderedReport(content, MIMETYPES[req.format], _filename(doc, req.format), engine, doc)


__all__ = ['MIMETYPES', 'PdfEngineUnavailable', 'RenderedReport', 'ReportForbidden', 'ReportValidationError',
           'UnknownDataset', 'build_report', 'capabilities']
