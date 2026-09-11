// MESFlow V71 UI foundation. Small, framework-free primitives shared by the
// operational screens; screen business logic remains in each page module.
const MFUI=(()=>{
  const escHtml=value=>window.esc?window.esc(value):String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const labels={
    OPEN:'Đang mở',ACKNOWLEDGED:'Đã tiếp nhận',RESOLVED:'Đã xử lý',MANUAL_IGNORED:'Đã bỏ qua',AUTO_IGNORED:'Tự bỏ qua',
    RUNNING:'Đang chạy',COMPLETED:'Hoàn tất',CLOSED:'Đã đóng',HEALTHY:'Ổn định',DEGRADED:'Suy giảm',DOWN:'Gián đoạn',UNKNOWN:'Chưa rõ',
    PASS:'Đạt',FAIL:'Không đạt',FAILED:'Không đạt',BLOCKED:'Bị chặn',SUCCESS:'Thành công',ONLINE:'Trực tuyến',OFFLINE:'Ngoại tuyến'
  };
  const tone=status=>{
    status=String(status||'UNKNOWN').toUpperCase();
    if(['HEALTHY','PASS','SUCCESS','COMPLETED','CLOSED','RESOLVED','ONLINE'].includes(status))return 'success';
    if(['DOWN','FAIL','FAILED','CRITICAL','ERROR','CANCELLED'].includes(status))return 'danger';
    // RUNNING/OPEN are active-in-progress, not a problem state -- give them
    // their own "info" (blue) identity instead of sharing amber with actual
    // attention-needed states (DEGRADED/BLOCKED/ACKNOWLEDGED/WARNING), so a
    // scan of the page can tell "still going" apart from "needs a look".
    if(['RUNNING','OPEN'].includes(status))return 'info';
    if(['DEGRADED','WARNING','BLOCKED','ACKNOWLEDGED'].includes(status))return 'warning';
    return 'neutral';
  };
  const statusBadge=(status,label='')=>`<span class="ui-status ui-status-${tone(status)}"><span aria-hidden="true" class="ui-status-mark"></span>${escHtml(label||labels[String(status||'').toUpperCase()]||status||'Chưa rõ')}</span>`;
  const pageHeader=({eyebrow='',title='',description='',actions=''})=>`<header class="ui-page-header"><div>${eyebrow?`<small class="ui-eyebrow">${escHtml(eyebrow)}</small>`:''}<h2>${escHtml(title)}</h2>${description?`<p>${escHtml(description)}</p>`:''}</div>${actions?`<div class="ui-page-actions">${actions}</div>`:''}</header>`;
  const pageShell=({id='',eyebrow='',title='',description='',actions='',toolbar='',content=''})=>`<div class="ui-page-shell"${id?` id="${escHtml(id)}"`:''}>${pageHeader({eyebrow,title,description,actions})}${toolbar?`<div class="ui-toolbar">${toolbar}</div>`:''}<div class="ui-page-content">${content}</div></div>`;
  // clearLabel/actions added for the UI Template Standard's Golden Reference
  // pages: Production Order's toolbar needs BOTH a filter-reset action
  // ("Đặt lại") and an unrelated utility action ("Làm mới" -- reload from
  // server, not a filter operation). Every prior filterBar() caller only
  // ever needed the one built-in "Xóa bộ lọc" clear button, so this stays
  // backward compatible: omitting clearLabel/actions reproduces the exact
  // markup those callers already depend on.
  // Trên máy điện thoại, bộ lọc GẬP LẠI mặc định.
  //
  // Lý do đo được: Trung tâm ngoại lệ có 8 trường lọc; ở 390px chúng chiếm
  // 509px và đẩy ngoại lệ đầu tiên xuống 740px -- gần một màn hình rưỡi cuộn
  // trước khi thấy nội dung chính. Không cách sắp xếp nào cứu được: 8 trường
  // không vừa một màn hình dọc. Thứ duy nhất còn lại là đừng hiện chúng cho
  // tới khi người dùng cần.
  //
  // Dùng <details>/<summary> THẬT chứ không phải div giả: bàn phím, trình đọc
  // màn hình và cả nút tìm-trong-trang của trình duyệt đều đã hiểu nó sẵn.
  // Thuộc tính `open` nằm sẵn trong markup, nên nếu JS chết thì desktop vẫn
  // thấy đủ bộ lọc -- hỏng về phía an toàn.
  const filterBar=({content='',count='',activeCount=0,clearId='',clearLabel='Xóa bộ lọc',actions=''})=>`<div class="ui-filter-bar" role="search"><details class="ui-filter-disclosure" open><summary class="ui-filter-summary"><span>Bộ lọc</span>${activeCount?`<span class="ui-filter-active">${Number(activeCount)}</span>`:''}</summary><div class="ui-filter-controls">${content}</div></details><div class="ui-filter-meta">${activeCount?`<span class="ui-filter-active">Bộ lọc (${Number(activeCount)})</span>`:''}${clearId?`<button class="btn tertiary" id="${escHtml(clearId)}" type="button">${escHtml(clearLabel)}</button>`:''}${count!==''?`<span aria-live="polite">${escHtml(count)} kết quả</span>`:''}${actions?`<div class="ui-filter-bar-actions">${actions}</div>`:''}</div></div>`;
  // ContentPanel: the one shared "PanelHeader (title/meta left, actions
  // right) + PanelBody" wrapper for a Golden Reference page's actual data
  // region -- a table, a card list, or a standard empty/loading state. Only
  // PanelBody's content differs by archetype (DataTable for List pages,
  // workflow cards for Session Exceptions); the panel itself is identical
  // markup/CSS for every page that adopts it.
  const contentPanel=({id='',title='',description='',actions='',body=''})=>`<section class="content-panel"${id?` id="${escHtml(id)}"`:''}>${(title||description||actions)?`<div class="content-panel-head"><div>${title?`<h3>${escHtml(title)}</h3>`:''}${description?`<p>${escHtml(description)}</p>`:''}</div>${actions?`<div class="content-panel-actions">${actions}</div>`:''}</div>`:''}<div class="content-panel-body">${body}</div></section>`;
  // StatsRow: the plain (unbordered-child) counts strip used directly under
  // a PageHeader -- e.g. Production Order's "3 lệnh đang hiển thị · 0 đang
  // lập kế hoạch · ...". items: [[label, value], ...].
  const statsRow=(items,{id=''}={})=>`<div class="stats-row"${id?` id="${escHtml(id)}"`:''} aria-live="polite">${items.map(([label,value])=>`<span><b>${escHtml(value)}</b> ${escHtml(label)}</span>`).join('')}</div>`;
  const loadingState=(message='Đang tải dữ liệu…')=>`<div class="ui-state ui-loading" aria-busy="true"><span class="ui-spinner" aria-hidden="true"></span><p>${escHtml(message)}</p></div>`;
  const emptyState=(title='Không có dữ liệu',message='')=>`<div class="ui-state ui-empty"><b>${escHtml(title)}</b>${message?`<p>${escHtml(message)}</p>`:''}</div>`;
  const errorState=(message='Không thể tải dữ liệu.',retryId='')=>`<div class="ui-state ui-error" role="alert"><b>Đã có lỗi</b><p>${escHtml(message)}</p>${retryId?`<button class="btn" id="${escHtml(retryId)}" type="button">Thử lại</button>`:''}</div>`;

  // --- Nhận dạng Operation: TÊN là chữ chính, MÃ là chữ phụ --------------
  //
  // Người vận hành tìm việc theo TÊN công đoạn ("Chấn bước 1"), không theo mã
  // ("111-THAN-THUNG-R-01"); mã chỉ dùng để đối chiếu SAU khi đã tìm thấy.
  // Trước đây mỗi màn tự ghép chuỗi `code · name` vào MỘT thẻ <b>, nên dãy ký
  // tự vô nghĩa đứng trước còn tên thật bị đẩy ra sau và cắt cụt ở cột hẹp --
  // và vì mỗi màn ghép một kiểu nên sửa chỗ này không làm chỗ kia đúng theo.
  // Một hàm dựng duy nhất để Dashboard không còn hai code path cho cùng một
  // khối chữ.
  //
  // Quy tắc fallback: thiếu tên thì MÃ lên làm chữ chính (không bao giờ để
  // trống), và khi đó KHÔNG lặp lại mã ở dòng dưới -- lặp chính nó thì dòng
  // phụ chỉ tốn chiều cao mà không thêm thông tin nào.
  const opIdentityText=({name='',code=''}={})=>{
    const n=String(name??'').trim(),c=String(code??'').trim();
    return [n,c].filter(Boolean).join(' · ')||'—';
  };
  // compact: biến thể cho chip timeline -- cùng thứ bậc (tên nặng hơn chữ
  // phụ), chỉ nhỏ hơn. Định nghĩa Ở ĐÂY một lần chứ không để mỗi màn tự hạ cỡ
  // chữ bằng luật riêng: đó đúng là kiểu lệch âm thầm mà primitive dùng chung
  // sinh ra để dẹp.
  // meta: chữ thuần, hàm này tự escape. metaHtml: đã là HTML do người gọi
  // dựng sẵn (chip timeline cần các span .qty-* tô màu sản lượng) -- người
  // gọi chịu trách nhiệm escape, đúng quy ước của mọi tham số `actions`/
  // `content` khác trong file này.
  // showCode=false: chip timeline không in lại mã trên bề mặt (khối tổng hợp
  // của nhân viên ngay phía trên đã mang mã, và chip chỉ rộng vài chục pixel)
  // -- nhưng `code` VẪN phải truyền vào, vì nó là nguồn fallback khi thiếu
  // tên và là phần không thể thiếu của title=.
  const opIdentity=({name='',code='',meta='',metaHtml='',compact=false,tooltip='',className='',showCode=true}={})=>{
    const n=String(name??'').trim(),c=String(code??'').trim();
    const primary=n||c||'—';
    const secondary=n&&showCode?c:'';
    const hint=String(tooltip||'').trim()||opIdentityText({name,code});
    const metaBody=metaHtml||(meta?escHtml(meta):'');
    const cls=['op-identity',compact?'compact':'',String(className||'').trim()].filter(Boolean).join(' ');
    return `<span class="${escHtml(cls)}" title="${escHtml(hint)}">`+
      `<b class="row-title">${escHtml(primary)}</b>`+
      (secondary?`<small class="row-code">${escHtml(secondary)}</small>`:'')+
      (metaBody?`<small class="op-identity-meta">${metaBody}</small>`:'')+
    '</span>';
  };

  // --- Ba trạng thái của một con số sản lượng ----------------------------
  //
  // (1) CHƯA nhập / chưa chốt  -> "—"
  // (2) ĐÃ chốt và bằng 0      -> "0"
  // (3) ĐÃ chốt và lớn hơn 0   -> số thật
  //
  // Trạng thái (1) và (2) trước đây in ra y hệt nhau ("Đạt 0 · NG 0"): các
  // cột số lượng trong CSDL là NOT NULL DEFAULT 0, nên `Number(x||0)` ở tầng
  // hiển thị biến "chưa biết" thành "biết và bằng 0". Quản đốc đọc "NG 0"
  // của một ca đang chạy thành "đã kiểm, không có hàng lỗi", trong khi thật
  // ra chưa ai nhập gì.
  //
  // Vì vậy `recorded` là THAM SỐ RIÊNG, tách khỏi con số: người gọi phải lấy
  // nó từ nguồn sự thật của mình và truyền vào, không được suy ra từ chính
  // giá trị. Đoán "cả ba đều 0 nghĩa là chưa nhập" -- cách bản trước làm --
  // sai đúng ở ca ngược lại: một ca chốt thật 0/0 bị giấu mất thành "—".
  //
  // Hàm này CỐ Ý không biết gì về hình dạng bản ghi của MESFlow: quyết định
  // "đã chốt hay chưa" là luật nghiệp vụ, sống ở app.js (mfOutputRecorded).
  const QTY_UNKNOWN='—';
  const qtyValue=(value,recorded=true)=>{
    if(!recorded)return QTY_UNKNOWN;
    if(value===null||value===undefined||value==='')return QTY_UNKNOWN;
    const n=Number(value);
    return Number.isFinite(n)?n.toLocaleString('vi-VN'):QTY_UNKNOWN;
  };
  // Đạt/NG luôn hiện cả hai khi đã chốt -- "Đạt 32" trơ trọi không nói được
  // NG vắng mặt vì bằng 0 hay vì chưa biết. Sửa/Phế chỉ hiện khi > 0: chúng
  // là ngoại lệ của sản xuất, không phải cặp chỉ số đọc hằng ngày.
  // plain=true trả chữ trần cho title= (thuộc tính này in thẳng markup ra
  // thành chữ nếu nhận HTML).
  const qtyLine=({good,defect,rework,scrap,recorded=true,plain=false}={})=>{
    if(!recorded){
      const text=`Đạt ${QTY_UNKNOWN} · NG ${QTY_UNKNOWN}`;
      return plain?text:`<span class="qty-empty">${text}</span>`;
    }
    const num=v=>Number(v||0);
    const parts=[['qty-good',`Đạt ${qtyValue(good,true)}`],['qty-ng',`NG ${qtyValue(defect,true)}`]];
    if(num(rework)>0)parts.push(['qty-fix',`Sửa ${qtyValue(rework,true)}`]);
    if(num(scrap)>0)parts.push(['qty-scrap',`Phế ${qtyValue(scrap,true)}`]);
    return plain
      ? parts.map(([,text])=>text).join(' · ')
      : parts.map(([cls,text])=>`<span class="${cls}">${escHtml(text)}</span>`).join(' · ');
  };

  let overlay=null;
  let origin=null;
  let popping=false;
  const destroy=({restoreHistory=true}={})=>{
    if(!overlay)return;
    const node=overlay; overlay=null;
    node.remove(); document.body.classList.remove('ui-overlay-open','drawer-open');
    if(origin&&origin.isConnected)origin.focus(); origin=null;
    if(restoreHistory&&!popping&&history.state?.mfOverlay)history.back();
  };
  const pushOverlayState=(id,urlParam,urlValue)=>{
    const url=new URL(location.href);
    // A cold deep link may already carry the overlay parameter. Establish a
    // clean parent entry first so closing/Back never leaves a stale drawer URL.
    if(urlParam&&url.searchParams.has(urlParam)){
      const parent=new URL(url);parent.searchParams.delete(urlParam);
      history.replaceState({...history.state,mfOverlay:null},'',parent);
    }
    if(urlParam&&urlValue!=null)url.searchParams.set(urlParam,String(urlValue));
    history.pushState({...history.state,mfOverlay:id},'',url);
  };
  const bindOverlay=(root,close,{historyId,urlParam,urlValue}={})=>{
    origin=document.activeElement;
    overlay=root; document.body.classList.add('ui-overlay-open');
    root.querySelector('[data-ui-close]')?.addEventListener('click',close);
    root.addEventListener('click',e=>{if(e.target.matches('[data-ui-backdrop]'))close()});
    if(historyId)pushOverlayState(historyId,urlParam,urlValue);
    requestAnimationFrame(()=>root.querySelector('[data-ui-initial-focus],h2,button')?.focus());
  };
  const openDrawer=({id='detail',size='LG',title='Chi tiết',subtitle='',status='',content='',footer='',urlParam='',urlValue=null,onClose=null}={})=>{
    if(overlay){
      const parent=new URL(location.href);['session','kiosk','exception'].forEach(key=>parent.searchParams.delete(key));
      history.replaceState({...history.state,mfOverlay:null},'',parent);
      destroy({restoreHistory:false});
    }
    const root=document.createElement('div'); root.className='ui-drawer-root'; root.dataset.uiOverlay=id;
    root.innerHTML=`<button class="ui-overlay-backdrop" data-ui-backdrop type="button" aria-label="Đóng"></button><aside class="ui-drawer ui-drawer-${escHtml(size.toLowerCase())}" role="dialog" aria-modal="true" aria-labelledby="${escHtml(id)}Title"><header class="ui-drawer-header"><div><h2 tabindex="-1" id="${escHtml(id)}Title">${escHtml(title)}</h2>${subtitle?`<p>${escHtml(subtitle)}</p>`:''}<div class="ui-drawer-status">${status}</div></div><button class="ui-icon-button" data-ui-close type="button" aria-label="Đóng chi tiết">×</button></header><div class="ui-drawer-body">${content||loadingState()}</div><footer class="ui-drawer-footer"${footer?'':' hidden'}>${footer}</footer></aside>`;
    document.body.appendChild(root);
    const close=()=>{destroy();if(onClose)onClose()};
    bindOverlay(root,close,{historyId:id,urlParam,urlValue});
    return {root,panel:root.querySelector('.ui-drawer'),body:root.querySelector('.ui-drawer-body'),header:root.querySelector('.ui-drawer-header'),footer:root.querySelector('.ui-drawer-footer'),close};
  };
  const closeDrawer=()=>destroy();
  const openModal=({id='modal',title='Xác nhận',content='',footer='',size='MD',onClose=null}={})=>{
    if(overlay)destroy({restoreHistory:false});
    const root=document.createElement('div'); root.className='ui-modal-root'; root.dataset.uiOverlay=id;
    root.innerHTML=`<button class="ui-overlay-backdrop" data-ui-backdrop type="button" aria-label="Đóng"></button><section class="ui-modal ui-modal-${escHtml(size.toLowerCase())}" role="dialog" aria-modal="true" aria-labelledby="${escHtml(id)}Title"><header><h2 tabindex="-1" id="${escHtml(id)}Title">${escHtml(title)}</h2><button class="ui-icon-button" data-ui-close type="button" aria-label="Đóng">×</button></header><div class="ui-modal-body">${content}</div><footer>${footer}</footer></section>`;
    document.body.appendChild(root); const close=()=>{destroy({restoreHistory:false});if(onClose)onClose()}; bindOverlay(root,close);
    return {root,body:root.querySelector('.ui-modal-body'),footer:root.querySelector('footer'),close};
  };
  const confirmDialog=({title='Xác nhận thao tác',message='',confirmLabel='Xác nhận',danger=false,reason=false}={})=>new Promise(resolve=>{
    const modal=openModal({id:'confirmDialog',title,content:`<p>${escHtml(message)}</p>${reason?'<label class="ui-field"><span>Lý do</span><textarea id="uiConfirmReason" rows="3"></textarea></label>':''}`,footer:`<button class="btn" id="uiConfirmCancel" type="button">Hủy</button><button class="btn ${danger?'danger':'primary'}" id="uiConfirmSubmit" type="button">${escHtml(confirmLabel)}</button>`,onClose:()=>resolve(null)});
    modal.root.querySelector('#uiConfirmCancel').onclick=()=>{modal.close();resolve(null)};
    modal.root.querySelector('#uiConfirmSubmit').onclick=()=>{const value=reason?(modal.root.querySelector('#uiConfirmReason').value||'').trim():true;modal.close();resolve(value)};
  });
  // Row menu: một menu "..." của dòng bảng, render THẲNG VÀO body ở position
  // fixed. Lý do: mọi bảng ở đây nằm trong .table-wrap{overflow:auto}, nên một
  // popover đặt absolute bên trong ô sẽ vừa bị cắt vừa làm scrollHeight của
  // wrapper phình ra -- đo được trên PO list: 2229px so với 2104px, tức là mở
  // menu thì mọc thêm thanh cuộn dọc. Fixed + portal ra body thì không có
  // ancestor nào cắt được, và chiều cao dòng không đổi.
  let rowMenuState=null;
  // Đặt menu ngay dưới trigger, lật lên trên khi không đủ chỗ, kẹp trong
  // viewport theo chiều ngang.
  const placeRowMenu=(el,trigger)=>{
    const r=trigger.getBoundingClientRect(),h=el.offsetHeight,w=el.offsetWidth;
    const top=(innerHeight-r.bottom>=h+8)?r.bottom+4:Math.max(8,r.top-h-4);
    el.style.top=`${Math.round(top)}px`;
    el.style.left=`${Math.round(Math.min(Math.max(8,r.right-w),innerWidth-w-8))}px`;
  };
  // Cuộn thì BÁM THEO trigger chứ không đóng. Bản trước đóng-khi-cuộn kèm một
  // cửa sổ bỏ qua 250ms, và cửa sổ đó là một con số đoán: cú cuộn đưa dòng
  // cuối vào tầm nhìn có thể đọng lại lâu hơn thế trên bảng dài, làm menu tự
  // đóng ngay sau khi mở (đã thấy flaky ở 1920 và 1366). Bám theo thì không
  // còn cuộc đua nào để thua; chỉ đóng khi chính trigger rời khỏi tầm nhìn.
  const followRowMenu=()=>{
    if(!rowMenuState)return;
    const r=rowMenuState.trigger.getBoundingClientRect();
    if(r.bottom<0||r.top>innerHeight){closeRowMenu();return}
    placeRowMenu(rowMenuState.el,rowMenuState.trigger);
  };
  const closeRowMenu=()=>{
    if(!rowMenuState)return;
    rowMenuState.el.remove();
    rowMenuState.trigger.setAttribute('aria-expanded','false');
    rowMenuState=null;
    removeEventListener('keydown',onRowMenuKey,true);
    removeEventListener('click',onRowMenuOutside,true);
    removeEventListener('scroll',followRowMenu,true);
    removeEventListener('resize',followRowMenu);
  };
  function onRowMenuKey(e){
    if(!rowMenuState)return;
    if(e.key==='Escape'){e.preventDefault();const t=rowMenuState.trigger;closeRowMenu();t.focus()}
  }
  function onRowMenuOutside(e){
    if(!rowMenuState)return;
    if(!rowMenuState.el.contains(e.target)&&!rowMenuState.trigger.contains(e.target))closeRowMenu();
  }
  const rowMenu=(trigger,items)=>{
    const reopening=rowMenuState&&rowMenuState.trigger===trigger;
    closeRowMenu();
    if(reopening)return;
    const el=document.createElement('div');
    el.className='ui-row-menu';el.setAttribute('role','menu');
    el.innerHTML=items.map((it,i)=>`<button type="button" role="menuitem" data-row-menu-index="${i}"${it.danger?' class="danger-text"':''}>${escHtml(it.label)}</button>`).join('');
    document.body.appendChild(el);
    placeRowMenu(el,trigger);
    trigger.setAttribute('aria-expanded','true');
    el.querySelectorAll('[data-row-menu-index]').forEach(b=>b.onclick=()=>{
      const item=items[Number(b.dataset.rowMenuIndex)];closeRowMenu();if(item&&item.onSelect)item.onSelect();
    });
    rowMenuState={el,trigger};
    // preventScroll: menu đã ở fixed đúng vị trí rồi; để trình duyệt tự cuộn
    // tới nó sẽ phát ra sự kiện scroll, và chính listener đóng-khi-cuộn bên
    // dưới sẽ đóng ngay menu vừa mở -- chỉ lộ ra ở những dòng gần đáy.
    el.querySelector('button')?.focus({preventScroll:true});
    addEventListener('keydown',onRowMenuKey,true);
    addEventListener('scroll',followRowMenu,true);
    addEventListener('resize',followRowMenu);
    // Ở tick sau: chính cú click mở menu vẫn đang lan, và nếu gắn ngay thì nó
    // tự bắt được cú click đó rồi đóng menu vừa mở.
    setTimeout(()=>{if(rowMenuState&&rowMenuState.el===el)addEventListener('click',onRowMenuOutside,true)},0);
  };
  const onKey=e=>{if(e.key==='Escape'&&overlay){e.preventDefault();destroy()}};
  document.addEventListener('keydown',onKey);
  addEventListener('popstate',()=>{if(overlay){popping=true;destroy({restoreHistory:false});popping=false}});
  const debounce=(fn,wait=250)=>{let timer;return(...args)=>{clearTimeout(timer);timer=setTimeout(()=>fn(...args),wait)}};
  const formatQuantity=value=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(Number(value||0));
  const formatDateTime=value=>value?new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(value)):'—';
  const formatDuration=seconds=>{seconds=Math.max(0,Number(seconds||0));const min=Math.floor(seconds/60),h=Math.floor(min/60);return h?`${h} giờ ${min%60} phút`:`${min} phút`};
  // --- gập/mở bộ lọc theo bề rộng màn hình -------------------------------
  //
  // <details> không tự biết viewport, nên phải có người đặt trạng thái ban
  // đầu. Quy tắc: <=700px thì gập, rộng hơn thì mở -- cùng ngưỡng với lưới 2
  // cột của bộ lọc trong ui.css, để hai thứ không nói hai chuyện khác nhau.
  //
  // Tôn trọng lựa chọn của người dùng: ai đã tự bấm mở/đóng thì lần đồng bộ
  // sau không giật lại. Cờ đánh dấu nằm trên chính phần tử nên khi trang vẽ
  // lại (mọi trang ở đây đều dựng lại innerHTML) nó biến mất cùng phần tử --
  // đúng ý: trang mới thì bắt đầu lại từ mặc định.
  const FILTER_COLLAPSE_MQ = window.matchMedia('(max-width:700px)');
  const syncFilterDisclosures = (root=document) => {
    const wantClosed = FILTER_COLLAPSE_MQ.matches;
    root.querySelectorAll?.('.ui-filter-disclosure').forEach(node => {
      if (node.dataset.userToggled === '1') return;
      node.open = !wantClosed;
    });
  };
  document.addEventListener('toggle', event => {
    const node = event.target;
    if (node instanceof HTMLElement && node.classList?.contains('ui-filter-disclosure')) {
      node.dataset.userToggled = '1';
    }
  }, true);
  FILTER_COLLAPSE_MQ.addEventListener('change', () => syncFilterDisclosures());
  // Trang được vẽ lại bằng innerHTML nên không có sự kiện nào báo; theo dõi
  // cây DOM là cách duy nhất bắt được phần tử mới mà không bắt mỗi trang phải
  // nhớ gọi hàm này.
  new MutationObserver(records => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.classList?.contains('ui-filter-disclosure') ||
            node.querySelector?.('.ui-filter-disclosure')) {
          syncFilterDisclosures(node.parentNode || document);
          return;
        }
      }
    }
  }).observe(document.documentElement, { childList: true, subtree: true });
  syncFilterDisclosures();


  // --- Back to top: primitive dùng chung cho MỌI màn dài ---------------------
  //
  // Vì sao là primitive chứ không phải một nút của riêng "Tiến trình sản xuất":
  // đo được, màn đó dài 8.3-11.7 viewport và "Tổng quan sản xuất" dài 7.1-10.5
  // với 8 PO x 80 Operation. Các màn danh sách khác cũng sẽ chạm ngưỡng đó khi
  // dữ liệu thật lớn lên. Một nút gắn cứng vào một màn thì màn thứ hai lại phải
  // dựng lại -- đúng kiểu lệch mà dự án này đã dọn nhiều lần.
  //
  // Quy tắc hiển thị (REQ-UI-018): chỉ hiện khi trang DÀI hơn ngưỡng VÀ người
  // dùng đã cuộn đủ xa; ẩn khi ở gần đỉnh. Ngưỡng tính theo VIEWPORT chứ không
  // theo px cố định, để một màn hình cao không phải cuộn vô lý mới thấy nút.
  const BACK_TO_TOP_VIEWPORTS = 1.5;
  const mountBackToTop = () => {
    if (document.querySelector('[data-back-to-top]')) return document.querySelector('[data-back-to-top]');
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ui-back-to-top';
    btn.setAttribute('data-back-to-top', '');
    btn.setAttribute('aria-label', 'Lên đầu trang');
    btn.hidden = true;
    btn.innerHTML = '<span aria-hidden="true">↑</span><b>Lên đầu trang</b>';
    btn.addEventListener('click', () => {
      // `smooth` là mặc định; người bật "giảm chuyển động" thì nhảy thẳng.
      const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
      window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
      // Trả tiêu điểm về đầu trang để bàn phím/screen-reader đi tiếp từ đó,
      // không bị bỏ lại ở cuối tài liệu.
      const first = document.querySelector('#content h2, #content h1, #content');
      if (first) { first.setAttribute('tabindex', '-1'); first.focus({ preventScroll: true }); }
    });
    document.body.appendChild(btn);

    const sync = () => {
      const doc = document.documentElement;
      // Không bao giờ đè lên modal/drawer đang mở -- chúng là ngữ cảnh độc
      // chiếm, một nút nổi bên dưới chỉ gây nhiễu và bắt được click nhầm.
      const overlay = document.body.classList.contains('modal-open')
        || document.body.classList.contains('ui-overlay-open')
        || !!document.querySelector('.modal-backdrop,.ui-drawer,.ec-drawer-shell');
      const longEnough = doc.scrollHeight > window.innerHeight * (1 + BACK_TO_TOP_VIEWPORTS);
      const scrolledEnough = window.scrollY > window.innerHeight * BACK_TO_TOP_VIEWPORTS;
      btn.hidden = overlay || !longEnough || !scrolledEnough;
    };
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => { ticking = false; sync(); });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
    // Trang được vẽ lại bằng innerHTML nên chiều cao đổi mà không có sự kiện
    // nào báo -- cùng lý do filter-disclosure phải theo dõi cây DOM.
    new MutationObserver(onScroll).observe(document.documentElement, { childList: true, subtree: true });
    sync();
    return btn;
  };

  // Gắn một lần cho cả app: mọi màn dài đều được, không màn nào phải nhớ gọi.
  //
  // Khối này phải nằm SAU khai báo `const mountBackToTop` -- trước đó nó đứng
  // cạnh syncFilterDisclosures() ở trên, tức gọi một `const` chưa khởi tạo.
  // Hôm nay không nổ vì core/ui.js là script chặn (không defer/async) nên
  // `readyState === "loading"` luôn đúng và lời gọi bị hoãn tới DOMContentLoaded.
  // Nhánh `else` thì nổ ReferenceError NGAY, trước cả `return` -- tức window.MFUI
  // không bao giờ được gán và CẢ APP chết, chỉ vì ai đó thêm `defer` hoặc nạp
  // file này động. Một quả mìn im lặng; đặt đúng chỗ thì hết.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => mountBackToTop(), { once: true });
  } else { mountBackToTop(); }

  return {statusBadge,opIdentity,mountBackToTop,BACK_TO_TOP_VIEWPORTS,opIdentityText,qtyValue,qtyLine,QTY_UNKNOWN,pageHeader,pageShell,filterBar,syncFilterDisclosures,contentPanel,statsRow,loadingState,emptyState,errorState,openDrawer,closeDrawer,openModal,confirmDialog,rowMenu,closeRowMenu,debounce,formatQuantity,formatDateTime,formatDuration};
})();
window.MFUI=MFUI;
