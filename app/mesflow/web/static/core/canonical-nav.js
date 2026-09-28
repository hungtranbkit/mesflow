// Canonical navigation shell (UI consolidation plan P1).
//
// REFACTOR-ONLY and OFF BY DEFAULT. Nothing in here runs unless the client
// opted in with `?ui_refactor=1` (persisted to localStorage; `?ui_refactor=0`
// turns it off again). With the flag off app.js builds the legacy sidebar
// exactly as before and never calls into this module's DOM half.
//
// What it does when enabled:
//   - 11 canonical screens replace the 25 legacy sidebar entries.
//   - Each canonical screen is a set of tabs; every tab is backed by ONE
//     existing legacy page ID and opens through the existing openPage(), so
//     the legacy renderer (and its permission check) is the only
//     implementation. No business renderer is duplicated or moved here.
//   - Legacy `?page=<old>` URLs keep working: they resolve to the canonical
//     screen + tab. URLs written in refactor mode carry `page=<legacy>` as
//     well as `screen=` and `tab=`, because existing code (boot po_id/roles
//     deep links, popstate, Daily Dashboard) already keys off `page=`, and
//     because `tab=` is ALREADY owned by Dashboard theo ngày (overview/people/
//     output) and Hướng dẫn (video). `page=` therefore wins on resolution; a
//     bare `?screen=quality&tab=qc` still resolves on its own.
//
// Permissions: nothing new. A tab is shown only if canOpenPage(tab.page) --
// the unchanged legacy page permission. A screen is shown in the sidebar only
// if the user can open at least one tab whose legacy page was ALREADY a
// sidebar entry; tabs backed by previously hidden pages (qc, kiosk-events,
// kpi-operations) never make a screen appear for a role that did not see it
// before.
//
// The pure half (data + resolve/serialize) has no DOM dependency so it can be
// unit-tested under Node; see tests/test_ui_canonical_nav.py.
(function(root,factory){
  const api=factory(root);
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MFCanonicalNav=api;
})(typeof window!=='undefined'?window:globalThis,function(root){
  const FLAG_PARAM='ui_refactor';
  const FLAG_STORAGE_KEY='mesflow.ui_refactor';

  // hiddenLegacy: the backing page existed only as a hidden SPA page (never a
  // sidebar entry). See the permission note above.
  const SCREENS=[
    {id:'overview',label:'Tổng quan',icon:'overview',tabs:[
      {id:'realtime',label:'Realtime',page:'overview'},
      {id:'daily',label:'Theo ngày',page:'dashboard'}]},
    {id:'planning',label:'Kế hoạch sản xuất',icon:'production-orders',tabs:[
      {id:'orders',label:'Production Order',page:'production-orders'},
      {id:'schedule',label:'Gantt & Material Flow',page:'production-schedule'}]},
    {id:'templates',label:'Template',icon:'templates',tabs:[
      {id:'templates',label:'Template',page:'templates'}]},
    {id:'operations-sessions',label:'Điều hành phiên',icon:'session-management',tabs:[
      {id:'all',label:'Tất cả phiên',page:'session-management'},
      {id:'exceptions',label:'Bất thường',page:'session-exceptions'}]},
    {id:'quality',label:'Chất lượng',icon:'rework-queue',tabs:[
      {id:'rework',label:'Hàng chờ sửa',page:'rework-queue'},
      {id:'qc',label:'QC',page:'qc',hiddenLegacy:true}]},
    // P3 golden reference: kind:'report' + inlineTabs -- the screen renders
    // its own tab bar (MFUI.screenTabs, in the page action row) from THIS
    // definition, so the shell's external strip stays hidden for it and the
    // tabs also exist with the refactor flag off.
    {id:'productivity',label:'Năng suất',icon:'employee-productivity',kind:'report',inlineTabs:true,tabs:[
      {id:'employees',label:'Nhân viên',page:'employee-productivity'},
      {id:'operations',label:'Operation',page:'kpi-operations',hiddenLegacy:true}]},
    {id:'kiosk-admin',label:'Trạm kiosk',icon:'kiosk-management',tabs:[
      {id:'stations',label:'Trạm',page:'kiosk-management'},
      {id:'events',label:'Sự kiện',page:'kiosk-events',hiddenLegacy:true}]},
    {id:'master-data',label:'Danh mục',icon:'employees',tabs:[
      {id:'employees',label:'Nhân viên',page:'employees'},
      {id:'qr',label:'QR Code',page:'qr-print'},
      {id:'equipment',label:'Thiết bị',page:'equipment'}]},
    {id:'trace-logs',label:'Truy vết & Nhật ký',icon:'production-trace',tabs:[
      {id:'trace',label:'Truy vết sản xuất',page:'production-trace'},
      {id:'business',label:'Nhật ký nghiệp vụ',page:'business-audit'},
      {id:'application',label:'Nhật ký ứng dụng',page:'system-logs'}]},
    {id:'admin',label:'Quản trị',icon:'users',tabs:[
      {id:'users',label:'Người dùng',page:'users'},
      {id:'calendar',label:'Lịch làm việc',page:'working-calendar'}]},
    {id:'system',label:'Hệ thống',icon:'system-overview',kind:'console',lazy:true,tabs:[
      {id:'overview',label:'Tổng quan',page:'system-overview'},
      {id:'errors',label:'Lỗi hệ thống',page:'system-errors'},
      {id:'logs',label:'Nhật ký',page:'system-logs-it'},
      {id:'services',label:'Dịch vụ',page:'system-services'},
      {id:'diagnostics',label:'Chẩn đoán',page:'system-diagnostics'},
      {id:'audit',label:'Nhật ký quản trị',page:'system-audit'}]}
  ];

  // Legacy IDs that are aliases only: they resolve to a canonical tab whose
  // renderer is a DIFFERENT (canonical) legacy page.
  const ALIASES={
    sessions:{screen:'operations-sessions',tab:'all'},
    'kpi-employees':{screen:'productivity',tab:'employees'}
  };

  // Legacy IDs deliberately NOT mapped in P1. They stay addressable exactly as
  // before via ?page=<id>; they just have no canonical sidebar entry.
  const UNMAPPED_LEGACY={
    tutorials:'Help moves to the header help action (P1), not a primary destination',
    notifications:'TODO(P1+): global header inbox; renderer left untouched',
    audit:'Legacy raw audit log; no canonical owner yet',
    monitoring:'NOT aliased to system?tab=overview: monitoring has no page permission while system-overview is Super Admin only -- aliasing would change who can open it',
    'daily-dashboard-kiosk':'Presentation mode launched from Dashboard theo ngày, not a sidebar screen'
  };

  const SCREEN_BY_ID=Object.fromEntries(SCREENS.map(s=>[s.id,s]));
  const LEGACY_TO_CANONICAL={};
  SCREENS.forEach(s=>s.tabs.forEach(t=>{LEGACY_TO_CANONICAL[t.page]={screen:s.id,tab:t.id,alias:false}}));
  Object.entries(ALIASES).forEach(([page,target])=>{LEGACY_TO_CANONICAL[page]={...target,alias:true}});

  const getScreen=id=>SCREEN_BY_ID[id]||null;
  const getTab=(screenId,tabId)=>{
    const s=getScreen(screenId);if(!s)return null;
    return s.tabs.find(t=>t.id===tabId)||null;
  };
  const legacyToCanonical=page=>LEGACY_TO_CANONICAL[page]||null;
  const isCanonicalScreenOnly=id=>!!SCREEN_BY_ID[id]&&!LEGACY_TO_CANONICAL[id];

  const allow=canOpenPage=>typeof canOpenPage==='function'?canOpenPage:()=>true;
  const visibleTabs=(screenId,canOpenPage)=>{
    const s=getScreen(screenId);if(!s)return [];
    const can=allow(canOpenPage);
    return s.tabs.filter(t=>can(t.page));
  };
  // See the permission note at the top: hidden-legacy tabs never make a
  // screen appear on their own.
  const visibleScreens=canOpenPage=>{
    const can=allow(canOpenPage);
    return SCREENS.filter(s=>s.tabs.some(t=>!t.hiddenLegacy&&can(t.page)));
  };

  // Which legacy page should openPage() actually render for `id`?
  //  - canonical-only screen id (e.g. 'quality') -> its first permitted tab
  //  - alias (sessions, kpi-employees)           -> canonical tab's page, but
  //    if the user cannot open that page and CAN open the alias page itself,
  //    keep rendering the alias page so refactor mode never takes away access.
  //  - anything else                              -> unchanged
  const renderTarget=(id,canOpenPage)=>{
    const can=allow(canOpenPage);
    if(isCanonicalScreenOnly(id)){
      const tabs=visibleTabs(id,can);
      return (tabs[0]||SCREEN_BY_ID[id].tabs[0]).page;
    }
    const mapped=LEGACY_TO_CANONICAL[id];
    if(mapped&&mapped.alias){
      const target=getTab(mapped.screen,mapped.tab).page;
      if(!can(target)&&can(id))return id;
      return target;
    }
    return id;
  };

  // URL -> {screen, tab, page}. `page` is always a legacy page ID openPage()
  // understands. screen/tab are null for unmapped legacy pages.
  const resolveLocation=(params,canOpenPage)=>{
    const p=params instanceof URLSearchParams?params:new URLSearchParams(params||'');
    const pageParam=p.get('page');
    const screenParam=p.get('screen');
    const tabParam=p.get('tab');
    const fromScreen=(screenId,tabId)=>{
      const tab=getTab(screenId,tabId);
      if(tab)return {screen:screenId,tab:tab.id,page:tab.page,alias:false};
      const page=renderTarget(screenId,canOpenPage);
      return {screen:screenId,tab:legacyToCanonical(page).tab,page,alias:false};
    };
    if(pageParam){
      if(isCanonicalScreenOnly(pageParam))return fromScreen(pageParam,tabParam);
      const mapped=LEGACY_TO_CANONICAL[pageParam];
      if(mapped){
        const page=mapped.alias?renderTarget(pageParam,canOpenPage):pageParam;
        return {screen:mapped.screen,tab:mapped.tab,page,alias:mapped.alias};
      }
      return {screen:null,tab:null,page:pageParam,alias:false};
    }
    if(screenParam){
      if(SCREEN_BY_ID[screenParam])return fromScreen(screenParam,tabParam);
      if(LEGACY_TO_CANONICAL[screenParam])return resolveLocation(new URLSearchParams({page:screenParam}),canOpenPage);
    }
    return {screen:'overview',tab:'realtime',page:'overview',alias:false};
  };

  // Write canonical screen/tab for the legacy page being rendered. Every
  // other parameter (session, po_id, roles, date, filters, ui_refactor) is
  // preserved untouched. For an unmapped page only a stale `screen` is
  // dropped; `tab` is left alone because Hướng dẫn owns ?tab=video.
  const serialize=(page,search)=>{
    const p=new URLSearchParams(search||'');
    p.set('page',page);
    const mapped=LEGACY_TO_CANONICAL[page];
    // An alias page is only rendered as itself when the user lacks the
    // canonical tab's permission; it still belongs to that screen/tab.
    if(mapped){p.set('screen',mapped.screen);p.set('tab',mapped.tab)}
    else p.delete('screen');
    return p.toString();
  };

  // ?ui_refactor=1 turns the flag on and persists it; ?ui_refactor=0 turns it
  // off and forgets it; otherwise the persisted value decides. Storage errors
  // (private mode) degrade to "URL param only".
  const readFlag=(search,storage)=>{
    const value=new URLSearchParams(search||'').get(FLAG_PARAM);
    try{
      if(value==='1'){storage&&storage.setItem(FLAG_STORAGE_KEY,'1');return true}
      if(value==='0'){storage&&storage.removeItem(FLAG_STORAGE_KEY);return false}
      return !!storage&&storage.getItem(FLAG_STORAGE_KEY)==='1';
    }catch(_){return value==='1'}
  };

  // ---------------------------------------------------------------- DOM half
  const doc=root.document;
  const enabled=!!(doc&&root.location&&readFlag(root.location.search,(()=>{try{return root.localStorage}catch(_){return null}})()));
  let deps=null,tabStrip=null;
  const screenButtons={};

  const escHtml=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

  // Called by app.js INSTEAD of the legacy menu loop when enabled.
  const mount=d=>{
    deps=d;
    const {nav,canOpenPage,openPage,navIcon,closeMobileSidebar}=d;
    doc.body.dataset.uiRefactor='1';
    nav.dataset.canonicalNav='1';
    for(const s of visibleScreens(canOpenPage)){
      const b=doc.createElement('button');
      b.className='sidebar-item nav-item';b.type='button';b.dataset.canonicalScreen=s.id;
      b.innerHTML=`<span class="sidebar-item-icon">${navIcon(s.icon)}</span><span class="sidebar-item-label">${escHtml(s.label)}</span>`;
      b.title=s.label;
      b.onclick=()=>{closeMobileSidebar();root.AppNav.reset();root.AppNav.clearReturnContext();openPage(renderTarget(s.id,canOpenPage))};
      nav.appendChild(b);screenButtons[s.id]=b;
    }
    const main=doc.querySelector('.workspace-main'),content=doc.getElementById('content');
    if(main&&content){
      tabStrip=doc.createElement('nav');
      tabStrip.id='canonicalTabs';tabStrip.className='mf-tabs canonical-tabs';
      tabStrip.setAttribute('role','tablist');tabStrip.hidden=true;
      main.insertBefore(tabStrip,content);
    }
    // Help is a header action in refactor mode, not a sidebar destination.
    // TODO(P1+): notifications inbox in the header; the legacy hidden
    // `notifications` page stays reachable via ?page=notifications.
    const header=doc.querySelector('.workspace-header');
    if(header&&canOpenPage('tutorials')){
      const help=doc.createElement('button');
      help.type='button';help.id='canonicalHelpAction';help.className='btn canonical-help-action';
      help.textContent='Hướng dẫn';help.title='Hướng dẫn sử dụng';
      help.onclick=()=>{root.AppNav.reset();root.AppNav.clearReturnContext();openPage('tutorials')};
      header.appendChild(help);
    }
  };

  // Sidebar button that setActive() should highlight for legacy page `id`.
  // Its data-page is pointed at `id` so setActive() records the real legacy
  // page in body.dataset.page (request abort groups, same-page popstate
  // checks and renderSimple's refresh button all read it).
  const activeButton=id=>{
    const mapped=LEGACY_TO_CANONICAL[id];
    const b=mapped&&screenButtons[mapped.screen];
    if(!b)return null;
    b.dataset.page=id;
    return b;
  };

  const renderTabs=id=>{
    if(!tabStrip)return;
    const mapped=LEGACY_TO_CANONICAL[id];
    const screen=mapped?SCREEN_BY_ID[mapped.screen]:null;
    const tabs=mapped?visibleTabs(mapped.screen,deps.canOpenPage):[];
    if(tabs.length<2||screen?.inlineTabs){tabStrip.hidden=true;tabStrip.innerHTML='';delete tabStrip.dataset.screen;delete tabStrip.dataset.console;tabStrip.classList.remove('canonical-console-tabs');return}
    tabStrip.dataset.screen=mapped.screen;
    if(screen?.kind==='console'){tabStrip.dataset.console=mapped.screen;tabStrip.classList.add('canonical-console-tabs')}else{delete tabStrip.dataset.console;tabStrip.classList.remove('canonical-console-tabs')}
    tabStrip.hidden=false;
    tabStrip.innerHTML=tabs.map(t=>{
      const on=t.id===mapped.tab;
      return `<button type="button" class="mf-tab${on?' active':''}" role="tab" aria-selected="${on}" data-canonical-tab="${t.id}" data-page="${t.page}">${escHtml(t.label)}</button>`;
    }).join('');
    tabStrip.querySelectorAll('[data-canonical-tab]').forEach(btn=>{
      btn.onclick=()=>{
        if(btn.classList.contains('active'))return;
        root.AppNav.reset();root.AppNav.clearReturnContext();
        deps.openPage(btn.dataset.page);
      };
    });
  };

  // Called from openPage() right after setActive().
  const afterActive=id=>{
    if(!doc.body.dataset.page)doc.body.dataset.page=id;
    const mapped=LEGACY_TO_CANONICAL[id];
    const screen=mapped?SCREEN_BY_ID[mapped.screen]:null;
    if(mapped){doc.body.dataset.canonicalScreen=mapped.screen;doc.body.dataset.canonicalTab=mapped.tab}else{delete doc.body.dataset.canonicalScreen;delete doc.body.dataset.canonicalTab}
    if(screen?.kind==='console')doc.body.dataset.canonicalConsole=mapped.screen;else delete doc.body.dataset.canonicalConsole;
    renderTabs(id);
  };

  // Called from openPage() right after the legacy setPageUrl(): adds screen/
  // tab to the SAME history entry (replace), so Back/Forward/reload carry them.
  const syncUrl=id=>{
    const url=new URL(root.location.href);
    const next=serialize(id,url.search);
    if(next===url.search.replace(/^\?/,''))return;
    url.search=next;
    root.history.replaceState(root.history.state,'',url);
  };

  return {
    FLAG_PARAM,FLAG_STORAGE_KEY,SCREENS,ALIASES,UNMAPPED_LEGACY,
    enabled,readFlag,getScreen,getTab,legacyToCanonical,visibleTabs,visibleScreens,
    renderTarget,resolveLocation,serialize,
    mount,activeButton,afterActive,syncUrl
  };
});
