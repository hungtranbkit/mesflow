#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VERSION="unknown"
if [[ -f VERSION.txt ]]; then
    VERSION="$(tr -d '[:space:]' < VERSION.txt)"
elif [[ -f VERSION ]]; then
    VERSION="$(tr -d '[:space:]' < VERSION)"
fi

PROJECT_NAME="${PROJECT_NAME:-mesflow}"
OUTPUT_DIR="${OUTPUT_DIR:-dist}"
OUTPUT_FILE="${OUTPUT_DIR}/${PROJECT_NAME}-source-v${VERSION}.zip"

mkdir -p "$OUTPUT_DIR"
rm -f "$OUTPUT_FILE"

echo "========================================"
echo " MESFlow Source Packager"
echo "========================================"
echo "Project : $PROJECT_NAME"
echo "Version : $VERSION"
echo "Output  : $OUTPUT_FILE"
echo

# Source-only package. Keep Dockerfile/Compose definitions, migrations,
# scripts, tests and .env.example; exclude generated/runtime/persistent data.
zip -q -r "$OUTPUT_FILE" . \
  -x '.git/*' \
  -x '.github/cache/*' \
  -x '.env' \
  -x '.env.*' \
  -x '.venv/*' \
  -x 'venv/*' \
  -x 'env/*' \
  -x '__pycache__/*' \
  -x '*/__pycache__/*' \
  -x '*.pyc' -x '*.pyo' -x '*.pyd' \
  -x 'node_modules/*' -x '*/node_modules/*' \
  -x '.npm/*' -x '.yarn/*' -x '.pnpm-store/*' \
  -x 'vendor/*' -x '*/vendor/*' \
  -x 'dist/*' -x 'build/*' -x 'target/*' \
  -x '.next/*' -x '.nuxt/*' -x '.cache/*' \
  -x '.pytest_cache/*' -x '*/.pytest_cache/*' \
  -x 'coverage/*' -x 'htmlcov/*' \
  -x 'test-results/*' -x 'playwright-report/*' \
  -x '.projectflow/ai-runs/*' \
  -x 'runtime/*' -x 'runtime-projectflow-local/*' \
  -x 'docker-data/*' -x '.docker/*' \
  -x 'data/*' -x 'database/*' \
  -x 'postgres-data/*' -x 'postgres_data/*' -x 'pgdata/*' \
  -x 'redis-data/*' -x 'redis_data/*' \
  -x 'uploads/*' -x 'media/*' -x 'storage/*' \
  -x 'logs/*' -x 'log/*' -x '*.log' \
  -x 'backups/*' -x 'backup/*' \
  -x 'artifacts/*' \
  -x '*.db' -x '*.sqlite' -x '*.sqlite3' \
  -x '*.dump' -x '*.sql' -x '*.backup' -x '*.bak' \
  -x '*.tar' -x '*.tar.gz' -x '*.tgz' -x '*.7z' -x '*.rar' -x '*.zip' \
  -x '.DS_Store' -x 'Thumbs.db' \
  -x 'tmp/*' -x 'temp/*' \
  -x "${OUTPUT_DIR}/*"

# .env.example is intentionally source-controlled. zip's exclusion patterns
# above only remove .env and .env.* files; explicitly add it back if present.
if [[ -f .env.example ]]; then
  zip -q -u "$OUTPUT_FILE" .env.example
fi

unzip -t "$OUTPUT_FILE" >/dev/null

# Guard against accidentally shipping persistent/sensitive data.
if unzip -Z1 "$OUTPUT_FILE" | grep -Eq '(^|/)(runtime|runtime-projectflow-local|node_modules|\.venv|\.pytest_cache|test-results|playwright-report)(/|$)|(^|/)\.env$|\.(db|sqlite|sqlite3|dump|backup)$'; then
  echo "ERROR: source package contains excluded runtime/generated data" >&2
  unzip -Z1 "$OUTPUT_FILE" | grep -E '(^|/)(runtime|runtime-projectflow-local|node_modules|\.venv|\.pytest_cache|test-results|playwright-report)(/|$)|(^|/)\.env$|\.(db|sqlite|sqlite3|dump|backup)$' >&2 || true
  exit 1
fi

echo "PASS: $OUTPUT_FILE"
ls -lh "$OUTPUT_FILE"
