(() => {
  const input = document.getElementById('scanner-input');
  const screens = [...document.querySelectorAll('.screen')];
  const deviceUuid = localStorage.getItem('mesflow_web_kiosk_uuid') || `WEB-${crypto.randomUUID()}`;
  localStorage.setItem('mesflow_web_kiosk_uuid', deviceUuid);
  document.getElementById('device-label').textContent = deviceUuid.slice(0, 20);

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
  function show(name) {
    screens.forEach(el => el.classList.toggle('active', el.id === `screen-${name}`));
    state = name;
    sendHeartbeat();
    if (!demoIsOpen()) setTimeout(focusScanner, 20);
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
    'SCN-002':'Dùng QR nhân viên WF|EMP|... hoặc QR Operation WF|OP|...',
    'EMP-001':'Kiểm tra thẻ hoặc trạng thái nhân viên trong Danh mục.',
    'OP-001':'Kiểm tra QR Operation hoặc tạo lại QR từ PO.',
    'PO-001':'Nhờ quản đốc Start/Tiếp tục PO.',
    'SES-409':'Quét lại thẻ; nếu còn lỗi, kiểm tra session đang mở.',
    'QTY-409':'Giảm số lượng hoặc kiểm tra sản lượng OP nguồn.',
    'NET-001':'Kiểm tra Wi-Fi/LAN và địa chỉ máy chủ.',
    'SYS-500':'Báo quản trị viên kèm mã lỗi này.'
  };
  function workerError(data,status) {
    const raw=`${data?.reason||''} ${data?.message||''}`.toUpperCase();
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
    document.getElementById('good-qty').value = '0'; document.getElementById('defect-qty').value = '0'; document.getElementById('rework-qty').value = '1'; document.getElementById('finish-note').value = '';
    document.getElementById('rework-validation').textContent = '';
    document.getElementById('good-validation').textContent = '';
    document.getElementById('defect-validation').textContent = '';
    document.getElementById('finish-submit-error').textContent = '';
    show('ready');
  }
  async function sendHeartbeat() {
    try {
      await fetch('/api/kiosk-web/heartbeat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          device_uuid:deviceUuid,
          device_name:'Web Kiosk Demo',
          firmware_version:document.documentElement.dataset.version || 'WEB-DEMO',
          ui_state:String(state || 'ready').toUpperCase(),
          health_state:lastHeartbeatError ? 'WARNING' : 'OK',
          queue_size:0,
          last_error:lastHeartbeatError
        }),
        keepalive:true
      });
      lastHeartbeatError='';
    } catch (error) {
      lastHeartbeatError=String(error?.message || 'Heartbeat failed');
    }
  }

  async function api(url, options={}) {
    let response;
    try {
      response = await fetch(url, {headers:{'Content-Type':'application/json', ...(options.headers||{})}, ...options});
    } catch (_) {
      const error = new Error('Không kết nối được máy chủ');
      error.code = 'NET-001'; error.action = ERROR_HELP['NET-001']; throw error;
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      const friendly=workerError(data,response.status),error = new Error(friendly.message);
      error.code = data.error_code || data.error || (response.status >= 500 ? 'SYS-500' : `HTTP-${response.status}`);
      error.action = friendly.action;
      throw error;
    }
    return data;
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
          document.getElementById('finish-operation').textContent = `${openSession.operation_code} · ${openSession.operation_name}`;
          pendingFinish.requestId = `${deviceUuid}-FINISH-${Date.now()}`;
          show('quantity-good'); document.getElementById('good-qty').focus();
        } else {
          document.getElementById('employee-name').textContent = employee.name;
          document.getElementById('employee-code').textContent = `${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''}`;
          show('operation');
        }
      } else if (state === 'operation') {
        if (result.type !== 'operation') { const e=new Error('Hãy quét QR Operation'); e.code='SCN-004'; e.action='Sau khi nhận diện nhân viên, quét QR Operation.'; throw e; }
        const op = result.operation;
        document.getElementById('starting-operation').textContent = `${op.code} · ${op.name}`;
        show('starting');
        if (tutorialMode) await new Promise(resolve => setTimeout(resolve, 9000));
        const started = await api('/api/kiosk-web/start', {method:'POST', body:JSON.stringify({employee_id:employee.id, operation_id:op.id, device_uuid:deviceUuid, request_id:`${deviceUuid}-START-${Date.now()}`})});
        document.getElementById('started-operation').textContent = `${op.code} · ${op.name}`;
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
  function focusQuantity(id) { setTimeout(() => document.getElementById(id).focus(), 30); }
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
    if (readQuantity('rework-qty', 1) === null || Number(field.value) > pendingFinish.defect) field.value = '1';
    document.getElementById('rework-max').textContent = `Tối đa ${pendingFinish.defect} sản phẩm lỗi`;
    document.getElementById('rework-validation').textContent = '';
    show('quantity-rework'); focusQuantity('rework-qty');
  }
  function nextRework() {
    const value = readQuantity('rework-qty', 1);
    const validation = document.getElementById('rework-validation');
    if (value === null) {
      validation.textContent = 'Nhập số lỗi sửa được lớn hơn 0';
      return;
    }
    if (value > pendingFinish.defect) {
      validation.textContent = 'Số lỗi sửa được không thể lớn hơn số sản phẩm lỗi';
      return;
    }
    validation.textContent = '';
    pendingFinish.rework = value; pendingFinish.hasRework = true; renderFinishConfirmation();
  }
  function renderFinishConfirmation() {
    const scrap = pendingFinish.defect - pendingFinish.rework;
    const rows = pendingFinish.hasRework
      ? [['Đạt',pendingFinish.good],['Lỗi tổng',pendingFinish.defect],['Sửa được',pendingFinish.rework],['Phế',scrap]]
      : [['Đạt',pendingFinish.good],['Lỗi',pendingFinish.defect]];
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

  async function finish() {
    if (!openSession) return setError('Không tìm thấy phiên đang làm','SES-404','Quét lại thẻ nhân viên để tải phiên đang mở.');
    const good = pendingFinish.good;
    const rework = pendingFinish.rework;
    const defect = pendingFinish.defect;
    try {
      await api(`/api/kiosk-web/finish/${openSession.id}`, {method:'POST', body:JSON.stringify({good_qty:good, defect_qty:defect, rework_qty:rework, note:pendingFinish.note, request_id:pendingFinish.requestId})});
      const scrap = defect - rework;
      document.getElementById('finished-summary').textContent = rework > 0
        ? `Đạt ${good} · Lỗi ${defect} · Sửa được ${rework} · Phế ${scrap}`
        : `Đạt ${good} · Lỗi ${defect}`;
      show('finished'); scheduleReset(3000);
    } catch (error) {
      document.getElementById('finish-submit-error').textContent = 'CHƯA GỬI ĐƯỢC SẢN LƯỢNG';
      document.getElementById('finish-confirm-ok').hidden = true;
      document.getElementById('finish-submit-retry').hidden = false;
      show('finish-confirm');
    }
  }

  input.addEventListener('keydown', event => {
    if (event.key === 'Enter') { event.preventDefault(); const value = input.value || scanBuffer; input.value=''; scanBuffer=''; scan(value); }
  });
  document.addEventListener('keydown', event => {
    if (quantityStates.includes(state)) {
      if (state === 'ask-rework' && event.key === '1') { event.preventDefault(); chooseNoRework(); }
      else if (state === 'ask-rework' && event.key === '2') { event.preventDefault(); chooseRework(); }
      else if (state === 'finish-confirm' && (event.key === '#' || event.key === '1')) { event.preventDefault(); finish(); }
      else if (state === 'finish-confirm' && (event.key === '*' || event.key === '2')) { event.preventDefault(); backFromConfirmation(); }
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


  const demoPanel = document.getElementById('demo-panel');
  const demoToggle = document.getElementById('demo-toggle');
  const demoClose = document.getElementById('demo-close');
  const demoLoading = document.getElementById('demo-loading');
  const demoContent = document.getElementById('demo-content');
  const demoEmployee = document.getElementById('demo-employee');
  const demoOperation = document.getElementById('demo-operation');
  let demoLoaded = false;

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
    updateDemoQr();
    demoLoading.hidden=true;
    demoContent.hidden=false;
    if (reason) document.getElementById('scan-status').textContent='Đang dùng dữ liệu hướng dẫn dự phòng';
  }

  async function loadDemoData(force=false) {
    if (demoLoaded && !force) return;
    const selectedEmployee = demoEmployee.value;
    const selectedOperation = demoOperation.value;
    demoLoading.textContent = 'Đang tải dữ liệu...';
    demoLoading.hidden = false;
    if (!demoLoaded) demoContent.hidden = true;
    try {
      const request=api('/api/kiosk-web/demo-data');
      const data=tutorialMode
        ? await Promise.race([
            request,
            new Promise((_,reject)=>setTimeout(()=>reject(new Error('demo-data timeout')),6000))
          ])
        : await request;
      demoEmployee.innerHTML = ''; demoOperation.innerHTML = '';
      (data.employees || []).forEach(emp => {
        const option = document.createElement('option');
        option.value = emp.id; option.dataset.qr = emp.qr || `WF|EMP|${emp.employee_no}`;
        option.textContent = `${emp.employee_no} · ${emp.name}${emp.department ? ` · ${emp.department}` : ''}`;
        demoEmployee.appendChild(option);
      });
      (data.operations || []).forEach(op => {
        const option = document.createElement('option');
        option.value = op.id; option.dataset.qr = op.qr || `WF|OP|${op.code}`;
        option.textContent = `${op.po_code || '-'} · ${op.part_code || '-'} · ${op.code} · ${op.name}`;
        demoOperation.appendChild(option);
      });
      ensureTutorialDemoOptions();
      if (!demoEmployee.options.length) demoEmployee.innerHTML = '<option value="">Chưa có nhân viên hoạt động</option>';
      if (!demoOperation.options.length) demoOperation.innerHTML = '<option value="">Chưa có công đoạn từ lệnh đang chạy</option>';
      if (selectedEmployee && [...demoEmployee.options].some(x => x.value === selectedEmployee)) demoEmployee.value = selectedEmployee;
      if (selectedOperation && [...demoOperation.options].some(x => x.value === selectedOperation)) demoOperation.value = selectedOperation;
      demoLoaded = true; updateDemoQr(); demoLoading.hidden = true; demoContent.hidden = false;
    } catch (error) {
      if (tutorialMode) {
        showTutorialDemoFallback(error.message);
        return;
      }
      demoLoading.textContent = `Không tải được dữ liệu mô phỏng: ${error.message}`;
    }
  }
  function openDemo() { clearTimeout(resetTimer); demoPanel.classList.add('open'); demoPanel.setAttribute('aria-hidden','false'); loadDemoData(true); }
  function closeDemo() { demoPanel.classList.remove('open'); demoPanel.setAttribute('aria-hidden','true'); focusScanner(); }
  async function copyText(text) {
    if (!text) return;
    try { await navigator.clipboard.writeText(text); document.getElementById('scan-status').textContent = `Đã copy: ${text}`; }
    catch (_) { document.getElementById('scan-status').textContent = text; }
  }
  demoToggle.addEventListener('click', openDemo); demoClose.addEventListener('click', closeDemo);
  document.getElementById('demo-refresh').addEventListener('click', () => { demoLoaded=false; loadDemoData(true); });
  demoEmployee.addEventListener('change', updateDemoQr); demoOperation.addEventListener('change', updateDemoQr);
  setInterval(() => { if (demoIsOpen()) loadDemoData(true); }, 10000);
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
