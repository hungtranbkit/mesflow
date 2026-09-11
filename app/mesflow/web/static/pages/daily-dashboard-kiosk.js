// Kiosk điều hành (control-room display) -- màn hình lớn treo tường xưởng.
//
// SEMANTICS, vì "kiosk" là từ bị dùng cho hai thứ khác nhau trong repo này:
//   * kiosk.py / kiosk_v2.py / templates/kiosk.html -> THIẾT BỊ ngoài xưởng,
//     công nhân quét thẻ QR lên đó. Có input, có ghi dữ liệu, có device identity.
//   * FILE NÀY -> màn hình TREO TƯỜNG, chỉ đọc, không quét, không ghi gì.
// Một admin bấm "Mở màn hình lớn" không bao giờ được rơi vào thứ trông giống
// terminal quét thẻ.
//
// v1 CHỈ HIỂN THỊ CHI TIẾT MỘT PO TẠI MỘT THỜI ĐIỂM.
// (nguồn sự thật: docs/MESFLOW_MASTER_REQUIREMENTS_VI.md, REQ-KIOSK-010)
//
// Lý do là một quan sát về người xem, không phải về kỹ thuật: người đứng trước
// TV đang theo dõi MỘT đơn hàng. Trộn task của nhiều PO lên cùng màn làm mọi
// con số mất nghĩa -- "đạt 120" là của PO nào? Biến động của PO khác vẫn cần
// biết, nhưng chỉ ở mức "có chuyện xảy ra, bấm để xem", và tuyệt đối không
// được làm xô lệch danh sách task đang xem.
//
// BA NGUYÊN TẮC CHỐNG "TASK BIẾN MẤT NHƯ MA THUẬT":
//   1. Phân trang tự động thay vì cắt top-N. Bản cũ đo chiều cao rồi giấu bớt
//      hàng kèm dòng "+N Operation khác" -- nghĩa là có task không bao giờ
//      xuất hiện. Nay mọi task active đều có lượt lên màn.
//   2. Trang được CHỤP LẠI (snapshot) trong suốt một chu kỳ. Dữ liệu mới về
//      giữa chừng không được phép sắp xếp lại danh sách dưới mắt người đang
//      đọc; nó chỉ có hiệu lực ở ranh giới trang kế tiếp.
//   3. Task hoàn thành KHÔNG biến mất ngay. Nó ở lại vài giây với nhãn "Vừa
//      hoàn thành" kèm người cập nhật, rồi mới rời danh sách ở chu kỳ sau.
//
// DỮ LIỆU. Hai endpoint chỉ-đọc dựng riêng cho màn này (app/mesflow/web/
// kiosk_board.py), cả hai đều gọi lại repository sẵn có chứ không viết lại quy
// tắc nghiệp vụ nào:
//   /api/kiosk-board?po_id=          -> PO + KPI + task, đã thu hẹp theo PO
//   /api/kiosk-board/activity?po_id= -> dòng sự kiện, có con trỏ since_id
(()=>{
  const PAGE_ID='daily-dashboard-kiosk';

  // --- nhịp ----------------------------------------------------------------
  const BOARD_MS=12000;          // KPI + task: trong khoảng 10-15s đã chốt
  const ACTIVITY_MS=4000;        // dòng sự kiện: nhanh hơn, payload nhỏ
  const HIDDEN_FACTOR=5;         // tab ẩn thì giãn nhịp ra, không spam API
  const PAGE_MS=10000;           // mỗi trang task đứng yên 10s (khoảng 8-12s)
  const INTERACT_PAUSE_MS=15000; // chạm/rê chuột thì dừng lật trang để đọc
  const COMPLETION_HOLD_MS=8000; // giữ task vừa xong trên màn (khoảng 5-10s)
  const NEW_EVENT_HIGHLIGHT_MS=2500;
  const FEED_MAX=15;             // giữ 8-15 sự kiện gần nhất TRONG BỘ NHỚ
  const OTHER_MAX=5;             // giữ tối đa 5 biến động PO khác trong bộ nhớ

  // SỐ HÀNG VẼ RA LÀ CHUYỆN KHÁC VỚI SỐ HÀNG GIỮ TRONG BỘ NHỚ. Ba panel phụ
  // cao theo nội dung, nên nếu cứ vẽ hết những gì đang giữ rồi để CSS cắt bằng
  // `overflow:hidden` thì hàng cuối bị cắt NGANG THÂN -- đo được ở bản trước:
  // ở 1366 panel "Cần xử lý ngay" hiện đúng một cảnh báo và cảnh báo đó bị cắt
  // đôi, đọc như layout vỡ chứ không như "còn nữa".
  // Nên số hàng vẽ ra đọc từ chính thang mật độ của Kiosk trong ui.css
  // (`--kd-*-rows`, REQ-KIOSK-012): một chỗ duy nhất quyết định mật độ, và
  // media query đổi bậc màn hình thì JS đi theo mà không cần biết breakpoint.

  const E=v=>window.esc?window.esc(v??''):String(v??'');
  const N=v=>Number(v||0).toLocaleString('vi-VN');
  const hcmToday=()=>new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const clock=d=>new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(d);
  const hhmm=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?'':new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',hour12:false}).format(d)};
  const hhmmss=v=>{const d=new Date(v);return Number.isNaN(d.getTime())?'':clock(d)};
  const dateLabel=v=>{const d=new Date(`${v}T12:00:00+07:00`);return Number.isNaN(d.getTime())?v:new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',weekday:'long',day:'2-digit',month:'2-digit',year:'numeric'}).format(d)};
  const pct=(a,b)=>Number(b)>0?Math.round(Number(a)/Number(b)*100):null;
  const validDate=v=>/^\d{4}-\d{2}-\d{2}$/.test(String(v||''));

  /** "vừa xong" / "3 phút trước" -- thời gian tương đối, kèm giờ tuyệt đối. */
  function relative(iso){
    const t=new Date(iso).getTime();
    if(Number.isNaN(t))return '';
    const s=Math.max(0,Math.round((Date.now()-t)/1000));
    if(s<45)return 'vừa xong';
    if(s<3600)return `${Math.round(s/60)} phút trước`;
    if(s<86400)return `${Math.round(s/3600)} giờ trước`;
    return hhmm(iso);
  }

  // --- câu chữ cho một sự kiện ---------------------------------------------
  // Mỗi dòng phải trả lời đủ: AI · LÀM GÌ · TRÊN CÁI GÌ · RA SAO · LÚC NÀO.
  // Không có actor thì nói thẳng "Hệ thống", KHÔNG bịa ra một cái tên người.
  const TONE={
    GOOD_QUANTITY_RECORDED:'ok', OPERATION_COMPLETED:'ok', PO_COMPLETED:'ok', SETUP_COMPLETED:'ok',
    DEFECT_QUANTITY_RECORDED:'bad', REPAIRABLE_DEFECT_RECORDED:'warn', REWORK_RESOLVED:'warn',
    SESSION_STARTED:'start', OPERATION_STARTED:'start', PO_STARTED:'start',
    SESSION_FINISHED:'neutral', SESSION_AUTO_CLOSED:'warn',
    VALUE_CHANGED:'warn', OPERATION_STATUS_CHANGED:'neutral', PO_STATUS_CHANGED:'neutral',
  };
  function actorOf(ev){
    return ev.actor_kind==='SYSTEM'||!ev.actor_name?'Hệ thống':ev.actor_name;
  }
  function objectOf(ev){
    if(ev.operation_name)return `OP ${ev.operation_name}`;
    if(ev.operation_code)return `OP ${ev.operation_code}`;
    if(ev.po_code)return `PO ${ev.po_code}`;
    return '';
  }
  /** Phần "làm gì" + "ra sao". Chỉ dùng dữ liệu có thật trong event. */
  function phraseOf(ev){
    const delta=ev.quantity_delta==null?null:Number(ev.quantity_delta);
    const signed=delta==null?'':`${delta>0?'+':''}${N(delta)}`;
    switch(ev.event_type){
      case 'GOOD_QUANTITY_RECORDED':return {action:`cập nhật ${signed} SP đạt`,impact:progressImpact(ev)};
      case 'DEFECT_QUANTITY_RECORDED':return {action:`ghi nhận ${signed} NG`,impact:''};
      case 'REPAIRABLE_DEFECT_RECORDED':return {action:`ghi nhận ${signed} lỗi sửa được`,impact:'vào hàng chờ sửa'};
      case 'SESSION_STARTED':return {action:'nhận việc',impact:'bắt đầu session'};
      case 'SESSION_FINISHED':return {action:'kết thúc việc',impact:''};
      case 'SESSION_AUTO_CLOSED':return {action:'tự đóng session cuối ca',impact:'chưa xác nhận số liệu'};
      case 'OPERATION_COMPLETED':return {action:'hoàn thành',impact:progressImpact(ev)};
      case 'OPERATION_STARTED':return {action:'bắt đầu chạy',impact:''};
      case 'SETUP_COMPLETED':return {action:'hoàn tất setup máy',impact:''};
      case 'REWORK_RESOLVED':return {action:'xử lý hàng chờ sửa',impact:''};
      case 'PO_COMPLETED':return {action:'hoàn thành toàn bộ PO',impact:''};
      case 'PO_STARTED':return {action:'bắt đầu sản xuất',impact:''};
      case 'VALUE_CHANGED':return {action:'chỉnh số liệu',impact:''};
      default:return {action:ev.title||ev.event_type,impact:''};
    }
  }
  /** "đạt 120/120, hoàn thành" -- chỉ khi biết cả hai số, không suy diễn. */
  function progressImpact(ev){
    const done=Number(ev.operation_done_qty||0),plan=Number(ev.operation_plan_qty||0);
    if(!plan)return '';
    const p=pct(done,plan);
    return p!==null&&p>=100?`đạt ${N(done)}/${N(plan)}, hoàn thành`:`đạt ${N(done)}/${N(plan)}`;
  }

  /** Đọc một token mật độ (số nguyên) của Kiosk từ CSS. */
  function density(el,name,dflt){
    if(!el)return dflt;
    const v=parseInt(getComputedStyle(el).getPropertyValue(name),10);
    return Number.isFinite(v)?v:dflt;
  }

  /** Số hàng vừa một khung, đo THẬT trên DOM đã render.
   *
   * Đo BƯỚC NHẢY giữa hai hàng liền nhau, không phải chiều cao một hàng: giữa
   * hai hàng còn có `gap`, bỏ qua nó thì phép chia ra thừa một hàng và hàng
   * cuối bị cắt ngang đáy panel. Trên màn treo tường không ai cuộn được, một
   * hàng cắt đôi đọc như layout vỡ chứ không như "còn nữa".
   *
   * Dùng chung cho danh sách task và dòng hoạt động -- hai panel co giãn duy
   * nhất của màn này.
   */
  function fitRows(box,sel,min,max,fallback){
    if(!box)return fallback;
    const rows=box.querySelectorAll(sel);
    if(!rows.length)return fallback;
    const first=rows[0].getBoundingClientRect();
    const pitch=rows.length>1
      ?rows[1].getBoundingClientRect().top-first.top
      :first.height+6;
    if(!(pitch>0))return fallback;
    const usable=box.getBoundingClientRect().height;
    // +gap vì hàng CUỐI không có gap phía sau nó.
    return Math.max(min,Math.min(max,Math.floor((usable+(pitch-first.height))/pitch)));
  }

  /** Vẽ giảm dần cho tới khi PHẦN TỬ CUỐI nằm trọn trong khung.
   *
   * Khác `fitRows` ở một điểm quyết định: `fitRows` chia chiều cao cho bước
   * nhảy, nên nó chỉ đúng khi MỌI hàng cao bằng nhau. Hàng task thì đúng như
   * vậy (một dòng, cắt bằng ellipsis), nhưng dòng hoạt động thì KHÔNG: câu
   * "Hệ thống tự đóng session cuối ca OP ... → chưa xác nhận số liệu" xuống
   * hai dòng còn "Trần Thị C nhận việc OP ..." chỉ một dòng. Đo được ở 1366:
   * `fitRows` trả 4 trong khi khung chỉ chứa 3 -- hàng thứ tư bị cắt ngang.
   * Vòng lặp này không giả định gì về chiều cao hàng, và nó còn tự tính cả
   * dòng "+N ... khác" vì dòng đó cũng là phần tử cuối.
   *
   * Số vòng tối đa bằng `max` (<=6 ở đây) và mỗi vòng chỉ dựng vài hàng.
   */
  function fitDown(box,draw,max,min){
    for(let n=max;n>min;n--){
      draw(n);
      const last=box.lastElementChild;
      if(!last)return n;
      if(last.getBoundingClientRect().bottom<=box.getBoundingClientRect().bottom+1)return n;
    }
    draw(min);
    return min;
  }

  async function renderDailyDashboardKiosk(){
    if(typeof dashboardTimer!=='undefined'&&dashboardTimer){clearInterval(dashboardTimer);dashboardTimer=null}
    const query=new URLSearchParams(location.search);
    const date=validDate(query.get('date'))?query.get('date'):hcmToday();
    const initialPo=Number(query.get('po_id')||0)||null;
    if(query.get('date')!==date)AppNav.setQuery({date});
    document.body.dataset.page=PAGE_ID;
    title.textContent='Kiosk điều hành';
    subtitle.textContent='Màn hình lớn cho xưởng — theo dõi chi tiết một Production Order.';

    // Toàn bộ trạng thái của màn nằm trong một chỗ, để không có hai nguồn sự
    // thật về "đang xem PO nào / đang ở trang mấy".
    const S={
      poId:initialPo,
      po:null,
      tasks:[],            // dữ liệu mới nhất từ server
      snapshot:[],         // danh sách ĐANG hiển thị, đóng băng trong chu kỳ
      completedHold:new Map(), // operation_id -> {task, until, actor, delta}
      page:0,
      perPage:8,
      pauseUntil:0,
      feed:[],
      feedShow:0,         // số sự kiện ĐANG vẽ; đo lại khi khung đổi
      budget:{},          // số hàng đang vẽ của hai panel cao-theo-nội-dung
      seen:new Set(),
      latestId:null,
      lastOk:null,
    };

    content.innerHTML=`<div class="kiosk-display kiosk-focus" id="kioskRoot" data-kiosk-date="${E(date)}">
    <header class="kiosk-header">
      <div class="kiosk-identity">
        <b>MESFlow</b>
        <span>Điều hành sản xuất</span>
      </div>
      <div class="kiosk-po" id="kioskPoBox">
        <small>Production Order đang theo dõi</small>
        <strong id="kioskPoCode">—</strong>
        <span id="kioskPoProduct"></span>
      </div>
      <div class="kiosk-po-progress" id="kioskPoProgress"></div>
      <div class="kiosk-day">
        <small>Ngày làm việc</small>
        <strong id="kioskDate">${E(dateLabel(date))}</strong>
      </div>
      <div class="kiosk-clock">
        <small>Giờ hiện tại</small>
        <strong id="kioskClock">${E(clock(new Date()))}</strong>
      </div>
      <div class="kiosk-live" id="kioskLive" data-state="loading">
        <i aria-hidden="true"></i>
        <span id="kioskLiveText">Đang tải dữ liệu…</span>
      </div>
      <div class="kiosk-actions">
        <label class="kiosk-po-pick">
          <span class="sr-only">Chọn Production Order</span>
          <select id="kioskPoSelect" aria-label="Chọn Production Order"></select>
        </label>
        <button class="kiosk-btn" id="kioskRefresh" type="button">Làm mới</button>
        <button class="kiosk-btn" id="kioskExit" type="button">Thoát</button>
      </div>
    </header>

    <section class="kiosk-kpis" id="kioskKpis" aria-live="polite"></section>

    <div class="kiosk-body kiosk-body-focus">
      <div class="kiosk-col-main">
        <section class="kiosk-panel kiosk-task-panel">
          <div class="kiosk-panel-head">
            <h2>Task đang chạy</h2>
            <span class="kiosk-pager" id="kioskPager"></span>
          </div>
          <div class="kiosk-panel-body" id="kioskTasks"></div>
        </section>
        <section class="kiosk-panel kiosk-chart-panel">
          <div class="kiosk-panel-head">
            <h2>Sản lượng theo giờ</h2>
            <span class="kiosk-panel-note" id="kioskChartNote"></span>
          </div>
          <div class="kiosk-panel-body" id="kioskHourly"></div>
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
        <section class="kiosk-panel kiosk-feed-panel">
          <div class="kiosk-panel-head">
            <h2>Hoạt động vừa xảy ra</h2>
            <span class="kiosk-panel-note" id="kioskFeedNote"></span>
          </div>
          <div class="kiosk-panel-body" id="kioskFeed" aria-live="polite"></div>
        </section>
        <section class="kiosk-panel kiosk-other-panel">
          <div class="kiosk-panel-head"><h2>Biến động PO khác</h2></div>
          <div class="kiosk-panel-body" id="kioskOther"></div>
        </section>
      </div>
    </div>
  </div>`;

    const $=id=>document.getElementById(id);
    const root=()=>$('kioskRoot');
    const alive=()=>{const el=root();return !!el&&el.dataset.kioskDate===date};

    $('kioskExit').onclick=()=>openPage('dashboard',document.querySelector('[data-page="dashboard"]'));

    const setLive=(state,text)=>{const c=$('kioskLive'),l=$('kioskLiveText');if(c)c.dataset.state=state;if(l)l.textContent=text};
    const tickClock=()=>{const el=$('kioskClock');if(el)el.textContent=clock(new Date())};

    // ---- header PO ----------------------------------------------------------
    function paintPo(po,kpis){
      $('kioskPoCode').textContent=po?po.code:'—';
      $('kioskPoProduct').textContent=po&&po.product?po.product:'';
      const box=$('kioskPoProgress');
      if(!po){box.innerHTML='';return}
      const plan=Number(po.planned_quantity||0),done=Number((kpis&&kpis.day_good_qty)||0);
      const p=pct(done,plan);
      box.innerHTML=`<small>Tiến độ hôm nay</small>
        <strong>${N(done)}${plan?` / ${N(plan)}`:''}</strong>
        ${p===null?'':`<i class="kiosk-meter"><u style="width:${Math.min(100,p)}%"></u></i>`}`;
    }

    function paintSelector(options){
      const sel=$('kioskPoSelect');
      if(!sel||sel.dataset.count===String(options.length)&&sel.value===String(S.poId))return;
      sel.innerHTML=options.map(o=>{
        const marks=[];
        if(Number(o.open_sessions||0)>0)marks.push(`${o.open_sessions} đang làm`);
        return `<option value="${o.id}" ${Number(o.id)===Number(S.poId)?'selected':''}>${E(o.code)}${o.product?` · ${E(o.product)}`:''}${marks.length?` — ${E(marks.join(', '))}`:''}</option>`;
      }).join('');
      sel.dataset.count=String(options.length);
      sel.onchange=()=>switchPo(Number(sel.value));
    }

    /** Đổi PO: đổi NGUYÊN KHỐI, không để panel nào còn dữ liệu PO cũ. */
    async function switchPo(poId){
      if(!poId||poId===S.poId)return;
      S.poId=poId;S.tasks=[];S.snapshot=[];S.page=0;
      S.completedHold.clear();S.feed=[];S.seen=new Set();S.latestId=null;
      AppNav.setQuery({po_id:poId});
      $('kioskTasks').innerHTML='<div class="kiosk-empty"><b>Đang tải…</b></div>';
      $('kioskFeed').innerHTML='';
      $('kioskOther').innerHTML='';
      setLive('loading','Đang đổi Production Order…');
      await loadBoard();
      await loadActivity();
    }

    // ---- KPI ---------------------------------------------------------------
    function paintKpis(k){
      const cards=[
        {label:'Sản lượng đạt hôm nay',value:N(k.day_good_qty),tone:''},
        {label:'NG hôm nay',value:N(k.day_defect_qty),tone:Number(k.day_defect_qty)>0?'bad':''},
        {label:'Lỗi sửa được',value:N(k.day_rework_qty),tone:Number(k.day_rework_qty)>0?'warn':''},
        {label:'Session đang mở',value:N(k.open_session_count),tone:''},
        {label:'Người đang làm',value:N(k.active_worker_count),tone:''},
        {label:'Operation của PO',value:N(k.operation_count),tone:''},
      ];
      $('kioskKpis').innerHTML=cards.map(c=>`<article class="kiosk-kpi ${c.tone}"><small>${E(c.label)}</small><strong>${E(c.value)}</strong></article>`).join('');
    }

    // ---- task list + auto paging -------------------------------------------
    // Thứ tự ổn định: đang có người làm trước, rồi theo sản lượng, rồi id. KHÔNG
    // phụ thuộc thứ tự server trả về, để một lần server đổi ORDER BY không làm
    // màn hình nhảy.
    const rank=t=>Number(t.open_session_count||0)>0?0:(t.day_state==='NEEDS_REVIEW'?1:2);
    const orderTasks=list=>[...list].sort((a,b)=>
      rank(a)-rank(b)||Number(b.day_good_qty||0)-Number(a.day_good_qty||0)||Number(a.operation_id)-Number(b.operation_id));

    /** Số hàng task vừa một trang. Trần 16 (bản trước là 12): hàng nay thấp
     * hơn nên ở 1920 một trang chứa được hơn 12 hàng thật -- giữ trần cũ là tự
     * tay bắt màn hình phải lật trang trong khi chỗ trống vẫn còn. */
    const measurePerPage=()=>fitRows($('kioskTasks'),'.kiosk-task',4,16,S.perPage);

    /** Danh sách hiển thị = task active + task vừa hoàn thành còn trong thời gian giữ. */
    function displayList(){
      const now=Date.now();
      for(const [id,hold] of [...S.completedHold]){if(hold.until<=now)S.completedHold.delete(id)}
      const active=orderTasks(S.tasks);
      const activeIds=new Set(active.map(t=>Number(t.operation_id)));
      // Task đang được giữ nối SAU danh sách active, không chen lên đầu: chen
      // lên đầu là tự tay tạo ra cú nhảy mà cả màn này đang tránh.
      const held=[...S.completedHold.values()].filter(h=>!activeIds.has(Number(h.task.operation_id))).map(h=>({...h.task,__justDone:h}));
      return [...active,...held];
    }

    function paintTasks(){
      const box=$('kioskTasks');if(!box)return;
      const list=S.snapshot;
      if(!list.length){
        box.innerHTML=`<div class="kiosk-empty kiosk-empty-done">
          <b>PO này hiện không còn task đang chạy</b>
          <span id="kioskEmptyHint">Xem hoạt động gần nhất bên phải, hoặc chuyển sang PO khác đang có việc.</span>
          <div class="kiosk-empty-actions" id="kioskEmptySuggest"></div></div>`;
        paintEmptySuggestions();
        $('kioskPager').textContent='';
        return;
      }
      const pages=Math.max(1,Math.ceil(list.length/S.perPage));
      if(S.page>=pages)S.page=0;
      const slice=list.slice(S.page*S.perPage,S.page*S.perPage+S.perPage);
      box.innerHTML=`<div class="kiosk-task-list">${slice.map(renderTask).join('')}</div>`;
      $('kioskPager').innerHTML=`<span class="kiosk-page-count">Trang ${S.page+1}/${pages}</span>
        <span class="kiosk-dots">${Array.from({length:pages},(_,i)=>`<i class="${i===S.page?'on':''}"></i>`).join('')}</span>
        <span class="kiosk-page-total">${N(list.length)} task</span>
        ${Date.now()<S.pauseUntil?'<span class="kiosk-paused">Đang tạm dừng lật trang</span>':''}`;
    }

    function renderTask(t){
      const plan=Number(t.planned_quantity||0),done=Number(t.total_good_qty||0);
      const p=pct(done,plan);
      const workers=(t.active_workers||[]).map(w=>w&&w.name).filter(Boolean);
      const just=t.__justDone;
      const state=just?'justdone':String(t.day_state||'').toLowerCase();
      const stateText=just?'Vừa hoàn thành':({RUNNING:'Đang chạy',NEEDS_REVIEW:'Cần xử lý',UPDATED:'Đã cập nhật',IDLE:'Không có người'}[t.day_state]||'—');
      return `<article class="kiosk-task state-${E(state)}" data-op="${E(t.operation_id)}">
        <div class="kiosk-task-main">
          <b>${E(t.operation_name||'—')}</b>
          <small>${E(t.operation_code||'')}</small>
        </div>
        <div class="kiosk-task-state"><em class="kiosk-state ${E(state)}">${E(stateText)}</em>${
          just&&just.actor?`<small>${E(just.actor)}${just.delta?` · ${just.delta>0?'+':''}${N(just.delta)} SP`:''}</small>`:''}</div>
        <div class="kiosk-task-people">${workers.length?E(workers.slice(0,2).join(', ')):'—'}${workers.length>2?` <u>+${workers.length-2}</u>`:''}</div>
        <div class="kiosk-task-qty"><b>${N(done)}</b>${plan?` / ${N(plan)}`:''}
          ${p===null?'':`<i class="kiosk-meter"><u style="width:${Math.min(100,p)}%"></u></i>`}</div>
        <div class="kiosk-task-ng ${Number(t.day_defect_qty)>0?'has':''}">${N(t.day_defect_qty)}</div>
      </article>`;
    }

    function paintEmptySuggestions(){
      const box=$('kioskEmptySuggest');if(!box)return;
      const others=(S.options||[]).filter(o=>Number(o.id)!==Number(S.poId)&&Number(o.open_sessions||0)>0).slice(0,3);
      box.innerHTML=others.length
        ?others.map(o=>`<button class="kiosk-btn" type="button" data-goto="${o.id}">${E(o.code)} · ${o.open_sessions} đang làm</button>`).join('')
        :'<span class="kiosk-empty-note">Hiện không có PO nào đang có session mở.</span>';
      box.querySelectorAll('[data-goto]').forEach(b=>b.onclick=()=>switchPo(Number(b.dataset.goto)));
    }

    // ---- sản lượng theo giờ (chỉ của PO đang xem) --------------------------
    // Cột giờ dựng từ chính session của PO này, không phải của cả xưởng. Cùng
    // một phép cộng với "Dashboard theo ngày", chỉ khác phạm vi.
    const hourOf=v=>{if(!v)return null;const d=new Date(v);if(Number.isNaN(d.getTime()))return null;
      return Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',hour12:false}).format(d))};
    function paintHourly(sessions){
      const box=$('kioskHourly'),note=$('kioskChartNote');if(!box)return;
      const buckets=Array.from({length:24},()=>({good:0,ng:0}));
      let total=0;
      for(const s0 of sessions||[]){
        const h=hourOf(s0.ended_at||s0.report_at||s0.started_at);
        if(h===null||h<0||h>23)continue;
        buckets[h].good+=Number(s0.good_qty||0);buckets[h].ng+=Number(s0.defect_qty||0);
        total+=Number(s0.good_qty||0);
      }
      if(!total){box.innerHTML='<div class="kiosk-empty"><b>Chưa có sản lượng ghi nhận</b><span>Cột giờ hiện khi có session đầu tiên kết thúc.</span></div>';if(note)note.textContent='';return}
      const peak=Math.max(...buckets.map(b=>b.good),1);
      if(note)note.textContent=`Tổng ${N(total)} SP đạt trong ngày`;
      box.innerHTML=`<div class="kiosk-chart-plot">${buckets.map((b,h)=>`
        <div class="kiosk-bar" title="${h}:00 — ${N(b.good)} đạt, ${N(b.ng)} NG">
          <span class="kiosk-bar-value">${b.good?N(b.good):''}</span>
          <i style="height:${Math.round(b.good/peak*100)}%"></i>
          <small>${String(h).padStart(2,'0')}</small>
        </div>`).join('')}</div>`;
    }

    // ---- cần xử lý ngay (chỉ của PO đang xem) ------------------------------
    // Không phát minh thêm luật ngoại lệ nào: unconfirmed_count đến thẳng từ
    // daily_progress, còn hai ngưỡng cục bộ (tỉ lệ NG, session mở quá lâu) luôn
    // in ra con số đã kích hoạt chúng để người đọc tự đánh giá.
    const NG_RATIO_ALERT=0.10, LONG_OPEN_HOURS=10;
    function buildAttention(tasks,sessions){
      const out=[];
      for(const x of tasks||[]){
        if(Number(x.unconfirmed_count||0)>0)
          out.push({sev:0,tag:'Session chưa xác nhận',title:x.operation_name||x.operation_code,
            sub:`${x.operation_code||''} · ${N(x.unconfirmed_count)} session tự đóng chưa xác nhận số liệu`});
        const good=Number(x.day_good_qty||0),ng=Number(x.day_defect_qty||0);
        if(ng>0&&good+ng>0&&ng/(good+ng)>=NG_RATIO_ALERT)
          out.push({sev:1,tag:'Tỉ lệ NG cao',title:x.operation_name||x.operation_code,
            sub:`${x.operation_code||''} · ${N(ng)} NG / ${N(good+ng)} SP (${Math.round(ng/(good+ng)*100)}%)`});
      }
      const now=Date.now();
      for(const s0 of sessions||[]){
        if(String(s0.status||'').toUpperCase()!=='OPEN')continue;
        const started=new Date(s0.started_at).getTime();
        if(Number.isNaN(started))continue;
        const hours=(now-started)/3600000;
        if(hours>=LONG_OPEN_HOURS)
          out.push({sev:1,tag:'Session mở quá lâu',title:s0.employee_name||s0.operation_name||'—',
            sub:`${s0.operation_code||''} · mở ${Math.round(hours)} giờ`});
      }
      return out.sort((a,b)=>a.sev-b.sev);
    }
    function paintAttention(list){
      const box=$('kioskAttention'),count=$('kioskAttentionCount'),foot=$('kioskAttentionFoot');
      if(!box)return;
      // Con số trên nhãn là TỔNG, không phải số dòng vẽ ra -- người xem phải
      // biết ngay quy mô kể cả khi màn chỉ đủ chỗ cho vài dòng đầu.
      if(count)count.textContent=list.length?N(list.length):'Sạch';
      if(foot)foot.textContent='Cảnh báo thiết bị/kiosk và ngoại lệ chưa xử lý chưa có nguồn dữ liệu ở màn này.';
      if(!list.length){
        box.innerHTML='<div class="kiosk-empty"><b>Không có điểm cần xử lý</b><span>Mọi Operation của PO này đang bình thường.</span></div>';
        return;
      }
      const max=density(root(),'--kd-attn-rows',3);
      const draw=n=>{
        const rest=list.length-n;
        box.innerHTML=list.slice(0,n).map(x=>
          `<article class="kiosk-attn sev-${x.sev}"><em>${E(x.tag)}</em><b>${E(x.title)}</b><small>${E(x.sub)}</small></article>`).join('')
          +(rest>0?`<p class="kiosk-attn-more">+${N(rest)} điểm cần xử lý khác</p>`:'');
      };
      const drew=fitDown(box,draw,Math.min(max,list.length),1);
      budgetChanged('attn',drew);
    }

    /** Hai panel thông báo cao theo NỘI DUNG, nên mỗi lần số hàng của chúng đổi
     * là chiều cao còn lại cho dòng hoạt động đổi theo. Bắt được ca này là điều
     * kiện để "không có hàng nào bị cắt" còn đúng sau lần tải thứ hai:
     * lần đầu `#kioskOther` rỗng nên panel đó chỉ cao bằng tiêu đề, dòng hoạt
     * động đo được 5 hàng; ngay sau đó biến động PO khác về, panel cao thêm
     * 80px và 2 trong 5 hàng vừa đo rơi ra ngoài khung.
     */
    function budgetChanged(key,rows){
      if(S.budget[key]===rows)return;
      S.budget[key]=rows;
      S.feedShow=0;   // buộc paintFeed đo lại trên khung mới
    }

    // ---- activity feed ------------------------------------------------------
    function paintFeed(){
      const box=$('kioskFeed');if(!box)return;
      if(!S.feed.length){
        S.feedShow=0;
        box.innerHTML='<div class="kiosk-empty"><b>Chưa có hoạt động</b><span>Sự kiện hiện ra ngay khi xưởng thao tác.</span></div>';
        return;
      }
      const now=Date.now();
      const eventHtml=ev=>{
        const {action,impact}=phraseOf(ev);
        const fresh=ev.__at&&now-ev.__at<NEW_EVENT_HIGHLIGHT_MS;
        return `<article class="kiosk-event tone-${E(TONE[ev.event_type]||'neutral')}${fresh?' is-new':''}" data-event="${E(ev.id)}">
          <time datetime="${E(ev.occurred_at||'')}"><b>${E(hhmm(ev.occurred_at))}</b><small>${E(relative(ev.occurred_at))}</small></time>
          <p><b class="kiosk-actor ${ev.actor_kind==='SYSTEM'?'is-system':''}">${E(actorOf(ev))}</b>
            <span>${E(action)}</span>
            ${objectOf(ev)?`<i>${E(objectOf(ev))}</i>`:''}
            ${impact?`<u>→ ${E(impact)}</u>`:''}</p>
        </article>`;
      };
      const max=density(root(),'--kd-feed-max',6);
      const draw=n=>{box.innerHTML=S.feed.slice(0,Math.max(1,n)).map(eventHtml).join('')};
      // Số hàng đã biết từ lần trước thì vẽ thẳng; chỉ đo lại khi chưa biết
      // (lần đầu, hoặc sau khi đổi cỡ cửa sổ). Nhịp 1 giây vì thế chỉ vẽ một
      // lần, không phải đo lại cả panel mỗi giây.
      //
      // Sàn của vòng vẽ là 1: thà hiện ít sự kiện hơn còn hơn hiện một dòng bị
      // cắt ngang thân. Sàn NGHIỆP VỤ ("4-6 sự kiện gần nhất") là một ràng buộc
      // của BỐ CỤC, không phải của vòng vẽ -- nó được canh ở
      // tests/e2e/kiosk-density-contract.spec.js, nơi bố cục hụt ngân sách sẽ
      // báo đỏ, thay vì âm thầm vỡ một hàng trên màn hình xưởng.
      if(S.feedShow){
        draw(S.feedShow);
        // Hàng sự kiện KHÔNG cao cố định: "vừa xong" thành "2 phút trước" là
        // câu dài thêm, và một câu dài thêm có thể xuống dòng. Nên số hàng đã
        // đo vẫn phải được kiểm lại mỗi lần vẽ -- chỉ MỘT phép đo, và chỉ khi
        // hàng cuối thật sự rơi ra ngoài mới vẽ lại.
        const b=box.getBoundingClientRect(),last=box.lastElementChild;
        if(last&&last.getBoundingClientRect().bottom>b.bottom+1)
          S.feedShow=fitDown(box,draw,Math.max(1,S.feedShow-1),1);
      }else S.feedShow=fitDown(box,draw,Math.min(max,S.feed.length),1);
      const shown=Math.min(S.feedShow,S.feed.length);
      $('kioskFeedNote').textContent=`${shown} sự kiện gần nhất · ${hhmmss(new Date())}`;
    }

    function paintOther(events){
      const box=$('kioskOther');if(!box)return;
      if(!events.length){box.innerHTML='<div class="kiosk-empty"><b>Không có biến động</b><span>Các PO khác chưa có thay đổi mới.</span></div>';return}
      const rowHtml=ev=>{
        const {action,impact}=phraseOf(ev);
        return `<article class="kiosk-other-row tone-${E(TONE[ev.event_type]||'neutral')}">
          <div><b>${E(hhmm(ev.occurred_at))}</b> · <span class="kiosk-other-po">${E(ev.po_code||'—')}</span></div>
          <p>${E(actorOf(ev))} ${E(action)}${objectOf(ev)?` · ${E(objectOf(ev))}`:''}${impact?` → ${E(impact)}`:''}</p>
          <button class="kiosk-btn kiosk-btn-sm" type="button" data-view-po="${E(ev.po_id)}">Xem PO</button>
        </article>`;
      };
      const max=Math.min(density(root(),'--kd-other-rows',2),events.length);
      budgetChanged('other',fitDown(box,n=>{box.innerHTML=events.slice(0,n).map(rowHtml).join('')},max,1));
      box.querySelectorAll('[data-view-po]').forEach(b=>b.onclick=()=>switchPo(Number(b.dataset.viewPo)));
    }

    // ---- tải dữ liệu --------------------------------------------------------
    async function loadBoard(){
      try{
        const q=new URLSearchParams({date});
        if(S.poId)q.set('po_id',String(S.poId));
        const data=await api(`/api/kiosk-board?${q.toString()}`);
        if(!alive())return;
        S.options=data.po_options||[];
        if(!data.production_order){
          $('kioskTasks').innerHTML='<div class="kiosk-empty"><b>Chưa có Production Order nào đang chạy</b><span>Màn hình sẽ hiện ngay khi có PO được Start.</span></div>';
          setLive('live','Trực tiếp · chưa có PO');
          return;
        }
        const before=new Map(S.tasks.map(t=>[Number(t.operation_id),t]));
        S.po=data.production_order;
        if(!S.poId){S.poId=Number(S.po.id);AppNav.setQuery({po_id:S.poId})}
        S.tasks=data.tasks||[];
        markCompletions(before,S.tasks);
        paintPo(S.po,data.kpis||{});
        paintSelector(S.options);
        paintKpis(data.kpis||{});
        paintHourly(data.sessions||[]);
        S.attention=buildAttention(S.tasks,data.sessions||[]);
        paintAttention(S.attention);
        reconcilePages();
        S.lastOk=new Date();
        setLive('live',`Trực tiếp · cập nhật ${clock(S.lastOk)}`);
      }catch(e){
        if(!alive())return;
        setLive('stale',S.lastOk?`Mất kết nối · số liệu lúc ${clock(S.lastOk)}`:`Không tải được dữ liệu · ${e.message||e}`);
      }
    }

    /** Task rời khỏi danh sách active -> giữ lại vài giây với nhãn "Vừa hoàn thành". */
    function markCompletions(before,now){
      if(!before.size)return;
      const nowIds=new Set(now.map(t=>Number(t.operation_id)));
      for(const [id,task] of before){
        const still=now.find(t=>Number(t.operation_id)===id);
        const finished=!nowIds.has(id)||(still&&String(still.operation_status||'').toUpperCase()==='COMPLETED'&&String(task.operation_status||'').toUpperCase()!=='COMPLETED');
        if(!finished)continue;
        const source=still||task;
        // Người vừa cập nhật + delta lấy từ chính dòng sự kiện, không đoán.
        const ev=[...S.feed].reverse().find(x=>Number(x.operation_id)===id&&x.actor_kind==='PERSON');
        const hold={task:source,until:Date.now()+COMPLETION_HOLD_MS,
          actor:ev?ev.actor_name:'',delta:ev&&ev.quantity_delta!=null?Number(ev.quantity_delta):0};
        S.completedHold.set(id,hold);
        // Nếu task đang NẰM TRÊN MÀN, đổi nhãn NGAY TẠI CHỖ của nó. Không chờ
        // ranh giới trang: chờ thì người xem thấy nó lặng lẽ biến mất ở lần lật
        // sau, đúng cái cảm giác "task bốc hơi" mà màn này sinh ra để xoá bỏ.
        // Đổi tại chỗ nên hàng không đổi vị trí -- vừa thấy rõ, vừa không xô
        // lệch trang đang đọc.
        const at=S.snapshot.findIndex(t=>Number(t.operation_id)===id);
        if(at>=0)S.snapshot[at]={...source,__justDone:hold};
      }
      if([...before.keys()].some(id=>S.completedHold.has(id)))paintTasks();
    }

    async function loadActivity(){
      if(!S.poId)return;
      try{
        const q=new URLSearchParams({po_id:String(S.poId)});
        if(S.latestId)q.set('since_id',String(S.latestId));
        const data=await api(`/api/kiosk-board/activity?${q.toString()}`);
        if(!alive())return;
        let added=false;
        for(const ev of data.events||[]){
          if(S.seen.has(ev.id))continue;      // khử trùng lặp theo id ổn định
          S.seen.add(ev.id);ev.__at=Date.now();
          S.feed.unshift(ev);added=true;
        }
        if(S.feed.length>FEED_MAX)S.feed.length=FEED_MAX;
        if(data.latest_id)S.latestId=data.latest_id;
        // "Biến động PO khác" TRƯỚC "Hoạt động vừa xảy ra": panel kia cao theo
        // nội dung, panel này là panel co giãn duy nhất của cột. Vẽ panel co
        // giãn sau cùng thì nó đo trên khung đã chốt, không phải khung sắp đổi.
        if((data.other_events||[]).length||!$('kioskOther').children.length){
          S.otherFeed=[...(data.other_events||[]).reverse(),...(S.otherFeed||[])]
            .filter((e,i,a)=>a.findIndex(x=>x.id===e.id)===i).slice(0,OTHER_MAX);
          paintOther(S.otherFeed||[]);
        }
        if(added||!$('kioskFeed').children.length||!S.feedShow)paintFeed();
      }catch(_e){/* feed hỏng không được làm sập cả màn hình */}
    }

    // ---- vòng lật trang -----------------------------------------------------
    // Snapshot chỉ được thay ở RANH GIỚI trang. Dữ liệu về giữa chừng nằm chờ
    // trong S.tasks, không đụng vào thứ người ta đang đọc.
    function reconcilePages(){
      if(!S.snapshot.length){S.snapshot=displayList();S.perPage=measurePerPage();paintTasks();S.perPage=measurePerPage();paintTasks();}
    }
    function advancePage(){
      if(Date.now()<S.pauseUntil)return;
      const list=displayList();
      const pages=Math.max(1,Math.ceil((S.snapshot.length||list.length)/S.perPage));
      if(S.page+1>=pages){S.snapshot=list;S.page=0}   // hết vòng -> nạp dữ liệu mới
      else S.page+=1;
      paintTasks();
    }

    const holdPaging=()=>{S.pauseUntil=Date.now()+INTERACT_PAUSE_MS;paintTasks()};
    ['pointerenter','pointerdown','touchstart'].forEach(evt=>
      $('kioskTasks').addEventListener(evt,holdPaging,{passive:true}));

    $('kioskRefresh').onclick=()=>{setLive('loading','Đang làm mới…');loadBoard();loadActivity()};

    // Tab ẩn thì giãn nhịp; quay lại thì làm mới ngay -- người vừa nhìn lại màn
    // hình không nên thấy số liệu của mười phút trước.
    document.addEventListener('visibilitychange',()=>{
      if(!alive())return;
      if(!document.hidden){loadBoard();loadActivity()}
    });
    // Đổi cỡ cửa sổ là đổi bậc mật độ (media query) -- cả hai panel co giãn
    // phải đo lại, không chỉ danh sách task.
    window.addEventListener('resize',()=>{
      if(!alive())return;
      S.perPage=measurePerPage();paintTasks();
      if(S.attention)paintAttention(S.attention);
      paintOther(S.otherFeed||[]);
      S.feedShow=0;if(S.feed.length)paintFeed();
    });

    await loadBoard();
    await loadActivity();

    // Hai mối nối cho test. Hành vi cần kiểm ở đây phụ thuộc THỜI GIAN (lật
    // trang mỗi 10s, giữ task vừa xong 8s); chờ đồng hồ thật trong e2e vừa
    // chậm vừa là nguồn flaky. Chúng chỉ GỌI LẠI đúng hàm mà timer gọi, không
    // có nhánh logic riêng -- nên không có đường nào để test xanh trong khi
    // màn hình thật sai.
    window.__kioskAdvance=()=>advancePage();
    window.__kioskReload=()=>loadBoard();

    let ms=0;
    dashboardTimer=setInterval(()=>{
      if(!alive()){clearInterval(dashboardTimer);dashboardTimer=null;return}
      tickClock();
      ms+=1000;
      const factor=document.hidden?HIDDEN_FACTOR:1;
      if(ms%(ACTIVITY_MS*factor)===0)loadActivity();
      if(ms%(BOARD_MS*factor)===0)loadBoard();
      if(ms%PAGE_MS===0&&!document.hidden)advancePage();
      if(ms%1000===0&&S.feed.length)paintFeed();
    },1000);
  }

  window.renderDailyDashboardKiosk=renderDailyDashboardKiosk;
  window.registerPage(PAGE_ID,renderDailyDashboardKiosk);
})();
