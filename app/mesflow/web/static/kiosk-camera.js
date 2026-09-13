// CAMERA ĐIỆN THOẠI LÀ MỘT NGUỒN QUÉT, KHÔNG PHẢI MỘT KIOSK THỨ HAI.
//
// Máy kiosk cố định nhận mã qua máy quét USB/GM65: nó gõ chuỗi rồi Enter, và
// kiosk.js gửi chuỗi đó tới /api/kiosk-web/scan. Camera trên điện thoại làm
// ĐÚNG việc đó, chỉ khác ở chỗ chuỗi đến từ ảnh thay vì bàn phím. Vì vậy module
// này KHÔNG biết gì về nghiệp vụ: nó không gọi API, không đọc nhân viên, không
// bắt đầu hay kết thúc session. Nó chỉ phát ra một sự kiện mang chuỗi vừa đọc
// được, và kiosk.js -- luồng duy nhất đã có -- quyết định phần còn lại.
//
// Nhờ ranh giới đó: mọi kiểm tra quyền, mọi luật nghiệp vụ, mọi thông báo lỗi
// đi qua đúng một đường như cũ; và đường máy quét USB không bị đụng tới một
// dòng nào.
//
// GIỚI HẠN CỦA iPHONE, đã tính từ đầu:
//   * Safari (và mọi trình duyệt trên iOS, vì đều dùng WebKit) KHÔNG có
//     BarcodeDetector -> phải giải mã bằng JavaScript. jsQR được nạp ĐỘNG, chỉ
//     khi bật camera và chỉ khi trình duyệt thiếu BarcodeDetector.
//   * navigator.vibrate không có trên iOS -> rung là tuỳ chọn, không phải điều
//     kiện để báo thành công. Âm thanh và nhấp nháy màn hình mới là tín hiệu
//     chính.
//   * getUserMedia đòi HTTPS (hoặc localhost). Trên http:// thường, nút bật
//     camera phải nói thẳng lý do thay vì im lặng hỏng.
//   * <video> phải có playsinline, nếu không iOS mở trình phát toàn màn hình
//     riêng và che mất giao diện.
(() => {
  'use strict';

  const layer = document.getElementById('camera-layer');
  const toggle = document.getElementById('camera-toggle');
  if (!layer || !toggle) return;

  const video = layer.querySelector('#camera-video');
  const statusEl = layer.querySelector('#camera-status');
  const hintEl = layer.querySelector('#camera-hint');
  const switchButton = layer.querySelector('#camera-switch');
  const closeButton = layer.querySelector('#camera-close');
  const frame = layer.querySelector('.camera-frame');

  //: Cùng một mã không được gửi lại trong khoảng này. Người cầm điện thoại giữ
  //: máy trước tem vài giây là chuyện bình thường, và camera đọc được 10 lần
  //: mỗi giây -- không chặn thì một lần giơ máy thành mười lần quét.
  const DUPLICATE_WINDOW_MS = 1800;
  //: Giải mã nhiều nhất chừng này lần mỗi giây. Cao hơn chỉ tốn pin và làm
  //: máy nóng; jsQR chạy trên luồng chính nên mỗi lần giải mã là một lần chặn.
  const DECODE_INTERVAL_MS = 90;
  //: Cạnh dài của khung ảnh đưa vào bộ giải mã. Ảnh 1280px không đọc được
  //: nhiều mã hơn ảnh 640px một cách đáng kể, nhưng tốn gấp bốn lần thời gian.
  const DECODE_MAX_EDGE = 640;
  const VENDOR_JSQR = '/static/vendor/jsqr-1.4.0.js';

  //: Màn nào KHÔNG được để camera che. Nhập sản lượng và xác nhận là lúc người
  //: ta cần nhìn bàn phím số và con số mình vừa gõ; camera lúc đó vừa vô dụng
  //: vừa che mất nội dung, và vẫn đang bật thì vừa tốn pin vừa quay khi không
  //: ai yêu cầu.
  const BLOCKED_SCREENS = new Set([
    'quantity-good', 'quantity-defect', 'ask-rework', 'quantity-rework', 'finish-confirm',
  ]);

  let stream = null;
  let running = false;
  let paused = false;              // tạm dừng vì màn nhập số, không phải do người tắt
  let wanted = false;              // người dùng ĐÃ bật camera (ý định, khác với đang chạy)
  let detector = null;             // BarcodeDetector nếu có
  let decodeQr = null;             // jsQR nếu phải dùng đường dự phòng
  let loopHandle = null;
  let lastPayload = '';
  let lastPayloadAt = 0;
  let devices = [];
  let deviceIndex = 0;
  let audio = null;
  let canvas = null;
  let canvasCtx = null;

  const secure = window.isSecureContext || location.hostname === 'localhost';
  const supported = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);

  function setStatus(text, kind = '') {
    if (!statusEl) return;
    statusEl.textContent = text || '';
    statusEl.dataset.kind = kind;
  }

  function setHint(text) { if (hintEl) hintEl.textContent = text || ''; }

  // --- tín hiệu đã đọc được mã -------------------------------------------
  //
  // Ba kênh cùng lúc, cố ý: người đứng máy có thể đang đeo găng (không cảm
  // được rung), ở xưởng ồn (không nghe được tiếng bíp), hoặc đang nhìn chỗ
  // khác (không thấy nhấp nháy). Một kênh hỏng thì hai kênh còn lại vẫn nói.
  function feedback() {
    frame?.classList.remove('hit');
    void frame?.offsetWidth;        // ép reflow để animation chạy lại từ đầu
    frame?.classList.add('hit');
    try { navigator.vibrate?.(40); } catch { /* iOS không có, không sao */ }
    beep();
  }

  function beep() {
    if (!audio) return;
    try {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = 'square';
      osc.frequency.value = 1180;
      gain.gain.setValueAtTime(0.0001, audio.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.16, audio.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + 0.12);
      osc.connect(gain).connect(audio.destination);
      osc.start();
      osc.stop(audio.currentTime + 0.13);
    } catch { /* âm thanh là thứ tốt-thì-có, không được làm hỏng lần quét */ }
  }

  // AudioContext phải được tạo/đánh thức TRONG một cử chỉ của người dùng, nếu
  // không iOS giữ nó ở trạng thái 'suspended' và mọi tiếng bíp về sau im lặng.
  function primeAudio() {
    try {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return;
      if (!audio) audio = new Ctor();
      if (audio.state === 'suspended') audio.resume();
    } catch { audio = null; }
  }

  // --- MẤT MẠNG: KHÔNG XẾP HÀNG HÀNH ĐỘNG NGHIỆP VỤ ----------------------
  //
  // Quyết định của V1, và lý do:
  //
  //   * Một lần QUÉT chỉ là tra cứu, gửi lại bao nhiêu lần cũng vô hại -- nên
  //     chẳng có gì để xếp hàng.
  //   * START/FINISH thì backend đã chống trùng thật (bảng kiosk_idempotency
  //     khoá theo request_id, xem WorkSessionRepository), nên gửi lại AN TOÀN.
  //     Nhưng "an toàn" ở đây chỉ có nghĩa là không tạo hai bản ghi. Một lệnh
  //     START bị giữ trong hàng đợi rồi bắn đi mười lăm phút sau vẫn tạo ra
  //     một session có giờ bắt đầu SAI -- dữ liệu sai mà không ai biết, tệ hơn
  //     hẳn một lỗi hiện ra trên màn hình.
  //
  // Nên: mất mạng thì nói thẳng, giữ nguyên mã vừa đọc, và để người đứng máy
  // quét lại khi có mạng. Không tự gửi, không tự xếp hàng.
  function offline() { return navigator.onLine === false; }

  function emit(payload) {
    const value = String(payload || '').trim();
    if (!value) return;
    if (offline()) {
      feedback();
      setStatus('Mất kết nối mạng — chưa gửi được mã. Giữ nguyên màn này, quét lại khi có mạng.', 'error');
      return;
    }
    const now = Date.now();
    // Chống quét trùng: CÙNG một mã trong cửa sổ ngắn chỉ tính một lần. Mã
    // KHÁC được cho qua ngay -- quét thẻ rồi quét công đoạn là hai mã liền
    // nhau, chặn theo thời gian thuần tuý sẽ nuốt mất cái thứ hai.
    if (value === lastPayload && now - lastPayloadAt < DUPLICATE_WINDOW_MS) return;
    lastPayload = value;
    lastPayloadAt = now;
    feedback();
    document.dispatchEvent(new CustomEvent('kiosk:camera-scan', { detail: { payload: value } }));
  }

  // --- vòng giải mã -------------------------------------------------------
  async function loadFallbackDecoder() {
    if (decodeQr) return decodeQr;
    if (window.jsQR) { decodeQr = window.jsQR; return decodeQr; }
    await new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = VENDOR_JSQR;
      script.onload = resolve;
      script.onerror = () => reject(new Error('không tải được bộ giải mã QR'));
      document.head.appendChild(script);
    });
    decodeQr = window.jsQR;
    if (!decodeQr) throw new Error('không tải được bộ giải mã QR');
    return decodeQr;
  }

  function frameImageData() {
    const width = video.videoWidth, height = video.videoHeight;
    if (!width || !height) return null;
    const scale = Math.min(1, DECODE_MAX_EDGE / Math.max(width, height));
    const w = Math.max(1, Math.round(width * scale));
    const h = Math.max(1, Math.round(height * scale));
    if (!canvas) { canvas = document.createElement('canvas'); canvasCtx = canvas.getContext('2d', { willReadFrequently: true }); }
    if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
    canvasCtx.drawImage(video, 0, 0, w, h);
    return canvasCtx.getImageData(0, 0, w, h);
  }

  async function decodeOnce() {
    if (detector) {
      const found = await detector.detect(video);
      if (found && found.length) return found[0].rawValue;
      return '';
    }
    if (!decodeQr) return '';
    const image = frameImageData();
    if (!image) return '';
    const result = decodeQr(image.data, image.width, image.height, { inversionAttempts: 'dontInvert' });
    return result ? result.data : '';
  }

  function scheduleLoop() {
    if (!running || paused) return;
    loopHandle = setTimeout(async () => {
      if (!running || paused) return;
      try {
        const payload = await decodeOnce();
        if (payload) emit(payload);
      } catch { /* một khung hỏng không được làm chết cả vòng quét */ }
      scheduleLoop();
    }, DECODE_INTERVAL_MS);
  }

  // --- vòng đời camera ----------------------------------------------------
  async function listCameras() {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      devices = all.filter(d => d.kind === 'videoinput');
    } catch { devices = []; }
    if (switchButton) switchButton.hidden = devices.length < 2;
  }

  async function openStream() {
    const constraints = devices.length > 1 && devices[deviceIndex]
      ? { video: { deviceId: { exact: devices[deviceIndex].deviceId } }, audio: false }
      // `ideal` chứ không `exact`: máy tính để bàn chỉ có webcam trước, và
      // `exact:'environment'` ở đó là OverconstrainedError -- tức là không
      // dùng thử được trên máy dev.
      : { video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false };
    return navigator.mediaDevices.getUserMedia(constraints);
  }

  function stopStream() {
    if (loopHandle) { clearTimeout(loopHandle); loopHandle = null; }
    running = false;
    // DỪNG HẲN track, không chỉ ẩn thẻ <video>. Track còn sống nghĩa là đèn
    // camera còn sáng và máy còn quay -- trong khi người dùng tin là đã tắt.
    if (stream) { stream.getTracks().forEach(track => { try { track.stop(); } catch { /* đã dừng */ } }); stream = null; }
    if (video) { try { video.pause(); } catch { /* ignore */ } video.srcObject = null; }
  }

  async function start() {
    if (running) return;
    if (!supported) { setStatus('Trình duyệt này không mở được camera.', 'error'); return; }
    if (!secure) {
      setStatus('Camera chỉ chạy trên HTTPS. Hãy mở trang bằng địa chỉ https://…', 'error');
      return;
    }
    setStatus('Đang mở camera…');
    try {
      stream = await openStream();
    } catch (error) {
      const name = error && error.name;
      if (name === 'NotAllowedError' || name === 'SecurityError')
        setStatus('Bạn đã từ chối quyền camera. Mở Cài đặt › Safari › Camera để cho phép, rồi thử lại.', 'error');
      else if (name === 'NotFoundError' || name === 'OverconstrainedError')
        setStatus('Không tìm thấy camera nào trên thiết bị này.', 'error');
      else if (name === 'NotReadableError')
        setStatus('Camera đang được ứng dụng khác sử dụng. Đóng ứng dụng đó rồi thử lại.', 'error');
      else
        setStatus(`Không mở được camera (${name || 'lỗi không rõ'}).`, 'error');
      return;
    }
    video.srcObject = stream;
    video.setAttribute('playsinline', '');   // iOS: không mở trình phát toàn màn hình
    video.muted = true;

    // HIỆN LỚP TRƯỚC KHI PHÁT, và KHÔNG chờ play().
    //
    // Đây là một cái bẫy thật, không phải chuyện lý thuyết: lớp camera còn
    // `display:none` cho tới khi có class `on`, mà WebKit KHÔNG bắt đầu phát
    // một MediaStream vào thẻ <video> đang ẩn -- lời hứa của play() không bao
    // giờ hoàn thành. Bản đầu `await video.play()` rồi mới thêm class, nên nó
    // tự khoá chính mình: màn hình đứng ở "Đang mở camera…" mãi mãi, trên
    // đúng iPhone là thiết bị đích.
    layer.classList.add('on');
    toggle.setAttribute('aria-pressed', 'true');
    toggle.textContent = 'Tắt camera';
    video.play().catch(() => { /* vài trình duyệt tự phát; không chặn luồng */ });

    // Bộ giải mã: ưu tiên API của trình duyệt, vì nó chạy ngoài luồng chính.
    detector = null;
    try {
      if ('BarcodeDetector' in window) {
        const formats = await window.BarcodeDetector.getSupportedFormats?.();
        if (!formats || formats.includes('qr_code')) detector = new window.BarcodeDetector({ formats: ['qr_code'] });
      }
    } catch { detector = null; }
    if (!detector) {
      setStatus('Đang chuẩn bị bộ giải mã…');
      try { await loadFallbackDecoder(); } catch {
        // Mở được camera nhưng không giải mã được thì coi như không dùng được:
        // trả về đúng trạng thái tắt, đừng để một lớp camera vô dụng nằm đè.
        stopStream();
        layer.classList.remove('on');
        toggle.setAttribute('aria-pressed', 'false');
        toggle.textContent = 'Camera điện thoại';
        setStatus('Không tải được bộ giải mã QR. Kiểm tra kết nối rồi thử lại.', 'error');
        return;
      }
    }

    await listCameras();
    running = true; paused = false;
    setStatus('');
    scheduleLoop();
  }

  function stop({ keepWanted = false } = {}) {
    stopStream();
    if (!keepWanted) wanted = false;
    layer.classList.remove('on');
    toggle.setAttribute('aria-pressed', 'false');
    toggle.textContent = 'Camera điện thoại';
    setStatus('');
  }

  // Tạm dừng: giữ Ý ĐỊNH bật của người dùng, nhưng thật sự tắt phần cứng. Quay
  // lại màn quét thì tự mở lại, không bắt bấm nút lần nữa.
  function pause() { if (!running && !wanted) return; paused = true; stopStream(); layer.classList.remove('on'); }
  async function resume() { if (!wanted || running) return; paused = false; await start(); }

  // --- nối vào luồng kiosk ------------------------------------------------
  document.addEventListener('kiosk:screen', event => {
    const name = event.detail && event.detail.name;
    if (!wanted) return;
    if (BLOCKED_SCREENS.has(name)) pause();
    else resume();
    setHint(name === 'ready' ? 'Đưa camera vào QR THẺ NHÂN VIÊN'
      : name === 'operation' ? 'Đưa camera vào QR CÔNG ĐOẠN' : '');
  });

  // Rời tab / khoá máy / chuyển app: tắt hẳn. Không quay khi không ai nhìn.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (running) { paused = true; stopStream(); } }
    else if (wanted && paused) resume();
  });
  window.addEventListener('pagehide', () => stopStream());
  window.addEventListener('online', () => { if (statusEl?.dataset.kind === 'error' && running) setStatus(''); });
  window.addEventListener('offline', () => {
    if (running) setStatus('Mất kết nối mạng — quét sẽ không gửi đi được.', 'error');
  });

  toggle.addEventListener('click', async () => {
    if (wanted) { stop(); return; }
    primeAudio();                   // phải nằm TRONG cử chỉ chạm, xem primeAudio
    wanted = true;
    await start();
    if (!running) wanted = false;   // mở hỏng thì đừng để nút kẹt ở trạng thái bật
  });
  closeButton?.addEventListener('click', () => stop());
  switchButton?.addEventListener('click', async () => {
    if (!devices.length) await listCameras();
    if (devices.length < 2) return;
    deviceIndex = (deviceIndex + 1) % devices.length;
    stopStream();
    await start();
  });

  // Nút chỉ hiện khi thiết bị thật sự mở được camera: một nút bấm vào là báo
  // lỗi thì thà đừng có.
  toggle.hidden = !supported;

  // Cho test và cho console của kỹ thuật viên: KHÔNG phải API nghiệp vụ.
  window.KioskCamera = {
    isRunning: () => running,
    isWanted: () => wanted,
    start, stop, pause, resume,
    // Đưa thẳng một chuỗi vào đúng đường mà camera dùng -- kể cả chặn trùng.
    emitForTest: emit,
    duplicateWindowMs: DUPLICATE_WINDOW_MS,
  };
})();
