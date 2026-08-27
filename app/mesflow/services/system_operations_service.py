"""Real, allow-listed service control for the SUPER_ADMIN System Console
(task spec section 11/12/22-26). Deliberately does NOT talk to Docker or a
shell itself -- it proxies to Deploy Agent's existing, already-tested
RecoveryOrchestrator (deploy-agent/agent_backend/incident_recovery.py) over
the same internal-token HTTP channel diagnostic_service.py's `_agent_get`
already uses for reads. No new job engine, no new sandbox/container logic.

Fixed allow-list, deliberately narrower than Deploy Agent's own (which also
manages postgres/nginx): only application-tier services a MESFlow operator
should ever restart from MESFlow's own console. Database and reverse-proxy
restart stay Deploy-Agent-console-only (spec section 12: "prefer not to
expose DB stop/restart initially").
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from mesflow.core.config import settings

# MESFlow-side id -> Deploy Agent's own RecoveryOrchestrator service id
# (deploy-agent/agent_backend/incident_recovery.py MANAGED_SERVICES).
# Every id that can ever reach an HTTP call to Deploy Agent is listed here,
# server-side, fixed -- no request field ever supplies a raw container/unit
# name (spec section 11/22: "No arbitrary service IDs should flow into
# shell commands").
SERVICE_ALLOWLIST: dict[str, dict[str, str]] = {
    'mesflow_app': {'agent_id': 'mesflow', 'label': 'MESFlow Application'},
    'qa_center': {'agent_id': 'qa', 'label': 'QA Center'},
}


def _agent_request(path: str, *, method: str = 'GET', body: dict[str, Any] | None = None,
                    timeout: float | None = None) -> tuple[dict[str, Any] | None, str]:
    if not settings.health_deploy_agent_url:
        return None, 'DEPLOY_AGENT_NOT_CONFIGURED'
    headers = {'X-MESFlow-Internal-Token': settings.internal_api_token} if settings.internal_api_token else {}
    data = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        data = json.dumps(body).encode('utf-8')
    req = urllib.request.Request(settings.health_deploy_agent_url + path, headers=headers,
                                  method=method, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout or settings.health_external_timeout_seconds) as r:
            return json.loads(r.read(500000)), ''
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read(500000)), f'HTTP_{e.code}'
        except Exception:
            return None, f'HTTP_{e.code}'
    except Exception as e:
        return None, type(e).__name__


class SystemOperationsService:
    def list_services(self) -> list[dict[str, Any]]:
        """Real health per allow-listed service. Never fabricates a status:
        an unreachable Deploy Agent reports every entry UNKNOWN with the
        real error, not a fake HEALTHY/DOWN guess."""
        data, err = _agent_request('/api/ops/recovery/services')
        items = {i['id']: i for i in (data or {}).get('items', [])} if not err and data and data.get('ok') else {}
        out = []
        for mesflow_id, meta in SERVICE_ALLOWLIST.items():
            item = items.get(meta['agent_id'])
            if item is None:
                out.append({'id': mesflow_id, 'label': meta['label'], 'status': 'UNKNOWN',
                           'reachable': False, 'error': err or 'NOT_FOUND'})
            else:
                out.append({'id': mesflow_id, 'label': meta['label'], 'status': item.get('state', 'UNKNOWN'),
                           'reachable': True, 'container': item.get('container'),
                           'health': item.get('health')})
        return out

    def restart_service(self, service_id: str, *, actor: str, reason: str,
                         production_approved: bool, correlation_id: str = '') -> dict[str, Any]:
        """Returns the REAL result of the restart attempt -- RESTARTED /
        FAILED_TO_RESTART / BLOCKED / an HTTP/network error -- never
        reports success merely because the request was sent (spec section
        24). production_approved is never inferred here: the caller
        (web route) decides it from the operator's explicit confirmation,
        checked against the server's own environment identity."""
        meta = SERVICE_ALLOWLIST.get(service_id)
        if not meta:
            return {'ok': False, 'result': 'UNKNOWN_SERVICE', 'service_id': service_id}
        data, err = _agent_request(
            f"/api/ops/recovery/services/{meta['agent_id']}/restart", method='POST',
            body={'confirm_production': bool(production_approved), 'incident_id': correlation_id,
                  'actor': actor, 'reason': reason},
            timeout=90,
        )
        if err:
            return {'ok': False, 'result': 'DEPLOY_AGENT_UNREACHABLE', 'service_id': service_id, 'error': err}
        item = (data or {}).get('item') or {}
        action = item.get('action', 'UNKNOWN')
        return {'ok': bool((data or {}).get('ok')), 'result': action, 'service_id': service_id,
                'reason_from_agent': item.get('reason', '')}
