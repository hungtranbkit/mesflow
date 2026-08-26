import json
from datetime import datetime, timezone
from mesflow.core.config import settings
from mesflow.db.connection import transaction, fetch_one

ACTION_POLICIES=(
 # Real confirmed bug (2026-08-26, Reliability Validation Round 2 Gate 17):
 # this literal '%' in the ILIKE pattern was never escaped for psycopg's
 # %-style parameter substitution -- every call to preview()/run() crashed
 # with "only '%s','%b','%t' are allowed as placeholders, got '%'" the
 # moment it reached this (the FIRST) policy, meaning log_retention had
 # NEVER successfully executed against a real database: not in the
 # existing test suite (only static/structural checks existed, never a
 # real preview()/run() call), and -- if this ran unmodified in production
 # via the nightly cron -- every single night, silently accumulating
 # instead of the safe, table-growth-bounding job it was meant to be.
 ('security', "(http_status IN (401,403) OR path ILIKE '/api/auth/%%')", 'log_retention_security_days'),
 ('unresolved_error', "outcome IN ('ERROR','FAILED') AND NOT resolved", 'log_retention_unresolved_error_days'),
 ('resolved_error', "outcome IN ('ERROR','FAILED') AND resolved", 'log_retention_resolved_error_days'),
 ('slow', "outcome='SLOW'", 'log_retention_slow_days'),
 ('success', "outcome='SUCCESS'", 'log_retention_success_days'),
)

def _days(attr): return max(1,int(getattr(settings,attr)))

def preview():
    action={}
    for name,condition,attr in ACTION_POLICIES:
        row=fetch_one(f"SELECT COUNT(*) count FROM action_logs WHERE {condition} AND created_at < now()-(%s * interval '1 day')",(_days(attr),))
        action[name]=int((row or {}).get('count',0))
    errors={}
    for name,resolved,attr in [('resolved',True,'log_retention_error_resolved_days'),('unresolved',False,'log_retention_error_unresolved_days')]:
        row=fetch_one("SELECT COUNT(*) count FROM error_traces WHERE resolved=%s AND created_at < now()-(%s * interval '1 day')",(resolved,_days(attr)))
        errors[name]=int((row or {}).get('count',0))
    return {'action_logs':action,'error_traces':errors,'total':sum(action.values())+sum(errors.values())}

def _delete_batches(cur,table,where,params,batch):
    total=0
    while True:
        cur.execute(f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} WHERE {where} ORDER BY id LIMIT %s)",(*params,batch))
        count=cur.rowcount
        total+=count
        if count<batch: break
    return total

def run(dry_run=False):
    before=preview()
    if dry_run:return {'dry_run':True,'preview':before,'action_deleted':0,'error_deleted':0}
    action_deleted=error_deleted=0;details={'action_logs':{},'error_traces':{}}
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO log_retention_runs(dry_run,details_json) VALUES(false,'{}') RETURNING id")
            run_id=cur.fetchone()['id']
            for name,condition,attr in ACTION_POLICIES:
                count=_delete_batches(cur,'action_logs',f"{condition} AND created_at < now()-(%s * interval '1 day')",(_days(attr),),settings.log_retention_batch_size)
                details['action_logs'][name]=count;action_deleted+=count
            for name,resolved,attr in [('resolved',True,'log_retention_error_resolved_days'),('unresolved',False,'log_retention_error_unresolved_days')]:
                count=_delete_batches(cur,'error_traces',"resolved=%s AND created_at < now()-(%s * interval '1 day')",(resolved,_days(attr)),settings.log_retention_batch_size)
                details['error_traces'][name]=count;error_deleted+=count
            cur.execute("UPDATE log_retention_runs SET action_deleted=%s,error_deleted=%s,details_json=%s,finished_at=CURRENT_TIMESTAMP WHERE id=%s",(action_deleted,error_deleted,json.dumps(details),run_id))
    return {'dry_run':False,'run_id':run_id,'action_deleted':action_deleted,'error_deleted':error_deleted,'details':details,'finished_at':datetime.now(timezone.utc).isoformat()}
