#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
warn=0
ok(){ echo "[PASS] $*"; }
bad(){ echo "[FAIL] $*"; fail=1; }
warning(){ echo "[WARN] $*"; warn=$((warn+1)); }

[[ -f .env ]] || bad ".env missing"
if [[ -f .env ]]; then
  mode="$(stat -c '%a' .env 2>/dev/null || true)"
  [[ "$mode" == "600" || "$mode" == "640" ]] && ok ".env permissions=$mode" || warning ".env permissions=$mode (recommend 600 or 640)"

  readv(){ grep -E "^$1=" .env | tail -1 | cut -d= -f2- || true; }
  [[ "$(readv MESFLOW_ENV)" == "production" ]] && ok "MESFLOW_ENV=production" || bad "MESFLOW_ENV must be production"
  [[ "$(readv MESFLOW_TEST_AUTO_LOGIN)" =~ ^(0|false|False)?$ ]] && ok "test auto-login disabled" || bad "MESFLOW_TEST_AUTO_LOGIN must be 0"
  [[ "$(readv MESFLOW_LOCAL_AUTO_LOGIN)" =~ ^(0|false|False)?$ ]] && ok "local auto-login disabled" || bad "MESFLOW_LOCAL_AUTO_LOGIN must be 0"
  [[ "$(readv MESFLOW_INTERNAL_QA_AUTO_LOGIN)" =~ ^(0|false|False)?$ ]] && ok "QA auto-login disabled" || bad "MESFLOW_INTERNAL_QA_AUTO_LOGIN must be 0"
  [[ "$(readv MESFLOW_ENABLE_FORCE_DELETE_PO)" =~ ^(0|false|False)?$ ]] && ok "force-delete disabled" || bad "MESFLOW_ENABLE_FORCE_DELETE_PO must be 0"

  secret="$(readv MESFLOW_SECRET_KEY)"
  [[ -n "$secret" && "$secret" != "CHANGE_ME" && "$secret" != "dev-only" ]] && ok "secret key configured" || bad "MESFLOW_SECRET_KEY unsafe/missing"
  pg="$(readv POSTGRES_PASSWORD)"
  [[ -n "$pg" && "$pg" != "MesflowChangeMe2026" ]] && ok "PostgreSQL password configured" || bad "POSTGRES_PASSWORD unsafe/missing"
  db="$(readv DATABASE_URL)"
  [[ "$db" == postgresql://* ]] && ok "DATABASE_URL PostgreSQL configured" || bad "DATABASE_URL missing/non-PostgreSQL"
fi

docker compose config --quiet && ok "compose config valid" || bad "compose config invalid"

if docker ps --format '{{.Names}}' | grep -qx mesflow-app; then
  curl -fsS http://127.0.0.1:8080/api/system/ready >/dev/null && ok "MESFlow ready" || bad "MESFlow /ready failed"
  code="$(curl -sS -o /tmp/mesflow-autologin.json -w '%{http_code}' -X POST http://127.0.0.1:8080/api/auth/test-auto-login || true)"
  [[ "$code" == "403" ]] && ok "production auto-login endpoint blocked" || bad "auto-login endpoint returned HTTP $code, expected 403"
else
  warning "mesflow-app is not currently running; runtime checks skipped"
fi

echo
echo "Preflight warnings: $warn"
if [[ "$fail" != "0" ]]; then
  echo "PRODUCTION PREFLIGHT: FAIL"
  exit 1
fi
echo "PRODUCTION PREFLIGHT: PASS"
