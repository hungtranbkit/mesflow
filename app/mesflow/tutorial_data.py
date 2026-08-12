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

            result={
                "ok":True,"prefix":"TUT39","production_order":PO_CODE,"template":TEMPLATE_CODE,
                "employees":len(employees),"stations":len(stations),"operations":len(operations),
                "sessions":len(sessions),"kiosk":DEVICE,
                "scenarios":[
                    "normal_good_defect_rework","zero_qty_long","missing_station","overlap",
                    "invalid_time","open_too_long","exception_in_progress","exception_resolved",
                    "exception_ignored","kiosk_degraded","offline_queue","offline_conflict",
                    "qc_completed","qc_open","session_adjustment","penalty","system_error_log"
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
