from __future__ import annotations
import json
from datetime import date, datetime, timezone, timedelta
from typing import Any
from mesflow.db.connection import transaction, fetch_all, fetch_one
from .base import NotFoundError, ConflictError
from mesflow.core.working_calendar import get_working_calendar, get_work_shift, shift_bounds, resolve_shift_context, working_seconds_between,all_shift_working_seconds_between
from mesflow.core.time_policy import coerce_utc,utc_now,business_date
from mesflow.db.repositories.scheduling import priority_for_operation,priority_sort_key
from mesflow.core.config import settings

class AuditRepository:
    def log(self,actor_username:str,action:str,entity_type:str='',entity_id:str='',details:dict[str,Any]|None=None):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,details_json)
                VALUES(%s,%s,%s,%s,%s) RETURNING *""",(actor_username or '',action,entity_type,entity_id,json.dumps(details or {},ensure_ascii=False)))
                return cur.fetchone()
    def list(self,limit:int=200,action:str='',entity_type:str=''):
        where=[]; params=[]
        if action: where.append('action=%s'); params.append(action)
        if entity_type: where.append('entity_type=%s'); params.append(entity_type)
        clause=(' WHERE '+' AND '.join(where)) if where else ''
        params.append(min(max(limit,1),1000))
        return fetch_all(f'SELECT * FROM audit_logs{clause} ORDER BY id DESC LIMIT %s',params)

class DashboardRepository:
    def summary(self):
        return fetch_one("""SELECT
          (SELECT COUNT(*) FROM production_orders) po_total,
          (SELECT COUNT(*) FROM production_orders WHERE status IN ('IN_PROGRESS','ACTIVE')) po_active,
          (SELECT COUNT(*) FROM operations) operation_total,
          (SELECT COUNT(*) FROM operations WHERE status='COMPLETED') operation_completed,
          (SELECT COALESCE(SUM(done_qty),0) FROM operations) total_good_qty,
          (SELECT COALESCE(SUM(defect_qty),0) FROM operations) total_defect_qty,
          (SELECT COALESCE(SUM(rework_qty),0) FROM operations) total_rework_qty,
          (SELECT COUNT(*) FROM work_sessions WHERE status='OPEN') active_sessions,
          (SELECT COUNT(*) FROM employees WHERE active=true) active_employees,
          (SELECT COUNT(*) FROM kiosk_status WHERE last_heartbeat_at >= CURRENT_TIMESTAMP-INTERVAL '2 minutes') online_kiosks,
          (SELECT COUNT(*) FROM kiosk_events WHERE status='OPEN' AND severity IN ('ERROR','CRITICAL')) open_critical_events,
          (SELECT COUNT(*) FROM notifications WHERE status='UNREAD') unread_notifications""")
    def po_progress(self,limit:int=100):
        # PO output must not sum sequential operations. For each Part we use
        # graph terminal operations; legacy Parts without dependency edges use
        # the final sort-order operation. Because the schema has one PO-level
        # plan (no Part-level quantity), multiple terminal Parts are weighted
        # equally and expressed as equivalent finished PO units.
        return fetch_all("""WITH ranked_operations AS (
          SELECT o.*,
            ROW_NUMBER() OVER (PARTITION BY o.part_id ORDER BY o.sort_order DESC,o.id DESC) reverse_rank,
            COUNT(*) FILTER (WHERE o.predecessor_operation_id IS NOT NULL) OVER (PARTITION BY o.part_id) edge_count,
            NOT EXISTS(SELECT 1 FROM operations successor WHERE successor.predecessor_operation_id=o.id) graph_terminal
          FROM operations o
        ), terminal_operations AS (
          SELECT * FROM ranked_operations
          WHERE (edge_count>0 AND graph_terminal) OR (edge_count=0 AND reverse_rank=1)
        ), operation_rollup AS (
          SELECT production_order_id,COUNT(*) operation_count,
            COUNT(*) FILTER (WHERE status='COMPLETED') completed_count
          FROM operations GROUP BY production_order_id
        ), part_rollup AS (
          SELECT production_order_id,COUNT(*) part_count FROM parts GROUP BY production_order_id
        ), terminal_rollup AS (
          SELECT production_order_id,COUNT(*) terminal_operation_count,
            ROUND(COALESCE(SUM(done_qty),0)::numeric/NULLIF(COUNT(*),0))::bigint good_quantity,
            COALESCE(SUM(defect_qty),0)::bigint defect_quantity,
            COALESCE(SUM(rework_qty),0)::bigint repairable_quantity
          FROM terminal_operations GROUP BY production_order_id
        ), repair_rollup AS (
          SELECT production_order_id,
            COALESCE(SUM(rework_qty),0)::bigint repair_pending_quantity,
            COALESCE(SUM(rework_qty*repair_cycle_time_seconds_per_unit),0)::bigint estimated_repair_work_seconds,
            COUNT(*) FILTER (WHERE rework_qty>0) repair_operation_count,
            COUNT(*) FILTER (WHERE rework_qty>0 AND repair_cycle_time_seconds_per_unit<=0) repair_unconfigured_operation_count
          FROM operations GROUP BY production_order_id
        ) SELECT po.id,po.id po_id,po.code,po.code po_code,po.product,po.status,
          po.planned_quantity,po.due_date,po.planned_start_at,po.planned_end_at,
          COALESCE(pr.part_count,0) part_count,COALESCE(op.operation_count,0) operation_count,
          COALESCE(op.completed_count,0) completed_count,COALESCE(tr.terminal_operation_count,0) terminal_operation_count,
          COALESCE(tr.good_quantity,0) done_qty,COALESCE(tr.good_quantity,0) good_quantity,
          COALESCE(tr.defect_quantity,0) defect_qty,COALESCE(tr.defect_quantity,0) defect_quantity,
          COALESCE(tr.repairable_quantity,0) rework_qty,COALESCE(tr.repairable_quantity,0) repairable_quantity,
          COALESCE(rr.repair_pending_quantity,0) repair_pending_quantity,
          COALESCE(rr.estimated_repair_work_seconds,0) estimated_repair_work_seconds,
          COALESCE(rr.repair_operation_count,0) repair_operation_count,
          COALESCE(rr.repair_unconfigured_operation_count,0) repair_unconfigured_operation_count,
          GREATEST(COALESCE(tr.defect_quantity,0)-COALESCE(tr.repairable_quantity,0),0) scrap_quantity,
          GREATEST(COALESCE(po.planned_quantity,0)-COALESCE(tr.good_quantity,0),0) remaining_quantity,
          CASE WHEN COALESCE(po.planned_quantity,0)>0 THEN
            ROUND(LEAST(COALESCE(tr.good_quantity,0)::numeric/po.planned_quantity*100,100),1)
          ELSE 0 END progress_percent,
          'TERMINAL_OPERATION_EQUAL_PART_WEIGHT' progress_basis
        FROM production_orders po
        LEFT JOIN part_rollup pr ON pr.production_order_id=po.id
        LEFT JOIN operation_rollup op ON op.production_order_id=po.id
        LEFT JOIN terminal_rollup tr ON tr.production_order_id=po.id
        LEFT JOIN repair_rollup rr ON rr.production_order_id=po.id
        ORDER BY po.updated_at DESC LIMIT %s""",(min(max(limit,1),500),))
    def operation_overview(self,limit:int=1000):
        rows=fetch_all("""SELECT po.id po_id,po.code po_code,po.product,po.status po_status,po.planned_quantity,po.due_date,
          p.id part_id,p.code part_code,p.name part_name,o.id operation_id,o.code operation_code,o.name operation_name,
          o.status operation_status,COALESCE(o.done_qty,0) done_qty,COALESCE(o.defect_qty,0) defect_qty,COALESCE(o.rework_qty,0) rework_qty,
          COALESCE(o.rework_qty,0) repair_pending_quantity,COALESCE(o.repair_cycle_time_seconds_per_unit,0) repair_cycle_time_seconds_per_unit,
          (COALESCE(o.rework_qty,0)*COALESCE(o.repair_cycle_time_seconds_per_unit,0))::bigint estimated_repair_work_seconds,
          COUNT(ws.id) FILTER (WHERE ws.status='OPEN') open_session_count,
          STRING_AGG(DISTINCT e.name,', ' ORDER BY e.name) FILTER (WHERE ws.status='OPEN') active_workers,
          MAX(COALESCE(ws.ended_at,ws.updated_at,ws.started_at)) last_activity_at
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        JOIN parts p ON p.id=o.part_id LEFT JOIN work_sessions ws ON ws.operation_id=o.id
        LEFT JOIN employees e ON e.id=ws.employee_id
        GROUP BY po.id,p.id,o.id
        ORDER BY CASE WHEN COUNT(ws.id) FILTER (WHERE ws.status='OPEN')>0 THEN 0
          WHEN o.status='IN_PROGRESS' THEN 1 WHEN o.status='PAUSED' THEN 2 WHEN o.status='COMPLETED' THEN 4 ELSE 3 END,
          po.updated_at DESC,p.sort_order,o.sort_order,o.id LIMIT %s""",(min(max(limit,1),5000),))
        for row in rows:
            plan=max(int(row.get('planned_quantity') or 0),0); done=max(int(row.get('done_qty') or 0),0)
            row['progress_percent']=round(min(done/plan*100,100),1) if plan else 0.0
            if int(row.get('open_session_count') or 0)>0: row['health']='RUNNING'
            elif str(row.get('operation_status') or '').upper()=='COMPLETED': row['health']='COMPLETED'
            elif str(row.get('operation_status') or '').upper()=='PAUSED': row['health']='PAUSED'
            elif done>0: row['health']='IN_PROGRESS'
            else: row['health']='NOT_STARTED'
        return rows

    def overview(self,limit:int=1000):
        return {'summary':self.summary(),'production_orders':self.po_progress(min(limit,500)),
          'operations':self.operation_overview(limit),'active_sessions':self.active_sessions(200)}

    def active_sessions(self,limit:int=100):
        rows=fetch_all("""SELECT ws.id,ws.started_at,ws.station_id,ws.device_uuid,
          e.employee_no,e.name employee_name,o.code operation_code,o.name operation_name,o.standard_seconds_per_unit,
          o.done_qty live_good_qty,COALESCE(po.planned_quantity,0) plan_qty,(COALESCE(po.planned_quantity,0)*o.standard_seconds_per_unit) planned_seconds,po.code po_code
        FROM work_sessions ws
        JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id
        JOIN production_orders po ON po.id=o.production_order_id
        WHERE ws.status='OPEN' ORDER BY ws.started_at LIMIT %s""",(min(max(limit,1),500),))
        cfg=get_working_calendar(); now=utc_now()
        for row in rows:
            elapsed=all_shift_working_seconds_between(row['started_at'],now)
            row['elapsed_seconds']=elapsed
            cycle=float(row.get('standard_seconds_per_unit') or 0)
            row['expected_qty']=int(elapsed//cycle) if cycle>0 else 0
        return rows
    def control_tower(self,limit:int=100):
        summary=dict(self.summary() or {})
        sessions=self.active_sessions(limit)
        cfg=get_working_calendar()
        now=utc_now()
        today=business_date(timezone_name=settings.timezone_name)

        performance=dict(fetch_one("""WITH active_po AS (
          SELECT po.id,COALESCE(po.planned_quantity,0) planned_quantity,COUNT(o.id) operation_count,
            COALESCE(SUM(o.done_qty),0) done_qty,COALESCE(SUM(o.defect_qty),0) defect_qty
          FROM production_orders po LEFT JOIN operations o ON o.production_order_id=po.id
          WHERE po.status IN ('IN_PROGRESS','ACTIVE','PAUSED') GROUP BY po.id
        ), completed_due AS (
          SELECT COUNT(*) FILTER (WHERE (updated_at AT TIME ZONE %s)::date<=due_date) on_time_count,COUNT(*) total_count
          FROM production_orders
          WHERE status='COMPLETED' AND due_date IS NOT NULL AND updated_at>=%s::date-INTERVAL '30 days'
        ) SELECT
          (SELECT COALESCE(SUM(good_qty),0) FROM work_sessions WHERE (COALESCE(ended_at,updated_at) AT TIME ZONE %s)::date=%s) today_good_qty,
          (SELECT COALESCE(SUM(defect_qty),0) FROM work_sessions WHERE (COALESCE(ended_at,updated_at) AT TIME ZONE %s)::date=%s) today_defect_qty,
          (SELECT COUNT(*) FROM work_sessions WHERE (started_at AT TIME ZONE %s)::date=%s) sessions_started_today,
          (SELECT COUNT(*) FROM work_sessions WHERE status<>'OPEN' AND (ended_at AT TIME ZONE %s)::date=%s) sessions_completed_today,
          COALESCE((SELECT SUM(planned_quantity*operation_count) FROM active_po),0) active_plan_qty,
          COALESCE((SELECT SUM(done_qty) FROM active_po),0) active_done_qty,
          COALESCE((SELECT SUM(defect_qty) FROM active_po),0) active_defect_qty,
          COALESCE((SELECT ROUND(on_time_count::numeric/NULLIF(total_count,0)*100,1) FROM completed_due),0) on_time_rate_percent""",
          (settings.timezone_name,today,settings.timezone_name,today,settings.timezone_name,today,settings.timezone_name,today,settings.timezone_name,today)) or {})
        today_total=int(performance.get('today_good_qty') or 0)+int(performance.get('today_defect_qty') or 0)
        performance['today_yield_percent']=round(int(performance.get('today_good_qty') or 0)/today_total*100,1) if today_total else 100.0
        active_plan=float(performance.get('active_plan_qty') or 0)
        performance['active_progress_percent']=round(float(performance.get('active_done_qty') or 0)/active_plan*100,1) if active_plan else 0.0

        daily_output=fetch_all("""SELECT d::date work_date,COALESCE(SUM(ws.good_qty),0) good_qty,COALESCE(SUM(ws.defect_qty),0) defect_qty,COALESCE(SUM(ws.rework_qty),0) rework_qty,
          COUNT(ws.id) session_count
        FROM generate_series(%s::date-6,%s::date,INTERVAL '1 day') d
        LEFT JOIN work_sessions ws ON (COALESCE(ws.ended_at,ws.updated_at) AT TIME ZONE %s)::date=d::date
        GROUP BY d ORDER BY d""",(today,today,settings.timezone_name))

        po_health=fetch_all("""WITH op_rollup AS (
          SELECT o.production_order_id,COUNT(*) operation_count,
            COUNT(*) FILTER (WHERE o.status='COMPLETED') completed_operation_count,
            COALESCE(SUM(o.done_qty),0) done_qty,COALESCE(SUM(o.defect_qty),0) defect_qty,COALESCE(SUM(o.rework_qty),0) rework_qty,
            COUNT(*) FILTER (WHERE COALESCE(o.standard_seconds_per_unit,0)<=0) unconfigured_cycle_count,
            COUNT(*) FILTER (WHERE o.predecessor_operation_id IS NOT NULL AND COALESCE(pred.status,'')<>'COMPLETED') blocked_operation_count
          FROM operations o LEFT JOIN operations pred ON pred.id=o.predecessor_operation_id
          GROUP BY o.production_order_id
        ), active_rollup AS (
          SELECT o.production_order_id,COUNT(ws.id) active_sessions,
            STRING_AGG(DISTINCT e.name,', ' ORDER BY e.name) workers
          FROM work_sessions ws JOIN operations o ON o.id=ws.operation_id JOIN employees e ON e.id=ws.employee_id
          WHERE ws.status='OPEN' GROUP BY o.production_order_id
        ) SELECT po.id,po.code,po.product,po.status,po.priority,po.due_date,po.planned_start_at,po.planned_end_at,
          po.planned_quantity,COALESCE(r.operation_count,0) operation_count,
          COALESCE(r.completed_operation_count,0) completed_operation_count,COALESCE(r.done_qty,0) done_qty,
          COALESCE(r.defect_qty,0) defect_qty,COALESCE(r.unconfigured_cycle_count,0) unconfigured_cycle_count,
          COALESCE(r.blocked_operation_count,0) blocked_operation_count,COALESCE(a.active_sessions,0) active_sessions,
          COALESCE(a.workers,'') workers
        FROM production_orders po LEFT JOIN op_rollup r ON r.production_order_id=po.id
        LEFT JOIN active_rollup a ON a.production_order_id=po.id
        WHERE po.status IN ('IN_PROGRESS','ACTIVE','PAUSED')
        ORDER BY CASE po.priority WHEN 'URGENT' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 ELSE 4 END,
          po.due_date NULLS LAST,po.updated_at DESC LIMIT %s""",(min(max(limit,1),500),))
        for row in po_health:
            operation_count=int(row.get('operation_count') or 0)
            target=int(row.get('planned_quantity') or 0)*operation_count
            done=int(row.get('done_qty') or 0)
            defect=int(row.get('defect_qty') or 0)
            row['progress_percent']=round(done/target*100,1) if target else 0.0
            row['yield_percent']=round(done/(done+defect)*100,1) if done+defect else 100.0
            health='ON_TRACK'; label='Đúng kế hoạch'; reason='Chưa phát hiện rủi ro nổi bật'
            due=row.get('due_date')
            planned_end=row.get('planned_end_at')
            if due and due<today and row['progress_percent']<100:
                health='CRITICAL'; label='Quá hạn'; reason=f"Quá hạn {(today-due).days} ngày"
            elif planned_end and planned_end<now and row['progress_percent']<100:
                health='CRITICAL'; label='Trễ kế hoạch'; reason='Đã qua thời điểm kết thúc dự kiến'
            elif str(row.get('status'))=='PAUSED':
                health='WARNING'; label='Tạm dừng'; reason='PO đang tạm dừng'
            elif str(row.get('status')) in ('IN_PROGRESS','ACTIVE') and int(row.get('active_sessions') or 0)==0:
                health='WARNING'; label='Không có người làm'; reason='PO đang chạy nhưng không có session mở'
            elif due and 0 <= (due-today).days <= 1 and row['progress_percent']<80:
                health='WARNING'; label='Nguy cơ trễ'; reason='Sắp đến hạn nhưng tiến độ dưới 80%'
            elif int(row.get('unconfigured_cycle_count') or 0)>0:
                health='CONFIG'; label='Thiếu định mức'; reason=f"{row['unconfigured_cycle_count']} Operation chưa có thời gian chuẩn"
            elif str(row.get('status')) in ('DRAFT','PLANNED'):
                health='PLANNING'; label='Đang chuẩn bị'; reason='PO chưa phát hành sản xuất'
            row['health']=health; row['health_label']=label; row['health_reason']=reason

        po_tree=fetch_all("""SELECT po.id po_id,po.code po_code,po.product,po.status po_status,po.priority,po.due_date,
          p.id part_id,p.code part_code,p.name part_name,p.sort_order part_sort,
          o.id operation_id,o.code operation_code,o.name operation_name,o.status operation_status,
          COALESCE(po.planned_quantity,0) plan_qty,o.done_qty,o.defect_qty,o.sort_order operation_sort,o.standard_seconds_per_unit,
          (COALESCE(po.planned_quantity,0)*o.standard_seconds_per_unit) planned_seconds,
          COUNT(ws.id) FILTER (WHERE ws.status='OPEN') active_session_count,
          STRING_AGG(DISTINCT e.name, ', ') FILTER (WHERE ws.status='OPEN') active_employees,
          MIN(ws.started_at) FILTER (WHERE ws.status='OPEN') active_since
        FROM production_orders po
        LEFT JOIN parts p ON p.production_order_id=po.id
        LEFT JOIN operations o ON o.part_id=p.id
        LEFT JOIN work_sessions ws ON ws.operation_id=o.id
        LEFT JOIN employees e ON e.id=ws.employee_id
        WHERE po.status IN ('IN_PROGRESS','ACTIVE','PAUSED')
        GROUP BY po.id,p.id,o.id
        ORDER BY po.due_date NULLS LAST,po.updated_at DESC,p.sort_order,p.id,o.sort_order,o.id""")
        for row in po_tree:
            if row.get('active_since'):
                row['active_elapsed_seconds']=working_seconds_between(row['active_since'],now,cfg)

        alerts=fetch_all("""WITH active AS (
          SELECT ws.id session_id,ws.started_at,ws.device_uuid,e.name employee_name,
            po.id po_id,po.code po_code,p.id part_id,p.code part_code,o.id operation_id,o.code operation_code,o.name operation_name,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP-ws.started_at))::bigint elapsed_seconds,
            ks.last_heartbeat_at
          FROM work_sessions ws
          JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id
          JOIN parts p ON p.id=o.part_id JOIN production_orders po ON po.id=o.production_order_id
          LEFT JOIN kiosk_status ks ON ks.device_uuid=ws.device_uuid WHERE ws.status='OPEN'
        ) SELECT * FROM (
          SELECT 'CRITICAL' severity,'KIOSK_OFFLINE' alert_type,po_id,part_id,operation_id,session_id,
            po_code||' · '||operation_code title,'Kiosk mất heartbeat khi session đang chạy: '||employee_name message,started_at occurred_at
          FROM active WHERE last_heartbeat_at IS NULL OR last_heartbeat_at<CURRENT_TIMESTAMP-INTERVAL '2 minutes'
          UNION ALL
          SELECT CASE WHEN po.due_date<CURRENT_DATE THEN 'CRITICAL' ELSE 'WARNING' END,'PO_RISK',po.id,NULL,NULL,NULL,
            po.code||' · '||po.product,
            CASE WHEN po.due_date<CURRENT_DATE THEN 'PO đã quá hạn' ELSE 'PO sắp đến hạn nhưng tiến độ dưới 80%' END,po.updated_at
          FROM production_orders po LEFT JOIN operations o ON o.production_order_id=po.id
          WHERE po.status IN ('IN_PROGRESS','ACTIVE','PAUSED') AND po.due_date IS NOT NULL GROUP BY po.id
          HAVING po.due_date<CURRENT_DATE OR (po.due_date<=CURRENT_DATE+1 AND COALESCE(SUM(o.done_qty),0)<COALESCE(NULLIF(COALESCE(po.planned_quantity,0)*COUNT(DISTINCT o.id),0),1)*0.8)
          UNION ALL
          SELECT CASE WHEN SUM(o.defect_qty)::numeric/NULLIF(SUM(o.done_qty+o.defect_qty),0)>=0.1 THEN 'CRITICAL' ELSE 'WARNING' END,
            'HIGH_DEFECT',po.id,NULL,NULL,NULL,po.code||' · '||po.product,
            'Tỷ lệ lỗi hiện tại '||ROUND(SUM(o.defect_qty)::numeric/NULLIF(SUM(o.done_qty+o.defect_qty),0)*100,1)||'%',MAX(o.updated_at)
          FROM production_orders po JOIN operations o ON o.production_order_id=po.id
          GROUP BY po.id HAVING SUM(o.done_qty+o.defect_qty)>0 AND SUM(o.defect_qty)::numeric/NULLIF(SUM(o.done_qty+o.defect_qty),0)>=0.05
        ) a ORDER BY CASE severity WHEN 'CRITICAL' THEN 1 ELSE 2 END,occurred_at DESC LIMIT 100""")
        for session_row in sessions:
            elapsed=int(session_row.get('elapsed_seconds') or 0)
            if elapsed>=7200:
                alerts.append({'severity':'CRITICAL' if elapsed>=14400 else 'WARNING','alert_type':'SESSION_LONG',
                  'po_id':None,'part_id':None,'operation_id':None,'session_id':session_row['id'],
                  'title':f"{session_row.get('po_code','')} · {session_row.get('operation_code','')}",
                  'message':f"Session của {session_row.get('employee_name','')} đã làm thực tế {round(elapsed/3600,1)} giờ (đã trừ giờ nghỉ)",
                  'occurred_at':session_row.get('started_at')})
        for row in po_health:
            if row['health'] in ('CRITICAL','WARNING') and not any(a.get('po_id')==row['id'] and a.get('alert_type')=='PO_RISK' for a in alerts):
                alerts.append({'severity':'CRITICAL' if row['health']=='CRITICAL' else 'WARNING','alert_type':'PO_HEALTH',
                  'po_id':row['id'],'part_id':None,'operation_id':None,'session_id':None,
                  'title':f"{row['code']} · {row['product']}",'message':row['health_reason'],'occurred_at':row.get('planned_end_at') or row.get('due_date')})

        flow_bottlenecks=fetch_all("""SELECT po.id po_id,po.code po_code,p.code part_code,o.id operation_id,o.code operation_code,o.name operation_name,
          src.code source_operation_code,src.done_qty source_done_qty,src.rework_qty source_rework_qty,o.input_source_kind,
          GREATEST(CASE WHEN o.input_source_kind='REWORK' THEN src.rework_qty ELSE src.done_qty END-
            COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=src.id AND c.source_qty_kind=o.input_source_kind),0),0) waiting_qty,
          po.planned_quantity
        FROM operations o JOIN operations src ON src.id=o.input_source_operation_id
        JOIN production_orders po ON po.id=o.production_order_id JOIN parts p ON p.id=o.part_id
        WHERE po.status IN ('IN_PROGRESS','ACTIVE','PAUSED')
          AND o.input_flow_enabled=true AND o.status<>'COMPLETED'
          AND GREATEST(CASE WHEN o.input_source_kind='REWORK' THEN src.rework_qty ELSE src.done_qty END-
            COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=src.id AND c.source_qty_kind=o.input_source_kind),0),0)>=GREATEST(1,CASE WHEN o.input_source_kind='REWORK' THEN 1 ELSE CEIL(COALESCE(po.planned_quantity,0)*0.1) END)
        ORDER BY waiting_qty DESC LIMIT 6""")
        bottlenecks=[]
        for row in flow_bottlenecks:
            bottlenecks.append({'type':'WIP_QUEUE','severity':'WARNING','po_id':row['po_id'],'po_code':row['po_code'],
              'operation_id':row['operation_id'],'operation_code':row['operation_code'],'operation_name':row['operation_name'],
              'part_code':row['part_code'],'value':int(row.get('waiting_qty') or 0),'label':'SP đang chờ',
              'message':f"{row.get('source_operation_code','OP nguồn')} đã cấp dư {int(row.get('waiting_qty') or 0)} SP"})
        for row in sessions:
            elapsed=int(row.get('elapsed_seconds') or 0); planned=int(row.get('planned_seconds') or 0)
            ratio=(elapsed/planned*100) if planned else 0
            if ratio>=85 or elapsed>=7200:
                bottlenecks.append({'type':'ACTIVE_TIME','severity':'CRITICAL' if ratio>=110 or elapsed>=14400 else 'WARNING',
                  'po_id':None,'po_code':row.get('po_code'),'operation_id':None,'operation_code':row.get('operation_code'),
                  'operation_name':row.get('operation_name'),'part_code':'','value':round(ratio,1) if planned else elapsed,
                  'label':'% thời gian' if planned else 'giây','message':f"{row.get('employee_name','')} đang làm lâu hơn nhịp dự kiến"})
        bottlenecks=sorted(bottlenecks,key=lambda x:(0 if x['severity']=='CRITICAL' else 1,-float(x.get('value') or 0)))[:8]

        kiosk_rows=fetch_all("""SELECT ki.device_uuid,COALESCE(NULLIF(ki.device_name,''),ki.device_uuid) device_name,
          st.code station_code,COALESCE(ks.ui_state,'NEVER_SEEN') ui_state,
          COALESCE(ks.health_state,'UNKNOWN') health_state,COALESCE(ks.queue_size,0) queue_size,
          COALESCE(ks.last_error,'') last_error,ks.last_heartbeat_at,
          CASE WHEN ks.last_heartbeat_at IS NULL THEN NULL
               ELSE EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP-ks.last_heartbeat_at))::bigint END heartbeat_age_seconds,
          COALESCE(ks.last_heartbeat_at>=CURRENT_TIMESTAMP-INTERVAL '2 minutes',FALSE) online
        FROM kiosk_identities ki
        LEFT JOIN kiosk_status ks ON ks.device_uuid=ki.device_uuid
        LEFT JOIN stations st ON st.id=COALESCE(ks.station_id,ki.station_id)
        WHERE UPPER(COALESCE(ki.status,'')) IN ('ACTIVE','APPROVED')
        ORDER BY online DESC,ks.last_heartbeat_at DESC NULLS LAST,ki.device_uuid LIMIT 30""")
        kiosk_health={'total':len(kiosk_rows),'online':0,'offline':0,'warning':0,'queued':0,'items':kiosk_rows}
        for row in kiosk_rows:
            if row.get('online'): kiosk_health['online']+=1
            else: kiosk_health['offline']+=1
            if int(row.get('queue_size') or 0)>0: kiosk_health['queued']+=1
            if row.get('online') and (int(row.get('queue_size') or 0)>0 or bool(row.get('last_error')) or str(row.get('health_state') or '').upper() not in ('OK','HEALTHY','READY','')):
                kiosk_health['warning']+=1
        performance['online_rate_percent']=round(kiosk_health['online']/kiosk_health['total']*100,1) if kiosk_health['total'] else 0.0

        summary['risk_alerts']=len(alerts)
        po_status_counts=fetch_all("SELECT status,COUNT(*) count FROM production_orders GROUP BY status ORDER BY status")
        recent=self.recent_activity(12)
        upcoming=fetch_all("""SELECT id,code,product,status,planned_quantity,planned_start_at,planned_end_at,due_date,priority
          FROM production_orders WHERE status IN ('DRAFT','PLANNED','RELEASED')
          ORDER BY COALESCE(planned_start_at,due_date::timestamp,updated_at),id LIMIT 8""")
        return {'summary':summary,'performance':performance,'daily_output':daily_output,'po_health':po_health,
          'sessions':sessions,'po_tree':po_tree,'alerts':alerts,'bottlenecks':bottlenecks,'kiosk_health':kiosk_health,
          'working_calendar':cfg,'po_status_counts':po_status_counts,'recent_activity':recent,'upcoming_pos':upcoming,
          'generated_at':fetch_one('SELECT CURRENT_TIMESTAMP generated_at')['generated_at']}

    def production_schedule(self,limit:int=200):
        rows=fetch_all("""SELECT po.id po_id,po.code po_code,po.product,po.status po_status,po.planned_start_at po_start,po.planned_end_at po_end,po.planned_quantity,
          p.id part_id,p.code part_code,p.name part_name,p.sort_order part_sort,
          o.id operation_id,o.code operation_code,o.name operation_name,o.status operation_status,o.sort_order operation_sort,
          o.predecessor_operation_id,o.dependency_type,o.lag_minutes,o.standard_seconds_per_unit,o.done_qty,o.defect_qty,o.rework_qty,
          o.planned_start_at,o.planned_end_at,o.input_flow_enabled,o.input_source_operation_id,o.input_source_kind,o.defects_consume_input,
          src.code input_source_code,src.name input_source_name,
          CASE WHEN o.input_source_kind='REWORK' THEN src.rework_qty ELSE src.done_qty END input_source_done_qty,
          GREATEST(COALESCE(CASE WHEN o.input_source_kind='REWORK' THEN src.rework_qty ELSE src.done_qty END,0)-
            COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=src.id AND c.source_qty_kind=o.input_source_kind),0),0) input_available_qty,
          MIN(ws.started_at) actual_start_at,MAX(ws.ended_at) actual_end_at,COUNT(ws.id) FILTER (WHERE ws.status='OPEN') active_sessions
        FROM production_orders po JOIN parts p ON p.production_order_id=po.id JOIN operations o ON o.part_id=p.id
        LEFT JOIN operations src ON src.id=o.input_source_operation_id
        LEFT JOIN work_sessions ws ON ws.operation_id=o.id
        WHERE po.status IN ('RELEASED','IN_PROGRESS','PAUSED')
        GROUP BY po.id,p.id,o.id,src.id ORDER BY po.planned_start_at NULLS LAST,po.id,p.sort_order,p.id,o.sort_order,o.id LIMIT %s""",(min(max(limit,1),1000),))
        by_id={r['operation_id']:r for r in rows}
        for r in rows:
            pred=by_id.get(r.get('predecessor_operation_id'))
            r['predecessor_code']=pred.get('operation_code') if pred else None
            r['blocked']=bool(pred and pred.get('operation_status')!='COMPLETED')
            plan=max(int(r.get('planned_quantity') or 0),0)
            good=max(int(r.get('done_qty') or 0),0)
            defect=max(int(r.get('defect_qty') or 0),0)
            r['progress_percent']=round(min(good/plan*100,100),1) if plan else 0.0
            r['reported_qty']=good+defect
            r['input_consumed_qty']=good+(defect if r.get('defects_consume_input') else 0)
            if r.get('planned_start_at') is None and r.get('po_start'):
                # fallback timeline: sequence Operations in each Part using standard duration
                siblings=[x for x in rows if x['part_id']==r['part_id']]
                cursor=r['po_start']
                from datetime import timedelta
                for x in siblings:
                    seconds=float(x.get('standard_seconds_per_unit') or 0)*int(x.get('planned_quantity') or 0)
                    x['calculated_start_at']=cursor
                    x['calculated_end_at']=cursor+timedelta(seconds=seconds) if seconds>0 else cursor
                    cursor=x['calculated_end_at']+timedelta(minutes=int(x.get('lag_minutes') or 0))
            else:
                r['calculated_start_at']=r.get('planned_start_at')
                r['calculated_end_at']=r.get('planned_end_at')
        return rows


    def production_control(self,limit:int=2000,now:datetime|None=None):
        """Decision-oriented PO/Operation control board.

        Reuses the production-schedule dataset, then derives readiness, WIP,
        schedule gap and a deterministic priority score.  No schema change is
        required; the score is advisory and all component reasons are returned
        to the UI for transparency.
        """
        rows=self.production_schedule(min(max(limit,1),2000))
        now=now or utc_now()
        by_id={int(r['operation_id']):r for r in rows if r.get('operation_id') is not None}
        po_groups={}
        for r in rows:
            po_groups.setdefault(int(r['po_id']),[]).append(r)

        def aware(v):
            if v is None: return None
            if isinstance(v,(date,datetime)):
                return coerce_utc(v,date_time=datetime.max.time().replace(microsecond=0))
            return None

        for po_id,ops in po_groups.items():
            po_start=aware(ops[0].get('po_start'))
            po_end=aware(ops[0].get('po_end'))
            due=aware(ops[0].get('due_date'))
            # Expected PO completion at the current moment.  Prefer planned
            # start/end, otherwise due date only contributes urgency.
            expected_po=0.0
            if po_start and po_end and po_end>po_start:
                if now<=po_start: expected_po=0.0
                elif now>=po_end: expected_po=100.0
                else: expected_po=(now-po_start).total_seconds()/(po_end-po_start).total_seconds()*100.0
            po_actual=sum(float(x.get('progress_percent') or 0) for x in ops)/len(ops) if ops else 0.0
            for r in ops:
                plan=max(int(r.get('planned_quantity') or 0),0)
                good=max(int(r.get('done_qty') or 0),0)
                defect=max(int(r.get('defect_qty') or 0),0)
                rework=max(int(r.get('rework_qty') or 0),0)
                reported=good+defect
                active=int(r.get('active_sessions') or 0)
                pred=by_id.get(int(r['predecessor_operation_id'])) if r.get('predecessor_operation_id') else None

                # WIP ready for this operation.
                if r.get('input_flow_enabled') and r.get('input_source_operation_id'):
                    wip=max(int(r.get('input_available_qty') or 0),0)
                    wip_source='LEDGER'
                elif pred:
                    upstream=max(int(pred.get('done_qty') or 0),0)
                    # Already reported on this OP approximates consumed pieces.
                    wip=max(upstream-reported,0)
                    wip_source='PREDECESSOR'
                else:
                    wip=max(plan-reported,0) if plan else 0
                    wip_source='PO'

                remaining=max(plan-good,0) if plan else 0
                progress=float(r.get('progress_percent') or 0)
                gap=max(expected_po-progress,0.0)
                score=0.0; reasons=[]

                # Deadline urgency.
                days_to_due=None
                if due:
                    days_to_due=(due-now).total_seconds()/86400.0
                    if days_to_due<0:
                        score+=42; reasons.append('PO đã quá hạn')
                    elif days_to_due<=1:
                        score+=32; reasons.append('PO còn ≤ 1 ngày')
                    elif days_to_due<=3:
                        score+=22; reasons.append('PO còn ≤ 3 ngày')
                    elif days_to_due<=7:
                        score+=10; reasons.append('PO sắp đến hạn')

                # Progress lag against PO time plan.
                if gap>=35:
                    score+=30; reasons.append(f'Chậm {gap:.0f}% so với tiến độ thời gian')
                elif gap>=20:
                    score+=22; reasons.append(f'Chậm {gap:.0f}% so với tiến độ thời gian')
                elif gap>=10:
                    score+=12; reasons.append(f'Chậm {gap:.0f}% so với tiến độ thời gian')

                # Ready WIP without manpower is an actionable bottleneck.
                if wip>0 and active==0 and remaining>0:
                    ratio=(wip/plan*100) if plan else 0
                    score+=18 if ratio>=20 else 10
                    reasons.append(f'{wip} SP đang chờ nhưng chưa có người làm')
                elif wip>0 and active>0:
                    reasons.append(f'{wip} SP đầu vào sẵn sàng')

                # Rework inventory deserves attention, especially repair OPs.
                if str(r.get('input_source_kind') or 'GOOD').upper()=='REWORK' and wip>0:
                    score+=12; reasons.append(f'{wip} SP lỗi đang chờ sửa')
                elif rework>0:
                    score+=min(10,4+rework/5); reasons.append(f'Đang có {rework} SP lỗi sửa được')

                status=str(r.get('operation_status') or '').upper()
                completed=status=='COMPLETED' or (plan>0 and good>=plan)
                blocked=bool(r.get('blocked'))
                if completed:
                    control='DONE'; label='HOÀN THÀNH'; score=-1
                    action='Không cần điều phối'
                elif blocked and wip<=0:
                    control='WAITING'; label='CHỜ ĐẦU VÀO'; score=min(score,8)
                    reasons=['OP trước chưa đủ đầu vào']
                    action='Theo dõi OP nguồn trước khi điều người'
                elif wip<=0 and r.get('input_flow_enabled'):
                    control='WAITING'; label='CHỜ ĐẦU VÀO'; score=min(score,8)
                    reasons=['Chưa có sản phẩm đầu vào khả dụng']
                    action='Không tăng người; xử lý OP nguồn'
                elif score>=55:
                    control='CRITICAL'; label='LÀM NGAY'
                    action='Ưu tiên cấp người/máy cho Operation này'
                elif score>=28:
                    control='WARNING'; label='CẦN CHÚ Ý'
                    action='Theo dõi sát và cân nhắc tăng nguồn lực'
                else:
                    control='ON_TRACK'; label='ĐÚNG TIẾN ĐỘ'
                    action='Tiếp tục kế hoạch hiện tại'

                r['wip_qty']=wip
                r['wip_source']=wip_source
                r['remaining_qty']=remaining
                r['expected_po_percent']=round(expected_po,1)
                r['po_actual_percent']=round(po_actual,1)
                r['schedule_gap_percent']=round(gap,1)
                r['days_to_due']=round(days_to_due,1) if days_to_due is not None else None
                r['priority_score']=round(max(score,0),1)
                r['control_state']=control
                r['control_label']=label
                r['priority_reasons']=reasons[:4]
                r['recommended_action']=action

        # Canonical scheduling/readiness result. This deliberately overwrites the
        # legacy PO-percent heuristic above while keeping response compatibility.
        for ops in po_groups.values():
            local_by_id={int(x['operation_id']):x for x in ops}
            for r in ops:
                pred=local_by_id.get(int(r['predecessor_operation_id'])) if r.get('predecessor_operation_id') else None
                result=priority_for_operation(r,pred,now)
                r.update(result)
                status=str(r.get('operation_status') or '').upper()
                if status in {'COMPLETED','CANCELLED'}:
                    r['control_state']='DONE';r['control_label']='HOÀN THÀNH' if status=='COMPLETED' else 'ĐÃ HỦY';r['recommended_action']='Không điều phối'
                elif not r['actionable']:
                    r['control_state']='WAITING';r['control_label']='CHỜ ĐẦU VÀO';r['recommended_action']='Theo dõi dependency/WIP trước khi điều người'
                elif r['dispatch_priority_score']>=55:
                    r['control_state']='CRITICAL';r['control_label']='LÀM NGAY';r['recommended_action']='Ưu tiên cấp người/máy cho Operation này'
                elif r['dispatch_priority_score']>=28:
                    r['control_state']='WARNING';r['control_label']='CẦN CHÚ Ý';r['recommended_action']='Theo dõi sát và cân nhắc tăng nguồn lực'
                else:
                    r['control_state']='ON_TRACK';r['control_label']='ĐÚNG TIẾN ĐỘ';r['recommended_action']='Tiếp tục kế hoạch hiện tại'
                duration=max(((r.get('operation_target_end_at')-r.get('operation_target_start_at')).total_seconds() if r.get('operation_target_end_at') and r.get('operation_target_start_at') else 0),1)
                r['schedule_gap_percent']=round(min(r.get('schedule_lateness_seconds',0)/duration*100,999),1)
        flat=[r for ops in po_groups.values() for r in ops]
        flat.sort(key=priority_sort_key)

        pos=[]
        for po_id,ops in po_groups.items():
            actionable=[x for x in ops if x.get('control_state') not in ('DONE','WAITING')]
            top=max(actionable,key=lambda x:float(x.get('priority_score') or 0),default=None)
            states={x.get('control_state') for x in ops}
            po_state='CRITICAL' if 'CRITICAL' in states else 'WARNING' if 'WARNING' in states else 'ON_TRACK' if 'ON_TRACK' in states else 'WAITING'
            pos.append({
                'po_id':po_id,'po_code':ops[0].get('po_code'),'product':ops[0].get('product'),'po_status':ops[0].get('po_status'),
                'planned_quantity':ops[0].get('planned_quantity'),'due_date':ops[0].get('due_date'),
                'operation_count':len(ops),'completed_count':sum(1 for x in ops if x.get('control_state')=='DONE'),
                'progress_percent':round(sum(float(x.get('progress_percent') or 0) for x in ops)/len(ops),1) if ops else 0.0,
                'control_state':po_state,'top_operation_id':top.get('operation_id') if top else None,
                'top_operation_code':top.get('operation_code') if top else None,'top_operation_name':top.get('operation_name') if top else None,
                'top_priority_score':top.get('priority_score') if top else 0,'top_action':top.get('recommended_action') if top else 'Theo dõi kế hoạch',
                'total_wip_qty':sum(int(x.get('wip_qty') or 0) for x in ops),
            })
        pos.sort(key=lambda x:(0 if x['control_state']=='CRITICAL' else 1 if x['control_state']=='WARNING' else 2 if x['control_state']=='ON_TRACK' else 3,-float(x.get('top_priority_score') or 0)))
        summary={
            'po_count':len(pos),'operation_count':len(flat),
            'critical_ops':sum(1 for x in flat if x.get('control_state')=='CRITICAL'),
            'warning_ops':sum(1 for x in flat if x.get('control_state')=='WARNING'),
            'waiting_ops':sum(1 for x in flat if x.get('control_state')=='WAITING'),
            'active_sessions':sum(int(x.get('active_sessions') or 0) for x in flat),
        }
        return {'summary':summary,'production_orders':pos,'operations':flat,'generated_at':now}


    def daily_progress(self,shift_date:str|None=None,limit:int=500,shift_id:int|None=None,shift_code:str|None=None):
        ctx=resolve_shift_context(shift_date,shift_id,shift_code)
        shift_start,shift_end=ctx['range_start'],ctx['range_end']
        work_windows=[(x['start_at'],x['end_at']) for x in ctx['intervals'] if x.get('interval_type')=='WORK']
        duration_parts=[]; duration_params=[]
        for left,right in work_windows:
            duration_parts.append("GREATEST(EXTRACT(EPOCH FROM (LEAST(COALESCE(ds.ended_at,CURRENT_TIMESTAMP),%s)-GREATEST(ds.started_at,%s))),0)")
            duration_params.extend([right,left])
        duration_sql=' + '.join(duration_parts) if duration_parts else '0'
        params=[shift_end,shift_start,shift_start,shift_end,shift_start,shift_end,shift_start,shift_end,*duration_params,min(max(limit,1),2000)]
        return fetch_all(f"""WITH shift_sessions AS (
          SELECT ws.*,COALESCE(ws.ended_at,ws.updated_at) report_at
          FROM work_sessions ws
          WHERE ws.started_at < %s AND COALESCE(ws.ended_at,CURRENT_TIMESTAMP) >= %s
        ), rollup AS (
          SELECT o.id operation_id,MIN(ds.started_at) first_started_at,MAX(ds.started_at) last_started_at,
            MAX(ds.report_at) last_report_at,COUNT(ds.id) session_count,
            COUNT(ds.id) FILTER (WHERE ds.status='OPEN') open_session_count,
            COALESCE(SUM(ds.good_qty) FILTER (WHERE ds.report_at >= %s AND ds.report_at < %s),0) day_good_qty,
            COALESCE(SUM(ds.defect_qty) FILTER (WHERE ds.report_at >= %s AND ds.report_at < %s),0) day_defect_qty,
            COALESCE(SUM(ds.rework_qty) FILTER (WHERE ds.report_at >= %s AND ds.report_at < %s),0) day_rework_qty,
            COALESCE(SUM({duration_sql}),0)::bigint day_work_seconds,
            STRING_AGG(DISTINCT e.name,', ' ORDER BY e.name) workers
          FROM operations o LEFT JOIN shift_sessions ds ON ds.operation_id=o.id
          LEFT JOIN employees e ON e.id=ds.employee_id GROUP BY o.id
        ) SELECT po.id po_id,po.code po_code,po.product,po.status po_status,
          p.id part_id,p.code part_code,p.name part_name,o.id operation_id,o.code operation_code,o.name operation_name,
          o.status operation_status,o.done_qty total_good_qty,o.defect_qty total_defect_qty,COALESCE(o.rework_qty,0) total_rework_qty,po.planned_quantity,
          COALESCE(o.standard_seconds_per_unit,0) standard_seconds_per_unit,
          (COALESCE(po.planned_quantity,0)*COALESCE(o.standard_seconds_per_unit,0))::bigint planned_work_seconds,
          COALESCE(r.session_count,0) session_count,COALESCE(r.open_session_count,0) open_session_count,
          COALESCE(r.day_good_qty,0) day_good_qty,COALESCE(r.day_defect_qty,0) day_defect_qty,COALESCE(r.day_rework_qty,0) day_rework_qty,
          COALESCE(r.day_work_seconds,0) day_work_seconds,r.workers,r.first_started_at,r.last_started_at,r.last_report_at,
          CASE WHEN COALESCE(r.open_session_count,0)>0 THEN 'RUNNING'
            WHEN COALESCE(r.day_defect_qty,0)>0 THEN 'HAS_DEFECT'
            WHEN COALESCE(r.session_count,0)>0 THEN 'UPDATED' ELSE 'IDLE' END day_state
        FROM operations o JOIN parts p ON p.id=o.part_id JOIN production_orders po ON po.id=o.production_order_id
        LEFT JOIN rollup r ON r.operation_id=o.id
        WHERE COALESCE(r.session_count,0)>0
        ORDER BY CASE WHEN COALESCE(r.open_session_count,0)>0 THEN 0 WHEN COALESCE(r.day_defect_qty,0)>0 THEN 1 ELSE 2 END,
          r.last_report_at DESC NULLS LAST LIMIT %s""",params)

    def daily_sessions(self,shift_date:str|None=None,limit:int=1000,shift_id:int|None=None,shift_code:str|None=None):
        ctx=resolve_shift_context(shift_date,shift_id,shift_code)
        work_parts=[];work_params=[]
        for interval in ctx['intervals']:
            if interval.get('interval_type')!='WORK':continue
            work_parts.append("GREATEST(EXTRACT(EPOCH FROM (LEAST(COALESCE(ws.ended_at,CURRENT_TIMESTAMP),%s)-GREATEST(ws.started_at,%s))),0)")
            work_params.extend([interval['end_at'],interval['start_at']])
        work_sql=' + '.join(work_parts) if work_parts else '0'
        return fetch_all(f"""SELECT ws.id session_id,ws.status session_status,ws.started_at,ws.ended_at,
          COALESCE(ws.ended_at,CURRENT_TIMESTAMP) effective_end_at,
          GREATEST(EXTRACT(EPOCH FROM (LEAST(COALESCE(ws.ended_at,CURRENT_TIMESTAMP),%s)-GREATEST(ws.started_at,%s))),0)::bigint duration_seconds,
          GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint total_duration_seconds,
          ({work_sql})::bigint work_duration_seconds,
          COALESCE(ws.good_qty,0) good_qty,COALESCE(ws.defect_qty,0) defect_qty,COALESCE(ws.rework_qty,0) rework_qty,
          e.id employee_id,e.employee_no employee_code,e.name employee_name,
          po.id po_id,po.code po_code,p.id part_id,p.code part_code,p.name part_name,
          o.id operation_id,o.code operation_code,o.name operation_name
        FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id JOIN production_orders po ON po.id=o.production_order_id
        JOIN parts p ON p.id=o.part_id
        WHERE ws.started_at < %s AND COALESCE(ws.ended_at,CURRENT_TIMESTAMP) >= %s
        ORDER BY ws.started_at,ws.id LIMIT %s""",(ctx['range_end'],ctx['range_start'],*work_params,ctx['range_end'],ctx['range_start'],min(max(limit,1),3000)))

    def shift_activity(self,shift_date:str|None=None,limit:int=100,shift_id:int|None=None,shift_code:str|None=None):
        ctx=resolve_shift_context(shift_date,shift_id,shift_code)
        return fetch_all("""SELECT * FROM (
          SELECT 'SESSION_STARTED' item_type,ws.id::text item_id,ws.started_at activity_at,
            e.name actor,o.name subject,'STARTED' status,po.code po_code,o.code operation_code,
            0::integer good_qty,0::integer defect_qty
          FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id
          JOIN production_orders po ON po.id=o.production_order_id WHERE ws.started_at >= %s AND ws.started_at < %s
          UNION ALL
          SELECT 'QUANTITY_REPORTED',ws.id::text,COALESCE(ws.ended_at,ws.updated_at),e.name,o.name,
            CASE WHEN ws.status='OPEN' THEN 'QUANTITY_UPDATED' ELSE 'FINISHED' END,po.code,o.code,
            COALESCE(ws.good_qty,0),COALESCE(ws.defect_qty,0)
          FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id
          JOIN production_orders po ON po.id=o.production_order_id
          WHERE COALESCE(ws.ended_at,ws.updated_at) >= %s AND COALESCE(ws.ended_at,ws.updated_at) < %s
        ) activity ORDER BY activity_at DESC LIMIT %s""",(ctx['range_start'],ctx['range_end'],ctx['range_start'],ctx['range_end'],min(max(limit,1),500)))

    def shift_dashboard(self,shift_date:str|None=None,shift_id:int|None=None,limit:int=1000):
        ctx=resolve_shift_context(shift_date,shift_id)
        shift=dict(ctx['shift'])
        serial_intervals=[]
        for iv in ctx['intervals']:
            item={k:v for k,v in iv.items() if k not in ('start_at','end_at')}
            item['start_at']=iv['start_at'].isoformat();item['end_at']=iv['end_at'].isoformat();serial_intervals.append(item)
        return {'context':{'shift_date':ctx['shift_date'].isoformat(),'shift_id':shift.get('id'),'shift_code':shift.get('code'),
          'shift_name':shift.get('name'),'timezone':shift.get('timezone'),'range_start':ctx['range_start'].isoformat(),
          'range_end':ctx['range_end'].isoformat(),'cross_midnight':bool(shift.get('cross_midnight')),
          'target_minutes':int(shift.get('target_minutes') or 0),'intervals':serial_intervals},
          'items':self.daily_progress(shift_date,limit,shift_id),'sessions':self.daily_sessions(shift_date,min(limit*2,3000),shift_id),
          'activity':self.shift_activity(shift_date,100,shift_id)}

    def recent_activity(self,limit:int=100):
        return fetch_all("""SELECT 'SESSION_STARTED' item_type,ws.id::text item_id,ws.started_at activity_at,
          e.name actor,o.name subject,'STARTED' status,po.code po_code,o.code operation_code,
          0::integer good_qty,0::integer defect_qty
        FROM work_sessions ws
        JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id
        JOIN production_orders po ON po.id=o.production_order_id
        WHERE ws.started_at IS NOT NULL
        UNION ALL
        SELECT 'QUANTITY_REPORTED',ws.id::text,COALESCE(ws.ended_at,ws.updated_at),
          e.name,o.name,CASE WHEN ws.status='OPEN' THEN 'QUANTITY_UPDATED' ELSE 'FINISHED' END,
          po.code,o.code,COALESCE(ws.good_qty,0),COALESCE(ws.defect_qty,0)
        FROM work_sessions ws
        JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id
        JOIN production_orders po ON po.id=o.production_order_id
        WHERE ws.ended_at IS NOT NULL OR COALESCE(ws.good_qty,0)>0 OR COALESCE(ws.defect_qty,0)>0
        UNION ALL
        SELECT 'QC',q.id::text,q.updated_at,COALESCE(u.display_name,''),o.name,q.status,
          po.code,o.code,COALESCE(q.good_qty,0),COALESCE(q.defect_qty,0)
        FROM qc_inspections q
        LEFT JOIN users u ON u.id=q.inspector_user_id
        JOIN operations o ON o.id=q.operation_id
        JOIN production_orders po ON po.id=o.production_order_id
        UNION ALL
        SELECT 'KIOSK_EVENT',k.id::text,k.received_at,k.device_uuid,k.event_type,k.status,
          NULL::text,NULL::text,0::integer,0::integer FROM kiosk_events k
        ORDER BY activity_at DESC LIMIT %s""",(min(max(limit,1),500),))

class ReportRepository:
    def production_order(self,po_id:int):
        po=fetch_one('SELECT * FROM production_orders WHERE id=%s',(po_id,))
        if not po: raise NotFoundError('production order not found')
        parts=fetch_all('SELECT * FROM parts WHERE production_order_id=%s ORDER BY sort_order,id',(po_id,))
        operations=fetch_all("""SELECT o.*,e.code equipment_code,e.name equipment_name,
          COUNT(ws.id) session_count,COALESCE(SUM(ws.good_qty),0) session_good_qty,
          COALESCE(SUM(ws.defect_qty),0) session_defect_qty,
          COALESCE(SUM(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at))),0)::bigint work_seconds
        FROM operations o LEFT JOIN equipment e ON e.id=o.equipment_id
        LEFT JOIN work_sessions ws ON ws.operation_id=o.id
        WHERE o.production_order_id=%s GROUP BY o.id,e.code,e.name ORDER BY o.sort_order,o.id""",(po_id,))
        qc=fetch_all("""SELECT q.*,o.code operation_code,o.name operation_name,u.display_name inspector_name
        FROM qc_inspections q JOIN operations o ON o.id=q.operation_id LEFT JOIN users u ON u.id=q.inspector_user_id
        WHERE o.production_order_id=%s ORDER BY q.id DESC""",(po_id,))
        adjustments=fetch_all("""SELECT a.*,o.code operation_code,u.display_name adjusted_by_name
        FROM operation_adjustments a JOIN operations o ON o.id=a.operation_id LEFT JOIN users u ON u.id=a.adjusted_by
        WHERE o.production_order_id=%s ORDER BY a.id DESC""",(po_id,))
        return {'production_order':po,'parts':parts,'operations':operations,'qc_inspections':qc,'adjustments':adjustments}
    def operation(self,operation_id:int):
        operation=fetch_one("""SELECT o.*,po.code po_code,p.code part_code,p.name part_name
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id JOIN parts p ON p.id=o.part_id
        WHERE o.id=%s""",(operation_id,))
        if not operation: raise NotFoundError('operation not found')
        sessions=fetch_all("""SELECT ws.*,e.employee_no,e.name employee_name,s.code station_code
        FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id LEFT JOIN stations s ON s.id=ws.station_id
        WHERE ws.operation_id=%s ORDER BY ws.id DESC""",(operation_id,))
        return {'operation':operation,'sessions':sessions}

    def operation_sessions(self,operation_id:int|None=None,date_from:str|None=None,date_to:str|None=None,
                           employee_id:int|None=None,status:str|None=None,limit:int=3000):
        conditions=['1=1']; params=[]
        if operation_id:
            conditions.append('ws.operation_id=%s'); params.append(operation_id)
        if date_from:
            conditions.append('ws.started_at >= %s::date'); params.append(date_from)
        if date_to:
            conditions.append("ws.started_at < (%s::date + INTERVAL '1 day')"); params.append(date_to)
        if employee_id:
            conditions.append('ws.employee_id=%s'); params.append(employee_id)
        status=(status or '').strip().upper()
        if status:
            conditions.append('ws.status=%s'); params.append(status)
        params.append(min(max(limit,1),10000))
        sessions=fetch_all(f"""SELECT ws.id session_id,ws.status,ws.started_at,ws.ended_at,
          COALESCE(ws.ended_at,CURRENT_TIMESTAMP) effective_end_at,
          GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds,
          COALESCE(ws.good_qty,0) good_qty,COALESCE(ws.defect_qty,0) defect_qty,COALESCE(ws.rework_qty,0) rework_qty,
          ws.device_uuid,ws.station_id,s.code station_code,s.name station_name,
          e.id employee_id,e.employee_no employee_code,e.name employee_name,e.department,e.team,e.position,
          o.id operation_id,o.code operation_code,o.name operation_name,o.status operation_status,
          po.id po_id,po.code po_code,po.product,p.id part_id,p.code part_code,p.name part_name
        FROM work_sessions ws
        JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id
        JOIN production_orders po ON po.id=o.production_order_id
        JOIN parts p ON p.id=o.part_id
        LEFT JOIN stations s ON s.id=ws.station_id
        WHERE {' AND '.join(conditions)}
        ORDER BY ws.started_at DESC,ws.id DESC LIMIT %s""",params)
        users=fetch_all(f"""SELECT e.id employee_id,e.employee_no employee_code,e.name employee_name,
          e.department,e.team,e.position,COUNT(ws.id) session_count,
          COUNT(*) FILTER (WHERE ws.status='OPEN') open_session_count,
          COALESCE(SUM(ws.good_qty),0) good_qty,COALESCE(SUM(ws.defect_qty),0) defect_qty,COALESCE(SUM(ws.rework_qty),0) rework_qty,
          COALESCE(SUM(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at))),0)::bigint work_seconds,
          MIN(ws.started_at) first_started_at,MAX(COALESCE(ws.ended_at,ws.updated_at,ws.started_at)) last_activity_at
        FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id
        WHERE {' AND '.join(conditions)} GROUP BY e.id ORDER BY work_seconds DESC,e.employee_no""",params[:-1])
        operations=fetch_all("""SELECT o.id operation_id,o.code operation_code,o.name operation_name,
          po.code po_code,po.product,p.code part_code,p.name part_name
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        JOIN parts p ON p.id=o.part_id
        WHERE EXISTS(SELECT 1 FROM work_sessions ws WHERE ws.operation_id=o.id)
        ORDER BY po.code,p.sort_order,o.sort_order,o.id LIMIT 5000""")
        return {'sessions':sessions,'users':users,'operations':operations}

    def session_exceptions(self,status:str|None=None,employee_id:int|None=None,limit:int=1000,workflow_status:str|None=None):
        conditions=[];params=[]
        if employee_id:
            conditions.append('ws.employee_id=%s');params.append(employee_id)
        status=(status or '').strip().upper()
        if status=='OPEN': conditions.append("ws.status='OPEN'")
        elif status=='CLOSED': conditions.append("ws.status='CLOSED'")
        workflow_status=(workflow_status or '').strip().upper()
        if workflow_status in ('NEW','IN_PROGRESS','RESOLVED','IGNORED'):
            if workflow_status=='NEW': conditions.append("COALESCE(r.workflow_status,'NEW')='NEW'")
            else: conditions.append('r.workflow_status=%s');params.append(workflow_status)
        where=('WHERE '+' AND '.join(conditions)) if conditions else ''
        params.append(min(max(limit,1),5000))
        return fetch_all(f"""WITH overlap_flags AS (
          SELECT a.id session_id,b.id conflict_session_id,'OVERLAP' exception_code,'CRITICAL' severity,
            'Chồng thời gian với session #'||b.id exception_message
          FROM work_sessions a JOIN work_sessions b ON b.employee_id=a.employee_id AND b.id<a.id
           AND tstzrange(a.started_at,COALESCE(a.ended_at,'infinity'::timestamptz),'[)')
               && tstzrange(b.started_at,COALESCE(b.ended_at,'infinity'::timestamptz),'[)')
        ), flags AS (
          SELECT ws.id session_id,NULL::bigint conflict_session_id,'OPEN_TOO_LONG' exception_code,'ERROR' severity,
            'Session đang mở quá 12 giờ' exception_message FROM work_sessions ws
            WHERE ws.status='OPEN' AND ws.started_at<CURRENT_TIMESTAMP-INTERVAL '12 hours'
          UNION ALL
          SELECT ws.id,NULL,'ZERO_QTY_LONG','WARNING','Session đóng trên 4 giờ nhưng sản lượng bằng 0'
            FROM work_sessions ws WHERE ws.status='CLOSED' AND COALESCE(ws.good_qty,0)+COALESCE(ws.defect_qty,0)=0
              AND ws.ended_at-ws.started_at>INTERVAL '4 hours'
          UNION ALL
          SELECT ws.id,NULL,'MISSING_STATION','WARNING','Session không có trạm/kiosk'
            FROM work_sessions ws WHERE ws.station_id IS NULL AND COALESCE(ws.device_uuid,'')=''
          UNION ALL
          SELECT ws.id,NULL,'INVALID_TIME','CRITICAL','Giờ kết thúc trước giờ bắt đầu'
            FROM work_sessions ws WHERE ws.ended_at IS NOT NULL AND ws.ended_at<ws.started_at
        ), all_flags AS (SELECT * FROM overlap_flags UNION ALL SELECT * FROM flags), detected AS (
          SELECT f.*,f.exception_code||':'||COALESCE(f.conflict_session_id,0)::text exception_fingerprint FROM all_flags f
        )
        SELECT f.exception_code,f.exception_fingerprint,f.severity,f.exception_message,f.conflict_session_id,
          ws.id session_id,ws.status session_status,ws.started_at,ws.ended_at,
          GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds,
          ws.good_qty,ws.defect_qty,COALESCE(ws.rework_qty,0) rework_qty,ws.station_id,ws.device_uuid,
          e.id employee_id,e.employee_no employee_code,e.name employee_name,
          o.id operation_id,o.code operation_code,o.name operation_name,
          po.code po_code,p.code part_code,
          COALESCE(r.workflow_status,'NEW') workflow_status,COALESCE(r.resolution,'') resolution,
          COALESCE(r.note,'') review_note,COALESCE(r.assigned_to,'') assigned_to,
          r.started_at review_started_at,COALESCE(r.started_by,'') started_by,
          r.resolved_at,COALESCE(r.resolved_by,'') resolved_by,r.updated_at review_updated_at
        FROM detected f JOIN work_sessions ws ON ws.id=f.session_id
        JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id
        JOIN production_orders po ON po.id=o.production_order_id JOIN parts p ON p.id=o.part_id
        LEFT JOIN session_exception_reviews r ON r.session_id=f.session_id AND r.exception_fingerprint=f.exception_fingerprint
        {where}
        ORDER BY CASE COALESCE(r.workflow_status,'NEW') WHEN 'NEW' THEN 0 WHEN 'IN_PROGRESS' THEN 1 WHEN 'RESOLVED' THEN 2 ELSE 3 END,
          CASE f.severity WHEN 'CRITICAL' THEN 0 WHEN 'ERROR' THEN 1 ELSE 2 END,ws.started_at DESC
        LIMIT %s""",params)

    def update_session_exception_reviews(self,items:list[dict[str,Any]],workflow_status:str,note:str,actor_username:str,assigned_to:str='',resolution:str=''):
        target=(workflow_status or '').strip().upper()
        if target not in ('NEW','IN_PROGRESS','RESOLVED','IGNORED'):
            raise ValueError('Trạng thái xử lý không hợp lệ')
        if target in ('RESOLVED','IGNORED') and not (note or '').strip():
            raise ValueError('Phải nhập ghi chú khi kết thúc xử lý')
        if not items: raise ValueError('Chưa chọn Session Exception')
        result=[]
        with transaction() as conn:
            with conn.cursor() as cur:
                for item in items[:500]:
                    session_id=int(item.get('session_id'))
                    code=str(item.get('exception_code') or '').strip().upper()
                    fingerprint=str(item.get('exception_fingerprint') or '').strip()
                    if not code or not fingerprint: raise ValueError('Thiếu định danh Session Exception')
                    cur.execute('SELECT id FROM work_sessions WHERE id=%s',(session_id,))
                    if not cur.fetchone(): raise NotFoundError(f'Không tìm thấy Session #{session_id}')
                    started_by=actor_username if target=='IN_PROGRESS' else ''
                    resolved_by=actor_username if target in ('RESOLVED','IGNORED') else ''
                    cur.execute("""INSERT INTO session_exception_reviews(
                      session_id,exception_code,exception_fingerprint,workflow_status,resolution,note,assigned_to,
                      started_by,started_at,resolved_by,resolved_at,updated_at)
                      VALUES(%s,%s,%s,%s,%s,%s,%s,%s,
                        CASE WHEN %s='IN_PROGRESS' THEN CURRENT_TIMESTAMP ELSE NULL END,%s,
                        CASE WHEN %s IN ('RESOLVED','IGNORED') THEN CURRENT_TIMESTAMP ELSE NULL END,CURRENT_TIMESTAMP)
                      ON CONFLICT(session_id,exception_fingerprint) DO UPDATE SET
                        workflow_status=EXCLUDED.workflow_status,resolution=EXCLUDED.resolution,note=EXCLUDED.note,
                        assigned_to=EXCLUDED.assigned_to,
                        started_by=CASE WHEN EXCLUDED.workflow_status='IN_PROGRESS' THEN EXCLUDED.started_by ELSE session_exception_reviews.started_by END,
                        started_at=CASE WHEN EXCLUDED.workflow_status='IN_PROGRESS' THEN COALESCE(session_exception_reviews.started_at,CURRENT_TIMESTAMP) ELSE session_exception_reviews.started_at END,
                        resolved_by=CASE WHEN EXCLUDED.workflow_status IN ('RESOLVED','IGNORED') THEN EXCLUDED.resolved_by ELSE '' END,
                        resolved_at=CASE WHEN EXCLUDED.workflow_status IN ('RESOLVED','IGNORED') THEN CURRENT_TIMESTAMP ELSE NULL END,
                        updated_at=CURRENT_TIMESTAMP RETURNING *""",
                      (session_id,code,fingerprint,target,resolution or '',note or '',assigned_to or '',started_by,target,resolved_by,target))
                    result.append(cur.fetchone())
        return result

    def employee_performance(self,employee_id:int|None=None,date_from:str|None=None,date_to:str|None=None,
                             status:str|None=None,limit:int=10000):
        employees=fetch_all("""SELECT e.id employee_id,e.employee_no employee_code,e.name employee_name,
          e.department,e.team,e.position,e.employment_status
        FROM employees e ORDER BY e.employee_no,e.name LIMIT 5000""")
        conditions=['1=1']; params=[]
        if employee_id:
            conditions.append('ws.employee_id=%s'); params.append(employee_id)
        if date_from:
            conditions.append('ws.started_at >= %s::date'); params.append(date_from)
        if date_to:
            conditions.append("ws.started_at < (%s::date + INTERVAL '1 day')"); params.append(date_to)
        status=(status or '').strip().upper()
        if status:
            conditions.append('ws.status=%s'); params.append(status)
        params.append(min(max(limit,1),20000))
        sessions=fetch_all(f"""SELECT ws.id session_id,ws.status,ws.started_at,ws.ended_at,
          GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds,
          COALESCE(ws.good_qty,0) good_qty,COALESCE(ws.defect_qty,0) defect_qty,COALESCE(ws.rework_qty,0) rework_qty,
          ws.device_uuid,s.code station_code,e.id employee_id,e.employee_no employee_code,e.name employee_name,
          e.department,e.team,e.position,o.id operation_id,o.code operation_code,o.name operation_name,
          COALESCE(o.standard_seconds_per_unit,0) standard_seconds_per_unit,
          po.code po_code,p.code part_code,p.name part_name
        FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id JOIN production_orders po ON po.id=o.production_order_id
        JOIN parts p ON p.id=o.part_id LEFT JOIN stations s ON s.id=ws.station_id
        WHERE {' AND '.join(conditions)} ORDER BY ws.started_at DESC,ws.id DESC LIMIT %s""",params)
        by_operation={}
        total_seconds=good=defect=expected_seconds=completed=open_count=reported=0
        for row in sessions:
            sec=int(row.get('duration_seconds') or 0); g=int(row.get('good_qty') or 0); d=int(row.get('defect_qty') or 0)
            std=float(row.get('standard_seconds_per_unit') or 0); qty=g+d
            total_seconds+=sec; good+=g; defect+=d; expected_seconds+=std*qty
            completed += 1 if row.get('status')!='OPEN' else 0; open_count += 1 if row.get('status')=='OPEN' else 0
            reported += 1 if qty>0 else 0
            key=row['operation_id']; item=by_operation.setdefault(key,{'operation_id':key,'operation_code':row['operation_code'],
              'operation_name':row['operation_name'],'po_code':row['po_code'],'part_code':row['part_code'],
              'session_count':0,'work_seconds':0,'good_qty':0,'defect_qty':0,'expected_seconds':0})
            item['session_count']+=1; item['work_seconds']+=sec; item['good_qty']+=g; item['defect_qty']+=d
            item['expected_seconds']+=std*qty
        op_rows=[]
        for item in by_operation.values():
            total=item['good_qty']+item['defect_qty']; actual=item['work_seconds']; expected=item['expected_seconds']
            item['yield_percent']=round(item['good_qty']/total*100,2) if total else 0
            item['units_per_hour']=round(item['good_qty']/(actual/3600),2) if actual else 0
            item['efficiency_percent']=round(expected/actual*100,2) if actual and expected else None
            op_rows.append(item)
        op_rows.sort(key=lambda x:(-x['work_seconds'],x['operation_code']))
        total_qty=good+defect; yield_percent=round(good/total_qty*100,2) if total_qty else 0
        efficiency=round(expected_seconds/total_seconds*100,2) if total_seconds and expected_seconds else None
        enough_data=completed>=5 and reported>=3 and total_qty>=20
        summary={'session_count':len(sessions),'completed_session_count':completed,'open_session_count':open_count,
          'reported_session_count':reported,'work_seconds':total_seconds,'good_qty':good,'defect_qty':defect,
          'yield_percent':yield_percent,'defect_percent':round(defect/total_qty*100,2) if total_qty else 0,
          'units_per_hour':round(good/(total_seconds/3600),2) if total_seconds else 0,
          'expected_seconds':round(expected_seconds),'efficiency_percent':efficiency,'operation_count':len(op_rows),
          'enough_data':enough_data,'data_note':'' if enough_data else 'Chưa đủ dữ liệu để xếp loại; cần ít nhất 5 session hoàn tất, 3 session có sản lượng và 20 sản phẩm.'}
        return {'employees':employees,'sessions':sessions,'operations':op_rows,'summary':summary}


    def session_management(self,po_id=None,part_id=None,operation_id=None,employee_id=None,status=None,date_from=None,date_to=None,limit=3000):
        conditions=['1=1']; params=[]
        if po_id: conditions.append('po.id=%s'); params.append(int(po_id))
        if part_id: conditions.append('p.id=%s'); params.append(int(part_id))
        if operation_id: conditions.append('o.id=%s'); params.append(int(operation_id))
        if employee_id: conditions.append('e.id=%s'); params.append(int(employee_id))
        if status: conditions.append('ws.status=%s'); params.append(str(status).upper())
        if date_from: conditions.append('(ws.started_at AT TIME ZONE %s)::date >= %s::date'); params.extend((settings.timezone_name,date_from))
        if date_to: conditions.append("(ws.started_at AT TIME ZONE %s)::date <= %s::date"); params.extend((settings.timezone_name,date_to))
        params.append(min(max(int(limit or 3000),1),10000))
        items=fetch_all(f"""SELECT ws.id session_id,ws.employee_id,ws.operation_id,ws.station_id,ws.device_uuid,ws.status,
          ws.started_at,ws.ended_at,ws.good_qty,ws.defect_qty,COALESCE(ws.rework_qty,0) rework_qty,ws.note,ws.created_at,ws.updated_at,
          e.employee_no employee_code,e.name employee_name,po.id po_id,po.code po_code,
          p.id part_id,p.code part_code,p.name part_name,o.code operation_code,o.name operation_name,
          s.code station_code,s.name station_name,
          GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds
        FROM work_sessions ws JOIN employees e ON e.id=ws.employee_id JOIN operations o ON o.id=ws.operation_id
        JOIN production_orders po ON po.id=o.production_order_id JOIN parts p ON p.id=o.part_id
        LEFT JOIN stations s ON s.id=ws.station_id WHERE {' AND '.join(conditions)}
        ORDER BY ws.started_at DESC,ws.id DESC LIMIT %s""",params)
        filters={
          'production_orders':fetch_all("SELECT id,code,product FROM production_orders ORDER BY code"),
          'parts':fetch_all("SELECT id,production_order_id,code,name FROM parts ORDER BY production_order_id,sort_order,id"),
          'operations':fetch_all("SELECT id,production_order_id,part_id,code,name FROM operations ORDER BY production_order_id,part_id,sort_order,id"),
          'employees':fetch_all("SELECT id,employee_no,name FROM employees WHERE active=TRUE ORDER BY employee_no"),
          'stations':fetch_all("SELECT id,code,name FROM stations WHERE active=TRUE ORDER BY code")
        }
        return {'items':items,'filters':filters}

    def recent_session_operations(self,po_id=None,part_id=None,operation_id=None,employee_id=None,activity='recent',limit=50):
        conditions=['EXISTS (SELECT 1 FROM work_sessions wx WHERE wx.operation_id=o.id)']; params=[]
        if po_id: conditions.append('po.id=%s'); params.append(int(po_id))
        if part_id: conditions.append('p.id=%s'); params.append(int(part_id))
        if operation_id: conditions.append('o.id=%s'); params.append(int(operation_id))
        if employee_id:
            conditions.append('EXISTS (SELECT 1 FROM work_sessions we WHERE we.operation_id=o.id AND we.employee_id=%s)')
            params.append(int(employee_id))
        if str(activity or '').lower()=='running':
            conditions.append("EXISTS (SELECT 1 FROM work_sessions wo WHERE wo.operation_id=o.id AND wo.status='OPEN')")
        params.append(min(max(int(limit or 50),1),200))
        items=fetch_all(f"""SELECT o.id operation_id,o.code operation_code,o.name operation_name,o.status operation_status,
          po.id po_id,po.code po_code,p.id part_id,p.code part_code,p.name part_name,
          COUNT(ws.id) session_count,COUNT(ws.id) FILTER (WHERE ws.status='OPEN') open_session_count,
          COALESCE(SUM(ws.good_qty),0) good_qty,COALESCE(SUM(ws.defect_qty),0) defect_qty,COALESCE(SUM(ws.rework_qty),0) rework_qty,
          MIN(ws.started_at) first_started_at,MAX(ws.started_at) last_started_at,
          MAX(COALESCE(ws.updated_at,ws.ended_at,ws.started_at)) last_activity_at,
          COALESCE(SUM(GREATEST(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)),0)::bigint work_seconds,
          STRING_AGG(DISTINCT e.employee_no || ' · ' || e.name, ', ' ORDER BY e.employee_no || ' · ' || e.name) workers
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id JOIN parts p ON p.id=o.part_id
        JOIN work_sessions ws ON ws.operation_id=o.id JOIN employees e ON e.id=ws.employee_id
        WHERE {' AND '.join(conditions)} GROUP BY o.id,po.id,p.id
        ORDER BY (COUNT(ws.id) FILTER (WHERE ws.status='OPEN')>0) DESC,MAX(COALESCE(ws.updated_at,ws.ended_at,ws.started_at)) DESC,o.id DESC LIMIT %s""",params)
        filters={
          'production_orders':fetch_all("SELECT id,code,product FROM production_orders ORDER BY code"),
          'parts':fetch_all("SELECT id,production_order_id,code,name FROM parts ORDER BY production_order_id,sort_order,id"),
          'operations':fetch_all("SELECT id,production_order_id,part_id,code,name FROM operations ORDER BY production_order_id,part_id,sort_order,id"),
          'employees':fetch_all("SELECT id,employee_no,name FROM employees WHERE active=TRUE ORDER BY employee_no")
        }
        return {'items':items,'filters':filters}

class KPIRepository:
    def employees(self,date_from:str|None=None,date_to:str|None=None,limit:int=500):
        conditions=['1=1']; params=[]
        if date_from: conditions.append('ws.started_at >= %s::date'); params.append(date_from)
        if date_to: conditions.append("ws.started_at < (%s::date + INTERVAL '1 day')"); params.append(date_to)
        params.append(min(max(limit,1),1000))
        return fetch_all(f"""SELECT e.id,e.employee_no,e.name,e.department,e.position,
          COUNT(ws.id) session_count,
          COALESCE(SUM(ws.good_qty),0) good_qty,COALESCE(SUM(ws.defect_qty),0) defect_qty,COALESCE(SUM(ws.rework_qty),0) rework_qty,
          CASE WHEN COALESCE(SUM(ws.good_qty+ws.defect_qty),0)>0 THEN
            ROUND(SUM(ws.good_qty)::numeric/NULLIF(SUM(ws.good_qty+ws.defect_qty),0)*100,2) ELSE 0 END yield_percent,
          COALESCE(SUM(EXTRACT(EPOCH FROM (COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at))),0)::bigint work_seconds,
          COALESCE((SELECT SUM(pt.points) FROM penalty_tickets pt WHERE pt.employee_id=e.id AND pt.status='OPEN'),0) penalty_points
        FROM employees e LEFT JOIN work_sessions ws ON ws.employee_id=e.id AND {' AND '.join(conditions)}
        GROUP BY e.id ORDER BY good_qty DESC,e.employee_no LIMIT %s""",params)
    def operations(self,limit:int=500):
        return fetch_all("""SELECT o.id,o.code,o.name,po.code po_code,po.planned_quantity plan_qty,o.done_qty,o.defect_qty,o.status,
          CASE WHEN po.planned_quantity>0 THEN ROUND(o.done_qty::numeric/po.planned_quantity*100,2) ELSE 0 END completion_percent,
          CASE WHEN o.done_qty+o.defect_qty>0 THEN ROUND(o.done_qty::numeric/(o.done_qty+o.defect_qty)*100,2) ELSE 0 END yield_percent,
          COUNT(ws.id) session_count
        FROM operations o JOIN production_orders po ON po.id=o.production_order_id
        LEFT JOIN work_sessions ws ON ws.operation_id=o.id GROUP BY o.id,po.id
        ORDER BY o.updated_at DESC LIMIT %s""",(min(max(limit,1),1000),))
    def snapshot(self,snapshot_date:date|None=None):
        snapshot_date=snapshot_date or business_date(timezone_name=settings.timezone_name)
        summary=DashboardRepository().summary()
        metrics=dict(summary or {})
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO kpi_snapshots(snapshot_date,scope_type,scope_id,metrics_json)
                VALUES(%s,'SYSTEM','ALL',%s) ON CONFLICT(snapshot_date,scope_type,scope_id)
                DO UPDATE SET metrics_json=EXCLUDED.metrics_json,created_at=CURRENT_TIMESTAMP RETURNING *""",(snapshot_date,metrics))
                return cur.fetchone()

class KioskEventRepository:
    def ingest(self,data:dict[str,Any]):
        # Accept both the canonical API contract and legacy/current ESP telemetry.
        # ESP firmware <= 5.1.7 sends client_event_id + device_id while the newer
        # analytics API originally required event_uuid + device_uuid. Normalizing
        # here keeps the device protocol backward compatible and avoids forcing a
        # fleet reflash just to record telemetry.
        event_uuid=str(data.get('event_uuid') or data.get('client_event_id') or '').strip()
        device_uuid=str(data.get('device_uuid') or data.get('device_id') or '').strip()
        event_type=str(data.get('event_type','')).strip().upper()
        severity=str(data.get('severity','INFO')).strip().upper()
        if not event_uuid or not device_uuid or not event_type: raise ValueError('event_uuid/client_event_id, device_uuid/device_id and event_type required')
        payload=data.get('payload')
        if not isinstance(payload,dict):
            # Preserve useful firmware fields (session_trace_id, ui_state, result,
            # worker/operation codes, HTTP status...) even when there is no nested
            # payload object in the legacy telemetry envelope.
            payload={k:v for k,v in data.items() if k not in {'payload','event_uuid','client_event_id','device_uuid','device_id','event_type','severity','message','station_id','session_id','operation_id','employee_id','occurred_at'}}
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO kiosk_events(event_uuid,device_uuid,station_id,event_type,severity,message,payload_json,session_id,operation_id,employee_id,occurred_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,CURRENT_TIMESTAMP))
                ON CONFLICT(event_uuid) DO UPDATE SET received_at=CURRENT_TIMESTAMP RETURNING *, (xmax=0) inserted""",
                (event_uuid,device_uuid,data.get('station_id'),event_type,severity,str(data.get('message','')),json.dumps(payload,ensure_ascii=False,default=str),data.get('session_id') or None,data.get('operation_id') or None,data.get('employee_id') or None,data.get('occurred_at')))
                event=cur.fetchone()
                if severity in {'ERROR','CRITICAL'}:
                    cur.execute("""INSERT INTO notifications(source_type,source_id,severity,title,message,target_role)
                    VALUES('KIOSK_EVENT',%s,%s,%s,%s,'admin') ON CONFLICT(source_type,source_id) DO NOTHING""",
                    (str(event['id']),severity,f'Kiosk {device_uuid}: {event_type}',str(data.get('message',''))))
                return event
    def list(self,limit:int=200,status:str='',severity:str='',device_uuid:str='',event_type:str=''):
        where=[]; params=[]
        if status: where.append('k.status=%s'); params.append(status)
        if severity: where.append('k.severity=%s'); params.append(severity)
        if device_uuid: where.append('k.device_uuid=%s'); params.append(device_uuid)
        if event_type: where.append('k.event_type=%s'); params.append(event_type)
        clause=(' WHERE '+' AND '.join(where)) if where else ''
        params.append(min(max(limit,1),1000))
        return fetch_all(f"""SELECT k.*,s.code station_code FROM kiosk_events k LEFT JOIN stations s ON s.id=k.station_id
        {clause} ORDER BY k.id DESC LIMIT %s""",params)
    def resolve(self,event_id:int,user_id:int,note:str=''):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE kiosk_events SET status='RESOLVED',resolved_at=CURRENT_TIMESTAMP,resolved_by=%s,resolution_note=%s
                WHERE id=%s AND status<>'RESOLVED' RETURNING *""",(user_id,note,event_id))
                row=cur.fetchone()
                if not row: raise ConflictError('event missing or already resolved')
                return row

class NotificationRepository:
    def list(self,limit:int=200,status:str='',role:str=''):
        where=[]; params=[]
        if status: where.append('status=%s'); params.append(status)
        if role: where.append("(target_role='' OR target_role=%s)"); params.append(role)
        clause=(' WHERE '+' AND '.join(where)) if where else ''
        params.append(min(max(limit,1),1000))
        return fetch_all(f'SELECT * FROM notifications{clause} ORDER BY id DESC LIMIT %s',params)
    def mark_read(self,notification_id:int,user_id:int):
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE notifications SET status='READ',read_at=CURRENT_TIMESTAMP,read_by=%s WHERE id=%s RETURNING *",(user_id,notification_id))
                row=cur.fetchone()
                if not row: raise NotFoundError('notification not found')
                return row
