"""HTTP routes of the Report Engine (issue #33).

GET /api/reports/engine/datasets
    Datasets the signed-in user may export + renderer capabilities.
GET /api/reports/engine/<dataset>/export?format=xlsx|pdf|html&<filters>
    One file, streamed from memory (never stored on disk, never cached:
    Cache-Control no-store), so one user's report can never be served to
    another.

Every call needs a valid login AND the dataset's permission (same rule as
the screen that shows those numbers). Each export is written to the
`mesflow.audit.report` log (who, dataset, filters, rows, engine) -- a log
line, not a DB write, so generating a report never modifies data.
"""
from __future__ import annotations

import logging

from flask import Blueprint, Response, jsonify, request, session

from mesflow.core.config import settings
from mesflow.db.repositories.analytics import ReportRepository
from mesflow.reporting import DATASETS, can_access, capabilities
from mesflow.reporting.engine import PdfEngineUnavailable, ReportForbidden, UnknownDataset, build_report
from mesflow.web.auth import _has_permission, login_required
from mesflow.web.errors import api_error_response

bp = Blueprint('report_engine', __name__, url_prefix='/api/reports/engine')
audit_log = logging.getLogger('mesflow.audit.report')


def _role() -> str:
    return str(session.get('role') or '').strip().lower()


@bp.get('/datasets')
@login_required
def list_datasets():
    items = [{'key': s.key, 'title': s.title, 'description': s.description,
              'filters': sorted(s.filters), 'formats': ['xlsx', 'pdf', 'html']}
             for s in DATASETS.values() if can_access(s, _role(), _has_permission)]
    return jsonify(ok=True, items=items, capabilities=capabilities())


@bp.get('/<dataset>/export')
@login_required
def export(dataset):
    try:
        report = build_report(dataset, request.args, repo=ReportRepository(), role=_role(),
                              has_permission=_has_permission,
                              generated_by=str(session.get('username') or 'unknown'),
                              timezone_name=settings.timezone_name)
    except UnknownDataset:
        return jsonify(ok=False, error='NOT_FOUND', message='Không có báo cáo này'), 404
    except ReportForbidden as exc:
        return jsonify(ok=False, error='FORBIDDEN', permission=exc.permission,
                       message='Bạn không có quyền xuất báo cáo này'), 403
    except PdfEngineUnavailable as exc:
        args = request.args.to_dict(flat=True)
        args['format'] = 'html'
        from urllib.parse import urlencode
        return jsonify(ok=False, error='PDF_ENGINE_UNAVAILABLE', detail=str(exc),
                       message='Máy chủ chưa tạo được PDF. Dùng bản in HTML (In / Lưu PDF) thay thế.',
                       fallback_url=f'{request.path}?{urlencode(args)}'), 503
    except Exception as exc:
        return api_error_response(exc, logger_name=__name__)
    audit_log.info('REPORT_EXPORT user=%s role=%s dataset=%s format=%s engine=%s rows=%s filters=%s',
                   session.get('username'), _role(), dataset, report.filename.rsplit('.', 1)[-1], report.engine,
                   report.document.row_count, report.document.metadata.get('filters'))
    inline = report.mimetype.startswith('text/html')
    resp = Response(report.content, mimetype=report.mimetype)
    resp.headers['Content-Disposition'] = ('inline' if inline else 'attachment') + f'; filename="{report.filename}"'
    resp.headers['Cache-Control'] = 'no-store, private'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Report-Engine'] = report.engine
    resp.headers['X-Report-Rows'] = str(report.document.row_count)
    return resp
