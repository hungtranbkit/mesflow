# MESFlow — bộ video hướng dẫn chi tiết (Ubuntu/Linux)

Bộ tutorial mới tạo nhiều video nhỏ thay vì một video dài.

Các video:
- 00 overview
- 01 Dashboard
- 02 Production Order
- 03 Template
- 04 Material Flow / tiến trình
- 05 Session
- 06 Ngoại lệ Session
- 07 Nhân viên + QR
- 08 Quản lý Kiosk
- 09 Kiosk cho công nhân
- 10 Lịch làm việc
- 11 User & RBAC
- 12 System Logs

Mặc định video chạy chậm hơn và hiển thị annotation giải thích từng khu vực.

## Chạy toàn bộ

```bash
cd /opt/mesflow

MESFLOW_TUTORIAL_USERNAME='admin' \
MESFLOW_TUTORIAL_PASSWORD='Admin@123456' \
bash scripts/make-user-guide-video.sh http://127.0.0.1:8080
```

Không cần quyền ghi vào `/opt/mesflow`. NPM/Playwright chạy trong:

```text
~/.mesflow-video
```

Video xuất ra:

```text
~/mesflow-user-guide/
```

## Chạy một video

```bash
MESFLOW_TUTORIAL_USERNAME='admin' \
MESFLOW_TUTORIAL_PASSWORD='Admin@123456' \
bash scripts/make-one-user-guide-video.sh kioskUser http://127.0.0.1:8080
```

Tên module:
`overview`, `dashboard`, `po`, `templates`, `material`, `sessions`,
`exceptions`, `employees`, `kioskAdmin`, `kioskUser`, `calendar`, `users`, `logs`.

## Làm chậm hơn nữa

```bash
MESFLOW_TUTORIAL_WAIT_MS=4500 \
MESFLOW_TUTORIAL_LONG_WAIT_MS=7000 \
MESFLOW_TUTORIAL_STEP_WAIT_MS=5200 \
MESFLOW_TUTORIAL_USERNAME='admin' \
MESFLOW_TUTORIAL_PASSWORD='Admin@123456' \
bash scripts/make-user-guide-video.sh http://127.0.0.1:8080
```

Kiosk operator video chỉ thay đổi DOM cục bộ để minh họa các bước; không submit dữ liệu sản xuất.


## Intro + giọng đọc tiếng Việt

Bản 65.8.44.37 tự thử tạo voice-over sau khi quay xong. Cài một lần trên Ubuntu:

```bash
cd /opt/mesflow
bash scripts/setup-tutorial-audio-ubuntu.sh
```

Sau đó chạy bộ video như bình thường. `edge-tts` được ưu tiên vì giọng Việt tự nhiên hơn; nếu không có thì dùng `espeak-ng` offline.

Mặc định:
- voice: `vi-VN-HoaiMyNeural`
- tốc độ đọc: `-8%`
- intro: 4 giây
- output có giọng: `~/mesflow-user-guide/final/`

Có thể đổi giọng/tốc độ:

```bash
MESFLOW_TTS_VOICE='vi-VN-NamMinhNeural' \
MESFLOW_TTS_RATE='-12%' \
MESFLOW_TUTORIAL_USERNAME='admin' \
MESFLOW_TUTORIAL_PASSWORD='Admin@123456' \
bash scripts/make-user-guide-video.sh http://127.0.0.1:8080
```

Tắt voice-over bằng `MESFLOW_TUTORIAL_WITH_VOICE=0`.


## Dataset đào tạo đầy đủ tính năng

Bản 65.8.44.39 có thể tạo một dataset `TUT39-*` chuyên dùng cho quay video:
PO, Template, nhân viên, trạm, session bình thường, đạt/lỗi/sửa được, QC,
session mở quá lâu, zero quantity, thiếu trạm, overlap, invalid time,
exception workflow, kiosk degraded, offline queue/conflict và system error log.

Dataset **không tự tạo mặc định** vì đây là thao tác ghi database.

Trên database test/đào tạo:

```bash
MESFLOW_TUTORIAL_SEED_DATA=1 \
MESFLOW_TUTORIAL_USERNAME='admin' \
MESFLOW_TUTORIAL_PASSWORD='Admin@123456' \
bash scripts/make-user-guide-video.sh http://127.0.0.1:8080
```

Nếu `MESFLOW_ENV=production`, seeder cố ý từ chối. Chỉ khi server đó thực sự dùng
database đào tạo/test và bạn chủ động chấp nhận tạo record TUT39:

```bash
MESFLOW_TUTORIAL_SEED_DATA=1 \
MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1 \
MESFLOW_TUTORIAL_USERNAME='admin' \
MESFLOW_TUTORIAL_PASSWORD='Admin@123456' \
bash scripts/make-user-guide-video.sh http://127.0.0.1:8080
```

Xem trạng thái:

```bash
MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1 \
bash scripts/prepare-tutorial-data.sh status
```

Xóa duy nhất dữ liệu tutorial:

```bash
MESFLOW_TUTORIAL_DATA_ALLOW_PRODUCTION=1 \
bash scripts/prepare-tutorial-data.sh cleanup
```

Cleanup chỉ nhắm record có prefix/marker `TUT-*` và `TUT39:*`.
