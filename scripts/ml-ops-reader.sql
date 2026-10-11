-- Operator-reviewed provisioning only. NEVER run against production as a test.
-- psql -v ON_ERROR_STOP=1 -v ml_operation_ids='{101,102}' -v ml_reader=mesflow_ml_reader -f ...
-- The role must already exist with LOGIN, no elevated/inherited privileges and
-- its credential delivered out of band. Do not put passwords in this file/CLI.
-- The view embeds the approved scope; the reader cannot widen it via SQL.
BEGIN;
CREATE OR REPLACE VIEW public.mesflow_ml_ops_sessions WITH (security_barrier=true) AS
 SELECT ws.id AS session_id,ws.operation_id,ws.ended_at,
        EXTRACT(EPOCH FROM (ws.ended_at-ws.started_at))::double precision AS duration_seconds,
        ws.good_qty,ws.defect_qty
 FROM public.work_sessions ws
 JOIN public.operations o ON o.id=ws.operation_id
 JOIN public.employees e ON e.id=ws.employee_id
 JOIN public.production_orders po ON po.id=o.production_order_id
 WHERE o.id=ANY(:'ml_operation_ids'::integer[])
   AND COALESCE(o.operation_type,'PRODUCTION')='PRODUCTION'
   AND ws.status='CLOSED' AND ws.quantity_confirmed IS TRUE
   AND ws.excluded_from_reports IS FALSE AND ws.closed_by_system IS FALSE
   AND ws.ended_at>ws.started_at AND ws.ended_at<=CURRENT_TIMESTAMP
   AND ws.good_qty IS NOT NULL AND ws.defect_qty IS NOT NULL
   AND ws.good_qty>=0 AND ws.defect_qty>=0
   AND COALESCE(ws.start_request_id,'') NOT LIKE 'QA-%'
   AND COALESCE(ws.start_request_id,'') NOT LIKE 'TUT%'
   AND COALESCE(ws.note,'') NOT LIKE 'TUT%'
   AND e.employee_no NOT LIKE 'TUT-%' AND po.code NOT LIKE 'TUT-%';
REVOKE ALL ON public.mesflow_ml_ops_sessions FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO :"ml_reader";
GRANT SELECT ON public.mesflow_ml_ops_sessions TO :"ml_reader";
ALTER ROLE :"ml_reader" SET default_transaction_read_only=on;
ALTER ROLE :"ml_reader" CONNECTION LIMIT 1;
COMMIT;
