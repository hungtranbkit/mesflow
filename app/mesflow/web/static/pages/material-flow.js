(function(){
  const E=v=>window.esc?window.esc(v??''):String(v??'');
  const F=v=>window.format?window.format(Number(v||0)):Number(v||0).toLocaleString('vi-VN');
  const DT=v=>v?new Date(v).toLocaleString('vi-VN'):'—';
  const kindLabel=k=>String(k||'GOOD').toUpperCase()==='REWORK'?'Lỗi sửa được (REWORK)':'Hàng đạt (GOOD)';

  function ensureModal(){
    let root=document.getElementById('materialFlowModal');
    if(root)return root;
    root=document.createElement('div');
    root.id='materialFlowModal';
    root.className='material-flow-overlay hidden';
    root.setAttribute('role','dialog');root.setAttribute('aria-modal','true');root.setAttribute('aria-labelledby','mfTitle');
    root.innerHTML=`<div class="material-flow-backdrop" data-mf-close></div>
      <section class="material-flow-dialog">
        <header class="mf-dialog-head"><div><small>DÒNG VẬT TƯ</small><h2 id="mfTitle">Truy vết Material Flow</h2><p id="mfSubtitle"></p></div><button class="btn" type="button" data-mf-close>Đóng</button></header>
        <div id="mfBody" class="mf-body"><div class="empty">Đang tải…</div></div>
      </section>`;
    document.body.appendChild(root);
    const close=()=>{root.classList.add('hidden');document.body.classList.remove('modal-open')};
    root.querySelectorAll('[data-mf-close]').forEach(x=>x.addEventListener('click',close));
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!root.classList.contains('hidden'))close()});
    return root;
  }

  function historyLabel(h){
    const old=(h&&typeof h.old_data==='object'&&h.old_data)||{}, neu=(h&&typeof h.new_data==='object'&&h.new_data)||{};
    if(h.action==='DELETE')return `Đã xóa ledger #${h.ledger_id}`;
    const labels={source_operation_id:'OP nguồn',target_operation_id:'OP đích',good_qty_consumed:'SL tốt',defect_qty_consumed:'SL lỗi',source_qty_kind:'Pool nguồn',origin:'Nguồn gốc'};
    const changes=[];
    Object.keys(labels).forEach(k=>{if(String(old[k]??'')!==String(neu[k]??''))changes.push(`${labels[k]}: ${old[k]??'—'} → ${neu[k]??'—'}`)});
    return changes.join(' · ')||'Cập nhật metadata ledger';
  }

  function relationHtml(r){
    if(!r.enabled)return `<div class="mf-state neutral"><b>Không giới hạn đầu vào bằng Material Flow</b><span>Operation này chưa bật liên kết nguồn. WIP/ưu tiên có thể được ước tính từ OP trước hoặc số lượng PO.</span></div>`;
    if(!r.source_operation_id)return `<div class="mf-state warning"><b>Đã bật Material Flow nhưng chưa chọn OP nguồn</b><span>Hãy mở “Sửa cấu hình” và chọn nguồn đầu vào.</span></div>`;
    const pct=r.source_pool_qty>0?Math.min(100,Math.round(Number(r.source_pool_allocated_qty||0)*100/Number(r.source_pool_qty))):0;
    return `<div class="mf-relation-card"><div class="mf-flow-line"><div><small>NGUỒN</small><b>${E(r.source_code||'—')}</b><span>${E(r.source_name||'')}</span></div><strong>→</strong><div><small>POOL</small><b>${E(kindLabel(r.source_kind))}</b><span>${r.defects_consume_input?'Lỗi của OP đích có tiêu hao đầu vào':'Chỉ hàng đạt tiêu hao đầu vào'}</span></div></div>
      <div class="mf-pool-meter"><i style="width:${pct}%"></i></div>
      <div class="mf-pool-stats"><span><small>Pool tạo ra</small><b>${F(r.source_pool_qty)}</b></span><span><small>Đã cấp toàn bộ</small><b>${F(r.source_pool_allocated_qty)}</b></span><span><small>Còn khả dụng</small><b>${F(r.source_pool_available_qty)}</b></span><span><small>OP này đã nhận</small><b>${F(r.this_operation_consumed_qty)}</b></span></div></div>`;
  }

  function downstreamHtml(rows){
    if(!rows.length)return '<div class="empty compact">Chưa có Operation nào lấy đầu ra của OP này làm nguồn.</div>';
    return `<div class="mf-downstream">${rows.map(x=>`<article><div><small>${E(x.part_code||'')}</small><b>${E(x.code)}</b><span>${E(x.name||'')}</span></div><em>${E(kindLabel(x.input_source_kind))}</em><strong>${F(x.consumed_from_this_source)} SP đã cấp</strong></article>`).join('')}</div>`;
  }

  window.openMaterialFlowTrace=async function(operationId){
    const root=ensureModal(),body=root.querySelector('#mfBody'),title=root.querySelector('#mfTitle'),sub=root.querySelector('#mfSubtitle');
    root.classList.remove('hidden');document.body.classList.add('modal-open');
    title.textContent='Đang tải Dòng vật tư…';sub.textContent='';body.innerHTML='<div class="empty">Đang đọc cấu hình và Ledger…</div>';
    try{
      const d=await window.api(`/api/operations/${Number(operationId)}/material-flow`),op=d.operation||{},r=d.relation||{},s=d.summary||{},items=d.items||[],history=d.history||[],downstream=d.downstream||[];
      title.textContent=`${op.code||''} · ${op.name||''}`;
      sub.textContent=`${op.po_code||''}${op.part_code?' · '+op.part_code:''}${op.part_name?' · '+op.part_name:''}`;
      body.innerHTML=`
        <section class="mf-section"><h3>Luồng đầu vào</h3>${relationHtml(r)}</section>
        <section class="mf-section"><div class="mf-summary">
          <div><small>Đạt tạo ra</small><b>${F(s.produced_qty)}</b></div><div><small>Lỗi sửa được</small><b>${F(s.rework_qty)}</b></div><div><small>Đầu vào đã nhận</small><b>${F(s.consumed_qty)}</b></div><div><small>Đầu ra đã cấp</small><b>${F(s.allocated_qty)}</b></div>
          <div><small>GOOD còn khả dụng</small><b>${F(s.good_available_qty)}</b></div><div><small>REWORK còn khả dụng</small><b>${F(s.rework_available_qty)}</b></div><div><small>Phế</small><b>${F(s.scrap_qty)}</b></div><div><small>Số Ledger</small><b>${F(s.ledger_count)}</b></div>
        </div></section>
        <section class="mf-section"><h3>Operation nhận đầu ra từ OP này</h3>${downstreamHtml(downstream)}</section>
        <section class="mf-section"><div class="mf-section-head"><div><h3>Ledger hiện tại</h3><p>Ledger được tạo khi session của OP đích tiêu thụ đầu vào.</p></div><span>${items.length} dòng</span></div>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>Hướng</th><th>Nguồn</th><th>Đích</th><th>Pool</th><th>Session</th><th>Nhân viên</th><th>SL tốt</th><th>SL lỗi</th><th>Nguồn gốc</th><th>Cập nhật</th></tr></thead><tbody>${items.length?items.map(x=>`<tr><td><span class="badge ${Number(x.source_operation_id)===Number(operationId)?'ok':'muted'}">${Number(x.source_operation_id)===Number(operationId)?'CẤP RA':'NHẬN VÀO'}</span></td><td><b>${E(x.source_code)}</b><br><small>${E(x.source_name)}</small></td><td><b>${E(x.target_code)}</b><br><small>${E(x.target_name)}</small></td><td>${E(kindLabel(x.source_qty_kind))}</td><td>#${x.session_id}<br><small>${E(x.session_status)}</small></td><td>${E(x.employee_no||'')}<br><small>${E(x.employee_name||'')}</small></td><td>${F(x.good_qty_consumed)}</td><td>${F(x.defect_qty_consumed)}</td><td><span class="badge">${E(x.origin||'RUNTIME')}</span></td><td>${DT(x.updated_at)}</td></tr>`).join(''):'<tr><td colspan="10"><div class="empty compact">Chưa phát sinh Ledger cho Operation này.</div></td></tr>'}</tbody></table></div></section>
        <section class="mf-section"><div class="mf-section-head"><div><h3>Lịch sử thay đổi</h3><p>RUNTIME = kiosk/session · BACKFILL = dữ liệu nâng cấp · ADMIN_EDIT = chỉnh session.</p></div><span>${history.length} thay đổi</span></div><div class="mf-history">${history.length?history.map(h=>`<article><b>${E(h.action)}</b><span>${E(historyLabel(h))}</span><small>${DT(h.changed_at)}</small></article>`).join(''):'<div class="empty compact">Ledger chưa từng bị chỉnh sửa hoặc xóa.</div>'}</div></section>`;
    }catch(e){
      title.textContent='Không tải được Dòng vật tư';sub.textContent='';
      body.innerHTML=`<div class="mf-state danger"><b>Không thể đọc Material Flow</b><span>${E(e.message||e)}</span><button class="btn" type="button" onclick="openMaterialFlowTrace(${Number(operationId)})">Thử lại</button></div>`;
    }
  };
})();
