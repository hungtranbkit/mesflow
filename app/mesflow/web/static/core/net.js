// MESFlow — lớp gọi mạng dùng chung (shared request layer).
//
// LÝ DO TỒN TẠI
// -------------
// Trước file này, mỗi màn tự gọi `fetch` rồi `catch(e){hiện e.message}`. Khi
// mạng chớp tắt một nhịp, `fetch` reject bằng TypeError của trình duyệt và
// `e.message` đúng bằng chuỗi "Failed to fetch" — nên người vận hành xưởng
// nhìn thấy một câu tiếng Anh của trình duyệt, giữa một phần mềm tiếng Việt.
//
// Tệ hơn là các màn tự làm mới theo chu kỳ (Dashboard theo ngày 10s, Tổng
// quan / Điều hành PO / Tiến trình 15s): nhịp làm mới hỏng sẽ GHI ĐÈ toàn bộ
// nội dung đang hiển thị bằng khối lỗi đó. Một cú chớp mạng 200ms xoá sạch
// bảng dữ liệu người ta đang đọc. Đây chính là "thỉnh thoảng UI hiện Failed
// to fetch" mà không ai tái hiện được: nó không phải lỗi của màn nào, nó là
// lỗi của việc KHÔNG có chỗ nào chịu trách nhiệm về "mạng chớp tắt".
//
// Nên chỗ đó là file này, và chỉ file này:
//   * phân loại lỗi (tạm thời hay vĩnh viễn) — `classify`
//   * thử lại có backoff + jitter cho request AN TOÀN — `backoffDelay`
//   * timeout + huỷ (abort) khi người dùng đổi bộ lọc/màn
//   * dịch mọi lỗi sang MỘT câu tiếng Việt — `friendlyMessage`
//
// Ba hàm trên là hàm THUẦN và được export ra ngoài để test đơn vị gọi THẲNG,
// không cần mock mạng, không cần dựng màn nào — xem
// tests/e2e/request-layer-unit.spec.js (chạy trong trình duyệt vì đây là
// script trình duyệt, nhưng không chạm tới mạng).
//
// Dùng bởi cả hai frontend: admin app (qua core/api.js) và Kiosk web (qua
// `api()` riêng của kiosk.js, vốn còn phải ánh xạ mã lỗi NET-001/SYS-500).
const MFNet=(()=>{
  'use strict';

  // GET/HEAD an toàn theo định nghĩa HTTP: gửi lại không đổi trạng thái server.
  const SAFE_METHODS=['GET','HEAD'];
  // 408 hết hạn chờ, 425 gửi quá sớm, 429 quá tải, 5xx phía server/proxy.
  // KHÔNG có 4xx nghiệp vụ ở đây: 400/401/403/404/409/422 là câu trả lời DỨT
  // KHOÁT của server, thử lại chỉ tốn thêm một vòng rồi hỏng y hệt.
  const RETRY_STATUS=[408,425,429,500,502,503,504];
  // Những mã nói "server/proxy không phục vụ được", để chọn đúng câu báo.
  const SERVER_DOWN_STATUS=[500,502,503,504];
  // 400ms → 1s → 2s: tổng cộng ~3.4s chờ trong trường hợp xấu nhất, vẫn nằm
  // dưới ngưỡng người dùng bỏ cuộc, và đủ dài để qua một nhịp restart
  // container hoặc một lần nginx đổi upstream.
  const BACKOFF_MS=[400,1000,2000];
  const JITTER_RATIO=0.25;
  // Retry-After dài hơn mức này thì THÔI thử lại và báo ngay, thay vì treo
  // giao diện chờ. Server nói "quay lại sau 5 phút" là một câu trả lời, không
  // phải một lời mời chờ.
  const MAX_RETRY_AFTER_MS=10000;
  const TIMEOUT_READ_MS=15000;
  // Ghi dữ liệu được chờ lâu hơn: import/restart service chạy thật sự lâu, và
  // cắt sớm một request ghi là cách chắc chắn nhất để không biết nó đã vào
  // hay chưa.
  const TIMEOUT_WRITE_MS=30000;

  const MESSAGES={
    offline:'Mất kết nối mạng',
    unstable:'Kết nối chưa ổn định, vui lòng thử lại',
    serverDown:'Máy chủ tạm thời không phản hồi',
    reconnecting:'Đang kết nối lại…',
  };

  const isOnline=()=>typeof navigator==='undefined'||navigator.onLine!==false;
  const upper=method=>String(method||'GET').toUpperCase();

  // --- (1) Phân loại -----------------------------------------------------
  //
  // Hàm thuần. Trả về {retryable, kind} — `kind` quyết định CÂU BÁO, còn
  // `retryable` quyết định CÓ THỬ LẠI hay không. Hai câu hỏi khác nhau: một
  // POST gặp 503 là `kind:'server'` (đáng báo "máy chủ tạm thời không phản
  // hồi") nhưng `retryable:false` (không được tự gửi lại).
  function classify({status=0,error=null,method='GET',idempotent=false,online=true}={}){
    // Huỷ do chính ta hoặc do caller: KHÔNG phải lỗi, không bao giờ thử lại,
    // và tuyệt đối không hiện gì cho người dùng.
    if(error&&error.name==='AbortError')return{retryable:false,kind:'cancelled'};
    const safe=idempotent===true||SAFE_METHODS.includes(upper(method));
    if(error){
      // fetch chỉ reject bằng TypeError khi KHÔNG chạm được tới server
      // (DNS, connection reset, offline, CORS). Mọi phản hồi HTTP — kể cả
      // 500 — đều resolve. Nên nhánh này luôn là "lỗi tầng mạng".
      const kind=error.name==='TimeoutError'?'timeout':(online?'network':'offline');
      return{retryable:safe,kind};
    }
    if(RETRY_STATUS.includes(status)){
      return{retryable:safe,kind:SERVER_DOWN_STATUS.includes(status)?'server':'busy'};
    }
    if(status===401||status===403)return{retryable:false,kind:'auth'};
    return{retryable:false,kind:'http'};
  }

  // --- (2) Backoff -------------------------------------------------------
  //
  // Hàm thuần (nhận `random` để test bơm giá trị cố định). `attempt` đếm từ 1
  // = lần thử lại thứ nhất.
  //
  // Jitter ±25% là bắt buộc chứ không phải trang trí: nếu 30 kiosk cùng mất
  // mạng một nhịp rồi cùng thử lại đúng 400ms sau, chúng tạo lại đúng cơn tải
  // vừa làm server ngã. Rải ra thì không.
  function backoffDelay(attempt,{retryAfterMs=0,random=Math.random}={}){
    const step=BACKOFF_MS[Math.min(Math.max(attempt,1),BACKOFF_MS.length)-1];
    const jitter=step*JITTER_RATIO*(random()*2-1);
    const own=Math.max(100,Math.round(step+jitter));
    // Server nói rõ bao lâu thì nghe server — nhưng không bao giờ chờ ít hơn
    // backoff của mình (nghe lời quá sát cũng thành retry storm).
    return retryAfterMs>0?Math.max(retryAfterMs,own):own;
  }

  // Retry-After có hai dạng hợp lệ: số giây, hoặc HTTP-date.
  function parseRetryAfter(value,now=Date.now()){
    if(value===null||value===undefined||value==='')return 0;
    const seconds=Number(String(value).trim());
    if(Number.isFinite(seconds))return Math.max(0,Math.round(seconds*1000));
    const at=Date.parse(String(value));
    return Number.isFinite(at)?Math.max(0,at-now):0;
  }

  // --- (3) Câu báo cho người dùng ---------------------------------------
  //
  // Hàm thuần. Đây là NƠI DUY NHẤT một lỗi mạng biến thành chữ người đọc, nên
  // "Failed to fetch" không có đường nào khác để ra tới màn hình.
  function friendlyMessage({kind='http',status=0,serverMessage='',online=true}={}){
    if(kind==='offline'||!online)return MESSAGES.offline;
    if(kind==='server'||SERVER_DOWN_STATUS.includes(status))return MESSAGES.serverDown;
    if(kind==='network'||kind==='timeout'||kind==='busy')return MESSAGES.unstable;
    // 4xx nghiệp vụ: server đã nói bằng tiếng Việt rồi ("Số lượng vượt quá
    // WIP", "Session đã kết thúc"). Câu của server LUÔN thắng — phủ nó bằng
    // một câu chung chung là làm hỏng thông tin, không phải làm đẹp lỗi.
    const fromServer=String(serverMessage||'').trim();
    if(fromServer)return fromServer;
    return status?`Yêu cầu không thành công (HTTP ${status})`:MESSAGES.unstable;
  }

  // ======================================================================
  // Phần dưới đây phụ thuộc trình duyệt. Node (test đơn vị) chỉ nạp ba hàm
  // thuần ở trên; những gì bên dưới không chạy khi không có `window`.
  // ======================================================================

  const inflight=new Map();   // dedupe GET đang bay
  const slots=new Map();      // slot -> controller đang chiếm chỗ
  const groups=new Map();     // group -> Set<controller>
  const reconnectHandlers=new Set();
  let retryingCount=0;
  let authRedirecting=false;

  const hasDom=()=>typeof document!=='undefined'&&!!document.body;

  // --- Chỉ báo "Đang kết nối lại…" --------------------------------------
  //
  // Chỉ dựng trong admin app. Kiosk web CỐ Ý không có: màn kiosk là luồng
  // toàn màn hình, khoá bàn phím, người vận hành đang quét mã — một chip nổi
  // ở góc chỉ thêm nhiễu, và kiosk.js đã có sẵn vùng báo lỗi riêng
  // (setError + mã NET-001) nói đúng chuyện đó ở đúng chỗ mắt đang nhìn.
  function statusHost(){
    if(!hasDom())return null;
    if(!document.getElementById('toast'))return null; // dấu hiệu của admin app
    let el=document.getElementById('netStatus');
    if(!el){
      el=document.createElement('div');
      el.id='netStatus';
      el.className='net-status';
      el.setAttribute('role','status');
      el.setAttribute('aria-live','polite');
      el.hidden=true;
      document.body.appendChild(el);
    }
    return el;
  }

  function renderNetStatus(){
    const el=statusHost();
    if(!el)return;
    if(!isOnline()){
      el.textContent=MESSAGES.offline;
      el.dataset.state='offline';
      el.hidden=false;
      return;
    }
    if(retryingCount>0){
      el.textContent=MESSAGES.reconnecting;
      el.dataset.state='retrying';
      el.hidden=false;
      return;
    }
    el.hidden=true;
    el.dataset.state='ok';
  }

  // --- Huỷ request cũ ----------------------------------------------------
  //
  // Đơn vị bị huỷ là MỘT LỜI GỌI LOGIC (`handle`), không phải một lần thử.
  // Khác biệt này quan trọng: một lời gọi có thể trải qua 4 lần thử và ~3.4
  // giây backoff. Nếu chỉ theo dõi AbortController của lần thử đang chạy thì
  // suốt quãng nằm chờ giữa hai lần thử, lời gọi đó biến mất khỏi sổ -- đổi
  // màn hay đổi bộ lọc đúng lúc ấy sẽ KHÔNG huỷ được nó, và nó vẫn sống dậy
  // sau đó để vẽ hoặc báo lỗi trên màn người dùng đã rời. `handle.controller`
  // được thay mỗi lần thử, còn `handle` thì ở lại trong sổ từ đầu đến cuối.
  //
  // `slot`  : một chỗ duy nhất. Lời gọi mới vào slot huỷ lời gọi cũ trong
  //           cùng slot -- đúng ngữ nghĩa "đổi bộ lọc thì kết quả cũ vô nghĩa".
  // `group` : huỷ theo lô. openPage() huỷ cả nhóm của màn vừa rời.
  function supersede(handle){
    handle.superseded=true;
    if(handle.controller)handle.controller.abort();
  }
  function track(handle,{slot='',group=''}){
    if(slot){
      const prev=slots.get(slot);
      if(prev&&prev!==handle)supersede(prev);
      slots.set(slot,handle);
    }
    if(group){
      if(!groups.has(group))groups.set(group,new Set());
      groups.get(group).add(handle);
    }
  }
  function untrack(handle,{slot='',group=''}){
    if(slot&&slots.get(slot)===handle)slots.delete(slot);
    if(group&&groups.has(group)){
      const set=groups.get(group);
      set.delete(handle);
      if(!set.size)groups.delete(group);
    }
  }
  function abortGroup(group){
    const set=groups.get(group);
    if(!set)return 0;
    const n=set.size;
    for(const handle of[...set])supersede(handle);
    groups.delete(group);
    return n;
  }
  function abortSlot(slot){
    const handle=slots.get(slot);
    if(!handle)return false;
    supersede(handle);slots.delete(slot);
    return true;
  }

  // Một request bị CHÍNH TA huỷ (đổi bộ lọc, rời màn) không được phép hiện
  // bất cứ thứ gì. Nó không phải lỗi, và mọi call site trong app đều kết thúc
  // bằng `catch(e){hiện e.message}` — nên ném ra là chắc chắn hiện.
  //
  // Cách duy nhất để "không hiện gì" mà không phải sửa ~40 call site là trả
  // về một promise KHÔNG BAO GIỜ settle: hàm gọi dừng lại ngay tại `await`,
  // không vẽ gì, không báo gì. Mỗi lần đổi bộ lọc bỏ lại đúng một closure —
  // trả giá bằng vài chục byte để đổi lấy việc không màn nào phải tự nhớ
  // "lỗi này thì im lặng", thứ mà chỉ cần một màn quên là bug quay lại.
  //
  // Ngoại lệ: caller tự truyền `signal` thì caller tự quản lý — ta ném
  // AbortError thật để họ bắt.
  const NEVER=new Promise(()=>{});
  // Giá trị nội bộ: "lời gọi này đã bị thay chỗ". Không bao giờ ra tới call
  // site -- nó được đổi thành NEVER ở json() ngay trước khi trả về.
  const SUPERSEDED=Symbol('mfnet-superseded');

  function netError({kind,status=0,serverMessage='',errorCode='',attempts=1,cause=null,body=null}){
    const err=new Error(friendlyMessage({kind,status,serverMessage,online:isOnline()}));
    err.name='MFNetError';
    err.kind=kind;
    err.status=status;
    err.attempts=attempts;
    err.errorCode=errorCode;
    err.serverMessage=serverMessage;
    // Thân JSON đã parse, để consumer nào có bảng ánh xạ lỗi riêng dùng lại
    // (kiosk.js đổi nó thành MÃ + HÀNH ĐỘNG cho người đứng máy).
    err.body=body;
    // Chi tiết kỹ thuật đi vào thuộc tính riêng, KHÔNG vào .message: console
    // và Error Trace vẫn tra được, còn người dùng thì không phải đọc nó.
    err.technical=cause?`${cause.name||'Error'}: ${cause.message||cause}`:(status?`HTTP ${status}`:'');
    return err;
  }

  function handleAuthExpiry(){
    if(!hasDom())return;
    // Chống vòng lặp đăng nhập: nếu đang Ở /login thì 401 là câu trả lời của
    // chính form đăng nhập, chuyển hướng về /login nữa là lặp vô hạn. Và cờ
    // `authRedirecting` chặn 5 request song song cùng gọi location.href.
    if(authRedirecting)return;
    const path=location.pathname||'';
    if(path.startsWith('/login'))return;
    authRedirecting=true;
    location.href='/login';
  }

  async function readJson(response){
    try{return await response.json()}catch(_){return{}}
  }

  function waitBeforeRetry(attempt,retryAfterMs){
    const delay=backoffDelay(attempt,{retryAfterMs});
    retryingCount++;renderNetStatus();
    return new Promise(resolve=>setTimeout(()=>{
      retryingCount=Math.max(0,retryingCount-1);renderNetStatus();resolve();
    },delay));
  }

  // --- (4) Request thật --------------------------------------------------
  //
  // Trả về dữ liệu JSON đã parse, hoặc ném MFNetError có `.message` LUÔN là
  // câu tiếng Việt hiển thị được.
  //
  // opt (ngoài các khoá của fetch):
  //   idempotent : true = call site CAM KẾT endpoint dedupe được (có
  //                request_id và backend chặn trùng). Chỉ khi đó một mutation
  //                mới được tự gửi lại.
  //   retries    : ghi đè số lần thử lại.
  //   timeout    : ms; 0 = không timeout.
  //   slot/group : xem track() ở trên.
  //   dedupe     : false để tắt gộp GET trùng.
  async function json(url,opt={}){
    const method=upper(opt.method);
    const safeMethod=SAFE_METHODS.includes(method);
    const idempotent=opt.idempotent===true;
    const canRetry=safeMethod||idempotent;
    const maxRetries=Number.isInteger(opt.retries)?opt.retries:(canRetry?BACKOFF_MS.length:0);
    const timeoutMs=Number.isFinite(opt.timeout)?opt.timeout:(safeMethod?TIMEOUT_READ_MS:TIMEOUT_WRITE_MS);

    // Gộp GET trùng đang bay: Dashboard theo ngày làm mới mỗi 10s, nếu server
    // chậm hơn 10s thì các nhịp chồng lên nhau và tự tạo tải. Hai người gọi
    // nhận CÙNG một object kết quả — các màn ở đây chỉ đọc snapshot rồi vẽ,
    // không sửa nó; ai cần object riêng thì truyền dedupe:false.
    const dedupeKey=(safeMethod&&!opt.signal&&opt.dedupe!==false&&opt.body===undefined&&!opt.slot)
      ?`${method} ${url}`:'';
    if(dedupeKey&&inflight.has(dedupeKey))return inflight.get(dedupeKey);

    // `raw` LUÔN settle (kể cả khi bị huỷ, nó resolve bằng SUPERSEDED), còn
    // `exposed` mới là thứ call site nhận. Tách hai cái ra vì promise không
    // bao giờ settle (hợp đồng "bị huỷ thì im lặng" ở trên) sẽ giữ khoá dedupe
    // lại vĩnh viễn nếu dùng chính nó để dọn sổ -- rời Tổng quan giữa chừng
    // rồi quay lại là màn treo mãi mãi, không lỗi, không gì cả.
    const raw=attemptLoop();
    const exposed=raw.then(result=>result===SUPERSEDED?NEVER:result);
    if(dedupeKey){
      inflight.set(dedupeKey,exposed);
      const clear=()=>inflight.delete(dedupeKey);
      raw.then(clear,clear);
    }
    return exposed;

    async function attemptLoop(){
      // Một `handle` cho CẢ lời gọi, controller thay theo từng lần thử --
      // xem track() ở trên về lý do.
      const handle={superseded:false,controller:null};
      track(handle,opt);
      try{
        for(let attempt=0;;attempt++){
          if(handle.superseded)return SUPERSEDED;
          const controller=new AbortController();
          handle.controller=controller;
          let timedOut=false;
          if(opt.signal){
            if(opt.signal.aborted)controller.abort();
            else opt.signal.addEventListener('abort',()=>controller.abort(),{once:true});
          }
          const timer=timeoutMs>0?setTimeout(()=>{timedOut=true;controller.abort()},timeoutMs):null;

          let response=null,failure=null;
          try{
            response=await fetch(url,{...opt,signal:controller.signal});
          }catch(err){
            failure=err;
          }finally{
            if(timer)clearTimeout(timer);
          }

          if(failure){
            if(handle.superseded)return SUPERSEDED;        // ta tự huỷ → im lặng
            const raw=timedOut?Object.assign(new Error('timeout'),{name:'TimeoutError'}):failure;
            const verdict=classify({error:raw,method,idempotent,online:isOnline()});
            // Caller tự truyền signal thì caller tự quản lý: ném AbortError
            // thật để họ bắt, không dùng hợp đồng im lặng ở trên.
            if(verdict.kind==='cancelled')throw Object.assign(new Error('Yêu cầu đã huỷ'),{name:'AbortError',kind:'cancelled'});
            if(verdict.retryable&&attempt<maxRetries){
              await waitBeforeRetry(attempt+1,0);
              continue;
            }
            renderNetStatus();
            throw netError({kind:verdict.kind,attempts:attempt+1,cause:raw});
          }

          if(response.status===401){
            handleAuthExpiry();
            throw netError({kind:'auth',status:401,serverMessage:'Phiên đăng nhập đã hết hạn.',attempts:attempt+1});
          }

          if(!response.ok){
            const verdict=classify({status:response.status,method,idempotent,online:isOnline()});
            const retryAfterMs=parseRetryAfter(response.headers&&response.headers.get('Retry-After'));
            if(verdict.retryable&&attempt<maxRetries&&retryAfterMs<=MAX_RETRY_AFTER_MS){
              await waitBeforeRetry(attempt+1,retryAfterMs);
              continue;
            }
            const data=await readJson(response);
            throw netError({
              kind:verdict.kind,status:response.status,attempts:attempt+1,body:data,
              serverMessage:data.message||data.error||data.detail||'',
              errorCode:data.error_code||data.error||'',
            });
          }

          const data=await readJson(response);
          // Bị huỷ trong lúc đang đọc thân phản hồi vẫn là bị huỷ: trả về dữ
          // liệu của bộ lọc cũ lúc này cũng sai y như vẽ nó ra.
          if(handle.superseded)return SUPERSEDED;
          if(data&&data.ok===false){
            // 200 nhưng nghiệp vụ từ chối: luôn là câu trả lời dứt khoát.
            throw netError({
              kind:'http',status:response.status,attempts:attempt+1,body:data,
              serverMessage:data.message||data.error||data.detail||'',
              errorCode:data.error_code||data.error||'',
            });
          }
          return data;
        }
      }finally{
        untrack(handle,opt);
      }
    }
  }

  // --- (5) Online trở lại ------------------------------------------------
  //
  // Màn chỉ-đọc đang đứng trước một khối lỗi thì tự nạp lại khi có mạng —
  // người dùng không phải đoán xem bấm "Thử lại" lúc nào mới ăn.
  function onReconnect(handler){
    if(typeof handler!=='function')return()=>{};
    reconnectHandlers.add(handler);
    return()=>reconnectHandlers.delete(handler);
  }
  function clearReconnect(){reconnectHandlers.clear()}

  if(typeof window!=='undefined'&&window.addEventListener){
    window.addEventListener('offline',renderNetStatus);
    window.addEventListener('online',()=>{
      renderNetStatus();
      for(const fn of[...reconnectHandlers]){
        try{fn()}catch(err){console.warn('[MFNet] reconnect handler lỗi',err)}
      }
    });
  }

  return{
    // hàm thuần — test đơn vị gọi thẳng
    classify,backoffDelay,parseRetryAfter,friendlyMessage,
    // hằng số để test và call site khỏi chép lại chuỗi
    MESSAGES,RETRY_STATUS,BACKOFF_MS,SAFE_METHODS,MAX_RETRY_AFTER_MS,
    TIMEOUT_READ_MS,TIMEOUT_WRITE_MS,
    // runtime
    json,abortGroup,abortSlot,onReconnect,clearReconnect,
    isOnline,renderNetStatus,
    isCancelled:err=>!!err&&(err.name==='AbortError'||err.kind==='cancelled'),
  };
})();
if(typeof module!=='undefined'&&module.exports)module.exports=MFNet;
if(typeof window!=='undefined')window.MFNet=MFNet;
