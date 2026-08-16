async function renderSessionExceptions(){
  if(dashboardTimer){clearInterval(dashboardTimer);dashboardTimer=null}
  const el=id=>document.getElementById(id);
  title.textContent='Phiên làm việc bất thường';
  subtitle.textContent='Danh sách việc cần kiểm tra: xem nguyên nhân → sửa Session nếu cần → xác nhận kết quả';

  content.innerHTML=`
  <section class="panel se-workspace">
    <div class="se-topbar">
      <div>
        <h2>Việc cần xử lý</h2>
        <p>Ưu tiên mục đang còn bất thường. Chọn một dòng để xem chi tiết và hành động.</p>
      </div>
      <div class="se-filters">
        <select id="seDataSource" aria-label="Nguồn dữ liệu">
          <option value="">Tất cả nguồn</option>
          <option value="QA_TEST">QA Test</option>
          <option value="TUTORIAL">Tutorial/Demo</option>
          <option value="UNKNOWN">Không xác định</option>
        </select>
        <select id="seSessionStatus">
          <option value="">OPEN + CLOSED</option>
          <option value="OPEN">Session đang mở</option>
          <option value="CLOSED">Session đã đóng</option>
        </select>
        <button class="btn" id="seRefresh">Làm mới</button>
      </div>
    </div>

    <div id="seSummary" class="se-summary"></div>
    <div class="se-workflow-tabs" role="tablist" aria-label="Trạng thái xử lý">
      <button class="btn primary" data-se-view="NEW" role="tab" aria-selected="true">Cần xử lý</button>
      <button class="btn" data-se-view="CONFIRMATION" role="tab" aria-selected="false">Cần xác nhận</button>
      <button class="btn" data-se-view="HISTORY" role="tab" aria-selected="false">Lịch sử</button>
    </div>
    <div id="seHistoryFilters" class="se-history-filters" hidden>
      <label>Từ ngày<input id="seHistoryFrom" type="date"></label>
      <label>Nhân viên<input id="seHistoryEmployee" placeholder="Mã hoặc tên"></label>
      <label>PO<input id="seHistoryPo" placeholder="Mã PO"></label>
      <label>Loại lỗi<select id="seHistoryType"><option value="">Tất cả</option></select></label>
      <label>Kết quả<select id="seHistoryResult"><option value="">Tất cả</option><option value="RESOLVED">Đã xử lý</option><option value="IGNORED">Bỏ qua</option></select></label>
      <label>Người xử lý<input id="seHistoryHandler" placeholder="Tài khoản"></label>
    </div>

    <div class="se-split">
      <div class="se-queue">
        <div class="se-queue-head">
          <b id="seCount">0 mục</b>
          <input id="seSearch" placeholder="Tìm nhân viên, PO, công đoạn, mã Session">
        </div>
        <div id="seList" class="se-list"></div>
      </div>

      <aside id="seDetail" class="se-detail">
        <div class="se-detail-empty">
          <b>Chọn một mục bên trái</b>
          <span>Chi tiết nguyên nhân và nút xử lý sẽ hiển thị tại đây.</span>
        </div>
      </aside>
    </div>
  </section>

  <div class="modal-backdrop hidden" id="seModal" role="dialog" aria-modal="true">
    <div class="modal session-exception-modal">
      <div class="session-edit-modal-head">
        <div><span class="se-modal-kicker" id="seModalKicker">Xử lý bất thường</span><h2 id="seModalTitle">Cập nhật xử lý</h2><p id="seModalHelp"></p></div>
        <button class="btn" id="seModalClose">Đóng</button>
      </div>

      <div id="seModalIssue" class="se-modal-issue"></div>

      <div class="session-exception-form">
        <label id="seAssignedWrap">Người phụ trách
          <div class="se-assignee-row"><input id="seAssigned" placeholder="Tên hoặc tài khoản phụ trách"><button type="button" class="btn" id="seAssignMe">Tôi xử lý</button></div>
          <small id="seAssignedHint">Có thể đổi người phụ trách nếu cần.</small>
        </label>
        <label id="seResolutionWrap">Kết quả xử lý
          <select id="seResolution">
            <option value="">Chọn kết quả</option>
            <option value="DATA_CORRECTED">Đã chỉnh dữ liệu</option>
            <option value="SESSION_CLOSED">Đã đóng Session</option>
            <option value="VALID_EXCEPTION">Trường hợp hợp lệ</option>
            <option value="DUPLICATE_ALERT">Cảnh báo trùng</option>
            <option value="OTHER">Khác</option>
          </select>
        </label>
        <label class="wide" id="seNoteWrap">Ghi chú
          <textarea id="seNote" placeholder="Ghi ngắn việc đã kiểm tra hoặc cần lưu ý..."></textarea>
          <small id="seNoteHint">Không bắt buộc khi nhận xử lý.</small>
        </label>
      </div>

      <div id="seModalNext" class="se-modal-next"></div>

      <div class="panel-actions se-modal-actions">
        <button class="btn" id="seModalCancel">Hủy</button>
        <button class="btn" id="seModalSecondary" hidden></button>
        <button class="btn primary" id="seModalSave">Cập nhật</button>
      </div>
    </div>
  </div>`;

  // Shared vocabulary lives in session-detail.js (window.MF_*) so this page
  // and the Session Detail drawer never drift into separate label sets.
  const labels=MF_EXCEPTION_LABELS,hints=MF_EXCEPTION_HINTS,workflowLabels=MF_WORKFLOW_LABELS,severityLabels=MF_SEVERITY_LABELS,impactLabels=MF_IMPACT_LABELS;

  let allItems=[],visible=[],current=null,targetStatus='',currentView='NEW';

  const itemKey=x=>`${x.session_id}|${x.exception_fingerprint}`;
  const isDone=x=>['RESOLVED','IGNORED'].includes(x.workflow_status);
  const qLower=v=>String(v||'').toLowerCase();

  const applyFilters=()=>{
    const q=qLower(el('seSearch').value).trim(),dataSource=el('seDataSource').value;
    const from=el('seHistoryFrom').value,employee=qLower(el('seHistoryEmployee').value).trim();
    const po=qLower(el('seHistoryPo').value).trim(),type=el('seHistoryType').value;
    const result=el('seHistoryResult').value,handler=qLower(el('seHistoryHandler').value).trim();
    visible=allItems.filter(x=>{
      if(dataSource&&x.data_source!==dataSource)return false;
      if(currentView==='NEW'&&!(x.is_active!==false&&x.workflow_status==='NEW'))return false;
      if(currentView==='CONFIRMATION'&&!(x.classification==='CONFIRMATION'&&x.workflow_status==='NEW'))return false;
      if(currentView==='IN_PROGRESS'&&x.workflow_status!=='IN_PROGRESS')return false;
      if(currentView==='HISTORY'&&(x.classification==='ACTION_REQUIRED'||x.classification==='CONFIRMATION')&&x.is_active!==false&&x.workflow_status==='NEW')return false;
      if(currentView==='HISTORY'){
        const ended=String(x.resolved_at||x.review_updated_at||'').slice(0,10);
        if(from&&ended<from)return false;
        if(employee&&![x.employee_code,x.employee_name].join(' ').toLowerCase().includes(employee))return false;
        if(po&&!qLower(x.po_code).includes(po))return false;
        if(type&&x.exception_code!==type)return false;
        if(result&&x.workflow_status!==result)return false;
        if(handler&&!qLower(x.resolved_by||x.assigned_to).includes(handler))return false;
      }
      if(q){
        const hay=[x.session_id,x.employee_code,x.employee_name,x.operation_code,x.operation_name,x.po_code,x.part_code,labels[x.exception_code],x.exception_message].join(' ').toLowerCase();
        if(!hay.includes(q))return false;
      }
      return true;
    });
    if(current&&!visible.some(x=>itemKey(x)===itemKey(current)))current=null;
    if(!current&&visible.length)current=visible[0];
    draw();
  };

  const drawSummary=()=>{
    const fresh=allItems.filter(x=>x.classification==='ACTION_REQUIRED'&&x.is_active!==false&&x.workflow_status==='NEW'),confirm=allItems.filter(x=>x.classification==='CONFIRMATION'&&x.is_active!==false&&x.workflow_status==='NEW'),doing=allItems.filter(x=>x.workflow_status==='IN_PROGRESS');
    const today=siteToday(),doneToday=allItems.filter(x=>isDone(x)&&String(x.resolved_at||'').slice(0,10)===today);
    el('seSummary').innerHTML=`
      <article><span>Cần xử lý</span><b>${fresh.length}</b></article>
      <article><span>Cần xác nhận</span><b>${confirm.length}</b></article>
      <article><span>Đang xử lý</span><b>${doing.length}</b></article>
      <article><span>Đã xử lý hôm nay</span><b>${doneToday.length}</b></article>`;
  };

  // Active list card — fixed Header/Body/Footer structure, inline actions.
  // Never patch this per-row with arbitrary margins; extend .se-card* in
  // ui.css instead.
  const queueCard=x=>{
    const selected=current&&itemKey(current)===itemKey(x);
    const inactive=x.is_active===false;
    const done=isDone(x);
    return `<article class="se-card ${selected?'selected':''} ${inactive?'inactive':''}" data-key="${esc(itemKey(x))}">
      <button class="se-card-trigger" type="button" data-key="${esc(itemKey(x))}">
        <div class="se-card-header">
          <div class="se-card-who"><b>${esc(x.employee_name||'—')}</b><small>${esc(x.employee_code||'—')} · Session #${x.session_id}</small></div>
          <div class="se-card-badges">
            <span class="workflow-badge ${String(x.workflow_status||'NEW').toLowerCase()}">${esc(workflowLabels[x.workflow_status]||x.workflow_status)}</span>
            ${inactive?'<span class="se-fixed-badge">Không còn phát hiện</span>':`<span class="log-level ${String(x.severity||'').toLowerCase()}">${esc(severityLabels[x.severity]||x.severity)}</span>`}
          </div>
        </div>
        <div class="se-card-body">
          <span class="se-card-op">${esc(x.operation_code||'—')} · ${esc(x.operation_name||'')} · ${esc(x.po_code||'—')}</span>
          <span class="se-card-message">${esc(x.exception_message||'')}</span>
          <span class="se-card-impact">${esc(impactLabels[x.exception_code]||'')}</span>
        </div>
      </button>
      <div class="se-card-footer">
        <span class="se-card-meta">Phát hiện: ${fmt(x.started_at)} · ${sourceBadgeHtml(x.data_source)}</span>
        <span class="se-card-actions">
          ${!done?`<button class="btn primary se-card-act" data-act="process" data-key="${esc(itemKey(x))}" type="button">Xử lý</button>`:''}
          ${!done?`<button class="btn se-card-act" data-act="ignore" data-key="${esc(itemKey(x))}" type="button">Bỏ qua</button>`:''}
          <button class="btn se-card-act" data-act="view" data-key="${esc(itemKey(x))}" type="button">Xem session</button>
        </span>
      </div>
    </article>`;
  };

  const detailHtml=x=>{
    if(!x)return `<div class="se-detail-empty"><b>Không có mục phù hợp</b><span>Thử đổi bộ lọc hoặc làm mới.</span></div>`;
    const inactive=x.is_active===false;
    const good=Number(x.good_qty||0),defect=Number(x.defect_qty||0),rework=Number(x.rework_qty||0);
    const canStart=x.workflow_status==='NEW';
    const canFinish=['NEW','IN_PROGRESS'].includes(x.workflow_status);
    return `
      <div class="se-detail-head">
        <div>
          <span class="se-eyebrow">${esc(workflowLabels[x.workflow_status]||x.workflow_status)} · Session #${x.session_id}</span>
          <h3>${esc(labels[x.exception_code]||x.exception_code)}</h3>
          <p>${esc(inactive?'Hệ thống hiện không còn phát hiện lỗi này sau khi Session được thay đổi. Có thể xác nhận hoàn tất nếu dữ liệu đã đúng.':x.exception_message||'')}</p>
        </div>
        ${inactive?'<span class="se-fixed-badge strong">Đã hết bất thường</span>':`<span class="log-level ${String(x.severity||'').toLowerCase()}">${esc(severityLabels[x.severity]||x.severity)}</span>`}
      </div>

      <div class="se-guidance">
        <b>Nên làm gì?</b>
        <span>${esc(hints[x.exception_code]||'Kiểm tra Session và bằng chứng liên quan trước khi thay đổi dữ liệu.')}</span>
      </div>

      <div class="se-detail-grid">
        <span><small>Nhân viên</small><b>${esc(x.employee_code||'')} · ${esc(x.employee_name||'')}</b></span>
        <span><small>Công đoạn</small><b>${esc(x.operation_code||'')} · ${esc(x.operation_name||'')}</b></span>
        <span><small>Lệnh / chi tiết</small><b>${esc(x.po_code||'—')} / ${esc(x.part_code||'—')}</b></span>
        <span><small>Thời gian</small><b>${fmt(x.started_at)} → ${x.ended_at?fmt(x.ended_at):'Đang mở'}</b></span>
        <span><small>Sản lượng</small><b>${good} đạt · ${defect} lỗi · ${rework} sửa được</b></span>
        <span><small>Trạm</small><b>${x.station_id||x.device_uuid?esc(x.device_uuid||`#${x.station_id}`):'Chưa có trạm'}</b></span>
        <span><small>Nguồn dữ liệu</small><b>${esc(({QA_TEST:'QA Test',TUTORIAL_DEMO:'Tutorial/Demo',REAL_USER:'Thực tế',UNKNOWN:'Không xác định'})[x.data_source]||'Không xác định')}</b>${x.source_trace_id?`<small>${esc(x.source_trace_id)}</small>`:''}</span>
      </div>

      ${x.review_note||x.assigned_to||isDone(x)?`<div class="se-review-note"><b>Dấu vết xử lý</b>
        <span>Ghi nhận: ${fmt(x.review_created_at||x.started_at)} · Phụ trách: ${esc(x.assigned_to||'Chưa phân công')}</span>
        <span>Bắt đầu: ${fmt(x.review_started_at)} · bởi ${esc(x.started_by||'—')}</span>
        ${isDone(x)?`<span>Kết thúc: ${fmt(x.resolved_at)} · bởi ${esc(x.resolved_by==='system:auto_ignore'?'Hệ thống (tự động)':x.resolved_by||'—')} · ${esc(x.resolution==='AUTO_IGNORED'?'Tự động bỏ qua (không ảnh hưởng dữ liệu)':x.workflow_status==='IGNORED'?'Bỏ qua có lý do':x.resolution||'Đã xử lý')}</span>`:''}
        <p>${esc(x.review_note||'Chưa có ghi chú')}</p></div>`:''}

      <div class="se-steps">
        <div class="${x.workflow_status!=='NEW'?'done':''}"><b>1</b><span><strong>Nhận xử lý</strong><small>Ghi người phụ trách nếu cần.</small></span>${canStart?'<button class="btn" id="seStartOne">Nhận xử lý</button>':'<span class="se-step-ok">✓</span>'}</div>
        <div class="${inactive?'done':''}"><b>2</b><span><strong>Kiểm tra / sửa Session</strong><small>Mở đúng Session #${x.session_id}, chỉnh dữ liệu có bằng chứng và lưu.</small></span><button class="btn primary" id="seOpenSession">Mở Session #${x.session_id}</button></div>
        <div class="${isDone(x)?'done':''}"><b>3</b><span><strong>Xác nhận kết quả</strong><small>${inactive?'Bất thường đã biến mất; xác nhận để đóng việc.':'Chỉ hoàn tất sau khi đã kiểm tra hoặc sửa xong.'}</small></span>${canFinish?'<button class="btn" id="seResolveOne">Hoàn tất</button>':'<span class="se-step-ok">✓</span>'}</div>
      </div>

      <div class="se-secondary-actions">
        ${!isDone(x)?'<button class="btn" id="seIgnoreOne">Bỏ qua có lý do</button>':''}
      </div>`;
  };

  // Opens the shared Session Detail drawer in place -- never navigates to
  // Session Management. "Mở trong Quản lý Session" inside the drawer remains
  // the optional, explicit secondary path for advanced/admin editing.
  const viewSessionDetail=x=>{
    SessionDetailDrawer.open(x.session_id,{
      exceptionCode:x.exception_code,
      exceptionFingerprint:x.exception_fingerprint,
      onClaim:fresh=>{current=fresh||x;openWorkflow('IN_PROGRESS')},
      onResolve:fresh=>{current=fresh||x;openWorkflow('RESOLVED')},
      onIgnore:fresh=>{current=fresh||x;openWorkflow('IGNORED')},
      onOpenManagement:()=>{
        window.MESFLOW_SESSION_EXCEPTION_CONTEXT={
          sessionId:Number(x.session_id),
          startedAt:x.started_at,
          exceptionCode:x.exception_code,
          exceptionLabel:labels[x.exception_code]||x.exception_code
        };
        // Recorded so the "← Quay lại bất thường" button inside Session
        // Management returns to this exact tab/filter/scroll state instead
        // of always reloading Session bất thường from scratch.
        AppNav.push(()=>openPage('session-exceptions',document.querySelector('[data-page="session-exceptions"]')));
        SessionDetailDrawer.close();
        openPage('session-management',document.querySelector('[data-page="session-management"]'));
      }
    });
  };

  const bindDetail=()=>{
    const start=el('seStartOne');if(start)start.onclick=()=>openWorkflow('IN_PROGRESS');
    const resolve=el('seResolveOne');if(resolve)resolve.onclick=()=>openWorkflow('RESOLVED');
    const ignore=el('seIgnoreOne');if(ignore)ignore.onclick=()=>openWorkflow('IGNORED');
    const open=el('seOpenSession');if(open)open.onclick=()=>viewSessionDetail(current);
  };

  const draw=()=>{
    drawSummary();
    el('seCount').textContent=`${visible.length} mục`;
    el('seList').innerHTML=visible.length?visible.map(queueCard).join(''):'<div class="control-clear-state"><b>Không có mục phù hợp</b><span>Không còn việc trong bộ lọc hiện tại.</span></div>';
    el('seDetail').innerHTML=detailHtml(current);
    document.querySelectorAll('.se-card-trigger').forEach(b=>b.onclick=()=>{current=visible.find(x=>itemKey(x)===b.dataset.key)||null;draw()});
    document.querySelectorAll('.se-card-act').forEach(b=>b.onclick=e=>{
      e.stopPropagation();
      const item=visible.find(x=>itemKey(x)===b.dataset.key);
      if(!item)return;
      current=item;
      if(b.dataset.act==='process')openWorkflow(item.workflow_status==='IN_PROGRESS'?'RESOLVED':'IN_PROGRESS');
      else if(b.dataset.act==='ignore')openWorkflow('IGNORED');
      else if(b.dataset.act==='view')viewSessionDetail(item);
    });
    bindDetail();
  };

  const load=async()=>{
    const qs=new URLSearchParams({status:el('seSessionStatus').value,limit:'2000',view:currentView==='HISTORY'?'history':'inbox'});
    const d=await api('/api/session-exceptions?'+qs.toString());
    const keep=current?itemKey(current):'';
    allItems=d.items||[];
    current=allItems.find(x=>itemKey(x)===keep)||null;
    applyFilters();
  };

  const issueSummary=x=>`<div class="se-modal-issue-main"><div><small>Bất thường</small><b>${esc(labels[x.exception_code]||x.exception_code)}</b></div><div><small>Session</small><b>#${x.session_id}</b></div><div><small>Nhân viên</small><b>${esc(x.employee_code||'')} · ${esc(x.employee_name||'')}</b></div><div><small>Công đoạn</small><b>${esc(x.operation_code||'')} · ${esc(x.operation_name||'')}</b></div></div><p>${esc(x.exception_message||'')}</p>`;

  const openWorkflow=status=>{
    if(!current){toast('Chưa chọn bất thường');return}
    targetStatus=status;
    const isReceive=status==='IN_PROGRESS',isFinish=status==='RESOLVED',isIgnore=status==='IGNORED';
    const currentUser=String(window.MESFLOW_USER?.username||'').trim();
    const info={
      IN_PROGRESS:['Nhận xử lý','Xác nhận người phụ trách. Sau đó có thể mở ngay Session để kiểm tra và sửa dữ liệu.'],
      RESOLVED:['Hoàn tất xử lý','Xác nhận kết quả sau khi đã kiểm tra hoặc sửa Session.'],
      IGNORED:['Bỏ qua có lý do','Chỉ dùng khi đã kiểm tra và xác nhận đây là trường hợp hợp lệ hoặc cảnh báo không cần sửa.']
    }[status];
    el('seModalKicker').textContent=`${labels[current.exception_code]||current.exception_code} · Session #${current.session_id}`;
    el('seModalTitle').textContent=info[0];
    el('seModalHelp').textContent=info[1];
    el('seModalIssue').innerHTML=issueSummary(current);
    el('seAssigned').value=isReceive?(current.assigned_to||currentUser):(current.assigned_to||'');
    el('seAssignMe').hidden=!isReceive;
    el('seAssignedWrap').hidden=false;
    el('seAssignedHint').textContent=isReceive?'Mặc định là tài khoản đang đăng nhập. Có thể đổi nếu giao cho người khác.':'Người đang hoặc đã phụ trách mục này.';
    el('seResolutionWrap').hidden=!isFinish;
    el('seResolution').disabled=!isFinish;
    el('seResolution').value=isFinish?(current.is_active===false?'DATA_CORRECTED':current.resolution||''):'';
    el('seNoteWrap').hidden=false;
    el('seNote').value=isReceive?'':current.review_note||'';
    el('seNote').placeholder=isReceive?'Ví dụ: Đang kiểm tra lại giờ kết thúc với tổ trưởng.':isIgnore?'Bắt buộc ghi rõ vì sao không cần xử lý.':'Ghi ngắn đã kiểm tra/sửa gì và kết quả.';
    el('seNoteHint').textContent=isReceive?'Không bắt buộc. Chỉ ghi khi cần bàn giao hoặc lưu ý.':isIgnore?'Bắt buộc ghi lý do bỏ qua.':isFinish?'Bắt buộc ghi kết quả xử lý.':'';
    el('seModalNext').innerHTML=isReceive?`<b>Bước tiếp theo</b><span>Sau khi nhận, nên mở Session #${current.session_id} để kiểm tra. Bạn có thể làm ngay bằng nút bên dưới.</span>`:isFinish?`<b>Kiểm tra trước khi hoàn tất</b><span>${current.is_active===false?'Hệ thống không còn phát hiện bất thường này. Hãy xác nhận dữ liệu hiện tại là đúng.':'Bất thường vẫn đang được phát hiện. Chỉ hoàn tất nếu đã kiểm tra và có lý do rõ ràng.'}</span>`:'<b>Lưu ý</b><span>Bỏ qua không sửa dữ liệu. Lý do sẽ được lưu trong nhật ký xử lý.</span>';
    el('seModalSave').textContent=isReceive?'Chỉ nhận xử lý':isFinish?'Xác nhận hoàn tất':'Xác nhận bỏ qua';
    el('seModalSecondary').hidden=!isReceive;
    el('seModalSecondary').textContent='Nhận và mở Session';
    el('seModalSecondary').className='btn primary';
    el('seModalSave').className=isReceive?'btn':'btn primary';
    el('seAssignMe').onclick=()=>{el('seAssigned').value=currentUser;el('seAssigned').focus()};
    el('seModal').classList.remove('hidden');
    document.body.classList.add('modal-open');
    setTimeout(()=>isReceive?el('seAssigned').focus():el('seNote').focus(),0);
  };

  const close=()=>{el('seModal').classList.add('hidden');document.body.classList.remove('modal-open')};
  el('seModalClose').onclick=el('seModalCancel').onclick=close;
  el('seModal').onclick=e=>{if(e.target===el('seModal'))close()};
  const saveWorkflow=async({openSessionAfter=false}={})=>{
    const note=el('seNote').value.trim();
    const assigned=el('seAssigned').value.trim();
    if(targetStatus==='IN_PROGRESS'&&!assigned){alert('Hãy chọn người phụ trách');el('seAssigned').focus();return}
    if(['RESOLVED','IGNORED'].includes(targetStatus)&&!note){alert('Phải nhập ghi chú xử lý');el('seNote').focus();return}
    if(targetStatus==='RESOLVED'&&!el('seResolution').value){alert('Hãy chọn kết quả xử lý');el('seResolution').focus();return}
    const payload={
      workflow_status:targetStatus,
      note,
      assigned_to:assigned,
      resolution:targetStatus==='RESOLVED'?el('seResolution').value:'',
      items:[{session_id:current.session_id,exception_code:current.exception_code,exception_fingerprint:current.exception_fingerprint}]
    };
    try{
      await api('/api/session-exceptions/workflow',{method:'PATCH',body:JSON.stringify(payload)});
      const selected=current;
      close();
      // Update the active list and either close or refresh the drawer --
      // never navigate to Session Management. Filters/tab/scroll on this
      // page are untouched by any of this.
      if(SessionDetailDrawer.isOpenFor(selected.session_id))SessionDetailDrawer.close();
      toast(targetStatus==='RESOLVED'?'Đã hoàn tất xử lý':targetStatus==='IN_PROGRESS'?'Đã nhận xử lý':targetStatus==='IGNORED'?'Đã bỏ qua có lý do':'Đã mở lại xử lý');
      await load();
      if(openSessionAfter&&targetStatus==='IN_PROGRESS'){
        const refreshed=allItems.find(x=>String(x.session_id)===String(selected.session_id)&&x.exception_code===selected.exception_code)||selected;
        current=refreshed;
        viewSessionDetail(refreshed);
        return;
      }
    }catch(e){alert(e.message)}
  };
  el('seModalSave').onclick=()=>saveWorkflow();
  el('seModalSecondary').onclick=()=>saveWorkflow({openSessionAfter:true});

  document.querySelectorAll('[data-se-view]').forEach(button=>button.onclick=()=>{
    const wasHistory=currentView==='HISTORY';
    currentView=button.dataset.seView;
    document.querySelectorAll('[data-se-view]').forEach(x=>{const selected=x===button;x.classList.toggle('primary',selected);x.setAttribute('aria-selected',String(selected))});
    el('seHistoryFilters').hidden=currentView!=='HISTORY';current=null;
    // Inbox tabs (Cần xử lý / Cần xác nhận) share one server-side fetch
    // (view=inbox); History is a different, wider server-side fetch
    // (view=history) -- crossing that boundary needs a real reload, not
    // just re-filtering the already-fetched Inbox subset.
    if(wasHistory!==(currentView==='HISTORY'))load();else applyFilters();
  });
  ['seHistoryFrom','seHistoryEmployee','seHistoryPo','seHistoryType','seHistoryResult','seHistoryHandler'].forEach(key=>el(key).oninput=applyFilters);
  el('seSearch').oninput=applyFilters;
  el('seSessionStatus').onchange=load;
  el('seDataSource').onchange=applyFilters;
  el('seRefresh').onclick=load;
  el('seHistoryType').insertAdjacentHTML('beforeend',Object.entries(labels).map(([value,label])=>`<option value="${esc(value)}">${esc(label)}</option>`).join(''));
  await load();
}
