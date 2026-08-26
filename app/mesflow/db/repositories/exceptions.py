"""Persistence for V67 Exception Center. Detection and decisions are separate."""
from __future__ import annotations
import json
from typing import Any
from mesflow.core.config import settings
from mesflow.core.working_calendar import get_work_shifts, resolve_shift_window_for_datetime
from mesflow.db.connection import fetch_all, fetch_one, transaction
from mesflow.db.repositories.base import ConflictError, NotFoundError
from mesflow.domain.audit import record_audit

ACTIVE=('OPEN','ACKNOWLEDGED')

class ExceptionRepository:
    def _session_past_shift_end_ids(self)->set[int]:
        """SESSION_PAST_SHIFT_END is computed in Python,
        not SQL, because it needs the SAME shift-resolution logic
        ShiftSessionReconciliationService uses (resolve_shift_window_for_datetime,
        per-session's OWN started_at, never "today's" shift) -- duplicating
        that in a raw SQL UNION branch would be exactly the "two parsers/
        two shift-boundary calculations drifting apart" class of bug this
        codebase's own comments elsewhere warn against. A session whose
        started_at falls in a NO_ACTIVE_SHIFT gap is skipped here too (same
        reasoning as the reconciliation service) -- it's still covered by
        the 12h LONG_OPEN_SESSION anomaly below regardless."""
        from mesflow.core.time_policy import utc_now
        from datetime import timedelta
        now=utc_now();grace=timedelta(minutes=settings.session_past_shift_end_grace_minutes)
        rows=fetch_all("SELECT id,started_at FROM work_sessions WHERE status='OPEN'")
        shifts=get_work_shifts()  # fetched ONCE, see resolve_shift_window_for_datetime()'s own docstring on why
        ids=set()
        for row in rows:
            window=resolve_shift_window_for_datetime(row['started_at'],shifts)
            if window is None: continue
            _shift,_start,end=window
            if now>=end+grace: ids.add(row['id'])
        return ids

    def detected_conditions(self)->list[dict[str,Any]]:
        past_shift_end_ids=self._session_past_shift_end_ids()
        rows=fetch_all("""WITH flags AS (
          SELECT ws.id session_id,'LONG_OPEN_SESSION' exception_type,'HIGH' severity,
            'Session mở quá lâu' title,'Session đã mở quá 12 giờ và cần được kiểm tra.' message,
            'Kiểm tra Session và xác nhận trạng thái.' recommended_action
          FROM work_sessions ws WHERE ws.status='OPEN' AND ws.started_at<CURRENT_TIMESTAMP-INTERVAL '12 hours'
          UNION ALL SELECT ws.id,'ZERO_QUANTITY_LONG','MEDIUM','Sản lượng bằng 0',
            'Session kéo dài trên 4 giờ nhưng được đóng với sản lượng bằng 0.','Đối chiếu sản lượng và xác nhận hoặc sửa Session.'
          FROM work_sessions ws WHERE ws.status='CLOSED' AND ws.ended_at-ws.started_at>INTERVAL '4 hours'
            AND COALESCE(ws.good_qty,0)+COALESCE(ws.defect_qty,0)=0
          UNION ALL SELECT ws.id,'MISSING_STATION','LOW','Thiếu thông tin trạm',
            'Session không ghi nhận trạm hoặc kiosk.','Xác nhận nguồn thao tác của Session.'
          FROM work_sessions ws WHERE ws.station_id IS NULL AND COALESCE(ws.device_uuid,'')=''
          UNION ALL SELECT ws.id,'INVALID_DURATION','CRITICAL','Thời gian Session không hợp lệ',
            'Giờ kết thúc trước giờ bắt đầu.','Mở Session, kiểm tra bằng chứng và sửa qua quy trình hiện có.'
          FROM work_sessions ws WHERE ws.ended_at IS NOT NULL AND ws.ended_at<ws.started_at
          UNION ALL SELECT ws.id,'OPERATION_COMPLETED_SESSION_OPEN','HIGH','Operation đã hoàn tất nhưng Session còn mở',
            'Operation đã hoàn tất trong khi Session liên quan vẫn OPEN.','Kiểm tra Session trước khi xác nhận trạng thái Operation.'
          FROM work_sessions ws JOIN operations ox ON ox.id=ws.operation_id WHERE ws.status='OPEN' AND ox.status='COMPLETED'
          UNION ALL SELECT a.id,'EMPLOYEE_SESSION_CONFLICT','CRITICAL','Nhân viên có Session xung đột',
            'Nhân viên có hai Session chồng thời gian.','Kiểm tra cả hai Session và bằng chứng kiosk.'
          FROM work_sessions a JOIN work_sessions b ON b.employee_id=a.employee_id AND b.id<a.id
            AND tstzrange(a.started_at,COALESCE(a.ended_at,'infinity'::timestamptz),'[)') && tstzrange(b.started_at,COALESCE(b.ended_at,'infinity'::timestamptz),'[)')
          UNION ALL SELECT ws.id,'SESSION_PAST_SHIFT_END','MEDIUM','Session quá giờ kết thúc ca',
            'Session vẫn còn OPEN sau khi ca làm việc đã kết thúc. Hệ thống sẽ tự động đóng ca sau ít phút nếu không có thao tác thủ công.',
            'Kết thúc Session thủ công, hoặc chờ hệ thống tự động đóng ca.'
          FROM work_sessions ws WHERE ws.status='OPEN' AND ws.id=ANY(%s)
        ) SELECT f.*,ws.employee_id,ws.operation_id,o.production_order_id,o.part_id,
          ws.started_at,ws.ended_at,ws.status session_status,ws.good_qty,ws.defect_qty,COALESCE(ws.rework_qty,0) rework_qty,
          e.employee_no employee_code,e.name employee_name,po.code po_code,p.code part_code,
          o.code operation_code,o.name operation_name,s.code station_code,
          GREATEST(EXTRACT(EPOCH FROM(COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds,
          f.exception_type||':SESSION:'||ws.id::text fingerprint
        FROM flags f JOIN work_sessions ws ON ws.id=f.session_id JOIN employees e ON e.id=ws.employee_id
        JOIN operations o ON o.id=ws.operation_id JOIN production_orders po ON po.id=o.production_order_id
        JOIN parts p ON p.id=o.part_id LEFT JOIN stations s ON s.id=ws.station_id""",
        (list(past_shift_end_ids),))
        return rows

    @staticmethod
    def _history(cur,exception_id,action,previous,new,actor_id=None,actor='',reason='',correlation_id='',metadata=None):
        cur.execute("""INSERT INTO exception_history(exception_id,action,previous_status,new_status,actor_id,actor_username,reason,metadata_json,correlation_id)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
          (exception_id,action,previous,new,actor_id,actor or '',reason or '',json.dumps(metadata or {},ensure_ascii=False,default=str),correlation_id or ''))
        return cur.fetchone()

    def reconcile(self,conditions:list[dict[str,Any]],correlation_id='')->list[dict[str,Any]]:
        # Deadlock hazard found live under concurrent load (Phase 5 added a
        # 6th UNION branch to detected_conditions(), which raised the row
        # count enough to make this pre-existing hazard reproduce reliably
        # in tests/integration/test_v67_exception_center.py's 5-concurrent-
        # requests test): two overlapping reconcile() calls could acquire
        # per-fingerprint FOR UPDATE locks in DIFFERENT orders (Python dict
        # iteration order == `conditions`' own UNION ALL order, which
        # Postgres does not guarantee is identical across two concurrent
        # executions), then both reach the bulk `condition_active=TRUE FOR
        # UPDATE` scan below and deadlock waiting on each other's rows.
        # Sorting by fingerprint (a stable string, same set of fingerprints
        # for the same underlying data regardless of scan order) makes
        # every concurrent caller take these locks in the SAME order --
        # the standard fix for a lock-ordering deadlock.
        current={x['fingerprint']:x for x in conditions}; created=[]
        with transaction() as conn:
          with conn.cursor() as cur:
            for fp in sorted(current):
                item=current[fp]
                cur.execute("SELECT * FROM exception_records WHERE fingerprint=%s ORDER BY occurrence_no DESC,id DESC LIMIT 1 FOR UPDATE",(fp,))
                prior=cur.fetchone()
                if prior and (prior['status'] in ACTIVE or prior['condition_active']):
                    cur.execute("UPDATE exception_records SET condition_active=TRUE,updated_at=CURRENT_TIMESTAMP,metadata_json=%s WHERE id=%s",
                                (json.dumps(item,ensure_ascii=False,default=str),prior['id']))
                    continue
                occurrence=(prior['occurrence_no']+1) if prior else 1
                cur.execute("""INSERT INTO exception_records(exception_type,severity,entity_type,entity_id,employee_id,production_order_id,part_id,operation_id,session_id,title,message,recommended_action,fingerprint,metadata_json,occurrence_no)
                  VALUES(%s,%s,'SESSION',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                  ON CONFLICT(fingerprint) WHERE status IN ('OPEN','ACKNOWLEDGED') DO NOTHING RETURNING *""",
                  (item['exception_type'],item['severity'],item['session_id'],item['employee_id'],item['production_order_id'],item['part_id'],item['operation_id'],item['session_id'],item['title'],item['message'],item['recommended_action'],fp,json.dumps(item,ensure_ascii=False,default=str),occurrence))
                row=cur.fetchone()
                if row:
                    self._history(cur,row['id'],'DETECTED',None,'OPEN',correlation_id=correlation_id,metadata={'fingerprint':fp});created.append(row)
            # ORDER BY id: same deterministic-lock-order reasoning as above.
            cur.execute("SELECT * FROM exception_records WHERE condition_active=TRUE ORDER BY id FOR UPDATE")
            for row in cur.fetchall():
                if row['fingerprint'] in current: continue
                if row['status'] not in ACTIVE:
                    # A human decision is immutable, but the condition edge is
                    # tracked so a later false->true transition becomes a real
                    # new incident rather than resurrecting the old decision.
                    cur.execute("UPDATE exception_records SET condition_active=FALSE,updated_at=CURRENT_TIMESTAMP WHERE id=%s",(row['id'],))
                    continue
                reason='SESSION_ALREADY_CLOSED' if row['exception_type'] in ('LONG_OPEN_SESSION','OPERATION_COMPLETED_SESSION_OPEN','SESSION_PAST_SHIFT_END') else 'CONDITION_NO_LONGER_TRUE'
                can_auto=row['severity'] in ('LOW','MEDIUM') or reason=='SESSION_ALREADY_CLOSED'
                if can_auto:
                    cur.execute("""UPDATE exception_records SET status='AUTO_IGNORED',condition_active=FALSE,ignored_at=CURRENT_TIMESTAMP,
                      auto_ignored_at=CURRENT_TIMESTAMP,auto_ignore_reason=%s,row_version=row_version+1,updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING *""",(reason,row['id']))
                    changed=cur.fetchone(); self._history(cur,row['id'],'AUTO_IGNORED',row['status'],'AUTO_IGNORED',reason=reason,correlation_id=correlation_id)
                    record_audit(cur,action='EXCEPTION_AUTO_IGNORED',entity_type='exception',entity_id=str(row['id']),correlation_id=correlation_id,before=row,after=changed,metadata={'reason':reason},source='exception-reconciliation')
                else:
                    cur.execute("UPDATE exception_records SET condition_active=FALSE,updated_at=CURRENT_TIMESTAMP WHERE id=%s",(row['id'],))
        return created

    def list(self,*,statuses=None,severity='',exception_type='',po_id=None,employee_id=None,operation_id=None,date_from='',date_to='',sort='severity',page=1,page_size=50):
        where=[];params=[]
        if statuses: where.append('x.status=ANY(%s)');params.append(list(statuses))
        if severity: where.append('x.severity=%s');params.append(severity)
        if exception_type: where.append('x.exception_type=%s');params.append(exception_type)
        for col,val in [('production_order_id',po_id),('employee_id',employee_id),('operation_id',operation_id)]:
            if val: where.append(f'x.{col}=%s');params.append(int(val))
        if date_from: where.append('x.detected_at>=%s::date');params.append(date_from)
        if date_to: where.append("x.detected_at<%s::date+INTERVAL '1 day'");params.append(date_to)
        clause=' WHERE '+' AND '.join(where) if where else ''
        order={'newest':'x.detected_at DESC','oldest':'x.detected_at ASC','longest':'x.detected_at ASC','severity':"CASE x.severity WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,x.detected_at ASC"}.get(sort,"x.detected_at DESC")
        count=fetch_one('SELECT COUNT(*) total FROM exception_records x'+clause,params)['total']
        params.extend([page_size,(page-1)*page_size])
        items=fetch_all(f"""SELECT x.*,e.employee_no employee_code,e.name employee_name,po.code po_code,p.code part_code,p.name part_name,
          o.code operation_code,o.name operation_name,ws.status session_status,ws.started_at,ws.ended_at,ws.good_qty,ws.defect_qty,COALESCE(ws.rework_qty,0) rework_qty,
          GREATEST(EXTRACT(EPOCH FROM(COALESCE(ws.ended_at,CURRENT_TIMESTAMP)-ws.started_at)),0)::bigint duration_seconds
          FROM exception_records x LEFT JOIN employees e ON e.id=x.employee_id LEFT JOIN production_orders po ON po.id=x.production_order_id
          LEFT JOIN parts p ON p.id=x.part_id LEFT JOIN operations o ON o.id=x.operation_id LEFT JOIN work_sessions ws ON ws.id=x.session_id
          {clause} ORDER BY {order},x.id DESC LIMIT %s OFFSET %s""",params)
        return {'items':items,'total':count,'page':page,'page_size':page_size}

    def get(self,exception_id:int):
        row=fetch_one("SELECT * FROM exception_records WHERE id=%s",(exception_id,))
        if not row: raise NotFoundError(f'Không tìm thấy ngoại lệ #{exception_id}')
        return row

    def history(self,exception_id:int):
        self.get(exception_id)
        return fetch_all("SELECT * FROM exception_history WHERE exception_id=%s ORDER BY created_at,id",(exception_id,))

    def for_session(self,session_id:int):
        return fetch_all("""SELECT x.*,e.employee_no employee_code,e.name employee_name,po.code po_code,p.code part_code,p.name part_name,
          o.code operation_code,o.name operation_name FROM exception_records x
          LEFT JOIN employees e ON e.id=x.employee_id LEFT JOIN production_orders po ON po.id=x.production_order_id
          LEFT JOIN parts p ON p.id=x.part_id LEFT JOIN operations o ON o.id=x.operation_id
          WHERE x.session_id=%s ORDER BY x.detected_at DESC,x.id DESC LIMIT 200""",(session_id,))

    def transition(self,exception_id:int,target:str,expected_version:int,actor_id:int|None,actor:str,reason:str,correlation_id:str):
        target=target.upper(); actions={'ACKNOWLEDGED':'ACKNOWLEDGED','RESOLVED':'RESOLVED','MANUAL_IGNORED':'IGNORED'}
        if target not in actions: raise ValueError('Trạng thái ngoại lệ không hợp lệ')
        with transaction() as conn:
          with conn.cursor() as cur:
            cur.execute('SELECT * FROM exception_records WHERE id=%s FOR UPDATE',(exception_id,));before=cur.fetchone()
            if not before: raise NotFoundError(f'Không tìm thấy ngoại lệ #{exception_id}')
            if before['row_version']!=expected_version: raise ConflictError('Ngoại lệ đã được người khác cập nhật. Vui lòng tải lại.')
            if before['status'] not in ACTIVE: raise ConflictError('Ngoại lệ đã được xử lý')
            if target=='ACKNOWLEDGED' and before['status']!='OPEN': raise ConflictError('Ngoại lệ đã được xác nhận')
            if target in ('RESOLVED','MANUAL_IGNORED') and before['severity'] in ('HIGH','CRITICAL') and not reason.strip():
                raise ValueError('Ngoại lệ HIGH/CRITICAL cần ghi lý do')
            cur.execute("""UPDATE exception_records SET status=%s,row_version=row_version+1,updated_at=CURRENT_TIMESTAMP,
              acknowledged_at=CASE WHEN %s='ACKNOWLEDGED' THEN CURRENT_TIMESTAMP ELSE acknowledged_at END,
              acknowledged_by=CASE WHEN %s='ACKNOWLEDGED' THEN %s ELSE acknowledged_by END,
              resolved_at=CASE WHEN %s='RESOLVED' THEN CURRENT_TIMESTAMP ELSE resolved_at END,
              ignored_at=CASE WHEN %s='MANUAL_IGNORED' THEN CURRENT_TIMESTAMP ELSE ignored_at END,
              resolved_by=CASE WHEN %s IN ('RESOLVED','MANUAL_IGNORED') THEN %s ELSE resolved_by END
              WHERE id=%s RETURNING *""",(target,target,target,actor_id,target,target,target,actor_id,exception_id))
            after=cur.fetchone();action=actions[target]
            self._history(cur,exception_id,action,before['status'],target,actor_id,actor,reason,correlation_id)
            record_audit(cur,action='EXCEPTION_'+action,entity_type='exception',entity_id=str(exception_id),actor_username=actor,actor_user_id=actor_id,
                         correlation_id=correlation_id,before=before,after=after,metadata={'reason':reason,'session_id':before.get('session_id')},source='exception-center')
            return after
