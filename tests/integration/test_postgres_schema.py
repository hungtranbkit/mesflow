import pytest

pytestmark = pytest.mark.postgres


def test_migration_has_one_applied_head(db):
    rows = db.execute('SELECT version_num FROM alembic_version').fetchall()
    assert len(rows) == 1, f'Expected one Alembic head, got {rows!r}'
    assert rows[0]['version_num'], 'Applied Alembic head must not be empty'


def test_required_postgres_tables_exist(db):
    expected = {
        'users', 'employees', 'production_orders', 'parts', 'operations',
        'work_sessions', 'work_shifts', 'work_shift_intervals',
        'action_logs', 'error_traces', 'session_exception_reviews', 'operation_input_consumptions',
        'log_retention_runs', 'alembic_version',
    }
    rows = db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'").fetchall()
    actual = {row['tablename'] for row in rows}
    assert expected <= actual


def test_default_day_and_night_shifts_are_seeded(db):
    rows = db.execute("SELECT code,cross_midnight,target_minutes FROM work_shifts ORDER BY sort_order").fetchall()
    by_code = {row['code']: row for row in rows}
    assert by_code['DAY']['cross_midnight'] is False
    assert by_code['NIGHT']['cross_midnight'] is True
    assert by_code['DAY']['target_minutes'] == 480
    assert by_code['NIGHT']['target_minutes'] == 480
    intervals = db.execute("SELECT s.code,i.interval_type,i.start_minute,i.end_minute FROM work_shift_intervals i JOIN work_shifts s ON s.id=i.shift_id ORDER BY s.code,i.sort_order").fetchall()
    assert any(x['code'] == 'NIGHT' and x['end_minute'] > 1440 for x in intervals)


def test_postgresql_specific_constraints_exist(db):
    indexes = db.execute("SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='work_sessions'").fetchall()
    assert any("WHERE (status = 'OPEN'" in row['indexdef'] or "WHERE status = 'OPEN'" in row['indexdef'] for row in indexes)


def test_alembic_version_column_accepts_long_revision(db):
    row=db.execute("""
        SELECT character_maximum_length AS max_length
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name='alembic_version' AND column_name='version_num'
    """).fetchone()
    assert row is not None
    assert row['max_length'] is None or row['max_length'] >= 128
