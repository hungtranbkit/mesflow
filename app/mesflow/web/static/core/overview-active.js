// Tổng quan: active-only projection (hotfix 2026-09-30).
//
// The Overview shows ONLY the people running an Operation right now:
//   - a worker disappears on the next refresh after their session ends
//     (closed by hand, by the kiosk, or AUTO_CLOSED at shift end -- all of
//     those are status CLOSED, which the backend's active_worker_list never
//     contains);
//   - with several people on one Operation only the finished one goes, the
//     rest stay;
//   - an Operation with nobody active renders NO "Hôm nay" block at all (no
//     "finished"/"no session" placeholder).
// Display filtering only: history, reports, timeline, quantities and audits
// are untouched -- today_worker_list / today metrics still arrive from the
// API and are used elsewhere (Operation detail, Dashboard theo ngày).
//
// Pure and DOM-free so it is unit-tested under Node
// (tests/test_overview_active_only.py).
(function(root,factory){
  const api=factory();
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.MFOverviewActive=api;
})(typeof window!=='undefined'?window:globalThis,function(){
  // The backend sends OPEN sessions only; stay defensive anyway so a row
  // that ever carries a closed/ended entry (or a stale cached payload)
  // cannot bring a finished worker back.
  const isActive=w=>{
    if(!w||typeof w!=='object')return false;
    if(w.status!=null&&String(w.status).toUpperCase()!=='OPEN')return false;
    if(w.ended_at||w.closed_at)return false;
    if(w.session_count!=null&&Number(w.session_count)<=0)return false;
    return true;
  };
  // One entry per employee per Operation, in the order the API gives
  // (earliest start first). A person with several OPEN sessions on the
  // same Operation is already folded server-side; this also folds any
  // duplicate that slips through, keeping the earliest start.
  const activeWorkers=row=>{
    const list=row&&Array.isArray(row.active_worker_list)?row.active_worker_list:[];
    const seen=new Map();
    for(const w of list){
      if(!isActive(w))continue;
      const key=w.employee_id!=null?`id:${w.employee_id}`:`name:${w.employee_no||''}|${w.name||''}`;
      const prev=seen.get(key);
      if(!prev){seen.set(key,{...w});continue}
      prev.session_count=Number(prev.session_count||1)+Number(w.session_count||1);
      if(w.started_at&&(!prev.started_at||new Date(w.started_at)<new Date(prev.started_at)))prev.started_at=w.started_at;
    }
    return [...seen.values()];
  };
  const hasActiveWork=row=>activeWorkers(row).length>0;
  return {isActive,activeWorkers,hasActiveWork};
});
