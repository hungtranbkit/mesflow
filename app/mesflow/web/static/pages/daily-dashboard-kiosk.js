// Kiosk điều hành (control-room display) -- the big-screen companion to
// "Dashboard theo ngày".
//
// SEMANTICS, because "kiosk" is an overloaded word in this codebase:
//   * kiosk.py / kiosk_v2.py / templates/kiosk.html  -> the SHOP-FLOOR device
//     an operator scans a QR badge on. Device runtime, touch input, writes.
//   * THIS file -> a passive CONTROL-ROOM DISPLAY for a TV on the wall of the
//     production office. Read-only, no input, no device identity, nothing to
//     scan. It never talks to any kiosk-device endpoint.
// Keeping the two apart matters: an admin opening "Mở màn hình lớn" must never
// land on anything that looks like a badge-scan terminal.
//
// DATA SOURCES -- all three already exist and are already used by shipped
// pages; this view adds no endpoint and re-derives no business rule:
//   /api/dashboard/day?date=   -> the authoritative CALENDAR-DAY rollup
//                                 (context/items/sessions/activity). Exactly
//                                 what renderDashboard() reads.
//   /api/dashboard/overview    -> PO-level plan/remaining/repair backlog.
//   /api/production-control    -> the dispatch engine's OWN control_state /
//                                 control_label / recommended_action. The
//                                 "dưới kế hoạch / làm ngay" judgement is read
//                                 from here, never recomputed locally.
// The last two are the same pair renderOverview() already fetches together.
(()=>{
  const PAGE_ID='daily-dashboard-kiosk';
  const REFRESH_MS=20000;            // inside the 15-30s window asked for
  // A transparent, clearly-labelled threshold -- NOT a fabricated "NG cao"
  // rule pretending to come from the backend. The row always shows the real
  // ratio next to it so a quản đốc can see why it was flagged.
  const NG_RATIO_ALERT=0.10;
  // "Session mở quá lâu": same shape as the daily dashboard's own
  // "Session mở quá cuối ca" marker -- an OPEN session that has outlived the
  // calendar day it belongs to, or has been running an implausibly long time.
  const LONG_OPEN_HOURS=10;

  const E=v=>window.esc?window.esc(v??''):String(v??'');
  const N=v=>Number(v||0).toLocaleString('vi-VN');
  const hcmToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const clock=d=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(d);
  const dateLabel=v=>{const d=new Date(`${v}T12:00:00+07:00`);return Number.isNaN(d.getTime())?v:new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',weekday:'long',day:'2-digit',month:'2-digit',year:'numeric'}).format(d)};
  const hourOf=v=>{if(!v)return null;const d=new Date(v);if(Number.isNaN(d.getTime()))return null;return Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',hour12:false}).format(d))};
  const pct=(a,b)=>Number(b)>0?Math.round(Number(a)/Number(b)*100):null;
  const validDate=v=>/^\d{4}-\d{2}-\d{2}$/.test(String(v||''));

  async function renderDailyDashboardKiosk(){
    // Take over the shared page timer so any previously rendered page's
    // polling stops, exactly like renderDashboard()/renderOverview() do.
    if(typeof dashboardTimer!=='undefined'&&dashboardTimer){clearInterval(dashboardTimer);dashboardTimer=null}
    const query=new URLSearchParams(location.search);
    const date=validDate(query.get('date'))?query.get('date'):hcmToday();
    // The date must survive refresh / Back / Forward / a copied link. openPage()
    // already put ?page= in the URL; make sure ?date= is there too even when the
    // view was deep-linked without one.
    if(query.get('date')!==date)AppNav.setQuery({date});
    // Drives the full-bleed dark layout in ui.css and lets the popstate handler
    // in app.js recognise which screen is on show. Reverts by itself the moment
    // another page calls setActive().
    document.body.dataset.page=PAGE_ID;
    title.textContent='Kiosk điều hành';
    subtitle.textContent='Màn hình lớn cho xưởng — tổng hợp toàn ngày, chỉ để theo dõi.';

    content.innerHTML=`<div class="kiosk-display" id="kioskRoot" data-kiosk-date="${E(date)}">
    <header class="kiosk-header">
      <div class="kiosk-identity">
        <b>MESFlow</b>
        <span id="kioskScope">Điều hành sản xuất</span>
      </div>
      <div class="kiosk-day">
        <small>Ngày làm việc</small>
        <strong id="kioskDate">${E(dateLabel(date))}</strong>
      </div>
      <div class="kiosk-clock">
        <small>Giờ hiện tại</small>
        <strong id="kioskClock">${E(clock(new Date()))}</strong>
      </div>
      <div class="kiosk-shift" id="kioskShift">
        <small>Ca hiện tại (tham khảo)</small>
        <strong>—</strong>
      </div>
      <div class="kiosk-live" id="kioskLive" data-state="loading">
        <i aria-hidden="true"></i>
        <span id="kioskLiveText">Đang tải dữ liệu…</span>
      </div>
      <div class="kiosk-actions">
        <button class="kiosk-btn" id="kioskRefresh" type="button">Làm mới ngay</button>
        <button class="kiosk-btn" id="kioskExit" type="button">Thoát</button>
      </div>
    </header>

    <section class="kiosk-kpis" id="kioskKpis" aria-live="polite"></section>

    <div class="kiosk-body">
      <div class="kiosk-col-main">
        <section class="kiosk-panel kiosk-chart-panel">
          <div class="kiosk-panel-head">
            <h2>Sản lượng theo giờ</h2>
            <span class="kiosk-panel-note" id="kioskChartNote"></span>
          </div>
          <div class="kiosk-panel-body" id="kioskHourly"></div>
        </section>
        <section class="kiosk-panel kiosk-station-panel">
          <div class="kiosk-panel-head">
            <h2>Trạng thái Operation</h2>
            <span class="kiosk-panel-note" id="kioskStationNote"></span>
          </div>
          <div class="kiosk-panel-body" id="kioskStations"></div>
        </section>
      </div>
      <div class="kiosk-col-side">
        <section class="kiosk-panel kiosk-attention-panel">
          <div class="kiosk-panel-head">
            <h2>Cần xử lý ngay</h2>
            <span class="kiosk-attention-count" id="kioskAttentionCount">—</span>
          </div>
          <div class="kiosk-panel-body" id="kioskAttention"></div>
          <p class="kiosk-panel-foot" id="kioskAttentionFoot"></p>
        </section>
        <section class="kiosk-panel kiosk-mini-panel kiosk-panel-ng">
          <div class="kiosk-panel-head"><h2>NG theo Operation</h2></div>
          <div class="kiosk-panel-body" id="kioskNg"></div>
        </section>
        <section class="kiosk-panel kiosk-mini-panel kiosk-panel-people">
          <div class="kiosk-panel-head"><h2>Nhân viên đang làm</h2></div>
          <div class="kiosk-panel-body" id="kioskPeople"></div>
        </section>
        <section class="kiosk-panel kiosk-mini-panel kiosk-panel-repair">
          <div class="kiosk-panel-head"><h2>Hàng chờ sửa</h2></div>
          <div class="kiosk-panel-body" id="kioskRepair"></div>
        </section>
      </div>
    </div>
  </div>`;

    const root=()=>document.getElementById('kioskRoot');
    const alive=()=>{const el=root();return !!el&&el.dataset.kioskDate===date};

    document.getElementById('kioskExit').onclick=()=>openPage('dashboard',document.querySelector('[data-page="dashboard"]'));

    // ---- header clock (1s) -------------------------------------------------
    const tickClock=()=>{const el=document.getElementById('kioskClock');if(el)el.textContent=clock(new Date())};

    // ---- shift metadata: REFERENCE ONLY, never a filter ---------------------
    // Requirement B: ca is metadata. The whole view is a calendar day; nothing
    // below ever narrows by shift.
    const paintShift=shifts=>{
      const box=document.getElementById('kioskShift');if(!box)return;
      const nowParts=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date()).split(':').map(Number);
      const minute=nowParts[0]*60+nowParts[1];
      const toMin=v=>{const [h,m]=String(v||'00:00').split(':').map(Number);return h*60+m};
      const hit=(shifts||[]).filter(x=>x.active!==false).find(x=>{const s=toMin(x.anchor_start),e=toMin(x.anchor_end);return (x.cross_midnight||e<=s)?(minute>=s||minute<e):(minute>=s&&minute<e)});
      box.innerHTML=`<small>Ca hiện tại (tham khảo)</small><strong>${hit?E(hit.name):'Ngoài ca'}</strong>`;
    };

    // ---- KPI strip ---------------------------------------------------------
    // Every tile below is backed by a field the API actually returns. Where a
    // number cannot be sourced honestly it is rendered as "—" with the reason,
    // never back-filled with a guess.
    const paintKpis=(day,pos,attentionCount)=>{
      const box=document.getElementById('kioskKpis');if(!box)return;
      const sessions=day.sessions||[],items=day.items||[];
      const good=sessions.reduce((n,x)=>n+Number(x.good_qty||0),0);
      const ng=sessions.reduce((n,x)=>n+Number(x.defect_qty||0),0);
      const runningOps=items.filter(x=>Number(x.open_session_count)>0).length;
      const openSessions=sessions.filter(x=>x.session_status==='OPEN');
      const working=new Set(openSessions.map(x=>x.employee_id)).size;
      const present=new Set(sessions.map(x=>x.employee_id)).size;
      // PO scope = the POs that actually produced today. Summing planned_quantity
      // over `items` would multiply each PO's plan by its operation count; these
      // come from the PO-level rows instead, de-duplicated by po_id.
      const todayPoIds=new Set(items.map(x=>Number(x.po_id)));
      const scoped=(pos||[]).filter(x=>todayPoIds.has(Number(x.po_id)));
      const plan=scoped.reduce((n,x)=>n+Number(x.planned_quantity||0),0);
      const cumGood=scoped.reduce((n,x)=>n+Number(x.good_quantity||0),0);
      const remaining=scoped.reduce((n,x)=>n+Number(x.remaining_quantity||0),0);
      const planPct=pct(cumGood,plan);
      const tiles=[
        {k:'good',label:'Sản lượng đạt',value:N(good),unit:'SP',note:`${sessions.length} session trong ngày`},
        {k:'plan',label:'Kế hoạch PO đang chạy',value:plan?N(plan):'—',unit:plan?'SP':'',note:plan?`${scoped.length} PO có sản xuất hôm nay`:'Chưa có PO gắn kế hoạch'},
        {k:(planPct===null?'plain':planPct>=100?'good':planPct>=80?'warn':'bad'),label:'% đạt kế hoạch',value:planPct===null?'—':`${planPct}%`,unit:'',note:planPct===null?'Chưa có kế hoạch để đối chiếu':`Lũy kế PO: ${N(cumGood)} / ${N(plan)} SP`},
        {k:'plain',label:'Còn phải sản xuất',value:plan?N(remaining):'—',unit:plan?'SP':'',note:plan?'Lũy kế theo PO đang chạy':'Chưa có kế hoạch để đối chiếu'},
        {k:'run',label:'Operation đang chạy',value:N(runningOps),unit:'OP',note:`${openSessions.length} session đang mở`},
        {k:'run',label:'Nhân viên đang làm',value:N(working),unit:'người',note:`${N(present)} người có hoạt động hôm nay`},
        {k:ng>0?'warn':'plain',label:'NG trong ngày',value:N(ng),unit:'SP',note:`${items.filter(x=>Number(x.day_defect_qty)>0).length} OP phát sinh NG`},
        {k:attentionCount>0?'bad':'good',label:'Cần xử lý ngay',value:N(attentionCount),unit:'điểm',note:attentionCount>0?'Xem danh sách bên phải':'Không có điểm cần xử lý'}
      ];
      box.innerHTML=tiles.map(t=>`<article class="kiosk-kpi ${t.k}"><small>${E(t.label)}</small><strong>${E(t.value)}${t.unit?`<u>${E(t.unit)}</u>`:''}</strong><span>${E(t.note)}</span></article>`).join('');
    };

    // ---- hourly output -----------------------------------------------------
    // Bucketed by the moment a session's numbers were last recorded
    // (effective_end_at is COALESCE(ended_at, CURRENT_TIMESTAMP) server-side, so
    // an OPEN session lands in the current hour). There is NO hourly plan
    // anywhere in the data model, so none is drawn -- the reference line is the
    // day's own average and is labelled as exactly that.
    const paintHourly=day=>{
      const box=document.getElementById('kioskHourly'),note=document.getElementById('kioskChartNote');if(!box)return;
      const buckets=Array.from({length:24},()=>({good:0,ng:0}));
      let placed=0;
      for(const s of day.sessions||[]){
        const h=hourOf(s.ended_at||s.effective_end_at||s.started_at);
        if(h===null||h<0||h>23)continue;
        buckets[h].good+=Number(s.good_qty||0);buckets[h].ng+=Number(s.defect_qty||0);placed++;
      }
      const totalGood=buckets.reduce((n,b)=>n+b.good,0);
      const active=buckets.filter(b=>b.good>0||b.ng>0);
      const avg=active.length?totalGood/active.length:0;
      const peak=Math.max(1,...buckets.map(b=>b.good+b.ng));
      if(note)note.textContent=placed?`Chưa cấu hình kế hoạch theo giờ · đường TB ${Math.round(avg).toLocaleString('vi-VN')} SP/giờ`:'Chưa cấu hình kế hoạch theo giờ';
      if(!placed){box.innerHTML='<div class="kiosk-empty"><b>Chưa có sản lượng ghi nhận</b><span>Biểu đồ sẽ hiện khi có session báo số lượng trong ngày.</span></div>';return}
      const avgTop=avg>0?(avg/peak*100):0;
      box.innerHTML=`<div class="kiosk-chart">
        <div class="kiosk-chart-plot">
          ${avg>0?`<i class="kiosk-chart-avg" style="bottom:${avgTop.toFixed(2)}%" aria-hidden="true"><b>TB ${Math.round(avg).toLocaleString('vi-VN')}</b></i>`:''}
          ${buckets.map((b,h)=>{
            const total=b.good+b.ng;
            const state=total===0?'none':b.good>=avg?'over':'under';
            return `<div class="kiosk-bar ${state}" title="${E(`${String(h).padStart(2,'0')}:00 · Đạt ${N(b.good)} · NG ${N(b.ng)}`)}">
              <span class="kiosk-bar-value">${total?N(b.good):''}</span>
              <span class="kiosk-bar-stack" style="height:${(total/peak*100).toFixed(2)}%">
                ${b.ng?`<i class="ng" style="height:${(b.ng/total*100).toFixed(2)}%"></i>`:''}
                <i class="good"></i>
              </span>
              <span class="kiosk-bar-label">${String(h).padStart(2,'0')}</span>
            </div>`}).join('')}
        </div>
        <div class="kiosk-chart-legend">
          <span><i class="sw over"></i>Đạt ≥ TB giờ</span>
          <span><i class="sw under"></i>Dưới TB giờ</span>
          <span><i class="sw ng"></i>NG</span>
          <span class="kiosk-legend-note">Kế hoạch theo giờ: chưa có trong dữ liệu</span>
        </div>
      </div>`;
    };

    // ---- Operation / station table ----------------------------------------
    // Convention: Vietnamese Operation NAME is the primary line, the code is the
    // small secondary line underneath. Ratios reuse the exact formulas the daily
    // dashboard already uses (total_good_qty/planned_quantity for product
    // progress, day_work_seconds/planned_work_seconds for time efficiency), so
    // the two screens can never disagree.
    const stateLabel=s=>({RUNNING:'Đang chạy',NEEDS_REVIEW:'Cần xử lý',UPDATED:'Đã cập nhật',IDLE:'Không có người'}[s]||s||'—');
    const paintStations=day=>{
      const box=document.getElementById('kioskStations'),note=document.getElementById('kioskStationNote');if(!box)return;
      const rank=x=>x.day_state==='NEEDS_REVIEW'?0:Number(x.open_session_count)>0?1:2;
      const rows=[...(day.items||[])].sort((a,b)=>rank(a)-rank(b)||Number(b.day_good_qty||0)-Number(a.day_good_qty||0));
      if(note)note.textContent=rows.length?`${rows.length} Operation có hoạt động · hiển thị ${Math.min(rows.length,12)}`:'';
      if(!rows.length){box.innerHTML='<div class="kiosk-empty"><b>Chưa có Operation hoạt động</b><span>Danh sách hiện khi có session bắt đầu trong ngày.</span></div>';return}
      box.innerHTML=`<div class="kiosk-table">
        <div class="kiosk-tr kiosk-th"><span>Operation</span><span>Trạng thái</span><span>Người làm</span><span>Đạt / Kế hoạch</span><span>NG</span><span>Hiệu suất giờ</span></div>
        ${rows.slice(0,12).map(x=>{
          const planQty=Number(x.planned_quantity||0),doneQty=Number(x.total_good_qty||0);
          const productPct=pct(doneQty,planQty);
          const plannedSec=Number(x.planned_work_seconds||0),actualSec=Number(x.day_work_seconds||0);
          const timePct=pct(actualSec,plannedSec);
          const timeState=timePct===null?'none':timePct>110?'bad':timePct>=80?'warn':'good';
          const workers=(x.active_workers||[]).map(w=>w&&w.name).filter(Boolean);
          return `<div class="kiosk-tr state-${E(String(x.day_state||'').toLowerCase())}">
            <span class="kiosk-op">
              <b>${E(x.operation_name||'—')}</b>
              <small>${E(x.operation_code||'')}${x.po_code?` · ${E(x.po_code)}`:''}</small>
            </span>
            <span><em class="kiosk-state ${E(String(x.day_state||'').toLowerCase())}">${E(stateLabel(x.day_state))}</em></span>
            <span class="kiosk-workers">${workers.length?E(workers.slice(0,2).join(', ')):'—'}${workers.length>2?` <u>+${workers.length-2}</u>`:''}</span>
            <span class="kiosk-qty"><b>${N(doneQty)}</b>${planQty?` / ${N(planQty)}`:' / —'}${productPct===null?'':`<i class="kiosk-meter"><u style="width:${Math.min(100,productPct)}%"></u></i>`}</span>
            <span class="kiosk-ng ${Number(x.day_defect_qty)>0?'has':''}">${N(x.day_defect_qty)}</span>
            <span class="kiosk-eff ${timeState}">${timePct===null?'<u>Chưa có định mức</u>':`${timePct}%`}</span>
          </div>`}).join('')}
      </div>`;
    };

    // ---- "Cần xử lý ngay" --------------------------------------------------
    // Assembled from signals that already exist. Nothing here invents a new
    // exception engine: NEEDS_REVIEW comes straight from daily_progress()'s own
    // day_state, the dispatch verdict comes from /api/production-control's
    // control_label + recommended_action, the repair backlog from the overview
    // endpoint. Only the NG ratio and the long-open-session cutoff are local,
    // and both display the raw number that triggered them.
    const buildAttention=(day,pos,controlOps)=>{
      const out=[];
      const dayEnd=day.context&&day.context.day_end?new Date(day.context.day_end).getTime():null;
      const now=Date.now();
      for(const x of day.items||[]){
        if(Number(x.unconfirmed_count||0)>0)out.push({sev:0,tag:'Session chưa xác nhận',title:x.operation_name||x.operation_code,sub:`${x.operation_code||''} · ${N(x.unconfirmed_count)} session tự đóng chưa xác nhận số liệu`});
      }
      for(const s of day.sessions||[]){
        if(s.session_status!=='OPEN')continue;
        const started=new Date(s.started_at).getTime();
        const hours=(now-started)/3600000;
        const overDay=dayEnd!==null&&now>dayEnd;
        if(hours>=LONG_OPEN_HOURS||overDay)out.push({sev:1,tag:'Session mở quá lâu',title:s.employee_name||s.employee_code||'—',sub:`${s.operation_name||s.operation_code||''} · đã mở ${Math.floor(hours)} giờ`});
      }
      for(const x of day.items||[]){
        const ng=Number(x.day_defect_qty||0),good=Number(x.day_good_qty||0),base=ng+good;
        if(ng>0&&base>0&&ng/base>=NG_RATIO_ALERT)out.push({sev:1,tag:'NG cao',title:x.operation_name||x.operation_code,sub:`${x.operation_code||''} · NG ${N(ng)}/${N(base)} = ${Math.round(ng/base*100)}%`});
      }
      // Dispatch verdict, read as-is from the control endpoint.
      const todayOps=new Set((day.items||[]).map(x=>Number(x.operation_id)));
      for(const x of controlOps||[]){
        if(x.control_state!=='CRITICAL')continue;
        if(todayOps.size&&!todayOps.has(Number(x.operation_id)))continue;
        out.push({sev:1,tag:E(x.control_label||'Làm ngay'),title:x.operation_name||x.operation_code,sub:`${x.operation_code||''} · ${x.recommended_action||'Ưu tiên điều phối'}`});
      }
      for(const po of pos||[]){
        const pending=Number(po.repair_pending_quantity||0);
        if(pending>0)out.push({sev:2,tag:'Chờ sửa',title:po.po_code||'—',sub:`${N(pending)} SP chờ sửa${po.product?` · ${po.product}`:''}`});
      }
      return out.sort((a,b)=>a.sev-b.sev);
    };
    const paintAttention=list=>{
      const box=document.getElementById('kioskAttention'),count=document.getElementById('kioskAttentionCount'),foot=document.getElementById('kioskAttentionFoot');
      if(!box)return;
      if(count){count.textContent=list.length?`${list.length} điểm`:'Sạch';count.classList.toggle('clear',!list.length)}
      // Requirement E lists two signals this system genuinely has no source for.
      // Say so, rather than shipping an empty widget that reads as "no problems".
      if(foot)foot.textContent='Thiếu vật tư và phút dừng theo lý do: chưa có nguồn dữ liệu trong hệ thống.';
      box.innerHTML=list.length
        ?`<div class="kiosk-alert-list">${list.slice(0,8).map(x=>`<article class="kiosk-alert sev${x.sev}"><span class="kiosk-alert-tag">${E(x.tag)}</span><b>${E(x.title)}</b><small>${E(x.sub)}</small></article>`).join('')}${list.length>8?`<div class="kiosk-alert-more">+${list.length-8} điểm khác</div>`:''}</div>`
        :'<div class="kiosk-empty ok"><b>Không có điểm cần xử lý</b><span>Mọi Operation trong ngày đang ở trạng thái bình thường.</span></div>';
    };

    // ---- side panels -------------------------------------------------------
    const paintSidePanels=(day,pos)=>{
      const ngBox=document.getElementById('kioskNg');
      if(ngBox){
        const rows=(day.items||[]).filter(x=>Number(x.day_defect_qty)>0).sort((a,b)=>Number(b.day_defect_qty)-Number(a.day_defect_qty));
        ngBox.innerHTML=rows.length?`<ul class="kiosk-list">${rows.slice(0,5).map(x=>`<li><span><b>${E(x.operation_name||x.operation_code)}</b><small>${E(x.operation_code||'')}</small></span><strong class="bad">${N(x.day_defect_qty)}</strong></li>`).join('')}</ul>`:'<div class="kiosk-empty ok compact"><b>Không có NG hôm nay</b></div>';
      }
      const peopleBox=document.getElementById('kioskPeople');
      if(peopleBox){
        const open=(day.sessions||[]).filter(x=>x.session_status==='OPEN');
        const byEmp=new Map();
        for(const s of open)if(!byEmp.has(s.employee_id))byEmp.set(s.employee_id,s);
        const rows=[...byEmp.values()];
        peopleBox.innerHTML=rows.length?`<ul class="kiosk-list">${rows.slice(0,6).map(s=>`<li><span><b>${E(s.employee_name||'—')}</b><small>${E(s.operation_name||s.operation_code||'')}</small></span><strong class="ok">Đang làm</strong></li>`).join('')}${rows.length>6?`<li class="more">+${rows.length-6} người</li>`:''}</ul>`:'<div class="kiosk-empty compact"><b>Không có ai đang làm</b></div>';
      }
      const repairBox=document.getElementById('kioskRepair');
      if(repairBox){
        const rows=(pos||[]).filter(x=>Number(x.repair_pending_quantity)>0).sort((a,b)=>Number(b.repair_pending_quantity)-Number(a.repair_pending_quantity));
        repairBox.innerHTML=rows.length?`<ul class="kiosk-list">${rows.slice(0,5).map(x=>`<li><span><b>${E(x.po_code)}</b><small>${E(x.product||'')}</small></span><strong class="warn">${N(x.repair_pending_quantity)} SP</strong></li>`).join('')}</ul>`:'<div class="kiosk-empty ok compact"><b>Không có hàng chờ sửa</b></div>';
      }
    };

    // ---- polling -----------------------------------------------------------
    // In-place update only: the shell above is never re-rendered, so a refresh
    // cannot make the TV flash or lose scroll. On failure the last good screen
    // stays exactly as it was and only the status chip changes -- a control-room
    // display going blank is worse than one showing slightly stale numbers.
    let shiftsLoaded=false,lastOk=null;
    const setLive=(state,text)=>{
      const chip=document.getElementById('kioskLive'),label=document.getElementById('kioskLiveText');
      if(chip)chip.dataset.state=state;
      if(label)label.textContent=text;
    };
    const load=async()=>{
      try{
        if(!shiftsLoaded){
          try{const s=await api('/api/settings/work-shifts');paintShift(s.items||[]);shiftsLoaded=true}
          catch(_e){/* ca chỉ là metadata tham khảo -- không được chặn cả màn hình */}
        }
        const [day,overview,control]=await Promise.all([
          api(`/api/dashboard/day?date=${encodeURIComponent(date)}&limit=1000`),
          api('/api/dashboard/overview?limit=5000'),
          api('/api/production-control?limit=2000')
        ]);
        if(!alive())return;
        const pos=overview.production_orders||[];
        const attention=buildAttention(day,pos,control.operations||[]);
        paintKpis(day,pos,attention.length);
        paintHourly(day);
        paintStations(day);
        paintAttention(attention);
        paintSidePanels(day,pos);
        lastOk=new Date();
        setLive('live',`Trực tiếp · Cập nhật lần cuối ${clock(lastOk)}`);
      }catch(e){
        if(!alive())return;
        setLive('stale',lastOk?`Mất kết nối · Số liệu lúc ${clock(lastOk)}`:`Không tải được dữ liệu · ${e.message||e}`);
        if(!lastOk){
          const box=document.getElementById('kioskKpis');
          if(box&&!box.children.length)box.innerHTML=`<article class="kiosk-kpi bad kiosk-kpi-error"><small>Không tải được dữ liệu</small><strong>—</strong><span>${E(e.message||e)}</span></article>`;
        }
      }
    };

    document.getElementById('kioskRefresh').onclick=()=>{setLive('loading','Đang làm mới…');load()};

    await load();
    // One timer drives both the clock and the data poll, so it is a single
    // handle the next page's `clearInterval(dashboardTimer)` can cancel. The
    // alive() guard stops it even if some future page forgets to.
    let ticks=0;
    dashboardTimer=setInterval(()=>{
      if(!alive()){clearInterval(dashboardTimer);dashboardTimer=null;return}
      tickClock();
      if(++ticks*1000>=REFRESH_MS){ticks=0;load()}
    },1000);
  }

  window.renderDailyDashboardKiosk=renderDailyDashboardKiosk;
  window.registerPage(PAGE_ID,renderDailyDashboardKiosk);
})();
