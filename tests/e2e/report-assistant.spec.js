const {test,expect}=require('@playwright/test');
const fs=require('fs');const crypto=require('crypto');
const html=fs.readFileSync('services/report-assistant/reports.html','utf8');
for(const width of [1366,390,320]){
 test(`report clarification preview and verified download ${width}`,async({page})=>{
  await page.setViewportSize({width,height:844});
  const calls=[];
  const intent={report_type:'productivity',from:'2026-10-01',to:'2026-10-10',po_id:null,operation_id:null,employee_id:null};
  const record={id:'demo-snapshot',mode:'demo',intent,generated_at:'2026-10-10T00:00:00Z',columns:['sample','good_qty'],rows:[{sample:'DEMO — DỮ LIỆU MẪU',good_qty:12}],sources:['Dữ liệu mẫu cố định'],notes:['Không truy vấn MES']};
  const csv=Buffer.from('\ufeffsample,good_qty\nDEMO,12\n');
  await page.route('https://reports.test/**',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/reports')return route.fulfill({contentType:'text/html',body:html});
   if(path==='/reports-api/status')return route.fulfill({json:{authenticated:false,mode:'demo'}});
   const body=route.request().postDataJSON();calls.push({path,body});
   if(path.endsWith('/intent'))return route.fulfill({json:{intent:{...intent,from:null,to:null},missing:['from','to'],source:'rules',notice:'Chọn ngày trước khi xem báo cáo.'}});
   if(path.endsWith('/preview'))return route.fulfill({json:record});
   if(path.endsWith('/export'))return route.fulfill({headers:{'Content-Type':'text/csv','X-Report-SHA256':crypto.createHash('sha256').update(csv).digest('hex')},body:csv});
   return route.abort();
  });
  await page.goto('https://reports.test/reports');
  await expect(page.locator('#identity')).toContainText('chỉ có báo cáo DEMO');
  await expect(page.locator('#mode option[value=live]')).toBeDisabled();
  await page.getByLabel('Yêu cầu bằng ngôn ngữ tự nhiên').fill('Năng suất nhân viên');
  await page.getByRole('button',{name:'Hiểu yêu cầu'}).click();
  await expect(page.locator('#notice')).toContainText('from, to');
  expect(calls.filter(x=>x.path.endsWith('/preview'))).toHaveLength(0);
  await page.locator('#from').fill(intent.from);await page.locator('#to').fill(intent.to);
  await page.getByRole('button',{name:'Xác nhận bộ lọc & xem trước'}).click();
  await expect(page.locator('#report-mode')).toContainText('DEMO');
  await expect(page.locator('#metadata')).toContainText('2026-10-01');
  await expect(page.locator('tbody tr')).toHaveCount(1);
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Tải CSV'}).click();
  expect((await download).suggestedFilename()).toBe('DEMO_productivity.csv');
  await expect(page.locator('#notice')).toContainText('SHA-256');
  expect(calls.find(x=>x.path.endsWith('/preview')).body).toEqual({mode:'demo',intent});
  expect(calls.find(x=>x.path.endsWith('/export')).body).toEqual({report_id:'demo-snapshot',format:'csv'});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
  await page.locator('#employee_id').fill('7');await expect(page.locator('#preview')).toBeHidden();
 });
}

test('expired live session cannot silently switch to demo or export data',async({page})=>{
 await page.route('https://reports.test/**',route=>{
  const path=new URL(route.request().url()).pathname;
  if(path==='/reports')return route.fulfill({contentType:'text/html',body:html});
  if(path.endsWith('/status'))return route.fulfill({json:{authenticated:true,mode:'live'}});
  return route.fulfill({status:401,json:{error:'Phiên hết hạn. Đăng nhập lại.'}});
 });
 await page.goto('https://reports.test/reports');
 await expect(page.locator('#mode')).toHaveValue('live');
 await page.locator('#report_type').selectOption('productivity');await page.locator('#from').fill('2026-10-01');await page.locator('#to').fill('2026-10-10');
 await page.getByRole('button',{name:'Xác nhận bộ lọc & xem trước'}).click();
 await expect(page.locator('#notice')).toContainText('Phiên hết hạn');await expect(page.locator('#preview')).toBeHidden();await expect(page.locator('#mode')).toHaveValue('live');
});
