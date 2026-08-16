const{test,expect}=require('@playwright/test');
async function login(p){await p.goto('/login');await p.request.post('/api/auth/test-auto-login');await p.goto('/app')}

test('business audit trail page renders with filters, no console/page errors',async({page})=>{
 await page.setViewportSize({width:1920,height:1080});
 const pageErrors=[];const consoleErrors=[];
 page.on('pageerror',e=>pageErrors.push(String(e)));
 page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
 await login(page);
 await page.evaluate(()=>openPage('business-audit'));
 await expect(page.locator('#baList')).toBeVisible();
 await page.waitForTimeout(500);
 await page.screenshot({path:'test-results/v72-business-audit.png',fullPage:true});
 expect(pageErrors,pageErrors.join('\n')).toEqual([]);
 expect(consoleErrors,consoleErrors.join('\n')).toEqual([]);
});

// Monitoring ownership cutover (reports/SYSTEM_LOG_AUDIT_SEPARATION.md):
// "System Health" and "Operations Center" fully moved to Deploy Agent's own
// Operations Center -- their MESFlow-side link-out pages were removed
// entirely (not just hidden), so this asserts they stay gone rather than
// testing a page that no longer exists.
test('System Health and Operations Center are not in the MESFlow menu anymore',async({page})=>{
 await page.setViewportSize({width:1920,height:1080});
 const pageErrors=[];const consoleErrors=[];
 page.on('pageerror',e=>pageErrors.push(String(e)));
 page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
 await login(page);
 await expect(page.locator('[data-page="system-health"]')).toHaveCount(0);
 await expect(page.locator('[data-page="operations-center"]')).toHaveCount(0);
 expect(await page.evaluate(()=>typeof window.renderOperationsCenter)).toBe('undefined');
 expect(pageErrors,pageErrors.join('\n')).toEqual([]);
 expect(consoleErrors,consoleErrors.join('\n')).toEqual([]);
});
