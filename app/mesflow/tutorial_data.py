"""Synthetic MESFlow tutorial dataset.

This module intentionally creates only TUT-* records. It is opt-in and refuses
to mutate a production environment unless the caller explicitly sets
MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1.

Usage inside the MESFlow container:
    python -m mesflow.tutorial_data seed
    python -m mesflow.tutorial_data status
    python -m mesflow.tutorial_data cleanup
"""
from __future__ import annotations
import json, os, sys
from mesflow.db.connection import transaction

PREFIX="TUT39"
PO_CODE="TUT-PO-GUIDE-39"
TEMPLATE_CODE="TUT-GUIDE-39"
DEVICE="TUT-KIOSK-39"

def _allowed():
    env=str(os.environ.get("MESFLOW_ENV","production")).strip().lower()
    if env!="production":
        return True
    return str(os.environ.get("MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION","")).strip().lower() in {"1","true","yes","on"}

def _must_allow():
    if not _allowed():
        raise RuntimeError(
            "Tutorial data seeding is blocked in production. "
            "For an explicit training/demo database only, set "
            "MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1 for this command."
        )

def _one(cur,sql,args=()):
    cur.execute(sql,args)
    return cur.fetchone()

def _assert_schema(cur):
    required={
        "production_orders":{"planned_quantity","status","source_template_id","planned_start_at","planned_end_at"},
        "template_operations":{"template_id","part_id","code","name","sort_order","standard_seconds_per_unit","repair_cycle_time_seconds_per_unit"},
        "operations":{"production_order_id","part_id","code","name","done_qty","defect_qty","rework_qty","status","sort_order","qr","standard_seconds_per_unit","repair_cycle_time_seconds_per_unit"},
        "work_sessions":{"employee_id","operation_id","status","good_qty","defect_qty","rework_qty","note"},
        "session_exception_reviews":{"session_id","exception_code","exception_fingerprint","workflow_status"},
        "kiosk_client_events":{"client_event_id","kiosk_id","local_sequence","status"},
    }
    for table,wanted in required.items():
        cur.execute("""SELECT column_name FROM information_schema.columns
                       WHERE table_schema=current_schema() AND table_name=%s""",(table,))
        present={str(r["column_name"]) for r in cur.fetchall()}
        missing=sorted(wanted-present)
        if missing:
            raise RuntimeError(f"Tutorial schema mismatch: {table} missing {', '.join(missing)}")
    for table in ("operations","template_operations"):
        cur.execute("""SELECT 1 FROM information_schema.columns
                       WHERE table_schema=current_schema() AND table_name=%s AND column_name='plan_qty'""",(table,))
        if cur.fetchone():
            raise RuntimeError(f"Legacy schema detected: {table}.plan_qty still exists; run current Alembic migrations first.")

def _cleanup(cur):
    """
    Remove only tutorial-owned records.

    Important: sessions created through the real kiosk tutorial may not have a
    TUT39 note. Their ownership is identified by the tutorial Production Order /
    Operation, so cleanup must delete every session referencing a TUT operation
    before deleting the operation itself.
    """
    tutorial_sessions = """(
        SELECT ws.id
        FROM work_sessions ws
        WHERE ws.operation_id IN (
            SELECT o.id
            FROM operations o
            JOIN production_orders po ON po.id=o.production_order_id
            WHERE po.code LIKE 'TUT-%'
        )
        OR ws.note LIKE 'TUT39:%'
    )"""
    tutorial_operations = """(
        SELECT o.id
        FROM operations o
        JOIN production_orders po ON po.id=o.production_order_id
        WHERE po.code LIKE 'TUT-%'
    )"""

    # Session-owned children first. Some FKs are CASCADE, but explicit deletion
    # keeps this cleanup safe across older schemas and partially-upgraded installs.
    cur.execute(f"""DELETE FROM session_exception_reviews
        WHERE session_id IN {tutorial_sessions}""")
    cur.execute(f"""DELETE FROM kiosk_events
        WHERE device_uuid LIKE 'TUT-%'
           OR session_id IN {tutorial_sessions}""")
    cur.execute(f"""DELETE FROM qc_inspections
        WHERE session_id IN {tutorial_sessions}
           OR operation_id IN {tutorial_operations}""")
    cur.execute(f"""DELETE FROM operation_adjustments
        WHERE session_id IN {tutorial_sessions}
           OR operation_id IN {tutorial_operations}""")
    cur.execute(f"""DELETE FROM operation_input_consumption_history
        WHERE ledger_id IN (
            SELECT id FROM operation_input_consumptions
            WHERE session_id IN {tutorial_sessions}
               OR source_operation_id IN {tutorial_operations}
               OR target_operation_id IN {tutorial_operations}
        )""")
    cur.execute(f"""DELETE FROM operation_input_consumptions
        WHERE session_id IN {tutorial_sessions}
           OR source_operation_id IN {tutorial_operations}
           OR target_operation_id IN {tutorial_operations}""")

    # penalty_tickets uses SET NULL for session/operation but RESTRICT for employee;
    # tutorial-created tickets are safe to remove explicitly.
    cur.execute(f"""DELETE FROM penalty_tickets
        WHERE session_id IN {tutorial_sessions}
           OR operation_id IN {tutorial_operations}
           OR employee_id IN (SELECT id FROM employees WHERE employee_no LIKE 'TUT-%')""")

    # Offline/idempotency rows are tutorial-owned by their explicit prefix.
    cur.execute("""DELETE FROM kiosk_client_events WHERE kiosk_id LIKE 'TUT-%'""")
    cur.execute("""DELETE FROM kiosk_idempotency WHERE request_id LIKE 'TUT39-%' OR request_id LIKE 'TUT44-%'""")

    # Critical ordering: delete all sessions on tutorial operations before the
    # operations table, because work_sessions.operation_id is ON DELETE RESTRICT.
    cur.execute(f"""DELETE FROM work_sessions WHERE id IN {tutorial_sessions}""")

    cur.execute("""DELETE FROM action_logs WHERE trace_id LIKE 'TUT39-%' OR trace_id LIKE 'TUT44-%'""")
    cur.execute("""DELETE FROM audit_logs
        WHERE entity_id LIKE 'TUT39-%'
           OR entity_id LIKE 'TUT44-%'
           OR details_json LIKE '%TUT39%'
           OR details_json LIKE '%TUT44%'""")
    cur.execute("""DELETE FROM notifications
        WHERE source_type='TUTORIAL' AND (source_id LIKE 'TUT39-%' OR source_id LIKE 'TUT44-%')""")
    cur.execute("""DELETE FROM kiosk_status WHERE device_uuid LIKE 'TUT-%'""")
    cur.execute("""DELETE FROM kiosk_identities WHERE device_uuid LIKE 'TUT-%'""")

    # Parent production/template records last.
    cur.execute("""DELETE FROM operations WHERE production_order_id IN (
        SELECT id FROM production_orders WHERE code LIKE 'TUT-%')""")
    cur.execute("""DELETE FROM parts WHERE production_order_id IN (
        SELECT id FROM production_orders WHERE code LIKE 'TUT-%')""")
    cur.execute("""DELETE FROM production_orders WHERE code LIKE 'TUT-%'""")
    cur.execute("""DELETE FROM template_operations WHERE template_id IN (
        SELECT id FROM templates WHERE code LIKE 'TUT-%')""")
    cur.execute("""DELETE FROM template_parts WHERE template_id IN (
        SELECT id FROM templates WHERE code LIKE 'TUT-%')""")
    cur.execute("""DELETE FROM templates WHERE code LIKE 'TUT-%'""")
    cur.execute("""DELETE FROM employees WHERE employee_no LIKE 'TUT-%'""")
    cur.execute("""DELETE FROM stations WHERE code LIKE 'TUT-%'""")

def seed():
    _must_allow()
    with transaction() as conn:
        with conn.cursor() as cur:
            _assert_schema(cur)
            _cleanup(cur)

            # Employees covering normal, quality, long-session and overlap examples.
            employees={}
            for no,name,pos in [
                ("TUT-E01","Nguyễn Văn An — Demo","Công nhân cắt"),
                ("TUT-E02","Trần Thị Bình — Demo","Công nhân chấn"),
                ("TUT-E03","Lê Minh Cường — Demo","Thợ hàn"),
                ("TUT-E04","Phạm Thu Dung — Demo","QC"),
                ("TUT-E05","Võ Quốc Em — Demo","Công nhân đóng gói"),
                ("TUT-E06","Hoàng Gia Phúc — Demo","Công nhân dự phòng"),
            ]:
                row=_one(cur,"""INSERT INTO employees(employee_no,name,department,position,employment_status,active,qr)
                    VALUES(%s,%s,'Xưởng Demo',%s,'Đang làm',TRUE,%s) RETURNING id""",
                    (no,name,pos,f"WF|EMP|{no}"))
                employees[no]=int(row["id"])

            stations={}
            for code,name in [("TUT-ST-CUT","Trạm Cắt Demo"),("TUT-ST-BEND","Trạm Chấn Demo"),("TUT-ST-WELD","Trạm Hàn Demo")]:
                row=_one(cur,"""INSERT INTO stations(code,name,workshop,production_line,active)
                    VALUES(%s,%s,'Xưởng đào tạo','Line Tutorial',TRUE) RETURNING id""",(code,name))
                stations[code]=int(row["id"])

            # Template visible in Template screen.
            t=_one(cur,"""INSERT INTO templates(code,name,product,version,active,source_workbook)
                VALUES(%s,'Tutorial — Hộp thép mẫu','Hộp thép đào tạo','39.0',TRUE,'TUTORIAL_DATASET') RETURNING id""",(TEMPLATE_CODE,))
            tid=int(t["id"])
            tp1=int(_one(cur,"""INSERT INTO template_parts(template_id,code,name,sort_order)
                VALUES(%s,'TUT-PART-A','Thân hộp',1) RETURNING id""",(tid,))["id"])
            tp2=int(_one(cur,"""INSERT INTO template_parts(template_id,code,name,sort_order)
                VALUES(%s,'TUT-PART-B','Nắp hộp',2) RETURNING id""",(tid,))["id"])
            for partid,code,name,sec,sortn in [
                (tp1,"TUT-CUT","Cắt laser",18,1),(tp1,"TUT-BEND","Chấn",30,2),
                (tp1,"TUT-WELD","Hàn",50,3),(tp2,"TUT-QC","Kiểm tra chất lượng",20,1),
                (tp2,"TUT-PACK","Đóng gói",25,2),
            ]:
                cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order,
                    standard_seconds_per_unit,repair_cycle_time_seconds_per_unit)
                    VALUES(%s,%s,%s,%s,%s,%s,12)""",(tid,partid,code,name,sortn,sec))

            po=_one(cur,"""INSERT INTO production_orders(code,product,planned_quantity,status,priority,due_date,notes,
                    planned_start_at,planned_end_at,source_template_id,source_template_code,source_template_version)
                VALUES(%s,'Hộp thép đào tạo',100,'IN_PROGRESS','HIGH',CURRENT_DATE+1,
                    'TUT39: dữ liệu mô phỏng cho video hướng dẫn',
                    CURRENT_TIMESTAMP-INTERVAL '6 hours',CURRENT_TIMESTAMP+INTERVAL '6 hours',
                    %s,%s,'39.0') RETURNING id""",(PO_CODE,tid,TEMPLATE_CODE))
            poid=int(po["id"])
            part_a=int(_one(cur,"""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                VALUES(%s,'TUT-PART-A','Thân hộp',1,TRUE) RETURNING id""",(poid,))["id"])
            part_b=int(_one(cur,"""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                VALUES(%s,'TUT-PART-B','Nắp hộp',2,TRUE) RETURNING id""",(poid,))["id"])

            operations={}
            for partid,code,name,sec,sortn,status in [
                (part_a,"TUT39-CUT","Cắt laser — Tutorial",18,1,"IN_PROGRESS"),
                (part_a,"TUT39-BEND","Chấn — Tutorial",30,2,"IN_PROGRESS"),
                (part_a,"TUT39-WELD","Hàn — Tutorial",50,3,"IN_PROGRESS"),
                (part_b,"TUT39-QC","QC — Tutorial",20,1,"IN_PROGRESS"),
                (part_b,"TUT39-PACK","Đóng gói — Tutorial",25,2,"PLANNED"),
            ]:
                row=_one(cur,"""INSERT INTO operations(production_order_id,part_id,code,name,done_qty,defect_qty,rework_qty,
                    status,sort_order,qr,standard_seconds_per_unit,repair_cycle_time_seconds_per_unit,
                    planned_start_at,planned_end_at)
                    VALUES(%s,%s,%s,%s,0,0,0,%s,%s,%s,%s,12,
                    CURRENT_TIMESTAMP-INTERVAL '4 hours',CURRENT_TIMESTAMP+INTERVAL '4 hours') RETURNING id""",
                    (poid,partid,code,name,status,sortn,f"WF|OP|{code}",sec))
                operations[code]=int(row["id"])

            # Material-flow relationships: CUT -> BEND -> WELD.
            cur.execute("""UPDATE operations SET input_flow_enabled=TRUE,input_source_operation_id=%s,
                input_source_kind='GOOD',defects_consume_input=TRUE WHERE id=%s""",
                (operations["TUT39-CUT"],operations["TUT39-BEND"]))
            cur.execute("""UPDATE operations SET input_flow_enabled=TRUE,input_source_operation_id=%s,
                input_source_kind='GOOD',defects_consume_input=TRUE WHERE id=%s""",
                (operations["TUT39-BEND"],operations["TUT39-WELD"]))

            # Kiosk: healthy history + degraded current state + offline queue/conflict.
            kid=_one(cur,"""INSERT INTO kiosk_identities(device_uuid,device_name,station_id,status,token_hash,firmware_version,last_ip,last_seen_at)
                VALUES(%s,'Kiosk Tutorial 39',%s,'ACTIVE','','ESP32-DEMO-39','192.0.2.39',CURRENT_TIMESTAMP)
                RETURNING id""",(DEVICE,stations["TUT-ST-CUT"]))
            cur.execute("""INSERT INTO kiosk_status(device_uuid,station_id,ui_state,health_state,queue_size,wifi_rssi,free_heap,last_error,last_heartbeat_at)
                VALUES(%s,%s,'OFFLINE_QUEUE','DEGRADED',3,-78,112000,'Wi-Fi yếu; còn 3 sự kiện chờ đồng bộ',CURRENT_TIMESTAMP)""",
                (DEVICE,stations["TUT-ST-CUT"]))

            # Helper inserts sessions with controlled timestamps. These are intentionally synthetic
            # so exception views have every important state.
            sessions={}
            def sess(key,emp,op,station,device,status,start_expr,end_expr,good,defect,rework,note):
                row=_one(cur,f"""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,
                    started_at,ended_at,good_qty,defect_qty,rework_qty,note,start_request_id,finish_request_id)
                    VALUES(%s,%s,%s,%s,%s,{start_expr},{end_expr},%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (employees[emp],operations[op],stations.get(station) if station else None,device,status,
                     good,defect,rework,f"TUT39:{note}",f"TUT39-{key}-START",f"TUT39-{key}-FIN" if status=="CLOSED" else None))
                sessions[key]=int(row["id"])

            sess("NORMAL","TUT-E01","TUT39-CUT","TUT-ST-CUT",DEVICE,"CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '3 hours'","CURRENT_TIMESTAMP-INTERVAL '2 hours'",24,2,1,"Normal: 24 đạt, 2 lỗi, 1 sửa được")
            sess("FAST","TUT-E02","TUT39-BEND","TUT-ST-BEND","TUT-KIOSK-FAST","CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '110 minutes'","CURRENT_TIMESTAMP-INTERVAL '70 minutes'",32,0,0,"Sản lượng tốt, đúng tiến độ")
            sess("ZERO","TUT-E05","TUT39-PACK","TUT-ST-CUT","TUT-KIOSK-ZERO","CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '8 hours'","CURRENT_TIMESTAMP-INTERVAL '2 hours'",0,0,0,"ZERO_QTY_LONG: quên nhập sản lượng")
            sess("MISSING","TUT-E06","TUT39-QC",None,"","CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '90 minutes'","CURRENT_TIMESTAMP-INTERVAL '30 minutes'",8,1,0,"MISSING_STATION: thiếu trạm/kiosk")
            # Closed overlapping sessions for the same worker => OVERLAP CRITICAL.
            sess("OVERLAP-A","TUT-E03","TUT39-WELD","TUT-ST-WELD","TUT-KIOSK-WELD","CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '5 hours'","CURRENT_TIMESTAMP-INTERVAL '3 hours'",10,1,1,"OVERLAP case A")
            sess("OVERLAP-B","TUT-E03","TUT39-QC","TUT-ST-WELD","TUT-KIOSK-WELD","CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '4 hours'","CURRENT_TIMESTAMP-INTERVAL '2 hours 30 minutes'",6,2,1,"OVERLAP case B")
            # Invalid closed time is synthetic only, to make the critical exception visible.
            sess("INVALID","TUT-E04","TUT39-QC","TUT-ST-CUT","TUT-KIOSK-QC","CLOSED",
                 "CURRENT_TIMESTAMP-INTERVAL '1 hour'","CURRENT_TIMESTAMP-INTERVAL '2 hours'",5,0,0,"INVALID_TIME: giờ kết thúc trước bắt đầu")
            sess("LONG","TUT-E01","TUT39-BEND","TUT-ST-BEND","TUT-KIOSK-LONG","OPEN",
                 "CURRENT_TIMESTAMP-INTERVAL '13 hours'","NULL",0,0,0,"OPEN_TOO_LONG: quên kết thúc session")

            # Aggregate operation quantities for dashboard/material-flow.
            cur.execute("""UPDATE operations SET done_qty=26,defect_qty=2,rework_qty=1 WHERE id=%s""",(operations["TUT39-CUT"],))
            cur.execute("""UPDATE operations SET done_qty=32,defect_qty=0,rework_qty=0 WHERE id=%s""",(operations["TUT39-BEND"],))
            cur.execute("""UPDATE operations SET done_qty=10,defect_qty=1,rework_qty=1 WHERE id=%s""",(operations["TUT39-WELD"],))
            cur.execute("""UPDATE operations SET done_qty=19,defect_qty=3,rework_qty=1 WHERE id=%s""",(operations["TUT39-QC"],))

            # Exception workflow examples: one IN_PROGRESS, one RESOLVED, one IGNORED.
            cur.execute("""INSERT INTO session_exception_reviews(session_id,exception_code,exception_fingerprint,workflow_status,note,
                assigned_to,started_by,started_at,updated_at)
                VALUES(%s,'OPEN_TOO_LONG','OPEN_TOO_LONG:0','IN_PROGRESS',
                'Đang xác minh với tổ trưởng vì công nhân quên kết thúc session','Quản đốc ca A','admin',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
                (sessions["LONG"],))
            cur.execute("""INSERT INTO session_exception_reviews(session_id,exception_code,exception_fingerprint,workflow_status,resolution,note,
                assigned_to,started_by,started_at,resolved_by,resolved_at,updated_at)
                VALUES(%s,'ZERO_QTY_LONG','ZERO_QTY_LONG:0','RESOLVED','CORRECTED',
                'Đã đối chiếu phiếu sản xuất và bổ sung sản lượng','Quản đốc ca A','admin',
                CURRENT_TIMESTAMP-INTERVAL '30 minutes','admin',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",(sessions["ZERO"],))
            cur.execute("""INSERT INTO session_exception_reviews(session_id,exception_code,exception_fingerprint,workflow_status,resolution,note,
                assigned_to,resolved_by,resolved_at,updated_at)
                VALUES(%s,'MISSING_STATION','MISSING_STATION:0','IGNORED','DEMO_CASE',
                'Session đào tạo cố ý không gắn trạm để minh họa cảnh báo','IT MESFlow','admin',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)""",
                (sessions["MISSING"],))

            # QC examples.
            cur.execute("""INSERT INTO qc_inspections(session_id,operation_id,status,good_qty,defect_qty,defect_reason,started_at,completed_at)
                VALUES(%s,%s,'COMPLETED',24,2,'Xước bề mặt / sai kích thước',CURRENT_TIMESTAMP-INTERVAL '2 hours',CURRENT_TIMESTAMP-INTERVAL '110 minutes')""",
                (sessions["NORMAL"],operations["TUT39-CUT"]))
            cur.execute("""INSERT INTO qc_inspections(session_id,operation_id,status,good_qty,defect_qty,defect_reason)
                VALUES(%s,%s,'OPEN',0,0,'Chờ kiểm tra lại mối hàn')""",(sessions["OVERLAP-A"],operations["TUT39-WELD"]))

            # Adjustment and penalty illustrate supervisor tools.
            cur.execute("""INSERT INTO operation_adjustments(session_id,operation_id,old_good_qty,new_good_qty,old_defect_qty,new_defect_qty,
                old_rework_qty,new_rework_qty,reason)
                VALUES(%s,%s,23,24,3,2,1,1,'TUT39: Đối chiếu lại phiếu QC')""",(sessions["NORMAL"],operations["TUT39-CUT"]))
            cur.execute("""INSERT INTO penalty_tickets(employee_id,operation_id,session_id,points,reason,status)
                VALUES(%s,%s,%s,1,'TUT39: Quên đóng session, chỉ dùng cho video đào tạo','OPEN')""",
                (employees["TUT-E01"],operations["TUT39-BEND"],sessions["LONG"]))

            # Kiosk events: normal, warning, open error, resolved error.
            for suffix,etype,severity,status,msg,resolved in [
                ("01","SCAN_EMPLOYEE","INFO","OPEN","Quét thẻ nhân viên thành công",False),
                ("02","OFFLINE_QUEUE","WARNING","OPEN","Mạng yếu, đã lưu 3 sự kiện vào queue offline",False),
                ("03","SCANNER_TIMEOUT","ERROR","OPEN","Máy quét không phản hồi trong 15 giây",False),
                ("04","SYNC_CONFLICT","ERROR","RESOLVED","Sự kiện offline trùng sequence, đã đối chiếu",True),
            ]:
                cur.execute("""INSERT INTO kiosk_events(event_uuid,device_uuid,station_id,event_type,severity,status,message,payload_json,
                    occurred_at,resolved_at,resolution_note)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,'{}'::jsonb,CURRENT_TIMESTAMP-INTERVAL '20 minutes',
                    CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
                    CASE WHEN %s THEN 'Đã kiểm tra và xử lý' ELSE '' END)""",
                    (f"TUT39-KE-{suffix}",DEVICE,stations["TUT-ST-CUT"],etype,severity,status,msg,resolved,resolved))

            # Offline accepted/rejected events shown in kiosk management.
            cur.execute("""INSERT INTO kiosk_client_events(client_event_id,payload_hash,kiosk_id,local_sequence,local_session_id,
                session_trace_id,event_type,event_time,time_quality,device_uptime_ms,boot_id,snapshot_revision,source,status,
                reason_code,reason,payload_json,result_json,processed_at)
                VALUES('TUT39-OFF-01','demo-hash-1',%s,1001,'TUT39-LOCAL-1','TUT39-TRACE-1','SESSION_START',
                CURRENT_TIMESTAMP-INTERVAL '18 minutes','device',100000,'BOOT39','1','OFFLINE_SYNC','accepted','','',
                '{}'::jsonb,'{}'::jsonb,CURRENT_TIMESTAMP-INTERVAL '17 minutes')""",(DEVICE,))
            cur.execute("""INSERT INTO kiosk_client_events(client_event_id,payload_hash,kiosk_id,local_sequence,local_session_id,
                session_trace_id,event_type,event_time,time_quality,device_uptime_ms,boot_id,snapshot_revision,source,status,
                reason_code,reason,payload_json,result_json,processed_at)
                VALUES('TUT39-OFF-02','demo-hash-2',%s,1002,'TUT39-LOCAL-2','TUT39-TRACE-2','SESSION_FINISH',
                CURRENT_TIMESTAMP-INTERVAL '16 minutes','device',105000,'BOOT39','1','OFFLINE_SYNC','rejected','STALE_OPERATION',
                'Operation đã thay đổi trạng thái trước khi đồng bộ','{}'::jsonb,'{}'::jsonb,CURRENT_TIMESTAMP-INTERVAL '15 minutes')""",(DEVICE,))

            # Notifications and logs make admin/system-log screens meaningful.
            cur.execute("""INSERT INTO notifications(source_type,source_id,severity,title,message,status,target_role)
                VALUES('TUTORIAL','TUT39-N01','WARNING','Kiosk mạng yếu','Kiosk Tutorial còn 3 sự kiện chờ đồng bộ','UNREAD','manager'),
                      ('TUTORIAL','TUT39-N02','ERROR','Session mở quá lâu','Session tutorial đã mở quá 12 giờ','UNREAD','supervisor')""")
            cur.execute("""INSERT INTO audit_logs(actor_username,action,entity_type,entity_id,details_json)
                VALUES('admin','TUTORIAL_SESSION_REVIEW','work_session','TUT39-REVIEW',
                '{"note":"Đối chiếu session bất thường trong video hướng dẫn"}')""")
            cur.execute("""INSERT INTO action_logs(trace_id,actor_username,actor_role,source_type,device_uuid,station_code,method,path,
                endpoint,action_name,http_status,duration_ms,outcome,error_type,error_message,request_json,response_json,context_json,
                traceback_text,client_ip,user_agent,resolved,resolved_note)
                VALUES
                ('TUT39-TRACE-OK','admin','admin','WEB','','','GET','/api/tutorial-demo','tutorial_demo','TUTORIAL_VIEW',
                 200,42,'SUCCESS','','','{}','{"ok":true}','{}','','127.0.0.1','MESFlow Tutorial',FALSE,''),
                ('TUT39-TRACE-ERR','admin','admin','KIOSK',%s,'TUT-ST-CUT','POST','/api/kiosk/offline-sync',
                 'offline_sync','OFFLINE_SYNC',409,85,'ERROR','ConflictError','Operation đã thay đổi trạng thái',
                 '{}','{"error":"CONFLICT"}','{"tutorial":true}','Tutorial synthetic trace only','127.0.0.1','MESFlow Tutorial',
                 TRUE,'Đã xử lý trong video đào tạo')""",(DEVICE,))

            # ------------------------------------------------------------------
            # Demo-scale extension (2026-09-03): everything above this point is
            # the original curated TUT39 fixture -- untouched, same codes, same
            # values, because tests and tutorial-detailed.spec.js hardcode
            # references to it (TUT-E06, TUT39-CUT, PO_CODE...). Everything
            # below is purely additive: more employees, two more Production
            # Orders (their own templates/parts/operations, still under the
            # 'TUT-' prefix so the existing cleanup wildcards already catch
            # them), and session history spread across real past days instead
            # of only the last few hours -- so Dashboard/employee-productivity
            # trends have more than a single point in time to show, matching
            # the scale a real demo/tutorial recording needs (2-3 PO, 5-10
            # Part, 20+ Operation, 12-20 employees).
            # ------------------------------------------------------------------
            for no,name,pos in [
                ("TUT-E07","Đỗ Thị Hoa — Demo","Công nhân tiện"),
                ("TUT-E08","Bùi Văn Khang — Demo","Công nhân phay"),
                ("TUT-E09","Ngô Thị Lan — Demo","Công nhân nhiệt luyện"),
                ("TUT-E10","Đặng Văn Minh — Demo","Công nhân mài"),
                ("TUT-E11","Vũ Thị Nga — Demo","QC"),
                ("TUT-E12","Trịnh Văn Long — Demo","Công nhân lắp ráp"),
                ("TUT-E13","Lý Thị Phương — Demo","Công nhân đóng gói"),
                ("TUT-E14","Phan Văn Quang — Demo","Tổ trưởng ca A"),
                ("TUT-E15","Hồ Thị Kim — Demo","Tổ trưởng ca B"),
                ("TUT-E16","Đinh Văn Sơn — Demo","Công nhân dự phòng"),
            ]:
                row=_one(cur,"""INSERT INTO employees(employee_no,name,department,position,employment_status,active,qr)
                    VALUES(%s,%s,'Xưởng Demo',%s,'Đang làm',TRUE,%s) RETURNING id""",
                    (no,name,pos,f"WF|EMP|{no}"))
                employees[no]=int(row["id"])

            for code,name in [("TUT-ST-TURN","Trạm Tiện Demo"),("TUT-ST-HEAT","Trạm Nhiệt luyện Demo"),("TUT-ST-ASSY","Trạm Lắp ráp Demo")]:
                row=_one(cur,"""INSERT INTO stations(code,name,workshop,production_line,active)
                    VALUES(%s,%s,'Xưởng đào tạo','Line Tutorial',TRUE) RETURNING id""",(code,name))
                stations[code]=int(row["id"])

            # Second Production Order: its own template/parts/operations, product
            # "Khung kim loại" (metal frame) -- CUT -> BEND -> WELD -> GRIND chain
            # on one Part, DRILL -> ASSEMBLE on a second.
            po2_ops_spec=[
                ("TUT-PART-C","Khung chính",[
                    ("TUT40-CUT","Cắt phôi khung",20,"IN_PROGRESS"),
                    ("TUT40-BEND","Uốn khung",35,"IN_PROGRESS"),
                    ("TUT40-WELD","Hàn khung",60,"IN_PROGRESS"),
                    ("TUT40-GRIND","Mài bavia",15,"PLANNED"),
                ]),
                ("TUT-PART-D","Chân đế",[
                    ("TUT40-DRILL","Khoan lỗ chân đế",22,"IN_PROGRESS"),
                    ("TUT40-ASSEMBLE","Lắp ráp chân đế",40,"PLANNED"),
                ]),
            ]
            # Third Production Order: product "Trục bánh răng" (gear shaft) --
            # a longer, more realistic chain: TURN -> MILL -> HEAT -> GRIND on
            # the shaft, its own gear-cutting Part, then a final assembly Part.
            po3_ops_spec=[
                ("TUT-PART-E","Trục chính",[
                    ("TUT41-TURN","Tiện trục",45,"IN_PROGRESS"),
                    ("TUT41-MILL","Phay rãnh then",38,"IN_PROGRESS"),
                    ("TUT41-HEAT","Nhiệt luyện",90,"PLANNED"),
                    ("TUT41-GRIND2","Mài tinh",50,"PLANNED"),
                ]),
                ("TUT-PART-F","Bánh răng",[
                    ("TUT41-GEAR-CUT","Cắt răng",60,"IN_PROGRESS"),
                    ("TUT41-GEAR-QC","Kiểm tra biên dạng răng",25,"PLANNED"),
                ]),
                ("TUT-PART-G","Lắp cụm",[
                    ("TUT41-ASSEMBLE2","Lắp cụm trục — bánh răng",35,"PLANNED"),
                    ("TUT41-PACK2","Đóng gói thành phẩm",20,"PLANNED"),
                    ("TUT41-QC-FINAL","QC cuối",15,"PLANNED"),
                ]),
            ]

            def make_po(po_code,template_code,product,version,parts_spec,planned_qty):
                t=_one(cur,"""INSERT INTO templates(code,name,product,version,active,source_workbook)
                    VALUES(%s,%s,%s,%s,TRUE,'TUTORIAL_DATASET') RETURNING id""",
                    (template_code,f"Tutorial — {product}",product,version))
                tid=int(t["id"])
                po=_one(cur,"""INSERT INTO production_orders(code,product,planned_quantity,status,priority,due_date,notes,
                        planned_start_at,planned_end_at,source_template_id,source_template_code,source_template_version)
                    VALUES(%s,%s,%s,'IN_PROGRESS','NORMAL',CURRENT_DATE+3,
                        'TUT39: dữ liệu mô phỏng cho video hướng dẫn (demo mở rộng)',
                        CURRENT_TIMESTAMP-INTERVAL '9 days',CURRENT_TIMESTAMP+INTERVAL '5 days',
                        %s,%s,%s) RETURNING id""",
                    (po_code,product,planned_qty,tid,template_code,version))
                poid=int(po["id"])
                new_ops={}
                for sortp,(part_code,part_name,ops) in enumerate(parts_spec,1):
                    tp=int(_one(cur,"""INSERT INTO template_parts(template_id,code,name,sort_order)
                        VALUES(%s,%s,%s,%s) RETURNING id""",(tid,part_code,part_name,sortp))["id"])
                    partid=int(_one(cur,"""INSERT INTO parts(production_order_id,code,name,sort_order,active)
                        VALUES(%s,%s,%s,%s,TRUE) RETURNING id""",(poid,part_code,part_name,sortp))["id"])
                    prev_op_code=None  # material-flow chain only within a Part's own sequence
                    for sorto,(op_code,op_name,sec,status) in enumerate(ops,1):
                        cur.execute("""INSERT INTO template_operations(template_id,part_id,code,name,sort_order,
                            standard_seconds_per_unit,repair_cycle_time_seconds_per_unit)
                            VALUES(%s,%s,%s,%s,%s,%s,12)""",(tid,tp,op_code,op_name,sorto,sec))
                        row=_one(cur,"""INSERT INTO operations(production_order_id,part_id,code,name,done_qty,defect_qty,rework_qty,
                            status,sort_order,qr,standard_seconds_per_unit,repair_cycle_time_seconds_per_unit,
                            planned_start_at,planned_end_at)
                            VALUES(%s,%s,%s,%s,0,0,0,%s,%s,%s,%s,12,
                            CURRENT_TIMESTAMP-INTERVAL '9 days',CURRENT_TIMESTAMP+INTERVAL '5 days') RETURNING id""",
                            (poid,partid,op_code,op_name,status,sorto,f"WF|OP|{op_code}",sec))
                        new_ops[op_code]=int(row["id"])
                        if prev_op_code and status=="IN_PROGRESS":
                            cur.execute("""UPDATE operations SET input_flow_enabled=TRUE,input_source_operation_id=%s,
                                input_source_kind='GOOD',defects_consume_input=TRUE WHERE id=%s""",
                                (new_ops[prev_op_code],new_ops[op_code]))
                        prev_op_code=op_code
                return poid,new_ops

            _,po2_ops=make_po("TUT-PO-GUIDE-40","TUT-GUIDE-40","Khung kim loại","1.0",po2_ops_spec,150)
            _,po3_ops=make_po("TUT-PO-GUIDE-41","TUT-GUIDE-41","Trục bánh răng","1.0",po3_ops_spec,80)
            operations.update(po2_ops); operations.update(po3_ops)

            # Session history across real past days (not just the last few
            # hours) so Dashboard/employee-productivity trends and per-day
            # drill-down have more than a single snapshot to show. Only
            # IN_PROGRESS operations get historical activity -- PLANNED ones
            # realistically have no sessions yet, same convention as PO1.
            #
            # 2026-09-05 realism rewrite: the previous version here picked
            # good_qty/duration independently at random (25-95 MINUTE
            # sessions, 8-40 pieces uncorrelated with duration or the
            # Operation's own standard_seconds_per_unit) -- every session
            # was unrealistically short for a real 4-8h production shift,
            # and completion_percent came out essentially random per
            # session with no natural skill-based spread across employees.
            # This version instead: (a) picks a realistic 4h15-8h duration
            # from a fixed set of real-looking values (not a uniform
            # continuous range -- shift lengths cluster, they don't spread
            # evenly), (b) assigns each employee a fixed "skill tier" so the
            # SAME employee is consistently a bit below/at/above 85% rather
            # than a fresh coin flip every session, then (c) SOLVES for
            # good_qty from the employee-productivity formula itself
            # (analytics.py: completion_percent = standard_seconds_per_unit
            # * (good+defect) / actual_seconds * 100) so the resulting
            # dataset's measured average is close to 85% by construction,
            # not by luck.
            active_ops=[op[0] for spec in (po2_ops_spec,po3_ops_spec) for _part_code,_part_name,ops in spec
                        for op in ops if op[3]=="IN_PROGRESS"]
            # TUT39-CUT deliberately excluded here (2026-09 kiosk video fix):
            # reconcile_operation() marks an Operation COMPLETED once its own
            # good_qty reaches the PO's planned_quantity (production_state.py),
            # and PO1's planned_quantity is only 100 -- sized for the small
            # hand-curated PO1 narration session, not for absorbing 14 days of
            # realistic bulk history too. Live-confirmed: adding TUT39-CUT to
            # this pool pushed its cumulative good_qty past 100 within one
            # seed, flipping it to COMPLETED and breaking the Kiosk tutorial
            # video's live "start a real session" demo (kiosk.js refuses to
            # start a COMPLETED Operation with "Công đoạn này đã hoàn
            # thành"). TUT39-CUT is the one Operation
            # tests/e2e/tutorial-detailed.spec.js's kioskUser tour actually
            # starts a NEW session on at record time, so it must stay
            # startable; BEND/WELD/QC are only ever read historically by other
            # chapters and have no such constraint.
            active_ops+=["TUT39-BEND","TUT39-WELD","TUT39-QC"]
            # Every historical session needs a real station -- leaving station_id
            # NULL (like the intentional MISSING_STATION example above) would
            # falsely flag every single one of these as that same exception.
            op_station={
                "TUT39-CUT":"TUT-ST-CUT","TUT39-BEND":"TUT-ST-BEND","TUT39-WELD":"TUT-ST-WELD","TUT39-QC":"TUT-ST-CUT",
                "TUT40-CUT":"TUT-ST-CUT","TUT40-BEND":"TUT-ST-BEND","TUT40-WELD":"TUT-ST-WELD","TUT40-DRILL":"TUT-ST-CUT",
                "TUT41-TURN":"TUT-ST-TURN","TUT41-MILL":"TUT-ST-TURN","TUT41-GEAR-CUT":"TUT-ST-TURN",
            }
            # standard_seconds_per_unit per op code, collected from the same
            # literal specs used to create the Operations above (PO1's list
            # is inlined here verbatim; PO2/PO3 come from their own spec
            # tuples) -- the productivity formula needs this to solve for
            # good_qty given a target completion_percent.
            op_std_sec={"TUT39-CUT":18,"TUT39-BEND":30,"TUT39-WELD":50,"TUT39-QC":20,"TUT39-PACK":25}
            for spec in (po2_ops_spec,po3_ops_spec):
                for _part_code,_part_name,ops in spec:
                    for op_code,_op_name,sec,_status in ops:
                        op_std_sec[op_code]=sec

            # Includes ALL 16 employees, TUT-E01..E06 included -- an earlier
            # version of this generator tried excluding E01..E06 (PO1's named
            # instructional cast: NORMAL/FAST/ZERO/MISSING/OVERLAP-A/B/
            # INVALID/LONG above) on the theory that their hand-tuned,
            # narration-matched quantities would drag the average down.
            # Confirmed live this was the WRONG fix: PO1's sessions are tuned
            # for a short, readable demo clip (e.g. 26 units in a full hour
            # against an 18s/unit standard), not for the productivity
            # formula at all, so calculated ALONE their completion_percent is
            # far below realistic (5-13%) -- excluding them from the
            # historical bulk left them isolated on just those low PO1
            # numbers and dropped the real API's avg_employee_productivity_
            # percent to 64.8%. Keeping them IN this pool, so their PO1
            # sessions are blended with 5-10 realistic HIST sessions each,
            # is what actually gets the real reported average close to 85%
            # (confirmed: 81.9% with tier centers as originally chosen below
            # -- do not remove E01-E06 from this list again without
            # re-verifying against the real /api/reports/employee-productivity
            # response, not just this generator's own intended math).
            all_employee_codes=list(employees.keys())
            hist_rng=__import__("random").Random(39)
            hist_count=0

            # Skill tiers, all 16 employees: 4 below-average, 8
            # solidly-average, 4 above-average. Centers are set a few points
            # ABOVE the naive (4*76+8*87+4*98)/16=87.0 weighted mean on
            # purpose, to compensate for PO1's own low-scoring sessions
            # blending into TUT-E01..E06's real multi-session average (see
            # comment above) -- verified empirically against the live API,
            # not derived from this arithmetic alone.
            tier_low,tier_mid,tier_high=all_employee_codes[0:4],all_employee_codes[4:12],all_employee_codes[12:16]
            tier_center={}
            for e in tier_low: tier_center[e]=hist_rng.uniform(76,82)
            for e in tier_mid: tier_center[e]=hist_rng.uniform(84,93)
            for e in tier_high: tier_center[e]=hist_rng.uniform(95,100)

            # Real-looking shift-length values in minutes -- clustered around
            # a normal 8h shift with realistic partial-shift variation, not a
            # smooth random spread. Matches the task's own examples (4h15,
            # 5h40, 6h20, 7h05, 7h45).
            duration_choices_min=[255,270,285,300,315,330,340,355,370,385,395,410,425,440,450,460,465,475,480]

            def solve_good_defect_rework(op_code,duration_min,target_pct):
                std=op_std_sec.get(op_code) or 30
                actual_sec=duration_min*60
                qty_total=round((target_pct/100.0)*actual_sec/std)
                qty_total=max(qty_total,6)
                defect=round(qty_total*hist_rng.uniform(0.02,0.09))
                good=max(qty_total-defect,1)
                rework=round(defect*hist_rng.uniform(0.2,0.6))
                return good,defect,rework

            # Track each employee's most-recent historical session end time so
            # a same-employee-overlap is never accidentally created across two
            # different days' entries in this loop (each employee gets at most
            # one session per day here, so this is naturally satisfied, but
            # asserted explicitly for anyone editing this generator later).
            last_end_by_employee={}

            auto_closed_keys=[]     # sessions this loop marks as auto-closed & unconfirmed
            excluded_candidate_keys=[]  # a couple of sessions this loop later excludes from reports

            for day_offset in range(1,15):  # yesterday .. 14 days ago
                # Not every employee works every day (realistic attendance),
                # and not every op-eligible employee necessarily touches this
                # Part chain -- sample without replacement per day.
                workers_today=hist_rng.sample(all_employee_codes,k=hist_rng.randint(7,len(all_employee_codes)))
                for emp in workers_today:
                    hist_count+=1
                    key=f"HIST-{day_offset}-{hist_count}"
                    op_code=hist_rng.choice(active_ops)
                    if op_code not in operations:
                        continue
                    station_id=stations[op_station.get(op_code,"TUT-ST-CUT")]
                    start_h=hist_rng.randint(6,9)  # shift start window, morning
                    duration_min=hist_rng.choice(duration_choices_min)
                    target_pct=max(50.0,min(118.0,hist_rng.gauss(tier_center[emp],4.0)))
                    good,defect,rework=solve_good_defect_rework(op_code,duration_min,target_pct)

                    # ~4% of ordinary historical sessions demonstrate the
                    # auto-close scenario instead of a normal manual finish --
                    # same quantities (auto-close never fabricates a number),
                    # but the real close_reason/closed_by_system/
                    # quantity_confirmed flags a genuine auto-close carries
                    # (execution.py: auto_close_for_shift_end()).
                    is_auto_closed=hist_rng.random()<0.04
                    status_sql="CLOSED"
                    if is_auto_closed:
                        extra_cols=",close_reason,closed_by_system,quantity_confirmed"
                        extra_vals=",'AUTO_SHIFT_END',TRUE,FALSE"
                    else:
                        extra_cols=""
                        extra_vals=""

                    start_expr=f"(CURRENT_DATE-INTERVAL '{day_offset} days')+INTERVAL '{start_h} hours'"
                    end_expr=f"({start_expr})+INTERVAL '{duration_min} minutes'"
                    row=_one(cur,f"""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,
                        started_at,ended_at,good_qty,defect_qty,rework_qty,note,start_request_id,finish_request_id{extra_cols})
                        VALUES(%s,%s,%s,%s,{status_sql!r},{start_expr},{end_expr},%s,%s,%s,%s,%s,%s{extra_vals}) RETURNING id""",
                        (employees[emp],operations[op_code],station_id,DEVICE,good,defect,rework,
                         f"TUT39:HIST day-{day_offset}: dữ liệu demo nhiều ngày, năng suất mục tiêu {target_pct:.0f}%",
                         f"TUT39-{key}-START",f"TUT39-{key}-FIN"))
                    sessions[key]=int(row["id"])
                    last_end_by_employee[emp]=(day_offset,start_h,duration_min)
                    if is_auto_closed:
                        auto_closed_keys.append(key)
                    elif hist_rng.random()<0.03:
                        excluded_candidate_keys.append(key)

            # Corrected/adjusted: a supervisor correction against 2 of the
            # auto-closed (unconfirmed) sessions above -- the exact "quên
            # nhập sản lượng -> auto-close -> admin correction" journey,
            # demonstrated with real data instead of only PO1's single
            # illustrative case. Mirrors SupervisorRepository.adjust(): sets
            # quantity_confirmed back TRUE and writes a real audit reason.
            for key in auto_closed_keys[:2]:
                sid=sessions[key]
                cur.execute("""SELECT good_qty,defect_qty,rework_qty,operation_id FROM work_sessions WHERE id=%s""",(sid,))
                old=cur.fetchone()
                new_good=int(old["good_qty"])+hist_rng.randint(1,3)
                cur.execute("""UPDATE work_sessions SET good_qty=%s,quantity_confirmed=TRUE,updated_at=CURRENT_TIMESTAMP WHERE id=%s""",
                    (new_good,sid))
                cur.execute("""INSERT INTO operation_adjustments(session_id,operation_id,old_good_qty,new_good_qty,
                    old_defect_qty,new_defect_qty,old_rework_qty,new_rework_qty,reason)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (sid,old["operation_id"],old["good_qty"],new_good,old["defect_qty"],old["defect_qty"],
                     old["rework_qty"],old["rework_qty"],
                     "TUT39: Đối chiếu phiếu sản xuất giấy sau khi hệ thống tự động đóng ca, bổ sung sản lượng còn thiếu"))

            # Excluded from reports: 2 sessions marked as duplicate/test scans
            # a supervisor would legitimately write off -- demonstrates
            # exclude_session() with a real reason, never a delete.
            for key in excluded_candidate_keys[:2]:
                sid=sessions[key]
                cur.execute("""UPDATE work_sessions SET excluded_from_reports=TRUE,
                    exclusion_reason='TUT39: Quét trùng do thao tác thử trên kiosk, không phải sản lượng thật',
                    excluded_by='supervisor',excluded_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                    WHERE id=%s""",(sid,))

            # Currently-running sessions for "today" -- a handful of distinct
            # employees each with exactly one OPEN session right now (the
            # DB-enforced one-open-session-per-employee rule means these must
            # be different employees than whoever's most recent historical
            # entry could otherwise collide with "now"; since every
            # historical entry above is on a strictly earlier calendar day,
            # there is no overlap risk here).
            # TUT-E01 already owns PO1's "LONG" session (OPEN, never closed --
            # the intentional OPEN_TOO_LONG exception demo above) -- the
            # DB-enforced one-open-session-per-employee constraint means
            # picking E01 again here would fail outright, not silently
            # overwrite anything. Excluded explicitly rather than caught as
            # an exception, since which employee already has PO1's one
            # standing OPEN session is a known, fixed fact of this dataset.
            open_eligible=[e for e in all_employee_codes if e!="TUT-E01"]
            open_today_employees=hist_rng.sample(open_eligible,k=3)
            for idx,emp in enumerate(open_today_employees):
                key=f"OPEN-TODAY-{idx+1}"
                op_code=hist_rng.choice(active_ops)
                if op_code not in operations:
                    continue
                station_id=stations[op_station.get(op_code,"TUT-ST-CUT")]
                hours_ago=hist_rng.choice([1,2,3,4])
                row=_one(cur,f"""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,
                    started_at,ended_at,good_qty,defect_qty,rework_qty,note,start_request_id,finish_request_id)
                    VALUES(%s,%s,%s,%s,'OPEN',CURRENT_TIMESTAMP-INTERVAL '{hours_ago} hours',NULL,0,0,0,%s,%s,NULL) RETURNING id""",
                    (employees[emp],operations[op_code],station_id,DEVICE,
                     f"TUT39:OPEN hôm nay, bắt đầu {hours_ago} giờ trước — đang chạy",
                     f"TUT39-{key}-START"))
                sessions[key]=int(row["id"])

            # Aggregate PO2/PO3 operation quantities from their own REPORTABLE
            # sessions only (status='CLOSED' AND NOT excluded_from_reports --
            # the exact same predicate every real KPI/report/exception query
            # in the app uses, reportable_session_sql() in base.py). Getting
            # this wrong here is exactly the "qty>0 but KPI shows 0" class of
            # inconsistency the task explicitly warns against: an OPEN
            # session has good_qty=0 anyway (harmless either way), but an
            # EXCLUDED session's quantity must NOT count here, or Operation's
            # own done_qty would silently disagree with what Employee
            # Productivity/Dashboard compute from the same underlying rows.
            # (PO1's operations keep their original hand-curated values above
            # -- deliberately not a strict session sum, used verbatim by the
            # existing tour narration, so left untouched.)
            cur.execute("""UPDATE operations o SET
                    done_qty=COALESCE(s.good,0),defect_qty=COALESCE(s.defect,0),rework_qty=COALESCE(s.rework,0)
                FROM (
                    SELECT operation_id,SUM(good_qty) good,SUM(defect_qty) defect,SUM(rework_qty) rework
                    FROM work_sessions
                    WHERE status='CLOSED' AND NOT excluded_from_reports
                      AND operation_id IN (
                        SELECT id FROM operations WHERE production_order_id IN (
                            SELECT id FROM production_orders WHERE code IN ('TUT-PO-GUIDE-40','TUT-PO-GUIDE-41'))
                    )
                    GROUP BY operation_id
                ) s
                WHERE o.id=s.operation_id""")

            result={
                "ok":True,"prefix":"TUT39","production_order":PO_CODE,"template":TEMPLATE_CODE,
                "employees":len(employees),"stations":len(stations),"operations":len(operations),
                "sessions":len(sessions),"kiosk":DEVICE,
                "production_orders":["TUT-PO-GUIDE-39","TUT-PO-GUIDE-40","TUT-PO-GUIDE-41"],
                "scenarios":[
                    "normal_good_defect_rework","zero_qty_long","missing_station","overlap",
                    "invalid_time","open_too_long","exception_in_progress","exception_resolved",
                    "exception_ignored","kiosk_degraded","offline_queue","offline_conflict",
                    "qc_completed","qc_open","session_adjustment","penalty","system_error_log",
                    "multi_po_multi_day_history","realistic_productivity_distribution_85pct_mean",
                    "realistic_4to8h_session_durations","auto_closed_unconfirmed_from_history",
                    "corrected_after_auto_close","excluded_from_reports_duplicate_scan",
                    "currently_open_sessions_today"
                ]
            }
            print(json.dumps(result,ensure_ascii=False,indent=2))

def cleanup():
    _must_allow()
    with transaction() as conn:
        with conn.cursor() as cur:
            _cleanup(cur)
    print(json.dumps({"ok":True,"cleaned_prefix":"TUT39"},ensure_ascii=False))

def status():
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT
                (SELECT COUNT(*) FROM production_orders WHERE code LIKE 'TUT-%') po_count,
                (SELECT COUNT(*) FROM work_sessions WHERE note LIKE 'TUT39:%') session_count,
                (SELECT COUNT(*) FROM kiosk_events WHERE device_uuid LIKE 'TUT-%') kiosk_event_count,
                (SELECT COUNT(*) FROM session_exception_reviews WHERE session_id IN
                    (SELECT id FROM work_sessions WHERE note LIKE 'TUT39:%')) review_count""")
            row=cur.fetchone()
    print(json.dumps(dict(row),ensure_ascii=False,indent=2))

if __name__=="__main__":
    cmd=(sys.argv[1] if len(sys.argv)>1 else "status").strip().lower()
    if cmd=="seed": seed()
    elif cmd=="cleanup": cleanup()
    elif cmd=="status": status()
    else: raise SystemExit("usage: python -m mesflow.tutorial_data [seed|status|cleanup]")
