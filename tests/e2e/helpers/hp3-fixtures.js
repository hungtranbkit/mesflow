// Shared API mocks for the hp3 UI-consistency lane. Deterministic, no DB
// seeding: these screens are being measured for SURFACE SHAPE, so the data
// only has to be shaped correctly and be non-empty.
const hcmDate = () => new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit'
}).format(new Date());
const at = (d, h, m = 0) =>
  new Date(`${d}T${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:00+07:00`).toISOString();

const SHIFTS = [{ id:1, code:'DAY', name:'Ca ngày', active:true, anchor_start:'07:30', anchor_end:'17:00',
  cross_midnight:false, target_minutes:480,
  intervals:[{ interval_type:'WORK', start_minute:450, end_minute:1020, sort_order:0 }] }];

function dayPayload(date) {
  const items = [
    { po_id:1, po_code:'PO-HP3-1', product:'Thùng rác inox', part_id:1, part_code:'PART-1', part_name:'Thân thùng',
      operation_id:11, operation_code:'111-THAN-THUNG-R-04', operation_name:'Hàn thùng rác inox',
      operation_status:'IN_PROGRESS', total_good_qty:300, total_defect_qty:12, planned_quantity:500,
      standard_seconds_per_unit:60, planned_work_seconds:30000, session_count:3, open_session_count:1,
      day_good_qty:120, day_defect_qty:18, day_rework_qty:4, day_scrap_qty:1, day_work_seconds:21000,
      active_workers:[{ employee_id:1, name:'Nguyễn Văn A' }], all_participants:[], day_contributors:[],
      last_report_at:at(date,14), unconfirmed_count:0, day_state:'RUNNING' },
    { po_id:1, po_code:'PO-HP3-1', product:'Thùng rác inox', part_id:1, part_code:'PART-1', part_name:'Thân thùng',
      operation_id:12, operation_code:'OP-SON-02', operation_name:'Sơn tĩnh điện',
      operation_status:'IN_PROGRESS', total_good_qty:150, total_defect_qty:2, planned_quantity:500,
      standard_seconds_per_unit:30, planned_work_seconds:15000, session_count:1, open_session_count:0,
      day_good_qty:40, day_defect_qty:1, day_rework_qty:0, day_scrap_qty:0, day_work_seconds:9000,
      active_workers:[], all_participants:[], day_contributors:[],
      last_report_at:at(date,11), unconfirmed_count:2, day_state:'NEEDS_REVIEW' }
  ];
  const sessions = [
    { session_id:1, session_status:'OPEN', started_at:at(date,8), ended_at:null, effective_end_at:at(date,9),
      duration_seconds:3600, work_duration_seconds:3600, good_qty:120, defect_qty:18, rework_qty:0, scrap_qty:0,
      employee_id:1, employee_code:'EMP-001', employee_name:'Nguyễn Văn A', po_id:1, po_code:'PO-HP3-1',
      part_id:1, part_code:'PART-1', part_name:'Thân thùng', operation_id:11,
      operation_code:'111-THAN-THUNG-R-04', operation_name:'Hàn thùng rác inox' },
    { session_id:2, session_status:'CLOSED', started_at:at(date,10), ended_at:at(date,11), effective_end_at:at(date,11),
      duration_seconds:3600, work_duration_seconds:3600, good_qty:40, defect_qty:1, rework_qty:0, scrap_qty:0,
      employee_id:2, employee_code:'EMP-002', employee_name:'Trần Thị B', po_id:1, po_code:'PO-HP3-1',
      part_id:1, part_code:'PART-1', part_name:'Thân thùng', operation_id:12,
      operation_code:'OP-SON-02', operation_name:'Sơn tĩnh điện' }
  ];
  const activity = [
    { kind:'SESSION_START', at:at(date,8), employee_name:'Nguyễn Văn A', operation_name:'Hàn thùng rác inox',
      operation_code:'111-THAN-THUNG-R-04', po_code:'PO-HP3-1', good_qty:0 },
    { kind:'QTY_REPORT', at:at(date,11), employee_name:'Trần Thị B', operation_name:'Sơn tĩnh điện',
      operation_code:'OP-SON-02', po_code:'PO-HP3-1', good_qty:40 }
  ];
  return { ok:true, context:{ date, timezone:'Asia/Ho_Chi_Minh', day_start:at(date,0), day_end:at(date,23,59) },
    items, sessions, activity };
}

const OVERVIEW = { ok:true, summary:{ unconfirmed_quantity_sessions:2 },
  production_orders:[{ po_id:1, po_code:'PO-HP3-1', product:'Thùng rác inox', planned_quantity:500,
    good_quantity:300, defect_quantity:12, scrap_quantity:0, remaining_quantity:200, progress_percent:60,
    due_date:'2026-09-30', repair_pending_quantity:9, repair_unconfigured_operation_count:0,
    estimated_repair_work_seconds:3600, control_state:'WARNING' }], operations:[] };

const CONTROL = { ok:true, production_orders:[{ po_id:1, control_state:'WARNING', control_label:'CẦN CHÚ Ý' }],
  operations:[{ po_id:1, operation_id:11, operation_code:'111-THAN-THUNG-R-04', operation_name:'Hàn thùng rác inox',
    control_state:'CRITICAL', control_label:'LÀM NGAY', recommended_action:'Ưu tiên cấp người/máy' }] };

const SESSION_MGMT = (date) => ({ ok:true, items:[
  { session_id:1, session_status:'OPEN', started_at:at(date,8), ended_at:null, duration_seconds:3600,
    work_duration_seconds:3600, good_qty:120, defect_qty:18, rework_qty:0, scrap_qty:0,
    employee_id:1, employee_code:'EMP-001', employee_name:'Nguyễn Văn A', po_id:1, po_code:'PO-HP3-1',
    part_code:'PART-1', part_name:'Thân thùng', operation_id:11, operation_code:'111-THAN-THUNG-R-04',
    operation_name:'Hàn thùng rác inox', exception_count:1 },
  { session_id:2, session_status:'CLOSED', started_at:at(date,10), ended_at:at(date,11), duration_seconds:3600,
    work_duration_seconds:3600, good_qty:40, defect_qty:1, rework_qty:0, scrap_qty:0,
    employee_id:2, employee_code:'EMP-002', employee_name:'Trần Thị B', po_id:1, po_code:'PO-HP3-1',
    part_code:'PART-1', part_name:'Thân thùng', operation_id:12, operation_code:'OP-SON-02',
    operation_name:'Sơn tĩnh điện', exception_count:0 }
] });

const SESSION_MGMT_OPS = (date) => ({ ok:true, items:[
  { operation_id:11, operation_code:'111-THAN-THUNG-R-04', operation_name:'Hàn thùng rác inox',
    po_id:1, po_code:'PO-HP3-1', part_code:'PART-1', part_name:'Thân thùng',
    session_count:3, open_session_count:1, last_activity_at:at(date,14),
    good_qty:300, defect_qty:12, exception_count:1 },
  { operation_id:12, operation_code:'OP-SON-02', operation_name:'Sơn tĩnh điện',
    po_id:1, po_code:'PO-HP3-1', part_code:'PART-1', part_name:'Thân thùng',
    session_count:1, open_session_count:0, last_activity_at:at(date,11),
    good_qty:150, defect_qty:2, exception_count:0 }
] });

const EXCEPTIONS = (date) => ({ ok:true, total:2, items:[
  { id:101, code:'EXC-101', status:'OPEN', severity:'HIGH', kind:'QTY_UNCONFIRMED',
    exception_type:'QTY_UNCONFIRMED', title:'Sản lượng chưa xác nhận', message:'Session đóng nhưng chưa xác nhận sản lượng',
    created_at:at(date,9), detected_at:at(date,9), session_id:1, employee_name:'Nguyễn Văn A',
    operation_code:'111-THAN-THUNG-R-04', operation_name:'Hàn thùng rác inox', po_code:'PO-HP3-1',
    source:'SYSTEM', impact:'Ảnh hưởng số liệu ngày' },
  { id:102, code:'EXC-102', status:'ACKNOWLEDGED', severity:'MEDIUM', kind:'SESSION_OVERLAP',
    exception_type:'SESSION_OVERLAP', title:'Session chồng lấn', message:'Hai session cùng nhân viên trùng giờ',
    created_at:at(date,12), detected_at:at(date,12), session_id:2, employee_name:'Trần Thị B',
    operation_code:'OP-SON-02', operation_name:'Sơn tĩnh điện', po_code:'PO-HP3-1',
    source:'SYSTEM', impact:'Sai giờ công' }
] });

const BUSINESS_AUDIT = (date) => ({ ok:true, total:2, items:[
  { id:1, at:at(date,9), actor:'admin', actor_name:'Quản trị', action:'SESSION_EDIT', action_label:'Sửa session',
    entity:'session', entity_id:'1', summary:'Sửa giờ kết thúc session #1', changes:[{field:'ended_at',before:'—',after:'11:00'}] },
  { id:2, at:at(date,13), actor:'admin', actor_name:'Quản trị', action:'QTY_CONFIRM', action_label:'Xác nhận sản lượng',
    entity:'session', entity_id:'2', summary:'Xác nhận 40 sản phẩm đạt', changes:[] }
] });


const SCHEDULE = (date) => ({ ok:true, items:[
  { po_id:1, po_code:'PO-HP3-1', product:'Thùng rác inox', po_status:'IN_PROGRESS', due_date:'2026-09-30',
    po_end:at(date,17,0), part_id:1, part_code:'PART-1', part_name:'Thân thùng',
    operation_id:11, operation_code:'111-THAN-THUNG-R-04', operation_name:'Hàn thùng rác inox',
    operation_status:'IN_PROGRESS', planned_start_at:at(date,7,30), planned_end_at:at(date,12,0),
    actual_start_at:at(date,8,0), actual_end_at:null, calculated_start_at:at(date,8,0),
    calculated_end_at:at(date,12,0), planned_quantity:500, done_qty:300, defect_qty:12,
    progress_percent:60, blocked:false, active_sessions:1, predecessor_code:null,
    input_flow_enabled:false, defects_consume_input:false },
  { po_id:1, po_code:'PO-HP3-1', product:'Thùng rác inox', po_status:'IN_PROGRESS', due_date:'2026-09-30',
    po_end:at(date,17,0), part_id:1, part_code:'PART-1', part_name:'Thân thùng',
    operation_id:12, operation_code:'OP-SON-02', operation_name:'Sơn tĩnh điện',
    operation_status:'PLANNED', planned_start_at:at(date,12,0), planned_end_at:at(date,17,0),
    actual_start_at:null, actual_end_at:null, calculated_start_at:at(date,12,0),
    calculated_end_at:at(date,17,0), planned_quantity:500, done_qty:150, defect_qty:2,
    progress_percent:30, blocked:false, active_sessions:0, predecessor_code:'111-THAN-THUNG-R-04',
    input_flow_enabled:true, defects_consume_input:false, input_source_code:'111-THAN-THUNG-R-04',
    input_source_operation_id:11, input_source_done_qty:300, input_available_qty:300, input_consumed_qty:150 },
  { po_id:2, po_code:'PO-HP3-2', product:'Khung inox', po_status:'IN_PROGRESS', due_date:'2026-10-05',
    po_end:at(date,16,0), part_id:2, part_code:'PART-2', part_name:'Khung đỡ',
    operation_id:21, operation_code:'OP-CAT-01', operation_name:'Cắt laser',
    operation_status:'COMPLETED', planned_start_at:at(date,8,0), planned_end_at:at(date,10,0),
    actual_start_at:at(date,8,0), actual_end_at:at(date,10,0), calculated_start_at:at(date,8,0),
    calculated_end_at:at(date,10,0), planned_quantity:200, done_qty:200, defect_qty:0,
    progress_percent:100, blocked:false, active_sessions:0, predecessor_code:null,
    input_flow_enabled:false, defects_consume_input:false },
]});

const REWORK = (date) => ({ ok:true, items:[
  { source_session_id:1, operation_id:11, operation_code:'111-THAN-THUNG-R-04',
    operation_name:'Hàn thùng rác inox', po_code:'PO-HP3-1', part_id:1, part_code:'PART-1',
    part_name:'Thân thùng', employee_name:'Nguyễn Văn A', employee_no:'EMP-001',
    source_finished_at:at(date,9,0), defect_qty:18, rework_qty:4, scrap_qty:2, pending_qty:12 },
  { source_session_id:2, operation_id:12, operation_code:'OP-SON-02',
    operation_name:'Sơn tĩnh điện', po_code:'PO-HP3-1', part_id:1, part_code:'PART-1',
    part_name:'Thân thùng', employee_name:'Trần Thị B', employee_no:'EMP-002',
    source_finished_at:at(date,11,0), defect_qty:6, rework_qty:0, scrap_qty:0, pending_qty:6 },
]});

async function mockAll(page) {
  const date = hcmDate();
  const json = (data) => (r) => r.fulfill({ json: data });
  await page.route('**/api/settings/work-shifts**', json({ ok:true, items:SHIFTS }));
  await page.route('**/api/dashboard/day**', json(dayPayload(date)));
  await page.route('**/api/dashboard/overview**', json(OVERVIEW));
  await page.route('**/api/production-control**', json(CONTROL));
  await page.route('**/api/session-management/operations**', json(SESSION_MGMT_OPS(date)));
  await page.route('**/api/session-management?**', json(SESSION_MGMT(date)));
  await page.route('**/api/session-exceptions?**', json(EXCEPTIONS(date)));
  await page.route('**/api/exceptions?**', json(EXCEPTIONS(date)));
  await page.route('**/api/audit-logs**', json(BUSINESS_AUDIT(date)));
  await page.route('**/api/production-schedule**', json(SCHEDULE(date)));
  await page.route('**/api/rework/queue**', json(REWORK(date)));
  await page.route('**/api/employees**', json({ ok:true, items:[
    { id:1, name:'Nguyễn Văn A', employee_no:'EMP-001' },
    { id:2, name:'Trần Thị B', employee_no:'EMP-002' }] }));
  await page.route('**/api/business-audit**', json(BUSINESS_AUDIT(date)));
}

module.exports = { mockAll, SCHEDULE, REWORK, hcmDate, at, dayPayload, SHIFTS, OVERVIEW, CONTROL,
  SESSION_MGMT, SESSION_MGMT_OPS, EXCEPTIONS, BUSINESS_AUDIT };
