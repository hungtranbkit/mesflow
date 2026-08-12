from contextlib import contextmanager
from typing import Any, Iterable
import psycopg
from psycopg.rows import dict_row
from mesflow.core.config import settings

@contextmanager
def transaction():
    conn=psycopg.connect(settings.database_url,row_factory=dict_row,autocommit=False)
    # Store/return all database timestamps in UTC; UI converts to Asia/Ho_Chi_Minh.
    conn.execute("SET TIME ZONE 'UTC'")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def _execute_cursor(cur, sql: str, params: Iterable[Any] | None = None):
    """Execute SQL without forcing psycopg placeholder parsing for no-param queries."""
    if params is None:
        return cur.execute(sql)
    values = tuple(params)
    return cur.execute(sql, values) if values else cur.execute(sql)


def fetch_one(sql: str, params: Iterable[Any] | None = None):
    with transaction() as conn:
        with conn.cursor() as cur:
            _execute_cursor(cur, sql, params)
            return cur.fetchone()


def fetch_all(sql: str, params: Iterable[Any] | None = None):
    with transaction() as conn:
        with conn.cursor() as cur:
            _execute_cursor(cur, sql, params)
            return list(cur.fetchall())


def execute(sql: str, params: Iterable[Any] | None = None):
    with transaction() as conn:
        with conn.cursor() as cur:
            _execute_cursor(cur, sql, params)
            return cur.rowcount
