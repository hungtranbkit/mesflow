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
  const resultEl = layer.querySelector('#camera-result');
  const resultKind = layer.querySelector('#camera-result-kind');
  const resultTitle = layer.querySelector('#camera-result-title');
  const resultSub = layer.querySelector('#camera-result-sub');
  const resultNext = layer.querySelector('#camera-result-next');

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
  let audioUnlocked = false;
  let lastResult = null;
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
  // ĐỌC ĐƯỢC MÃ khác với QUÉT THÀNH CÔNG. Ở đây mới chỉ có một chuỗi ký tự:
  // máy chủ chưa nói gì, mã có thể là tem sai, nhân viên nghỉ việc, công đoạn
  // đã đóng. Nên chỗ này chỉ nhấp nháy khung + rung -- tiếng "tít" dành riêng
  // cho lúc máy chủ đã trả lời ĐƯỢC (xem kiosk:scan-result bên dưới). Kêu ngay
  // ở đây thì người đứng máy nghe tiếng thành công rồi bỏ đi, trong khi màn
  // hình đang báo lỗi.
  function feedback() {
    frame?.classList.remove('hit');
    void frame?.offsetWidth;        // ép reflow để animation chạy lại từ đầu
    frame?.classList.add('hit');
    try { navigator.vibrate?.(40); } catch { /* iOS không có, không sao */ }
  }

  //: Một nốt vuông ngắn. Sóng vuông nghe rõ hơn sóng sin qua loa điện thoại
  //: trong tiếng máy xưởng, và tai người nhạy nhất quanh 1-2 kHz.
  function tone(freq, seconds, delay = 0, volume = 0.16) {
    if (!audio) return;
    try {
      const at = audio.currentTime + delay;
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = 'square';
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(volume, at + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + seconds);
      osc.connect(gain).connect(audio.destination);
      osc.start(at);
      osc.stop(at + seconds + 0.01);
    } catch { /* âm thanh là thứ tốt-thì-có, không được làm hỏng lần quét */ }
  }

  // Hai tiếng KHÁC HẲN nhau, không phải hai mức to nhỏ: người đeo tai chống ồn
  // ở xưởng phân biệt được cao/thấp chứ không phân biệt được to/nhỏ.
  function beepSuccess() { wakeAudio(); tone(1180, 0.12); }
  function beepError() { wakeAudio(); tone(300, 0.16); tone(220, 0.18, 0.2); }

  // AudioContext phải được TẠO và THẬT SỰ CHẠY trong một cử chỉ của người dùng.
  //
  // Trên iOS, `new AudioContext()` ra đời ở trạng thái 'suspended' và
  // `resume()` chỉ được chấp nhận bên trong một cử chỉ -- nhưng chừng đó vẫn
  // chưa đủ: WebKit chỉ mở khoá hẳn khi đã có một node CHẠY XONG trong chính
  // cử chỉ ấy. Nên phát một đoạn đệm 1 mẫu (hoàn toàn im lặng) ngay tại đây;
  // đó là thứ biến mọi tiếng bíp về sau từ im lặng thành nghe được.
  function primeAudio() {
    try {
      const Ctor = window.AudioContext || window.webkitAudioContext;
      if (!Ctor) return;
      if (!audio) audio = new Ctor();
      if (audio.state === 'suspended') audio.resume();
      const buffer = audio.createBuffer(1, 1, audio.sampleRate || 22050);
      const source = audio.createBufferSource();
      source.buffer = buffer;
      source.connect(audio.destination);
      source.start(0);
      audioUnlocked = true;
    } catch { audio = null; }
  }

  // iOS treo AudioContext lại khi khoá máy hoặc chuyển app. resume() ở đây là
  // nỗ lực tốt nhất -- nếu hệ điều hành từ chối thì lần chạm nút tiếp theo mở
  // lại được, và hình ảnh vẫn nói đủ.
  function wakeAudio() {
    try { if (audio && audio.state === 'suspended') audio.resume(); } catch { /* thôi */ }
  }

  // --- KẾT QUẢ QUÉT HIỆN NGAY TRÊN CAMERA ---------------------------------
  //
  // Lỗi thật gặp trên iPhone: quét được, máy chủ nhận đúng tên, nhưng lớp
  // camera phủ kín màn hình nên người dùng phải TẮT camera mới đọc được kết
  // quả. Ở xưởng, "tắt camera để xem rồi bật lại để quét tiếp" là bỏ hẳn lý do
  // dùng điện thoại. Thẻ này mang đúng nội dung màn bên dưới đang hiện, không
  // hơn: mọi câu chữ và mọi luật đều do kiosk.js quyết, module này chỉ vẽ.
  function clearResult() {
    lastResult = null;
    if (!resultEl) return;
    resultEl.hidden = true;
    resultEl.classList.remove('flash');
    layer.classList.remove('has-result');
  }

  function renderResult(detail) {
    const data = detail || {};
    lastResult = data;
    if (!resultEl) return;
    const ok = data.ok !== false;
    resultEl.dataset.kind = ok ? 'ok' : 'error';
    // "Đã quét:" là chữ người dùng đọc ra để biết máy ĐÃ ăn mã -- giữ nguyên
    // câu đó kể cả khi lỗi, vì mã thì vẫn đọc được, chỉ nghiệp vụ mới từ chối.
    if (resultKind) resultKind.textContent = ok ? `Đã quét: ${data.label || 'QR'}` : (data.label || 'Không nhận được mã');
    if (resultTitle) resultTitle.textContent = data.title || '';
    if (resultSub) resultSub.textContent = data.sub || '';
    if (resultNext) resultNext.textContent = data.next || '';
    resultEl.hidden = false;
    layer.classList.add('has-result');
    resultEl.classList.remove('flash');
    void resultEl.offsetWidth;      // ép reflow để nhịp nhấp nháy chạy lại
    resultEl.classList.add('flash');
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
      // Không có lần gọi máy chủ nào để sinh ra kiosk:scan-result, nên tiếng
      // báo lỗi phải phát ngay tại đây, nếu không lần quét này im lặng hoàn toàn.
      beepError();
      renderResult({ok:false, label:'Mất kết nối mạng', title:'Chưa gửi được mã',
        sub:value, next:'Giữ nguyên màn này, quét lại khi có mạng.'});
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
    clearResult();
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
    // Về màn chờ nghĩa là lượt của người vừa rồi đã khép lại -- tên của họ
    // không được nằm lại trên camera cho người kế tiếp đọc. Dọn thẻ ở ĐÂY chứ
    // không hẹn giờ riêng: kiosk.js đã có đúng một chỗ quyết định lúc nào một
    // lượt kết thúc (reset/scheduleReset), thêm đồng hồ thứ hai là thêm một
    // nguồn sự thật lệch pha với nó.
    if (name === 'ready') clearResult();
    if (!wanted) return;
    if (BLOCKED_SCREENS.has(name)) pause();
    else resume();
    setHint(name === 'ready' ? 'Đưa camera vào QR THẺ NHÂN VIÊN'
      : name === 'operation' ? 'Đưa camera vào QR CÔNG ĐOẠN' : '');
  });

  // Máy chủ đã trả lời: ĐÂY mới là lúc biết lần quét thành công hay không.
  //
  // Chỉ làm gì khi người dùng ĐÃ bật camera. Trạm cố định với máy quét USB
  // chưa bao giờ kêu tiếng nào, và một bản vá cho điện thoại không được tự
  // thêm âm thanh vào một cái máy đang chạy tốt ở xưởng. `wanted` còn đúng cả
  // khi camera đang tạm dừng ở màn nhập sản lượng -- tiếng bíp vẫn phải kêu ở
  // đó, vì người dùng vẫn đang cầm điện thoại.
  document.addEventListener('kiosk:scan-result', event => {
    if (!(running || paused || wanted)) return;
    const detail = event.detail || {};
    if (detail.ok === false) beepError(); else beepSuccess();
    renderResult(detail);
  });

  // Rời tab / khoá máy / chuyển app: tắt hẳn. Không quay khi không ai nhìn.
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { if (running) { paused = true; stopStream(); } }
    else if (wanted && paused) { wakeAudio(); resume(); }
  });
  window.addEventListener('pagehide', () => stopStream());
  window.addEventListener('online', () => { if (statusEl?.dataset.kind === 'error' && running) setStatus(''); });
  window.addEventListener('offline', () => {
    if (running) setStatus('Mất kết nối mạng — quét sẽ không gửi đi được.', 'error');
  });

  // Bấm nút camera là cử chỉ chính, nhưng không phải cử chỉ DUY NHẤT: người
  // dùng có thể bấm "Mô phỏng quét QR" hoặc một nút bất kỳ trước đó. Mở khoá ở
  // cử chỉ đầu tiên nào cũng được, một lần rồi thôi -- tiếng bíp khi đó nghe
  // được kể cả với máy quét USB cắm vào điện thoại qua OTG.
  const unlockOnce = () => {
    primeAudio();
    if (audioUnlocked) {
      document.removeEventListener('pointerdown', unlockOnce, true);
      document.removeEventListener('touchend', unlockOnce, true);
    }
  };
  document.addEventListener('pointerdown', unlockOnce, true);
  document.addEventListener('touchend', unlockOnce, true);

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
    audioState: () => (audio ? audio.state : 'none'),
    isAudioUnlocked: () => audioUnlocked,
    lastResult: () => lastResult,
  };
})();
