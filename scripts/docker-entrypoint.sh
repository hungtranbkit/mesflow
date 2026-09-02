#!/usr/bin/env sh
set -eu
cd /app
python -m mesflow.cli wait-db
alembic upgrade head
python -m mesflow.cli verify-schema
python -m mesflow.cli seed-rbac
python -m mesflow.cli seed-admin
python -m mesflow.cli seed-default-users
python -m mesflow.cli seed-super-admin
python -m mesflow.cli record-deployment
exec waitress-serve --listen=0.0.0.0:8080 --threads=${MESFLOW_THREADS:-8} --call mesflow.web.app:create_app
