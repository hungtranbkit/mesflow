"""Camera điện thoại là một NGUỒN QUÉT, không phải một kiosk thứ hai.

Bài này đọc thẳng mã nguồn tĩnh, vì thứ cần khoá ở đây là RANH GIỚI kiến trúc
chứ không phải một hành vi chạy được:

  * camera không tự gọi API, không tự dựng luật nghiệp vụ -- nó chỉ phát ra
    chuỗi vừa đọc được, và luồng cũ (scan -> /api/kiosk-web/scan) làm phần còn
    lại. Ranh giới này là thứ giữ cho quyền, luật, và câu báo lỗi chỉ có MỘT
    bản;
  * đường máy quét USB/GM65 không bị đụng tới;
  * không có service worker, vì kiosk đã có cơ chế tự nạp lại theo phiên bản và
    một service worker phục vụ từ cache sẽ đánh nhau với đúng cơ chế đó.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'app/mesflow/web/static'
CAMERA_JS = STATIC / 'kiosk-camera.js'
KIOSK_JS = STATIC / 'kiosk.js'
KIOSK_HTML = ROOT / 'app/mesflow/web/templates/kiosk.html'
KIOSK_PY = ROOT / 'app/mesflow/web/kiosk.py'
VENDOR = STATIC / 'vendor/jsqr-1.4.0.js'


def _read(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f'{path} not present in this test image -- run from a real checkout')
    return path.read_text(encoding='utf-8')


def _code_only(source: str) -> str:
    """Bỏ chú thích, giữ nguyên chuỗi.

    Cần thật sự tách chú thích chứ không tìm chuỗi con: chính những dòng chú
    thích giải thích ranh giới ("không tự gọi /api/…") lại chứa đúng cái từ mà
    bài này cấm xuất hiện trong MÃ. Tìm thô sẽ đỏ vì lời giải thích, và cách
    duy nhất để xanh lại là xoá lời giải thích -- tức là bài kiểm phạt đúng
    thứ nó nên thưởng.
    """
    out, i, n = [], 0, len(source)
    quote = None
    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ''
        if quote:
            out.append(ch)
            if ch == '\\' and i + 1 < n:
                out.append(nxt); i += 2; continue
            if ch == quote:
                quote = None
            i += 1; continue
        if ch in ('"', "'", '`'):
            quote = ch; out.append(ch); i += 1; continue
        if ch == '/' and nxt == '/':
            while i < n and source[i] != '\n':
                i += 1
            continue
        if ch == '/' and nxt == '*':
            i += 2
            while i + 1 < n and not (source[i] == '*' and source[i + 1] == '/'):
                i += 1
            i += 2; continue
        out.append(ch); i += 1
    return ''.join(out)


# --- ranh giới: camera KHÔNG chạm nghiệp vụ ------------------------------

def test_camera_khong_tu_goi_api_nao():
    """Gọi API thẳng từ đây là dựng một luồng nghiệp vụ thứ hai."""
    source = _code_only(_read(CAMERA_JS))
    for forbidden in ('fetch(', 'XMLHttpRequest', '/api/', 'MFNet'):
        assert forbidden not in source, f'kiosk-camera.js không được tự {forbidden}'


def test_camera_chi_phat_su_kien_va_kiosk_js_lang_nghe():
    camera = _read(CAMERA_JS)
    kiosk = _read(KIOSK_JS)
    assert "dispatchEvent(new CustomEvent('kiosk:camera-scan'" in camera
    assert "addEventListener('kiosk:camera-scan'" in kiosk
    # Và chuỗi đó phải đi vào ĐÚNG hàm mà máy quét USB dùng.
    handler = kiosk[kiosk.index("addEventListener('kiosk:camera-scan'"):]
    assert 'scan(payload)' in handler[:400], handler[:400]


def test_duong_may_quet_usb_khong_bi_dung_toi():
    """Hồi quy quan trọng nhất: trạm cố định phải chạy y như trước."""
    kiosk_js = _read(KIOSK_JS)
    html = _read(KIOSK_HTML)
    assert 'scanner-input' in html
    assert "input.addEventListener('keydown'" in kiosk_js
    assert 'focusScanner' in kiosk_js


# --- chống quét trùng ----------------------------------------------------

def test_cua_so_chong_trung_nam_trong_khoang_da_chot():
    source = _read(CAMERA_JS)
    match = re.search(r'DUPLICATE_WINDOW_MS\s*=\s*(\d+)', source)
    assert match, 'không tìm thấy cửa sổ chống quét trùng'
    window_ms = int(match.group(1))
    assert 1500 <= window_ms <= 2000, f'{window_ms}ms nằm ngoài khoảng 1500-2000ms đã chốt'


def test_chong_trung_theo_MA_chu_khong_theo_thoi_gian_thuan():
    """Chặn theo thời gian thuần sẽ nuốt mất lần quét công đoạn ngay sau thẻ."""
    source = _read(CAMERA_JS)
    assert 'value === lastPayload' in source, 'phải so CHÍNH mã, không chỉ so thời gian'


# --- riêng tư: camera tắt hẳn khi không dùng -----------------------------

def test_tat_camera_la_dung_track_chu_khong_chi_an_the_video():
    source = _read(CAMERA_JS)
    assert 'track.stop()' in source
    assert "addEventListener('visibilitychange'" in source
    assert "addEventListener('pagehide'" in source


def test_khong_gui_hinh_anh_di_dau():
    """Chỉ đọc QR tại chỗ. Không có đường nào đẩy khung hình lên máy chủ."""
    source = _code_only(_read(CAMERA_JS))
    for forbidden in ('toDataURL', 'toBlob', 'FormData', 'sendBeacon', 'WebSocket'):
        assert forbidden not in source, f'kiosk-camera.js không được dùng {forbidden}'


# --- bộ giải mã dự phòng cho iPhone --------------------------------------

def test_jsqr_duoc_nap_dong_chu_khong_nam_trong_trang():
    """250 KB không được nạp cho trạm cố định vốn không bao giờ dùng tới."""
    html = _read(KIOSK_HTML)
    assert 'jsqr' not in html.lower(), 'jsQR phải nạp động, không đặt <script> sẵn trong trang'
    source = _read(CAMERA_JS)
    assert 'loadFallbackDecoder' in source
    assert "createElement('script')" in source
    # Và chỉ nạp khi trình duyệt KHÔNG có BarcodeDetector.
    assert 'BarcodeDetector' in source


def test_thu_vien_nhung_kem_co_nguon_goc_ghi_ro():
    readme = _read(STATIC / 'vendor/README.md')
    assert 'jsqr@1.4.0' in readme
    assert 'Apache-2.0' in readme
    assert 'bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859' in readme
    if VENDOR.is_file():
        import hashlib
        digest = hashlib.sha256(VENDOR.read_bytes()).hexdigest()
        assert digest == 'bc40c8a15196236b2314db0856f72ca0b49980cd5413b8c852a7349f5fee0859', digest


# --- PWA tối thiểu, và KHÔNG service worker ------------------------------

def test_manifest_co_va_tro_dung_trang_kiosk():
    source = _read(KIOSK_PY)
    assert "@bp.get('/kiosk.webmanifest')" in source
    match = re.search(r'KIOSK_MANIFEST\s*=\s*(\{.*?\n\})', source, re.S)
    assert match, 'không tìm thấy KIOSK_MANIFEST'
    body = match.group(1)
    assert "'start_url': '/kiosk'" in body
    assert "'display': 'standalone'" in body
    html = _read(KIOSK_HTML)
    assert 'rel="manifest"' in html
    assert 'apple-mobile-web-app-capable' in html


def test_khong_co_service_worker_o_bat_ky_dau():
    """Service worker phục vụ từ cache sẽ giữ kiosk ở phiên bản cũ trong im lặng."""
    for path in (CAMERA_JS, KIOSK_JS, KIOSK_HTML):
        source = _code_only(_read(path))
        assert 'serviceWorker' not in source, f'{path.name} đăng ký service worker'
    assert not list(STATIC.glob('*service-worker*'))
    assert not list(STATIC.glob('sw.js'))


# --- màn hình điện thoại -------------------------------------------------

def test_viewport_chua_cho_tai_tho():
    html = _read(KIOSK_HTML)
    assert 'viewport-fit=cover' in html
    # Và vẫn giữ khoá phóng to: ô số focus mà trang tự zoom là lỗi đã biết.
    assert 'user-scalable=no' in html


def test_css_dung_safe_area_va_khong_dung_has():
    css = _read(STATIC / 'kiosk.css')
    assert 'env(safe-area-inset-bottom)' in css
    assert 'env(safe-area-inset-top)' in css
    # :has() chỉ có từ Safari 15.4; máy ở xưởng không ai cập nhật.
    assert ':has(' not in css, 'không được phụ thuộc :has()'


def test_ban_phim_so_nam_TRONG_man_dang_dung_no():
    """Hiện/ẩn bảng số theo một biến riêng là nguồn sự thật THỨ HAI.

    Đã hỏng thật một lần: bài kiểm chống chạm-xuyên-màn bật/tắt `.active` trực
    tiếp để đo toạ độ nút, không đi qua show(). Bảng số khi đó vẫn tưởng đang ở
    màn nhập số nên chiếm chỗ trong CẢ màn xác nhận, đẩy nút XÁC NHẬN lên chồng
    vào vùng nút TIẾP TỤC -- đúng cái chồng vùng mà P0 trước đã sửa. Cho bảng số
    nằm BÊN TRONG màn đang dùng nó thì màn ẩn là nó ẩn theo, không ai phải nhớ.
    """
    kiosk = _read(KIOSK_JS)
    assert "host.appendChild(keypadNode)" in kiosk
    assert "keypadNode.hidden = true" in kiosk
    css = _read(STATIC / 'kiosk.css')
    assert 'body.kiosk-touch .qty-keypad:not([hidden])' in css


def test_ban_phim_so_chi_dung_state_san_luong_co_san():
    """Bảng số KHÔNG được là đường dữ liệu thứ hai cho sản lượng."""
    kiosk = _read(KIOSK_JS)
    block = kiosk[kiosk.index("const keypad = document.getElementById('qty-keypad')"):]
    block = block[:1200]
    assert 'setQty(' in block
    assert 'markQtyTouched(' in block
    assert '.value =' not in block, 'phải ghi vào state, không ghi thẳng vào DOM'
