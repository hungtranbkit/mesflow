const {test,expect}=require('@playwright/test');
// Operation Detail "Bổ sung phiên" (2026-09-26 hotfix): per-employee "+ Phiên"
// prefill, Operation-level "+ Bổ sung phiên", live Thời gian / So định mức
// preview, required reason, one POST on double-submit, in-place refresh with
// the new row in Phiên gần nhất. APIs are mocked; the real create path is
// covered by tests/integration/test_op_detail_manual_session.py.
async function login(page){await page.goto('/login');await page.request.post('/api/auth/test-auto-login');
 await page.waitForURL(/\/app/,{timeout:20000}).catch(()=>{});
 await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible()}
const pad=n=>String(n).padStart(2,'0');
// Yesterday in the browser's own clock -- never a hardcoded date.
const local=(h,m=0)=>{const d=new Date(Date.now()-86400000);d.setHours(h,m,0,0);return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(h)}:${pad(m)}`};
const iso=v=>new Date(v).toISOString();
const SESSION=(id,emp,extra={})=>({session_id:id,status:'CLOSED',started_at:iso(local(13)),ended_at:iso(local(14)),duration_seconds:3600,good_qty:20,defect_qty:0,rework_qty:0,employee_id:emp.id,employee_code:emp.employee_no,employee_name:emp.name,quantity_confirmed:true,adjustment_count:0,close_reason:'',...extra});
const EMPLOYEES=[{id:11,employee_no:'NV011',name:'Nguyễn Văn An',active:true},{id:12,employee_no:'NV012',name:'Trần Thị Bình',active:true}];
async function mock(page){
 const state={posts:[],sessions:[SESSION(501,EMPLOYEES[0])]};
 const production_orders=[{id:1,po_id:1,code:'PO-MS',po_code:'PO-MS',product:'SẢN PHẨM',status:'IN_PROGRESS',planned_quantity:100,good_quantity:20,defect_quantity:0,repair_pending_quantity:0,estimated_repair_work_seconds:0,repair_unconfigured_operation_count:0,scrap_quantity:0,progress_percent:20,due_date:'2026-12-01'}];
 const operations=[{po_id:1,po_code:'PO-MS',part_id:1,part_code:'P1',part_name:'Thân',operation_id:7,operation_sort:1,operation_code:'OP7',operation_name:'May thân',done_qty:20,defect_qty:0,rework_qty:0,repair_pending_quantity:0,estimated_repair_work_seconds:0,progress_percent:20,control_state:'ON_TRACK',active_worker_list:[],active_worker_count:0}];
 await page.route('**/api/dashboard/overview*',r=>r.fulfill({json:{ok:true,production_orders,operations,summary:{}}}));
 await page.route('**/api/production-control*',r=>r.fulfill({json:{ok:true,production_orders:[{po_id:1,control_state:'ON_TRACK'}],operations:[],summary:{}}}));
 await page.route('**/api/reports/operations/7',r=>r.fulfill({json:{ok:true,report:{operation:{id:7,code:'OP7',name:'May thân',po_code:'PO-MS',part_code:'P1',part_name:'Thân',standard_seconds_per_unit:120}}}}));
 await page.route('**/api/reports/operation-sessions*',r=>r.fulfill({json:{ok:true,report:{sessions:state.sessions,users:[],operations:[]}}}));
 await page.route('**/api/employees*',r=>r.fulfill({json:{ok:true,items:EMPLOYEES}}));
 await page.route('**/api/supervisor/sessions/manual',async r=>{
  const body=JSON.parse(r.request().postData()||'{}');state.posts.push(body);
  await new Promise(res=>setTimeout(res,400));
  const emp=EMPLOYEES.find(x=>x.id===body.employee_id);
  // Older than the existing row on purpose: it must still be shown.
  state.sessions=[...state.sessions,SESSION(777,emp,{started_at:iso(body.started_at),ended_at:iso(body.ended_at),duration_seconds:(new Date(body.ended_at)-new Date(body.started_at))/1000,good_qty:body.good_qty,defect_qty:body.defect_qty,rework_qty:body.rework_qty,close_reason:'MANUAL_SUPPLEMENT',adjustment_count:1})];
  await r.fulfill({status:201,json:{ok:true,session:{id:777,status:'CLOSED'},idempotent_replay:false}})});
 return state}
async function openDetail(page){await page.evaluate(()=>openPage('overview'));
 await page.locator('[data-op-detail="7"]').dblclick();
 const modal=page.locator('.op-detail-modal');await expect(modal.locator('.op-detail-user-row')).toHaveCount(1);return modal}
const noOverflow=async page=>{expect(await page.locator('.op-detail-modal').evaluate(m=>m.scrollWidth>m.clientWidth+1)).toBe(false)};

for(const viewport of [{width:1366,height:768},{width:390,height:844}])test(`manual session ${viewport.width}x${viewport.height}`,async({page})=>{
 await page.setViewportSize(viewport);const state=await mock(page);await login(page);
 const modal=await openDetail(page);
 const form=modal.locator('[data-manual-session-form]');
 await expect(form).toBeHidden();
 if(viewport.width>800)await expect(modal.locator('.op-detail-user-head')).toContainText('Bổ sung');
 // Per-employee action preselects that employee.
 await modal.locator('[data-manual-session-employee="11"]').click();
 await expect(form).toBeVisible();
 await expect(form.locator('select[name="employee_id"]')).toHaveValue('11');
 await expect(form.locator('select[name="employee_id"] option')).toHaveCount(3);
 await form.locator('input[name="started_at"]').fill(local(8));
 await form.locator('input[name="ended_at"]').fill(local(10));
 await form.locator('input[name="good_qty"]').fill('30');
 await expect(form.locator('input[name="rework_qty"]')).toHaveValue('0');
 await expect(form.locator('label',{hasText:'Lỗi sửa được'}).locator('input[name="rework_qty"]')).toHaveAttribute('min','0');
 await form.locator('input[name="defect_qty"]').fill('2');
 // Lỗi sửa được > Lỗi: friendly message while typing, and no request on submit.
 await form.locator('input[name="rework_qty"]').fill('3');
 await expect(form.locator('[data-manual-error]')).toHaveText('Lỗi sửa được không được lớn hơn số Lỗi.');
 await form.locator('input[name="rework_qty"]').fill('1');
 await expect(form.locator('[data-manual-error]')).toBeHidden();
 await expect(form.locator('[data-manual-duration]')).toHaveText(`2 giờ 00 phút · ${local(8).slice(8,10)}/${local(8).slice(5,7)} 08:00 → 10:00`);
 // 120 s/SP x 32 SP / 7200 s x 100 = 53.3% -- same formula/copy as the list;
 // Lỗi sửa được is inside Lỗi, so it does not change the score.
 await expect(form.locator('[data-manual-score]')).toHaveText('53.3% · Chậm hơn định mức');
 await noOverflow(page);
 await page.screenshot({path:`test-results/op-manual-session-form-${viewport.width}x${viewport.height}.png`,fullPage:true});
 // Reason is required: no request goes out without it.
 await form.locator('[data-manual-session-submit]').click();
 await expect(form.locator('[data-manual-error]')).toHaveText('Hãy nhập lý do bổ sung.');
 // End before start is refused client-side too.
 await form.locator('input[name="reason"]').fill('Quên quét QR kết thúc');
 await form.locator('input[name="ended_at"]').fill(local(7));
 await form.locator('[data-manual-session-submit]').click();
 await expect(form.locator('[data-manual-error]')).toHaveText('Giờ kết thúc phải sau giờ bắt đầu.');
 await form.locator('input[name="ended_at"]').fill(local(10));
 await form.locator('input[name="rework_qty"]').fill('3');
 await form.locator('[data-manual-session-submit]').click();
 await expect(form.locator('[data-manual-error]')).toHaveText('Lỗi sửa được không được lớn hơn số Lỗi.');
 await form.locator('input[name="rework_qty"]').fill('1');
 await expect(form.locator('[data-manual-score]')).toHaveText('53.3% · Chậm hơn định mức');
 expect(state.posts).toHaveLength(0);
 // Double submit -> exactly one POST.
 const submit=form.locator('[data-manual-session-submit]');
 await submit.click();await form.evaluate(f=>f.requestSubmit());
 await expect(page.locator('#toast')).toContainText('Đã bổ sung phiên #777 · 30 đạt · 2 lỗi (sửa được 1)');
 expect(state.posts).toHaveLength(1);
 const sent=state.posts[0];
 expect(sent).toMatchObject({operation_id:7,employee_id:11,started_at:local(8),ended_at:local(10),good_qty:30,defect_qty:2,rework_qty:1,reason:'Quên quét QR kết thúc'});
 expect(sent.request_id).toMatch(/^op-detail-manual-7-/);
 // Refreshed in place: form closed, new row in Phiên gần nhất, aggregate updated.
 await expect(modal.locator('[data-manual-session-form]')).toBeHidden();
 const row=modal.locator('[data-session-item="777"]');
 await expect(row).toHaveClass(/is-new/);
 await expect(row).toContainText('Bổ sung tay');
 await expect(row).not.toContainText('Đã điều chỉnh');
 await expect(row).toContainText('32 SP');
 await expect(row).toContainText('30 đạt · 2 lỗi · 1 sửa');
 await expect(modal.locator('.op-detail-user-row').first()).toContainText('sửa được 1');
 await expect(modal.locator('.op-detail-user-row').first()).toContainText('2');
 await expect(modal.locator('.op-detail-kpis')).toContainText('50 / 2');
 // Existing Sửa SL stays on closed rows.
 await expect(modal.locator('[data-edit-session-qty="501"]')).toHaveText('Sửa SL');
 // Operation-level action: manager chooses any employee.
 await modal.locator('[data-manual-session-open]').click();
 await expect(modal.locator('[data-manual-session-form] select[name="employee_id"]')).toHaveValue('');
 await noOverflow(page);
 await page.screenshot({path:`test-results/op-manual-session-after-${viewport.width}x${viewport.height}.png`,fullPage:true})});
