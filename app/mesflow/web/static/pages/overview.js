async function renderOverview(){
  if(typeof dashboardTimer!=='undefined'&&dashboardTimer){clearInterval(dashboardTimer);dashboardTimer=null}
  title.textContent='Tổng quan sản xuất';subtitle.textContent='Sản lượng, tiến độ và kế hoạch xử lý hàng chờ sửa theo Production Order';
  const E=v=>window.esc?window.esc(v??''):String(v??''),N=v=>Number(v||0).toLocaleString('vi-VN');
  const D=v=>v?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',day:'2-digit',month:'2-digit',year:'numeric'}).format(new Date(v)):'—';
  const work=v=>{v=Number(v||0);if(!v)return 'CHƯA CÓ ĐỊNH MỨC SỬA';const h=v/3600;return `${h.toLocaleString('vi-VN',{maximumFractionDigits:1})} GIỜ CÔNG`};
  const stateText=s=>({CRITICAL:'CHẬM',WARNING:'CẦN CHÚ Ý',ON_TRACK:'ĐÚNG TIẾN ĐỘ',WAITING:'CHỜ ĐẦU VÀO',DONE:'HOÀN THÀNH'}[s]||'CHƯA ĐỦ DỮ LIỆU');
  const stateRank=s=>({CRITICAL:0,WARNING:1,WAITING:2,ON_TRACK:3,DONE:4}[s]??9);
  const progress=(value,cls='')=>`<div class="pc-progress ${E(String(cls).toLowerCase())}" aria-label="Tiến độ ${Number(value||0).toFixed(1)}%"><i style="width:${Math.max(0,Math.min(100,Number(value||0)))}%"></i></div>`;
  const poProgressText=x=>{const planned=Number(x.progress_planned_qty||0),actual=Number(x.progress_actual_good_qty||0);return planned>0?`${Math.min(100,Math.max(0,actual/planned*100)).toLocaleString('vi-VN',{maximumFractionDigits:1})}%`:'Chưa có định mức sản lượng'};
  content.innerHTML=`<div class="page-shell">
  ${MFUI.filterBar({content:'<label><span>Tìm nhanh</span><input id="ovSearch" placeholder="Mã PO, Part hoặc Operation"></label><label><span>Production Order</span><select id="ovPoFilter"><option value="">Tất cả PO</option></select></label><label><span>Hàng sửa</span><select id="ovRepair"><option value="">Tất cả</option><option value="defect">Có lỗi</option><option value="pending">Có hàng chờ sửa</option><option value="none">Không có hàng chờ sửa</option></select></label><label><span>Tình trạng</span><select id="ovPriority"><option value="">Tất cả tình trạng</option><option value="CRITICAL">Chậm</option><option value="WARNING">Cần chú ý</option><option value="ON_TRACK">Đúng tiến độ</option><option value="WAITING">Chờ đầu vào</option></select></label><label><span>Sắp xếp</span><select id="ovSort"><option value="priority">Vấn đề trước</option><option value="repair_qty">Chờ sửa nhiều nhất</option><option value="repair_work">Chờ sửa lâu nhất</option><option value="due">PO gần deadline nhất</option><option value="progress">Tiến độ thấp trước</option><option value="po">Theo mã PO</option></select></label>',actions:'<button class="btn" id="ovExpandAll" type="button">Mở tất cả</button><button class="btn" id="ovCollapseAll" type="button">Thu gọn</button><button class="btn" id="ovReload">Làm mới</button>'})}
  <section class="overview-summary" id="ovKpis" aria-live="polite"></section>
  <section id="ovAlerts" aria-live="polite"></section>
  <section class="panel repair-plan" id="ovRepairPlan"></section>
  <section id="ovPos" class="overview-po-list" aria-live="polite"><div class="overview-loading">Đang tổng hợp sản lượng…</div></section>
</div>`;
  let overview={production_orders:[],operations:[]},control={production_orders:[],operations:[]},selectedPo=null;
  const poControl=()=>new Map((control.production_orders||[]).map(x=>[Number(x.po_id),x])),opControl=()=>new Map((control.operations||[]).map(x=>[Number(x.operation_id),x]));
  const mergedPos=()=>{const m=poControl();return (overview.production_orders||[]).map(x=>({...m.get(Number(x.po_id||x.id)),...x}))};
  const mergedOps=()=>{const m=opControl();return (overview.operations||[]).map(x=>({...x,...m.get(Number(x.operation_id))}))};
  const visiblePos=()=>{const q=(document.getElementById('ovSearch').value||'').trim().toLowerCase(),state=document.getElementById('ovPriority').value,repair=document.getElementById('ovRepair').value,ops=mergedOps(),matches=new Set(ops.filter(x=>!q||`${x.po_code} ${x.part_code} ${x.part_name||''} ${x.operation_code} ${x.operation_name}`.toLowerCase().includes(q)).map(x=>Number(x.po_id)));return mergedPos().filter(x=>(!selectedPo||Number(x.po_id)===selectedPo)&&(!state||x.control_state===state)&&(!q||`${x.po_code} ${x.product||''}`.toLowerCase().includes(q)||matches.has(Number(x.po_id)))&&(!repair||(repair==='defect'&&Number(x.defect_quantity)>0)||(repair==='pending'&&Number(x.repair_pending_quantity)>0)||(repair==='none'&&Number(x.repair_pending_quantity)===0)))};
  const fillPoFilter=()=>{const el=document.getElementById('ovPoFilter'),cur=selectedPo!=null?String(selectedPo):el.value;el.innerHTML='<option value="">Tất cả PO</option>'+mergedPos().slice().sort((a,b)=>String(a.po_code).localeCompare(String(b.po_code))).map(x=>`<option value="${x.po_id}">${E(x.po_code)} · ${E(x.product||'')}</option>`).join('');el.value=[...el.options].some(o=>o.value===cur)?cur:''};
  const drawLegacySummary=()=>{const rows=visiblePos(),sum=k=>rows.reduce((a,x)=>a+Number(x[k]||0),0),pending=sum('repair_pending_quantity'),repairPos=rows.filter(x=>Number(x.repair_pending_quantity)>0).length,estimated=sum('estimated_repair_work_seconds'),unconfigured=rows.some(x=>Number(x.repair_unconfigured_operation_count)>0);const values=[['PO đang chạy',rows.length,''],['Kế hoạch',sum('planned_quantity'),'SP'],['Lỗi tổng',sum('defect_quantity'),'SP'],['Phế',sum('scrap_quantity'),'SP']];
    // spec section 5: a session the shift auto-close job closed without any
    // human confirming the final numbers must not read as silently clean --
    // a visible, honest count, never folded into the qty KPIs above (those
    // already count its real 0/0 until someone corrects it).
    const unconfirmed=Number(overview.summary?.unconfirmed_quantity_sessions||0);
    // Progress is an operation-output metric, separate from the existing
    // finished-product/result field (good_quantity).  Aggregate quantities,
    // never average per-PO percentages and never infer finished goods from
    // an operation's completion state.
    const progressPlan=sum('progress_planned_qty'),progressActual=sum('progress_actual_good_qty'),totalProgressCopy=progressPlan>0?`${Math.min(100,Math.max(0,progressActual/progressPlan*100)).toLocaleString('vi-VN',{maximumFractionDigits:1})}%`:'Chưa có định mức sản lượng',missingProgress=rows.some(x=>Number(x.progress_missing_operation_count)>0);
    document.getElementById('ovKpis').innerHTML=values.map(([l,v,u])=>`<article><span>${l}</span><strong>${N(v)}</strong><small>${u}</small></article>`).join('')+`<article><span>Tiến độ sản lượng theo công đoạn</span><strong>${totalProgressCopy}</strong><small>${missingProgress?'Có công đoạn chưa có định mức':''}</small></article>`+`<button class="repair-summary" id="ovRepairOnly"><span>CHỜ SỬA</span><strong>${N(pending)} SP</strong><small>${repairPos} PO · ${unconfigured?'CHƯA ĐỦ ĐỊNH MỨC':work(estimated)}</small></button>`;
    const totalProgressCard=document.querySelector('#ovKpis article:nth-child(7) span');
    // Bug found live (2026-09-02, user-reported UI review): this used to be
    // an 8th item squeezed into .overview-summary's 7-column grid -- it has
    // no column of its own, so it wrapped onto a lone second row at a
    // single narrow 1fr width (same as a plain number KPI cell) with the
    // rest of that row empty, and 3 lines of text (label/count/description)
    // crammed into it with no breathing room. Given its own full-width row
    // instead, styled like every other "N việc cần xử lý" banner in the app
    // (.session-inbox-banner -- Session Management's own inbox banner,
    // same underlying concept) rather than a one-off KPI-grid hack.
    // Same DOM shape as Session Management's own inbox banner (app.js
    // smInboxBanner) -- a plain <div>, not <a>, with an explicit <button>
    // wired up below. Found live: reusing .session-inbox-banner directly
    // on an <a> (the original overview.js pattern) leaks the browser's
    // default link styling (blue + underline) onto the title/description,
    // since that class was only ever designed for a <div> wrapper.
    document.getElementById('ovAlerts').innerHTML=unconfirmed?`<div class="session-inbox-banner"><div><b>${N(unconfirmed)} phiên làm việc · Chờ xác nhận sản lượng</b><span>Tự động kết thúc khi hết ca; cần nhập sản lượng thực tế</span></div><button class="btn primary" id="ovGoUnconfirmed" type="button">Xem ngay</button></div>`:'';
    const goUnconfirmed=document.getElementById('ovGoUnconfirmed');
    if(goUnconfirmed)goUnconfirmed.onclick=()=>openPage('session-exceptions',document.querySelector('[data-page="session-exceptions"]'));};
  // Production Overview hotfix (2026-09-26): who is running each Operation
  // RIGHT NOW, from the backend's active_worker_list (OPEN sessions only --
  // never the day rollup), so management no longer has to switch to
  // Dashboard theo ngày. Nothing is rendered when nobody is on it, so idle
  // rows keep their exact previous shape. At most 3 chips, the rest fold
  // into a +N chip whose tooltip names them.
  const T=v=>v?new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(v)):'';
  const workerTip=w=>[w.name,w.employee_no,w.setup?'Chuẩn bị máy':'',w.started_at?`từ ${T(w.started_at)}`:'',(w.station_codes||[]).join(', '),Number(w.session_count)>1?`${w.session_count} phiên đang mở`:''].filter(Boolean).join(' · ');
  const activeWorkers=x=>{const list=Array.isArray(x.active_worker_list)?x.active_worker_list:[];if(!list.length)return '';const shown=list.slice(0,3),rest=list.slice(3);return `<div class="overview-op-workers" aria-label="${list.length} người đang làm"><em>Đang làm</em>${shown.map(w=>`<span class="ov-worker${w.setup?' setup':''}" title="${E(workerTip(w))}"><i></i><b>${E(w.name||w.employee_no||'—')}</b>${w.employee_no?`<small>${E(w.employee_no)}</small>`:''}${w.setup?'<small class="ov-worker-tag">Chuẩn bị</small>':''}${Number(w.session_count)>1?`<small class="ov-worker-tag">×${Number(w.session_count)}</small>`:''}</span>`).join('')}${rest.length?`<span class="ov-worker more" title="${E(rest.map(workerTip).join('\n'))}"><b>+${rest.length}</b></span>`:''}</div>`};
  const operationRows=poId=>mergedOps().filter(x=>Number(x.po_id)===Number(poId)).sort((a,b)=>Number(a.part_id)-Number(b.part_id)||Number(a.operation_sort)-Number(b.operation_sort)).map(x=>`<div class="overview-op-row ${Number(x.repair_pending_quantity)>0?'has-repair':''}" data-repair-op="${x.operation_id}" data-op-detail="${x.operation_id}" tabindex="0" role="button" aria-label="Mở chi tiết Operation ${E(x.operation_code)}" title="Nhấp đúp để xem người đã làm và năng suất"><span><b class="row-title">${E(x.operation_name)}</b><small class="row-code">${E(x.operation_code)}</small><small>${E(x.part_code)} ${E(x.part_name||'')}</small></span><span><b>${Number(x.progress_percent||0).toFixed(1)}%</b>${progress(x.progress_percent,x.control_state)}</span><span><small>Đạt</small><b>${N(x.done_qty)}</b></span><span><small>Lỗi</small><b>${N(x.defect_qty)}</b></span><span><small>Chờ sửa</small><b>${N(x.repair_pending_quantity)}</b><small>${Number(x.repair_pending_quantity)>0?work(x.estimated_repair_work_seconds):'—'}</small></span><span><button class="btn mini" data-open-op="${x.operation_id}" type="button">Mở OP</button></span>${activeWorkers(x)}</div>`).join('');
  const showOperationDetail=async(operationId,opts={})=>{
    const source=mergedOps().find(x=>Number(x.operation_id)===Number(operationId))||{};
    const old=document.querySelector('.op-detail-backdrop');if(old)old.remove();
    const backdrop=document.createElement('div');backdrop.className='modal-backdrop op-detail-backdrop';
    backdrop.innerHTML=`<div class="modal op-detail-modal" role="dialog" aria-modal="true" aria-labelledby="opDetailTitle"><div class="op-detail-head"><div><small>Operation Detail</small><h2 id="opDetailTitle">${E(source.operation_code||'Operation')} · ${E(source.operation_name||'')}</h2><p>${E(source.po_code||'')} · ${E(source.part_code||'')} ${E(source.part_name||'')}</p></div><button class="btn" type="button" data-op-detail-close>Đóng</button></div><div class="op-detail-loading">Đang tải người thực hiện và năng suất…</div></div>`;
    document.body.appendChild(backdrop);
    const modal=backdrop.querySelector('.op-detail-modal');
    const close=()=>{document.removeEventListener('keydown',onKey);backdrop.remove()};
    const onKey=e=>{if(e.key==='Escape')close()};
    document.addEventListener('keydown',onKey);
    backdrop.addEventListener('click',e=>{if(e.target===backdrop)close()});
    backdrop.querySelector('[data-op-detail-close]').onclick=close;
    backdrop.querySelector('[data-op-detail-close]').focus();
    const score=(standard,s)=>{
      const actual=Number(s.duration_seconds||0),qty=Number(s.good_qty||0)+Number(s.defect_qty||0),closed=String(s.status||'').toUpperCase()==='CLOSED';
      if(!closed||s.excluded_from_reports||standard<=0||actual<=0||qty<=0)return null;
      return standard*qty/actual*100;
    };
    const speed=pct=>pct==null?{text:'Chưa đủ dữ liệu',cls:'na'}:pct>100?{text:'Nhanh hơn định mức',cls:'fast'}:pct<100?{text:'Chậm hơn định mức',cls:'slow'}:{text:'Đúng định mức',cls:'target'};
    const when=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(d.getTime())?'—':d.toLocaleString('vi-VN',{hour12:false})};
    const role=String(window.MESFLOW_USER?.role||'').toLowerCase(),canAdjustSessionQty=role==='admin'||role==='super_admin';
    const quantityConfirmed=v=>v===true||v===1||String(v||'').toLowerCase()==='true';
    const needsQuantityReview=s=>String(s.status||'').toUpperCase()==='CLOSED'&&Number(s.good_qty||0)===0&&Number(s.defect_qty||0)===0&&!quantityConfirmed(s.quantity_confirmed);
    // Bổ sung phiên (manual supplement): same session.edit boundary as the
    // /api/supervisor/sessions/* endpoints -- admin/manager/supervisor, never
    // operator/kiosk. The server enforces it again; this only hides the UI.
    const canManualSession=typeof hasPermission==='function'?hasPermission('session.edit'):['admin','super_admin','manager','supervisor'].includes(role);
    const isManual=s=>String(s.close_reason||'').toUpperCase()==='MANUAL_SUPPLEMENT';
    const hm=sec=>{sec=Math.max(0,Math.round(Number(sec)||0));const h=Math.floor(sec/3600),m=Math.floor(sec%3600/60);return h?`${h} giờ ${String(m).padStart(2,'0')} phút`:`${m} phút`};
    const localNow=()=>{const d=new Date();d.setSeconds(0,0);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16)};
    let manualEmployees=null;
    const loadManualEmployees=async()=>{if(manualEmployees)return manualEmployees;const d=await api('/api/employees?limit=1000');manualEmployees=(d.items||[]).filter(x=>x.active!==false).sort((a,b)=>String(a.employee_no||'').localeCompare(String(b.employee_no||'')));return manualEmployees};
    const bindManualForm=()=>{
      const form=modal.querySelector('[data-manual-session-form]');if(!form)return;
      const errorBox=form.querySelector('[data-manual-error]'),submit=form.querySelector('[data-manual-session-submit]');
      const showError=msg=>{errorBox.textContent=msg||'';errorBox.hidden=!msg};
      // Live preview: same score()/speed() and copy as the session list.
      const preview=()=>{
        const st=form.started_at.value,en=form.ended_at.value,sec=st&&en?(new Date(en)-new Date(st))/1000:NaN;
        const clock=v=>v.slice(11,16),day=v=>`${v.slice(8,10)}/${v.slice(5,7)}`,range=Number.isFinite(sec)?` · ${day(st)} ${clock(st)} → ${day(en)===day(st)?'':`${day(en)} `}${clock(en)}`:'';
        form.querySelector('[data-manual-duration]').textContent=Number.isFinite(sec)?(sec>0?`${hm(sec)}${range}`:'Kết thúc phải sau bắt đầu'):'—';
        const standard=Number(modal.dataset.standard||0),pct=Number.isFinite(sec)&&sec>0?score(standard,{status:'CLOSED',duration_seconds:sec,good_qty:form.good_qty.value,defect_qty:form.defect_qty.value}):null,sp=speed(pct),out=form.querySelector('[data-manual-score]');
        out.textContent=pct==null?(standard>0?'—':'Chưa cấu hình định mức'):`${pct.toFixed(1)}% · ${sp.text}`;out.className=`op-speed ${pct==null?'na':sp.cls}`;
      };
      form.oninput=()=>{preview();if(!errorBox.hidden)showError('')};
      const open=async employeeId=>{
        form.hidden=false;showError('');
        // One idempotency key per opened form: a double click or a retry after
        // a lost response replays the first create instead of making two rows.
        form.dataset.requestId=`op-detail-manual-${operationId}-${Date.now()}-${Math.random().toString(36).slice(2,10)}`;
        const max=localNow();form.started_at.max=max;form.ended_at.max=max;
        form.scrollIntoView({block:'nearest'});
        const select=form.employee_id;
        try{
          const list=await loadManualEmployees();
          select.innerHTML='<option value="">Chọn nhân viên</option>'+list.map(x=>`<option value="${Number(x.id)}">${E(x.employee_no||'')} · ${E(x.name||'')}</option>`).join('');
        }catch(err){select.innerHTML='<option value="">Không tải được danh sách nhân viên</option>';showError(err.message||String(err))}
        if(employeeId)select.value=String(employeeId);
        (employeeId?form.started_at:select).focus();
        preview();
      };
      modal.querySelector('[data-manual-session-open]')?.addEventListener('click',()=>open(null));
      modal.querySelectorAll('[data-manual-session-employee]').forEach(b=>b.addEventListener('click',e=>{e.stopPropagation();open(Number(b.dataset.manualSessionEmployee))}));
      form.querySelector('[data-manual-session-cancel]').onclick=()=>{form.hidden=true;form.reset();showError('')};
      form.onsubmit=async e=>{
        e.preventDefault();
        if(form.dataset.saving==='1')return;
        const employeeId=Number(form.employee_id.value),st=form.started_at.value,en=form.ended_at.value,good=Number(form.good_qty.value),defect=Number(form.defect_qty.value),reason=String(form.reason.value||'').trim(),note=String(form.note.value||'').trim();
        if(!employeeId)return showError('Hãy chọn nhân viên.');
        if(!st||!en)return showError('Hãy nhập giờ bắt đầu và giờ kết thúc.');
        if(new Date(en)<=new Date(st))return showError('Giờ kết thúc phải sau giờ bắt đầu.');
        if(new Date(en)>new Date())return showError('Giờ kết thúc không được ở tương lai.');
        if(form.good_qty.value===''||form.defect_qty.value===''||!Number.isInteger(good)||!Number.isInteger(defect)||good<0||defect<0)return showError('Sản lượng phải là số nguyên không âm.');
        if(!reason)return showError('Hãy nhập lý do bổ sung.');
        form.dataset.saving='1';submit.disabled=true;submit.textContent='Đang lưu…';
        try{
          // datetime-local is sent as-is: the server reads it in the factory timezone.
          const res=await api('/api/supervisor/sessions/manual',{method:'POST',body:JSON.stringify({operation_id:Number(operationId),employee_id:employeeId,started_at:st,ended_at:en,good_qty:good,defect_qty:defect,reason,note,request_id:form.dataset.requestId})});
          const created=res.session||{};
          toast(`Đã bổ sung phiên #${created.id||''} · ${N(good)} đạt · ${N(defect)} lỗi`);
          await reloadDetail(created.id);
          if(typeof load==='function')load();
        }catch(err){showError(err.message||String(err));form.dataset.saving='';submit.disabled=false;submit.textContent='Lưu phiên bổ sung'}
      };
    };
    const reloadDetail=async(highlightId)=>{
    try{
      const [detailRes,sessionsRes]=await Promise.all([
        api(`/api/reports/operations/${operationId}`),
        api(`/api/reports/operation-sessions?operation_id=${operationId}&limit=3000`)
      ]);
      const op=detailRes.report?.operation||source,report=sessionsRes.report||{},sessions=Array.isArray(report.sessions)?report.sessions:[];
      const standard=Number(op.standard_seconds_per_unit||source.standard_seconds_per_unit||0);
      modal.dataset.standard=String(standard);
      const people=new Map();
      sessions.forEach(s=>{
        const key=String(s.employee_id||s.employee_code||s.employee_name||'unknown');
        if(!people.has(key))people.set(key,{employee_id:s.employee_id,code:s.employee_code||'',name:s.employee_name||'Không rõ',sessions:0,open:0,good:0,defect:0,worked:0,scores:[]});
        const p=people.get(key);p.sessions+=1;p.open+=String(s.status||'').toUpperCase()==='OPEN'?1:0;p.good+=Number(s.good_qty||0);p.defect+=Number(s.defect_qty||0);p.worked+=Number(s.duration_seconds||0);
        const sc=score(standard,s);if(sc!=null)p.scores.push(sc);
      });
      const employees=[...people.values()].map(p=>({...p,productivity:p.scores.length?p.scores.reduce((a,b)=>a+b,0)/p.scores.length:null})).sort((a,b)=>(a.productivity==null)-(b.productivity==null)||(b.productivity||0)-(a.productivity||0)||String(a.code).localeCompare(String(b.code)));
      const totalGood=sessions.reduce((a,x)=>a+Number(x.good_qty||0),0),totalDefect=sessions.reduce((a,x)=>a+Number(x.defect_qty||0),0);
      const employeeRows=employees.length?employees.map(p=>{const st=speed(p.productivity);return `<div class="op-detail-user-row"><span><b>${E(p.name)}</b><small>${E(p.code)}${p.open?` · ${p.open} đang làm`:''}</small></span><span><b>${N(p.sessions)}</b><small>phiên làm việc</small></span><span><b>${N(p.good)}</b><small>Đạt · ${N(p.defect)} lỗi</small></span><span><b>${work(p.worked)}</b><small>thời gian thực tế</small></span><span><b>${p.productivity==null?'—':`${p.productivity.toFixed(1)}%`}</b><small class="op-speed ${st.cls}">${st.text}</small></span>${canManualSession?`<span class="op-manual-cell">${p.employee_id?`<button class="btn mini op-manual-add" type="button" data-manual-session-employee="${Number(p.employee_id)}" title="Bổ sung phiên cho ${E(p.name)}" aria-label="Bổ sung phiên cho ${E(p.name)}">+ Phiên</button>`:''}</span>`:''}</div>`}).join(''):'<div class="op-detail-empty">Chưa có nhân viên nào làm Operation này.</div>';
      const visibleSessions=sessions.slice(0,30);
      if(highlightId&&!visibleSessions.some(s=>Number(s.session_id)===Number(highlightId))){const created=sessions.find(s=>Number(s.session_id)===Number(highlightId));if(created)visibleSessions.push(created)}
      const needsQtyCount=visibleSessions.filter(needsQuantityReview).length;
      const sessionRows=visibleSessions.map(s=>{
        const sc=score(standard,s),st=speed(sc),needsQty=needsQuantityReview(s),manual=isManual(s),adjusted=Number(s.adjustment_count||0)>(manual?1:0),closed=String(s.status||'').toUpperCase()==='CLOSED';
        const flags=`${manual?'<small class="op-session-flag manual">Bổ sung tay</small>':''}${needsQty?'<small class="op-session-flag needs-qty">0/0 · Chưa xác nhận sản lượng</small>':''}${adjusted?`<small class="op-session-flag adjusted">Đã điều chỉnh${s.last_adjusted_at?` · ${when(s.last_adjusted_at)}`:''}</small>`:''}`;
        const action=canAdjustSessionQty&&closed?`<button class="btn mini ${needsQty?'primary':''}" type="button" data-edit-session-qty="${s.session_id}">${needsQty?'Bổ sung SL':'Sửa SL'}</button>`:'<span class="op-session-no-action" aria-hidden="true">—</span>';
        const editor=canAdjustSessionQty&&closed?`<form class="op-session-qty-editor" data-session-qty-form="${s.session_id}" hidden><div class="op-session-edit-title"><b>Chỉnh sản lượng phiên #${s.session_id}</b><span>Lưu qua cơ chế SESSION_ADJUST · có audit</span></div><div class="op-session-edit-fields"><label>Đạt<input name="good_qty" type="number" min="0" step="1" value="${Number(s.good_qty||0)}" required></label><label>Lỗi<input name="defect_qty" type="number" min="0" step="1" value="${Number(s.defect_qty||0)}" required></label><label>Trong đó sửa lại<input name="rework_qty" type="number" min="0" step="1" value="${Number(s.rework_qty||0)}" required></label><label class="reason">Ghi chú / lý do <small>(không bắt buộc)</small><input name="reason" type="text" maxlength="500" placeholder="Để trống để hệ thống tự ghi lý do"></label></div><div class="op-session-edit-actions"><button class="btn" type="button" data-session-edit-cancel>Hủy</button><button class="btn primary" type="submit">Lưu sản lượng</button></div></form>`:'';
        return `<div class="op-detail-session-item${needsQty?' needs-quantity':''}${adjusted?' was-adjusted':''}${Number(highlightId)===Number(s.session_id)?' is-new':''}" data-session-item="${s.session_id}"><div class="op-detail-session-row"><span class="op-session-cell employee"><b>${E(s.employee_name||'Không rõ')}</b><small>${E(s.employee_code||'')}</small>${flags}</span><span class="op-session-cell period"><b>${when(s.started_at)}</b><small>${String(s.status||'').toUpperCase()==='OPEN'?'Đang làm':when(s.ended_at)}</small></span><span class="op-session-cell quantity"><b>${N(Number(s.good_qty||0)+Number(s.defect_qty||0))} SP</b><small>${N(s.good_qty)} đạt · ${N(s.defect_qty)} lỗi${Number(s.rework_qty||0)>0?` · ${N(s.rework_qty)} sửa`:''}</small></span><span class="op-session-cell duration"><b>${work(s.duration_seconds)}</b><small>${sc==null?'—':`${sc.toFixed(1)}%`}</small></span><span class="op-session-cell benchmark"><small class="op-speed ${st.cls}">${st.text}</small>${s.excluded_from_reports?'<small class="op-excluded">Loại khỏi báo cáo</small>':''}</span><span class="op-session-actions">${action}</span></div>${editor}</div>`}).join('');
      const manualForm=`<form class="op-manual-form" data-manual-session-form hidden novalidate><div class="op-manual-title"><b>Bổ sung phiên làm việc</b><span>Cho trường hợp quên quét QR bắt đầu/kết thúc · tạo phiên CLOSED thật · có audit</span></div><div class="op-manual-fields"><label class="wide"><span>Nhân viên <b>*</b></span><select name="employee_id" required><option value="">Đang tải danh sách…</option></select></label><label><span>Bắt đầu <b>*</b></span><input name="started_at" type="datetime-local" step="60" required></label><label><span>Kết thúc <b>*</b></span><input name="ended_at" type="datetime-local" step="60" required></label><label><span>Sản lượng Đạt</span><input name="good_qty" type="number" min="0" step="1" inputmode="numeric" value="0" required></label><label><span>Lỗi</span><input name="defect_qty" type="number" min="0" step="1" inputmode="numeric" value="0" required></label><div class="op-manual-preview"><small>Thời gian</small><output name="duration_preview" data-manual-duration>—</output></div><div class="op-manual-preview"><small>So định mức</small><output name="score_preview" data-manual-score>—</output></div><label class="wide"><span>Lý do bổ sung <b>*</b></span><input name="reason" type="text" maxlength="500" required placeholder="Ví dụ: công nhân quên quét QR kết thúc"></label><label class="wide"><span>Ghi chú <small>(không bắt buộc)</small></span><input name="note" type="text" maxlength="500"></label></div><div class="op-manual-error" data-manual-error role="alert" hidden></div><div class="op-manual-actions"><button class="btn" type="button" data-manual-session-cancel>Hủy</button><button class="btn primary" type="submit" data-manual-session-submit>Lưu phiên bổ sung</button></div></form>`;
      modal.innerHTML=`<div class="op-detail-head"><div><small>Operation Detail · Nhấp đúp từ Tổng quan</small><h2 id="opDetailTitle">${E(op.code||source.operation_code||'')} · ${E(op.name||source.operation_name||'')}</h2><p>${E(op.po_code||source.po_code||'')} · ${E(op.part_code||source.part_code||'')} ${E(op.part_name||source.part_name||'')}</p></div><button class="btn" type="button" data-op-detail-close>Đóng</button></div><div class="op-detail-kpis"><div><small>Nhân viên đã làm</small><b>${N(employees.length)}</b></div><div><small>Phiên làm việc</small><b>${N(sessions.length)}</b></div><div><small>Đạt / Lỗi</small><b>${N(totalGood)} / ${N(totalDefect)}</b></div><div><small>Định mức</small><b>${standard>0?`${N(standard)} giây/SP`:'Chưa cấu hình'}</b></div></div><div class="op-detail-note">Năng suất dùng cùng công thức báo cáo hiện tại: <b>định mức × (Đạt + Lỗi) ÷ thời gian thực tế × 100%</b>. Trên 100% = nhanh hơn định mức; dưới 100% = chậm hơn định mức.</div><section class="op-detail-section${canManualSession?' has-manual':''}"><div class="op-detail-section-head"><div><h3>Ai đã làm Operation này</h3><span>Sắp theo năng suất từ cao xuống thấp</span></div>${canManualSession?'<button class="btn mini" type="button" data-manual-session-open>+ Bổ sung phiên</button>':''}</div>${canManualSession?manualForm:''}<div class="op-detail-user-head"><span>Nhân viên</span><span>Phiên</span><span>Sản lượng</span><span>Thời gian</span><span>Năng suất</span>${canManualSession?'<span>Bổ sung</span>':''}</div>${employeeRows}</section><section class="op-detail-section"><div class="op-detail-section-head"><h3>Phiên gần nhất</h3><span class="${needsQtyCount?'op-detail-attention':''}">${needsQtyCount?`⚠ ${needsQtyCount} phiên 0/0 cần bổ sung sản lượng`:'Tối đa 30 phiên'}</span></div><div class="op-detail-session-head"><span>Nhân viên</span><span>Bắt đầu / kết thúc</span><span>Sản lượng</span><span>Thời gian</span><span>So định mức</span><span>Thao tác</span></div>${sessionRows||'<div class="op-detail-empty">Chưa có phiên làm việc.</div>'}</section>`;
      modal.querySelector('[data-op-detail-close]').onclick=close;
      if(canManualSession)bindManualForm();
      if(highlightId){const row=modal.querySelector(`[data-session-item="${Number(highlightId)}"]`);if(row)row.scrollIntoView({block:'nearest'})}
      // Delegated once per modal: reloadDetail() re-renders innerHTML in place.
      if(!modal.dataset.delegated){modal.dataset.delegated='1';
      modal.addEventListener('click',e=>{
        const editBtn=e.target.closest('[data-edit-session-qty]');
        if(editBtn&&modal.contains(editBtn)){
          e.preventDefault();e.stopPropagation();
          const item=editBtn.closest('[data-session-item]'),form=item?.querySelector('[data-session-qty-form]');if(!form)return;
          modal.querySelectorAll('[data-session-qty-form]').forEach(other=>{if(other!==form)other.hidden=true});
          form.hidden=!form.hidden;
          if(!form.hidden)form.querySelector('input[name="good_qty"]')?.focus();
          return;
        }
        const cancelBtn=e.target.closest('[data-session-edit-cancel]');
        if(cancelBtn&&modal.contains(cancelBtn)){
          e.preventDefault();e.stopPropagation();
          const form=cancelBtn.closest('[data-session-qty-form]');if(form)form.hidden=true;
        }
      });}
      modal.querySelectorAll('[data-session-qty-form]').forEach(form=>form.onsubmit=async e=>{
        e.preventDefault();
        const sessionId=Number(form.dataset.sessionQtyForm),good=Number(form.good_qty.value),defect=Number(form.defect_qty.value),rework=Number(form.rework_qty.value),typedReason=String(form.reason.value||'').trim(),defaultReason=form.closest('[data-session-item]')?.classList.contains('needs-quantity')?'Bổ sung sản lượng phiên 0/0 từ OP Detail':'Điều chỉnh sản lượng từ OP Detail',reason=typedReason||defaultReason;
        if(!Number.isInteger(good)||!Number.isInteger(defect)||!Number.isInteger(rework)||good<0||defect<0||rework<0)return alert('Sản lượng phải là số nguyên không âm.');
        if(rework>defect)return alert('Số lượng sửa lại không được lớn hơn số lượng lỗi.');
        const submit=form.querySelector('button[type="submit"]');submit.disabled=true;submit.textContent='Đang lưu…';
        try{
          await api(`/api/supervisor/sessions/${sessionId}/adjust`,{method:'POST',body:JSON.stringify({good_qty:good,defect_qty:defect,rework_qty:rework,reason,request_id:`op-detail-adjust-${sessionId}-${Date.now()}`})});
          toast('Đã điều chỉnh sản lượng · phiên bất thường đã được xác nhận');
          close();
          await showOperationDetail(operationId);
        }catch(err){alert(err.message||err);submit.disabled=false;submit.textContent='Lưu sản lượng'}
      });
      modal.querySelector('[data-op-detail-close]').focus();
    }catch(err){
      modal.innerHTML=`<div class="op-detail-head"><div><small>Operation Detail</small><h2 id="opDetailTitle">${E(source.operation_code||'Operation')}</h2></div><button class="btn" type="button" data-op-detail-close>Đóng</button></div><div class="op-detail-error">Không tải được chi tiết Operation: ${E(err.message||err)}</div>`;
      modal.querySelector('[data-op-detail-close]').onclick=close;
    }
    };
    await reloadDetail(opts.highlightSessionId);
  };
  const drawSummary=()=>{const rows=visiblePos();const poRows=rows.map(x=>{const missing=Number(x.progress_missing_operation_count||0),defect=Number(x.defect_quantity||0),scrap=Number(x.scrap_quantity||0),repair=Number(x.repair_pending_quantity||0);return `<article class="overview-compact-po" data-compact-po="${x.po_id}"><div class="compact-po-code"><b>${E(x.po_code)}</b><small>${E(x.product||'')}</small></div><span class="compact-plan">${N(x.planned_quantity)} SP</span><strong class="compact-progress">${poProgressText(x)}</strong><span class="compact-warning">${missing?`Có ${missing} công đoạn chưa có định mức`:''}</span><span class="compact-repair">${N(repair)} SP</span><small class="compact-due">${D(x.due_date)}</small></article>`}).join('');document.getElementById('ovKpis').innerHTML=rows.length?`<div class="overview-compact-head"><span>PO</span><span>Kế hoạch</span><span>Tiến độ theo công đoạn</span><span>Cảnh báo</span><span>Chờ sửa</span><span>Hạn</span></div>${poRows}`:'<div class="overview-empty compact">Không có PO phù hợp</div>';};
  const drawPlan=()=>{const rows=mergedOps().filter(x=>Number(x.repair_pending_quantity)>0).sort((a,b)=>Number(b.estimated_repair_work_seconds)-Number(a.estimated_repair_work_seconds)||Number(b.repair_pending_quantity)-Number(a.repair_pending_quantity));document.getElementById('ovRepairPlan').innerHTML=`<div class="panel-head"><div><h2>Kế hoạch sửa</h2><p>Nguồn phát sinh được giữ theo PO, Part và Operation. Chưa theo dõi bắt đầu/hoàn tất sửa trong Phase 1.</p></div><b>${N(rows.reduce((n,x)=>n+Number(x.repair_pending_quantity),0))} SP chờ sửa</b></div>${rows.length?`<div class="repair-plan-table"><div class="head"><span>PO / Part</span><span>Operation</span><span>Chờ sửa</span><span>Giờ công</span><span>Deadline</span></div>${rows.slice(0,20).map(x=>`<button data-plan-po="${x.po_id}" data-plan-op="${x.operation_id}"><span><b>${E(x.po_code)}</b><small>${E(x.part_code)} · ${E(x.part_name||'')}</small></span><span><b>${E(x.operation_code)}</b><small>${E(x.operation_name)}</small></span><strong>${N(x.repair_pending_quantity)} SP</strong><span>${work(x.estimated_repair_work_seconds)}</span><span>${D(x.due_date)}</span></button>`).join('')}</div>`:'<div class="overview-empty compact"><strong>Không có hàng chờ sửa</strong></div>'}`};
  const drawPos=()=>{const sort=document.getElementById('ovSort').value,rows=visiblePos();rows.sort((a,b)=>sort==='repair_qty'?Number(b.repair_pending_quantity)-Number(a.repair_pending_quantity):sort==='repair_work'?Number(b.estimated_repair_work_seconds)-Number(a.estimated_repair_work_seconds):sort==='due'?String(a.due_date||'9999').localeCompare(String(b.due_date||'9999')):sort==='progress'?Number(a.progress_percent)-Number(b.progress_percent):sort==='po'?String(a.po_code).localeCompare(String(b.po_code)):stateRank(a.control_state)-stateRank(b.control_state)||Number(b.priority_score||0)-Number(a.priority_score||0));let ovAutoOpen=0;document.getElementById('ovPos').innerHTML=rows.length?rows.map(x=>{
    // Progressive disclosure (REQ-UI-019): mở sẵn TỐI ĐA một PO -- PO đang được
    // lọc, nếu không thì PO cần chú ý nhất (danh sách đã sort theo mức độ).
    // Đo được với 8 PO x 80 OP: mở hết = 10.5 viewport ở 390.
    const selected=String(document.getElementById('ovPoFilter')?.value||'')===String(x.po_id);
    let isOpen=false;
    if(selected)isOpen=true;else if(ovAutoOpen<1){isOpen=true;ovAutoOpen++}
    return `<details class="overview-po ${E(String(x.control_state||'').toLowerCase())}" data-po-section="${x.po_id}"${isOpen?' open':''}><summary class="overview-po-sticky"><div><h2>${E(x.po_code)} <small>${E(x.product||'')}</small></h2><span>Hạn ${D(x.due_date)}</span></div><div class="overview-po-progress"><strong>${poProgressText(x)}</strong>${progress(x.progress_percent,x.control_state)}</div><div class="overview-po-actions"><em class="pc-state ${E(String(x.control_state||'').toLowerCase())}"><i></i>${E(stateText(x.control_state))}</em><button class="btn mini overview-po-open" data-open-po="${x.po_id}" type="button">Mở PO</button></div></summary><div class="overview-po-main"><div class="overview-po-metrics"><span><small>Lỗi tổng</small><b>${N(x.defect_quantity)}</b></span><span><small>Phế</small><b>${N(x.scrap_quantity)}</b></span></div>${Number(x.repair_pending_quantity)>0?`<button class="po-repair-callout" data-po-repair="${x.po_id}"><span>CẦN SỬA</span><strong>${N(x.repair_pending_quantity)} SP</strong><small>${Number(x.repair_unconfigured_operation_count)>0?'CHƯA CÓ ĐỊNH MỨC SỬA':work(x.estimated_repair_work_seconds)}</small></button>`:'<div class="po-repair-none">Không có hàng chờ sửa</div>'}</div><div class="overview-op-head"><span>Operation</span><span>Tiến độ</span><span>Đạt</span><span>Lỗi</span><span>Chờ sửa</span><span></span></div><div class="overview-op-list">${operationRows(x.po_id)}</div></details>`}).join(''):'<div class="overview-empty"><strong>Không có Production Order phù hợp</strong></div>';document.querySelectorAll('[data-open-po]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();window.openProductionOrder(Number(b.dataset.openPo))});document.querySelectorAll('[data-open-op]').forEach(b=>b.onclick=e=>{e.preventDefault();e.stopPropagation();showOperationDetail(Number(b.dataset.openOp))});document.querySelectorAll('[data-po-repair]').forEach(b=>b.onclick=()=>{const po=b.closest('.overview-po');if(po&&'open'in po)po.open=true;po.querySelector('.overview-op-list').scrollIntoView({behavior:'smooth',block:'start'});po.classList.add('repair-focus');setTimeout(()=>po.classList.remove('repair-focus'),1800)});document.querySelectorAll('[data-op-detail]').forEach(row=>{row.onclick=e=>{if(!e.target.closest('button,a,input,select'))row.focus({preventScroll:true})};row.ondblclick=e=>{if(e.target.closest('button,a,input,select'))return;showOperationDetail(Number(row.dataset.opDetail))};row.onkeydown=e=>{if((e.key==='Enter'||e.key===' ')&&!e.target.closest('button,a,input,select')){e.preventDefault();showOperationDetail(Number(row.dataset.opDetail))}}});};
  const annotatePoCards=()=>{const pos=new Map(mergedPos().map(x=>[String(x.po_id),x]));document.querySelectorAll('#ovPos [data-po-section]').forEach(card=>{const x=pos.get(String(card.dataset.poSection));if(!x)return;const missing=Number(x.progress_missing_operation_count||0),meta=`Tiến độ sản lượng theo công đoạn: ${poProgressText(x)}`;let el=card.querySelector('.overview-po-progress-meta');if(!el){el=document.createElement('small');el.className='overview-po-progress-meta';card.querySelector('.overview-po-sticky>div:first-child')?.append(el)}el.textContent=missing?`${meta} · Có công đoạn chưa có định mức`:meta})};
  const draw=()=>{fillPoFilter();drawSummary();drawPlan();drawPos();annotatePoCards();document.querySelectorAll('[data-plan-po]').forEach(b=>b.onclick=()=>{selectedPo=Number(b.dataset.planPo);draw();setTimeout(()=>document.querySelector(`[data-repair-op="${b.dataset.planOp}"]`)?.scrollIntoView({behavior:'smooth',block:'center'}),20)})};
  let loaded=false;
  const load=async()=>{try{[overview,control]=await Promise.all([api('/api/dashboard/overview?limit=5000'),api('/api/production-control?limit=2000')]);if(document.getElementById('ovPos'))draw();loaded=true}catch(e){MFUI.refreshError({loaded,host:document.getElementById('ovPos'),error:e,retry:load,screen:'Tổng quan'})}};
  const ovSetAll=open=>document.querySelectorAll('#ovPos details.overview-po').forEach(d=>{d.open=open});
  document.getElementById('ovExpandAll').onclick=()=>ovSetAll(true);
  document.getElementById('ovCollapseAll').onclick=()=>ovSetAll(false);
  ['ovSearch','ovRepair','ovPriority','ovSort'].forEach(id=>document.getElementById(id).addEventListener(id==='ovSearch'?'input':'change',draw));document.getElementById('ovPoFilter').addEventListener('change',e=>{selectedPo=e.target.value?Number(e.target.value):null;draw()});document.getElementById('ovReload').onclick=load;await load();dashboardTimer=setInterval(()=>{const userViewing=document.visibilityState==='visible'&&document.hasFocus();if(document.getElementById('ovPos')&&userViewing===false)load()},60000);
}
