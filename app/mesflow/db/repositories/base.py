from __future__ import annotations
from typing import Any, Iterable
from psycopg import sql
from mesflow.db.connection import transaction, fetch_all, fetch_one

class RepositoryError(RuntimeError): pass
class NotFoundError(RepositoryError): pass
class ConflictError(RepositoryError): pass

class BaseRepository:
    table:str=''
    id_column:str='id'
    selectable_columns:tuple[str,...]=()
    writable_columns:tuple[str,...]=()

    def list(self, limit:int=200, offset:int=0, order_by:str|None=None):
        order=order_by if order_by in self.selectable_columns else self.id_column
        query=sql.SQL('SELECT {} FROM {} ORDER BY {} LIMIT %s OFFSET %s').format(
            sql.SQL(',').join(map(sql.Identifier,self.selectable_columns)),
            sql.Identifier(self.table), sql.Identifier(order))
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(query,(limit,offset))
                return list(cur.fetchall())

    def get(self, entity_id:Any):
        query=sql.SQL('SELECT {} FROM {} WHERE {}=%s').format(
            sql.SQL(',').join(map(sql.Identifier,self.selectable_columns)),
            sql.Identifier(self.table), sql.Identifier(self.id_column))
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(query,(entity_id,))
                row=cur.fetchone()
                if not row: raise NotFoundError(f'{self.table} not found')
                return row

    def create(self,data:dict[str,Any]):
        clean={k:v for k,v in data.items() if k in self.writable_columns}
        if not clean: raise RepositoryError('No writable fields')
        columns=list(clean)
        query=sql.SQL('INSERT INTO {} ({}) VALUES ({}) RETURNING {}').format(
            sql.Identifier(self.table),
            sql.SQL(',').join(map(sql.Identifier,columns)),
            sql.SQL(',').join(sql.Placeholder()*len(columns)),
            sql.Identifier(self.id_column))
        try:
            with transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(query,tuple(clean[c] for c in columns))
                    return cur.fetchone()[self.id_column]
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23505': raise ConflictError(str(exc)) from exc
            raise

    def update(self,entity_id:Any,data:dict[str,Any]):
        clean={k:v for k,v in data.items() if k in self.writable_columns}
        if not clean: return self.get(entity_id)
        assignments=sql.SQL(',').join(sql.SQL('{}={}').format(sql.Identifier(k),sql.Placeholder()) for k in clean)
        query=sql.SQL('UPDATE {} SET {}, updated_at=CURRENT_TIMESTAMP WHERE {}=%s RETURNING {}').format(
            sql.Identifier(self.table),assignments,sql.Identifier(self.id_column),
            sql.SQL(',').join(map(sql.Identifier,self.selectable_columns)))
        try:
            with transaction() as conn:
                with conn.cursor() as cur:
                    cur.execute(query,tuple(clean.values())+(entity_id,))
                    row=cur.fetchone()
                    if not row: raise NotFoundError(f'{self.table} not found')
                    return row
        except Exception as exc:
            if getattr(exc,'sqlstate',None)=='23505': raise ConflictError(str(exc)) from exc
            raise

    def delete(self,entity_id:Any):
        query=sql.SQL('DELETE FROM {} WHERE {}=%s').format(sql.Identifier(self.table),sql.Identifier(self.id_column))
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(query,(entity_id,))
                if cur.rowcount==0: raise NotFoundError(f'{self.table} not found')
                return True
