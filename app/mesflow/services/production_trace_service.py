"""V68 normalized read model over native trace, quantity, audit, kiosk and exceptions."""
from __future__ import annotations
import json
from dataclasses import asdict,dataclass
from datetime import datetime
from typing import Any
from mesflow.db.connection import fetch_all,fetch_one
from mesflow.db.repositories.base import NotFoundError

@dataclass(frozen=True)
class TraceEvent:
    id:str;event_type:str;category:str;occurred_at:datetime;actor_id:int|None;actor_name:str
    po_id:int|None;part_id:int|None;operation_id:int|None;session_id:int|None
    title:str;description:str;quantity_delta:int|None;metadata:dict[str,Any];correlation_id:str;session_trace_id:str;source:str

class ProductionTraceService:
    def _scope(self,kind,id):
        if kind=='po':
            row=fetch_one('SELECT id po_id,code po_code,status,planned_quantity,planned_start_at,planned_end_at,created_at,updated_at FROM production_orders WHERE id=%s',(id,))
            if not row:raise NotFoundError('Không tìm thấy Production Order')
            return row,'t.production_order_id=%s',[id]
        if kind=='operation':
            row=fetch_one('''SELECT o.id operation_id,o.code operation_code,o.name operation_name,o.status,o.done_qty good_qty,o.defect_qty,o.rework_qty,
              po.id po_id,po.code po_code,po.planned_quantity,o.created_at,o.updated_at FROM operations o JOIN production_orders po ON po.id=o.production_order_id WHERE o.id=%s''',(id,))
            if not row:raise NotFoundError('Không tìm thấy Operation')
            return row,'t.operation_id=%s',[id]
        row=fetch_one('''SELECT ws.id session_id,ws.status,ws.started_at,ws.ended_at,ws.good_qty,ws.defect_qty,ws.rework_qty,ws.start_request_id,ws.finish_request_id,
          e.id employee_id,e.name employee_name,o.id operation_id,o.code operation_code,p.id part_id,p.code part_code,po.id po_id,po.code po_code
          FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id JOIN parts p ON p.id=o.part_id
          JOIN production_orders po ON po.id=o.production_order_id WHERE ws.id=%s''',(id,))
        if not row:raise NotFoundError('Không tìm thấy Session')
        return row,'t.session_id=%s',[id]
    @staticmethod
    def _event(row,source=None):
        meta=row.get('metadata_json') or {}
        if isinstance(meta,str):
            try:meta=json.loads(meta)
            except Exception:meta={}
        return TraceEvent(str(row['id']),row['event_type'],row['category'],row['occurred_at'],row.get('actor_id'),row.get('actor_name') or '',row.get('production_order_id'),row.get('part_id'),row.get('operation_id'),row.get('session_id'),row['title'],row.get('description') or '',row.get('quantity_delta'),meta,row.get('correlation_id') or '',row.get('session_trace_id') or '',source or row.get('source') or 'NATIVE')
    def trace(self,kind,id,*,limit=100,before=None,categories=None,operation_id=None,employee_id=None,include_audit=False):
        context,scope,params=self._scope(kind,id);where=[scope]
        cursor_time,cursor_id=(before.rsplit('|',1) if before and '|' in before else (before,''))
        if cursor_time:where.append('t.occurred_at<=%s');params.append(cursor_time)
        if categories:where.append('t.category=ANY(%s)');params.append(list(categories))
        if operation_id:where.append('t.operation_id=%s');params.append(operation_id)
        if employee_id:where.append("(t.metadata_json->>'employee_id')::bigint=%s");params.append(employee_id)
        native=fetch_all(f"SELECT t.* FROM production_trace_events t WHERE {' AND '.join(where)} ORDER BY occurred_at DESC,id DESC LIMIT %s",(*params,limit+1))
        events=[self._event(x) for x in native]
        # Exception decisions remain canonical in V67 history; normalize them,
        # never duplicate them into the native event table.
        scope_col={'po':'production_order_id','operation':'operation_id','session':'session_id'}[kind]
        exceptions=fetch_all(f'''SELECT 'exception:'||h.id id,CASE h.action WHEN 'DETECTED' THEN 'EXCEPTION_DETECTED' WHEN 'RESOLVED' THEN 'EXCEPTION_RESOLVED' ELSE 'EXCEPTION_'||h.action END event_type,
          'EXCEPTION' category,h.created_at occurred_at,h.actor_id,h.actor_username actor_name,x.production_order_id,x.part_id,x.operation_id,x.session_id,
          x.title,COALESCE(h.reason,x.message) description,NULL::integer quantity_delta,h.metadata_json,h.correlation_id,'' session_trace_id,'V67_EXCEPTION' source
          FROM exception_history h JOIN exception_records x ON x.id=h.exception_id WHERE x.{scope_col}=%s''',(id,))
        events.extend(self._event(x,'V67_EXCEPTION') for x in exceptions)
        if kind=='session':
            kiosk=fetch_all("""SELECT 'kiosk:'||id id,event_type,'SYSTEM' category,COALESCE(event_time,received_at) occurred_at,NULL::bigint actor_id,kiosk_id actor_name,
              NULL::bigint production_order_id,NULL::bigint part_id,NULL::bigint operation_id,server_session_id session_id,event_type title,reason description,
              NULL::integer quantity_delta,payload_json metadata_json,'' correlation_id,session_trace_id,'KIOSK' source FROM kiosk_client_events WHERE server_session_id=%s""",(id,))
            events.extend(self._event(x,'KIOSK') for x in kiosk)
        if include_audit:
            entity={'po':'production_order','operation':'operation','session':'work_session'}[kind]
            audits=fetch_all("SELECT 'audit:'||id id,action event_type,'CHANGE' category,created_at occurred_at,actor_user_id actor_id,actor_username actor_name,NULL::bigint production_order_id,NULL::bigint part_id,NULL::bigint operation_id,NULL::bigint session_id,action title,'' description,NULL::integer quantity_delta,jsonb_build_object('before',before_json,'after',after_json,'details',details_json) metadata_json,correlation_id,'' session_trace_id,'AUDIT' source FROM audit_logs WHERE entity_type=%s AND entity_id=%s",(entity,str(id)))
            events.extend(self._event(x,'AUDIT') for x in audits)
        # Explicitly labelled inference for pre-V68 rows only.
        native_types={x.event_type for x in events if x.source=='NATIVE'}
        if kind=='session':
            if 'SESSION_STARTED' not in native_types:events.append(TraceEvent(f'legacy:start:{id}','SESSION_STARTED','SESSION',context['started_at'],None,'',context['po_id'],context['part_id'],context['operation_id'],id,'Session bắt đầu','Suy ra từ started_at của dữ liệu trước V68',None,{},context.get('start_request_id') or '','', 'LEGACY_DERIVED'))
            if context.get('ended_at') and 'SESSION_FINISHED' not in native_types:events.append(TraceEvent(f'legacy:finish:{id}','SESSION_FINISHED','SESSION',context['ended_at'],None,'',context['po_id'],context['part_id'],context['operation_id'],id,'Session kết thúc','Suy ra từ ended_at của dữ liệu trước V68',None,{},context.get('finish_request_id') or '','', 'LEGACY_DERIVED'))
        if cursor_time:
            events=[x for x in events if (x.occurred_at.isoformat(),x.id)<(cursor_time,cursor_id)]
        if categories:events=[x for x in events if x.category in categories]
        events.sort(key=lambda x:(x.occurred_at,x.id),reverse=True);has_more=len(events)>limit;events=events[:limit]
        return {'context':context,'events':[asdict(x) for x in events],'next_before':f'{events[-1].occurred_at.isoformat()}|{events[-1].id}' if has_more and events else None,'has_more':has_more,'coverage':{'native_from_version':'68.0.0.1','legacy_complete':False}}
    def quantity_history(self,kind,id,limit=200):
        col={'po':'production_order_id','operation':'operation_id','session':'session_id'}[kind]
        items=fetch_all(f'SELECT * FROM quantity_movements WHERE {col}=%s ORDER BY occurred_at DESC,id DESC LIMIT %s',(id,min(limit,500)))
        return {'items':items,'reconciliation':self.reconcile(kind,id)}
    def reconcile(self,kind,id):
        if kind=='session':
            current=fetch_one('SELECT good_qty,defect_qty,rework_qty FROM work_sessions WHERE id=%s',(id,));where='session_id=%s';params=(id,)
        elif kind=='operation':
            current=fetch_one('SELECT done_qty good_qty,defect_qty,rework_qty FROM operations WHERE id=%s',(id,));where='operation_id=%s';params=(id,)
        else:
            current=fetch_one('SELECT COALESCE(SUM(done_qty),0) good_qty,COALESCE(SUM(defect_qty),0) defect_qty,COALESCE(SUM(rework_qty),0) rework_qty FROM operations WHERE production_order_id=%s',(id,));where='production_order_id=%s';params=(id,)
        sums=fetch_one(f"SELECT COALESCE(SUM(delta) FILTER(WHERE movement_type='GOOD'),0) good_qty,COALESCE(SUM(delta) FILTER(WHERE movement_type='DEFECT'),0) defect_qty,COALESCE(SUM(delta) FILTER(WHERE movement_type='REPAIRABLE'),0) rework_qty FROM quantity_movements WHERE {where}",params)
        # Pre-V68 quantities are outside ledger coverage; mismatch is evidence,
        # not automatically corruption.
        return {'current':current,'ledger':sums,'matches':all(int(current[k] or 0)==int(sums[k] or 0) for k in ('good_qty','defect_qty','rework_qty')),'coverage_complete':False}
