const { chromium } = require('@playwright/test');
const fs = require('fs');

(async()=>{
  const baseURL=process.env.MESFLOW_BASE_URL||'http://127.0.0.1:8080';
  const username=process.env.MESFLOW_TUTORIAL_USERNAME||'admin';
  const password=process.env.MESFLOW_TUTORIAL_PASSWORD||'';
  const out=process.env.MESFLOW_TUTORIAL_AUTH_STATE||'tutorial-auth-state.json';
  if(!password) throw new Error('Thiếu MESFLOW_TUTORIAL_PASSWORD');

  const browser=await chromium.launch({headless:true});
  const context=await browser.newContext({baseURL});
  const req=context.request;

  let last='';
  for(let attempt=1;attempt<=8;attempt++){
    const r=await req.post('/api/auth/login',{data:{username,password}});
    const text=await r.text();
    last=`HTTP ${r.status()} ${text.slice(0,300)}`;
    if(r.ok()){
      const me=await req.get('/api/auth/me');
      if(!me.ok()) throw new Error(`Login thành công nhưng /api/auth/me lỗi HTTP ${me.status()}`);
      await context.storageState({path:out});
      console.log(`[AUTH] Đăng nhập một lần thành công; đã lưu phiên dùng chung: ${out}`);
      await browser.close();
      return;
    }
    if(r.status()===429){
      const waitMs=Math.min(60000,5000*attempt);
      console.log(`[AUTH] Hệ thống giới hạn đăng nhập tạm thời; chờ ${Math.round(waitMs/1000)} giây rồi thử lại (${attempt}/8).`);
      await new Promise(r=>setTimeout(r,waitMs));
      continue;
    }
    throw new Error(`Login tutorial thất bại: ${last}`);
  }
  throw new Error(`Không đăng nhập được sau khi chờ giới hạn đăng nhập: ${last}`);
})().catch(e=>{console.error(e.stack||e);process.exit(1);});
