const{test,expect}=require('@playwright/test');
const{openFilters}=require('./helpers/filters');

// Production Trace — dòng thời gian V68 (sự kiện, quantity/rework, change audit)
// và REQ-TRACE-001: màn hình LUÔN mở sẵn một PO thay vì bắt người dùng bấm chọn.
//
// Phần lớn bài dưới đây kiểm đúng một câu hỏi: "khi mở màn hình ra thì đang xem
// PO nào, và ai quyết định điều đó" — URL, thứ hạng PO của server, hay lựa chọn
// của chính người dùng.

async function login(page){await page.goto('/login');await page.request.post('/api/auth/test-auto-login');/* /login khi đã có phiên tự chuyển sang /app; đợi xong rồi mới goto tiếp */await page.waitForURL(/\/app/,{timeout:20000}).catch(()=>{});await page.goto('/app')}

const PO_RUNNING={id:11,code:'PO-RUN-11',product:'Khung A',status:'IN_PROGRESS',planned_quantity:200,open_sessions:2,operation_count:3};
const PO_IDLE={id:22,code:'PO-IDLE-22',product:'Vỏ B',status:'RELEASED',planned_quantity:100,open_sessions:0,operation_count:2};
const PO_DONE={id:3,code:'PO-DONE-03',product:'Nắp C',status:'COMPLETED',planned_quantity:50,open_sessions:0,operation_count:1};
// `/api/production-orders` trả về theo id TĂNG DẦN, đúng như repository thật.
const ALL_POS=[PO_DONE,PO_RUNNING,PO_IDLE];
// Bộ chọn của Kiosk/Dashboard chỉ xếp hạng PO đang mở: đang có session mở trước.
const OPEN_POS=[PO_RUNNING,PO_IDLE];

const events=[
 {id:'9',event_type:'VALUE_CHANGED',category:'CHANGE',occurred_at:'2026-08-13T08:40:00Z',actor_id:1,actor_name:'Supervisor A',po_id:11,part_id:2,operation_id:3,session_id:77,title:'Điều chỉnh sản lượng Session',description:'Double scan correction',quantity_delta:null,metadata:{before:{good_qty:120},after:{good_qty:118}},correlation_id:'corr-fix',session_trace_id:'',source:'AUDIT'},
 {id:'8',event_type:'REPAIRABLE_DEFECT_RECORDED',category:'REWORK',occurred_at:'2026-08-13T08:35:00Z',actor_name:'Nguyễn Văn A',po_id:11,part_id:2,operation_id:3,session_id:77,title:'Ghi nhận lỗi sửa được',description:'',quantity_delta:2,metadata:{movement_id:8},correlation_id:'corr-finish',session_trace_id:'trace-77',source:'NATIVE'},
 {id:'7',event_type:'DEFECT_QUANTITY_RECORDED',category:'DEFECT',occurred_at:'2026-08-13T08:34:00Z',actor_name:'Nguyễn Văn A',po_id:11,part_id:2,operation_id:3,session_id:77,title:'Ghi nhận sản lượng lỗi',description:'',quantity_delta:3,metadata:{movement_id:7},correlation_id:'corr-finish',session_trace_id:'trace-77',source:'NATIVE'},
 {id:'6',event_type:'GOOD_QUANTITY_RECORDED',category:'QUANTITY',occurred_at:'2026-08-13T08:33:00Z',actor_name:'Nguyễn Văn A',po_id:11,part_id:2,operation_id:3,session_id:77,title:'Ghi nhận sản lượng đạt',description:'',quantity_delta:20,metadata:{movement_id:6},correlation_id:'corr-finish',session_trace_id:'trace-77',source:'NATIVE'},
 {id:'5',event_type:'SESSION_STARTED',category:'SESSION',occurred_at:'2026-08-13T07:30:00Z',actor_name:'Nguyễn Văn A',po_id:11,part_id:2,operation_id:3,session_id:77,title:'Session bắt đầu',description:'OP Chấn',quantity_delta:null,metadata:{employee_id:4},correlation_id:'corr-start',session_trace_id:'trace-77',source:'NATIVE'}];

/**
 * Mock cả ba nguồn mà màn hình dùng để quyết định PO đang xem.
 *
 * `all`/`open` truyền vào để dựng đúng các thế giới cần thử: có PO đang chạy,
 * chỉ còn PO đã đóng sổ, hoặc chưa có PO nào.
 */
async function mock(page,{all=ALL_POS,open=OPEN_POS}={}){
  const seen={traceUrls:[]};
  await page.route(/\/api\/production-orders\?limit=1000/,r=>r.fulfill({json:{ok:true,items:all}}));
  // Glob phải có '*' ở cuối: bộ chọn gửi kèm ?include_id= khi URL có po_id.
  await page.route('**/api/kiosk-board/po-options*',r=>{
    const include=new URL(r.request().url()).searchParams.get('include_id');
    const pinned=include?all.filter(x=>String(x.id)===include):[];
    // include_id GHIM PO được hỏi lên đầu, đúng như ORDER BY của server thật.
    r.fulfill({json:{ok:true,items:[...pinned,...open.filter(x=>!pinned.includes(x))],total:open.length,truncated:false,query:''}});
  });
  await page.route(/\/api\/production-orders\/(\d+)\/trace.*/,r=>{
    const url=r.request().url();seen.traceUrls.push(url);
    const id=Number(url.match(/production-orders\/(\d+)\/trace/)[1]);
    const po=all.find(x=>x.id===id);
    if(!po)return r.fulfill({status:404,json:{ok:false,error:'NOT_FOUND',message:'Không tìm thấy Production Order'}});
    r.fulfill({json:{ok:true,context:{po_id:po.id,po_code:po.code,status:po.status,planned_quantity:po.planned_quantity},events:po.id===11?events:[],next_before:null,has_more:false,coverage:{native_from_version:'68.0.0.1'}}});
  });
  await page.route(/\/api\/production-orders\/(\d+)\/quantity-history/,r=>r.fulfill({json:{ok:true,items:[],reconciliation:{current:{good_qty:118,defect_qty:3,rework_qty:2},ledger:{good_qty:118,defect_qty:3,rework_qty:2},matches:true}}}));
  // PO đơn lẻ: dùng cho lần "hỏi thẳng server" khi po_id nằm ngoài cửa sổ danh sách.
  await page.route(/\/api\/production-orders\/(\d+)$/,r=>{
    const id=Number(r.request().url().match(/production-orders\/(\d+)$/)[1]);
    const po=all.find(x=>x.id===id);
    if(!po)return r.fulfill({status:404,json:{ok:false,error:'NOT_FOUND',message:'Không tìm thấy Production Order'}});
    r.fulfill({json:{ok:true,item:po}});
  });
  return seen;
}

const openTrace=async(page,query='')=>{await page.goto(`/app?page=production-trace${query}`)};
const noHorizontalScroll=async page=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);

test.describe('REQ-TRACE-001 — luôn mở sẵn một Production Order',()=>{
  test('không có po_id trong URL thì tự chọn PO đang có session mở',async({page})=>{
    await login(page);await mock(page);
    await openTrace(page);
    await expect(page.locator('#ptPo')).toHaveValue(String(PO_RUNNING.id));
    await expect(page.locator('.trace-summary')).toContainText(PO_RUNNING.code);
    // Không còn màn "chưa chọn PO" giả: có PO là có dòng thời gian.
    await expect(page.locator('.trace-event')).toHaveCount(5);
    await expect(page.locator('.ui-empty')).toHaveCount(0);
    // PO tự chọn cũng phải vào URL, nếu không F5 lại quay về ô trống.
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_RUNNING.id}`));
  });

  test('bộ chọn xếp PO đang chạy trước, PO đã đóng sổ vẫn chọn được',async({page})=>{
    await login(page);await mock(page);
    await openTrace(page);
    const values=await page.locator('#ptPo option').evaluateAll(o=>o.map(x=>x.value));
    expect(values).toEqual([String(PO_RUNNING.id),String(PO_IDLE.id),String(PO_DONE.id)]);
    // Không còn option rỗng "Chọn PO cần truy vết".
    expect(values).not.toContain('');
    await expect(page.locator('#ptPo option').first()).toContainText('2 đang làm');
  });

  test('po_id hợp lệ trong URL thắng tất cả, kể cả PO đã COMPLETED',async({page})=>{
    await login(page);await mock(page);
    await openTrace(page,`&po_id=${PO_DONE.id}`);
    await expect(page.locator('#ptPo')).toHaveValue(String(PO_DONE.id));
    await expect(page.locator('.trace-summary')).toContainText(PO_DONE.code);
    await expect(page.locator('#ptNotice')).toBeHidden();
  });

  test('người dùng đã tự chọn thì không bị nhảy về PO mặc định',async({page})=>{
    await login(page);await mock(page);
    await openTrace(page);
    await page.selectOption('#ptPo',String(PO_IDLE.id));
    await expect(page.locator('.trace-summary')).toContainText(PO_IDLE.code);
    await expect(page).toHaveURL(new RegExp(`po_id=${PO_IDLE.id}`));
    // F5 và Back/Forward đều phải giữ đúng PO người dùng chọn.
    await page.reload();
    await expect(page.locator('#ptPo')).toHaveValue(String(PO_IDLE.id));
    await expect(page.locator('.trace-summary')).toContainText(PO_IDLE.code);
  });

  test('po_id không tồn tại thì NÓI RA rồi mới hiển thị PO gần nhất',async({page})=>{
    await login(page);await mock(page);
    await openTrace(page,'&po_id=987654');
    await expect(page.locator('#ptNotice')).toBeVisible();
    await expect(page.locator('#ptNotice')).toContainText('987654');
    await expect(page.locator('#ptPo')).toHaveValue(String(PO_RUNNING.id));
  });

  test('chỉ còn PO đã đóng sổ thì vẫn mở PO mới nhất, không để trống',async({page})=>{
    await login(page);await mock(page,{all:[PO_DONE],open:[]});
    await openTrace(page);
    await expect(page.locator('#ptPo')).toHaveValue(String(PO_DONE.id));
    await expect(page.locator('.trace-summary')).toContainText(PO_DONE.code);
  });

  test('trạng thái rỗng chỉ khi hệ thống thật sự chưa có PO nào',async({page})=>{
    await login(page);await mock(page,{all:[],open:[]});
    await openTrace(page);
    await expect(page.locator('.ui-empty')).toContainText('Chưa có Production Order nào');
    // Hình dạng trang KHÔNG đổi: bộ chọn vẫn ở đó, chỉ là không có gì để chọn.
    await expect(page.locator('#ptPo')).toBeDisabled();
    await expect(page.locator('.trace-filters')).toBeHidden();
    await expect(page).not.toHaveURL(/po_id=/);
  });

  for(const[w,h]of[[390,844],[1366,768],[1920,1080]]){
    test(`không vỡ layout ở ${w}×${h}`,async({page})=>{
      await page.setViewportSize({width:w,height:h});
      await login(page);await mock(page);
      await openTrace(page);
      await expect(page.locator('.trace-summary')).toBeVisible();
      await expect(page.locator('.trace-event').first()).toBeVisible();
      // <=700px bộ lọc gập lại (core/ui.js), nên phải mở ra mới thấy bộ chọn PO.
      await openFilters(page);
      await expect(page.locator('#ptPo')).toBeVisible();
      // Dải danh mục: hiện ra khi đã có dữ liệu, và không tab nào chiếm trọn
      // hàng ở màn hẹp (.mf-tabs cuộn ngang thay vì wrap -- xem ui.css).
      await expect(page.locator('.trace-filters')).toBeVisible();
      const tabWidths=await page.locator('.pt-filter').evaluateAll(n=>n.map(x=>x.getBoundingClientRect().width));
      for(const tw of tabWidths)expect(tw).toBeLessThan(w*0.8);
      await noHorizontalScroll(page);
      await page.screenshot({path:`test-results/trace-default-po-${w}.png`,fullPage:true});
    });
  }
});

test('PO Production Trace, quantity/rework và Change Audit',async({page})=>{
  await page.setViewportSize({width:1920,height:1080});
  await login(page);await mock(page);
  await openTrace(page);
  await expect(page.locator('.trace-event')).toHaveCount(5);
  await expect(page.locator('.trace-summary')).toContainText('118');
  await page.screenshot({path:'test-results/v68-po-production-trace.png',fullPage:true});
  await page.locator('.cat-rework details summary').click();
  await page.screenshot({path:'test-results/v68-expanded-quantity-rework.png',fullPage:true});
  await expect(page.locator('.trace-diff')).toContainText('120 → 118');
  await page.screenshot({path:'test-results/v68-change-audit.png',fullPage:true});
  await noHorizontalScroll(page);
});

test('Session Drawer dùng V68 normalized timeline',async({page})=>{await page.setViewportSize({width:1366,height:768});await login(page);await page.route('/api/session-management/77',r=>r.fulfill({json:{ok:true,session:{session_id:77,status:'CLOSED',employee_name:'Nguyễn Văn A',employee_code:'NV-001',po_code:'PO-260813-001',part_code:'P-01',operation_code:'OP-CHAN',operation_name:'Chấn',started_at:'2026-08-13T07:30:00Z',ended_at:'2026-08-13T08:40:00Z',duration_seconds:4200,good_qty:118,defect_qty:3,rework_qty:2},activity:[],exceptions:[],reviews:[]}}));await page.route(/\/api\/sessions\/77\/trace.*/,r=>r.fulfill({json:{ok:true,events,context:{},has_more:false}}));await page.evaluate(()=>SessionDetailDrawer.open(77));await expect(page.locator('.trace-mini')).toContainText('Ghi nhận sản lượng đạt');await page.screenshot({path:'test-results/v68-session-drawer-timeline.png'});await noHorizontalScroll(page)});
