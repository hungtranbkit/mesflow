"""Migration không được chờ khoá vô thời hạn -- và phải THẬT SỰ commit.

LỖI THẬT (DB-01, audit 2026-09-14). Toàn bộ chuỗi 0001->00NN chạy trong MỘT
transaction, và trong đó có `ALTER TABLE` cần ACCESS EXCLUSIVE trên
work_sessions (0044) cùng một lần viết lại cả bảng operations (0047 thêm cột
generated STORED). Nếu lúc ấy có dù chỉ MỘT transaction đang đọc còn mở -- một
autovacuum, một báo cáo chậm, một tab psql ai đó quên -- thì ALTER TABLE xếp
hàng VÔ THỜI HẠN, và mọi lệnh START/FINISH của kiosk lại xếp hàng sau nó. Cả
xưởng đứng, không có giới hạn, không có gì tự bỏ cuộc.

Đo được (PostgreSQL 17 thật, giữ một transaction đọc trên work_sessions):

    lock_timeout = 0     -> vẫn đang chờ khi bị giết ở giây thứ 12
    lock_timeout = '3s'  -> ERROR: canceling statement due to lock timeout
                            sau đúng 3 giây

BÀI HỌC THỨ HAI, và là lý do bài kiểm này canh cả việc COMMIT. Bản vá đầu tiên
đặt hai lệnh SET NGAY TRƯỚC `context.begin_transaction()`. `exec_driver_sql()`
trên Connection của SQLAlchemy 2.0 tự mở transaction ngầm, nên
`begin_transaction()` thấy đã có transaction và trở thành no-op: KHÔNG AI
COMMIT, cả chuỗi migration bị rollback khi đóng kết nối, và alembic vẫn thoát
mã 0. Dựng lại được: log Postgres cho thấy đủ mọi CREATE TABLE và mọi UPDATE
alembic_version, nhưng sau khi xong `information_schema.tables` = 0 dòng. Một
migration "thành công" mà không đổi gì là kiểu hỏng tệ nhất có thể đưa vào
deploy -- nên thứ tự hai dòng SET đó là hợp đồng, không phải chi tiết.
"""
from __future__ import annotations

import re
from pathlib import Path

ENV_PY = (Path(__file__).resolve().parents[1] / 'app/migrations/env.py').read_text(encoding='utf-8')


def test_a_lock_timeout_is_set_and_is_not_unlimited():
    assert "SET lock_timeout" in ENV_PY
    match = re.search(r'LOCK_TIMEOUT = os\.environ\.get\(\s*"MESFLOW_MIGRATION_LOCK_TIMEOUT",\s*"([^"]+)"',
                      ENV_PY)
    assert match, 'không tìm thấy mặc định của lock_timeout'
    assert match.group(1) not in ('0', '', '0s'), 'mặc định vô hạn là đúng cái lỗi này'


def test_statement_timeout_stays_unlimited_on_purpose():
    """Chặn chờ KHOÁ, không chặn LÀM VIỆC: một backfill trên bảng lớn có thể
    chạy lâu một cách chính đáng, cắt giữa chừng thì tệ hơn hẳn chờ."""
    match = re.search(r'STATEMENT_TIMEOUT = os\.environ\.get\(\s*"MESFLOW_MIGRATION_STATEMENT_TIMEOUT",\s*"([^"]+)"',
                      ENV_PY)
    assert match and match.group(1) == '0'


def test_both_settings_are_overridable_without_a_code_change():
    """Một lần migration nặng có kế hoạch cần cửa sổ khoá dài hơn -- phải chỉnh
    được bằng biến môi trường, đừng bắt ai sửa mã lúc đang deploy."""
    assert 'MESFLOW_MIGRATION_LOCK_TIMEOUT' in ENV_PY
    assert 'MESFLOW_MIGRATION_STATEMENT_TIMEOUT' in ENV_PY


def test_the_sets_run_inside_alembics_transaction_not_before_it():
    """HỢP ĐỒNG THỨ TỰ, không phải chuyện thẩm mỹ.

    Đặt SET trước `context.begin_transaction()` làm cả chuỗi migration âm thầm
    rollback trong khi alembic báo thành công (xem docstring của tệp này).
    """
    body = ENV_PY[ENV_PY.index('def run_migrations_online'):]
    begin = body.index('with context.begin_transaction():')
    run = body.index('context.run_migrations()')
    for statement in ('SET lock_timeout', 'SET statement_timeout'):
        where = body.index(f'f"{statement}')
        assert begin < where < run, (
            f'{statement} phải nằm SAU begin_transaction() và TRƯỚC '
            'run_migrations() -- đặt trước sẽ làm migration không bao giờ commit')


def test_the_whole_chain_still_runs_in_one_transaction():
    """CỐ Ý chưa bật transaction_per_migration: nó thu ngắn cửa sổ khoá nhưng
    cho phép một lần nâng cấp dừng giữa chừng, mà sáu lệnh seed trong repo còn
    thiếu ON CONFLICT (DB-20) nên chạy lại một chuỗi nửa vời sẽ hỏng. Phải sửa
    tính idempotent trước; bài này giữ cho quyết định đó là CÓ Ý THỨC."""
    assert 'transaction_per_migration' not in ENV_PY.replace('# ', '')[:0] or True
    body = ENV_PY[ENV_PY.index('def run_migrations_online'):]
    code = '\n'.join(x for x in body.splitlines() if not x.lstrip().startswith('#'))
    assert 'transaction_per_migration' not in code, (
        'bật transaction_per_migration thì phải sửa DB-20 trước -- xem chú thích')
