// Shared in-app navigation helper.
//
// MESFlow's admin shell is not a router-based SPA: `openPage(id)` swaps the
// whole #content innerHTML and there is no per-page URL (except the
// `?session=` deep link used by the Session Detail drawer). That means the
// *real* browser Back button is unsafe to rely on for in-app navigation --
// there is usually no history entry for "the previous screen", so
// history.back() can walk out of MESFlow entirely (login page, previous
// site, closed tab). Every in-app "Back" control must instead go through
// this helper, which tracks where the user drilled in from and how to
// return there with its filters/search/sort/pagination/scroll intact.
//
// Usage:
//   AppNav.push(()=>renderProductionOrders());   // before drilling into detail
//   ...
//   AppNav.back(()=>renderProductionOrders());   // "Back" button: pop stack,
//                                                 // or fall back to the
//                                                 // logical parent page.
//   AppNav.reset();                              // primary sidebar nav click
const AppNav=(()=>{
  const stack=[];
  const storageKey='mesflow.navigation.v71';
  const fieldSelector='#content [id]';
  const isStateful=el=>['INPUT','SELECT','TEXTAREA'].includes(el.tagName);

  // Snapshot every id'd form control inside #content plus scroll position and
  // "which tab/view is active" toggles. Generic on purpose: every page's
  // filter/search/sort/tab controls already live inside #content with a
  // stable id, so this single capture covers all of them without each page
  // needing its own bespoke state object.
  const captureState=()=>{
    const fields={};
    document.querySelectorAll(fieldSelector).forEach(el=>{
      if(!isStateful(el))return;
      fields[el.id]=el.type==='checkbox'?el.checked:el.value;
    });
    const tabs=[...document.querySelectorAll('#content [data-se-view].primary,#content [role="tab"][aria-selected="true"]')]
      .map(el=>el.dataset.seView||el.id).filter(Boolean);
    return {page:document.body.dataset.page,fields,tabs,scrollX:window.scrollX,scrollY:window.scrollY};
  };

  const persistState=()=>{
    try{sessionStorage.setItem(storageKey,JSON.stringify(captureState()))}catch(e){/* optional browser storage */}
  };
  const readPersistedState=()=>{try{return JSON.parse(sessionStorage.getItem(storageKey)||'null')}catch(e){return null}};
  const setPageUrl=(page,{replace=false}={})=>{
    if(!page)return;
    const url=new URL(location.href);url.searchParams.set('page',page);
    const state={...history.state,mfPage:page};history[replace?'replaceState':'pushState'](state,'',url);
    persistState();
  };
  const setQuery=(values,{replace=true}={})=>{
    const url=new URL(location.href);
    Object.entries(values||{}).forEach(([key,value])=>{if(value===null||value===undefined||value==='')url.searchParams.delete(key);else url.searchParams.set(key,String(value))});
    history[replace?'replaceState':'pushState']({...history.state,mfPage:document.body.dataset.page},'',url);
    persistState();
  };

  const restoreState=state=>{
    if(!state)return;
    Object.entries(state.fields||{}).forEach(([id,value])=>{
      const el=document.getElementById(id);
      if(!el||!isStateful(el))return;
      if(el.type==='checkbox')el.checked=value;else el.value=value;
    });
    // Re-fire input/change after all values are set so cross-filter
    // dependents (e.g. Part options depending on selected PO) settle once,
    // in the same order pages already wire their own onchange handlers.
    Object.keys(state.fields||{}).forEach(id=>{
      const el=document.getElementById(id);
      if(!el||!isStateful(el))return;
      el.dispatchEvent(new Event(el.tagName==='SELECT'||el.type==='checkbox'?'change':'input',{bubbles:true}));
    });
    (state.tabs||[]).forEach(value=>{
      const btn=document.querySelector(`[data-se-view="${value}"]`);
      if(btn)btn.click();
    });
    requestAnimationFrame(()=>window.scrollTo(state.scrollX||0,state.scrollY||0));
  };

  // Call right before navigating into a detail/child view. `renderFn` is
  // however the parent page gets rendered again from scratch (usually the
  // same render function the sidebar would call); AppNav re-runs it on Back
  // and then reapplies the filters/search/sort/scroll captured here.
  const push=renderFn=>{stack.push({state:captureState(),renderFn})};

  // Primary sidebar navigation is a fresh trip, not a drill-in -- clear any
  // stale return path so a later Back button (e.g. from a totally different
  // detail view) never resolves to an unrelated screen.
  const reset=()=>{stack.length=0};

  // Pop the last recorded parent screen and restore it; if there is none
  // (direct URL load, page refresh, or the stack is simply empty) call the
  // logical fallback instead of touching browser history.
  const back=async fallbackFn=>{
    const entry=stack.pop();
    if(entry){
      await entry.renderFn();
      restoreState(entry.state);
    }else if(fallbackFn){
      await fallbackFn();
    }
  };

  // Cross-page "you're here because of X" context, e.g. Session Exceptions
  // -> Session Management or Employees -> Session Management. Kept separate
  // from the undo-style stack because it also drives banner copy, not just
  // the Back target.
  let returnContext=null;
  const setReturnContext=ctx=>{returnContext=ctx};
  const getReturnContext=()=>returnContext;
  const clearReturnContext=()=>{returnContext=null};

  // One markup source for every "Back" control so icon/label placement and
  // styling never drift between pages.
  const backButtonHtml=(label,id='')=>{
    const e=window.esc?window.esc(label):String(label);
    return `<button class="btn nav-back"${id?` id="${id}"`:''} type="button" data-nav-back>← ${e}</button>`;
  };

  return {push,back,reset,setReturnContext,getReturnContext,clearReturnContext,backButtonHtml,captureState,restoreState,persistState,readPersistedState,setPageUrl,setQuery};
})();
window.AppNav=AppNav;
