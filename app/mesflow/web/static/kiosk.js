(() => {
  const input = document.getElementById('scanner-input');
  const screens = [...document.querySelectorAll('.screen')];
  // randomUUID is restricted to secure contexts in Chromium. LOCAL Docker
  // commonly serves the kiosk over plain HTTP on a container hostname, where
  // crypto exists but randomUUID does not. Device identity is not a secret;
  // keep a collision-resistant fallback so one unavailable browser API cannot
  // abort all kiosk initialization and event binding.
  function newDeviceUuid() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
    else for (let i=0;i<bytes.length;i+=1) bytes[i]=Math.floor(Math.random()*256);
    bytes[6]=(bytes[6]&0x0f)|0x40; bytes[8]=(bytes[8]&0x3f)|0x80;
    const hex=[...bytes].map(value=>value.toString(16).padStart(2,'0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  }
  const deviceUuid = localStorage.getItem('mesflow_web_kiosk_uuid') || `WEB-${newDeviceUuid()}`;
  localStorage.setItem('mesflow_web_kiosk_uuid', deviceUuid);
  document.getElementById('device-label').textContent = deviceUuid.slice(0, 20);

  // Kiosk token. Starting a session writes to the real production record, so
  // this terminal has to prove it is one -- the page itself is public (nobody
  // signs in on a shop-floor screen), which is exactly why the credential
  // lives on the device instead of in a login. An admin enrolls a machine
  // once by opening /kiosk?token=<token issued for this device>; the token is
  // kept in localStorage and stripped from the address bar immediately, so it
  // is not left sitting in the URL of an unattended screen. A signed-in
  // browser needs no token at all -- the session is accepted instead.
  const TOKEN_KEY = 'mesflow_web_kiosk_token';
  (function enrollFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const supplied = (params.get('token') || '').trim();
    if (!supplied) return;
    localStorage.setItem(TOKEN_KEY, supplied);
    params.delete('token');
    const query = params.toString();
    history.replaceState(history.state, '', `${window.location.pathname}${query ? `?${query}` : ''}`);
  })();
  const kioskToken = () => localStorage.getItem(TOKEN_KEY) || '';
  const authHeaders = () => { const t = kioskToken(); return t ? {'X-Kiosk-Token': t} : {}; };

  let state = 'ready';
  const tutorialMode = new URLSearchParams(window.location.search).get('tutorial') === '1';
  let employee = null;
  let openSession = null;
  let scanBuffer = '';
  let scanTimer = null;
  let resetTimer = null;
  let lastHeartbeatError = '';
  let pendingFinish = { good:0, defect:0, rework:0, hasRework:false, note:'', requestId:'' };
  const quantityStates = ['quantity-good','quantity-defect','ask-rework','quantity-rework','finish-confirm'];

  function demoIsOpen() { return document.getElementById('demo-panel')?.classList.contains('open'); }
  // Màn nhập số -> ô input của nó. Focus ĐỒNG BỘ ngay khi màn hiện (xem chú
  // thích trong show()): chuyển màn làm ô cũ bị ẩn và mất focus, nếu focus ô
  // mới trễ thì có một cửa sổ KHÔNG ô nào nhận phím -- chữ số gõ trong cửa sổ
  // đó rơi mất. Hậu quả P0 quan sát được ở xưởng: người nhập Đạt/Lỗi xong,
  // Confirm hiện 0/0, và vì defect=0 nên bước "CÓ LỖI SỬA ĐƯỢC?" không xuất
  // hiện -> không khai được rework.
  const QUANTITY_INPUT = {'quantity-good':'good-qty','quantity-defect':'defect-qty','quantity-rework':'rework-qty'};
  function show(name) {
    screens.forEach(el => el.classList.toggle('active', el.id === `screen-${name}`));
    state = name;
    sendHeartbeat();
    const qtyInputId = QUANTITY_INPUT[name];
    if (qtyInputId) {
      const el = document.getElementById(qtyInputId);
      if (el) {
        // Ép layout flush TRƯỚC khi focus. Màn vừa chuyển display:none->flex
        // ở forEach ngay trên; gọi focus() trong cùng tick khi kiểu dáng chưa
        // recalc thì trình duyệt coi ô còn ẩn và focus() KHÔNG dính (đúng gốc
        // P0). Đọc offsetHeight buộc reflow, sau đó focus chắc chắn ăn -- đồng
        // bộ, không có cửa sổ trễ nào cho phím số rơi vào.
        void el.offsetHeight;
        el.focus({preventScroll:true});
      }
    } else if (!demoIsOpen()) {
      setTimeout(focusScanner, 20);
    }
  }
  function focusScanner() { if (!quantityStates.includes(state) && !demoIsOpen()) input.focus({preventScroll:true}); }
  function scheduleReset(delay) {
    clearTimeout(resetTimer);
    if (demoIsOpen()) return;
    const effectiveDelay = tutorialMode ? Math.max(Number(delay) || 0, 12000) : delay;
    resetTimer = setTimeout(reset, effectiveDelay);
  }
  const ERROR_HELP = {
    'SCN-001':'Kiểm tra nguồn, dây USB/UART và chế độ Enter/CR của máy quét.',
    'SCN-002':'Dùng QR nhân viên WF|EMP|... hoặc QR Operation WF|OP|... / WF|OPID|...',
    'EMP-001':'Kiểm tra thẻ hoặc trạng thái nhân viên trong Danh mục.',
    'EMP-002':'Thẻ này trỏ tới nhiều nhân viên. Sửa mã QR trong Danh mục rồi in lại thẻ.',
    'OP-001':'Kiểm tra QR Operation hoặc tạo lại QR từ PO.',
    'OP-002':'Tem này trùng mã với một Operation khác. In lại tem QR cho Operation này rồi quét lại.',
    'PO-001':'Nhờ quản đốc Start/Tiếp tục PO.',
    'SES-409':'Quét lại thẻ; nếu còn lỗi, kiểm tra session đang mở.',
    'QTY-409':'Giảm số lượng hoặc kiểm tra sản lượng OP nguồn.',
    'NET-001':'Kiểm tra Wi-Fi/LAN và địa chỉ máy chủ.',
    'AUTH_REQUIRED':'Máy này chưa được cấp token. Nhờ quản trị viên cấp token cho kiosk rồi mở lại màn hình bằng đường dẫn kèm token, hoặc đăng nhập trên máy này.',
    'FORBIDDEN':'Token của máy này đã bị thu hồi hoặc hết hiệu lực. Nhờ quản trị viên cấp lại.',
    'SYS-500':'Báo quản trị viên kèm mã lỗi này.'
  };
  function workerError(data,status) {
    const raw=`${data?.reason||''} ${data?.message||''}`.toUpperCase();
    // Not enrolled / token revoked: the operator can do nothing at the screen
    // itself, so say who to ask instead of showing a raw auth failure.
    if(status===401||status===403)
      return {message:'Máy kiosk này chưa được cấp quyền ghi dữ liệu.',
              action:ERROR_HELP[status===401?'AUTH_REQUIRED':'FORBIDDEN']};
    if(raw.includes('COMPLETED'))return {message:'Công đoạn này đã hoàn thành.',action:'Chọn công đoạn khác hoặc báo quản đốc nếu cần làm lại.'};
    if(raw.includes('CANCELLED'))return {message:'Công đoạn này đã bị hủy.',action:'Không tiếp tục sản xuất. Hỏi quản đốc để được điều phối.'};
    if(raw.includes('WIP=0')||raw.includes('NO_WIP'))return {message:'Chưa có sản phẩm đầu vào.',action:'Chờ WIP từ công đoạn trước hoặc báo quản đốc.'};
    if(raw.includes('DEPENDENCY')||raw.includes('OP TRƯỚC'))return {message:'Công đoạn trước chưa đủ điều kiện.',action:'Kiểm tra công đoạn trước hoặc báo quản đốc.'};
    if(status===409)return {message:'Công đoạn này hiện không thể bắt đầu.',action:'Kiểm tra trạng thái PO/Operation hoặc báo quản đốc.'};
    if(status===400)return {message:'Dữ liệu quét hoặc sản lượng chưa hợp lệ.',action:'Kiểm tra lại thông tin rồi thực hiện lại.'};
    if(status>=500)return {message:'Mất kết nối máy chủ.',action:'Chờ một lát rồi thử lại.'};
    return {message:'Chưa thực hiện được.',action:'Thử lại hoặc báo quản đốc nếu lỗi lặp lại.'};
  }
  function setError(message, code='SCN-000', action='') {
    const safeCode = String(code || 'SCN-000').toUpperCase();
    document.getElementById('error-code').textContent = safeCode;
    document.getElementById('error-message').textContent = message || 'Không thể xử lý yêu cầu';
    document.getElementById('error-action').textContent = action || ERROR_HELP[safeCode] || 'Quét lại. Nếu lỗi lặp lại, báo quản đốc kèm mã lỗi.';
    document.getElementById('scan-status').textContent = 'Cần thử lại';
    lastHeartbeatError = `${safeCode}: ${message || ''}`.slice(0, 240);
    show('error');
  }
  function reset() {
    clearTimeout(resetTimer);
    employee = null; openSession = null; scanBuffer = ''; input.value = '';
    pendingFinish = { good:0, defect:0, rework:0, hasRework:false, note:'', requestId:'' };
    document.getElementById('good-qty').value = '0'; document.getElementById('defect-qty').value = '0'; document.getElementById('rework-qty').value = '0'; document.getElementById('finish-note').value = '';
    document.getElementById('rework-validation').textContent = '';
    document.getElementById('good-validation').textContent = '';
    document.getElementById('defect-validation').textContent = '';
    document.getElementById('finish-submit-error').textContent = '';
    show('ready');
  }
  // The version this tab actually loaded with (kiosk.html sets
  // data-version="{{ version }}" on <html>). Compared against every
  // heartbeat response below to detect a server redeploy.
  const loadedVersion = document.documentElement.dataset.version || '';
  let reloadPending = false;
  function reloadIfNewVersionAvailable(serverVersion) {
    if (reloadPending || !serverVersion || !loadedVersion || serverVersion === loadedVersion) return;
    // Never yank the screen mid-task -- a locked-keyboard kiosk an operator
    // can't reach must still finish whatever they're doing; only reload
    // between tasks (state==='ready'), and check again on the next
    // heartbeat if it's currently busy.
    if (state !== 'ready' || demoIsOpen()) return;
    reloadPending = true;
    window.location.reload();
  }
  async function sendHeartbeat() {
    try {
      const response = await fetch('/api/kiosk-web/heartbeat', {
        method:'POST',
        headers:{'Content-Type':'application/json', ...authHeaders()},
        body:JSON.stringify({
          device_uuid:deviceUuid,
          device_name:'Web Kiosk Demo',
          firmware_version:loadedVersion || 'WEB-DEMO',
          ui_state:String(state || 'ready').toUpperCase(),
          health_state:lastHeartbeatError ? 'WARNING' : 'OK',
          queue_size:0,
          last_error:lastHeartbeatError
        }),
        keepalive:true
      });
      lastHeartbeatError='';
      const data = await response.json().catch(() => null);
      if (data?.ok) reloadIfNewVersionAvailable(data.version);
    } catch (error) {
      lastHeartbeatError=String(error?.message || 'Heartbeat failed');
    }
  }

  // Dùng chung core/net.js với admin app: cùng bộ phân loại lỗi tạm thời,
  // cùng backoff+jitter, cùng timeout. Kiosk chỉ giữ phần RIÊNG của nó — đổi
  // lỗi thành MÃ + HÀNH ĐỘNG mà người đứng máy tự làm được.
  //
  // Chỉ báo "Đang kết nối lại…" của net.js cố ý KHÔNG dựng ở đây: màn kiosk
  // là luồng toàn màn hình, khoá bàn phím; vùng báo lỗi sẵn có (setError) nói
  // đúng chuyện đó ở đúng chỗ mắt người quét mã đang nhìn.
  async function api(url, options={}) {
    try {
      return await MFNet.json(url, {
        ...options,
        headers:{'Content-Type':'application/json', ...authHeaders(), ...(options.headers||{})},
      });
    } catch (err) {
      if (MFNet.isCancelled(err)) throw err;
      const kind = err && err.kind;
      if (kind === 'network' || kind === 'timeout' || kind === 'offline') {
        // Giữ nguyên câu + mã NET-001 màn kiosk vẫn dùng: nó đi kèm một hành
        // động cụ thể, cụ thể hơn câu chung của net.js.
        const error = new Error(kind === 'offline' ? 'Mất kết nối mạng' : 'Không kết nối được máy chủ');
        error.code = 'NET-001'; error.action = ERROR_HELP['NET-001']; throw error;
      }
      const data = (err && err.body) || {};
      const status = (err && err.status) || 0;
      const friendly = workerError(data, status), error = new Error(friendly.message);
      error.code = data.error_code || data.error || (status >= 500 ? 'SYS-500' : `HTTP-${status}`);
      error.action = friendly.action;
      throw error;
    }
  }
  async function scan(qr) {
    qr = String(qr || '').trim(); if (!qr) return;
    document.getElementById('scan-status').textContent = 'Đã nhận mã · đang xử lý…';
    document.body.classList.add('kiosk-busy');
    try {
      const result = await api('/api/kiosk-web/scan', {method:'POST', body:JSON.stringify({qr})});
      if (state === 'ready') {
        if (result.type !== 'employee') { const e=new Error('Hãy quét thẻ nhân viên trước'); e.code='SCN-003'; e.action='Quét thẻ nhân viên trước, sau đó mới quét Operation.'; throw e; }
        employee = result.employee;
        if (result.open_session) {
          openSession = result.open_session;
          document.getElementById('finish-employee').textContent = `${employee.employee_no} · ${employee.name}`;
          document.getElementById('finish-operation').textContent =
            `${openSession.operation_display_key || openSession.operation_code} · ${openSession.operation_name}`;
          pendingFinish.requestId = `${deviceUuid}-FINISH-${Date.now()}`;
          if (OpPolicy.isSetup(openSession)) {
            // A setup produces nothing, so there is nothing to type. The
            // backend discards quantities for a setup session anyway (see
            // WorkSessionRepository._finish_within), which is exactly how the
            // fixed ESP terminal finishes one on its ordinary keypad screen --
            // this just spares the browser operator the three empty prompts.
            pendingFinish.good = 0; pendingFinish.defect = 0;
            pendingFinish.rework = 0; pendingFinish.hasRework = false;
            renderFinishConfirmation();
          } else {
            show('quantity-good');   // show() tự focus good-qty đồng bộ
          }
        } else {
          document.getElementById('employee-name').textContent = employee.name;
          document.getElementById('employee-code').textContent = `${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''}`;
          show('operation');
        }
      } else if (state === 'operation') {
        if (result.type !== 'operation') { const e=new Error('Hãy quét QR Operation'); e.code='SCN-004'; e.action='Sau khi nhận diện nhân viên, quét QR Operation.'; throw e; }
        const op = result.operation;
        document.getElementById('starting-operation').textContent =
          `${op.display_key || op.code} · ${op.name}`;
        show('starting');
        if (tutorialMode) await new Promise(resolve => setTimeout(resolve, 9000));
        // `request_id` sinh MỘT LẦN ở đây rồi nằm trong body, nên mọi lần gửi
        // lại đều mang đúng một id: backend (kiosk_idempotency +
        // pg_advisory_xact_lock trong WorkSessionRepository.start) trả về
        // chính session đã tạo thay vì tạo cái thứ hai. Đó là lý do — và là
        // điều kiện duy nhất — để bật `idempotent` cho một POST.
        const startRequestId = `${deviceUuid}-START-${Date.now()}`;
        const started = await api('/api/kiosk-web/start', {idempotent:true, method:'POST', body:JSON.stringify({employee_id:employee.id, operation_id:op.id, device_uuid:deviceUuid, request_id:startRequestId})});
        document.getElementById('started-operation').textContent =
          `${op.display_key || op.code} · ${op.name}`;
        show('started'); scheduleReset(3500);
      } else if (state === 'started' || state === 'finished' || state === 'error') {
        reset(); setTimeout(() => scan(qr), 50);
      }
    } catch (error) { setError(error.message, error.code, error.action); }
    finally { document.body.classList.remove('kiosk-busy'); }
  }

  function readQuantity(id, minimum=0) {
    const value = Number(document.getElementById(id).value);
    return Number.isSafeInteger(value) && value >= minimum ? value : null;
  }
  // Giữ hàm để mọi caller cũ vẫn gọi được, nhưng nay ĐỒNG BỘ: show() đã focus
  // đúng ô rồi, đây chỉ là lớp phòng hờ, không được là setTimeout (chính
  // setTimeout 30ms cũ là gốc của bug P0 mất chữ số).
  function focusQuantity(id) { const el=document.getElementById(id); if(el) el.focus({preventScroll:true}); }
  function nextGood() {
    const value = readQuantity('good-qty');
    if (value === null) { document.getElementById('good-validation').textContent = 'Nhập số nguyên từ 0 trở lên'; return; }
    document.getElementById('good-validation').textContent = '';
    pendingFinish.good = value;
    show('quantity-defect'); focusQuantity('defect-qty');
  }
  function nextDefect() {
    const value = readQuantity('defect-qty');
    if (value === null) { document.getElementById('defect-validation').textContent = 'Nhập số nguyên từ 0 trở lên'; return; }
    document.getElementById('defect-validation').textContent = '';
    pendingFinish.defect = value;
    if (value === 0) {
      pendingFinish.rework = 0; pendingFinish.hasRework = false; renderFinishConfirmation();
    } else {
      show('ask-rework');
    }
  }
  function chooseNoRework() {
    pendingFinish.rework = 0; pendingFinish.hasRework = false; renderFinishConfirmation();
  }
  function chooseRework() {
    pendingFinish.hasRework = true;
    const field = document.getElementById('rework-qty');
    field.max = String(pendingFinish.defect);
    field.min = '0';
    if (readQuantity('rework-qty', 0) === null || Number(field.value) > pendingFinish.defect) field.value = '0';
    document.getElementById('rework-max').textContent = `Nhập 0 đến ${pendingFinish.defect}`;
    document.getElementById('rework-validation').textContent = '';
    show('quantity-rework'); focusQuantity('rework-qty');
  }
  function nextRework() {
    // Khoảng hợp lệ là 0..NG. Cho phép 0 vì người vừa bấm "CÓ" rồi nhận ra
    // không có cái nào sửa được thì phải đi tiếp được, không bị kẹt màn hình.
    // (ESP v2 từ chối 0 ở màn này -- xem docs/KIOSK_ESP_PARITY.md.)
    const value = readQuantity('rework-qty', 0);
    const validation = document.getElementById('rework-validation');
    if (value === null) {
      validation.textContent = `Nhập số từ 0 đến ${pendingFinish.defect}`;
      return;
    }
    if (value > pendingFinish.defect) {
      validation.textContent = 'Số lỗi sửa được không thể lớn hơn số sản phẩm lỗi';
      return;
    }
    validation.textContent = '';
    pendingFinish.rework = value;
    // rework=0 thì không còn là "có lỗi sửa được": bảng xác nhận phải hiện
    // đúng như khi chọn "tiếp tục", không hiện dòng Sửa được 0 / Phế = NG.
    pendingFinish.hasRework = value > 0;
    renderFinishConfirmation();
  }
  function renderFinishConfirmation() {
    const scrap = pendingFinish.defect - pendingFinish.rework;
    const isSetup = OpPolicy.isSetup(openSession);
    const rows = isSetup
      ? [['Setup máy','Hoàn tất']]
      : (pendingFinish.hasRework
        ? [['Đạt',pendingFinish.good],['NG tổng',pendingFinish.defect],['Sửa được',pendingFinish.rework],['Phế',scrap]]
        : [['Đạt',pendingFinish.good],['NG',pendingFinish.defect]]);
    document.getElementById('finish-confirm-summary').innerHTML = rows.map(([label,value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('');
    document.getElementById('finish-submit-error').textContent = '';
    document.getElementById('finish-confirm-ok').hidden = false;
    document.getElementById('finish-submit-retry').hidden = true;
    show('finish-confirm');
  }
  function backFromConfirmation() {
    document.getElementById('finish-submit-error').textContent = '';
    if (pendingFinish.hasRework) { show('quantity-rework'); focusQuantity('rework-qty'); }
    else { show('quantity-defect'); focusQuantity('defect-qty'); }
  }

  // Đang gửi thì KHÔNG nhận thêm lệnh gửi nữa. ESP v2 làm y vậy: ở
  // UiState::FINISHING, handleKeypadKey rơi xuống nhánh "không phải màn nhập
  // số" và bỏ qua phím (mesflow_app.cpp). Trên bàn phím khoá cứng, người ta
  // bấm lại khi màn hình đứng vài giây; không ghi trùng nhờ request_id dùng
  // lại, nhưng để lọt phím vẫn là sai -- mỗi lần bấm lại một lượt gọi mạng.
  let submitting = false;

  async function finish() {
    if (submitting) return;
    if (!openSession) return setError('Không tìm thấy phiên đang làm','SES-404','Quét lại thẻ nhân viên để tải phiên đang mở.');
    const good = pendingFinish.good;
    const rework = pendingFinish.rework;
    const defect = pendingFinish.defect;
    submitting = true;
    // Từ lúc finish được phép TỰ gửi lại (idempotent + request_id), khoảng
    // chờ xấu nhất là ~3.4s backoff chứ không còn là một nhịp mạng. Trên màn
    // kiosk khoá bàn phím, 3.4 giây không có gì nhúc nhích sau khi bấm XÁC
    // NHẬN đọc y như máy treo — và phản xạ của người đứng máy là bấm lại.
    // Bấm lại không ghi trùng (cùng request_id), nhưng để màn im lặng suốt
    // quãng đó là bỏ đúng phần "trạng thái nhỏ khi đang thử lại" mà cả luồng
    // này dựa vào.
    //
    // Dùng chính nút vừa bấm làm chỗ báo: nó nằm đúng nơi mắt và tay đang ở,
    // không cần thêm phần tử nào vào markup của màn (tránh đụng vùng lane1
    // vừa đồng nhất với ESP v2). #finish-submit-error KHÔNG dùng được cho
    // việc này -- nó là role="alert" và mang nghĩa lỗi, còn đây là tiến trình.
    const confirmButton = document.getElementById('finish-confirm-ok');
    const retryButton = document.getElementById('finish-submit-retry');
    const confirmLabel = confirmButton.querySelector('span');
    const restoreSubmitUi = () => {
      confirmButton.disabled = false; retryButton.disabled = false;
      confirmLabel.textContent = 'XÁC NHẬN';
    };
    document.getElementById('finish-submit-error').textContent = '';
    confirmButton.disabled = true; retryButton.disabled = true;
    confirmLabel.textContent = 'ĐANG GỬI…';
    try {
      // Cùng lý do như START: `pendingFinish.requestId` sinh một lần lúc nhận
      // phiên đang mở và không đổi qua các lần gửi lại, nên sản lượng không
      // thể bị ghi hai lần — kể cả khi mạng rớt đúng lúc đã gửi xong mà chưa
      // kịp nhận phản hồi, tình huống mà trước đây công nhân buộc phải tự
      // bấm "Gửi lại" và không ai biết lần đầu đã vào hay chưa.
      await api(`/api/kiosk-web/finish/${openSession.id}`, {idempotent:true, method:'POST', body:JSON.stringify({good_qty:good, defect_qty:defect, rework_qty:rework, note:pendingFinish.note, request_id:pendingFinish.requestId})});
      const scrap = defect - rework;
      document.getElementById('finished-summary').textContent = rework > 0
        ? `Đạt ${good} · NG ${defect} · Sửa được ${rework} · Phế ${scrap}`
        : `Đạt ${good} · NG ${defect}`;
      show('finished'); scheduleReset(3000);
    } catch (error) {
      document.getElementById('finish-submit-error').textContent = 'CHƯA GỬI ĐƯỢC SẢN LƯỢNG';
      document.getElementById('finish-confirm-ok').hidden = true;
      document.getElementById('finish-submit-retry').hidden = false;
      show('finish-confirm');
    } finally {
      submitting = false;
      restoreSubmitUi();
    }
  }

  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); const value = input.value || scanBuffer; input.value=''; scanBuffer=''; scan(value); }
  });
  document.addEventListener('keydown', event => {
    if (quantityStates.includes(state)) {
      // Nhập số theo STATE, không theo focus. GỐC P0: chữ số dựa vào ô
      // <input> đang được focus, nhưng khi chuyển màn (Đạt->Lỗi->Sửa) ô mới
      // KHÔNG focus kịp trong cùng tick keydown (focus() ngay sau đổi display
      // không dính; setTimeout thì trễ và có cửa sổ phím rơi). Hậu quả ở
      // xưởng: Lỗi về 0, Confirm 0/0, và defect=0 nên bước "CÓ LỖI SỬA ĐƯỢC?"
      // không hiện. Kiosk khoá bàn phím -> "ô đang nhập" là thứ STATE nói,
      // không phải thứ focus nói. Ghi thẳng chữ số vào đúng ô theo state:
      // xác định, không phụ thuộc focus/layout/timing.
      if (QUANTITY_INPUT[state]) {
        const field = document.getElementById(QUANTITY_INPUT[state]);
        if (field) {
          if (/^[0-9]$/.test(event.key)) {
            event.preventDefault();
            const cur = (field.value === '0' || field.value === '') ? '' : field.value;
            field.value = (cur + event.key).slice(0, 7);   // trần 7 chữ số
            return;
          }
          if (event.key === 'Backspace') {
            event.preventDefault();
            field.value = field.value.slice(0, -1) || '0';
            return;
          }
        }
      }
      // Bàn phím kiosk web phải gõ giống bàn phím ESP. Bảng đối chiếu đầy đủ
      // ở docs/KIOSK_ESP_PARITY.md; chỗ web CỐ Ý khác firmware cũng nằm ở đó.
      if (state === 'ask-rework') {
        // 1 = CÓ (nhập số), 2/#/Enter = tiếp tục không có, * = quay lại.
        if (event.key === '1') { event.preventDefault(); chooseRework(); }
        else if (event.key === '2' || event.key === '#' || event.key === 'Enter') { event.preventDefault(); chooseNoRework(); }
        else if (event.key === '*') { event.preventDefault(); show('quantity-defect'); focusQuantity('defect-qty'); }
        return;
      }
      if (state === 'finish-confirm') {
        if (event.key === '#' || event.key === '1' || event.key === 'Enter') { event.preventDefault(); finish(); }
        else if (event.key === '*' || event.key === '2') { event.preventDefault(); backFromConfirmation(); }
        return;
      }
      // Màn nhập số: # / Enter xác nhận, * quay lại -- đúng phím của ESP.
      // Chữ số do chính ô <input type=number> nhận, không chặn ở đây.
      if (event.key === '#' || event.key === 'Enter') {
        event.preventDefault();
        if (state === 'quantity-good') nextGood();
        else if (state === 'quantity-defect') nextDefect();
        else if (state === 'quantity-rework') nextRework();
        return;
      }
      if (event.key === '*') {
        event.preventDefault();
        if (state === 'quantity-defect') { show('quantity-good'); focusQuantity('good-qty'); }
        else if (state === 'quantity-rework') show('ask-rework');
        return;
      }
      return;
    }
    if (event.key === 'Enter') { if (scanBuffer) { const code=scanBuffer; scanBuffer=''; scan(code); } return; }
    if (event.key.length === 1) { scanBuffer += event.key; clearTimeout(scanTimer); scanTimer=setTimeout(()=>{scanBuffer='';},180); }
  });
  // Numeric kiosk inputs: clear the default zero on focus/touch for faster entry.
  // If the operator leaves the field empty, restore zero so existing quantity logic stays unchanged.
  ['good-qty','defect-qty','rework-qty'].forEach(id => {
    const qtyInput = document.getElementById(id);
    if (!qtyInput) return;
    const clearDefaultZero = () => {
      if (String(qtyInput.value).trim() === '0') qtyInput.value = '';
    };
    qtyInput.addEventListener('focus', clearDefaultZero);
    qtyInput.addEventListener('pointerdown', clearDefaultZero);
    qtyInput.addEventListener('blur', () => {
      if (String(qtyInput.value).trim() === '') qtyInput.value = '0';
    });
  });

  document.addEventListener('click', event => { if (!event.target.closest('#demo-panel, #demo-toggle')) focusScanner(); });
  document.querySelectorAll('[data-action="cancel"],[data-action="reset"]').forEach(button => button.addEventListener('click', reset));
  document.getElementById('good-next').addEventListener('click', nextGood);
  document.getElementById('defect-back').addEventListener('click', () => { show('quantity-good'); focusQuantity('good-qty'); });
  document.getElementById('defect-next').addEventListener('click', nextDefect);
  document.getElementById('rework-none').addEventListener('click', chooseNoRework);
  document.getElementById('rework-yes').addEventListener('click', chooseRework);
  document.getElementById('ask-rework-back').addEventListener('click', () => { show('quantity-defect'); focusQuantity('defect-qty'); });
  document.getElementById('rework-back').addEventListener('click', () => show('ask-rework'));
  document.getElementById('rework-next').addEventListener('click', nextRework);
  document.getElementById('finish-confirm-ok').addEventListener('click', () => finish());
  document.getElementById('finish-confirm-edit').addEventListener('click', backFromConfirmation);
  document.getElementById('finish-submit-retry').addEventListener('click', () => finish());


  // --- Bảng mô phỏng quét QR (REQ-KIOSK-012) --------------------------------
  // Xưởng chạy hàng chục PO song song. Một <select> phẳng gom hết công đoạn
  // của mọi PO là không tìm nổi, và phần đuôi bị LIMIT cắt thì không cách nào
  // chọn tới. Nên phạm vi (PO) và tìm kiếm đi XUỐNG SERVER: lọc lại ở trình
  // duyệt trên tập đã bị cắt chỉ giấu vấn đề chứ không giải quyết nó.
  const demoPanel = document.getElementById('demo-panel');
  const demoToggle = document.getElementById('demo-toggle');
  const demoClose = document.getElementById('demo-close');
  const demoLoading = document.getElementById('demo-loading');
  const demoContent = document.getElementById('demo-content');
  const demoEmployee = document.getElementById('demo-employee');
  const demoOperation = document.getElementById('demo-operation');
  const demoPo = document.getElementById('demo-po');
  const demoSearch = document.getElementById('demo-operation-search');
  const demoCount = document.getElementById('demo-operation-count');
  const demoEmpty = document.getElementById('demo-operation-empty');
  const DEMO_PO_KEY = 'mesflow_kiosk_demo_po';
  let demoLoaded = false;
  let demoPoList = [];
  let demoPoTotal = 0;
  // Khi người dùng đã tự chọn PO thì không có đường nào tự đổi giúp họ nữa --
  // đổi phạm vi dưới tay người đang quét là cách nhanh nhất để công của lệnh
  // này bị ghi sang lệnh khác.
  let demoPoTouched = false;
  let demoSearchTimer = null;
  // Tìm kiếm có debounce + nạp lại theo chu kỳ chạy song song; chỉ phản hồi
  // của lần gọi MỚI NHẤT được phép vẽ, nếu không một phản hồi cũ về muộn sẽ
  // ghi đè kết quả đúng.
  let demoRequestSeq = 0;

  function canonicalPoId(raw) {
    const value = Number.parseInt(String(raw ?? '').trim(), 10);
    return Number.isInteger(value) && value > 0 ? String(value) : '';
  }
  function storedPoId() {
    try { return localStorage.getItem(DEMO_PO_KEY) || ''; } catch (_) { return ''; }
  }
  function rememberPoId(value) {
    try {
      if (value) localStorage.setItem(DEMO_PO_KEY, value);
      else localStorage.removeItem(DEMO_PO_KEY);
    } catch (_) { /* chế độ riêng tư: mất trí nhớ chứ không gãy panel */ }
  }
  // URL thắng bộ nhớ cục bộ ở lần mở đầu tiên: mở `/kiosk?po_id=…` là một chỉ
  // định rõ ràng của người vừa bấm link, còn localStorage chỉ là lần trước.
  // '' = "Tất cả PO" (khác với "chưa chọn gì").
  let demoPoId = canonicalPoId(new URLSearchParams(window.location.search).get('po_id'))
    || canonicalPoId(storedPoId());

  function employeeQr() {
    const option = demoEmployee.options[demoEmployee.selectedIndex];
    return option ? option.dataset.qr : '';
  }
  function operationQr() {
    const option = demoOperation.options[demoOperation.selectedIndex];
    return option ? option.dataset.qr : '';
  }
  function updateDemoQr() {
    document.getElementById('demo-employee-qr').textContent = employeeQr() || 'Chưa có QR nhân viên';
    document.getElementById('demo-operation-qr').textContent = operationQr() || 'Chưa có QR Operation';
    const hasOperation = !!operationQr();
    document.getElementById('demo-scan-operation').disabled = !hasOperation;
    document.getElementById('demo-copy-operation').disabled = !hasOperation;
  }
  function ensureTutorialDemoOptions() {
    if (!tutorialMode) return;
    const hasEmployee=[...demoEmployee.options].some(x=>x.textContent.includes('TUT-E06'));
    if (!hasEmployee) {
      const option=document.createElement('option');
      option.value='tutorial-employee';
      option.dataset.qr='WF|EMP|TUT-E06';
      option.textContent='TUT-E06 · Nhân viên hướng dẫn';
      demoEmployee.appendChild(option);
    }
    const hasOperation=[...demoOperation.options].some(x=>x.textContent.includes('TUT39-CUT'));
    if (!hasOperation) {
      const option=document.createElement('option');
      option.value='tutorial-operation';
      option.dataset.qr='WF|OP|TUT39-CUT';
      option.textContent='TUT-PO-GUIDE-39 · TUT-PART-A · TUT39-CUT · Cắt laser — Hướng dẫn';
      demoOperation.appendChild(option);
    }
  }

  function showTutorialDemoFallback(reason='') {
    demoEmployee.innerHTML='';
    demoOperation.innerHTML='';
    ensureTutorialDemoOptions();
    demoLoaded=true;
    renderDemoPoOptions();
    renderOperationSummary(demoOperation.options.length, demoOperation.options.length);
    updateDemoQr();
    demoLoading.hidden=true;
    demoContent.hidden=false;
    if (reason) document.getElementById('scan-status').textContent='Đang dùng dữ liệu hướng dẫn dự phòng';
  }

  function selectedPoLabel() {
    if (!demoPoId) return 'tất cả PO';
    const found = demoPoList.find(po => String(po.id) === demoPoId);
    return found ? (found.code || `#${found.id}`) : `PO #${demoPoId}`;
  }

  function renderDemoPoOptions() {
    demoPo.innerHTML = '';
    const all = document.createElement('option');
    all.value = '';
    all.textContent = demoPoTotal ? `Tất cả PO (${demoPoTotal})` : 'Tất cả PO';
    demoPo.appendChild(all);
    demoPoList.forEach(po => {
      const option = document.createElement('option');
      option.value = String(po.id);
      const count = Number(po.operation_count || 0);
      option.textContent = `${po.code || `#${po.id}`}${po.product ? ` · ${po.product}` : ''} · ${count} OP`;
      demoPo.appendChild(option);
    });
    // PO đang chọn không còn trong danh sách (vừa đóng lệnh, hoặc `po_id` trên
    // URL trỏ vào PO không chạy): GIỮ nó lại và nói thẳng, thay vì lặng lẽ
    // rơi về "Tất cả PO" và bày ra công đoạn của mọi lệnh khác.
    if (demoPoId && !demoPoList.some(po => String(po.id) === demoPoId)) {
      const stale = document.createElement('option');
      stale.value = demoPoId;
      stale.textContent = `PO #${demoPoId} · không còn đang chạy`;
      demoPo.appendChild(stale);
    }
    demoPo.value = demoPoId;
  }

  function emptyOperationMessage(term) {
    const scoped = !!demoPoId;
    if (term && scoped) return `Không có công đoạn nào khớp “${term}” trong ${selectedPoLabel()}. Xoá ô tìm kiếm, hoặc chọn “Tất cả PO”.`;
    if (term) return `Không có công đoạn nào khớp “${term}” trong các lệnh đang chạy.`;
    if (scoped) return `${selectedPoLabel()} chưa có công đoạn nào quét được. Chọn PO khác hoặc “Tất cả PO”.`;
    return 'Chưa có công đoạn từ lệnh đang chạy.';
  }

  function renderOperationSummary(shown, total) {
    const term = demoSearch.value.trim();
    const has = shown > 0;
    demoOperation.hidden = !has;
    demoEmpty.hidden = has;
    // `total` đếm TRƯỚC LIMIT ở server, nên "500/812" là lời thú nhận trung
    // thực rằng danh sách đang thiếu -- lọc hẹp lại thì con số tự khớp.
    demoCount.textContent = has
      ? (total > shown ? `${shown}/${total} công đoạn` : `${shown} công đoạn`)
      : '0 công đoạn';
    demoCount.classList.toggle('is-capped', total > shown);
    if (!has) demoEmpty.textContent = emptyOperationMessage(term);
  }

  function demoDataUrl(include) {
    const params = new URLSearchParams();
    if (include) params.set('include', include);
    if (demoPoId) params.set('po_id', demoPoId);
    const term = demoSearch.value.trim();
    if (term) params.set('q', term);
    const query = params.toString();
    return `/api/kiosk-web/demo-data${query ? `?${query}` : ''}`;
  }

  function renderDemoOperations(data) {
    const selectedOperation = demoOperation.value;
    demoOperation.innerHTML = '';
    (data.operations || []).forEach(op => {
      const option = document.createElement('option');
      option.value = op.id; option.dataset.qr = op.qr || `WF|OP|${op.code}`;
      option.dataset.poId = op.po_id == null ? '' : String(op.po_id);
      option.textContent = `${op.po_code || '-'} · ${op.part_code || '-'} · ${op.code} · ${op.name}`;
      demoOperation.appendChild(option);
    });
    ensureTutorialDemoOptions();
    const shown = demoOperation.options.length;
    if (selectedOperation && [...demoOperation.options].some(x => x.value === selectedOperation)) {
      demoOperation.value = selectedOperation;
    }
    renderOperationSummary(shown, Math.max(Number(data.operations_total || 0), shown));
  }

  function renderDemoEmployees(data) {
    const selectedEmployee = demoEmployee.value;
    demoEmployee.innerHTML = '';
    (data.employees || []).forEach(emp => {
      const option = document.createElement('option');
      option.value = emp.id; option.dataset.qr = emp.qr || `WF|EMP|${emp.employee_no}`;
      option.textContent = `${emp.employee_no} · ${emp.name}${emp.department ? ` · ${emp.department}` : ''}`;
      demoEmployee.appendChild(option);
    });
    ensureTutorialDemoOptions();
    if (!demoEmployee.options.length) demoEmployee.innerHTML = '<option value="">Chưa có nhân viên hoạt động</option>';
    if (selectedEmployee && [...demoEmployee.options].some(x => x.value === selectedEmployee)) {
      demoEmployee.value = selectedEmployee;
    }
  }

  async function loadDemoData(force=false, include='') {
    if (demoLoaded && !force) return;
    const seq = ++demoRequestSeq;
    const operationsOnly = include === 'operations';
    demoLoading.textContent = 'Đang tải dữ liệu...';
    if (!demoLoaded) { demoLoading.hidden = false; demoContent.hidden = true; }
    try {
      const request=api(demoDataUrl(include));
      const data=tutorialMode
        ? await Promise.race([
            request,
            new Promise((_,reject)=>setTimeout(()=>reject(new Error('demo-data timeout')),6000))
          ])
        : await request;
      if (seq !== demoRequestSeq) return;   // đã có lần gọi mới hơn
      if (!operationsOnly) {
        renderDemoEmployees(data);
        demoPoList = Array.isArray(data.production_orders) ? data.production_orders : demoPoList;
        demoPoTotal = Number(data.production_orders_total || demoPoList.length || 0);
        // `po_id` trên URL là chỉ định của người vừa mở màn này nên mỗi lần
        // nạp lại vẫn phải giữ đúng PO đó -- TRỪ KHI người dùng đã tự chọn PO
        // khác. Sau một lần chọn tay, không có gì được đổi phạm vi nữa.
        const urlPoId = canonicalPoId(new URLSearchParams(window.location.search).get('po_id'));
        if (urlPoId && !demoPoTouched && demoPoId !== urlPoId) demoPoId = urlPoId;
        renderDemoPoOptions();
      }
      renderDemoOperations(data);
      demoLoaded = true; updateDemoQr(); demoLoading.hidden = true; demoContent.hidden = false;
    } catch (error) {
      if (seq !== demoRequestSeq) return;
      if (tutorialMode) {
        showTutorialDemoFallback(error.message);
        return;
      }
      // The roster is signed-in-only now (it carries every badge QR). A real
      // terminal never needs it -- the scanner types into the input -- so this
      // says who can open it rather than reading as a kiosk failure.
      demoLoading.textContent = String(error.code || '').includes('401') || error.code === 'AUTH_REQUIRED'
        ? 'Danh sách mô phỏng chỉ dành cho tài khoản đã đăng nhập. Máy quét thật vẫn hoạt động bình thường.'
        : `Không tải được dữ liệu mô phỏng: ${error.message}`;
      demoLoading.hidden = false;
    }
  }

  // Đổi PO / gõ tìm kiếm chỉ cần nạp lại danh sách công đoạn. Nạp lại cả danh
  // sách nhân viên sẽ dựng lại <select> đó và làm mất nhân viên đang chọn.
  const reloadDemoOperations = () => loadDemoData(true, 'operations');

  function onDemoPoChange() {
    demoPoId = canonicalPoId(demoPo.value);
    demoPoTouched = true;
    rememberPoId(demoPoId);
    reloadDemoOperations();
  }

  function openDemo() { clearTimeout(resetTimer); demoPanel.classList.add('open'); demoPanel.setAttribute('aria-hidden','false'); demoToggle.setAttribute('aria-expanded','true'); loadDemoData(true); }
  function closeDemo() { demoPanel.classList.remove('open'); demoPanel.setAttribute('aria-hidden','true'); demoToggle.setAttribute('aria-expanded','false'); focusScanner(); }
  async function copyText(text) {
    if (!text) return;
    try { await navigator.clipboard.writeText(text); document.getElementById('scan-status').textContent = `Đã copy: ${text}`; }
    catch (_) { document.getElementById('scan-status').textContent = text; }
  }
  // Stable public hook for the tutorial recorder. The normal UI still uses the
  // same button listener; the recorder may call open() directly to avoid flaky
  // synthetic-click behavior caused by tutorial overlays.
  window.MESFlowKioskDemo = {
    open: openDemo,
    close: closeDemo,
    reload: () => { demoLoaded=false; return loadDemoData(true); },
    scanEmployee: () => scan(employeeQr()),
    scanOperation: () => scan(operationQr()),
    // Đổi phạm vi PO qua đúng đường mà cái <select> đi, để cái gọi từ script
    // và cái người dùng bấm không bao giờ lệch nhau. '' = Tất cả PO.
    selectProductionOrder: id => { demoPo.value = canonicalPoId(id); return onDemoPoChange(); },
    searchOperations: term => { demoSearch.value = String(term || ''); return reloadDemoOperations(); },
    // Feed an arbitrary payload through the same path a scanner gun uses --
    // the demo selects can only offer QRs that exist in the demo dataset.
    scan: qr => scan(String(qr || ''))
  };

  demoToggle.addEventListener('click', openDemo);
  demoClose.addEventListener('click', closeDemo);
  document.getElementById('demo-refresh').addEventListener('click', () => { demoLoaded=false; loadDemoData(true); });
  demoEmployee.addEventListener('change', updateDemoQr); demoOperation.addEventListener('change', updateDemoQr);
  demoPo.addEventListener('change', onDemoPoChange);
  demoSearch.addEventListener('input', () => {
    clearTimeout(demoSearchTimer);
    demoSearchTimer = setTimeout(reloadDemoOperations, 220);
  });
  demoSearch.addEventListener('search', () => { clearTimeout(demoSearchTimer); reloadDemoOperations(); });
  // Nạp lại nền để danh sách không cũ đi. Bỏ qua khi người dùng đang gõ hoặc
  // đang mở chính hai ô chọn -- dựng lại <select> dưới tay họ là mất lựa chọn.
  setInterval(() => {
    if (!demoIsOpen()) return;
    const busy = document.activeElement;
    if (busy === demoSearch || busy === demoOperation || busy === demoPo || busy === demoEmployee) return;
    loadDemoData(true);
  }, 10000);
  document.getElementById('demo-scan-employee').addEventListener('click', () => scan(employeeQr()));
  document.getElementById('demo-scan-operation').addEventListener('click', () => scan(operationQr()));
  document.getElementById('demo-copy-employee').addEventListener('click', () => copyText(employeeQr()));
  document.getElementById('demo-copy-operation').addEventListener('click', () => copyText(operationQr()));

  const hcmClock = new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  const updateClock = () => document.getElementById('clock').textContent = hcmClock.format(new Date());
  updateClock(); setInterval(updateClock, 1000);
  sendHeartbeat(); setInterval(sendHeartbeat, 30000);
  window.addEventListener('online', sendHeartbeat);
  window.addEventListener('beforeunload', () => navigator.sendBeacon?.('/api/kiosk-web/heartbeat', new Blob([JSON.stringify({device_uuid:deviceUuid,device_name:'Web Kiosk Demo',ui_state:'CLOSING',health_state:'OK',queue_size:0})], {type:'application/json'})));
  reset();
})();
