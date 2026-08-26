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
        repo.create(settings.admin_username,'KIMEX Administrator',settings.admin_password,'admin',True)
        print('[SEED] Initial administrator created')
    else:
        print('[SEED] Users already exist; skipped')



def seed_default_users():
    """Optional bootstrap accounts. Disabled by default in production.

    Existing users are never overwritten. Passwords come from environment; no
    production password is hard-coded in source.

    RBAC only defines 5 roles (rbac_roles: admin, manager, supervisor,
    operator, viewer -- see mesflow.web.users.ROLES). The extra personas
    below (QA Inspector, Maintenance, Kiosk User) have no dedicated role or
    permission scope of their own, so per "do not invent new roles unless
    already defined by MESFlow" each is mapped to its closest real role
    rather than given a fabricated one: QA Inspector -> viewer (read-only
    across granted screens, matching an auditor/inspector who reviews but
    never edits); Maintenance and Kiosk User -> operator (operator's own
    permission set is literally "Thao tac san xuat va kiosk" -- production
    ops and kiosk -- the closest floor-level fit; equipment.edit is
    manager/admin-only in the real RBAC, so a dedicated low-privilege
    maintenance-edit role does not exist today). The original 4 entries
    (manager/supervisor/operator/viewer, one per role) are kept verbatim
    for backward compatibility with any environment that already ran this
    with the old spec list; the rest are additive.
    """
    enabled=str(os.environ.get('MESFLOW_SEED_DEFAULT_USERS','0')).lower() in {'1','true','yes','on'}
    if not enabled:
        print('[SEED] Default role users disabled; skipped')
        return
    repo=UserRepository()
    specs=[
      ('manager','KIMEX Manager','manager','MESFLOW_MANAGER_PASSWORD'),
      ('supervisor','KIMEX Supervisor','supervisor','MESFLOW_SUPERVISOR_PASSWORD'),
      ('operator','KIMEX Operator','operator','MESFLOW_OPERATOR_PASSWORD'),
      ('viewer','KIMEX Viewer','viewer','MESFLOW_VIEWER_PASSWORD'),
      ('operator2','KIMEX Operator - Kiosk ca 2','operator','MESFLOW_OPERATOR2_PASSWORD'),
      ('qa','KIMEX QA Inspector','viewer','MESFLOW_QA_PASSWORD'),
      ('maintenance','KIMEX Maintenance','operator','MESFLOW_MAINTENANCE_PASSWORD'),
      ('kiosk01','KIMEX Kiosk User 01','operator','MESFLOW_KIOSK01_PASSWORD'),
      ('kiosk02','KIMEX Kiosk User 02','operator','MESFLOW_KIOSK02_PASSWORD'),
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


def reset_password():
    """Emergency, server-side password reset for an EXISTING user, invoked
    as `python -m mesflow.cli reset-password <username>` (same
    `docker compose run --rm mesflow ...` pattern scripts/reset-admin-password.sh
    already uses for reset-admin). For "I'm locked out and cannot log in at
    all" -- the in-app path at Users & Roles -> reset password
    (mesflow.web.users.reset_user_password, audit action USER_PASSWORD_RESET)
    already covers the case where an admin is still logged in and resetting
    someone ELSE's password; this is the fallback when nobody can log in.

    Deliberately does NOT reuse UserRepository.reset_password() (the
    upsert reset_admin() above calls): that method creates the user if
    missing and unconditionally forces role='admin', active=True on
    conflict -- correct for recovering the one fixed admin account, wrong
    for any other username (it would silently promote whoever you name to
    admin). This uses UserRepository.set_password() instead, which only
    ever touches password_hash/must_change_password/updated_at -- role,
    active, display_name and every other column are left exactly as they
    were. Refuses to run against a username that doesn't already exist
    (no upsert) so a typo can't silently create a stray account.

    Records audit_logs action ADMIN_PASSWORD_RESET (distinct from
    USER_PASSWORD_RESET above -- this one means "done from a root/server
    shell, outside any web session"). Password is read via getpass (never
    echoed, never logged, never passed as a CLI argument that would land in
    shell history or `docker compose run` process listings) and never
    printed. No destructive DB changes -- one UPDATE on one existing row.
    """
    if len(sys.argv) < 3 or not sys.argv[2].strip():
        raise SystemExit('usage: python -m mesflow.cli reset-password <username>')
    username = sys.argv[2].strip()
    repo = UserRepository()
    user = repo.get_by_username(username)
    if not user:
        raise SystemExit(
            f"ERROR: no user '{username}' exists -- this command never creates one. "
            f"Verify the exact username first (Users & Roles page, or "
            f"'SELECT username, role FROM users;' via psql) before retrying."
        )
    import getpass
    password = getpass.getpass(f"New password for '{username}' (>=8 chars, letters+digits, not echoed): ")
    # Same policy as mesflow.web.users._password_error -- keep both in sync
    # if the policy ever changes.
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise SystemExit('ERROR: password must be at least 8 characters and contain both a letter and a digit')
    confirm = getpass.getpass('Confirm new password: ')
    if password != confirm:
        raise SystemExit('ERROR: passwords do not match; nothing was changed')
    repo.set_password(user['id'], password, must_change=False)
    password = confirm = None  # drop references promptly; never logged/printed
    from mesflow.db.repositories.analytics import AuditRepository
    AuditRepository().log(
        'cli:reset-password', 'ADMIN_PASSWORD_RESET', 'user', str(user['id']),
        {'target_username': username, 'source': 'server_cli'},
    )
    print(f"[CLI] Password reset for '{username}' (id={user['id']}, role='{user['role']}' unchanged). "
          f"Audit event ADMIN_PASSWORD_RESET recorded in audit_logs.")


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


def run_predictive():
    """Phase 3 scheduled job (section 48): sample metrics, clean up old
    samples past retention, recompute forecast/anomaly/recurrence, and
    report its own status through Phase 1's Jobs card (scheduled_job_health)
    so a silently-dead predictive job shows up as MISSED, not as a
    falsely-green Health Center (section 53).

    Monitoring ownership cutover (reports/SYSTEM_LOG_AUDIT_SEPARATION.md):
    Deploy Agent is now authoritative for infra monitoring/diagnostics. This
    legacy job is a no-op unless MESFLOW_LEGACY_HEALTH_WRITER_ENABLED=1 --
    it no longer writes health_metric_samples, predictive_insights, or
    scheduled_job_health. Not removed: still callable to prove the
    mechanism still works, and to allow a deliberate rollback."""
    if not settings.legacy_health_writer_enabled:
        print('[PREDICTIVE] legacy health writer disabled; skipped (Deploy Agent is authoritative for infra monitoring)')
        return
    t0=time.time();job='predictive_metrics_collection'
    def report(status,error=''):
        with psycopg.connect(settings.database_url) as c:
            c.execute("""UPDATE scheduled_job_health SET last_started_at=%s,last_finished_at=CURRENT_TIMESTAMP,
                last_status=%s,duration_ms=%s,last_error=%s,
                consecutive_failures=CASE WHEN %s='SUCCESS' THEN 0 ELSE consecutive_failures+1 END,
                next_expected_at=CURRENT_TIMESTAMP+(expected_interval_seconds||' seconds')::interval
                WHERE job_name=%s""",
                (started_at,status,int((time.time()-t0)*1000),error,status,job))
    started_at=datetime.now(timezone.utc)
    try:
        from mesflow.services.metrics_service import MetricsCollector
        from mesflow.services.predictive_service import PredictiveService
        written=MetricsCollector().collect()
        MetricsCollector().cleanup()
        insights=PredictiveService().sync(correlation_id=f'cli-run-predictive-{int(time.time())}')
        report('SUCCESS')
        print(f'[PREDICTIVE] collected {len(written)} samples, {len(insights)} active insight(s)')
    except Exception as e:
        report('FAILED',f'{type(e).__name__}: {e}')
        raise


def reconcile_exceptions():
    """Exception detection/auto-ignore used to run ONLY as
    a side effect of GET /api/exceptions (still true today, kept for
    interactive-UX freshness -- see mesflow.web.exceptions -- and heavily
    exercised by tests/integration/test_v67_exception_center.py, so NOT
    removed). This is the missing REAL, UI-independent path: run via cron
    (scripts/install-reconcile-cron.sh) so an exception is detected/
    auto-resolved even when nobody has the Exception Center open -- which
    matters now that shift auto-close creates exactly that case (a
    session closes at 3am; nobody sees the Center until the next shift)."""
    from mesflow.core.scheduled_job import scheduled_job_run
    from mesflow.services.exception_service import ExceptionDetectionService
    correlation_id=f'cli-reconcile-exceptions-{int(time.time())}'
    with scheduled_job_run('exception_reconciliation'):
        created=ExceptionDetectionService().reconcile(correlation_id)
    print(f'[RECONCILE] exception_reconciliation: {len(created)} new exception(s) detected')


def reconcile_shift_sessions():
    """Finds every OPEN work_session past its own
    shift's end boundary (grace period from MESFLOW_SHIFT_AUTO_CLOSE_GRACE_MINUTES)
    and auto-closes it -- see services/shift_session_service.py for the
    detection+dispatch logic and execution.py's auto_close_for_shift_end()
    for the dedicated (never finish()-reusing) close lifecycle.

    Respects MESFLOW_SHIFT_AUTO_CLOSE_ENABLED/_DRY_RUN (rollout
    safety) unless --dry-run/--live is passed explicitly on the command
    line, which always wins over the environment default -- lets a human
    inspect a real dry-run from cron output without needing to touch env
    vars, and lets a human force a real run once satisfied."""
    from mesflow.core.scheduled_job import scheduled_job_run
    from mesflow.services.shift_session_service import ShiftSessionReconciliationService
    explicit_dry_run=None
    if '--dry-run' in sys.argv: explicit_dry_run=True
    elif '--live' in sys.argv: explicit_dry_run=False
    correlation_id=f'cli-reconcile-shift-sessions-{int(time.time())}'
    with scheduled_job_run('shift_session_reconciliation'):
        results=ShiftSessionReconciliationService().reconcile(dry_run=explicit_dry_run,correlation_id=correlation_id)
    by_action={}
    for item in results: by_action[item['action']]=by_action.get(item['action'],0)+1
    print(f'[RECONCILE] shift_session_reconciliation: {len(results)} candidate(s) -- {by_action}')
    for item in results:
        if item['action']=='FAILED':
            print(f"  FAILED session #{item['session_id']}: {item.get('error')}")


def audit_sessions():
    """Read-only production data audit -- `mesflow
    audit-sessions [--json]`. Never modifies anything (see
    services/session_audit_service.py's own docstring). Meant to be run
    before/after a rollout and periodically to catch data
    drift early: open sessions, ones past their shift end or over 12h,
    ones still open from a previous calendar day, employee time-overlap
    conflicts, impossible (ended-before-started) durations, and offline
    events whose device clock drifted materially from the server's."""
    from mesflow.services.session_audit_service import audit
    result=audit()
    if '--json' in sys.argv:
        print(json.dumps(result,indent=2,default=str,ensure_ascii=False))
        return
    for category,items in result.items():
        print(f'{category}: {len(items)}')
    total_flagged=sum(len(v) for k,v in result.items() if k!='OPEN')
    print(f'\n{len(result["OPEN"])} OPEN session(s), {total_flagged} flagged row(s) across the other categories '
          f'(a session can appear in more than one -- e.g. both OPEN_OVER_12H and PAST_SHIFT_END).')
    print('Use --json for the full per-item detail.')


def audit_integrity():
    """Read-only database invariant audit -- `mesflow
    audit-integrity [--json]`. Never modifies anything (see
    services/integrity_audit_service.py's own docstring). Complements
    audit-sessions (which flags staleness) with checks that flag outright
    corruption: status/ended_at mismatches, negative quantities, orphaned
    FKs, duplicate close/quantity/offline events, an auto-close that
    changed quantity, an Operation marked COMPLETED with a session still
    OPEN on it, and a DISABLED/PENDING kiosk with a live heartbeat. Meant
    to be run after every chaos/load/soak test phase."""
    from mesflow.services.integrity_audit_service import audit_integrity as run
    result=run()
    if '--json' in sys.argv:
        print(json.dumps(result,indent=2,default=str,ensure_ascii=False))
        return
    total=sum(len(v) for v in result.values())
    for category,items in result.items():
        print(f'{category}: {len(items)}')
    print(f'\nINTEGRITY VIOLATIONS: {total}')
    print('Use --json for the full per-item detail.')


if __name__=='__main__':
    cmd=sys.argv[1] if len(sys.argv)>1 else ''
    funcs={'wait-db':wait_db,'seed-admin':seed_admin,'seed-default-users':seed_default_users,'reset-admin':reset_admin,'reset-password':reset_password,'verify-schema':verify_schema,'record-deployment':record_deployment,'run-predictive':run_predictive,'reconcile-exceptions':reconcile_exceptions,'reconcile-shift-sessions':reconcile_shift_sessions,'audit-sessions':audit_sessions,'audit-integrity':audit_integrity}
    if cmd not in funcs: raise SystemExit('unknown command')
    funcs[cmd]()
