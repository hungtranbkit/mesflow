(() => {
  // MỘT LUỒNG NGHIỆP VỤ, HAI CỬA VÀO.
  //
  // /kiosk (trạm cố định, công khai) gọi /api/kiosk-web/*; /kiosk-mobile (điện
  // thoại, BẮT BUỘC đăng nhập) gọi /api/kiosk-mobile/*. Máy chủ quyết định cửa
  // nào khoá bằng gì -- trang chỉ đọc tiền tố mà chính máy chủ đã ghi ra khi
  // dựng trang. Không đoán theo User-Agent, không đoán theo location.pathname:
  // cả hai đều là thứ trình duyệt tự khai, và một quyết định BẢO MẬT không bao
  // giờ được lấy từ phía trình duyệt. Ở đây nó chỉ là ĐỊA CHỈ để gọi; cái khoá
  // nằm ở server (xem web/auth.py, kiosk_mobile_required).
  const API_BASE = document.body.dataset.kioskApi || '/api/kiosk-web';
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
  // `openSession` = việc ĐANG được chốt sản lượng (con trỏ ngữ cảnh).
  // `openSessions` = TẤT CẢ việc người này đang giữ. Từ 0054 hai thứ đó không
  // còn là một: quét tem một việc khác chỉ đổi con trỏ, không đụng danh sách.
  let openSession = null;
  let openSessions = [];
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

  // SỐ LƯỢNG SỐNG Ở ĐÂY, không ở ô <input>.
  //
  // Vòng trước đã bỏ được phụ thuộc focus cho đường `keydown` (ghi theo
  // state). Nhưng bàn phím MỀM / IME / dán / đọc chính tả / nút tăng-giảm của
  // <input type=number> KHÔNG đi qua keydown mang chữ số: Gboard bắn
  // keydown key='Unidentified' (keyCode 229) rồi chèn chữ bằng
  // beforeinput/input. Đường đó vẫn rơi đúng vào phần tử ĐANG FOCUS -- nên
  // ngay sau khi chuyển màn (ô cũ bị display:none làm mất focus, ô mới chưa
  // chắc nhận được) chữ số lại rơi mất y như cũ. Người gõ bàn phím CỨNG không
  // dính, nên test gõ keyboard.press() xanh trong khi xưởng vẫn báo 0/0.
  //
  // Sửa tận gốc: sản lượng là một con số trong state. Mọi đường nhập (keydown
  // theo state, và input/beforeinput của chính ô) đều chỉ ghi vào ĐÂY; ô
  // <input> chỉ là chỗ hiển thị lại. Mọi chỗ đọc đều đọc state, không đọc DOM
  // -- nên không còn "giá trị hiển thị" và "giá trị gửi đi" lệch nhau.
  const QTY_IDS = ['good-qty','defect-qty','rework-qty'];
  const QTY_MAX_DIGITS = 7;
  const qty = {'good-qty':'0','defect-qty':'0','rework-qty':'0'};
  // SỐ 0 MẶC ĐỊNH KHÔNG PHẢI LÀ CÂU TRẢ LỜI.
  //
  // Ô luôn hiển thị '0' (quyết định của vòng trước: ô rỗng làm người đứng máy
  // tin mình đã nhập trong khi hệ thống đọc ra 0). Nhưng '0' hiển thị sẵn và
  // '0' người thật sự bấm là HAI thứ khác nhau, và trước đây cả hai đọc ra
  // cùng một số. Hậu quả đo được: nút TIẾP TỤC của quantity-good,
  // quantity-defect và nút XÁC NHẬN của finish-confirm CHỒNG LÊN NHAU trên
  // màn hình (Pixel 7: y 396-444 / 418-466 / 382-458 tại cùng x), nên ba cú
  // chạm ở ĐÚNG MỘT ĐIỂM đi thẳng qua ba màn và ghi 0/0 mà không ai nhập gì.
  //
  // `qtyTouched` là thứ tách hai nghĩa đó ra. Mọi đường nhập đều đánh dấu:
  // gõ phím theo state, bàn phím mềm/IME/Gboard/dán/đọc chính tả qua `input`.
  // Đây là guard theo TRẠNG THÁI, không phải cửa sổ thời gian -- không cú
  // chạm hợp lệ nào bị nuốt: cú chạm vẫn chạy, vẫn hiện thông báo, chỉ không
  // trả lời thay người một câu hỏi chưa ai trả lời.
  const qtyTouched = {'good-qty':false,'defect-qty':false,'rework-qty':false};
  function markQtyTouched(id) { if (id in qtyTouched) qtyTouched[id] = true; }
  function clearQtyTouched(id) { if (id in qtyTouched) qtyTouched[id] = false; }
  function renderQty(id) {
    const el = document.getElementById(id);
    if (el && el.value !== qty[id]) el.value = qty[id];
  }
  // Chỉ nhận chữ số. Nguồn nào cũng đi qua đây: gõ phím, bàn phím mềm, dán,
  // đọc chính tả. '' nghĩa là ô trống -- KHÁC với số 0 người thật sự nhập.
  function setQty(id, raw) {
    let digits = String(raw == null ? '' : raw).replace(/[^0-9]/g, '').slice(0, QTY_MAX_DIGITS);
    // Bỏ số 0 dẫn đầu: bàn phím mềm chèn chữ số vào ô đang mang '0' mặc định
    // thì ra '08'. Nó vẫn ra đúng 8 khi Number(), nhưng màn hình phải hiện
    // đúng con số sẽ được ghi -- không để hiển thị và dữ liệu nói khác nhau.
    if (digits.length > 1) digits = digits.replace(/^0+/, '') || '0';
    qty[id] = digits;
    renderQty(id);
  }
  function resetQty() { QTY_IDS.forEach(id => { setQty(id, '0'); clearQtyTouched(id); }); }
  // KẾT QUẢ MỘT LẦN QUÉT, NÓI RA THÀNH SỰ KIỆN.
  //
  // Màn kiosk vẽ kết quả vào các <section class="screen"> như cũ. Nhưng camera
  // điện thoại là một lớp `position:fixed; inset:0` nằm ĐÈ lên tất cả: máy chủ
  // trả về đúng tên nhân viên, kiosk.js vẽ đúng tên đó, và người cầm điện
  // thoại vẫn không thấy gì cho tới khi tắt camera đi. Đó là lỗi đã gặp trên
  // iPhone thật, và nó là lỗi HIỂN THỊ, không phải lỗi nghiệp vụ.
  //
  // Sửa bằng một sự kiện chứ không bằng cách cho kiosk.js vẽ lên lớp camera:
  // kiosk.js không được biết có module camera hay không (trạm cố định chạy
  // không có tệp đó), và lớp camera không được biết luật nghiệp vụ. Sự kiện
  // này chỉ mang thứ đã hiển thị ở màn bên dưới -- không có dữ liệu mới, không
  // có đường gọi API thứ hai.
  function announceScan(detail) {
    document.dispatchEvent(new CustomEvent('kiosk:scan-result', {detail}));
  }
  function show(name) {
    // Mỗi lần chuyển màn là một bước mới của luồng. Lần trả-về đang chờ thuộc
    // về màn sắp rời, không được phép nổ vào màn sắp tới -- một lần quét mới
    // trong cửa sổ 15 giây huỷ timer cũ chính bằng dòng này.
    cancelReset();
    screens.forEach(el => el.classList.toggle('active', el.id === `screen-${name}`));
    state = name;
    // Nguồn quét NGOÀI bàn phím (camera điện thoại) cần biết luồng đang ở đâu:
    // lúc nhập sản lượng thì phải tắt camera đi, cả vì nó che bàn phím số lẫn
    // vì không ai yêu cầu nó quay lúc đó. Phát sự kiện thay vì gọi thẳng, để
    // kiosk.js không phải biết có module camera hay không -- máy kiosk cố định
    // chạy y như cũ khi tệp đó không được nạp.
    // Cùng một sự thật ở hai chỗ đọc được: sự kiện cho JavaScript, thuộc tính
    // trên <body> cho CSS. Dùng data-attribute thay cho :has() vì :has() chỉ
    // có từ Safari 15.4 trở lên, mà máy ở xưởng thì không ai cập nhật.
    document.body.dataset.screen = name;
    document.dispatchEvent(new CustomEvent('kiosk:screen', {detail:{name}}));
    sendHeartbeat();
    // VỪA XONG VIỆC = thời điểm nạp bản mới. Nếu một bản mới đã được nhìn thấy
    // lúc đang dở tay thì nạp NGAY ở đây, không chờ nhịp heartbeat kế tiếp
    // (cách tới 30 giây) và không cần thêm một vòng mạng nào -- điều đó cũng có
    // nghĩa bản vá vẫn tới được máy kể cả khi mạng vừa rớt ngay sau lúc phát
    // hiện. Khi chưa thấy bản mới nào thì đây là một lời gọi rỗng.
    applyPendingReload();
    const qtyInputId = QUANTITY_INPUT[name];
    // BÀN PHÍM SỐ ĐI THEO MÀN, không theo một biến trạng thái riêng.
    //
    // Bản đầu hiện/ẩn bảng số bằng body[data-screen]. Sai ở chỗ: đó là NGUỒN
    // SỰ THẬT THỨ HAI cho câu hỏi "màn nào đang hiện", và hai nguồn lệch nhau
    // được. Bài kiểm chống chạm-xuyên-màn bật/tắt .active trực tiếp để đo toạ
    // độ nút, không đi qua show() -- lúc đó bảng số vẫn tưởng đang ở màn nhập
    // số, nên nó chiếm chỗ trong CẢ màn xác nhận và đẩy nút XÁC NHẬN lên
    // chồng vào vùng nút TIẾP TỤC. Đúng cái chồng vùng mà P0 kia đã sửa.
    //
    // Cách chắc chắn: cho bảng số nằm BÊN TRONG màn đang dùng nó. Màn ẩn thì
    // nó ẩn theo, không cần ai nhớ đồng bộ.
    const keypadNode = document.getElementById('qty-keypad');
    if (keypadNode) {
      const host = qtyInputId ? document.getElementById(`screen-${name}`) : null;
      if (host) { host.appendChild(keypadNode); keypadNode.hidden = false; }
      else { keypadNode.hidden = true; }
    }
    if (qtyInputId) {
      const el = document.getElementById(qtyInputId);
      if (el) {
        renderQty(qtyInputId);
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
  // Màn kết quả giữ bao lâu trước khi máy tự trả về "chờ quét thẻ nhân viên".
  // Trạm đứng một mình giữa hai lượt thợ: thứ gì còn trên màn lúc người vừa
  // làm bỏ đi thì phải tự sạch, nếu không người tiếp theo bước tới đúng kết
  // quả của người trước và cái trạm trông như đã treo.
  const FINISHED_RESET_MS = 15000;
  function cancelReset() { clearTimeout(resetTimer); resetTimer = null; }
  // force: cắm giờ kể cả khi bảng mô phỏng đang mở. Bảng đó chính là cách
  // người dùng trình duyệt điều khiển trạm này (laptop làm gì có súng quét),
  // nên để nó chặn lần trả-về-sau-khi-thành-công là đúng thứ đã ghim màn kết
  // quả ở đó vĩnh viễn. Rời màn của một việc đã xong không phải thứ tuỳ chọn.
  function scheduleReset(delay, {force = false} = {}) {
    cancelReset();
    if (demoIsOpen() && !force) return;
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
    'AUTH_REQUIRED':'Màn hình này không cần đăng nhập. Nếu vẫn báo lỗi, chụp màn hình và báo quản trị viên.',
    'FORBIDDEN':'Token của máy này đã bị thu hồi hoặc hết hiệu lực. Nhờ quản trị viên cấp lại, hoặc xóa token trên máy này để dùng ở chế độ công khai.',
    'SYS-500':'Báo quản trị viên kèm mã lỗi này.'
  };
  function workerError(data,status) {
    const raw=`${data?.reason||''} ${data?.message||''}`.toUpperCase();
    // The kiosk surface itself needs no login (see web/auth.py kiosk_public),
    // so a 401 here is an unexpected server-side condition, not "please sign
    // in" -- never tell a worker at a locked-down machine to log in. A 403 is
    // still real and actionable: this machine is carrying a kiosk token that
    // an admin has since revoked.
    if(status===403)
      return {message:'Token của máy kiosk này đã bị thu hồi.',action:ERROR_HELP['FORBIDDEN']};
    if(status===401)
      return {message:'Máy chủ từ chối yêu cầu của kiosk.',action:ERROR_HELP['AUTH_REQUIRED']};
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
    cancelReset();
    employee = null; openSession = null; openSessions = []; scanBuffer = ''; input.value = '';
    pendingFinish = { good:0, defect:0, rework:0, hasRework:false, note:'', requestId:'' };
    resetQty(); document.getElementById('finish-note').value = '';
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
  // Bản mới ĐÃ THẤY nhưng chưa nạp được vì lúc đó đang dở việc. Nhớ lại thay vì
  // quên đi: nhịp heartbeat kế tiếp có thể cách tới 30 giây, và mạng xưởng có
  // thể rớt ngay sau đó -- lúc người ta vừa xong việc thì đã biết thừa là có
  // bản mới, không việc gì phải đi hỏi lại rồi chờ một vòng mạng nữa.
  let pendingVersion = '';
  function isIdleForReload() {
    // Chỉ 'ready' mới là rảnh. 'finished'/'error' trông như đã xong nhưng vẫn
    // đang đếm giờ tự quay về màn chờ, và người đứng máy còn đang đọc số vừa
    // ghi -- nạp lại lúc đó là giật mất dòng xác nhận khỏi mắt họ.
    return state === 'ready' && !demoIsOpen();
  }
  function applyPendingReload() {
    if (reloadPending || !pendingVersion || !isIdleForReload()) return;
    reloadPending = true;
    // Tài liệu kiosk trả về no-store (xem web/kiosk.py::_never_cache) nên lần
    // nạp này lấy HTML mới, và HTML mới mang `?v=` mới cho JS/CSS.
    window.location.reload();
  }
  function reloadIfNewVersionAvailable(serverVersion) {
    if (reloadPending || !serverVersion || !loadedVersion || serverVersion === loadedVersion) {
      // Bằng nhau nghĩa là tab này đã ở đúng bản của máy chủ -- kể cả khi trước
      // đó từng thấy một bản khác (deploy rồi rollback). Xoá cờ để không còn
      // lần nạp lại nào bị treo lại mà không có lý do.
      if (serverVersion && serverVersion === loadedVersion) pendingVersion = '';
      return;
    }
    // Never yank the screen mid-task -- a locked-keyboard kiosk an operator
    // can't reach must still finish whatever they're doing; only reload
    // between tasks, and remember the new version until then.
    pendingVersion = serverVersion;
    applyPendingReload();
  }
  async function sendHeartbeat() {
    try {
      const response = await fetch(`${API_BASE}/heartbeat`, {
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
      // Máy chủ có thể ĐÃ nhận ra tem này là ai/việc gì rồi mới từ chối vì
      // luật nghiệp vụ (rõ nhất: PO-001 "PO chưa Start"). Phần đã nhận ra đó
      // phải sống sót qua lớp lỗi này, nếu không màn hình chỉ còn mỗi câu từ
      // chối và người quét không biết mình vừa quét trúng cái gì.
      if (data.scanned) error.scanned = data.scanned;
      throw error;
    }
  }
  // Vào luồng KẾT THÚC cho một việc cụ thể. Tách ra khỏi nhánh quét thẻ vì từ
  // 0054 có BA đường dẫn tới đây: quét thẻ khi đang giữ đúng một việc, quét tem
  // một việc đang chạy từ màn danh sách, và quét tem một việc đang chạy KHÁC
  // ngay giữa lúc đang nhập sản lượng cho việc này. Cả ba phải đặt cùng một
  // trạng thái, nếu không sẽ có đường chốt số vào nhầm session.
  // Trả về nhãn Operation để nơi gọi ghép câu thông báo.
  function enterFinishFor(session) {
    openSession = session;
    const openOp = `${session.operation_display_key || session.operation_code} · ${session.operation_name}`;
    document.getElementById('finish-employee').textContent = `${employee.employee_no} · ${employee.name}`;
    document.getElementById('finish-operation').textContent = openOp;
    pendingFinish.requestId = `${deviceUuid}-FINISH-${Date.now()}`;
    // Bắt đầu một lượt kết thúc là bắt đầu từ trắng: số của lượt trước (và dấu
    // "đã nhập" của nó) không được chảy sang người -- hay sang VIỆC -- kế tiếp.
    resetQty();
    pendingFinish.good = 0; pendingFinish.defect = 0;
    pendingFinish.rework = 0; pendingFinish.hasRework = false;
    pendingFinish.note = '';
    if (OpPolicy.isSetup(session)) {
      // A setup produces nothing, so there is nothing to type. The backend
      // discards quantities for a setup session anyway (see
      // WorkSessionRepository._finish_within), which is exactly how the fixed
      // ESP terminal finishes one on its ordinary keypad screen -- this just
      // spares the browser operator the three empty prompts.
      renderFinishConfirmation();
    } else {
      show('quantity-good');   // show() tự focus good-qty đồng bộ
    }
    return openOp;
  }

  // Danh sách việc đang chạy. Chỉ đọc -- không nút bấm trên từng dòng: tem
  // Operation là thứ chọn. Thời gian đã chạy là thông tin giúp người đứng máy
  // nhận ra việc nào là việc nào nhanh hơn cả mã.
  function renderSessionList() {
    document.getElementById('sessions-employee-name').textContent = employee.name;
    document.getElementById('sessions-employee-code').textContent =
      `${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''} · ${openSessions.length} việc đang chạy`;
    const list = document.getElementById('sessions-list');
    list.textContent = '';
    for (const s of openSessions) {
      const li = document.createElement('li');
      const code = document.createElement('b');
      code.textContent = s.operation_display_key || s.operation_code || '';
      const name = document.createElement('span');
      name.textContent = s.operation_name || '';
      const since = document.createElement('small');
      since.textContent = elapsedLabel(s.started_at);
      li.append(code, name, since);
      list.append(li);
    }
  }

  function elapsedLabel(startedAt) {
    const ms = Date.now() - new Date(startedAt).getTime();
    if (!Number.isFinite(ms) || ms < 0) return '';
    const min = Math.floor(ms / 60000);
    return min < 60 ? `${min} phút` : `${Math.floor(min / 60)} giờ ${min % 60} phút`;
  }

  async function scan(qr) {
    // CHUỖI THÔ, đúng như nguồn quét đưa vào -- không trim, không chuẩn hoá.
    // Bản gửi đi (`qr`) vẫn được trim như cũ; bản thô này tồn tại vì nó là thứ
    // duy nhất trả lời được câu "tem in ra có đúng không, hay máy đọc sai".
    const rawQr = String(qr == null ? '' : qr);
    qr = rawQr.trim(); if (!qr) return;
    document.getElementById('scan-status').textContent = 'Đã nhận mã · đang xử lý…';
    document.body.classList.add('kiosk-busy');
    try {
      const result = await api(`${API_BASE}/scan`, {method:'POST', body:JSON.stringify({qr})});
      if (state === 'ready') {
        if (result.type !== 'employee') { const e=new Error('Hãy quét thẻ nhân viên trước'); e.code='SCN-003'; e.action='Quét thẻ nhân viên trước, sau đó mới quét Operation.'; throw e; }
        employee = result.employee;
        // `open_sessions` là trường mới; `open_session` là trường cũ. Đọc cả
        // hai để màn hình này chạy được cả khi máy chủ chưa lên bản có 0054.
        openSessions = result.open_sessions || (result.open_session ? [result.open_session] : []);
        if (openSessions.length === 1) {
          // ĐÚNG MỘT VIỆC: giữ nguyên luồng cũ từng bước -- vào thẳng màn nhập
          // sản lượng. Đây là đại đa số ca làm, và thêm một nhịp chọn cho họ là
          // bước lùi so với 71.0.0.317.
          const openOp = enterFinishFor(openSessions[0]);
          announceScan({ok:true, kind:'employee', label:'Thẻ nhân viên', title:employee.name,
            sub:`${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''}`,
            raw:rawQr, next:`Đang làm: ${openOp} — nhập sản lượng để KẾT THÚC`});
        } else if (openSessions.length > 1) {
          // TỪ HAI VIỆC TRỞ LÊN: không tự chọn hộ. Máy không biết người đứng
          // máy vừa rời khỏi máy nào, và đoán sai thì sản lượng bị ghi sang
          // đúng một Operation khác -- hỏng lặng lẽ, không ai biết cho tới lúc
          // đối soát cuối ca. Hiện đủ danh sách rồi để tem Operation quyết định.
          renderSessionList();
          announceScan({ok:true, kind:'employee', label:'Thẻ nhân viên', title:employee.name,
            sub:`${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''}`,
            raw:rawQr, next:`Đang chạy ${openSessions.length} việc — quét mã công đoạn`});
          show('sessions');
        } else {
          document.getElementById('employee-name').textContent = employee.name;
          document.getElementById('employee-code').textContent = `${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''}`;
          announceScan({ok:true, kind:'employee', label:'Thẻ nhân viên', title:employee.name,
            sub:`${employee.employee_no}${employee.department ? ` · ${employee.department}` : ''}`,
            raw:rawQr, next:'Tiếp theo: quét QR CÔNG ĐOẠN'});
          show('operation');
        }
      } else if (state === 'operation' || state === 'sessions' || quantityStates.includes(state)) {
        if (result.type !== 'operation') { const e=new Error('Hãy quét QR Operation'); e.code='SCN-004'; e.action='Sau khi nhận diện nhân viên, quét QR Operation.'; throw e; }
        const op = result.operation;
        const opText = `${op.display_key || op.code} · ${op.name}`;
        // ĐANG MỞ hay CHƯA? Đây là toàn bộ ngữ nghĩa của máy quét từ 0054, và
        // nó chỉ có một câu trả lời vì uq_open_session_per_employee_operation
        // cấm hai session OPEN cùng một Operation.
        const already = openSessions.find(s => Number(s.operation_id) === Number(op.id));
        if (already) {
          // CHUYỂN NGỮ CẢNH, không bắt đầu, không kết thúc. Kể cả khi đang nhập
          // dở sản lượng cho việc khác: con số đang gõ thuộc về việc kia và bị
          // bỏ (enterFinishFor gọi resetQty), nhưng KHÔNG session nào bị đóng --
          // đóng chỉ xảy ra sau bước xác nhận, y như trước.
          enterFinishFor(already);
          announceScan({ok:true, kind:'operation', label:'QR công đoạn', title:op.name,
            sub:op.display_key || op.code, raw:rawQr, next:`Đang làm: ${opText} — nhập sản lượng để KẾT THÚC`});
          return;
        }
        document.getElementById('starting-operation').textContent = opText;
        announceScan({ok:true, kind:'operation', label:'QR công đoạn', title:op.name,
          sub:op.display_key || op.code, raw:rawQr, next:'Đang bắt đầu công đoạn…'});
        show('starting');
        if (tutorialMode) await new Promise(resolve => setTimeout(resolve, 9000));
        // `request_id` sinh MỘT LẦN ở đây rồi nằm trong body, nên mọi lần gửi
        // lại đều mang đúng một id: backend (kiosk_idempotency +
        // pg_advisory_xact_lock trong WorkSessionRepository.start) trả về
        // chính session đã tạo thay vì tạo cái thứ hai. Đó là lý do — và là
        // điều kiện duy nhất — để bật `idempotent` cho một POST.
        const startRequestId = `${deviceUuid}-START-${Date.now()}`;
        const started = await api(`${API_BASE}/start`, {idempotent:true, method:'POST', body:JSON.stringify({employee_id:employee.id, operation_id:op.id, device_uuid:deviceUuid, request_id:startRequestId})});
        // Ghi việc vừa mở vào danh sách đang giữ, để lần quét tem TIẾP THEO của
        // chính nó đi vào nhánh "đang mở" ở trên và kết thúc đúng session --
        // không phải quét lại thẻ nhân viên mới thấy nó.
        if (started && started.session) {
          openSessions = [{
            id: started.session.id,
            operation_id: started.session.operation_id,
            started_at: started.session.started_at,
            operation_code: op.code,
            operation_display_key: op.display_key || op.code,
            operation_name: op.name,
            operation_type: op.operation_type,
          }, ...openSessions.filter(s => Number(s.operation_id) !== Number(op.id))];
        }
        document.getElementById('started-operation').textContent = opText;
        announceScan({ok:true, kind:'operation', label:'QR công đoạn', title:op.name,
          sub:op.display_key || op.code, raw:rawQr, next:'ĐÃ BẮT ĐẦU — quét lại thẻ nhân viên khi xong'});
        // Người đang giữ nhiều việc cần thấy ngay là mình vừa thành N việc,
        // chứ không phải chỉ "đã bắt đầu" rồi tự đếm trong đầu.
        const startedNote = document.getElementById('started-note');
        if (startedNote) startedNote.textContent = openSessions.length > 1
          ? `Đang chạy ${openSessions.length} việc · quét lại thẻ khi hoàn thành`
          : 'Quét lại thẻ khi hoàn thành';
        show('started'); scheduleReset(3500);
      } else if (state === 'started' || state === 'finished' || state === 'error') {
        reset(); setTimeout(() => scan(qr), 50);
      }
    } catch (error) {
      setError(error.message, error.code, error.action);
      // GỐC CỦA LỖI P0: cả thân hàm nằm trong một `try`, nên BẤT KỲ lời từ
      // chối nghiệp vụ nào cũng nhảy thẳng xuống đây và lần quét bị công bố
      // như "không nhận được mã" -- kể cả khi máy chủ đã đọc ra chính xác đó
      // là công đoạn nào. Người cầm điện thoại không bao giờ thấy tên, không
      // bao giờ thấy chuỗi QR, nên không có cách nào biết tem in đúng hay sai.
      //
      // Nay tách làm hai lớp: cái ĐÃ NHẬN RA (tên + mã + chuỗi thô) và cái
      // ĐÃ TỪ CHỐI (mã lỗi + câu giải thích). Lỗi không còn chiếm chỗ của tên.
      // Không có nhánh nào ở đây gọi start/finish, nên một PO chưa Start vẫn
      // dừng đúng ở lần quét: không session nào được tạo.
      const named = error.scanned && error.scanned.title ? error.scanned : null;
      const code = String(error.code || 'SCN-000').toUpperCase();
      announceScan(named
        ? {ok:false, kind:named.kind || 'operation',
           label:named.kind === 'employee' ? 'Thẻ nhân viên' : 'QR công đoạn',
           title:named.title, sub:named.sub || '', raw:rawQr,
           error:`${code} · ${error.message || 'Không xử lý được'}`,
           next:error.action || ''}
        // Không nhận ra được gì thì thứ chắc chắn đúng chỉ còn chuỗi vừa đọc.
        // Nó vẫn phải hiện: đó là bằng chứng phân biệt "tem in sai" với "máy
        // đọc sai", và không có nó thì cả hai trông giống hệt nhau.
        : {ok:false, kind:'error', label:'Không nhận được mã',
           title:error.message || 'Không xử lý được', sub:code, raw:rawQr,
           next:error.action || ''});
    }
    finally { document.body.classList.remove('kiosk-busy'); }
  }

  // Đọc số đã nhập, KHÔNG đọc DOM. Ô trống trả null chứ không phải 0:
  // `Number('')` là 0, nên trước đây một ô chưa nhận được chữ số nào đi thẳng
  // vào sản lượng như một số 0 hợp lệ -- không báo lỗi, và vì defect=0 nên
  // nextDefect() bỏ luôn bước "CÓ LỖI SỬA ĐƯỢC?". Chính chỗ này biến một lần
  // rơi phím thành "Confirm 0/0" im lặng.
  function readQuantity(id, minimum=0) {
    const raw = qty[id];
    // Chưa ai chạm vào ô này -> chưa có câu trả lời. Trả null y như ô rỗng,
    // nên màn hình ở lại và hiện thông báo thay vì đi tiếp bằng số 0 mặc
    // định mà không ai nhập (xem chú thích ở `qtyTouched`).
    if (!qtyTouched[id]) return null;
    if (raw === '') return null;
    const value = Number(raw);
    return Number.isSafeInteger(value) && value >= minimum ? value : null;
  }
  // Giữ hàm để mọi caller cũ vẫn gọi được, nhưng nay ĐỒNG BỘ: show() đã focus
  // đúng ô rồi, đây chỉ là lớp phòng hờ, không được là setTimeout (chính
  // setTimeout 30ms cũ là gốc của bug P0 mất chữ số).
  function focusQuantity(id) { const el=document.getElementById(id); if(el) el.focus({preventScroll:true}); }
  function nextGood() {
    const value = readQuantity('good-qty');
    if (value === null) { document.getElementById('good-validation').textContent = 'Nhập số sản phẩm đạt — bấm 0 nếu không có'; return; }
    document.getElementById('good-validation').textContent = '';
    pendingFinish.good = value;
    show('quantity-defect'); focusQuantity('defect-qty');
  }
  function nextDefect() {
    const value = readQuantity('defect-qty');
    if (value === null) { document.getElementById('defect-validation').textContent = 'Nhập số sản phẩm lỗi — bấm 0 nếu không có'; return; }
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
    const current = readQuantity('rework-qty', 0);
    // Ô do HỆ THỐNG đặt lại thì vẫn là chưa ai trả lời -- người vừa bấm "CÓ,
    // NHẬP SỐ" thì phải nhập số, không được đi tiếp bằng 0 dựng sẵn.
    if (current === null || current > pendingFinish.defect) { setQty('rework-qty', '0'); clearQtyTouched('rework-qty'); }
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
      await api(`${API_BASE}/finish/${openSession.id}`, {idempotent:true, method:'POST', body:JSON.stringify({good_qty:good, defect_qty:defect, rework_qty:rework, note:pendingFinish.note, request_id:pendingFinish.requestId})});
      // Việc này đã đóng -- bỏ khỏi danh sách đang giữ. Các việc còn lại KHÔNG
      // bị đụng tới: chốt sản lượng OP2 không được ảnh hưởng OP1/OP3.
      openSessions = openSessions.filter(s => Number(s.id) !== Number(openSession.id));
      const scrap = defect - rework;
      document.getElementById('finished-summary').textContent = rework > 0
        ? `Đạt ${good} · NG ${defect} · Sửa được ${rework} · Phế ${scrap}`
        : `Đạt ${good} · NG ${defect}`;
      // Còn việc đang chạy thì phải nói ra, nếu không người đứng máy rời đi
      // trong khi một Operation vẫn đang mở dưới tên mình.
      const finishedNote = document.getElementById('finished-note');
      if (finishedNote) finishedNote.textContent = openSessions.length
        ? `Còn ${openSessions.length} việc đang chạy · quét lại thẻ để tiếp tục`
        : '';
      show('finished'); scheduleReset(FINISHED_RESET_MS, {force:true});
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
  // MÃ QR CÓ THỂ TỚI GIỮA LÚC ĐANG NHẬP SỐ.
  //
  // Từ 0054 người đứng máy được quét tem một việc khác ngay khi đang ở màn nhập
  // sản lượng -- để bắt đầu thêm việc, hoặc để chuyển sang chốt số cho việc
  // khác. Nhưng màn nhập số đang nuốt phím theo STATE, nên chuỗi từ súng quét
  // sẽ rơi vào đúng cái hố đó nếu không tách ra.
  //
  // Tách bằng NỘI DUNG, không bằng tốc độ gõ: mọi mã của hệ thống đều có dấu
  // `|` (WF|EMP|..., WF|OP|..., WF|OPID|...), còn bàn phím số rời thì không có
  // phím nào sinh ra `|`. Vì vậy "đệm có chứa `|`" là bằng chứng chắc chắn đây
  // là một lần quét chứ không phải một con số ai đó đang gõ -- không cần đoán
  // theo ngưỡng thời gian, thứ sẽ hỏng với người gõ nhanh hoặc súng quét chậm.
  const looksLikeScan = text => text.includes('|');
  document.addEventListener('keydown', event => {
    if (quantityStates.includes(state)) {
      // Đệm chạy SONG SONG với ô nhập số và tự xoá sau 180ms im lặng, nên một
      // người gõ tay không bao giờ tích đủ thành một mã. Chữ số vẫn đi tiếp
      // xuống ô nhập như cũ -- dòng này không chặn phím nào.
      if (event.key.length === 1) {
        scanBuffer += event.key;
        clearTimeout(scanTimer);
        scanTimer = setTimeout(() => { scanBuffer = ''; }, 180);
      }
      if (event.key === 'Enter' && looksLikeScan(scanBuffer)) {
        event.preventDefault();
        const code = scanBuffer; scanBuffer = '';
        scan(code);
        return;
      }
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
          const id = field.id;
          if (/^[0-9]$/.test(event.key)) {
            event.preventDefault();
            const cur = (qty[id] === '0' || qty[id] === '') ? '' : qty[id];
            setQty(id, cur + event.key);
            markQtyTouched(id);
            return;
          }
          if (event.key === 'Backspace') {
            event.preventDefault();
            setQty(id, qty[id].slice(0, -1) || '0');
            // Xoá cũng là một câu trả lời: người đã cầm lấy ô này rồi.
            markQtyTouched(id);
            return;
          }
        }
      }
      // PHÍM XÁC NHẬN CỦA WEB LÀ `Enter`, KHÔNG PHẢI `#`.
      //
      // Người dùng thật ở đây gõ bằng BÀN PHÍM SỐ RỜI, và bàn phím số rời
      // KHÔNG CÓ phím `#` -- nó có 0-9, `.`, `/`, `*`, `-`, `+`, Num Lock và
      // Enter, hết. Trên bàn phím đầy đủ `#` là Shift+3, tức là người đứng máy
      // phải với sang cụm phím chính và bấm hai phím để xác nhận một con số họ
      // vừa gõ bằng một tay ở cụm số. Màn hình lại đang in `#` như thể đó là
      // một phím có thật trên thiết bị của họ.
      //
      // `*` thì NGƯỢC LẠI -- bàn phím số rời CÓ `*` -- nên phím quay lại giữ
      // nguyên. Thay đổi ở đây cố ý không đối xứng, vì phần cứng không đối xứng.
      //
      // ESP KHÔNG ĐỔI: bàn phím màng của thiết bị có `#` vật lý và firmware vẫn
      // dùng nó. Bảng đối chiếu hai bên ở docs/KIOSK_ESP_PARITY.md §2.
      //
      // `event.key === 'Enter'` bắt CẢ HAI phím Enter -- Enter cụm chính và
      // Enter cụm số. Chúng chỉ khác nhau ở `event.code`
      // (`Enter` / `NumpadEnter`), còn `key` đều là `'Enter'`. Vì vậy TUYỆT ĐỐI
      // không thêm một nhánh `event.code === 'NumpadEnter'` bên cạnh: nó sẽ
      // khớp lần thứ hai trên cùng một lần bấm và bắn hành động hai lần.
      if (state === 'ask-rework') {
        // 1 = CÓ (nhập số), 2/Enter = tiếp tục không có, * = quay lại.
        if (event.key === '1') { event.preventDefault(); chooseRework(); }
        else if (event.key === '2' || event.key === 'Enter') { event.preventDefault(); chooseNoRework(); }
        else if (event.key === '*') { event.preventDefault(); show('quantity-defect'); focusQuantity('defect-qty'); }
        return;
      }
      if (state === 'finish-confirm') {
        if (event.key === '1' || event.key === 'Enter') { event.preventDefault(); finish(); }
        else if (event.key === '*' || event.key === '2') { event.preventDefault(); backFromConfirmation(); }
        return;
      }
      // Màn nhập số: Enter xác nhận, * quay lại.
      // Chữ số do chính ô <input type=number> nhận, không chặn ở đây.
      if (event.key === 'Enter') {
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
  QTY_IDS.forEach(id => {
    const qtyInput = document.getElementById(id);
    if (!qtyInput) return;

    // CHỌN HẾT số 0 mặc định thay vì XOÁ TRẮNG ô. Gõ chữ số đầu tiên vẫn thay
    // chỗ số 0 y như cũ (đúng cái "nhập cho nhanh" mà bản cũ nhắm tới), nhưng
    // ô không bao giờ rỗng -- nên màn hình luôn hiện đúng con số sắp được ghi.
    // Ô rỗng là thứ đã làm người đứng máy tin mình đã nhập trong khi hệ thống
    // đọc ra 0.
    const selectAll = () => { try { qtyInput.select(); } catch (_) {} };
    qtyInput.addEventListener('focus', selectAll);
    qtyInput.addEventListener('pointerup', selectAll);

    // Đường nhập KHÔNG qua keydown: bàn phím mềm/Gboard/IME (keydown bắn
    // key='Unidentified', keyCode 229, KHÔNG mang chữ số), dán, đọc chính tả,
    // nút tăng-giảm của <input type=number>. Trình duyệt đã ghi thẳng vào ô;
    // kéo nó về state để state vẫn là nguồn sự thật duy nhất, VÀ đánh dấu
    // touched -- nếu không, người gõ bằng bàn phím điện thoại sẽ bị coi là
    // chưa nhập gì và kẹt vĩnh viễn ở màn nhập số. (`beforeinput` không cần
    // nghe riêng: `input` bắn sau MỌI lần chèn, kể cả khi IME kết thúc soạn
    // thảo.)
    qtyInput.addEventListener('input', () => { setQty(id, qtyInput.value); markQtyTouched(id); });

    // Trên màn nhập số, ô này là ĐÍCH DUY NHẤT của bàn phím mềm. Nếu focus
    // rời đi mà vẫn đang ở màn đó (chuyển màn xong focus không dính, người
    // chạm ra vùng trống, bàn phím mềm tự đóng...), trả focus về -- nếu
    // không, chữ số gõ bằng bàn phím mềm rơi vào hư không và ô đứng yên ở 0.
    // Bỏ qua khi focus đi sang chính các nút của màn đó, để không cướp cú bấm.
    qtyInput.addEventListener('focusout', event => {
      if (QUANTITY_INPUT[state] !== id) return;
      // Bảng "Mô phỏng quét QR" có ô chọn riêng: đòi lại focus lúc nó đang mở
      // sẽ làm không bấm được gì trong đó.
      if (demoIsOpen()) return;
      const to = event.relatedTarget;
      if (to && to.closest && (to.closest(`#screen-${state}`) || to.closest('#demo-panel, #demo-toggle'))) return;
      // Đòi lại NGAY trong cùng nhịp: nếu đợi tới rAF thì vẫn còn một cửa sổ
      // vài mili-giây không ô nào nhận được chữ -- đúng khe mà bàn phím mềm
      // làm rơi chữ số. rAF giữ lại làm lớp đỡ cho trình duyệt nào không cho
      // focus lại ngay trong focusout.
      const reclaim = () => {
        if (QUANTITY_INPUT[state] === id && document.activeElement !== qtyInput) {
          qtyInput.focus({preventScroll:true});
        }
      };
      reclaim();
      requestAnimationFrame(reclaim);
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
  const demoBusy = document.getElementById('demo-busy');
  const demoError = document.getElementById('demo-error');
  // Mọi thứ khoá được trong lúc chờ. Khoá bằng `disabled` -- kích thước nút
  // không đổi một pixel nào, khác hẳn việc thay nội dung bằng chữ "đang tải".
  const demoControls = ['demo-employee','demo-operation','demo-scan-employee','demo-copy-employee',
    'demo-scan-operation','demo-copy-operation','demo-refresh'].map(id => document.getElementById(id));
  let demoInflight = 0;
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

  // Chỉ báo chờ KHÔNG được chiếm chỗ trong luồng: thanh 2px nằm absolute trên
  // viền dưới của đầu bảng. Trước đây #demo-loading là một block chữ chờ
  // cao ~70px chèn ngay trên #demo-content, nên mỗi lần làm mới -- kể cả lần
  // tự làm mới 10 giây/lần trong lúc người ta đang quét -- toàn bộ select, nút
  // và ô QR bị đẩy xuống rồi nhảy ngược lên. Đó chính là cú nhảy layout này.
  function setDemoBusy(on) {
    demoInflight = Math.max(0, demoInflight + (on ? 1 : -1));
    const busy = demoInflight > 0;
    demoPanel.dataset.demoState = busy ? 'loading' : (demoLoaded ? 'ready' : 'idle');
    demoPanel.setAttribute('aria-busy', busy ? 'true' : 'false');
    demoBusy.setAttribute('aria-hidden', busy ? 'false' : 'true');
    demoControls.forEach(el => { if (el) el.disabled = busy; });
  }
  // Lỗi là phần tử CUỐI bảng: hiện nó ra không đẩy bất cứ control nào bên trên.
  function setDemoError(message='') {
    demoError.textContent = message;
    demoError.hidden = !message;
  }

  function showTutorialDemoFallback(reason='') {
    demoEmployee.innerHTML='';
    demoOperation.innerHTML='';
    ensureTutorialDemoOptions();
    demoLoaded=true;
    updateDemoQr();
    setDemoError('');
    demoPanel.dataset.demoState='ready';
    if (reason) document.getElementById('scan-status').textContent='Đang dùng dữ liệu hướng dẫn dự phòng';
  }

  // Chữ ký của một danh sách: nếu lần làm mới trả về đúng dữ liệu cũ thì KHÔNG
  // dựng lại option nào. Lần tự làm mới 10 giây/lần vì thế im lặng tuyệt đối --
  // không chớp ô QR, không đóng dropdown đang mở, không đổi chiều cao.
  function optionsSignature(list, toText, toQr) {
    return (list || []).map(x => `${x.id}\u0001${toQr(x)}\u0001${toText(x)}`).join('\u0002');
  }
  function renderedSignature(select) {
    return [...select.options].map(o => `${o.value}\u0001${o.dataset.qr || ''}\u0001${o.textContent}`).join('\u0002');
  }
  function fillSelect(select, list, toText, toQr, emptyLabel) {
    select.innerHTML = '';
    (list || []).forEach(item => {
      const option = document.createElement('option');
      option.value = item.id; option.dataset.qr = toQr(item);
      option.textContent = toText(item);
      select.appendChild(option);
    });
    if (!select.options.length) select.innerHTML = `<option value="">${emptyLabel}</option>`;
  }

  // `silent`: lần tự làm mới nền -- không chỉ báo, không chớp gì cả. Chỉ lần do
  // người dùng bấm (mở bảng / "Tải lại danh sách") mới bật thanh chờ.
  async function loadDemoData(force=false, {silent=false}={}) {
    if (demoLoaded && !force) return;
    const selectedEmployee = demoEmployee.value;
    const selectedOperation = demoOperation.value;
    const employeeText = emp => `${emp.employee_no} · ${emp.name}${emp.department ? ` · ${emp.department}` : ''}`;
    const employeeQrOf = emp => emp.qr || `WF|EMP|${emp.employee_no}`;
    const operationText = op => `${op.po_code || '-'} · ${op.part_code || '-'} · ${op.code} · ${op.name}`;
    const operationQrOf = op => op.qr || `WF|OP|${op.code}`;
    // Giữ nguyên màn hình cũ cho tới khi có response: KHÔNG ẩn #demo-content,
    // không xoá option nào ở đây. Thất bại thì người dùng vẫn còn đúng danh
    // sách đang cầm trên tay.
    if (!silent) setDemoBusy(true);
    try {
      const request=api(`${API_BASE}/demo-data`);
      const data=tutorialMode
        ? await Promise.race([
            request,
            new Promise((_,reject)=>setTimeout(()=>reject(new Error('demo-data timeout')),6000))
          ])
        : await request;
      if (renderedSignature(demoEmployee) !== optionsSignature(data.employees, employeeText, employeeQrOf)) {
        fillSelect(demoEmployee, data.employees, employeeText, employeeQrOf, 'Chưa có nhân viên hoạt động');
      }
      if (renderedSignature(demoOperation) !== optionsSignature(data.operations, operationText, operationQrOf)) {
        fillSelect(demoOperation, data.operations, operationText, operationQrOf, 'Chưa có công đoạn từ lệnh đang chạy');
      }
      ensureTutorialDemoOptions();
      if (selectedEmployee && [...demoEmployee.options].some(x => x.value === selectedEmployee)) demoEmployee.value = selectedEmployee;
      if (selectedOperation && [...demoOperation.options].some(x => x.value === selectedOperation)) demoOperation.value = selectedOperation;
      demoLoaded = true; updateDemoQr(); setDemoError('');
    } catch (error) {
      if (tutorialMode) {
        showTutorialDemoFallback(error.message);
        return;
      }
      // The roster is signed-in-only now (it carries every badge QR). A real
      // terminal never needs it -- the scanner types into the input -- so this
      // says who can open it rather than reading as a kiosk failure.
      setDemoError(String(error.code || '').includes('401') || error.code === 'AUTH_REQUIRED'
        ? 'Danh sách mô phỏng chỉ dành cho tài khoản đã đăng nhập. Máy quét thật vẫn hoạt động bình thường.'
        : `Không tải được dữ liệu mô phỏng: ${error.message}`);
    } finally {
      if (!silent) setDemoBusy(false);
      else demoPanel.dataset.demoState = demoLoaded ? 'ready' : 'idle';
    }
  }
  function openDemo() {
    // Mở bảng giữa chừng thì không được reset màn dưới tay người đang thao
    // tác, nhưng cũng không được gỡ lần trả-về mà một finish thành công đã cắm.
    if (state !== 'finished') cancelReset();
    demoPanel.classList.add('open'); demoPanel.setAttribute('aria-hidden','false');
    demoToggle.setAttribute('aria-expanded','true'); loadDemoData(true);
  }
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
    reload: () => loadDemoData(true),
    scanEmployee: () => scan(employeeQr()),
    scanOperation: () => scan(operationQr()),
    // Feed an arbitrary payload through the same path a scanner gun uses --
    // the demo selects can only offer QRs that exist in the demo dataset.
    scan: qr => scan(String(qr || '')),
    // Đưa một con số phiên bản của máy chủ vào ĐÚNG hàm mà heartbeat gọi.
    // Không có lối này thì bài kiểm tự động cập nhật phải chờ trọn một nhịp
    // heartbeat (30 giây) cho MỖI lần đo, và "chờ 30 giây rồi xem có gì xảy ra
    // không" là hình dạng của một bài kiểm chập chờn. Đây là cùng một hàm, cùng
    // một điều kiện -- không phải một đường tắt bỏ qua luật nào.
    applyServerVersion: v => reloadIfNewVersionAvailable(String(v || '')),
    loadedVersion: () => loadedVersion
  };

  demoToggle.addEventListener('click', openDemo);
  demoClose.addEventListener('click', closeDemo);
  document.getElementById('demo-refresh').addEventListener('click', () => loadDemoData(true));
  demoEmployee.addEventListener('change', updateDemoQr); demoOperation.addEventListener('change', updateDemoQr);
  setInterval(() => { if (demoIsOpen()) loadDemoData(true, {silent:true}); }, 10000);
  document.getElementById('demo-scan-employee').addEventListener('click', () => scan(employeeQr()));
  document.getElementById('demo-scan-operation').addEventListener('click', () => scan(operationQr()));
  document.getElementById('demo-copy-employee').addEventListener('click', () => copyText(employeeQr()));
  document.getElementById('demo-copy-operation').addEventListener('click', () => copyText(operationQr()));

  // Camera điện thoại đọc được mã -> đi vào ĐÚNG scan() mà máy quét USB dùng.
  // Không có đường tắt nào khác: mọi kiểm tra và mọi luật nghiệp vụ nằm sau
  // <API_BASE>/scan, và cả hai nguồn quét đều phải đi qua đó.
  document.addEventListener('kiosk:camera-scan', event => {
    const payload = event.detail && event.detail.payload;
    if (payload) scan(payload);
  });

  // BÀN PHÍM SỐ CẢM ỨNG.
  //
  // Chỉ dựng trên thiết bị con trỏ THÔ (điện thoại, máy bảng). Trạm cố định có
  // bàn phím rời và máy quét USB: thêm một bảng số ở đó là thêm một vùng chạm
  // chồng lên luồng đang chạy tốt, và mọi bài kiểm hiện có đang khoá đúng
  // luồng ấy. Bảng số ghi thẳng vào state sản lượng (setQty/markQtyTouched),
  // đúng một đường với bàn phím cứng -- không có đường dữ liệu thứ hai.
  const touchDevice = window.matchMedia?.('(pointer: coarse)')?.matches
    || navigator.maxTouchPoints > 0;
  if (touchDevice) document.body.classList.add('kiosk-touch');
  const keypad = document.getElementById('qty-keypad');
  if (keypad) {
    keypad.addEventListener('click', event => {
      const key = event.target.closest('[data-key]');
      if (!key) return;
      const id = QUANTITY_INPUT[state];
      if (!id) return;
      const action = key.dataset.key;
      if (action === 'back') setQty(id, qty[id].slice(0, -1) || '0');
      else if (action === 'clear') setQty(id, '0');
      else setQty(id, qty[id] === '0' ? action : qty[id] + action);
      // Mọi phím -- kể cả Xoá -- đều là một câu trả lời của con người. Không
      // đánh dấu thì màn xác nhận vẫn coi số 0 mặc định là "chưa ai nhập".
      markQtyTouched(id);
    });
  }

  const hcmClock = new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  const updateClock = () => document.getElementById('clock').textContent = hcmClock.format(new Date());
  updateClock(); setInterval(updateClock, 1000);
  sendHeartbeat(); setInterval(sendHeartbeat, 30000);
  window.addEventListener('online', sendHeartbeat);
  window.addEventListener('beforeunload', () => navigator.sendBeacon?.(`${API_BASE}/heartbeat`, new Blob([JSON.stringify({device_uuid:deviceUuid,device_name:'Web Kiosk Demo',ui_state:'CLOSING',health_state:'OK',queue_size:0})], {type:'application/json'})));
  reset();
})();
