/* V67 operational Exception Center. Loaded after the legacy renderer so the
   navigation/API contract stays backward compatible while the page upgrades. */
const ExceptionCenter=(()=>{
  const state={view:'action',items:[],selected:null,scroll:0,timer:null,resolution:null};
  const labels={LONG_OPEN_SESSION:'Session mở quá lâu',ZERO_QUANTITY_LONG:'Sản lượng bất thường',MISSING_STATION:'Thiếu thông tin trạm',INVALID_DURATION:'Thời gian không hợp lệ',OPERATION_COMPLETED_SESSION_OPEN:'Operation hoàn tất nhưng Session còn mở',EMPLOYEE_SESSION_CONFLICT:'Session xung đột'};
  const statusLabel={OPEN:'Cần xử lý',ACKNOWLEDGED:'Đã xác nhận',RESOLVED:'Đã giải quyết',AUTO_IGNORED:'Tự động bỏ qua',MANUAL_IGNORED:'Đã bỏ qua'};
  // §3 of the 2026-08-28 Session Exception Resolution modal task: presentation
  // (label/input widget) only -- WHICH fields are ever offered per exception
  // type still comes from the server's own EDITABLE_FIELDS_BY_EXCEPTION_TYPE
  // (returned as resolution-context's `editable_fields`), never guessed here.
  const FIELD_META={
    started_at:{label:'Giờ bắt đầu',type:'datetime'},
    ended_at:{label:'Giờ kết thúc',type:'datetime'},
    status:{label:'Trạng thái',type:'select',options:[['OPEN','Đang mở'],['CLOSED','Đã đóng']]},
    good_qty:{label:'Số lượng đạt',type:'number'},
    defect_qty:{label:'Số lượng lỗi',type:'number'},
    rework_qty:{label:'Số lượng sửa được',type:'number'},
    station_id:{label:'ID trạm',type:'number'},
  };
  // Same site-wide convention as renderSessionManagement()'s own
  // localInput/toIso (app.js) -- Asia/Ho_Chi_Minh fixed offset, kept
  // identical rather than reinvented so a Session edited from either
  // screen behaves the same way for the same wall-clock input.
  const localInput=v=>{if(!v)return '';const d=new Date(v);if(Number.isNaN(d.getTime()))return '';return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(d).replace(' ','T').slice(0,16)};
  const toIso=v=>v?new Date(v+':00+07:00').toISOString():null;
  const query=()=>{const p=new URLSearchParams({view:state.view,sort:document.getElementById('ecSort')?.value||'severity',page_size:'100'});for(const id of ['ecSeverity','ecType','ecPo','ecEmployee','ecOperation','ecFrom','ecTo']){const v=document.getElementById(id)?.value;if(v)p.set({ecSeverity:'severity',ecType:'exception_type',ecPo:'po_id',ecEmployee:'employee_id',ecOperation:'operation_id',ecFrom:'from',ecTo:'to'}[id],v)}return p};
  const filterFields=()=>`<label><span>Mức độ</span><select id="ecSeverity"><option value="">Mọi mức độ</option>${['CRITICAL','HIGH','MEDIUM','LOW'].map(x=>`<option>${x}</option>`).join('')}</select></label><label><span>Loại</span><select id="ecType"><option value="">Mọi loại</option>${Object.entries(labels).map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select></label><label><span>ID PO</span><input id="ecPo" inputmode="numeric" placeholder="ID PO"></label><label><span>ID nhân viên</span><input id="ecEmployee" inputmode="numeric" placeholder="ID nhân viên"></label><label><span>ID Operation</span><input id="ecOperation" inputmode="numeric" placeholder="ID Operation"></label><label><span>Từ ngày</span><input id="ecFrom" type="date"></label><label><span>Đến ngày</span><input id="ecTo" type="date"></label><label><span>Sắp xếp</span><select id="ecSort"><option value="severity">Mức độ · lâu nhất</option><option value="newest">Mới nhất</option><option value="oldest">Cũ nhất</option><option value="longest">Chờ lâu nhất</option></select></label>`;
  const card=x=>`<article class="ec-card severity-${x.severity.toLowerCase()}" data-id="${x.id}" tabindex="0"><div class="ec-severity"><b>${esc(x.severity)}</b><span>${esc(statusLabel[x.status]||x.status)}</span></div><div class="ec-card-main"><header><h3>${esc(x.title||labels[x.exception_type]||x.exception_type)}</h3><time>${fmt(x.detected_at)}</time></header><p>${esc(x.message)}</p><div class="ec-context"><b>${esc(x.employee_name||'Không rõ nhân viên')}</b><span>PO ${esc(x.po_code||'—')}</span><span>Part ${esc(x.part_code||'—')}</span><span>${esc(x.operation_name||x.operation_code||'—')}</span><span>Session #${x.session_id||'—'}</span></div><div class="ec-recommend"><b>Cần làm:</b> ${esc(x.recommended_action||'Kiểm tra và xác nhận tình trạng.')}</div></div><button class="btn primary ec-review">Xử lý</button></article>`;
  async function load(quiet=false){try{const data=await api('/api/exceptions?'+query());state.items=data.items||[];const high=state.items.filter(x=>['HIGH','CRITICAL'].includes(x.severity)).length;document.getElementById('ecSummary').innerHTML=`<b>${data.total} ngoại lệ</b>${high?`<span class="ec-severity-badge">${high} mức cao/nghiêm trọng</span>`:''}<small>Cập nhật ${new Intl.DateTimeFormat('vi-VN',{timeStyle:'medium'}).format(new Date())}</small>`;document.getElementById('ecList').innerHTML=state.items.length?state.items.map(card).join(''):`<div class="empty"><b>Không có ngoại lệ trong nhóm này</b><span>Hệ thống vẫn tiếp tục đối soát định kỳ.</span></div>`;bindCards()}catch(e){if(!quiet)document.getElementById('ecList').innerHTML=`<div class="empty danger">${esc(e.message)}</div>`}}
  function bindCards(){document.querySelectorAll('.ec-card').forEach(el=>{const open=()=>openResolution(Number(el.dataset.id));el.onclick=open;el.onkeydown=e=>{if(e.key==='Enter')open()}})}

  // --- Inline Session Exception Resolution modal (2026-08-28) -------------
  // §1 of that task: replace "navigate to Session Management and scroll to
  // Session #ID" with a first-class modal that never leaves this page for
  // the primary flow. "Mở Session đầy đủ" (openSessionInManagement, below)
  // is kept only as the explicit secondary fallback the spec asks for.

  function hasUnsavedDraft(){const r=state.resolution;if(!r||!r.session)return false;return (r.editableFields||[]).some(f=>String(draftRaw(r,f))!==String(baselineRaw(r,f)))}
  function baselineRaw(r,field){const v=r.session[field];if(FIELD_META[field]?.type==='datetime')return localInput(v);return v??''}
  function draftRaw(r,field){return field in r.draft?r.draft[field]:baselineRaw(r,field)}

  async function openResolution(id){
    state.scroll=window.scrollY;
    document.getElementById('ecDrawer')?.remove();
    try{
      const data=await api(`/api/session-exceptions/${id}/resolution-context`);
      state.resolution={id,exception:data.exception,session:data.session,activity:data.activity||[],history:data.history||[],editableFields:data.editable_fields||[],tab:'overview',draft:{},banner:null,blockedResolve:false};
    }catch(e){toast(e.message);return}
    renderResolution();
  }

  function fieldDisplay(field,value){
    const meta=FIELD_META[field]||{};
    if(meta.type==='datetime')return fmt(value?toIso(value):null);
    if(field==='status')return value==='OPEN'?'Đang mở':value==='CLOSED'?'Đã đóng':(value||'—');
    return (value===null||value===undefined||value==='')?'—':String(value);
  }
  function diffRows(r){
    return (r.editableFields||[]).map(f=>{
      const before=baselineRaw(r,f),after=draftRaw(r,f);
      if(String(before)===String(after))return null;
      return {field:f,label:(FIELD_META[f]||{}).label||f,before:fieldDisplay(f,before),after:fieldDisplay(f,after)};
    }).filter(Boolean);
  }
  function fieldInput(r,field){
    const meta=FIELD_META[field];if(!meta)return '';
    const raw=draftRaw(r,field);
    const disabled=(field==='ended_at'&&r.editableFields.includes('status')&&draftRaw(r,'status')==='OPEN');
    if(meta.type==='select')return `<label class="ec-field"><span>${meta.label}</span><select data-field="${field}" ${disabled?'disabled':''}>${meta.options.map(([v,l])=>`<option value="${v}" ${v===raw?'selected':''}>${l}</option>`).join('')}</select></label>`;
    if(meta.type==='datetime')return `<label class="ec-field"><span>${meta.label}</span><input type="datetime-local" data-field="${field}" value="${esc(raw||'')}" ${disabled?'disabled':''}></label>`;
    return `<label class="ec-field"><span>${meta.label}</span><input type="number" data-field="${field}" value="${esc(raw??'')}" ${disabled?'disabled':''}></label>`;
  }
  function bannerHtml(b){
    if(!b)return '';
    return `<div class="ec-banner ${b.type}">${esc(b.text)}</div>`;
  }
  function tabOverview(r){
    const s=r.session||{},x=r.exception;
    return `<section><h3>Ngoại lệ</h3><dl><dt>Loại</dt><dd>${esc(x.title||labels[x.exception_type]||x.exception_type)}</dd><dt>Mức độ</dt><dd>${esc(x.severity)}</dd><dt>Trạng thái</dt><dd>${esc(statusLabel[x.status]||x.status)}</dd><dt>Mô tả</dt><dd>${esc(x.message)}</dd><dt>Cần làm</dt><dd>${esc(x.recommended_action||'—')}</dd></dl></section>
      <section><h3>Bối cảnh sản xuất</h3><dl><dt>Nhân viên</dt><dd>${esc(s.employee_name||x.employee_name||'—')} (${esc(s.employee_code||'—')})</dd><dt>PO</dt><dd>${esc(s.po_code||x.po_code||'—')}</dd><dt>Part</dt><dd>${esc(s.part_code||x.part_code||'—')} · ${esc(s.part_name||'')}</dd><dt>Operation</dt><dd>${esc(s.operation_code||x.operation_code||'—')} · ${esc(s.operation_name||x.operation_name||'')}</dd><dt>Trạm / kiosk</dt><dd>${esc(s.station_name||s.station_code||s.device_uuid||'—')}</dd></dl></section>
      <section><h3>Thời gian và sản lượng</h3><div class="ec-metrics"><span><small>Bắt đầu</small><b>${fmt(s.started_at)}</b></span><span><small>Kết thúc</small><b>${fmt(s.ended_at)}</b></span><span><small>Thời lượng</small><b>${fmtDuration(s.duration_seconds)}</b></span><span><small>Đạt</small><b>${s.good_qty??0}</b></span><span><small>NG</small><b>${s.defect_qty??0}</b></span><span><small>Sửa được</small><b>${s.rework_qty??0}</b></span></div></section>`;
  }
  function tabAdjust(r){
    if(!r.editableFields.length)return `<section><p class="ec-empty-note">Loại ngoại lệ này không có trường điều chỉnh Session nào theo quy tắc nghiệp vụ hiện tại. Dùng "Bỏ qua" nếu đã xác nhận đây không phải lỗi thật, hoặc "Mở Session đầy đủ" cho các thay đổi phức tạp hơn.</p></section>`;
    const rows=diffRows(r);
    return `<section><h3>Sửa Session #${r.session.session_id}</h3><div class="ec-field-grid">${r.editableFields.map(f=>fieldInput(r,f)).join('')}</div></section>
      <section><h3>Xem trước thay đổi</h3>${rows.length?`<div class="ec-diff-wrap"><table class="ec-diff"><thead><tr><th>Trường</th><th>Trước</th><th>Sau</th></tr></thead><tbody>${rows.map(d=>`<tr><td>${esc(d.label)}</td><td>${esc(d.before)}</td><td>${esc(d.after)}</td></tr>`).join('')}</tbody></table></div>`:'<p class="ec-empty-note">Chưa có thay đổi nào.</p>'}</section>`;
  }
  function tabVerify(r){
    return `<section><h3>Dòng thời gian kiosk</h3><ol class="ec-timeline"><li><time>${fmt(r.session.started_at)}</time><span>Session bắt đầu</span></li>${(r.activity||[]).map(x=>`<li><time>${fmt(x.occurred_at)}</time><span>${esc(x.message||x.event_type)}</span></li>`).join('')}</ol></section>`;
  }
  function tabHistory(r){
    return `<section><h3>Lịch sử xử lý ngoại lệ</h3><ol class="ec-timeline">${(r.history||[]).map(x=>`<li><time>${fmt(x.created_at)}</time><span><b>${esc(x.action)}</b> · ${esc(x.actor_username||'Hệ thống')}<small>${esc(x.reason||'')}</small></span></li>`).join('')||'<li>Chưa có thao tác xử lý.</li>'}</ol></section>`;
  }
  const TABS=[['overview','Tổng quan',tabOverview],['adjust','Điều chỉnh',tabAdjust],['verify','Kiểm tra',tabVerify],['history','Lịch sử',tabHistory]];

  function renderResolution(){
    const r=state.resolution;if(!r)return;
    document.getElementById('ecDrawer')?.remove(); // every re-render (tab switch, save, ack, ...) replaces the modal, never stacks a second copy
    const x=r.exception,s=r.session||{};
    const canAck=x.status==='OPEN';
    const canAdjust=x.status!=='RESOLVED'&&x.status!=='AUTO_IGNORED'&&x.status!=='MANUAL_IGNORED'&&r.editableFields.length>0;
    const stillOpen=x.status==='OPEN'||x.status==='ACKNOWLEDGED';
    // §6/§9 of the task: "Hoàn tất xử lý" is disabled the moment a
    // correction attempt has told us the anomaly is still active
    // (r.blockedResolve, set by saveCorrection()/resolveInline()'s own
    // 409) -- server-side resolve() re-verifies regardless (see its own
    // reconcile()-then-check), so this is an honest UX signal on top of a
    // real safety check, never a substitute for it. Before any correction
    // is attempted this stays enabled: some exception types need no edit
    // at all here (fixed via "Mở Session đầy đủ" then a plain resolve).
    const canResolve=stillOpen&&!r.blockedResolve;
    const node=document.createElement('div');node.id='ecDrawer';node.className='ec-drawer-shell';
    node.innerHTML=`<button class="ec-drawer-backdrop" aria-label="Đóng"></button><aside class="ec-drawer ec-resolution" role="dialog" aria-modal="true" aria-label="Xử lý ngoại lệ Session"><header><div><small>SESSION #${x.session_id||'—'}</small><h2>${esc(s.employee_name||x.employee_name||'Ngoại lệ')}</h2><span class="ec-status">${esc(statusLabel[x.status]||x.status)}</span></div><button id="ecClose" aria-label="Đóng">×</button></header>
      <nav class="ec-modal-tabs mf-tabs">${TABS.map(([v,l])=>`<button data-tab="${v}" class="mf-tab ${r.tab===v?'active':''}">${l}</button>`).join('')}</nav>
      <div class="ec-drawer-body">${bannerHtml(r.banner)}${TABS.find(t=>t[0]===r.tab)[2](r)}</div>
      <footer><textarea id="ecReason" class="ec-reason" placeholder="Ghi lý do xử lý / điều chỉnh (bắt buộc để lưu điều chỉnh, hoàn tất hoặc bỏ qua)">${esc(r.reasonDraft||'')}</textarea><div class="ec-actions">${x.session_id?'<button class="btn" data-action="open-full">Mở Session đầy đủ</button>':''}${canAck?'<button class="btn" data-action="take">Nhận xử lý</button>':''}${canAdjust?'<button class="btn" data-action="save">Lưu điều chỉnh</button>':''}<button class="btn primary" data-action="resolve" ${canResolve?'':'disabled'} ${!canResolve&&stillOpen?'title="Ngoại lệ vẫn còn hiệu lực -- sửa Session hoặc kiểm tra lại trước khi hoàn tất"':''}>Hoàn tất xử lý</button><button class="btn danger" data-action="ignore" ${stillOpen?'':'disabled'}>Bỏ qua</button><button class="btn" data-action="close">Đóng</button></div></footer></aside>`;
    document.body.appendChild(node);
    node.querySelector('#ecClose').onclick=node.querySelector('.ec-drawer-backdrop').onclick=()=>closeResolution();
    // The reason textarea and any in-progress field edits must survive a
    // tab switch or a status-triggered re-render (both call renderResolution()
    // again) -- otherwise switching to "Kiểm tra" to check evidence before
    // saving would silently discard what the operator already typed.
    node.querySelector('#ecReason').oninput=e=>{r.reasonDraft=e.target.value};
    node.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>{r.tab=b.dataset.tab;renderResolution()});
    node.querySelectorAll('[data-field]').forEach(el=>el.onchange=e=>{
      r.draft[e.target.dataset.field]=e.target.value;
      if(e.target.dataset.field==='status')renderResolution();
    });
    node.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>{
      const a=b.dataset.action;
      if(a==='open-full')return openSessionInManagement(x);
      if(a==='close')return closeResolution();
      if(a==='take')return ackInline();
      if(a==='save')return saveCorrection();
      if(a==='resolve')return resolveInline();
      if(a==='ignore')return ignoreInline();
    });
  }
  function closeResolution(){
    if(hasUnsavedDraft()&&!confirm('Có thay đổi chưa lưu. Đóng và bỏ qua thay đổi này?'))return;
    document.getElementById('ecDrawer')?.remove();state.resolution=null;window.scrollTo(0,state.scroll);load(true);
  }
  function reasonValue(){return (document.getElementById('ecReason')?.value||'').trim()}

  async function ackInline(){
    const r=state.resolution;
    try{
      const res=await api(`/api/exceptions/${r.id}/acknowledge`,{method:'POST',body:JSON.stringify({expected_version:r.exception.row_version})});
      r.exception=res.item;r.banner={type:'info',text:'Đã nhận xử lý ngoại lệ.'};renderResolution();
    }catch(e){toast(e.message)}
  }
  async function saveCorrection(){
    const r=state.resolution,reason=reasonValue();
    if(!reason){toast('Cần nhập lý do điều chỉnh trước khi lưu.');document.getElementById('ecReason')?.focus();return}
    const body={reason,expected_updated_at:r.session.updated_at};
    for(const f of r.editableFields){
      const meta=FIELD_META[f];let v=draftRaw(r,f);
      if(meta?.type==='datetime')v=v?toIso(v):null;
      body[f]=v;
    }
    // Raw fetch (not the shared api() helper): a SESSION_CHANGED 409 carries
    // a structured `current` snapshot the modal needs to redraw with --
    // api()'s own contract only ever throws a plain Error(message), so
    // reaching for it here would silently drop that payload. See §11.
    let resp,res;
    try{
      resp=await fetch(`/api/session-exceptions/${r.id}/correct-session`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      res=await resp.json().catch(()=>({}));
    }catch(_networkErr){toast('Không thể kết nối máy chủ. Thử lại.');return}
    if(resp.status===401){location.href='/login';return}
    if(resp.status===409&&res.error==='SESSION_CHANGED'){
      if(res.current){r.session=res.current;r.draft={}}
      r.banner={type:'danger',text:'Session đã được người khác thay đổi trong lúc bạn đang xử lý. Dữ liệu đã được làm mới -- vui lòng kiểm tra lại trước khi lưu.'};
      renderResolution();return;
    }
    if(!resp.ok||res.ok===false){toast(res.message||res.error||`HTTP ${resp.status}`);return}
    r.session=res.item;r.exception=res.exception;r.draft={};r.blockedResolve=!res.cleared;
    r.banner=res.cleared
      ?{type:'success',text:'Đã lưu điều chỉnh. Ngoại lệ không còn hiệu lực -- có thể bấm "Hoàn tất xử lý".'}
      :{type:'warn',text:`Đã lưu điều chỉnh nhưng ngoại lệ vẫn còn: ${res.exception.message||res.exception.title||'điều kiện bất thường vẫn đúng'}`};
    r.reasonDraft='';
    renderResolution();load(true);
  }
  async function resolveInline(){
    const r=state.resolution,reason=reasonValue();
    if(['HIGH','CRITICAL'].includes(r.exception.severity)&&!reason){toast('Ngoại lệ mức cao cần ghi lý do.');document.getElementById('ecReason')?.focus();return}
    try{
      await api(`/api/exceptions/${r.id}/resolve`,{method:'POST',body:JSON.stringify({expected_version:r.exception.row_version,reason})});
      toast('Đã hoàn tất xử lý ngoại lệ.');closeResolutionAfterDecision();
    }catch(e){
      toast(e.message);
      r.blockedResolve=true;
      try{const fresh=await api(`/api/session-exceptions/${r.id}/resolution-context`);r.exception=fresh.exception;r.session=fresh.session;r.banner={type:'warn',text:'Ngoại lệ vẫn còn hiệu lực, chưa thể hoàn tất -- kiểm tra tab Điều chỉnh.'};renderResolution()}catch(_e){}
    }
  }
  async function ignoreInline(){
    const r=state.resolution,reason=reasonValue();
    if(!reason){toast('Bỏ qua ngoại lệ cần ghi lý do.');document.getElementById('ecReason')?.focus();return}
    try{
      await api(`/api/exceptions/${r.id}/ignore`,{method:'POST',body:JSON.stringify({expected_version:r.exception.row_version,reason})});
      toast('Đã bỏ qua ngoại lệ.');closeResolutionAfterDecision();
    }catch(e){toast(e.message)}
  }
  function closeResolutionAfterDecision(){document.getElementById('ecDrawer')?.remove();state.resolution=null;window.scrollTo(0,state.scroll);load();}

  // §3 of the 2026-08-27 Session Exception Management task (kept as the
  // explicit secondary fallback per §1 of the 2026-08-28 follow-up): open
  // the exact Session in the full Session Management editor for cases the
  // inline modal's narrow field set can't cover (reassigning employee/
  // operation, transferring Operation, excluding from reports, etc).
  function openSessionInManagement(item){
    if(!item?.session_id){toast('Ngoại lệ này không gắn với một Session cụ thể.');return}
    window.MESFLOW_SESSION_EXCEPTION_CONTEXT={
      sessionId:Number(item.session_id),
      startedAt:item.started_at||state.resolution?.session?.started_at,
      exceptionCode:item.exception_type,
      exceptionLabel:item.title||labels[item.exception_type]||item.exception_type
    };
    AppNav.push(()=>openPage('session-exceptions',document.querySelector('[data-page="session-exceptions"]')));
    document.getElementById('ecDrawer')?.remove();state.resolution=null;
    openPage('session-management',document.querySelector('[data-page="session-management"]'));
  }

  async function render(){if(state.timer)clearTimeout(state.timer);title.textContent='Trung tâm ngoại lệ';subtitle.textContent='Việc cần xử lý, xác nhận và lịch sử bất thường sản xuất';content.innerHTML=`<div class="page-shell"><nav class="ec-tabs mf-tabs">${[['action','Cần xử lý'],['all','Tất cả'],['resolved','Đã giải quyết'],['ignored','Đã bỏ qua'],['history','Lịch sử']].map(([v,l])=>`<button data-view="${v}" class="mf-tab ${state.view===v?'active':''}">${l}</button>`).join('')}<div id="ecSummary" class="ec-summary-compact">Đang đối soát…</div></nav>${MFUI.filterBar({content:filterFields(),actions:'<button class="btn primary" id="ecApply">Áp dụng</button>'})}<section class="content-panel"><div class="content-panel-head"><div><h3>Danh sách ngoại lệ</h3></div></div><div class="content-panel-body ec-list" id="ecList">Đang tải…</div></section></div>`;document.querySelectorAll('.ec-tabs button').forEach(b=>b.onclick=()=>{state.view=b.dataset.view;render()});document.getElementById('ecApply').onclick=()=>load();await load();const poll=async()=>{if(document.body.dataset.page!=='session-exceptions')return;if(!state.resolution)await load(true);state.timer=setTimeout(poll,15000)};state.timer=setTimeout(poll,15000)}
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.getElementById('ecDrawer'))closeResolution()});return {render,closeDrawer:closeResolution};
})();
renderSessionExceptions=ExceptionCenter.render;
