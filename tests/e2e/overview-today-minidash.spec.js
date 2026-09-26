const {test,expect}=require('@playwright/test');
// Production Overview mini-dashboard (2026-09-26, part 3): three-line "Hôm nay"
// block per Operation (NV/phiên/giờ, Đạt/Lỗi/Sửa được, thực tế/ĐM/So ĐM/pace)
// and a "Hôm nay" strip in every PO header derived from the same rows. APIs are
// mocked; the numbers themselves are pinned by
// tests/integration/test_overview_today_minidash.py.
async function login(page){await page.goto('/login');await page.request.post('/api/auth/test-auto-login');
 await page.waitForURL(/\/app/,{timeout:20000}).catch(()=>{});
 await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible()}
const W=(id,name,extra={})=>({employee_id:id,employee_no:`NV${String(id).padStart(3,'0')}`,name,session_count:1,...extra});
// 00:42Z = 07:42 local, 10:00Z = 17:00 local (Asia/Ho_Chi_Minh).
const TODAY=(extra={})=>({date:'2026-09-26',first_started_at:'2026-09-26T00:42:00Z',last_ended_at:'2026-09-26T10:00:00Z',open_session_count:0,recorded_session_count:1,scored_session_count:1,standard_seconds_per_unit:60,standard_configured:true,productivity_percent:50,...extra});
const OP=(id,name,{po=1,active=[],today=null,history=[],state='IDLE'}={})=>({po_id:po,po_code:`PO-${po}`,part_id:1,part_code:'P1',part_name:'Thân',operation_id:id,operation_sort:id,operation_code:`OP${id}`,operation_name:name,done_qty:40,defect_qty:1,rework_qty:0,repair_pending_quantity:0,estimated_repair_work_seconds:0,progress_percent:40,control_state:'ON_TRACK',open_session_count:active.length,active_worker_list:active,active_worker_count:active.length,today,today_worker_list:history,today_worker_count:history.length,today_last_ended_at:today?today.last_ended_at:null,today_state:state});
async function mock(page){
 const PO=(id,code)=>({id,po_id:id,code,po_code:code,product:'SẢN PHẨM',status:'IN_PROGRESS',planned_quantity:100,good_quantity:40,defect_quantity:1,repair_pending_quantity:0,estimated_repair_work_seconds:0,repair_unconfigured_operation_count:0,scrap_quantity:0,remaining_quantity:60,progress_percent:40,due_date:'2026-10-01'});
 const operations=[
  OP(1,'May thân',{active:[W(1,'Nguyễn Văn An',{started_at:'2026-09-26T01:00:00Z'})],state:'RUNNING',history:[W(2,'Trần Thị Bình')],
   today:TODAY({employee_count:2,employee_ids:[1,2],session_count:3,open_session_count:1,good_qty:120,defect_qty:4,rework_qty:2,work_seconds:9000,actual_work_seconds:9000,expected_seconds:7440,scored_work_seconds:9000,scored_expected_seconds:9387,weighted_session_count:2,weighted_productivity_percent:104.3,delta_seconds:-387,pace:'FAST'})}),
  OP(2,'Ráp cổ',{state:'STOPPED',history:[W(2,'Trần Thị Bình'),W(3,'Lê Chi')],
   today:TODAY({employee_count:2,employee_ids:[2,3],session_count:2,good_qty:200,defect_qty:10,rework_qty:3,work_seconds:10800,actual_work_seconds:10800,expected_seconds:12600,scored_work_seconds:14000,scored_expected_seconds:12600,weighted_session_count:2,weighted_productivity_percent:90,delta_seconds:1400,pace:'SLOW'})}),
  OP(3,'Đóng nút',{active:[W(4,'Phạm Dũng',{started_at:'2026-09-26T06:00:00Z'})],state:'RUNNING',
   today:TODAY({employee_count:1,employee_ids:[4],session_count:2,open_session_count:1,good_qty:30,defect_qty:0,rework_qty:0,work_seconds:2400,actual_work_seconds:2400,expected_seconds:1800,scored_work_seconds:1820,scored_expected_seconds:1800,weighted_session_count:1,weighted_productivity_percent:98.9,delta_seconds:20,pace:'ON_TARGET'})}),
  OP(4,'Chưa có định mức',{state:'STOPPED',history:[W(1,'Nguyễn Văn An')],
   today:TODAY({employee_count:1,employee_ids:[1],session_count:1,good_qty:5,defect_qty:0,rework_qty:0,work_seconds:1500,actual_work_seconds:1500,expected_seconds:0,standard_seconds_per_unit:0,standard_configured:false,scored_work_seconds:0,scored_expected_seconds:0,weighted_session_count:0,weighted_productivity_percent:null,delta_seconds:null,pace:null,productivity_percent:null})}),
  ...[5,6,7,8,9].map(i=>OP(i,`Công đoạn chưa làm ${i}`)),
  OP(20,'PO khác',{po:2})];
 await page.route('**/api/dashboard/overview*',r=>r.fulfill({json:{ok:true,production_orders:[PO(1,'PO-1'),PO(2,'PO-2')],operations,summary:{}}}));
 await page.route('**/api/production-control*',r=>r.fulfill({json:{ok:true,production_orders:[{po_id:1,control_state:'CRITICAL'},{po_id:2,control_state:'ON_TRACK'}],operations:[],summary:{}}}));
 await page.route('**/api/reports/operations/1',r=>r.fulfill({json:{ok:true,report:{operation:{id:1,code:'OP1',name:'May thân',po_code:'PO-1',part_code:'P1',part_name:'Thân',standard_seconds_per_unit:60}}}}));
 await page.route('**/api/reports/operation-sessions*',r=>r.fulfill({json:{ok:true,report:{sessions:[],users:[],operations:[]}}}));
 await page.route('**/api/employees*',r=>r.fulfill({json:{ok:true,items:[]}}))}
const txt=loc=>loc.evaluate(el=>el.textContent.replace(/\s+/g,' ').trim());
for(const viewport of [{width:1366,height:768},{width:390,height:844}])test(`today mini-dashboard ${viewport.width}x${viewport.height}`,async({page})=>{
 await page.setViewportSize(viewport);await mock(page);await login(page);
 await page.evaluate(()=>openPage('overview'));await expect(page.locator('.overview-po')).toHaveCount(2);
 const row=id=>page.locator(`[data-repair-op="${id}"]`),m=(id,k)=>row(id).locator(`[data-today="${k}"]`);
 // ---- Operation block: three compact lines.
 await expect(row(1).locator('.ov-today-line')).toHaveCount(3);
 await expect(m(1,'employees').locator('b')).toHaveText('2');
 await expect(m(1,'sessions').locator('b')).toHaveText('3');
 await expect(m(1,'span')).toHaveText('07:42 → đang chạy');
 await expect(m(2,'span')).toHaveText('07:42 → 17:00');
 expect(await txt(row(1).locator('.ov-today-line').nth(1))).toBe('Đạt120Lỗi4Sửa được2Làm2g 30p');  // separators are CSS-only
 await expect(m(1,'time').locator('b')).toHaveText('2g 30p');
 await expect(m(1,'expected').locator('b')).toHaveText('2g 04p');
 await expect(m(1,'expected')).toHaveAttribute('title',/định mức 60 giây\/SP × \(Đạt \+ Lỗi\) 124 SP[\s\S]*Sửa được đã nằm trong Lỗi/);
 await expect(m(1,'productivity').locator('b')).toHaveText('104,3%');
 await expect(m(1,'productivity')).toHaveClass(/fast/);
 await expect(m(1,'delta')).toHaveText('Nhanh hơn dự kiến 6p');
 await expect(m(2,'delta')).toHaveText('Chậm hơn dự kiến 23p');
 await expect(m(2,'productivity')).toHaveClass(/slow/);
 await expect(m(2,'productivity').locator('b')).toHaveText('90,0%');
 await expect(m(3,'delta')).toHaveText('Đúng dự kiến');
 await expect(m(3,'delta')).toHaveClass(/target/);
 // No định mức: honest label, no fake %, no ĐM, no pace.
 await expect(m(4,'productivity')).toHaveText('Chưa có định mức');
 await expect(m(4,'expected')).toHaveCount(0);
 await expect(m(4,'delta')).toHaveCount(0);
 await expect(m(4,'time').locator('b')).toHaveText('25p');
 await expect(row(5).locator('[data-today-metrics]')).toContainText('Chưa có phiên làm việc');
 // OPEN wins: green line on running rows, neutral history elsewhere.
 await expect(row(1).locator('.overview-op-workers:not(.is-stopped)')).toContainText('Đang làm');
 await expect(row(1).locator('.overview-op-workers.is-stopped')).toHaveCount(0);
 await expect(row(2).locator('.overview-op-workers.is-stopped')).toHaveCount(1);
 // ---- PO strip, derived from the same rows.
 const strip=page.locator('[data-po-section="1"] [data-po-today]').first(),s=k=>strip.locator(`[data-po-today="${k}"]`);
 await expect(strip).toBeVisible();
 await expect(s('employees').locator('b')).toHaveText('4');          // union {1,2,3,4}, not 2+2+1+1
 await expect(s('sessions').locator('b')).toHaveText('8');
 await expect(s('ops').locator('b')).toHaveText('4/9');
 await expect(s('running').locator('b')).toHaveText('2');
 await expect(s('good').locator('b')).toHaveText('355');
 await expect(s('defect').locator('b')).toHaveText('14');
 await expect(s('rework').locator('b')).toHaveText('5');
 await expect(s('time').locator('b')).toHaveText('6g 35p');
 await expect(s('expected').locator('b')).toHaveText('6g 04p');
 await expect(s('productivity').locator('b')).toHaveText('95,8%');  // 23787 ÷ 24820, weighted
 await expect(s('productivity')).toHaveAttribute('title',/1 OP chưa có định mức không tính/);
 await expect(s('slow').locator('b')).toHaveText('1');
 // Collapsed PO still shows its strip in the header.
 const other=page.locator('[data-po-section="2"]');
 await expect(other).not.toHaveAttribute('open','');
 await expect(other.locator('[data-po-today]')).toHaveText(/Chưa có phiên làm việc · 0\/1 OP/);
 await expect(other.locator('[data-po-today]')).toBeVisible();
 // ---- Layout.
 expect(await page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth)).toBe(false);
 expect(await page.locator('body').evaluate(x=>x.scrollWidth>x.clientWidth)).toBe(false);
 const spill=await page.locator('[data-today-metrics],.ov-today-line,[data-po-today]').evaluateAll(els=>els.filter(el=>el.scrollWidth>el.clientWidth+1||el.getBoundingClientRect().right>el.parentElement.getBoundingClientRect().right+1).length);
 expect(spill).toBe(0);
 await expect(row(1).locator('.row-title')).toBeVisible();
 await expect(row(1).locator('.pc-progress')).toBeVisible();
 if(viewport.width>900){
  const box=await row(1).evaluate(r=>{const b=s=>r.querySelector(s).getBoundingClientRect();const kids=[...r.children];return {today:b('[data-today-metrics]'),repair:kids[4].getBoundingClientRect(),open:kids[5].getBoundingClientRect(),row:r.getBoundingClientRect()}});
  expect(box.today.left).toBeGreaterThanOrEqual(box.repair.right-1);
  expect(box.today.right).toBeLessThanOrEqual(box.open.left+1);
  expect(box.today.height).toBeLessThan(70);  // three short lines, never a fourth
  const heights=await page.locator('[data-po-section="1"] [data-today-metrics]').evaluateAll(els=>els.map(e=>e.getBoundingClientRect().height));
  expect(Math.max(...heights)).toBeLessThan(70);
  expect(box.row.height).toBeLessThan(130);  // dense row incl. the worker line, not a card
  await expect(row(1).locator('[data-open-op]')).toBeVisible();
  const sb=await strip.boundingBox();expect(sb.height).toBeLessThanOrEqual(40);  // one line at 1366
  // Double-click still opens Operation Detail.
  await row(1).dblclick({position:{x:20,y:12}});
  await expect(page.locator('.op-detail-modal')).toBeVisible();
 }else{
  // Mobile: strip groups stack; the block spans the row under the identity.
  const g=await strip.locator('.ov-po-today-g').evaluateAll(els=>els.map(e=>e.getBoundingClientRect().top));
  expect(g.length).toBe(3);expect(g[1]).toBeGreaterThan(g[0]);expect(g[2]).toBeGreaterThan(g[1]);
  const w=await row(1).evaluate(r=>({row:r.getBoundingClientRect().width,today:r.querySelector('[data-today-metrics]').getBoundingClientRect().width}));
  expect(w.today).toBeGreaterThan(w.row*0.8);
 }
 await page.screenshot({path:`test-results/overview-today-minidash-${viewport.width}x${viewport.height}.png`,fullPage:false})});
