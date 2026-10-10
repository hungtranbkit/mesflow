#!/usr/bin/env python3
"""Run as root on verified TEST only; provision SELECT grants, no business DML.

The existing app credential stays inside its container. Only the new restricted
DSN crosses stdout of the captured subprocess; it is saved root-only, not logged.
"""
import json
import os
from pathlib import Path
import socket
import secrets
import subprocess
import urllib.request

assert os.geteuid() == 0 and socket.gethostname() == 'vps-78ae7aec', 'TEST host required'
with urllib.request.urlopen('http://127.0.0.1:8080/api/system/ready', timeout=10) as response:
    ready = json.load(response)
assert ready['ok'] and ready['server_role'] == 'PRODUCTION_TEST'
target = Path('/opt/mesflow/report-snapshots.env')
existing = target.exists()
scope_file = Path('/opt/mesflow/report-scope.env')
scope_key = scope_file.read_text().strip().split('=', 1)[1] if scope_file.exists() else secrets.token_urlsafe(48)
program = r'''
import os, secrets, json, psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from urllib.parse import quote
dsn = os.environ.get('DATABASE_URL') or os.environ['WORKSHOP_DATABASE_URL']
role = 'mesflow_snapshot_reader'
tables = ['work_sessions','employees','operations','production_orders','parts',
          'stations','work_shifts','work_shift_intervals','session_exception_reviews','kiosk_client_events']
password = secrets.token_urlsafe(48)
with psycopg.connect(dsn) as conn:
    present = conn.execute('SELECT rolsuper,rolcreaterole,rolcreatedb,rolbypassrls FROM pg_roles WHERE rolname=%s', (role,)).fetchone()
    if EXISTING:
        assert present == (False, False, False, False), 'Unexpected reader privileges'
    else:
        assert not present, 'Role exists without its saved credential; inspect before proceeding'
        conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2').format(sql.Identifier(role), sql.Literal(password)))
    conn.execute(sql.SQL('ALTER ROLE {} SET default_transaction_read_only=on').format(sql.Identifier(role)))
    conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(conn.info.dbname), sql.Identifier(role)))
    conn.execute(sql.SQL('GRANT USAGE ON SCHEMA public TO {}').format(sql.Identifier(role)))
    for table in tables:
        conn.execute(sql.SQL('GRANT SELECT ON TABLE public.{} TO {}').format(sql.Identifier(table), sql.Identifier(role)))
    conn.execute(sql.SQL('GRANT SELECT (id,role,active,must_change_password) ON public.users TO {}').format(sql.Identifier(role)))
    assert not conn.execute("SELECT has_table_privilege(%s,'users','SELECT')", (role,)).fetchone()[0]
    assert not conn.execute("SELECT has_column_privilege(%s,'users','password_hash','SELECT')", (role,)).fetchone()[0]
    assert not conn.execute("SELECT has_table_privilege(%s,'work_sessions','UPDATE')", (role,)).fetchone()[0]
parts = conninfo_to_dict(dsn)
value = 'postgresql://' + role + ':' + quote(password, safe='') + '@' + parts.get('host','postgres') + ':' + parts.get('port','5432') + '/' + quote(parts['dbname'], safe='')
print(json.dumps({'database_url':None if EXISTING else value}))
'''
result = subprocess.run(['docker', 'exec', '-i', 'mesflow-app', 'python', '-'],
                        input='EXISTING='+repr(existing)+'\n'+program, text=True, capture_output=True)
if result.returncode:
    raise SystemExit('Reader provisioning failed; no credentials logged. Inspect role state on TEST.')
value = json.loads(result.stdout)['database_url']
if existing:
    lines = [line for line in target.read_text().splitlines() if not line.startswith('REPORT_SCOPE_KEY=')]
else:
    lines = ['DATABASE_URL=' + value]
for path, content in ((target, '\n'.join(lines) + '\nREPORT_SCOPE_KEY=' + scope_key + '\n'),
                      (scope_file, 'REPORT_SCOPE_KEY=' + scope_key + '\n')):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(content)
print('TEST reader SELECT-only grants and private scope check provisioned; env files root:0600')
