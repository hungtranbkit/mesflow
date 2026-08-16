"""Transactional writers for V68 append-only trace sources."""
from psycopg.types.json import Jsonb
def context(cur,operation_id):
    cur.execute('SELECT o.id operation_id,o.production_order_id,o.part_id FROM operations o WHERE o.id=%s',(operation_id,));return cur.fetchone()
def record_event(cur,*,event_type,category,title,po_id=None,part_id=None,operation_id=None,session_id=None,actor_id=None,actor_name='',description='',quantity_delta=None,correlation_id='',session_trace_id='',source='NATIVE',metadata=None,occurred_at=None):
    ctx=context(cur,operation_id) if operation_id else {}
    cur.execute("""INSERT INTO production_trace_events(event_type,category,occurred_at,actor_id,actor_name,production_order_id,part_id,operation_id,session_id,title,description,quantity_delta,metadata_json,correlation_id,session_trace_id,source)
      VALUES(%s,%s,COALESCE(%s,CURRENT_TIMESTAMP),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
      (event_type,category,occurred_at,actor_id,actor_name,po_id or ctx.get('production_order_id'),part_id or ctx.get('part_id'),operation_id,session_id,title,description,quantity_delta,Jsonb(metadata or {}),correlation_id,session_trace_id,source));return cur.fetchone()
def record_quantities(cur,*,session,good,defect,rework,actor_id=None,actor_name='',source,reason='',correlation_id='',session_trace_id=''):
    ctx=context(cur,session['operation_id']);old={'GOOD':int(session.get('good_qty') or 0),'DEFECT':int(session.get('defect_qty') or 0),'REPAIRABLE':int(session.get('rework_qty') or 0)};new={'GOOD':good,'DEFECT':defect,'REPAIRABLE':rework}
    rows=[]
    for kind in ('GOOD','DEFECT','REPAIRABLE'):
        delta=new[kind]-old[kind]
        if not delta:continue
        cur.execute("""INSERT INTO quantity_movements(movement_type,delta,previous_value,new_value,production_order_id,operation_id,session_id,actor_id,actor_name,source,reason,correlation_id,session_trace_id)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",(kind,delta,old[kind],new[kind],ctx['production_order_id'],session['operation_id'],session['id'],actor_id,actor_name,source,reason,correlation_id,session_trace_id));rows.append(cur.fetchone())
    return rows
