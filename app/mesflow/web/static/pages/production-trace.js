const ProductionTrace=(()=>{
  let poId=null,before=null,allEvents=[],poOptions=[],notice='';
  const cats=[['','Tất cả'],['PO,OPERATION','Sản xuất'],['SESSION','Session'],['QUANTITY','Sản lượng'],['DEFECT','NG'],['REWORK','Rework'],['EXCEPTION','Ngoại lệ'],['CHANGE','Thay đổi']];
  const day=d=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'full'}).format(new Date(d));
  const technical=m=>`<details><summary>Chi tiết kỹ thuật</summary><pre>${esc(JSON.stringify(m||{},null,2))}</pre></details>`;
  const auditDiff=e=>{const m=e.metadata||{},parse=x=>{try{return typeof x==='string'?JSON.parse(x):x||{}}catch(_){return {}}};const a=parse(m.before),b=parse(m.after);const ignored=new Set(['updated_at','created_at']);const keys=[...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>!ignored.has(k)&&JSON.stringify(a[k])!==JSON.stringify(b[k]));return keys.length?`<div class="trace-diff">${keys.map(k=>`<span><small>${esc(k.replaceAll('_',' '))}</small><b>${esc(a[k]??'—')} → ${esc(b[k]??'—')}</b></span>`).join('')}</div>`:''};
  const item=e=>`<article class="trace-event cat-${e.category.toLowerCase()}"><time>${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',timeStyle:'medium'}).format(new Date(e.occurred_at))}</time><i></i><div><header><b>${esc(e.title)}</b><span>${esc(e.category)}</span>${e.source==='LEGACY_DERIVED'?'<em>Dữ liệu suy ra</em>':''}</header><p>${esc(e.description||'')}</p>${e.quantity_delta!=null?`<strong class="trace-qty ${e.quantity_delta<0?'negative':''}">${e.quantity_delta>0?'+':''}${e.quantity_delta}</strong>`:''}${e.category==='CHANGE'?auditDiff(e):''}<small>${esc(e.actor_name||'Hệ thống')}${e.operation_id?` · OP #${e.operation_id}`:''}${e.session_id?` · Session #${e.session_id}`:''}</small>${technical(e.metadata)}</div></article>`;
  const draw=()=>{const groups=new Map;for(const e of allEvents){const d=day(e.occurred_at);if(!groups.has(d))groups.set(d,[]);groups.get(d).push(e)}document.getElementById('ptTimeline').innerHTML=allEvents.length?[...groups].map(([d,rows])=>`<section class="trace-day"><h3>${esc(d)}</h3>${rows.map(item).join('')}</section>`).join(''):'<div class="empty">Chưa có sự kiện trace phù hợp.</div>'};

  // --- Chọn PO mặc định ----------------------------------------------------
  //
  // Production Trace chỉ trả lời được điều gì khi đang xem MỘT PO. Bản đầu mở
  // ra với bộ chọn RỖNG: màn hình nói "Chưa chọn Production Order" trong khi
  // xưởng vẫn đang chạy, và người dùng phải bấm một cú không mang thông tin
  // nào trước khi thấy bất cứ thứ gì. Trạng thái rỗng ở đó không mô tả dữ
  // liệu, nó chỉ mô tả việc màn hình chưa được hỏi -- đúng kiểu "không có gì
  // ở đây" giả mà REQ-UI-010 cấm.
  //
  // Nên màn này LUÔN mở sẵn một PO, theo đúng thứ tự này:
  //
  //   1. `?po_id=` trong URL THẮNG TẤT CẢ, kể cả khi PO đó đã đóng sổ: đó là
  //      PO mà người dùng (hoặc cái link họ nhận được) đã chọn. Truy vết một
  //      PO đã xong là việc bình thường của màn này.
  //   2. Chưa có thì lấy PO đứng đầu bộ chọn dùng chung với Kiosk/Dashboard
  //      (`/api/kiosk-board/po-options`): đang có session mở -> hoạt động gần
  //      đây -> hạn gần -> mới nhất. Dùng CHUNG một thứ hạng để ba màn không
  //      nói ba chuyện khác nhau về "PO nào đang chạy" (REQ-DASH-006 §4).
  //   3. Không PO nào đang mở thì lấy PO mới nhất của hệ thống.
  //   4. Chỉ khi hệ thống THẬT SỰ chưa có PO nào mới hiện trạng thái rỗng.
  //
  // PO đang xem luôn được ghi vào URL, nên refresh / Back / Forward / gửi link
  // đều ra đúng một màn hình. Người dùng đổi PO thì lựa chọn đó vào URL ngay,
  // và không có đường nào để màn hình tự nhảy sang PO khác sau lưng họ.
  const urlPoId=()=>{const raw=new URLSearchParams(location.search).get('po_id');return /^\d+$/.test(raw||'')&&Number(raw)>0?Number(raw):null};
  const poLabel=o=>`${esc(o.code)}${o.product?` · ${esc(o.product)}`:''}${Number(o.open_sessions||0)>0?` — ${Number(o.open_sessions)} đang làm`:''}`;

  /** Bộ chọn: PO đang chạy (theo thứ hạng của server) trước, phần còn lại mới nhất trước.
   *
   * Danh sách đầy đủ vẫn cần cho một màn truy vết -- PO đã COMPLETED vẫn phải
   * chọn được -- nhưng `/api/production-orders` trả về theo `id` TĂNG DẦN, nên
   * để nguyên thì PO cũ nhất nằm trên cùng và PO vừa tạo nằm tận đáy.
   */
  const mergeOptions=(ranked,all)=>{
    const seen=new Set(ranked.map(x=>Number(x.id)));
    return [...ranked,...all.filter(x=>!seen.has(Number(x.id))).sort((a,b)=>Number(b.id)-Number(a.id))];
  };

  async function resolvePo(){
    notice='';
    const wanted=urlPoId();
    const [all,ranked]=await Promise.all([
      api('/api/production-orders?limit=1000').then(d=>d.items||[]),
      // include_id GHIM PO trong URL vào kết quả dù nó xếp ngoài cửa sổ 40 của
      // bộ chọn; không có nó thì <select> không có option nào khớp và bộ chọn
      // sẽ nói khác phần tóm tắt phía trên.
      api(`/api/kiosk-board/po-options${wanted?`?include_id=${wanted}`:''}`).then(d=>d.items||[])
        .catch(()=>{notice='Không xếp hạng được PO đang chạy, tạm xếp theo PO mới nhất.';return []}),
    ]);
    poOptions=mergeOptions(ranked,all);
    if(wanted){
      if(poOptions.some(x=>Number(x.id)===wanted))return wanted;
      // PO nằm ngoài cả hai cửa sổ danh sách vẫn có thể tồn tại. HỎI server
      // thay vì đoán: đổi PO sau lưng người dùng là kiểu hỏng tệ nhất ở một
      // màn hình mà họ tin rằng mình đang nhìn đúng đơn hàng mình chọn.
      try{
        poOptions=[(await api(`/api/production-orders/${wanted}`)).item,...poOptions];
        return wanted;
      }catch(_e){
        // Và khi thật sự không mở được thì NÓI RA, không im lặng thay PO.
        notice=`Không mở được Production Order #${wanted} (đã xoá hoặc không tồn tại). Đang hiển thị PO gần nhất.`;
      }
    }
    return poOptions.length?Number(poOptions[0].id):null;
  }

  async function load(reset=true){
    if(reset){before=null;allEvents=[]}
    if(!poId)return;
    const s=document.getElementById('ptSummary');
    if(reset){s.className='';s.innerHTML=MFUI.loadingState('Đang tải dòng thời gian…')}
    const category=document.querySelector('.pt-filter.active')?.dataset.category||'';
    const params=new URLSearchParams({limit:'100'});
    if(category)params.set('category',category);
    if(before)params.set('before',before);
    try{
      const [d,q]=await Promise.all([api(`/api/production-orders/${poId}/trace?${params}`),api(`/api/production-orders/${poId}/quantity-history`)]);
      document.querySelector('.trace-filters').hidden=false;document.getElementById('ptTimelinePanel').hidden=false;
      allEvents.push(...d.events);before=d.next_before;
      const c=d.context,r=q.reconciliation.current;
      s.className='trace-summary';
      s.innerHTML=`<div><small>Production Order</small><h2>${esc(c.po_code)}</h2><span class="badge">${esc(c.status)}</span></div><div class="trace-current"><span><small>Kế hoạch</small><b>${c.planned_quantity||0}</b></span><span><small>Đạt</small><b>${r.good_qty||0}</b></span><span><small>NG</small><b>${r.defect_qty||0}</b></span><span><small>Sửa được</small><b>${r.rework_qty||0}</b></span></div><div class="trace-coverage"><b>${q.reconciliation.matches?'Đối chiếu số liệu khớp':'Đối chiếu số liệu chưa bao phủ toàn bộ'}</b><small>Trace chuẩn từ KIMEX V68; dữ liệu cũ chỉ được suy ra một phần.</small></div>`;
      draw();
      document.getElementById('ptMore').hidden=!d.has_more;
    }catch(e){
      // Màn này tự nạp ngay khi mở, nên một lỗi ở đây (403 với role không có
      // quyền xem trace, PO vừa bị xoá, mất mạng) phải thành một câu nói được
      // -- trước đây nó chỉ là một promise reject và một trang trắng.
      // "Tải thêm" hỏng thì chỉ báo, KHÔNG xoá phần dòng thời gian đã đọc được.
      if(!reset){toast(e.message||'Không tải thêm được sự kiện.');return}
      document.querySelector('.trace-filters').hidden=true;document.getElementById('ptTimelinePanel').hidden=true;
      // MFUI.refreshError chứ không phải một khối errorState tự dựng: màn này
      // không tự làm mới nên mọi lần reset đều là "tải đầu" (loaded mặc định
      // false) và vẫn vẽ đúng khối lỗi như trước -- cái thêm được là nút Thử
      // lại chung một kiểu với các màn khác, và một lần tự nạp lại khi mạng
      // online trở lại qua MFNet.onReconnect.
      s.className='';
      MFUI.refreshError({host:s,error:e,retry:()=>load(true),screen:'Truy vết sản xuất'});
    }
  }

  async function render(){
    title.textContent='Production Trace';subtitle.textContent='Dòng thời gian PO, Session, sản lượng, ngoại lệ và thay đổi';
    content.innerHTML=`<div class="page-shell">${MFUI.loadingState('Đang tải Production Order…')}</div>`;
    // resolvePo() hỏi hai API trước khi trang có hình dạng nào. Không bắt lỗi ở
    // đây thì một nhịp mạng hỏng làm renderProductionTrace() reject ra ngoài và
    // người dùng ngồi lại với cái spinner vĩnh viễn -- đúng lỗi mà nhánh network
    // resilience vừa vá cho danh sách PO cũ (MFUI.refreshError).
    let resolved;
    try{resolved=await resolvePo()}
    catch(e){MFUI.refreshError({host:content,error:e,retry:render,screen:'Truy vết sản xuất'});return}
    poId=resolved;
    // Chưa có PO nào: giữ NGUYÊN hình dạng trang (bộ lọc + bộ chọn, đã tắt) và
    // nói thật ở chỗ dành cho dữ liệu. Trạng thái rỗng THẬT là "không có gì để
    // truy vết", không phải "bạn chưa bấm chọn" — và một màn hình đổi hẳn bố
    // cục theo việc kho dữ liệu rỗng hay không là một màn hình thứ hai phải
    // nhớ, cho cả người dùng lẫn mọi bài test dùng chung primitive này.
    content.innerHTML=`<div class="page-shell">
  ${MFUI.filterBar({content:`<label><span>Production Order</span><select id="ptPo"${poId?'':' disabled'}>${poId?poOptions.map(x=>`<option value="${x.id}"${Number(x.id)===poId?' selected':''}>${poLabel(x)}</option>`).join(''):'<option>Chưa có Production Order</option>'}</select></label>`,actions:'<button class="btn" id="ptReload">Làm mới</button>'})}
  <p class="trace-notice" id="ptNotice"${notice?'':' hidden'}>${esc(notice)}</p>
  <section id="ptSummary">${poId?MFUI.loadingState('Đang tải dòng thời gian…'):MFUI.emptyState('Chưa có Production Order nào','Khởi tạo một PO từ Template rồi quay lại đây để xem dòng thời gian sản xuất.')}</section>
  <nav class="trace-filters mf-tabs" hidden>${cats.map(([v,l],i)=>`<button class="pt-filter mf-tab ${i===0?'active':''}" data-category="${v}">${l}</button>`).join('')}</nav>
  <section class="content-panel" id="ptTimelinePanel" hidden><div class="content-panel-body"><main id="ptTimeline" class="production-trace"></main><button class="btn" id="ptMore" hidden>Tải thêm sự kiện</button></div></section>
</div>`;
    // PO đang xem nằm trong URL ngay từ lần mở đầu tiên: refresh và Back/Forward
    // phải quay lại đúng PO đó, kể cả khi nó được chọn giúp. replaceState chứ
    // không push -- lần mở trang đã có sẵn một entry `?page=` của openPage().
    // poId rỗng thì XOÁ po_id khỏi URL: giữ lại một tham số trỏ vào hư vô chỉ
    // làm lần refresh sau đi lại đúng đường vòng đó.
    AppNav.setQuery({po_id:poId});
    document.getElementById('ptPo').onchange=e=>{poId=Number(e.target.value)||null;AppNav.setQuery({po_id:poId});const n=document.getElementById('ptNotice');n.hidden=true;n.textContent='';load(true)};
    // Chưa có PO thì "Làm mới" phải hỏi lại DANH SÁCH PO — người vừa tạo PO ở
    // màn khác quay về đây cần thấy nó, không phải tải lại một khoảng trống.
    document.getElementById('ptReload').onclick=()=>poId?load(true):render();
    document.getElementById('ptMore').onclick=()=>load(false);
    document.querySelectorAll('.pt-filter').forEach(b=>b.onclick=()=>{document.querySelectorAll('.pt-filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');load(true)});
    if(!poId)return;
    return load(true);
  }
  // Deep link từ màn khác: ghi PO vào URL trước rồi render đọc lại từ đó, nên
  // chỉ có MỘT đường quyết định PO đang xem.
  return {render,openPo:id=>{AppNav.setQuery({po_id:Number(id)||null});return render()}};
})();
function renderProductionTrace(){return ProductionTrace.render()}
registerPage('production-trace',()=>renderProductionTrace());
