const {test,expect}=require('@playwright/test');
const fs=require('fs');const path=require('path');
const matrix=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../tutorial/coverage-matrix.json'),'utf8'));
const exceptionScenarios=JSON.parse(fs.readFileSync(path.resolve(__dirname,'../../tutorial/exception-scenarios.json'),'utf8')).scenarios;

async function login(page){
  const state=process.env.MESFLOW_TUTORIAL_AUTH_STATE;
  if(state&&fs.existsSync(state)){
    const target=new URL(process.env.MESFLOW_BASE_URL||'http://127.0.0.1:8080');
    if(['127.0.0.1','localhost'].includes(target.hostname)){const auth=JSON.parse(fs.readFileSync(state,'utf8')),cookie=(auth.cookies||[]).find(x=>x.name==='session');if(cookie)await page.context().addCookies([{...cookie,domain:target.hostname}])}
  }else{
    const password=process.env.MESFLOW_TUTORIAL_PASSWORD||'';
    // Same as tutorial-video.spec.js/tutorial-detailed.spec.js: this runner
    // needs a real credential (auth state or password) that a plain CI
    // Playwright run never provides -- skip cleanly instead of hard-failing.
    test.skip(!password,'Thiếu MESFLOW_TUTORIAL_PASSWORD hoặc MESFLOW_TUTORIAL_AUTH_STATE (chạy qua scripts/make-user-guide-video.sh)');
    const r=await page.request.post('/api/auth/login',{data:{username:process.env.MESFLOW_TUTORIAL_USERNAME||'admin',password}});expect(r.ok(),'Đăng nhập coverage runner').toBeTruthy()
  }
  await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible();
}
async function openFeature(page,feature){
  if(feature.path){await page.goto(feature.path);return}
  if(!await page.locator('#appLayout').count()){await page.goto('/app');await expect(page.locator('#appLayout')).toBeVisible()}
  await page.evaluate(id=>window.openPage(id,document.querySelector(`[data-page="${id}"]`)),feature.page);
  await expect(page.locator('#content')).toBeVisible();
  await page.evaluate(()=>scrollTo(0,0));
}
function percentages(features){
  const dimensions=matrix.dimensions,counts=Object.fromEntries(dimensions.map(d=>[d,features.filter(f=>f.coverage.includes(d)).length]));
  const pct=n=>Math.round(n*100/features.length),critical=features.filter(f=>f.critical);
  return {feature_count:features.length,covered:features.filter(f=>f.preflight==='passed').length,missing:features.filter(f=>f.preflight!=='passed').length,happy_path_percent:pct(counts.happy_path),exception_percent:pct(counts.exception),recovery_percent:pct(counts.recovery),ui_check_percent:pct(counts.automated_assertion),functional_check_percent:pct(features.filter(f=>f.functional==='passed').length),critical_exception_percent:critical.length?Math.round(critical.filter(f=>f.coverage.includes('exception')&&f.coverage.includes('recovery')).length*100/critical.length):100,overall_percent:Math.round(Object.values(counts).reduce((a,b)=>a+b,0)*100/(features.length*dimensions.length))};
}

test('selector preflight + feature coverage',async({page},testInfo)=>{
  test.setTimeout(180000);await login(page);const results=[];
  for(const feature of matrix.features.filter(x=>x.critical)){const scenario=exceptionScenarios.find(x=>x.feature===feature.id);expect(scenario,`${feature.id}: thiếu exception tutorial`).toBeTruthy();for(const field of ['error','causes','signs','recovery','escalate'])expect(String(scenario[field]||''),`${feature.id}: thiếu ${field}`).toBeTruthy()}
  for(const source of matrix.features){
    const feature={...source,preflight:'failed',functional:'failed',issues:[],evidence:null};
    const consoleErrors=[],failedRequests=[];const onConsole=m=>{if(m.type()==='error')consoleErrors.push(m.text())},onFailed=r=>failedRequests.push({url:r.url(),error:r.failure()?.errorText});page.on('console',onConsole);page.on('requestfailed',onFailed);
    try{await openFeature(page,feature);const target=page.locator(feature.selector).first();await expect(target,`${feature.id}: selector stale`).toBeAttached({timeout:8000});await expect(target,`${feature.id}: target hidden`).toBeVisible({timeout:8000});feature.preflight='passed';
      const ui=await target.evaluate(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el),hit=document.elementFromPoint(Math.max(0,Math.min(innerWidth-1,r.left+r.width/2)),Math.max(0,Math.min(innerHeight-1,r.top+r.height/2))),clips=['hidden','clip'].includes(s.overflow)||['hidden','clip'].includes(s.overflowX)||['hidden','clip'].includes(s.overflowY);return {visible:r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden',outside:r.bottom<=0||r.right<=0||r.top>=innerHeight||r.left>=innerWidth,clipped:r.width<innerWidth&&(r.left<0||r.right>innerWidth),covered:!!hit&&!el.contains(hit)&&hit!==el,text_overflow:clips&&(el.scrollWidth>el.clientWidth+2||el.scrollHeight>el.clientHeight+2),rect:{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom},viewport:{width:innerWidth,height:innerHeight}}});
      feature.ui=ui;for(const [key,value] of Object.entries(ui))if(value===true&&key!=='visible')feature.issues.push(`UI_${key.toUpperCase()}`);if(!ui.visible)feature.issues.push('UI_NOT_VISIBLE');
      feature.evidence=testInfo.outputPath(`coverage-${feature.id}.png`);await page.screenshot({path:feature.evidence,fullPage:false});
      if(consoleErrors.length)feature.issues.push('CONSOLE_ERROR');if(failedRequests.length)feature.issues.push('FAILED_REQUEST');feature.functional=feature.issues.length?'failed':'passed';
    }catch(error){feature.issues.push(String(error?.message||error));feature.evidence=testInfo.outputPath(`coverage-${feature.id}-failed.png`);await page.screenshot({path:feature.evidence,fullPage:true}).catch(()=>{})}
    finally{page.off('console',onConsole);page.off('requestfailed',onFailed)}results.push(feature);console.log(`TUTORIAL_PREFLIGHT feature=${feature.id} status=${feature.preflight} selector=${encodeURIComponent(feature.selector)}`);
  }
  const summary=percentages(results),thresholds=matrix.thresholds,gate={happy_path:summary.happy_path_percent>=thresholds.happy_path_percent,critical_exceptions:summary.critical_exception_percent>=thresholds.critical_exception_percent,overall:summary.overall_percent>=thresholds.overall_percent,selectors:summary.missing===0,functional:results.every(x=>x.functional==='passed')};
  const report={schema_version:1,generated_at:new Date().toISOString(),thresholds,summary,gate,status:Object.values(gate).every(Boolean)?'passed':'failed',features:results};const reportPath=process.env.MESFLOW_TUTORIAL_COVERAGE_REPORT||testInfo.outputPath('tutorial-coverage-report.json');fs.mkdirSync(path.dirname(reportPath),{recursive:true});fs.writeFileSync(reportPath,JSON.stringify(report,null,2));console.log(`TUTORIAL_COVERAGE payload=${encodeURIComponent(JSON.stringify({status:report.status,summary,gate,report_path:reportPath}))}`);
  expect.soft(gate.selectors,`Selector preflight thiếu ${summary.missing} feature`).toBeTruthy();expect.soft(gate.functional,'Có UI/console/network assertion thất bại').toBeTruthy();expect.soft(gate.overall,`Coverage ${summary.overall_percent}% < ${thresholds.overall_percent}%`).toBeTruthy();
});
