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
  const filterBar=({content='',count='',activeCount=0,clearId='',clearLabel='Xóa bộ lọc',actions=''})=>`<div class="ui-filter-bar" role="search"><div class="ui-filter-controls">${content}</div><div class="ui-filter-meta">${activeCount?`<span class="ui-filter-active">Bộ lọc (${Number(activeCount)})</span>`:''}${clearId?`<button class="btn tertiary" id="${escHtml(clearId)}" type="button">${escHtml(clearLabel)}</button>`:''}${count!==''?`<span aria-live="polite">${escHtml(count)} kết quả</span>`:''}${actions?`<div class="ui-filter-bar-actions">${actions}</div>`:''}</div></div>`;
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
  const onKey=e=>{if(e.key==='Escape'&&overlay){e.preventDefault();destroy()}};
  document.addEventListener('keydown',onKey);
  addEventListener('popstate',()=>{if(overlay){popping=true;destroy({restoreHistory:false});popping=false}});
  const debounce=(fn,wait=250)=>{let timer;return(...args)=>{clearTimeout(timer);timer=setTimeout(()=>fn(...args),wait)}};
  const formatQuantity=value=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(Number(value||0));
  const formatDateTime=value=>value?new Intl.DateTimeFormat('vi-VN',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Ho_Chi_Minh'}).format(new Date(value)):'—';
  const formatDuration=seconds=>{seconds=Math.max(0,Number(seconds||0));const min=Math.floor(seconds/60),h=Math.floor(min/60);return h?`${h} giờ ${min%60} phút`:`${min} phút`};
  return {statusBadge,pageHeader,pageShell,filterBar,contentPanel,statsRow,loadingState,emptyState,errorState,openDrawer,closeDrawer,openModal,confirmDialog,debounce,formatQuantity,formatDateTime,formatDuration};
})();
window.MFUI=MFUI;
