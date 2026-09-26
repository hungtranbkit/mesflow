const {test,expect}=require('@playwright/test');
// Production Overview hotfix (2026-09-26): each Operation row names who is on
// it right now (active_worker_list = OPEN sessions). Mocked data covers zero /
// one / many (+N) / SETUP / one person with two open sessions.
async function login(page){await page.goto('/login');await page.request.post('/api/auth/test-auto-login');
 await page.waitForURL(/\/app/,{timeout:20000}).catch(()=>{});
 await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible()}
const W=(id,name,extra={})=>({employee_id:id,employee_no:`NV${String(id).padStart(3,'0')}`,name,started_at:'2026-09-26T01:00:00Z',session_count:1,session_ids:[id*10],station_codes:['ST-01'],setup:false,...extra});
const OP=(id,name,workers)=>({po_id:1,po_code:'PO-AW',part_id:1,part_code:'P1',part_name:'Thân',operation_id:id,operation_sort:id,operation_code:`OP${id}`,operation_name:name,done_qty:40,defect_qty:1,rework_qty:0,repair_pending_quantity:0,estimated_repair_work_seconds:0,progress_percent:40,control_state:'ON_TRACK',open_session_count:workers.length,active_worker_list:workers,active_worker_count:workers.length});
async function mock(page){
 const production_orders=[{id:1,po_id:1,code:'PO-AW',po_code:'PO-AW',product:'SẢN PHẨM',status:'IN_PROGRESS',planned_quantity:100,good_quantity:40,defect_quantity:1,repair_pending_quantity:0,estimated_repair_work_seconds:0,repair_unconfigured_operation_count:0,scrap_quantity:0,remaining_quantity:60,progress_percent:40,due_date:'2026-10-01'}];
 const operations=[OP(1,'Không ai làm',[]),OP(2,'Một người',[W(1,'Nguyễn Văn An')]),
  OP(3,'Nhiều người',[W(2,'Trần Thị Bình'),W(3,'Lê Chi'),W(4,'Phạm Dũng'),W(5,'Hoàng Em'),W(6,'Võ Phương')]),
  OP(4,'Chuẩn bị và nhiều phiên',[W(7,'Đỗ Giang',{setup:true}),W(8,'Bùi Hà',{session_count:2,session_ids:[80,81]})])];
 await page.route('**/api/dashboard/overview*',r=>r.fulfill({json:{ok:true,production_orders,operations,summary:{}}}));
 await page.route('**/api/production-control*',r=>r.fulfill({json:{ok:true,production_orders:[{po_id:1,control_state:'ON_TRACK'}],operations:[],summary:{}}}))}
for(const viewport of [{width:1920,height:1080},{width:1366,height:768},{width:390,height:844}])test(`active workers ${viewport.width}x${viewport.height}`,async({page})=>{
 await page.setViewportSize(viewport);await mock(page);await login(page);
 await page.evaluate(()=>openPage('overview'));await expect(page.locator('.overview-po')).toHaveCount(1);
 const row=id=>page.locator(`[data-repair-op="${id}"]`);
 await expect(page.locator('.overview-op-workers')).toHaveCount(3);
 await expect(row(1).locator('.overview-op-workers')).toHaveCount(0);
 await expect(row(2).locator('.overview-op-workers')).toContainText('Nguyễn Văn An');
 await expect(row(2).locator('.overview-op-workers')).toContainText('NV001');
 const many=row(3).locator('.overview-op-workers');
 await expect(many.locator('.ov-worker')).toHaveCount(4);
 await expect(many).toContainText('Phạm Dũng');await expect(many).not.toContainText('Hoàng Em');
 await expect(many.locator('.ov-worker.more')).toHaveText('+2');
 await expect(many.locator('.ov-worker.more')).toHaveAttribute('title',/Hoàng Em[\s\S]*Võ Phương/);
 await expect(row(4).locator('.ov-worker.setup')).toContainText('Chuẩn bị');
 await expect(row(4).locator('.overview-op-workers')).toContainText('×2');
 // Existing columns untouched: progress/qty still render on a staffed row.
 await expect(row(3)).toContainText('40.0%');
 const spill=await page.locator('.overview-op-workers').evaluateAll(els=>els.filter(el=>el.scrollWidth>el.clientWidth+1||el.getBoundingClientRect().right>el.parentElement.getBoundingClientRect().right+1).length);
 expect(spill).toBe(0);
 expect(await page.locator('body').evaluate(x=>x.scrollWidth>x.clientWidth)).toBe(false);
 await page.screenshot({path:`test-results/overview-active-workers-${viewport.width}x${viewport.height}.png`,fullPage:true})});
