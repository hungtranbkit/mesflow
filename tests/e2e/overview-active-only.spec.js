const {test,expect}=require('@playwright/test');
// Tổng quan active-only hotfix (2026-09-30). Across refreshes of the SAME
// screen (the "Làm mới" button runs the same load() the 60 s timer does):
//   1. two people on OP1 -> both listed;
//   2. one finishes -> only the other is listed, OP1 stays;
//   3. the last one finishes (AUTO_CLOSED at shift end) -> OP1 has no
//      "Hôm nay" block at all, and no placeholder.
// One employee with OPEN sessions on two Operations shows on both.
async function login(page){await page.goto('/login');await page.request.post('/api/auth/test-auto-login');
 await page.waitForURL(/\/app/,{timeout:20000}).catch(()=>{});
 await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible()}
const W=(id,name,extra={})=>({employee_id:id,employee_no:`NV${String(id).padStart(3,'0')}`,name,started_at:'2026-09-30T01:00:00Z',session_count:1,session_ids:[id*10],station_codes:['ST-01'],setup:false,...extra});
const TODAY=(extra={})=>({date:'2026-09-30',employee_count:3,employee_ids:[1,2,3],session_count:3,open_session_count:2,good_qty:50,defect_qty:1,rework_qty:0,work_seconds:3600,actual_work_seconds:3600,expected_seconds:3000,standard_seconds_per_unit:60,standard_configured:true,first_started_at:'2026-09-30T01:00:00Z',last_ended_at:null,scored_work_seconds:0,scored_expected_seconds:0,weighted_session_count:0,weighted_productivity_percent:null,delta_seconds:null,pace:null,...extra});
const OP=(id,name,active,history=[],today=TODAY())=>({po_id:1,po_code:'PO-AO',part_id:1,part_code:'P1',part_name:'Thân',operation_id:id,operation_sort:id,operation_code:`OP${id}`,operation_name:name,done_qty:40,defect_qty:1,rework_qty:0,repair_pending_quantity:0,estimated_repair_work_seconds:0,progress_percent:40,control_state:'ON_TRACK',open_session_count:active.length,active_worker_list:active,active_worker_count:active.length,today,today_worker_list:history,today_worker_count:history.length,today_state:active.length?'RUNNING':(history.length?'STOPPED':'IDLE')});
const STEPS=[
 // 1. An + Bình on OP1; Chi on OP2 AND OP3 (two OPEN sessions, two Operations).
 [OP(1,'May thân',[W(1,'Nguyễn Văn An'),W(2,'Trần Thị Bình')]),OP(2,'Ráp cổ',[W(3,'Lê Chi')]),OP(3,'Đóng nút',[W(3,'Lê Chi',{started_at:'2026-09-30T02:00:00Z'})])],
 // 2. Bình finished on OP1.
 [OP(1,'May thân',[W(1,'Nguyễn Văn An')],[W(2,'Trần Thị Bình',{last_ended_at:'2026-09-30T03:00:00Z'})]),OP(2,'Ráp cổ',[W(3,'Lê Chi')]),OP(3,'Đóng nút',[W(3,'Lê Chi')])],
 // 3. An auto-closed at shift end; Chi finished OP3 but still on OP2.
 [OP(1,'May thân',[],[W(1,'Nguyễn Văn An',{last_ended_at:'2026-09-30T10:00:00Z',auto_closed:true}),W(2,'Trần Thị Bình',{last_ended_at:'2026-09-30T03:00:00Z'})]),OP(2,'Ráp cổ',[W(3,'Lê Chi')]),OP(3,'Đóng nút',[],[W(3,'Lê Chi',{last_ended_at:'2026-09-30T04:00:00Z'})])],
];
for(const viewport of [{width:1366,height:768},{width:390,height:844}])test(`active only across refreshes ${viewport.width}x${viewport.height}`,async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 let step=0,calls=0;
 const production_orders=[{id:1,po_id:1,code:'PO-AO',po_code:'PO-AO',product:'SẢN PHẨM',status:'IN_PROGRESS',planned_quantity:100,good_quantity:40,defect_quantity:1,repair_pending_quantity:0,estimated_repair_work_seconds:0,repair_unconfigured_operation_count:0,scrap_quantity:0,remaining_quantity:60,progress_percent:40,due_date:'2026-10-01'}];
 await page.route('**/api/dashboard/overview*',r=>{calls++;return r.fulfill({json:{ok:true,production_orders,operations:STEPS[step],summary:{}}})});
 await page.route('**/api/production-control*',r=>r.fulfill({json:{ok:true,production_orders:[{po_id:1,control_state:'ON_TRACK'}],operations:[],summary:{}}}));
 await page.setViewportSize(viewport);await login(page);
 await page.evaluate(()=>openPage('overview'));await expect(page.locator('.overview-po')).toHaveCount(1);
 const row=id=>page.locator(`[data-repair-op="${id}"]`),names=id=>row(id).locator('[data-today-metrics] .ov-worker .ov-worker-name');
 const refresh=async n=>{step=n;const before=calls;await page.click('#ovReload');await expect.poll(()=>calls).toBeGreaterThan(before)};
 // 1.
 await expect(names(1)).toHaveText(['Nguyễn Văn An','Trần Thị Bình']);
 await expect(names(2)).toHaveText(['Lê Chi']);
 await expect(names(3)).toHaveText(['Lê Chi']);
 await expect(row(1).locator('[data-today="employees"] b')).toHaveText('2');
 // 2. Only the finished worker disappears; the Operation and An stay.
 await refresh(1);
 await expect(names(1)).toHaveText(['Nguyễn Văn An']);
 await expect(row(1)).not.toContainText('Trần Thị Bình');
 await expect(row(1).locator('[data-today="employees"] b')).toHaveText('1');
 await expect(row(1).locator('[data-today="good"] b')).toHaveText('50');  // day metrics untouched
 // 3. Nobody left on OP1 / OP3 -> no block, no placeholder; OP2 unchanged.
 await refresh(2);
 for(const id of [1,3]){
  await expect(row(id).locator('[data-today-metrics]')).toHaveCount(0);
  await expect(row(id)).not.toContainText('Đã kết thúc');
  await expect(row(id)).not.toContainText('Chưa có phiên làm việc');
 }
 await expect(row(1)).not.toContainText('Nguyễn Văn An');
 await expect(row(1)).toContainText('40.0%');  // the Operation row itself stays
 await expect(names(2)).toHaveText(['Lê Chi']);
 expect(await page.locator('body').evaluate(x=>x.scrollWidth>x.clientWidth)).toBe(false);
 expect(errors).toEqual([]);
 await page.screenshot({path:`test-results/overview-active-only-${viewport.width}x${viewport.height}.png`,fullPage:true})});
