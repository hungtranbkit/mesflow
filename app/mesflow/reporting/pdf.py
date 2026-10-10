"""HTML/PDF renderer: Jinja print layout -> WeasyPrint.

WeasyPrint needs native Pango/HarfBuzz libraries (installed in the app
Dockerfile). When the Python package or those libraries are missing,
pdf_status() says why and render_pdf() raises PdfEngineUnavailable; the web
layer answers 503 with a link to the same layout as HTML (browser print),
so a missing library never breaks the rest of the app.

Security: the HTML is rendered with autoescape, and WeasyPrint gets a
url_fetcher that refuses every URL, so report content can never make the
server fetch a remote/local resource (SSRF / file read).
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mesflow.reporting.datasets import DATE, DATETIME, DURATION, INT, NUMBER, PERCENT, ReportDocument

TEMPLATE = 'report_engine_document.html'
_TEMPLATES = Path(__file__).resolve().parents[1] / 'web' / 'templates'


class PdfEngineUnavailable(RuntimeError):
    """WeasyPrint (or its native libraries) cannot be loaded."""


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=select_autoescape(['html']))


def _group(n: int) -> str:
    return f'{n:,}'.replace(',', '.')


def make_formatter(tz: ZoneInfo):
    """Vietnamese display: 1.234 ; 85,5% ; 12:05:09 ; 02/09/2026 08:00."""
    def fmt(value: Any, kind: str) -> str:
        if value is None or value == '':
            return ''
        if kind == INT:
            return _group(int(value))
        if kind == NUMBER:
            v = float(value)
            return _group(int(v)) if v == int(v) else f'{v:.2f}'.replace('.', ',')
        if kind == PERCENT:
            return f'{float(value):.1f}%'.replace('.', ',')
        if kind == DURATION:
            s = int(round(max(float(value), 0)))
            return f'{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}'
        if kind == DATETIME and isinstance(value, datetime):
            return (value.astimezone(tz) if value.tzinfo else value).strftime('%d/%m/%Y %H:%M')
        if kind == DATE and isinstance(value, (date, datetime)):
            return value.strftime('%d/%m/%Y')
        return str(value)
    return fmt


def render_html(doc: ReportDocument, *, timezone_name: str, html_mode: bool = False) -> str:
    return _env().get_template(TEMPLATE).render(doc=doc, fmt=make_formatter(ZoneInfo(timezone_name)), html_mode=html_mode)


def _deny_all_urls(url: str, *args, **kwargs):
    raise ValueError(f'Report Engine PDF does not fetch external resources: {url[:80]}')


@lru_cache(maxsize=1)
def _probe() -> tuple[bool, str]:
    try:
        import weasyprint  # noqa: F401  (OSError when libpango is missing)
        return True, f'weasyprint {getattr(weasyprint, "__version__", "?")}'
    except ImportError as exc:
        return False, f'Chưa cài thư viện WeasyPrint ({exc})'
    except OSError as exc:
        return False, f'Thiếu thư viện hệ thống cho WeasyPrint (Pango/HarfBuzz): {exc}'
    except Exception as exc:  # pragma: no cover - any other load failure
        return False, f'Không nạp được WeasyPrint: {type(exc).__name__}: {exc}'


def pdf_status() -> tuple[bool, str]:
    return _probe()


def render_pdf(doc: ReportDocument, *, timezone_name: str) -> bytes:
    ok, reason = pdf_status()
    if not ok:
        raise PdfEngineUnavailable(reason)
    from weasyprint import HTML

    html = render_html(doc, timezone_name=timezone_name)
    # <title> becomes the PDF title; base_url=None + deny-all fetcher = no I/O.
    return HTML(string=html, base_url=None, url_fetcher=_deny_all_urls).write_pdf()
