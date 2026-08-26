const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const tutorialConfig=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../tutorial/tutorial.config.json'),'utf8'));
const terminology=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../tutorial/terminology.json'),'utf8'));
const SPEED=tutorialConfig.tutorial_speed;

const WAIT = Number(process.env.MESFLOW_TUTORIAL_WAIT_MS || 6000);
const LONG_WAIT = Number(process.env.MESFLOW_TUTORIAL_LONG_WAIT_MS || 10000);
const STEP_WAIT = Number(process.env.MESFLOW_TUTORIAL_STEP_WAIT_MS || 7500);
const MODULE = process.env.MESFLOW_TUTORIAL_MODULE || 'overview';
let stepNumber=0;
let recentSteps=[];
let qaRuntime={consoleErrors:[],pageErrors:[],failedRequests:[],unexpectedResponses:[],bugs:[],steps:[],lastCursor:{console:0,page:0,request:0,response:0}};

async function pause(page, ms=WAIT){ await page.waitForTimeout(ms); }

async function clickStep(page,locator){
  await locator.click();
  await page.waitForTimeout(SPEED.pause_after_click_ms);
}

async function typeStep(page,locator,value){
  await locator.fill('');
  await locator.pressSequentially(String(value),{delay:SPEED.typing_delay_ms});
  await page.waitForTimeout(SPEED.pause_after_click_ms);
}

function voiceText(text){
  let value=String(text||'');
  for(const [term,replacement] of Object.entries(terminology)){
    value=value.replace(new RegExp(`\\b${term.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')}\\b`,'gi'),replacement.voice_text);
  }
  return value;
}

function narrationDuration(text){
  const words=voiceText(text).trim().split(/\s+/).filter(Boolean).length;
  return Math.max(2600,Math.ceil(words/Number(SPEED.voice_words_per_minute||122)*60000));
}

async function card(page,title,body='',ms=LONG_WAIT){
  await page.evaluate(({title,body})=>{
    document.body.classList.remove('__tutorialGuided');
    document.getElementById('__tutorialPanel')?.remove();
    document.getElementById('__tutorialConnector')?.remove();
    document.getElementById('__tutorialOverlay')?.remove();
    const el=document.createElement('div');
    el.id='__tutorialOverlay';
    el.style.cssText='position:fixed;inset:0;z-index:2147483647;display:flex;align-items:center;justify-content:center;background:rgba(7,14,24,.82);color:white;font-family:Arial,sans-serif;pointer-events:none';
    el.innerHTML=`<div style="width:min(1180px,82vw);padding:52px 64px;border-radius:26px;background:rgba(16,31,51,.96);box-shadow:0 30px 90px rgba(0,0,0,.48)">
      <div style="font-size:52px;font-weight:850;line-height:1.15">${title}</div>
      ${body?`<div style="margin-top:22px;font-size:28px;line-height:1.55;color:#dce8f5">${body}</div>`:''}
    </div>`;
    document.body.appendChild(el);
  },{title,body});
  await pause(page,ms);
  await page.evaluate(()=>document.getElementById('__tutorialOverlay')?.remove());
  await pause(page,700);
}

function cleanLogValue(value){ return String(value??'').replace(/[\r\n]+/g,' ').replace(/\s+/g,' ').trim(); }

async function note(page, selector, title, explanation, detail={}){
  stepNumber+=1;
  const stepId=`${MODULE}-${String(stepNumber).padStart(2,'0')}`;
  const action=detail.action||`Quan sát vùng “${title}”`;
  const expected=detail.expected||'Xác định được dữ liệu và cách dùng vùng này trong công việc.';
  const telemetry={step_id:stepId,step_number:stepNumber,title,selector,action,expected};
  recentSteps.push(telemetry);recentSteps=recentSteps.slice(-8);
  console.log(`TUTORIAL_STEP step_id=${cleanLogValue(stepId)} number=${stepNumber} selector=${encodeURIComponent(selector)} action=${encodeURIComponent(action)} expected=${encodeURIComponent(expected)}`);
  // Tutorial selectors are explanatory, not assertions. Never let an optional,
  // hidden or virtualized element consume the whole Playwright test timeout.
  const prepared=await page.evaluate(({selector})=>{
    const candidates=[...document.querySelectorAll(selector)];
    let target=candidates.find(el=>{
      const r=el.getBoundingClientRect();
      const cs=getComputedStyle(el);
      return r.width>0 && r.height>0 && cs.display!=='none' && cs.visibility!=='hidden';
    }) || candidates[0] || null;
    if(!target)return false;
    const initial=target.getBoundingClientRect();
    if(initial.width*initial.height>innerWidth*innerHeight*.55){
      const child=[...target.querySelectorAll('.quantity-summary,h1,h2,.screen-copy,.status-card')].find(el=>{
        const r=el.getBoundingClientRect(),cs=getComputedStyle(el);
        return r.width>0&&r.height>0&&cs.display!=='none'&&cs.visibility!=='hidden';
      });
      if(child)target=child;
    }
    target.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
    target.dataset.__tutorialTarget='1';
    return true;
  },{selector}).catch(()=>false);

  if(!prepared){
    const bug={code:'TUTORIAL_SELECTOR_NOT_FOUND',step_id:stepId,selector,action,expected,actual:'Không có phần tử phù hợp trong DOM',url:page.url()};
    qaRuntime.bugs.push(bug);qaRuntime.steps.push({...telemetry,status:'failed',ui_assertions:{exists:false},evidence:null});
    console.log(`TUTORIAL_QA_BUG payload=${encodeURIComponent(JSON.stringify(bug))}`);
    return false;
  }

  await pause(page,SPEED.pause_before_step_ms);
  const spoken=detail.voice_text||voiceText(`${title}. ${explanation} ${action} ${expected}`);
  await page.evaluate(({stepId,stepNumber,title,explanation,action,expected,selector})=>{
    document.getElementById('__tutorialPanel')?.remove();
    document.getElementById('__tutorialConnector')?.remove();
    document.querySelectorAll('.__tutorialFocus').forEach(x=>x.classList.remove('__tutorialFocus'));
    const target=document.querySelector('[data-__tutorial-target="1"]');
    if(!target)return;
    target.removeAttribute('data-__tutorial-target');
    target.classList.add('__tutorialFocus');
    const r=target.getBoundingClientRect();
    const panel=document.createElement('aside');
    panel.id='__tutorialPanel';
    panel.setAttribute('aria-label','Hướng dẫn bước hiện tại');
    panel.innerHTML=`<div class="__tutorialHeading"><span>Bước ${stepNumber}</span><h2>${title}</h2></div><p class="__tutorialExplain">${explanation}</p><div class="__tutorialOutcome"><b>Áp dụng</b><span>${expected}</span></div>`;
    document.body.appendChild(panel);
    if(!document.getElementById('__tutorialStyle')){
      const style=document.createElement('style'); style.id='__tutorialStyle';
      style.textContent=`#__tutorialPanel{position:fixed;z-index:2147483647;width:min(62vw,760px);padding:16px 20px;background:#102b3f;color:#fff;border:1px solid rgba(255,255,255,.24);border-radius:9px;font-family:Inter,Arial,sans-serif;box-shadow:0 14px 34px rgba(16,43,63,.22);pointer-events:none}#__tutorialPanel .__tutorialHeading{display:flex;align-items:baseline;gap:14px;margin-bottom:8px}#__tutorialPanel .__tutorialHeading span{flex:none;font-size:12px;font-weight:700;color:#b9d1df}#__tutorialPanel h2{margin:0;font-size:20px;line-height:1.25}#__tutorialPanel p{margin:0;font-size:15px;line-height:1.45}#__tutorialPanel .__tutorialExplain{color:#edf4f8}#__tutorialPanel .__tutorialOutcome{display:flex;gap:10px;margin-top:10px;padding-top:9px;border-top:1px solid rgba(255,255,255,.18);font-size:13px;line-height:1.4}#__tutorialPanel .__tutorialOutcome b{flex:none;color:#b9d1df}.__tutorialFocus{position:relative!important;z-index:2147483645!important;outline:4px solid #e6a936!important;outline-offset:5px!important;box-shadow:0 0 0 9999px rgba(7,18,27,.32)!important;animation:__tutorialPulse .7s ease-out 1}@keyframes __tutorialPulse{0%{outline-offset:1px}100%{outline-offset:5px}}@media(max-width:900px){#__tutorialPanel{width:calc(100vw - 24px);padding:14px 16px}#__tutorialPanel h2{font-size:18px}#__tutorialPanel p{font-size:14px}}@media(prefers-reduced-motion:reduce){.__tutorialFocus{animation:none!important}*{scroll-behavior:auto!important}}`;
      document.head.appendChild(style);
    }
    const gap=18,panelWidth=Math.min(innerWidth*.62,760),panelHeight=panel.offsetHeight;
    const candidates=[
      {name:'bottom',left:(innerWidth-panelWidth)/2,top:innerHeight-panelHeight-gap},
      {name:'top',left:(innerWidth-panelWidth)/2,top:gap},
      {name:'right',left:innerWidth-panelWidth-gap,top:gap},
      {name:'left',left:gap,top:gap}
    ];
    const overlaps=c=>!(c.left+panelWidth<r.left-gap||c.left>r.right+gap||c.top+panelHeight<r.top-gap||c.top>r.bottom+gap);
    const chosen=candidates.find(c=>!overlaps(c))||candidates[1];
    panel.style.left=Math.max(12,chosen.left)+'px';panel.style.top=Math.max(12,chosen.top)+'px';
    panel.dataset.position=chosen.name;
    document.body.classList.add('__tutorialGuided');
  },{stepId,stepNumber,title,explanation,action,expected,selector});
  const screenshotDir=process.env.MESFLOW_TUTORIAL_SCREENSHOT_DIR;
  if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:`${screenshotDir}/${stepId}.png`,fullPage:false})}
  const ui=await page.evaluate(()=>{
    const target=document.querySelector('.__tutorialFocus');if(!target)return {exists:false};
    const r=target.getBoundingClientRect(),style=getComputedStyle(target),panel=document.getElementById('__tutorialPanel'),pr=panel?.getBoundingClientRect();
    const x=Math.max(0,Math.min(innerWidth-1,r.left+r.width/2)),y=Math.max(0,Math.min(innerHeight-1,r.top+r.height/2)),center=document.elementFromPoint(x,y);
    const clips=['hidden','clip'].includes(style.overflow)||['hidden','clip'].includes(style.overflowX)||['hidden','clip'].includes(style.overflowY);
    return {exists:true,visible:r.width>0&&r.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&style.opacity!=='0',outside_viewport:r.bottom<=0||r.right<=0||r.top>=innerHeight||r.left>=innerWidth,clipped:r.width<innerWidth&&r.height<innerHeight&&(r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight),covered:!!center&&!target.contains(center)&&center!==target&&!panel?.contains(center),text_overflow:clips&&(target.scrollWidth>target.clientWidth+2||target.scrollHeight>target.clientHeight+2),blocking_dialog:[...document.querySelectorAll('[role="dialog"],dialog,[aria-modal="true"]')].some(el=>el!==panel&&getComputedStyle(el).display!=='none'&&el.getBoundingClientRect().width>0),tutorial_overlay_covers_target:!!(pr&&!(pr.right<r.left||pr.left>r.right||pr.bottom<r.top||pr.top>r.bottom)),rect:{x:r.x,y:r.y,width:r.width,height:r.height},viewport:{width:innerWidth,height:innerHeight}};
  });
  const c=qaRuntime.lastCursor,browser={console_errors:qaRuntime.consoleErrors.slice(c.console),page_errors:qaRuntime.pageErrors.slice(c.page),failed_requests:qaRuntime.failedRequests.slice(c.request),unexpected_responses:qaRuntime.unexpectedResponses.slice(c.response)};
  qaRuntime.lastCursor={console:qaRuntime.consoleErrors.length,page:qaRuntime.pageErrors.length,request:qaRuntime.failedRequests.length,response:qaRuntime.unexpectedResponses.length};
  const failures=[];if(!ui.visible)failures.push('TARGET_NOT_VISIBLE');if(ui.outside_viewport)failures.push('TARGET_OUTSIDE_VIEWPORT');if(ui.clipped)failures.push('TARGET_CLIPPED');if(ui.covered)failures.push('TARGET_COVERED');if(ui.text_overflow)failures.push('TEXT_OVERFLOW');if(ui.blocking_dialog)failures.push('BLOCKING_DIALOG');if(ui.tutorial_overlay_covers_target)failures.push('TUTORIAL_OVERLAY_COVERS_TARGET');if(browser.console_errors.length)failures.push('CONSOLE_ERROR');if(browser.page_errors.length)failures.push('PAGE_ERROR');if(browser.failed_requests.length)failures.push('FAILED_REQUEST');if(browser.unexpected_responses.length)failures.push('UNEXPECTED_HTTP_STATUS');
  const evidence=screenshotDir?`${screenshotDir}/${stepId}.png`:null,stepResult={...telemetry,status:failures.length?'failed':'passed',url:page.url(),ui_assertions:ui,browser_assertions:browser,evidence};qaRuntime.steps.push(stepResult);
  console.log(`TUTORIAL_QA_STEP payload=${encodeURIComponent(JSON.stringify(stepResult))}`);
  if(failures.length){const bug={code:failures.join(','),step_id:stepId,selector,action,url:page.url(),expected,actual:{ui,browser},evidence};qaRuntime.bugs.push(bug);console.log(`TUTORIAL_QA_BUG payload=${encodeURIComponent(JSON.stringify(bug))}`)}
  await pause(page,narrationDuration(spoken));
  await pause(page,SPEED.pause_after_step_ms);
  await page.evaluate(()=>{
    document.getElementById('__tutorialPanel')?.remove();
    document.getElementById('__tutorialConnector')?.remove();
    document.querySelectorAll('.__tutorialFocus').forEach(x=>x.classList.remove('__tutorialFocus'));
    document.querySelectorAll('[data-__tutorial-target]').forEach(x=>x.removeAttribute('data-__tutorial-target'));
    document.body.classList.remove('__tutorialGuided');
  });
  return failures.length===0;
}

async function writeBugReport(page,testInfo,error){
  const step=recentSteps.at(-1)||{};
  const screenshotPath=testInfo.outputPath(`tutorial-bug-${step.step_id||MODULE}.png`);
  await page.screenshot({path:screenshotPath,fullPage:true}).catch(()=>{});
  const report={module:MODULE,step_id:step.step_id||null,action:step.action||null,selector:step.selector||null,screenshot_path:screenshotPath,exception:String(error?.stack||error),recent_log:recentSteps};
  const reportPath=testInfo.outputPath(`tutorial-bug-${step.step_id||MODULE}.json`);
  fs.writeFileSync(reportPath,JSON.stringify(report,null,2));
  console.log(`TUTORIAL_BUG_REPORT path=${reportPath} step_id=${cleanLogValue(step.step_id||MODULE)} selector=${encodeURIComponent(step.selector||'')} action=${encodeURIComponent(step.action||'')}`);
  return reportPath;
}

async function openKioskDemo(page){
  // Prefer the kiosk's own exported demo API instead of a synthetic browser click.
  // The UI button remains visible in the video; this only makes recording deterministic.
  const result=await page.evaluate(async()=>{
    const api=window.MESFlowKioskDemo;
    if(api?.open){
      api.open();
      return 'api';
    }
    const panel=document.getElementById('demo-panel');
    if(panel){
      panel.classList.add('open');
      panel.setAttribute('aria-hidden','false');
      return 'dom-fallback';
    }
    return 'missing';
  });
  expect(result,'Không tìm thấy API/panel mô phỏng QR của kiosk').not.toBe('missing');
  await expect(page.locator('#demo-panel')).toHaveClass(/open/);
  await expect(
    page.locator('#demo-content'),
    'Mô phỏng QR phải tải được dữ liệu thật hoặc dữ liệu hướng dẫn dự phòng'
  ).toBeVisible({timeout:15000});
  await expect(page.locator('#demo-loading'),'Dữ liệu mô phỏng phải tải xong trước khi chọn mã').toBeHidden({timeout:15000});
}

async function closeKioskDemo(page){
  await page.evaluate(()=>{
    if(window.MESFlowKioskDemo?.close) window.MESFlowKioskDemo.close();
    else {
      const panel=document.getElementById('demo-panel');
      panel?.classList.remove('open');
      panel?.setAttribute('aria-hidden','true');
    }
  });
  await expect(page.locator('#demo-panel')).not.toHaveClass(/open/);
}

async function selectTutorialDemoData(page){
  await page.evaluate(()=>{
    const emp=[...document.querySelectorAll('#demo-employee option')].find(x=>x.textContent.includes('TUT-E06'));
    const op=[...document.querySelectorAll('#demo-operation option')].find(x=>x.textContent.includes('TUT39-CUT'));
    if(!emp||!op)throw new Error('TUTORIAL_KIOSK_FIXTURE_MISSING');
    const employee=document.querySelector('#demo-employee'),operation=document.querySelector('#demo-operation');
    employee.value=emp.value;operation.value=op.value;
    employee.dispatchEvent(new Event('change',{bubbles:true}));
    operation.dispatchEvent(new Event('change',{bubbles:true}));
  });
}

async function login(page){
  const localCookie=process.env.MESFLOW_TUTORIAL_LOCAL_SESSION_COOKIE||'';
  if(localCookie){
    const target=new URL(process.env.MESFLOW_BASE_URL||'http://127.0.0.1:8080');
    if(!['127.0.0.1','localhost'].includes(target.hostname))throw new Error('LOCAL_TUTORIAL_COOKIE_REJECTED_FOR_REMOTE_HOST');
    await page.context().addCookies([{name:'session',value:localCookie,domain:target.hostname,path:'/',httpOnly:true,sameSite:'Lax'}]);
  }
  const authState=process.env.MESFLOW_TUTORIAL_AUTH_STATE||'';
  if(!localCookie&&authState&&fs.existsSync(authState)){
    const target=new URL(process.env.MESFLOW_BASE_URL||'http://127.0.0.1:8080');
    if(['127.0.0.1','localhost'].includes(target.hostname)){const auth=JSON.parse(fs.readFileSync(authState,'utf8')),cookie=(auth.cookies||[]).find(x=>x.name==='session');if(cookie)await page.context().addCookies([{...cookie,domain:target.hostname}])}
  }
  // The batch runner authenticates once and shares storageState across all modules.
  // This avoids repeatedly hitting the production login rate limiter.
  const me=await page.request.get('/api/auth/me');
  if(!me.ok()){
    const user=process.env.MESFLOW_TUTORIAL_USERNAME||'admin';
    const password=process.env.MESFLOW_TUTORIAL_PASSWORD||'';
    // This narration/recording spec needs a real credential (cookie, auth
    // state, or password) -- none of which a plain CI Playwright run
    // provides. Skip cleanly instead of hard-failing so the standard
    // regression suite isn't reported as broken by a tool that's only ever
    // meant to run through scripts/make-user-guide-video.sh.
    test.skip(!password,'Thiếu MESFLOW_TUTORIAL_PASSWORD (chạy qua scripts/make-user-guide-video.sh)');
    const r=await page.request.post('/api/auth/login',{data:{username:user,password}});
    const text=await r.text();
    expect(r.ok(),`Đăng nhập video hướng dẫn lỗi HTTP ${r.status()} ${text.slice(0,240)}`).toBeTruthy();
  }
  await page.goto('/app');
  await expect(page.locator('#appLayout')).toBeVisible();
}

async function open(page,id){
  await page.evaluate(id=>{
    const btn=document.querySelector(`[data-page="${id}"]`);
    if(typeof window.openPage!=='function')throw new Error('openPage unavailable');
    return window.openPage(id,btn);
  },id);
  await expect(page.locator('#content')).toBeVisible();
  await pause(page,SPEED.pause_after_navigation_ms);
}

const tours = {
  overview: async page=>{
    await open(page,'overview');
    await card(page,'Video tổng quan MESFlow','Mục tiêu: hiểu luồng lệnh sản xuất → chi tiết → công đoạn → phiên làm việc → sản lượng, cách theo dõi tiến độ và nơi xử lý vấn đề. Video này chỉ giới thiệu luồng; các video sau đi chi tiết từng màn hình.');
    await note(page,'#content .panel, #content article','Tổng quan sản xuất','Dùng để nhìn nhanh PO đang chạy, tình trạng xưởng và những điểm cần chú ý trước khi đi vào từng màn hình nghiệp vụ.');
    await note(page,'nav, .sidebar, #sidebar','Menu chức năng','Các tab được hiển thị theo quyền của user. Admin thấy toàn bộ; Manager, Supervisor, Operator và Viewer chỉ thấy những phần được cấp quyền.');
    await card(page,'Luồng sử dụng đề xuất','1) Tạo mẫu quy trình → 2) Tạo và bắt đầu lệnh sản xuất → 3) Công nhân thao tác tại trạm → 4) Theo dõi phiên làm việc và tiến độ → 5) Xử lý bất thường và lỗi → 6) Xem báo cáo và nhật ký.',LONG_WAIT);
  },
  dashboard: async page=>{
    await open(page,'dashboard');
    await card(page,'Tổng quan sản xuất theo ngày','Màn hình điều hành trong ca. Hãy bắt đầu từ ngày/ca, sau đó đọc KPI, tiến độ và danh sách session.');
    await note(page,'#dailyDate','Chọn ngày','Đổi ngày để xem đúng dữ liệu lịch sử. Khi theo dõi realtime nên để ngày hiện tại.');
    await note(page,'#dailyShift','Chọn ca','MESFlow dùng lịch làm việc và khoảng nghỉ để tính thời gian sản xuất thực tế.');
    await note(page,'#dailyKpis .daily-kpi:nth-child(1)','Nhân viên có hoạt động','Số người đã có ít nhất một phiên làm việc trong ngày và ca đang chọn. Hệ thống đếm mỗi mã nhân viên một lần; dùng để biết ca này đã huy động bao nhiêu người.',{action:'Đọc số nhân viên và số phiên làm việc bên dưới chỉ số.',expected:'Phân biệt được người đã có hoạt động với người hiện đang làm.'});
    await note(page,'#dailyKpis .daily-kpi:nth-child(2)','Đang làm việc','Số nhân viên có phiên làm việc chưa kết thúc tại thời điểm tải bảng tổng quan. Dữ liệu này cho biết lực lượng đang hoạt động ngay lúc này.',{action:'Đối chiếu số người với số phiên đang mở.',expected:'Nhận ra nhanh ca đang có bao nhiêu người thực sự làm việc và phiên nào có thể bị quên kết thúc.'});
    await note(page,'#dailyKpis .daily-kpi:nth-child(3)','Sản lượng đạt','Tổng số sản phẩm đạt của mọi phiên làm việc trong ngày và ca được chọn. Đây là kết quả thực tế do người vận hành ghi nhận, không phải số kế hoạch.',{action:'Đọc tổng sản phẩm đạt và phạm vi dữ liệu của chỉ số.',expected:'Biết dùng số thực tế này để so với kế hoạch ca và phát hiện thiếu sản lượng.'});
    await note(page,'#opTimeProgress .op-time-row:not(.head) .op-dual-progress','Tiến độ theo công đoạn','Mỗi công đoạn có hai thước đo: thời gian thực tế so với định mức và sản phẩm đạt so với số lượng kế hoạch. So sánh hai thanh để phát hiện nơi dùng nhiều thời gian nhưng đầu ra thấp.',{action:'So sánh phần trăm thời gian với phần trăm sản phẩm của một công đoạn.',expected:'Xác định được công đoạn đúng tiến độ hoặc có nguy cơ chậm và cần quản lý kiểm tra.'});
    await note(page,'#sessionTimeline, .session-timeline','Phiên làm việc theo nhân viên','Xem ai đang làm gì, thời điểm bắt đầu và phiên nào chưa kết thúc.');
  },
  po: async page=>{
    await open(page,'production-orders');
    await card(page,'Lệnh sản xuất','Video này giải thích trạng thái, cách lọc, tạo lệnh từ mẫu quy trình, bắt đầu lệnh và cách xem từng chi tiết, công đoạn.');
    await note(page,'.filter-bar, #poSearch','Lọc và tìm lệnh sản xuất','Dùng bộ lọc trạng thái và tìm kiếm theo mã để thu hẹp danh sách. Khi có nhiều đơn hàng, bước này giúp tránh mở hoặc thao tác nhầm lệnh.');
    await note(page,'#poList table, #poList','Thông tin lệnh sản xuất','Đọc mã lệnh, số lượng kế hoạch, trạng thái và tiến độ tổng. Các số này cho biết mục tiêu phải làm, lệnh đang ở giai đoạn nào và lệnh nào cần theo dõi trước.');
    await note(page,'#poList .po-actions, #addPO','Các thao tác','Tùy trạng thái và quyền, người dùng có thể tạo, sửa, bắt đầu hoặc đóng lệnh. Chỉ bắt đầu sau khi đã kiểm tra mã chi tiết và công đoạn; không xóa cưỡng bức lệnh đang chạy.');
    await card(page,'Quy trình lệnh sản xuất chuẩn','Tạo lệnh từ mẫu quy trình → kiểm tra số lượng và kế hoạch → bắt đầu lệnh → cho phép trạm bắt đầu công đoạn → theo dõi đến hoàn tất.',LONG_WAIT);
  },
  templates: async page=>{
    await open(page,'templates');
    await card(page,'Mẫu quy trình sản xuất','Mẫu quy trình là cấu trúc chuẩn để tái sử dụng: mỗi chi tiết chứa các công đoạn; mỗi công đoạn có định mức thời gian và có thể có ràng buộc.');
    await note(page,'#tplSearch','Chọn mẫu quy trình','Tìm theo mã, tên hoặc sản phẩm rồi chọn đúng mẫu trước khi chỉnh. Tránh sửa mẫu đang được dùng làm chuẩn nếu chưa hiểu ảnh hưởng.');
    await note(page,'.panel, .template-tree','Cây chi tiết / công đoạn','Chi tiết đại diện cho một chi tiết hoặc cụm; công đoạn là các bước như cắt, chấn, hàn, làm nguội, đóng gói...');
    await note(page,'input, select','Định mức','Cycle time/giây trên sản phẩm là cơ sở tính tiến độ thời gian và cảnh báo chậm.');
    await card(page,'Nguyên tắc','Template chuẩn giúp PO mới đồng nhất. Thay đổi Template không nên âm thầm làm sai PO đang chạy; luôn kiểm tra PO được sinh ra sau khi sửa.',LONG_WAIT);
  },
  material: async page=>{
    await open(page,'production-schedule');
    await card(page,'Tiến trình & Dòng vật tư','Màn hình này dùng để theo dõi luồng qua các công đoạn và xem công đoạn nào đang chặn công đoạn sau.');
    await note(page,'.toolbar','Lọc theo PO','Khi có nhiều PO, lọc đúng PO để tránh đọc nhầm tiến trình.');
    await note(page,'.panel, .material-flow, .schedule','Dòng công đoạn','Đọc từ công đoạn đầu tới cuối: đã làm, đang làm, còn lại và quan hệ phụ thuộc.');
    await note(page,'.op-dual-progress, .op-progress-line','Thời gian so với sản phẩm','Sản phẩm thấp nhưng thời gian cao là dấu hiệu cần chú ý; sản phẩm cao và thời gian hợp lý cho thấy công đoạn đang theo kế hoạch.');
  },
  sessions: async page=>{
    await open(page,'session-management');
    await card(page,'Quản lý phiên làm việc','Phiên làm việc là khoảng thời gian một nhân viên thực hiện một công đoạn. Đây là dữ liệu nền để tính thời gian, sản lượng và truy vết.');
    await note(page,'.toolbar','Tìm và lọc phiên làm việc','Lọc theo trạng thái đang mở hoặc đã đóng, nhân viên, lệnh sản xuất hoặc công đoạn để kiểm tra nhanh.');
    await note(page,'.session-accordion, .session-row, .panel','Chi tiết phiên làm việc','Xem thời điểm bắt đầu, kết thúc, nhân viên, lệnh sản xuất, chi tiết, công đoạn, trạm, thiết bị và sản lượng.');
    await note(page,'.session-detail-grid','Sản lượng','MESFlow tách Đạt, Lỗi, Lỗi sửa được và Phế. Không nên gộp các số này khi phân tích chất lượng.');
    await card(page,'Khi nào sửa phiên làm việc?','Chỉ sửa khi có bằng chứng dữ liệu sai hoặc phiên làm việc bị quên kết thúc. Việc sửa cần quyền phù hợp và nên có nhật ký truy vết.',LONG_WAIT);
  },
  exceptions: async page=>{
    await open(page,'session-exceptions');
    await card(page,'Phiên làm việc bất thường','Dữ liệu hướng dẫn tạo sẵn các trường hợp: phiên mở quá lâu, phiên dài nhưng sản lượng bằng không, thiếu trạm, chồng thời gian và thời gian không hợp lệ.');
    await note(page,'.panel, .exception-card, table','Danh sách ngoại lệ','Đọc mức độ nghiêm trọng, lỗi hoặc cảnh báo; sau đó xem nhân viên, phiên làm việc, công đoạn và nguyên nhân.');
    await note(page,'.toolbar','Bộ lọc trạng thái xử lý','Có thể lọc: mới phát hiện, đang xử lý, đã xử lý và bỏ qua để quản lý danh sách cần kiểm tra.');
    const data=await page.request.get('/api/session-exceptions?limit=100');
    if(data.ok()){
      const body=await data.json();
      const tut=(body.items||[]).find(x=>String(x.po_code||'').startsWith('TUT-')&&x.workflow_status==='NEW');
      if(tut){
        await card(page,'Bắt đầu xử lý bất thường',`Ví dụ Session #${tut.session_id}: chuyển từ mới phát hiện sang đang xử lý, giao cho quản đốc và ghi chú nguyên nhân.`,STEP_WAIT);
        await page.request.patch('/api/session-exceptions/workflow',{data:{
          items:[{session_id:tut.session_id,exception_code:tut.exception_code,exception_fingerprint:tut.exception_fingerprint}],
          workflow_status:'IN_PROGRESS',assigned_to:'Quản đốc ca A',note:'TUT39: đang đối chiếu phiếu sản xuất'
        }});
        await open(page,'session-exceptions');
        await pause(page,STEP_WAIT);
        await card(page,'Kết thúc xử lý','Sau khi có bằng chứng, trường hợp bất thường có thể chuyển sang đã xử lý kèm ghi chú. Không nên đóng cảnh báo chỉ để làm sạch màn hình.',STEP_WAIT);
        await page.request.patch('/api/session-exceptions/workflow',{data:{
          items:[{session_id:tut.session_id,exception_code:tut.exception_code,exception_fingerprint:tut.exception_fingerprint}],
          workflow_status:'RESOLVED',resolution:'VERIFIED',note:'TUT39: đã xác minh và hoàn tất xử lý'
        }});
        await open(page,'session-exceptions');
        await pause(page,STEP_WAIT);
      }
    }
  },
  employees: async page=>{
    await open(page,'employees');
    await card(page,'Nhân viên','Quản lý danh sách người thao tác MESFlow, mã nhân viên và QR/thẻ dùng tại kiosk.');
    await note(page,'.toolbar','Tìm nhân viên','Dùng mã hoặc tên để xác nhận đúng người trước khi sửa.');
    await note(page,'.panel, table','Danh sách','Kiểm tra mã, tên, trạng thái hoạt động và thông tin liên quan.');
    await open(page,'qr-print');
    await card(page,'Trung tâm QR','Sau khi dữ liệu nhân viên/Operation đúng, dùng màn hình QR để lọc và in mã phục vụ thao tác ngoài xưởng.');
    await note(page,'.toolbar','Lọc trước khi in','Chỉ chọn đúng nhóm cần in để tránh nhầm QR giữa PO/Operation/nhân viên.');
  },
  kioskAdmin: async page=>{
    await open(page,'kiosk-management');
    await card(page,'Quản lý trạm thao tác','Dành cho quản lý kỹ thuật: xem thiết bị đang trực tuyến hay mất kết nối, tín hiệu kết nối, phần mềm thiết bị, địa chỉ mạng, dữ liệu đang chờ đồng bộ và lỗi.');
    await note(page,'#kmSummary','Tóm tắt trạng thái thiết bị','Nhìn nhanh tổng số trạm, số trạm trực tuyến, chờ đăng ký, có lỗi và xung đột khi đồng bộ.');
    await note(page,'#kmSearch','Tìm thiết bị','Tìm theo tên, UUID, trạm, IP hoặc firmware.');
    await note(page,'#kmList','Danh sách trạm','Mỗi thẻ cho biết trạng thái, mạng không dây, số thao tác chờ đồng bộ và lỗi gần nhất.');
    await note(page,'#kmDetail','Lịch sử thao tác','Chọn một trạm để xem lịch sử quét mã, bắt đầu hoặc kết thúc phiên, tín hiệu kết nối, đồng bộ sau khi có mạng và lỗi theo thời gian.');
  },
  kioskUser: async page=>{
    // Nếu một lần quay trước bị ngắt, chỉ dọn phiên mở của nhân viên tutorial.
    const pre=await page.request.post('/api/kiosk-web/scan',{data:{qr:'WF|EMP|TUT-E06'}});
    if(pre.ok()){
      const body=await pre.json();
      if(body.open_session?.id){
        await page.request.post(`/api/kiosk-web/finish/${body.open_session.id}`,{data:{
          good_qty:0,defect_qty:0,rework_qty:0,
          note:'TUT44: dọn phiên tutorial còn mở trước khi quay',
          request_id:`TUT44-CLEAN-${Date.now()}`
        }});
      }
    }

    await page.goto('/kiosk?tutorial=1');
    await pause(page,1600);
    await card(page,'Trạm thao tác — hướng dẫn đầy đủ','Video này dùng chính nút “Mô phỏng quét QR” trên trạm để đi qua toàn bộ màn hình thực tế, gồm cả trường hợp quét sai thứ tự.');

    await note(page,'.kiosk-header','1. Kiểm tra trạm','Kiểm tra tên trạm, phiên bản, thời gian và trạng thái máy quét trước khi bắt đầu.');
    await note(page,'#demo-toggle','2. Mở mô phỏng quét QR','Khi đào tạo, bấm nút này để chọn mã nhân viên và công đoạn mà không cần máy quét thật.');

    await openKioskDemo(page);
    await selectTutorialDemoData(page);
    await note(page,'#demo-content','3. Chọn dữ liệu mô phỏng','Video chọn nhân viên đào tạo và một công đoạn thuộc lệnh đang chạy. Mã QR hiển thị bên dưới tương đương dữ liệu từ máy quét thật.');

    // Quét sai thứ tự để cho thấy màn hình lỗi.
    await clickStep(page,page.locator('#demo-scan-operation'));
    await pause(page,700);
    await closeKioskDemo(page);
    await expect(page.locator('#screen-error')).toHaveClass(/active/);
    await note(page,'#screen-error','4. Quét sai thứ tự','Nếu quét công đoạn trước thẻ nhân viên, trạm báo rõ lỗi và hướng dẫn quét lại đúng thứ tự.');
    await clickStep(page,page.locator('#screen-error [data-action="reset"]'));
    await expect(page.locator('#screen-ready')).toHaveClass(/active/);

    // Quét nhân viên.
    await openKioskDemo(page);
    await selectTutorialDemoData(page);
    await clickStep(page,page.locator('#demo-scan-employee'));
    await pause(page,700);
    await closeKioskDemo(page);
    await expect(page.locator('#screen-operation')).toHaveClass(/active/);
    await note(page,'#screen-operation','5. Đã nhận nhân viên','Trạm hiển thị tên và mã nhân viên. Tiếp theo quét công đoạn cần thực hiện.');

    // Quét công đoạn, giữ màn hình "đang bắt đầu" lâu hơn chỉ trong tutorial=1.
    await openKioskDemo(page);
    await selectTutorialDemoData(page);
    await clickStep(page,page.locator('#demo-scan-operation'));
    await pause(page,600);
    await closeKioskDemo(page);
    await expect(page.locator('#screen-starting')).toHaveClass(/active/);
    await note(page,'#screen-starting','6. Đang bắt đầu công việc','Trạm đang gửi yêu cầu mở phiên làm việc lên MESFlow.',{voice_text:'MESFlow đang mở phiên làm việc cho nhân viên tại công đoạn đã chọn.'});
    await expect(page.locator('#screen-started')).toHaveClass(/active/);
    await note(page,'#screen-started','7. Bắt đầu thành công','Dấu xác nhận màu xanh cho biết phiên làm việc đã được mở. Khi làm xong, quét lại thẻ nhân viên.',{voice_text:'Phiên làm việc đã mở. Khi làm xong, hãy quét lại thẻ nhân viên.'});

    // Quét lại nhân viên để kết thúc.
    await openKioskDemo(page);
    await selectTutorialDemoData(page);
    await clickStep(page,page.locator('#demo-scan-employee'));
    await pause(page,900);
    await closeKioskDemo(page);
    await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

    await typeStep(page,page.locator('#good-qty'),'12');
    await note(page,'#screen-quantity-good','8. Nhập sản phẩm đạt','Ví dụ nhập 12 sản phẩm đạt trong phiên làm việc này.');
    await clickStep(page,page.locator('#good-next'));
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

    await typeStep(page,page.locator('#defect-qty'),'3');
    await note(page,'#screen-quantity-defect','9. Nhập sản phẩm lỗi','Nhập tổng số lỗi phát sinh. Ví dụ này nhập 3 sản phẩm lỗi.');
    await clickStep(page,page.locator('#defect-next'));
    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);

    await note(page,'#screen-ask-rework','10. Có lỗi sửa được không?','Nếu không có lỗi sửa được thì chọn “Không, xong”. Video chọn “Có lỗi sửa được” để đi tiếp qua đầy đủ màn hình.');
    await clickStep(page,page.locator('#rework-yes'));
    await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);

    await typeStep(page,page.locator('#rework-qty'),'2');
    await note(page,'#screen-quantity-rework','11. Nhập số lỗi sửa được','Ví dụ có 3 sản phẩm lỗi, 2 sản phẩm sửa được, nên phần còn lại là 1 sản phẩm phế.');
    await clickStep(page,page.locator('#rework-next'));
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);

    await note(page,'#screen-finish-confirm','12. Kiểm tra trước khi xác nhận','Đọc lại: đạt 12, lỗi 3, sửa được 2, phế 1. Nếu sai thì quay lại; nếu đúng mới xác nhận.');
    await clickStep(page,page.locator('#finish-confirm-ok'));
    await expect(page.locator('#screen-finished')).toHaveClass(/active/);
    await note(page,'#screen-finished','13. Hoàn tất','Khi thấy “Đã ghi nhận”, MESFlow đã kết thúc phiên làm việc và lưu sản lượng.',{voice_text:'Đã ghi nhận. Phiên làm việc kết thúc và sản lượng đã được lưu.'});

    await card(page,'Khi mất mạng','Trạm có thể lưu tạm thao tác và đồng bộ lại khi kết nối trở lại. Nếu có xung đột, quản lý kiểm tra tại màn hình Quản lý trạm thao tác trước khi yêu cầu nhập lại.',LONG_WAIT);
  },
  calendar: async page=>{
    await open(page,'working-calendar');
    await card(page,'Lịch làm việc','Ca làm và khoảng nghỉ ảnh hưởng trực tiếp tới thời gian thực tế, KPI và tiến độ.');
    await note(page,'.panel, table','Cấu hình ca','Kiểm tra giờ bắt đầu/kết thúc và các khoảng nghỉ trước khi áp dụng cho sản xuất.');
    await card(page,'Ví dụ','Nếu nghỉ trưa 11:30–13:00 thì MESFlow phải loại khoảng này khỏi thời gian làm việc/session theo quy tắc đã cấu hình.',STEP_WAIT);
  },
  users: async page=>{
    await open(page,'users');
    await card(page,'Người dùng & Phân quyền','RBAC tách quyền theo vai trò. Không chỉ ẩn tab ở frontend; backend cũng phải từ chối API khi thiếu quyền.');
    await note(page,'.panel, table','Tài khoản người dùng','Admin quản lý tài khoản, trạng thái và role. Không dùng chung tài khoản admin cho vận hành hằng ngày.');
    await note(page,'button','Vai trò & phân quyền','Mở ma trận quyền để quyết định role nào được View/Create/Edit/Delete/Operate theo từng module.');
    await card(page,'Role mặc định','Admin: toàn quyền · Manager: kế hoạch/vận hành · Supervisor: điều hành xưởng · Operator: thao tác · Viewer: chỉ xem.',LONG_WAIT);
  },
  logs: async page=>{
    await open(page,'system-logs');
    await card(page,'Nhật ký hệ thống','Dùng khi điều tra lỗi hoặc truy vết thao tác: Nhật ký thao tác cho biết ai làm gì; phần chi tiết lỗi giúp tìm nguyên nhân theo mã truy vết.');
    await note(page,'.toolbar','Tìm kiếm','Dataset tutorial có cả trace thành công và trace lỗi đã xử lý để minh họa cách tìm nguyên nhân.');
    await note(page,'.panel, table','Chi tiết nhật ký','Đối chiếu nhật ký với phiên làm việc, lệnh sản xuất và trạm trước khi chỉnh dữ liệu.');
  },
  commonCases: async page=>{
    await card(page,'Các tình huống cần lưu ý','Video này tổng hợp các trường hợp dễ gặp ngoài xưởng bằng dữ liệu TUT39. Mục tiêu là biết nhìn dấu hiệu ở đâu và xử lý theo thứ tự nào.',LONG_WAIT);
    await open(page,'session-exceptions');
    await card(page,'1. Phiên làm việc mở quá lâu','Trường hợp này thường do công nhân quên kết thúc. Kiểm tra nhân viên, công đoạn, thời điểm bắt đầu và bằng chứng trước khi chỉnh hoặc đóng phiên.',STEP_WAIT);
    await card(page,'2. Phiên làm việc dài nhưng sản lượng bằng không','Trường hợp này có thể do quên nhập số lượng, thao tác thử hoặc dữ liệu sai. Không tự điền số khi chưa đối chiếu phiếu sản xuất.',STEP_WAIT);
    await card(page,'3. Chồng thời gian','Chồng thời gian là trường hợp nghiêm trọng vì một nhân viên không thể thực sự làm hai phiên cùng lúc. Kiểm tra lịch sử và chỉnh phiên sai thay vì sửa trực tiếp số liệu tổng hợp của công đoạn.',STEP_WAIT);
    await card(page,'4. Thời gian không hợp lệ','INVALID_TIME nghĩa là giờ kết thúc trước giờ bắt đầu. Đây là dữ liệu phải điều tra; không dùng để tính KPI cho tới khi được sửa.',STEP_WAIT);
    await open(page,'session-management');
    await card(page,'5. Đạt, lỗi và sửa được','Sản phẩm đạt, lỗi và lỗi sửa được là ba giá trị khác nhau. Số sửa được không được lớn hơn số lỗi; phần lỗi còn lại là phế theo logic hệ thống.',STEP_WAIT);
    await open(page,'kiosk-management');
    await card(page,'6. Trạm mạng yếu hoặc mất mạng','Trạm có thể tiếp tục lưu tạm thao tác khi mất mạng. Quản lý cần xem số thao tác đang chờ, tín hiệu kết nối, lỗi gần nhất và xung đột đồng bộ trước khi yêu cầu công nhân nhập lại.',STEP_WAIT);
    await card(page,'7. Xung đột khi đồng bộ','Nếu dữ liệu đồng bộ bị từ chối vì trạng thái công đoạn đã thay đổi, không được gửi lại mù quáng. Phải đối chiếu phiên trên máy chủ với dữ liệu lưu tại trạm để tránh nhân đôi sản lượng.',STEP_WAIT);
    await open(page,'system-logs');
    await card(page,'8. Có lỗi hệ thống','Dùng mã truy vết và phần chi tiết lỗi để tìm yêu cầu bị lỗi. Ghi lại thời gian, người dùng, trạm, lệnh sản xuất và công đoạn rồi mới sửa dữ liệu hoặc khởi động lại dịch vụ.',STEP_WAIT);
    await card(page,'Nguyên tắc xử lý','Ưu tiên giữ bằng chứng → xác định phạm vi → xử lý đúng đối tượng → đối chiếu và cân chỉnh số liệu khi cần → kiểm tra lại Tổng quan sản xuất, Phiên làm việc và Dòng vật tư → ghi chú kết quả.',LONG_WAIT);
  }
};

test(`MESFlow tutorial chi tiết — ${MODULE}`, async ({page},testInfo)=>{
  stepNumber=0;recentSteps=[];qaRuntime={consoleErrors:[],pageErrors:[],failedRequests:[],unexpectedResponses:[],bugs:[],steps:[],lastCursor:{console:0,page:0,request:0,response:0}};
  page.on('console',m=>{if(m.type()==='error')qaRuntime.consoleErrors.push({text:m.text(),url:m.location().url||page.url()})});
  page.on('pageerror',e=>qaRuntime.pageErrors.push({error:String(e),url:page.url()}));
  page.on('requestfailed',r=>qaRuntime.failedRequests.push({url:r.url(),method:r.method(),error:r.failure()?.errorText||'request failed'}));
  page.on('response',r=>{if(r.status()>=400)qaRuntime.unexpectedResponses.push({url:r.url(),status:r.status(),method:r.request().method()})});
  await login(page);
  await card(page,`MESFlow — ${MODULE}`,'Hướng dẫn chi tiết, chạy chậm, tập trung vào cách sử dụng thực tế.',STEP_WAIT);
  const fn=tours[MODULE];
  expect(fn,`Module tutorial không tồn tại: ${MODULE}`).toBeTruthy();
  try{await fn(page)}catch(error){await writeBugReport(page,testInfo,error);qaRuntime.bugs.push({code:'FUNCTIONAL_EXCEPTION',module:MODULE,url:page.url(),exception:String(error?.stack||error)})}
  await card(page,'Hoàn tất video','Chuyển sang video tiếp theo để học từng nhóm chức năng theo trình tự.',STEP_WAIT);
  const report={schema_version:1,module:MODULE,generated_at:new Date().toISOString(),status:qaRuntime.bugs.length?'failed':'passed',steps:qaRuntime.steps,bugs:qaRuntime.bugs,summary:{steps:qaRuntime.steps.length,passed:qaRuntime.steps.filter(x=>x.status==='passed').length,failed:qaRuntime.steps.filter(x=>x.status==='failed').length,bugs:qaRuntime.bugs.length}};
  const reportPath=testInfo.outputPath(`tutorial-qa-${MODULE}.json`);fs.writeFileSync(reportPath,JSON.stringify(report,null,2));console.log(`TUTORIAL_QA_REPORT path=${reportPath} status=${report.status} steps=${report.summary.steps} bugs=${report.summary.bugs}`);
  expect.soft(qaRuntime.bugs,`Tutorial QA phát hiện ${qaRuntime.bugs.length} lỗi; xem ${reportPath}`).toHaveLength(0);
});
