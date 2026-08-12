import json
import sys
import os
import time
from datetime import datetime, timezone
import psycopg
from mesflow import __version__
from mesflow.core.config import settings
from mesflow.db.repositories.user_repository import UserRepository


def wait_db():
    last=None
    for _ in range(60):
        try:
            with psycopg.connect(settings.database_url,connect_timeout=3) as c:
                c.execute('SELECT 1')
            print('[DB] PostgreSQL ready')
            return
        except Exception as e:
            last=e; time.sleep(1)
    raise RuntimeError(f'PostgreSQL unavailable: {last}')


def seed_admin():
    repo=UserRepository()
    if repo.count()==0:
        if not settings.admin_password or len(settings.admin_password) < 10:
            raise RuntimeError('MESFLOW_ADMIN_PASSWORD must be explicitly set to at least 10 characters for first production bootstrap')
        repo.create(settings.admin_username,'MESFlow Administrator',settings.admin_password,'admin',True)
        print('[SEED] Initial administrator created')
    else:
        print('[SEED] Users already exist; skipped')



def seed_default_users():
    """Optional bootstrap accounts. Disabled by default in production.

    Existing users are never overwritten. Passwords come from environment; no
    production password is hard-coded in source.
    """
    enabled=str(os.environ.get('MESFLOW_SEED_DEFAULT_USERS','0')).lower() in {'1','true','yes','on'}
    if not enabled:
        print('[SEED] Default role users disabled; skipped')
        return
    repo=UserRepository()
    specs=[
      ('manager','MESFlow Manager','manager','MESFLOW_MANAGER_PASSWORD'),
      ('supervisor','MESFlow Supervisor','supervisor','MESFLOW_SUPERVISOR_PASSWORD'),
      ('operator','MESFlow Operator','operator','MESFLOW_OPERATOR_PASSWORD'),
      ('viewer','MESFlow Viewer','viewer','MESFLOW_VIEWER_PASSWORD'),
    ]
    for username,name,role,key in specs:
        if repo.get_by_username(username):
            print(f'[SEED] {username} exists; preserved'); continue
        password=str(os.environ.get(key,'')).strip()
        if len(password)<10:
            raise RuntimeError(f'{key} must be set to at least 10 characters when MESFLOW_SEED_DEFAULT_USERS=1')
        repo.create(username,name,password,role,True)
        print(f'[SEED] Created {username} ({role}); password change required')


def reset_admin():
    user_id = UserRepository().reset_password(
        settings.admin_username,
        settings.admin_password,
        activate=True,
        role='admin',
    )
    print(f'[SEED] Administrator password reset for {settings.admin_username}; id={user_id}')


def verify_schema():
    required=['users','employees','stations','operations','work_sessions','kiosk_events','notifications','rbac_roles','rbac_permissions','rbac_role_permissions','alembic_version']
    with psycopg.connect(settings.database_url) as c:
        rows=c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
        existing={r[0] for r in rows}
        missing=sorted(set(required)-existing)
        if missing: raise RuntimeError(f'Missing tables: {missing}')
        version=c.execute('SELECT version_num FROM alembic_version').fetchone()[0]
    print(json.dumps({'ok':True,'migration_head':version,'tables_checked':required}))


def record_deployment():
    deployment_id=settings.deployment_id or f'manual-{int(time.time())}'
    with psycopg.connect(settings.database_url) as c:
        c.execute("""
          INSERT INTO deployment_history(deployment_id,version,status,finished_at,details)
          VALUES(%s,%s,'healthy',now(),%s::json)
          ON CONFLICT(deployment_id) DO UPDATE SET
            version=excluded.version,status='healthy',finished_at=now(),details=excluded.details
        """,(deployment_id,__version__,json.dumps({'environment':settings.environment})))
    print(f'[DEPLOY] Recorded {deployment_id}')


if __name__=='__main__':
    cmd=sys.argv[1] if len(sys.argv)>1 else ''
    funcs={'wait-db':wait_db,'seed-admin':seed_admin,'seed-default-users':seed_default_users,'reset-admin':reset_admin,'verify-schema':verify_schema,'record-deployment':record_deployment}
    if cmd not in funcs: raise SystemExit('unknown command')
    funcs[cmd]()
