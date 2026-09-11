const ProductionTrace=(()=>{
  let poId=null,before=null,allEvents=[];
  const cats=[['','Tất cả'],['PO,OPERATION','Sản xuất'],['SESSION','Session'],['QUANTITY','Sản lượng'],['DEFECT','NG'],['REWORK','Rework'],['EXCEPTION','Ngoại lệ'],['CHANGE','Thay đổi']];
  const qLabel={GOOD:'Đạt',DEFECT:'NG',REPAIRABLE:'Sửa được',REWORK_RECOVERED:'Đã phục hồi',SCRAP:'Phế'};
  const day=d=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',dateStyle:'full'}).format(new Date(d));
  const technical=m=>`<details><summary>Chi tiết kỹ thuật</summary><pre>${esc(JSON.stringify(m||{},null,2))}</pre></details>`;
  const auditDiff=e=>{const m=e.metadata||{},parse=x=>{try{return typeof x==='string'?JSON.parse(x):x||{}}catch(_){return {}}};const a=parse(m.before),b=parse(m.after);const ignored=new Set(['updated_at','created_at']);const keys=[...new Set([...Object.keys(a),...Object.keys(b)])].filter(k=>!ignored.has(k)&&JSON.stringify(a[k])!==JSON.stringify(b[k]));return keys.length?`<div class="trace-diff">${keys.map(k=>`<span><small>${esc(k.replaceAll('_',' '))}</small><b>${esc(a[k]??'—')} → ${esc(b[k]??'—')}</b></span>`).join('')}</div>`:''};
  const item=e=>`<article class="trace-event cat-${e.category.toLowerCase()}"><time>${new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',timeStyle:'medium'}).format(new Date(e.occurred_at))}</time><i></i><div><header><b>${esc(e.title)}</b><span>${esc(e.category)}</span>${e.source==='LEGACY_DERIVED'?'<em>Dữ liệu suy ra</em>':''}</header><p>${esc(e.description||'')}</p>${e.quantity_delta!=null?`<strong class="trace-qty ${e.quantity_delta<0?'negative':''}">${e.quantity_delta>0?'+':''}${e.quantity_delta}</strong>`:''}${e.category==='CHANGE'?auditDiff(e):''}<small>${esc(e.actor_name||'Hệ thống')}${e.operation_id?` · OP #${e.operation_id}`:''}${e.session_id?` · Session #${e.session_id}`:''}</small>${technical(e.metadata)}</div></article>`;
  const draw=()=>{const groups=new Map;for(const e of allEvents){const d=day(e.occurred_at);if(!groups.has(d))groups.set(d,[]);groups.get(d).push(e)}document.getElementById('ptTimeline').innerHTML=allEvents.length?[...groups].map(([d,rows])=>`<section class="trace-day"><h3>${esc(d)}</h3>${rows.map(item).join('')}</section>`).join(''):'<div class="empty">Chưa có sự kiện trace phù hợp.</div>'};
  const showEmptyPoState=()=>{const s=document.getElementById('ptSummary');s.className='';s.innerHTML=MFUI.emptyState('Chưa chọn Production Order','Chọn một Production Order để xem lịch sử.');document.querySelector('.trace-filters').hidden=true;document.getElementById('ptTimelinePanel').hidden=true};
  async function load(reset=true){if(reset){before=null;allEvents=[]}if(!poId){showEmptyPoState();return}document.querySelector('.trace-filters').hidden=false;document.getElementById('ptTimelinePanel').hidden=false;const category=document.querySelector('.pt-filter.active')?.dataset.category||'';const params=new URLSearchParams({limit:'100'});if(category)params.set('category',category);if(before)params.set('before',before);
    // Cùng lý do như render(): hai lời gọi này trước đây không có try/catch,
    // nên một nhịp mạng hỏng thành unhandled rejection -- dòng thời gian
    // đứng im, không nội dung, không lỗi, không ai biết vì sao.
    // `allEvents.length` phân biệt "tải trang đầu" với "Tải thêm sự kiện":
    // bấm tải thêm mà hỏng thì phải giữ nguyên những gì đã đọc được.
    let d,q;
    try{[d,q]=await Promise.all([api(`/api/production-orders/${poId}/trace?${params}`),api(`/api/production-orders/${poId}/quantity-history`)])}
    catch(e){MFUI.refreshError({loaded:allEvents.length>0,host:document.getElementById('ptTimeline'),error:e,retry:()=>load(reset),screen:'Truy vết sản xuất'});return}
    allEvents.push(...d.events);before=d.next_before;const c=d.context,r=q.reconciliation.current;const s=document.getElementById('ptSummary');s.className='trace-summary';s.innerHTML=`<div><small>Production Order</small><h2>${esc(c.po_code)}</h2><span class="badge">${esc(c.status)}</span></div><div class="trace-current"><span><small>Kế hoạch</small><b>${c.planned_quantity||0}</b></span><span><small>Đạt</small><b>${r.good_qty||0}</b></span><span><small>NG</small><b>${r.defect_qty||0}</b></span><span><small>Sửa được</small><b>${r.rework_qty||0}</b></span></div><div class="trace-coverage"><b>${q.reconciliation.matches?'Đối chiếu số liệu khớp':'Đối chiếu số liệu chưa bao phủ toàn bộ'}</b><small>Trace chuẩn từ KIMEX V68; dữ liệu cũ chỉ được suy ra một phần.</small></div>`;draw();document.getElementById('ptMore').hidden=!d.has_more}
  async function render(){title.textContent='Production Trace';subtitle.textContent='Dòng thời gian PO, Session, sản lượng, ngoại lệ và thay đổi';
    // Danh sách PO là thứ ĐẦU TIÊN màn này cần, và trước đây nó không có
    // try/catch nào: mạng chớp một nhịp là promise của renderProductionTrace
    // reject ra ngoài, màn đứng nguyên ở nội dung cũ và không báo gì -- người
    // dùng bấm vào Truy vết sản xuất rồi không thấy chuyện gì xảy ra.
    let pos;
    try{pos=await api('/api/production-orders?limit=1000')}
    catch(e){MFUI.refreshError({host:content,error:e,retry:render,screen:'Truy vết sản xuất'});return}
    content.innerHTML=`<div class="page-shell">
  ${MFUI.filterBar({content:`<label><span>Production Order</span><select id="ptPo"><option value="">Chọn PO cần truy vết</option>${(pos.items||[]).map(x=>`<option value="${x.id}">${esc(x.code)} · ${esc(x.product)}</option>`).join('')}</select></label>`,actions:'<button class="btn" id="ptReload">Làm mới</button>'})}
  <section id="ptSummary">${MFUI.emptyState('Chưa chọn Production Order','Chọn một Production Order để xem lịch sử.')}</section>
  <nav class="trace-filters mf-tabs" hidden>${cats.map(([v,l],i)=>`<button class="pt-filter mf-tab ${i===0?'active':''}" data-category="${v}">${l}</button>`).join('')}</nav>
  <section class="content-panel" id="ptTimelinePanel" hidden><div class="content-panel-body"><main id="ptTimeline" class="production-trace"></main><button class="btn" id="ptMore" hidden>Tải thêm sự kiện</button></div></section>
</div>`;document.getElementById('ptPo').onchange=e=>{poId=Number(e.target.value)||null;load(true)};document.getElementById('ptReload').onclick=()=>load(true);document.getElementById('ptMore').onclick=()=>load(false);document.querySelectorAll('.pt-filter').forEach(b=>b.onclick=()=>{document.querySelectorAll('.pt-filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');load(true)})}
  return {render,openPo:id=>{poId=Number(id);return render().then(()=>{document.getElementById('ptPo').value=String(poId);return load(true)})}};
})();
function renderProductionTrace(){return ProductionTrace.render()}
registerPage('production-trace',()=>renderProductionTrace());
