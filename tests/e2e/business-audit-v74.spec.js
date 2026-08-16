const{test,expect}=require('@playwright/test');
async function login(p){await p.goto('/login');await p.request.post('/api/auth/test-auto-login');await p.goto('/app')}

// Redesigned Business Audit Trail (Nhật ký nghiệp vụ) for normal managers --
// section 16. Seeds one real WORK_SHIFTS_REPLACE audit row via a genuine
// read-then-rewrite-same PUT (never mutates the actual shift config other
// tests may depend on) so there is real, rich content to inspect beyond the
// LOGIN_SUCCESS row test-auto-login already produces. SESSION_EDIT/
// SESSION_EXCEPTION_WORKFLOW_UPDATE presentation correctness is already
// exhaustively covered with real fixtures by
// tests/test_v74_audit_presentation_unit.py and
// tests/integration/test_v74_audit_presentation.py -- this spec verifies
// the UI/visual contract, not business logic already proven elsewhere.

test('business audit trail: readable cards, Vietnamese labels, no raw JSON, drawer, no overflow, zero errors',async({page})=>{
 await page.setViewportSize({width:1920,height:1080});
 const pageErrors=[];const consoleErrors=[];
 page.on('pageerror',e=>pageErrors.push(String(e)));
 page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});

 await login(page);
 // Seed a real WORK_SHIFTS_REPLACE audit row (read current config, write
 // the exact same thing back) -- genuine application code path, zero
 // configuration drift for any other test sharing this database.
 const current=await page.request.get('/api/settings/work-shifts');
 const currentBody=await current.json();
 await page.request.put('/api/settings/work-shifts',{data:{items:currentBody.items}});

 await page.evaluate(()=>openPage('business-audit'));
 await expect(page.locator('#baList .ba-card').first()).toBeVisible();

 // No raw JSON visible initially (before opening any drawer).
 const listText=await page.locator('#baList').innerText();
 expect(listText).not.toMatch(/[{[]"[a-zA-Z_]+":/); // no {"key": ... / ["key": style raw JSON fragments
 expect(listText).not.toContain('details_json');
 expect(listText).not.toContain('exception_fingerprint');

 // Action names are Vietnamese (catalog labels), not raw ENUM_LIKE codes.
 const badges=await page.locator('.ba-action-badge').allInnerTexts();
 expect(badges.length).toBeGreaterThan(0);
 for(const b of badges)expect(b).not.toMatch(/^[A-Z_]+$/); // never a bare SNAKE_CASE code as the visible title

 await page.screenshot({path:'test-results/v74-business-audit-list.png',fullPage:true});

 // Open the detail drawer for the WORK_SHIFTS_REPLACE card we just seeded.
 const shiftCard=page.locator('.ba-card',{hasText:'Cập nhật lịch làm việc'}).first();
 await expect(shiftCard).toBeVisible();
 await shiftCard.locator('[data-open-audit]').click();
 const drawer=page.locator('.ui-drawer');
 await expect(drawer).toBeVisible();
 await expect(drawer.getByText('Thông tin chung')).toBeVisible();

 // Raw evidence is accessible ONLY inside the collapsed technical section.
 const techDetails=drawer.locator('details:has-text("Thông tin kỹ thuật")');
 await expect(techDetails).toBeVisible();
 const isOpenBefore=await techDetails.evaluate(el=>el.open);
 expect(isOpenBefore).toBe(false); // collapsed by default
 const bodyTextBeforeExpand=await drawer.locator('.ui-drawer-body').innerText();
 expect(bodyTextBeforeExpand).not.toContain('"items":[{"code"'); // raw JSON not visible while collapsed
 await techDetails.locator('summary').click();
 await expect(techDetails.locator('pre.ba-raw').first()).toBeVisible();
 const rawText=await techDetails.locator('pre.ba-raw').first().innerText();
 expect(rawText.length).toBeGreaterThan(0); // full raw evidence genuinely present once expanded

 await page.screenshot({path:'test-results/v74-business-audit-drawer.png',fullPage:true});

 // Drawer closes without losing filters/scroll -- category chip stays
 // selected and the list stays rendered after close.
 const activeChipBefore=await page.locator('.ba-chip.active').getAttribute('data-cat');
 await page.keyboard.press('Escape');
 await expect(drawer).toHaveCount(0);
 const activeChipAfter=await page.locator('.ba-chip.active').getAttribute('data-cat');
 expect(activeChipAfter).toBe(activeChipBefore);
 await expect(page.locator('#baList .ba-card').first()).toBeVisible();

 // No horizontal overflow at 1920x1080.
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth);
 expect(overflow).toBeLessThanOrEqual(1);

 expect(pageErrors,pageErrors.join('\n')).toEqual([]);
 expect(consoleErrors,consoleErrors.join('\n')).toEqual([]);
});

test('business audit trail: category filter chips work and stay Vietnamese',async({page})=>{
 await page.setViewportSize({width:1920,height:1080});
 const pageErrors=[];const consoleErrors=[];
 page.on('pageerror',e=>pageErrors.push(String(e)));
 page.on('console',m=>{if(m.type()==='error')consoleErrors.push(m.text())});
 await login(page);
 await page.evaluate(()=>openPage('business-audit'));
 const chips=await page.locator('.ba-chip').allInnerTexts();
 expect(chips).toEqual(['Tất cả','Session','Sản lượng','PO','Công đoạn','Lịch làm việc','Nhân viên','Xử lý bất thường','Quản trị']);
 await page.locator('.ba-chip',{hasText:'Quản trị'}).click();
 await expect(page.locator('.ba-chip.active')).toHaveText('Quản trị');
 await page.waitForTimeout(300);
 await page.screenshot({path:'test-results/v74-business-audit-category-filter.png',fullPage:true});
 expect(pageErrors,pageErrors.join('\n')).toEqual([]);
 expect(consoleErrors,consoleErrors.join('\n')).toEqual([]);
});
