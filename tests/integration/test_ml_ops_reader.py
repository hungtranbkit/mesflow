"""Only disposable compose-test DB. No live MESFlow or gateway dependencies."""
import os
from pathlib import Path
import uuid
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest
from mesflow.ml_ops.source import read_sessions
from mesflow.ml_ops.domain import DataError

pytestmark=pytest.mark.postgres


def test_scoped_view_source_and_database_write_denial(db,seeded_factory):
    g=seeded_factory
    role='ml_reader_'+uuid.uuid4().hex[:10];password=uuid.uuid4().hex
    ids=[]
    try:
        for excluded,confirmed,system in ((False,True,False),(True,True,False),(False,False,False),(False,True,True)):
            row=db.execute("""INSERT INTO work_sessions(employee_id,operation_id,station_id,device_uuid,status,
              started_at,ended_at,good_qty,defect_qty,excluded_from_reports,quantity_confirmed,closed_by_system,start_request_id)
              VALUES(%s,%s,%s,'ml-synthetic-test','CLOSED',CURRENT_TIMESTAMP-INTERVAL '2 hours',
              CURRENT_TIMESTAMP-INTERVAL '1 hour',20,1,%s,%s,%s,%s) RETURNING id""",
              (g['employee_id'],g['operation_id'],g['station_id'],excluded,confirmed,system,'ML-SYNTH-'+uuid.uuid4().hex)).fetchone()
            ids.append(row['id'])
        db.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS').format(sql.Identifier(role),sql.Literal(password)))
        script=(Path(__file__).resolve().parents[2]/'scripts/ml-ops-reader.sql').read_text()
        script=script.replace(":'ml_operation_ids'",sql.Literal('{'+str(g['operation_id'])+'}').as_string(db))
        script=script.replace(':"ml_reader"',sql.Identifier(role).as_string(db))
        db.execute(script)
        parts=conninfo_to_dict(os.environ['DATABASE_URL']);parts.update(user=role,password=password)
        dsn=make_conninfo(**parts)
        rows=read_sessions(dsn,(g['operation_id'],))
        assert {r['session_id'] for r in rows}.intersection(ids)=={ids[0]}
        assert set(rows[0])=={'session_id','operation_id','ended_at','duration_seconds','good_qty','defect_qty'}
        assert read_sessions(dsn,(-1,))==[]
        with psycopg.connect(dsn,autocommit=True) as reader:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):reader.execute('UPDATE work_sessions SET good_qty=0')
            reader.execute('SET default_transaction_read_only=off')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):reader.execute('UPDATE work_sessions SET good_qty=0')
            with pytest.raises(psycopg.errors.InsufficientPrivilege):reader.execute('SELECT password_hash FROM users')
            assert reader.execute('SELECT COUNT(*) FROM mesflow_ml_ops_sessions WHERE operation_id<>%s',(g['operation_id'],)).fetchone()[0]==0
        with pytest.raises(DataError,match='restricted_reader'):read_sessions(os.environ['DATABASE_URL'],(g['operation_id'],))
        db.execute(sql.SQL('GRANT SELECT ON users TO {}').format(sql.Identifier(role)))
        with pytest.raises(DataError,match='broad_database'):read_sessions(dsn,(g['operation_id'],))
    finally:
        db.execute('DROP VIEW IF EXISTS public.mesflow_ml_ops_sessions')
        db.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))
        db.execute('DELETE FROM work_sessions WHERE id=ANY(%s)',(ids,))
