document.getElementById('loginForm').addEventListener('submit',async e=>{e.preventDefault();const error=document.getElementById('error');error.textContent='';const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value.trim(),password:password.value})});const d=await r.json().catch(()=>({}));if(r.ok&&d.ok)location.href=(document.getElementById('nextUrl')?.value||'/app');else error.textContent=d.error==='INVALID_CREDENTIALS'?'Sai tên đăng nhập hoặc mật khẩu.':(d.message||d.error||'Đăng nhập thất bại.');});

(async()=>{
  if(document.body.dataset.testAutoLogin!=='1')return;
  const status=document.getElementById('autoLoginStatus');
  if(status)status.textContent='Chế độ test: đang tự đăng nhập...';
  // ?persona=operator (etc.) quick-switches which RBAC test persona this
  // auto-login lands as -- server validates against a fixed allowlist and
  // never trusts an arbitrary username from here (see /api/auth/test-auto-login).
  const persona=new URLSearchParams(location.search).get('persona');
  try{
    const r=await fetch('/api/auth/test-auto-login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(persona?{persona}:{})});
    const d=await r.json().catch(()=>({}));
    if(r.ok&&d.ok){location.href=(document.getElementById('nextUrl')?.value||'/app');return;}
    if(status)status.textContent=d.error==='AUTO_LOGIN_INVALID_PERSONA'?'Persona không hợp lệ.':'Auto-login không thành công. Có thể đăng nhập thủ công.';
  }catch(_){if(status)status.textContent='Không kết nối được auto-login. Có thể đăng nhập thủ công.';}
})();
