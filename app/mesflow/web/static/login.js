document.getElementById('loginForm').addEventListener('submit',async e=>{e.preventDefault();const error=document.getElementById('error');error.textContent='';const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value.trim(),password:password.value})});const d=await r.json().catch(()=>({}));if(r.ok&&d.ok)location.href=(document.getElementById('nextUrl')?.value||'/app');else error.textContent=d.error==='INVALID_CREDENTIALS'?'Sai tên đăng nhập hoặc mật khẩu.':(d.message||d.error||'Đăng nhập thất bại.');});

(async()=>{
  if(document.body.dataset.testAutoLogin!=='1')return;
  const status=document.getElementById('autoLoginStatus');
  if(status)status.textContent='Chế độ test: đang tự đăng nhập...';
  try{
    const r=await fetch('/api/auth/test-auto-login',{method:'POST',headers:{'Content-Type':'application/json'}});
    const d=await r.json().catch(()=>({}));
    if(r.ok&&d.ok){location.href=(document.getElementById('nextUrl')?.value||'/app');return;}
    if(status)status.textContent='Auto-login không thành công. Có thể đăng nhập thủ công.';
  }catch(_){if(status)status.textContent='Không kết nối được auto-login. Có thể đăng nhập thủ công.';}
})();
