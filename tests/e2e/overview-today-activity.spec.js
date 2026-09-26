const {test,expect}=require('@playwright/test');
// Production Overview hotfix (2026-09-26, part 2): "Hôm nay" block per
// Operation row + neutral "Đã dừng HH:mm" line for closed-today workers.
// OPEN (active_worker_list) wins over the today history.
async function login(page){await page.goto('/login');await page.request.post('/api/auth/test-auto-login');
 await page.waitForURL(/\/app/,{timeout:20000}).catch(()=>{});
 await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible()}
const W=(id,name,extra={})=>({employee_id:id,employee_no:`NV${String(id).padStart(3,'0')}`,name,session_count:1,...extra});
const TODAY=(extra={})=>({date:'2026-09-26',employee_count:2,session_count:3,open_session_count:0,good_qty:120,defect_qty:4,rework_qty:2,recorded_session_count:3,work_seconds:9000,productivity_percent:104.3,scored_session_count:3,standard_seconds_per_unit:60,last_ended_at:'2026-09-26T09:30:00Z',...extra});
const OP=(id,name,{active=[],today=null,history=[],state='IDLE'}={})=>({po_id:1,po_code:'PO-TD',part_id:1,part_code:'P1',part_name:'Thân',operation_id:id,operation_sort:id,operation_code:`OP${id}`,operation_name:name,done_qty:40,defect_qty:1,rework_qty:0,repair_pending_quantity:id===2?3:0,estimated_repair_work_seconds:0,progress_percent:40,control_state:'ON_TRACK',open_session_count:active.length,active_worker_list:active,active_worker_count:active.length,today,today_worker_list:history,today_worker_count:history.length,today_last_ended_at:today?today.last_ended_at:null,today_state:state});
async function mock(page){
 const production_orders=[{id:1,po_id:1,code:'PO-TD',po_code:'PO-TD',product:'SẢN PHẨM',status:'IN_PROGRESS',planned_quantity:100,good_quantity:40,defect_quantity:1,repair_pending_quantity:3,estimated_repair_work_seconds:0,repair_unconfigured_operation_count:0,scrap_quantity:0,remaining_quantity:60,progress_percent:40,due_date:'2026-10-01'}];
 const operations=[OP(1,'Chưa làm hôm nay'),
  OP(2,'Đang làm và đã làm',{active:[W(1,'Nguyễn Văn An',{started_at:'2026-09-26T08:00:00Z'})],today:TODAY({open_session_count:1}),history:[W(2,'Trần Thị Bình',{last_ended_at:'2026-09-26T07:00:00Z'})],state:'RUNNING'}),
  OP(3,'Đã dừng nhiều người',{today:TODAY({employee_count:5,session_count:6,productivity_percent:87.5}),history:[W(3,'Lê Chi',{last_ended_at:'2026-09-26T09:30:00Z',auto_closed:true}),W(4,'Phạm Dũng'),W(5,'Hoàng Em',{session_count:2}),W(6,'Võ Phương'),W(7,'Đỗ Giang')],state:'STOPPED'}),
  OP(4,'Chưa có định mức',{today:TODAY({employee_count:1,session_count:1,productivity_percent:null,standard_seconds_per_unit:0,work_seconds:1500}),history:[W(8,'Bùi Hà')],state:'STOPPED'})];
 await page.route('**/api/dashboard/overview*',r=>r.fulfill({json:{ok:true,production_orders,operations,summary:{}}}));
 await page.route('**/api/production-control*',r=>r.fulfill({json:{ok:true,production_orders:[{po_id:1,control_state:'ON_TRACK'}],operations:[],summary:{}}}))}
for(const viewport of [{width:1920,height:1080},{width:1366,height:768},{width:390,height:844}])test(`today activity ${viewport.width}x${viewport.height}`,async({page})=>{
 await page.setViewportSize(viewport);await mock(page);await login(page);
 await page.evaluate(()=>openPage('overview'));await expect(page.locator('.overview-po')).toHaveCount(1);
 const row=id=>page.locator(`[data-repair-op="${id}"]`);
 await expect(page.locator('[data-today-metrics]')).toHaveCount(4);
 // Idle row: compact empty block, no worker line.
 await expect(row(1).locator('[data-today-metrics]')).toContainText('Chưa có phiên làm việc');
 await expect(row(1).locator('.overview-op-workers')).toHaveCount(0);
 // OPEN wins: green line only, no neutral history line.
 await expect(row(2).locator('.overview-op-workers')).toHaveCount(1);
 await expect(row(2).locator('.overview-op-workers')).toContainText('Đang làm');
 await expect(row(2).locator('.overview-op-workers.is-stopped')).toHaveCount(0);
 const t2=row(2).locator('[data-today-metrics]');
 await expect(t2.locator('[data-today="employees"] b')).toHaveText('2');
 await expect(t2.locator('[data-today="sessions"] b')).toHaveText('3');
 await expect(t2.locator('[data-today="good"] b')).toHaveText('120');
 await expect(t2.locator('[data-today="defect"] b')).toHaveText('4');
 await expect(t2.locator('[data-today="rework"] b')).toHaveText('2');
 await expect(t2.locator('[data-today="time"] b')).toHaveText('2 giờ 30 phút');
 await expect(t2.locator('[data-today="productivity"] b')).toHaveText('104,3%');
 await expect(t2.locator('[data-today="productivity"]')).toHaveClass(/fast/);
 await expect(t2.locator('[data-today="productivity"]')).toHaveAttribute('title',/Nhanh hơn định mức[\s\S]*định mức × \(Đạt \+ Lỗi\) ÷ thời gian thực tế × 100%/);
 // Closed-today: neutral "Đã dừng HH:mm" (local time), max 3 chips + N.
 const stopped=row(3).locator('.overview-op-workers.is-stopped');
 await expect(stopped.locator('em')).toHaveText('Đã dừng 16:30');
 await expect(stopped.locator('.ov-worker')).toHaveCount(4);
 await expect(stopped.locator('.ov-worker.more')).toHaveText('+2');
 await expect(stopped).toContainText('×2');
 await expect(stopped.locator('.ov-worker').first()).toHaveAttribute('title',/Lê Chi[\s\S]*dừng 16:30[\s\S]*tự đóng khi hết ca/);
 await expect(row(3).locator('[data-today="productivity"]')).toHaveClass(/slow/);
 await expect(row(4).locator('[data-today="productivity"] b')).toHaveText('Chưa có định mức');
 await expect(row(4).locator('[data-today="time"] b')).toHaveText('25 phút');
 // Existing columns untouched.
 await expect(row(2)).toContainText('40.0%');
 if(viewport.width>900){
  await expect(row(2).locator('[data-open-op]')).toBeVisible();
  await expect(page.locator('.overview-op-today-head')).toHaveText('Hôm nay');
  // Same grid line as the Operation's own columns, between Chờ sửa and Mở OP.
  const pos=await row(2).evaluate(r=>{const b=s=>r.querySelector(s).getBoundingClientRect();const kids=[...r.children];return {today:b('[data-today-metrics]'),repair:kids[4].getBoundingClientRect(),open:kids[5].getBoundingClientRect(),name:kids[0].getBoundingClientRect()}});
  expect(pos.today.left).toBeGreaterThanOrEqual(pos.repair.right-1);
  expect(pos.today.right).toBeLessThanOrEqual(pos.open.left+1);
  expect(pos.today.top).toBeLessThan(pos.name.bottom);
 }
 const spill=await page.locator('[data-today-metrics],.overview-op-workers').evaluateAll(els=>els.filter(el=>el.scrollWidth>el.clientWidth+1||el.getBoundingClientRect().right>el.parentElement.getBoundingClientRect().right+1).length);
 expect(spill).toBe(0);
 expect(await page.locator('body').evaluate(x=>x.scrollWidth>x.clientWidth)).toBe(false);
 await page.screenshot({path:`test-results/overview-today-activity-${viewport.width}x${viewport.height}.png`,fullPage:true})});
