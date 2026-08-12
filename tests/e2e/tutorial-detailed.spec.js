const { test, expect } = require('@playwright/test');

const WAIT = Number(process.env.MESFLOW_TUTORIAL_WAIT_MS || 6000);
const LONG_WAIT = Number(process.env.MESFLOW_TUTORIAL_LONG_WAIT_MS || 10000);
const STEP_WAIT = Number(process.env.MESFLOW_TUTORIAL_STEP_WAIT_MS || 7500);
const MODULE = process.env.MESFLOW_TUTORIAL_MODULE || 'overview';

async function pause(page, ms=WAIT){ await page.waitForTimeout(ms); }

async function card(page,title,body='',ms=LONG_WAIT){
  await page.evaluate(({title,body})=>{
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

async function note(page, selector, title, body){
  // Tutorial selectors are explanatory, not assertions. Never let an optional,
  // hidden or virtualized element consume the whole Playwright test timeout.
  const prepared=await page.evaluate(({selector})=>{
    const candidates=[...document.querySelectorAll(selector)];
    const target=candidates.find(el=>{
      const r=el.getBoundingClientRect();
      const cs=getComputedStyle(el);
      return r.width>0 && r.height>0 && cs.display!=='none' && cs.visibility!=='hidden';
    }) || candidates[0] || null;
    if(!target)return false;
    target.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});
    target.dataset.__tutorialTarget='1';
    return true;
  },{selector}).catch(()=>false);

  if(!prepared){
    await card(page,title,body,STEP_WAIT);
    return;
  }

  await pause(page,350);
  await page.evaluate(({title,body})=>{
    document.getElementById('__tutorialNote')?.remove();
    document.querySelectorAll('.__tutorialFocus').forEach(x=>x.classList.remove('__tutorialFocus'));
    const target=document.querySelector('[data-__tutorial-target="1"]');
    if(!target)return;
    target.removeAttribute('data-__tutorial-target');
    target.classList.add('__tutorialFocus');
    const r=target.getBoundingClientRect();
    const note=document.createElement('div');
    note.id='__tutorialNote';
    note.style.cssText='position:fixed;z-index:2147483647;width:520px;padding:22px 26px;border-radius:18px;background:#0d2035;color:#fff;font-family:Arial,sans-serif;box-shadow:0 18px 60px rgba(0,0,0,.4);pointer-events:none';
    const left=Math.min(window.innerWidth-550,Math.max(20,r.right+24));
    const top=Math.min(window.innerHeight-230,Math.max(20,r.top));
    note.style.left=left+'px'; note.style.top=top+'px';
    note.innerHTML=`<div style="font-size:26px;font-weight:800">${title}</div><div style="font-size:20px;line-height:1.5;margin-top:10px;color:#d9e6f2">${body}</div>`;
    document.body.appendChild(note);
    if(!document.getElementById('__tutorialStyle')){
      const style=document.createElement('style'); style.id='__tutorialStyle';
      style.textContent='.__tutorialFocus{position:relative!important;z-index:2147483646!important;outline:5px solid #ffbd2e!important;outline-offset:5px!important;box-shadow:0 0 0 9999px rgba(3,10,18,.48)!important}';
      document.head.appendChild(style);
    }
  },{selector,title,body});
  await pause(page,STEP_WAIT);
  await page.evaluate(()=>{
    document.getElementById('__tutorialNote')?.remove();
    document.querySelectorAll('.__tutorialFocus').forEach(x=>x.classList.remove('__tutorialFocus'));
    document.querySelectorAll('[data-__tutorial-target]').forEach(x=>x.removeAttribute('data-__tutorial-target'));
  });
  await pause(page,700);
}

async function login(page){
  // The batch runner authenticates once and shares storageState across all modules.
  // This avoids repeatedly hitting the production login rate limiter.
  const me=await page.request.get('/api/auth/me');
  if(!me.ok()){
    const user=process.env.MESFLOW_TUTORIAL_USERNAME||'admin';
    const password=process.env.MESFLOW_TUTORIAL_PASSWORD||'';
    expect(password,'Thiếu MESFLOW_TUTORIAL_PASSWORD').toBeTruthy();
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
  await pause(page,1600);
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
    await note(page,'.daily-kpis, #dailyKpis','Chỉ số trong ca','Đọc tổng số phiên làm việc, số người đang làm, sản lượng và tình trạng theo ca.');
    await note(page,'.op-dual-progress, .op-progress-line','Hai loại tiến độ','Thanh mảnh thể hiện tiến độ thời gian; thanh đặc thể hiện tiến độ sản phẩm. So sánh hai thanh để nhận ra công đoạn đang chậm hay thiếu sản lượng.');
    await note(page,'#sessionTimeline, .session-timeline','Phiên làm việc theo nhân viên','Xem ai đang làm gì, thời điểm bắt đầu và phiên nào chưa kết thúc.');
  },
  po: async page=>{
    await open(page,'production-orders');
    await card(page,'Lệnh sản xuất','Video này giải thích trạng thái, cách lọc, tạo lệnh từ mẫu quy trình, bắt đầu lệnh và cách xem từng chi tiết, công đoạn.');
    await note(page,'.toolbar','Lọc và tìm PO','Dùng bộ lọc trạng thái và tìm kiếm thay vì cuộn toàn bộ danh sách.');
    await note(page,'.po-card, .panel','Thẻ PO','Đọc mã PO, kế hoạch, trạng thái và tiến độ tổng trước khi mở chi tiết.');
    await note(page,'button','Các thao tác','Tùy trạng thái và quyền, các nút cho phép tạo, sửa, Start, đóng hoặc thao tác quản trị. Production không nên dùng Force Delete.');
    await card(page,'Quy trình lệnh sản xuất chuẩn','Tạo lệnh từ mẫu quy trình → kiểm tra số lượng và kế hoạch → bắt đầu lệnh → cho phép trạm bắt đầu công đoạn → theo dõi đến hoàn tất.',LONG_WAIT);
  },
  templates: async page=>{
    await open(page,'templates');
    await card(page,'Mẫu quy trình sản xuất','Mẫu quy trình là cấu trúc chuẩn để tái sử dụng: mỗi chi tiết chứa các công đoạn; mỗi công đoạn có định mức thời gian và có thể có ràng buộc.');
    await note(page,'.toolbar','Chọn Template','Chọn đúng template trước khi chỉnh. Tránh sửa template đang được dùng làm chuẩn nếu chưa hiểu ảnh hưởng.');
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

    await page.locator('#demo-toggle').click();
    await expect(page.locator('#demo-panel')).toHaveClass(/open/);
    await expect(page.locator('#demo-content'),'Mô phỏng QR phải tải được dữ liệu thật hoặc dữ liệu hướng dẫn dự phòng').toBeVisible({timeout:15000});
    await page.evaluate(()=>{
      const emp=[...document.querySelectorAll('#demo-employee option')].find(x=>x.textContent.includes('TUT-E06'));
      const op=[...document.querySelectorAll('#demo-operation option')].find(x=>x.textContent.includes('TUT39-CUT'));
      if(!emp) throw new Error('Không tìm thấy TUT-E06. Hãy tạo dữ liệu hướng dẫn trước.');
      if(!op) throw new Error('Không tìm thấy TUT39-CUT. Hãy tạo dữ liệu hướng dẫn trước.');
      const e=document.querySelector('#demo-employee'),o=document.querySelector('#demo-operation');
      e.value=emp.value;o.value=op.value;
      e.dispatchEvent(new Event('change',{bubbles:true}));
      o.dispatchEvent(new Event('change',{bubbles:true}));
    });
    await note(page,'#demo-content','3. Chọn dữ liệu mô phỏng','Video chọn nhân viên đào tạo và một công đoạn thuộc lệnh đang chạy. Mã QR hiển thị bên dưới tương đương dữ liệu từ máy quét thật.');

    // Quét sai thứ tự để cho thấy màn hình lỗi.
    await page.locator('#demo-scan-operation').click();
    await pause(page,700);
    await page.locator('#demo-close').click();
    await expect(page.locator('#screen-error')).toHaveClass(/active/);
    await note(page,'#screen-error','4. Quét sai thứ tự','Nếu quét công đoạn trước thẻ nhân viên, trạm báo rõ lỗi và hướng dẫn quét lại đúng thứ tự.');
    await page.locator('#screen-error [data-action="reset"]').click();
    await expect(page.locator('#screen-ready')).toHaveClass(/active/);

    // Quét nhân viên.
    await page.locator('#demo-toggle').click();
    await expect(page.locator('#demo-panel')).toHaveClass(/open/);
    await expect(page.locator('#demo-content')).toBeVisible({timeout:15000});
    await page.locator('#demo-scan-employee').click();
    await pause(page,700);
    await page.locator('#demo-close').click();
    await expect(page.locator('#screen-operation')).toHaveClass(/active/);
    await note(page,'#screen-operation','5. Đã nhận nhân viên','Trạm hiển thị tên và mã nhân viên. Tiếp theo quét công đoạn cần thực hiện.');

    // Quét công đoạn, giữ màn hình "đang bắt đầu" lâu hơn chỉ trong tutorial=1.
    await page.locator('#demo-toggle').click();
    await expect(page.locator('#demo-panel')).toHaveClass(/open/);
    await expect(page.locator('#demo-content')).toBeVisible({timeout:15000});
    await page.locator('#demo-scan-operation').click();
    await pause(page,600);
    await page.locator('#demo-close').click();
    await expect(page.locator('#screen-starting')).toHaveClass(/active/);
    await note(page,'#screen-starting','6. Đang bắt đầu công việc','Trạm đang gửi yêu cầu mở phiên làm việc lên MESFlow.');
    await expect(page.locator('#screen-started')).toHaveClass(/active/);
    await note(page,'#screen-started','7. Bắt đầu thành công','Dấu xác nhận màu xanh cho biết phiên làm việc đã được mở. Khi làm xong, quét lại thẻ nhân viên.');

    // Quét lại nhân viên để kết thúc.
    await page.locator('#demo-toggle').click();
    await expect(page.locator('#demo-panel')).toHaveClass(/open/);
    await expect(page.locator('#demo-content')).toBeVisible({timeout:15000});
    await page.locator('#demo-scan-employee').click();
    await pause(page,900);
    await page.locator('#demo-close').click();
    await expect(page.locator('#screen-quantity-good')).toHaveClass(/active/);

    await page.locator('#good-qty').fill('12');
    await note(page,'#screen-quantity-good','8. Nhập sản phẩm đạt','Ví dụ nhập 12 sản phẩm đạt trong phiên làm việc này.');
    await page.locator('#good-next').click();
    await expect(page.locator('#screen-quantity-defect')).toHaveClass(/active/);

    await page.locator('#defect-qty').fill('3');
    await note(page,'#screen-quantity-defect','9. Nhập sản phẩm lỗi','Nhập tổng số lỗi phát sinh. Ví dụ này nhập 3 sản phẩm lỗi.');
    await page.locator('#defect-next').click();
    await expect(page.locator('#screen-ask-rework')).toHaveClass(/active/);

    await note(page,'#screen-ask-rework','10. Có lỗi sửa được không?','Nếu không có lỗi sửa được thì chọn “Không, xong”. Video chọn “Có lỗi sửa được” để đi tiếp qua đầy đủ màn hình.');
    await page.locator('#rework-yes').click();
    await expect(page.locator('#screen-quantity-rework')).toHaveClass(/active/);

    await page.locator('#rework-qty').fill('2');
    await note(page,'#screen-quantity-rework','11. Nhập số lỗi sửa được','Ví dụ có 3 sản phẩm lỗi, 2 sản phẩm sửa được, nên phần còn lại là 1 sản phẩm phế.');
    await page.locator('#rework-next').click();
    await expect(page.locator('#screen-finish-confirm')).toHaveClass(/active/);

    await note(page,'#screen-finish-confirm','12. Kiểm tra trước khi xác nhận','Đọc lại: đạt 12, lỗi 3, sửa được 2, phế 1. Nếu sai thì quay lại; nếu đúng mới xác nhận.');
    await page.locator('#finish-confirm-ok').click();
    await expect(page.locator('#screen-finished')).toHaveClass(/active/);
    await note(page,'#screen-finished','13. Hoàn tất','Khi thấy “Đã ghi nhận”, MESFlow đã kết thúc phiên làm việc và lưu sản lượng.');

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

test(`MESFlow tutorial chi tiết — ${MODULE}`, async ({page})=>{
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await login(page);
  await card(page,`MESFlow — ${MODULE}`,'Hướng dẫn chi tiết, chạy chậm, tập trung vào cách sử dụng thực tế.',STEP_WAIT);
  const fn=tours[MODULE];
  expect(fn,`Module tutorial không tồn tại: ${MODULE}`).toBeTruthy();
  await fn(page);
  await card(page,'Hoàn tất video','Chuyển sang video tiếp theo để học từng nhóm chức năng theo trình tự.',STEP_WAIT);
  expect(errors,`Page errors: ${errors.join(' | ')}`).toEqual([]);
});
