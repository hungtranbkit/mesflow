#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Không tìm thấy .env"
  exit 1
fi

USERNAME="${1:-admin}"
PASSWORD="${2:-Admin@123456}"

if grep -q '^MESFLOW_ADMIN_USERNAME=' .env; then
  sed -i "s/^MESFLOW_ADMIN_USERNAME=.*/MESFLOW_ADMIN_USERNAME=${USERNAME}/" .env
else
  printf '\nMESFLOW_ADMIN_USERNAME=%s\n' "$USERNAME" >> .env
fi

if grep -q '^MESFLOW_ADMIN_PASSWORD=' .env; then
  sed -i "s/^MESFLOW_ADMIN_PASSWORD=.*/MESFLOW_ADMIN_PASSWORD=${PASSWORD}/" .env
else
  printf 'MESFLOW_ADMIN_PASSWORD=%s\n' "$PASSWORD" >> .env
fi

docker compose up -d postgres
docker compose run --rm mesflow python -m mesflow.cli reset-admin
docker compose up -d --force-recreate mesflow

echo "Đã reset tài khoản: ${USERNAME}"
echo "Hãy đăng nhập bằng mật khẩu vừa đặt."
