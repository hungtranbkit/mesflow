// Shared Session Detail component. Loaded once, used by Session Exceptions
// (in-place drawer, replacing the old "navigate to Session Management" flow)
// and reusable by Session Management (same field grid, same labels) so the
// two never drift into separate implementations. Never navigates the page.

// --- Shared Vietnamese label maps -----------------------------------------
// Single source of truth for exception/workflow/source vocabulary. Other
// pages should read these instead of keeping their own copies.
const MF_EXCEPTION_LABELS={
  OVERLAP:'Chồng thời gian',
  OPEN_TOO_LONG:'Mở quá lâu',
  ZERO_QTY_LONG:'Không có sản lượng',
  MISSING_STATION:'Thiếu trạm',
  INVALID_TIME:'Sai thời gian'
};
const MF_EXCEPTION_HINTS={
  OVERLAP:'Kiểm tra hai Session trùng giờ. Thường cần sửa thời gian hoặc Session ghi nhầm.',
  OPEN_TOO_LONG:'Kiểm tra công nhân đã kết thúc công việc chưa. Nếu quên đóng, sửa Session và nhập giờ kết thúc đúng.',
  ZERO_QTY_LONG:'Đối chiếu phiếu sản xuất. Chỉ nhập sản lượng khi có bằng chứng; nếu thực tế không sản xuất, ghi rõ lý do.',
  MISSING_STATION:'Xác minh công nhân làm tại trạm nào. Chỉ bổ sung trạm nếu có căn cứ.',
  INVALID_TIME:'Giờ kết thúc đang trước giờ bắt đầu. Cần sửa lại thời gian đúng trước khi hoàn tất xử lý.'
};
const MF_WORKFLOW_LABELS={NEW:'Mới',IN_PROGRESS:'Đang xử lý',RESOLVED:'Đã xử lý',IGNORED:'Bỏ qua'};
const MF_SEVERITY_LABELS={CRITICAL:'Nghiêm trọng',ERROR:'Cần xử lý',WARNING:'Cảnh báo',INFO:'Đã thay đổi'};
const MF_SOURCE_LABELS={QA_TEST:'QA Test',TUTORIAL:'Tutorial/Demo',TUTORIAL_DEMO:'Tutorial/Demo',REAL_USER:'Thực tế',UNKNOWN:'Không xác định'};
const MF_CLASSIFICATION_LABELS={ACTION_REQUIRED:'Cần xử lý',CONFIRMATION:'Cần xác nhận',USER_MISTAKE:'Lỗi thao tác nhỏ',AUTO_RECOVERED:'Tự khôi phục',QA_TEST:'QA Test',TUTORIAL:'Tutorial/Demo',HISTORY_ONLY:'Lịch sử',UNKNOWN:'Không xác định'};
const MF_IMPACT_LABELS={
  OVERLAP:'Ảnh hưởng: thời gian công đoạn đang bị trùng.',
  OPEN_TOO_LONG:'Ảnh hưởng: thời gian công đoạn đang sai.',
  ZERO_QTY_LONG:'Ảnh hưởng: sản lượng/KPI có thể thiếu chính xác.',
  MISSING_STATION:'Ảnh hưởng: không xác định được trạm làm việc.',
  INVALID_TIME:'Ảnh hưởng: thời gian công đoạn đang sai.'
};

// --- Shared key/value detail grid ------------------------------------------
// rows: [{label, value(html-safe already), wide?}]. One canonical layout for
// "Session Detail" content everywhere it appears.
function kvGrid(rows){
  return `<div class="kv-grid">${rows.filter(Boolean).map(row=>{
    if(row.wide) return `<div class="kv-row kv-wide"><div class="kv-wide-block"><small>${esc(row.label)}</small><b>${row.value}</b></div></div>`;
    return `<div class="kv-row"><span class="kv-label">${esc(row.label)}</span><span class="kv-value">${row.value}</span></div>`;
  }).join('')}</div>`;
}

const sourceBadgeHtml=source=>{
  const key=String(source||'UNKNOWN').toLowerCase();
  return `<span class="se-source-badge ${esc(key)}">${esc(MF_SOURCE_LABELS[String(source||'').toUpperCase()]||'Không xác định')}</span>`;
};

const mfDisplayDuration=seconds=>{
  seconds=Math.max(0,Number(seconds||0));
  const minutes=Math.floor(seconds/60);
  return `${Math.floor(minutes/60)}h ${String(minutes%60).padStart(2,'0')}m`;
};

// Core session field rows shared between the drawer and Session Management.
function sessionCoreFieldRows(x){
  const good=Number(x.good_qty||0),defect=Number(x.defect_qty||0),rework=Number(x.rework_qty||0);
  return [
    {label:'Session ID',value:`#${esc(x.session_id)}`},
    {label:'Nhân viên',value:esc(x.employee_name||'—')},
    {label:'Mã nhân viên',value:esc(x.employee_code||'—')},
    {label:'Production Order',value:esc(x.po_code||'—')},
    {label:'Part',value:esc(`${x.part_code||'—'}${x.part_name?' · '+x.part_name:''}`)},
    {label:'Operation',value:esc(`${x.operation_code||'—'}${x.operation_name?' · '+x.operation_name:''}`)},
    {label:'Trạm',value:esc(x.station_code||x.station_name||'Chưa gán')},
    {label:'Device / kiosk',value:esc(x.device_uuid||'—')},
    {label:'Nguồn',value:sourceBadgeHtml(x.data_source)},
    {label:'Trạng thái',value:x.status==='OPEN'?'<span class="badge warning">Đang chạy</span>':'<span class="badge success">Đã kết thúc</span>'},
    {label:'Bắt đầu',value:esc(fmt(x.started_at))},
    {label:'Kết thúc',value:x.ended_at?esc(fmt(x.ended_at)):'Đang chạy'},
    {label:'Thời lượng',value:esc(mfDisplayDuration(x.duration_seconds))},
    {label:'Sản lượng',value:`${good} đạt · ${defect} lỗi · ${rework} sửa được`}
  ];
}

function technicalDetailsHtml(x){
  const rows=[
    {label:'session_id',value:esc(x.session_id)},
    {label:'employee_id',value:esc(x.employee_id)},
    {label:'operation_id',value:esc(x.operation_id)},
    {label:'station_id',value:esc(x.station_id||'—')},
    {label:'po_id',value:esc(x.po_id||'—')},
    {label:'part_id',value:esc(x.part_id||'—')},
    {label:'device_uuid (raw)',value:esc(x.device_uuid||'—')},
    {label:'start_request_id',value:esc(x.start_request_id||'—')},
    {label:'finish_request_id',value:esc(x.finish_request_id||'—')},
    {label:'created_at',value:esc(fmt(x.created_at))},
    {label:'updated_at',value:esc(fmt(x.updated_at))},
    {label:'Ghi chú',value:esc(x.note||'Không có ghi chú'),wide:true}
  ];
  return `<div class="drawer-tech"><details><summary>Chi tiết kỹ thuật</summary>${kvGrid(rows)}</details></div>`;
}

function activityTimelineHtml(activity){
  if(!activity||!activity.length) return '<p class="drawer-empty">Chưa có hoạt động kiosk ghi nhận cho Session này.</p>';
  return `<div class="drawer-timeline">${activity.map(e=>`<div class="drawer-timeline-item"><time>${esc(fmt(e.occurred_at))}</time><div><b>${esc(e.event_type||'—')}</b>${e.message?`<small>${esc(e.message)}</small>`:''}</div></div>`).join('')}</div>`;
}

function exceptionHistoryHtml(exceptions){
  if(!exceptions||!exceptions.length) return '<p class="drawer-empty">Session này chưa từng phát sinh bất thường.</p>';
  return `<div class="drawer-timeline">${exceptions.map(x=>`<div class="drawer-timeline-item"><time>${esc(fmt(x.started_at))}</time><div><b>${esc(MF_EXCEPTION_LABELS[x.exception_code]||x.exception_code)} <span class="workflow-badge ${String(x.workflow_status||'NEW').toLowerCase()}">${esc(MF_WORKFLOW_LABELS[x.workflow_status]||x.workflow_status)}</span></b><small>${esc(x.exception_message||'')}</small></div></div>`).join('')}</div>`;
}

function resolutionHistoryHtml(reviews){
  if(!reviews||!reviews.length) return '<p class="drawer-empty">Chưa có xử lý nào được ghi nhận.</p>';
  return `<div class="drawer-timeline">${reviews.map(r=>{
    const isDone=['RESOLVED','IGNORED'].includes(r.workflow_status);
    const when=isDone?r.resolved_at:(r.started_at||r.created_at);
    const by=isDone?(r.resolved_by==='system:auto_ignore'?'Hệ thống (tự động)':r.resolved_by):r.started_by;
    const reasonText=r.resolution==='AUTO_IGNORED'?'Tự động bỏ qua (không ảnh hưởng dữ liệu)':(r.workflow_status==='IGNORED'?'Bỏ qua có lý do':(r.resolution||''));
    return `<div class="drawer-timeline-item"><time>${esc(fmt(when))}</time><div><b>${esc(MF_EXCEPTION_LABELS[r.exception_code]||r.exception_code)} · ${esc(MF_WORKFLOW_LABELS[r.workflow_status]||r.workflow_status)}</b><small>${esc([by&&`bởi ${by}`,reasonText].filter(Boolean).join(' · '))}</small>${r.note?`<small>${esc(r.note)}</small>`:''}</div></div>`;
  }).join('')}</div>`;
}

// --- Session Detail drawer ---------------------------------------------
const SessionDetailDrawer=(()=>{
  let root=null,openSessionId=null;
  const ensureRoot=()=>{
    if(root)return root;
    root=document.createElement('div');
    root.id='sessionDetailDrawerRoot';
    root.className='drawer-backdrop hidden';
    document.body.appendChild(root);
    root.addEventListener('click',e=>{if(e.target===root)close()});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!root.classList.contains('hidden'))close()});
    return root;
  };
  const setUrlState=id=>{
    try{
      const url=new URL(location.href);
      if(id)url.searchParams.set('session',String(id));else url.searchParams.delete('session');
      history.replaceState(history.state,'',url.toString());
    }catch(e){/* URL state is optional; never block the drawer on it */}
  };
  const close=()=>{
    if(!root)return;
    root.classList.add('hidden');
    document.body.classList.remove('drawer-open');
    openSessionId=null;
    setUrlState(null);
  };
  const isOpenFor=sessionId=>openSessionId!==null&&Number(sessionId)===openSessionId;
  const actionButtonsHtml=opts=>{
    const buttons=[];
    if(opts.onClaim&&opts.exceptionStatus==='NEW')buttons.push('<button class="btn primary" id="sdActClaim" type="button">Xử lý</button>');
    else if(opts.onResolve&&opts.exceptionStatus==='IN_PROGRESS')buttons.push('<button class="btn primary" id="sdActResolve" type="button">Xử lý</button>');
    if(opts.onIgnore&&['NEW','IN_PROGRESS'].includes(opts.exceptionStatus))buttons.push('<button class="btn" id="sdActIgnore" type="button">Bỏ qua</button>');
    return buttons.join('');
  };
  const render=(data,opts)=>{
    const x=data.session;
    const activeException=(opts.exceptionCode&&opts.exceptionFingerprint)
      ?(data.exceptions||[]).find(e=>e.exception_code===opts.exceptionCode&&e.exception_fingerprint===opts.exceptionFingerprint)
      :(data.exceptions||[]).find(e=>e.is_active!==false&&['NEW','IN_PROGRESS'].includes(e.workflow_status));
    const exceptionStatus=activeException?activeException.workflow_status:null;
    const panel=root.querySelector('.drawer-panel');
    panel.querySelector('.drawer-head').innerHTML=`
      <div>
        <h2>Session #${esc(x.session_id)}</h2>
        <p>${esc(x.employee_name||'')} · ${esc(x.operation_code||'')} ${esc(x.operation_name||'')}</p>
        <div class="drawer-badges">${sourceBadgeHtml(x.data_source)}${x.status==='OPEN'?'<span class="badge warning">Đang chạy</span>':'<span class="badge success">Đã kết thúc</span>'}${activeException?`<span class="workflow-badge ${String(activeException.workflow_status||'NEW').toLowerCase()}">${esc(MF_WORKFLOW_LABELS[activeException.workflow_status]||activeException.workflow_status)}</span>`:''}</div>
      </div>
      <button class="btn drawer-close" id="sdClose" type="button">Đóng</button>`;
    const currentExceptionSection=activeException?`
      <section class="drawer-section">
        <h3>Bất thường hiện tại</h3>
        <div class="drawer-callout">
          <b>${esc(MF_EXCEPTION_LABELS[activeException.exception_code]||activeException.exception_code)}</b>
          <p>${esc(activeException.exception_message||'')}</p>
          <p>${esc(MF_IMPACT_LABELS[activeException.exception_code]||'')}</p>
          <p>${esc(MF_EXCEPTION_HINTS[activeException.exception_code]||'Kiểm tra Session và bằng chứng liên quan trước khi thay đổi dữ liệu.')}</p>
        </div>
      </section>`:'';
    panel.querySelector('.drawer-body').innerHTML=`
      ${currentExceptionSection}
      <section class="drawer-section"><h3>Thông tin Session</h3>${kvGrid(sessionCoreFieldRows(x))}</section>
      <section class="drawer-section"><h3>Dòng thời gian hoạt động</h3>${activityTimelineHtml(data.activity)}</section>
      <section class="drawer-section"><h3>Lịch sử bất thường</h3>${exceptionHistoryHtml(data.exceptions)}</section>
      <section class="drawer-section"><h3>Lịch sử xử lý</h3>${resolutionHistoryHtml(data.reviews)}</section>
      <section class="drawer-section">${technicalDetailsHtml(x)}</section>`;
    panel.querySelector('.drawer-actions').innerHTML=`
      <div class="drawer-actions-primary">${actionButtonsHtml({...opts,exceptionStatus})}</div>
      ${opts.onOpenManagement?'<button class="btn" id="sdActOpenManagement" type="button">Mở trong Quản lý Session</button>':''}`;
    panel.querySelector('#sdClose').onclick=close;
    const claim=panel.querySelector('#sdActClaim');if(claim)claim.onclick=()=>opts.onClaim(activeException);
    const resolve=panel.querySelector('#sdActResolve');if(resolve)resolve.onclick=()=>opts.onResolve(activeException);
    const ignore=panel.querySelector('#sdActIgnore');if(ignore)ignore.onclick=()=>opts.onIgnore(activeException);
    const openMgmt=panel.querySelector('#sdActOpenManagement');if(openMgmt)openMgmt.onclick=()=>opts.onOpenManagement(x);
  };
  const open=async(sessionId,opts={})=>{
    sessionId=Number(sessionId);
    openSessionId=sessionId;
    const r=ensureRoot();
    r.innerHTML=`<div class="drawer-panel" role="dialog" aria-modal="true" aria-label="Chi tiết Session">
      <div class="drawer-head"><div><h2>Session #${esc(sessionId)}</h2><p>Đang tải...</p></div><button class="btn drawer-close" id="sdClose" type="button">Đóng</button></div>
      <div class="drawer-body" aria-busy="true"><p class="drawer-empty">Đang tải chi tiết Session…</p></div>
      <div class="drawer-actions"></div>
    </div>`;
    r.querySelector('#sdClose').onclick=close;
    r.classList.remove('hidden');
    document.body.classList.add('drawer-open');
    setUrlState(sessionId);
    try{
      const data=await api(`/api/session-management/${sessionId}`);
      if(openSessionId!==sessionId)return; // a newer open() superseded this one
      render(data,opts);
    }catch(e){
      if(openSessionId!==sessionId)return;
      r.querySelector('.drawer-body').innerHTML=`<div class="empty danger"><b>Không tải được Session</b><span>${esc(e.message||'Thử lại.')}</span></div>`;
      r.querySelector('.drawer-body').removeAttribute('aria-busy');
    }
  };
  return {open,close,isOpenFor};
})();
window.SessionDetailDrawer=SessionDetailDrawer;
window.kvGrid=kvGrid;
window.MF_EXCEPTION_LABELS=MF_EXCEPTION_LABELS;
window.MF_EXCEPTION_HINTS=MF_EXCEPTION_HINTS;
window.MF_WORKFLOW_LABELS=MF_WORKFLOW_LABELS;
window.MF_SEVERITY_LABELS=MF_SEVERITY_LABELS;
window.MF_SOURCE_LABELS=MF_SOURCE_LABELS;
window.MF_CLASSIFICATION_LABELS=MF_CLASSIFICATION_LABELS;
window.sessionCoreFieldRows=sessionCoreFieldRows;
window.MF_IMPACT_LABELS=MF_IMPACT_LABELS;
window.sourceBadgeHtml=sourceBadgeHtml;
