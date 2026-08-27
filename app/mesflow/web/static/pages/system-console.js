// SUPER_ADMIN / IT System Console (task spec sections 5-16). Every call here
// hits /api/system-health/* -- gated server-side by super_admin_required()/
// ok() in mesflow.web.system_health -- built on data other modules already
// collect (SystemHealthService/DiagnosticService/LogService/
// SystemOperationsService/system_audit_service). No second data store, no
// invented metrics: anything the backend can't reliably read comes back as
// "Không khả dụng" and is rendered as such, never a fabricated value.

const SC_SEVERITY_LABEL={CRITICAL:'Nghiêm trọng',ERROR:'Lỗi',HIGH:'Nghiêm trọng',MEDIUM:'Cảnh báo',WARNING:'Cảnh báo',INFO:'Thông tin'};
const SC_SEVERITY_TONE=s=>({CRITICAL:'danger',HIGH:'danger',ERROR:'danger',MEDIUM:'warning',WARNING:'warning',INFO:'neutral'}[String(s||'').toUpperCase()]||'neutral');

async function renderSystemOverview(){
  title.textContent='Tổng quan hệ thống';subtitle.textContent='Sức khỏe MESFlow, cơ sở dữ liệu, QA Center và Deploy Agent — không dùng dữ liệu giả định.';
  content.innerHTML=MFUI.loadingState();
  let d;try{d=await api('/api/system-health')}catch(e){content.innerHTML=MFUI.errorState(e.message,'scOverviewRetry');document.getElementById('scOverviewRetry').onclick=renderSystemOverview;return}
  const env=String(d.environment||'').toUpperCase()||'KHÔNG RÕ';
  const envTone=env==='PRODUCTION'?'danger':(env==='TEST'?'warning':'neutral');
  const compRow=c=>{
    const label={MESFLOW:'MESFlow Application',POSTGRESQL:'Database',DEPLOY_AGENT:'Deploy Agent',QA_CENTER:'QA Center',SERVER:'Server / Docker',DOCKER:'Docker',KIOSK_FLEET:'Kiosk Fleet',JOBS:'Background Jobs',SESSION_LIFECYCLE:'Session Lifecycle'}[c.component]||c.component;
    if(!c.configured)return `<tr><td>${esc(label)}</td><td>${MFUI.statusBadge('UNKNOWN','Không khả dụng')}</td><td class="sc-muted">Chưa cấu hình</td></tr>`;
    return `<tr><td>${esc(label)}</td><td>${MFUI.statusBadge(c.status)}</td><td>${esc(c.message||'')}</td></tr>`;
  };
  content.innerHTML=`<div class="page-shell">
    ${MFUI.contentPanel({title:'Định danh môi trường',body:`<div class="sc-kv-grid">
      <div><span>Môi trường</span><b>${MFUI.statusBadge(envTone==='danger'?'CRITICAL':(envTone==='warning'?'WARNING':'HEALTHY'),env)}</b></div>
      <div><span>MESFlow version</span><b>${esc(d.application_version||'—')}</b></div>
      <div><span>Server role</span><b>${esc(d.server_role||'—')}</b></div>
      <div><span>Thời gian máy chủ</span><b>${esc(fmt(d.checked_at))}</b></div>
      <div><span>Cảnh báo đang mở</span><b>${esc(d.active_alerts_count??0)}</b></div>
      <div><span>Lỗi hệ thống gần đây</span><b>${esc(d.recent_errors_count??0)}</b></div>
    </div>`})}
    ${MFUI.contentPanel({title:'Sức khỏe thành phần',body:`<div class="table-wrap"><table><thead><tr><th>Thành phần</th><th>Trạng thái</th><th>Chi tiết</th></tr></thead><tbody>${(d.components||[]).map(compRow).join('')}</tbody></table></div>`})}
  </div>`;
}

async function renderSystemErrors(){
  title.textContent='Lỗi hệ thống';subtitle.textContent='HTTP 500, kết nối DB, dịch vụ gián đoạn — khác với NG sản phẩm và ngoại lệ Session (không dùng chung).';
  content.innerHTML=`${MFUI.filterBar({content:'',actions:'<button class="btn primary" id="scErrLoad">Làm mới</button>'})}<div id="scErrRows">${MFUI.loadingState()}</div>`;
  const rows=document.getElementById('scErrRows');
  async function run(){
    rows.innerHTML=MFUI.loadingState();
    try{
      const d=await api('/api/system-health/errors?limit=200');
      const items=d.items||[];
      rows.innerHTML=items.length?`<div class="table-wrap"><table><thead><tr><th>Lần cuối</th><th>Dịch vụ</th><th>Mức độ</th><th>Thông điệp</th><th>Số lần</th><th>Lần đầu</th></tr></thead><tbody>${items.map(x=>`<tr><td>${esc(fmt(x.last_at))}</td><td>${esc(x.component||'')}</td><td>${MFUI.statusBadge(SC_SEVERITY_TONE(x.severity)==='danger'?'CRITICAL':'WARNING',SC_SEVERITY_LABEL[String(x.severity||'').toUpperCase()]||x.severity)}</td><td>${esc(x.message||'')}</td><td>${esc(x.occurrences||1)}</td><td>${esc(fmt(x.first_at))}</td></tr>`).join('')}</tbody></table></div>`:MFUI.emptyState('Không có lỗi hệ thống','Trong cửa sổ theo dõi hiện tại.');
    }catch(e){rows.innerHTML=MFUI.errorState(e.message)}
  }
  document.getElementById('scErrLoad').onclick=run;await run();
}

async function renderSystemLogsIT(){
  title.textContent='Nhật ký';subtitle.textContent='Log kỹ thuật theo nguồn, giới hạn số dòng — không phải trình duyệt file hệ thống.';
  const sources=[['mesflow','MESFlow application'],['postgres','Database'],['qa','QA Center'],['agent','Deploy Agent']];
  content.innerHTML=`${MFUI.filterBar({content:`<label><span>Nguồn</span><select id="scLogSource">${sources.map(([v,l])=>`<option value="${v}">${esc(l)}</option>`).join('')}</select></label><label><span>Số dòng</span><select id="scLogLines"><option value="100">100</option><option value="200" selected>200</option><option value="500">500</option><option value="1000">1000 (tối đa)</option></select></label>`,actions:'<button class="btn primary" id="scLogLoad">Tải log</button>'})}<div id="scLogView">${MFUI.emptyState('Chọn nguồn và tải log','Log được lấy trực tiếp từ Deploy Agent, đã được ẩn thông tin nhạy cảm (password/token/cookie/...).')}</div>`;
  document.getElementById('scLogLoad').onclick=async()=>{
    const view=document.getElementById('scLogView');view.innerHTML=MFUI.loadingState();
    const source=document.getElementById('scLogSource').value,lines=document.getElementById('scLogLines').value;
    try{
      const d=await api(`/api/system-health/logs?source=${encodeURIComponent(source)}&lines=${encodeURIComponent(lines)}`);
      if(!d.ok){view.innerHTML=MFUI.errorState(d.error==='NOT_CONFIGURED'?'Deploy Agent chưa được cấu hình cho MESFlow.':(d.error||'Không tải được log'));return}
      view.innerHTML=`<div class="content-panel"><div class="content-panel-head"><div><h3>${esc(d.label||source)}</h3><p>${esc(d.lines||lines)} dòng gần nhất</p></div></div><div class="content-panel-body"><pre class="json sc-log-pre">${esc(d.text||'(trống)')}</pre></div></div>`;
    }catch(e){view.innerHTML=MFUI.errorState(e.message)}
  };
}

const SC_SERVICE_LABEL={mesflow_app:'MESFlow Application',qa_center:'QA Center'};

async function renderSystemServices(){
  title.textContent='Dịch vụ';subtitle.textContent='Sức khỏe và khởi động lại theo danh sách cho phép — không có ô nhập tên dịch vụ tự do.';
  content.innerHTML=MFUI.loadingState();
  let env='';try{env=String((await api('/api/system-health')).environment||'').toUpperCase()}catch(_){}
  async function run(){
    content.innerHTML=MFUI.loadingState();
    let d;try{d=await api('/api/system-health/services')}catch(e){content.innerHTML=MFUI.errorState(e.message);return}
    const items=d.items||[];
    content.innerHTML=`<div class="page-shell">${env==='PRODUCTION'?'<div class="sc-prod-banner"><b>Môi trường PRODUCTION</b> — thao tác khởi động lại có thể làm gián đoạn người dùng đang sử dụng hệ thống.</div>':''}
      <div class="table-wrap"><table><thead><tr><th>Dịch vụ</th><th>Trạng thái</th><th>Chi tiết</th><th></th></tr></thead><tbody>${items.map(x=>`<tr><td>${esc(SC_SERVICE_LABEL[x.id]||x.label||x.id)}</td><td>${MFUI.statusBadge(x.reachable?x.status:'UNKNOWN',x.reachable?x.status:'Không kết nối được')}</td><td>${x.reachable?esc(x.health?JSON.stringify(x.health):(x.container||'')):esc(x.error||'')}</td><td><button class="btn" data-restart="${esc(x.id)}" ${x.reachable?'':'disabled'}>Khởi động lại</button></td></tr>`).join('')}</tbody></table></div>
    </div>`;
    content.querySelectorAll('[data-restart]').forEach(btn=>btn.onclick=async()=>{
      const id=btn.dataset.restart,label=SC_SERVICE_LABEL[id]||id;
      const message=env==='PRODUCTION'
        ?`Khởi động lại ${label} trên PRODUCTION? Có thể làm gián đoạn người dùng đang sử dụng hệ thống.`
        :`Khởi động lại ${label} trên ${env||'môi trường hiện tại'}?`;
      const reason=await MFUI.confirmDialog({title:'Xác nhận khởi động lại dịch vụ',message,confirmLabel:'Khởi động lại',danger:true,reason:true});
      if(reason===null)return;
      if(!reason){toast('Vui lòng nhập lý do');return}
      btn.disabled=true;btn.textContent='Đang khởi động lại…';
      try{
        const res=await api(`/api/system-health/services/${encodeURIComponent(id)}/restart`,{method:'POST',body:JSON.stringify({reason,confirm_production:env==='PRODUCTION'})});
        const r=res.item||{};
        toast(res.ok?`${label}: ${r.result||'RESTARTED'}`:`${label} THẤT BẠI: ${r.result||r.error||'lỗi không rõ'}`);
      }catch(e){toast(`${label} THẤT BẠI: ${e.message}`)}
      await run();
    });
  }
  await run();
}

async function renderSystemDiagnostics(){
  title.textContent='Chẩn đoán';subtitle.textContent='Kiểm tra chỉ đọc: DB, migration, QA Center, Deploy Agent, kiosk fleet.';
  content.innerHTML=MFUI.loadingState();
  let list;try{list=(await api('/api/system-health/diagnostics')).items||[]}catch(e){content.innerHTML=MFUI.errorState(e.message);return}
  content.innerHTML=`<div class="table-wrap"><table><thead><tr><th>Kiểm tra</th><th>Kết quả</th><th>Chi tiết</th><th></th></tr></thead><tbody>${list.map(x=>`<tr id="scDiag-${esc(x.id)}"><td>${esc(x.label)}</td><td class="sc-diag-result">—</td><td class="sc-diag-detail sc-muted">Chưa chạy</td><td><button class="btn" data-diag="${esc(x.id)}">Chạy kiểm tra</button></td></tr>`).join('')}</tbody></table></div>`;
  content.querySelectorAll('[data-diag]').forEach(btn=>btn.onclick=async()=>{
    const id=btn.dataset.diag,row=document.getElementById(`scDiag-${id}`),resultCell=row.querySelector('.sc-diag-result'),detailCell=row.querySelector('.sc-diag-detail');
    btn.disabled=true;resultCell.innerHTML=MFUI.statusBadge('RUNNING','Đang chạy…');detailCell.textContent='';
    try{
      const d=(await api(`/api/system-health/diagnostics/${encodeURIComponent(id)}`,{method:'POST'})).item||{};
      const data=d.data_json||{};
      const failed=data.error||data.connection==='FAILED'||data.agent_reachable===false||data.reachable===false;
      resultCell.innerHTML=MFUI.statusBadge(failed?'CRITICAL':'HEALTHY',failed?'FAIL':'PASS');
      detailCell.innerHTML=`<pre class="json sc-diag-json">${esc(JSON.stringify(data,null,1))}</pre>`;
    }catch(e){resultCell.innerHTML=MFUI.statusBadge('CRITICAL','FAIL');detailCell.textContent=e.message}
    btn.disabled=false;
  });
}

async function renderSystemAudit(){
  title.textContent='Nhật ký quản trị';subtitle.textContent='Cấp/thu hồi Super Admin, khởi động lại dịch vụ, thao tác kỹ thuật đặc quyền — chỉ ghi thêm, không xóa.';
  content.innerHTML=MFUI.loadingState();
  try{
    const items=(await api('/api/system-health/audit?limit=300')).items||[];
    content.innerHTML=items.length?`<div class="table-wrap"><table><thead><tr><th>Thời gian</th><th>Người thực hiện</th><th>Vai trò</th><th>Môi trường</th><th>Hành động</th><th>Đối tượng</th><th>Lý do</th><th>Kết quả</th></tr></thead><tbody>${items.map(x=>`<tr><td>${esc(fmt(x.occurred_at))}</td><td>${esc(x.actor_username||'')}</td><td>${esc(x.actor_role||'')}</td><td>${esc(x.environment||'')}</td><td><b>${esc(x.action||'')}</b></td><td>${esc(x.target||'')}</td><td>${esc(x.reason||'')}</td><td>${MFUI.statusBadge(/SUCCESS|RESTARTED|STARTED|STOPPED/.test(x.result||'')?'HEALTHY':'CRITICAL',x.result||'')}</td></tr>`).join('')}</tbody></table></div>`:MFUI.emptyState('Chưa có thao tác đặc quyền nào được ghi nhận');
  }catch(e){content.innerHTML=MFUI.errorState(e.message)}
}
