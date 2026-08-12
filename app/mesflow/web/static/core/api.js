async function api(url,opt={}){
  const headers={...(opt.headers||{})};
  if(opt.body!==undefined&&!headers['Content-Type'])headers['Content-Type']='application/json';
  const r=await fetch(url,{...opt,headers});
  if(r.status===401){location.href='/login';throw new Error('AUTH_REQUIRED')}
  const d=await r.json().catch(()=>({}));
  if(!r.ok||d.ok===false)throw new Error(d.message||d.error||`HTTP ${r.status}`);
  return d;
}
function toast(msg){
  const t=document.getElementById('toast');
  if(!t)return;
  t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200);
}
