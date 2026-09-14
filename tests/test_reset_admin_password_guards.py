"""Script cứu hộ đổi mật khẩu admin không được có mặc định.

LỖI THẬT (SEC-15, audit 2026-09-14). `scripts/reset-admin-password.sh` mở đầu
bằng ``PASSWORD="${2:-Admin@123456}"``. Chạy script mà quên tham số thứ hai là
đặt đúng chuỗi đó lên máy đích -- và chuỗi đó nằm CÔNG KHAI trong repo, kể cả
trong một report ghi kèm địa chỉ https://mesflow.net ngay cùng một câu.

Hậu quả là vòng lặp im lặng: đổi mật khẩu xong, một cú chạy script vô ý khôi
phục lại đúng mật khẩu vừa bị loại bỏ, và không ai biết.

Bài này đọc chính tệp script (nó là bash, không import được), nên nó khoá được
hợp đồng mà không cần chạy script -- chạy thật sẽ sửa .env của máy đang chạy.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/reset-admin-password.sh'
SOURCE = SCRIPT.read_text(encoding='utf-8')

#: Những chuỗi đã nằm công khai trong repo này.
BURNED = ('Admin@123456', 'changeme', 'CHANGE_ME', 'dev-only', 'password', '123456')


def test_there_is_no_default_password():
    """Gốc của lỗi: ``${2:-<gì đó>}`` là một mặc định, và mọi mặc định ở đây
    đều đã công khai."""
    match = re.search(r'PASSWORD="\$\{2:-([^}]*)\}"', SOURCE)
    assert match, 'không tìm thấy dòng gán PASSWORD'
    assert match.group(1) == '', f'vẫn còn mặc định: {match.group(1)!r}'


def test_it_refuses_to_run_without_a_password():
    assert 'Thiếu mật khẩu' in SOURCE
    assert re.search(r'if \[ -z "\$PASSWORD" \]', SOURCE), 'không kiểm mật khẩu rỗng'


def test_every_burned_string_is_rejected_by_name():
    """Không đủ nếu chỉ bỏ mặc định: người ta vẫn có thể GÕ lại đúng chuỗi đó."""
    case = SOURCE[SOURCE.index('case "$PASSWORD" in'):]
    case = case[:case.index('esac')]
    for burned in BURNED:
        assert burned in case, f'{burned!r} không bị từ chối'


def test_a_minimum_length_is_enforced():
    assert '${#PASSWORD}' in SOURCE
    match = re.search(r'-lt (\d+)', SOURCE)
    assert match and int(match.group(1)) >= 12


def test_the_committed_report_no_longer_spells_the_password_out():
    """Che trong cây làm việc KHÔNG xoá khỏi lịch sử git -- giá trị đó vẫn phải
    coi là đã lộ và phải đổi trên host. Bài này chỉ canh nó thôi lan thêm."""
    report = (Path(__file__).resolve().parents[1]
              / 'reports/UI_AUDIT_MESFLOW_NET_20260909.md')
    if not report.is_file():
        return
    text = report.read_text(encoding='utf-8')
    assert 'Admin@123456' not in text
    assert 'REDACTED' in text
    # ...và phải nói rõ rằng che không đủ, phải đổi mật khẩu thật.
    assert 'lịch sử git' in text and 'đổi' in text
