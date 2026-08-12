from __future__ import annotations
from mesflow.db.connection import fetch_all
from .base import ConflictError, NotFoundError

def validate_operation_dependencies(operation_id:int|None,production_order_id:int,predecessor_operation_id=None,input_source_operation_id=None,cur=None)->None:
    query='''SELECT id,code,production_order_id,predecessor_operation_id,
      CASE WHEN input_flow_enabled THEN input_source_operation_id END input_source_operation_id
      FROM operations WHERE production_order_id=%s ORDER BY id'''
    if cur is None:rows=fetch_all(query,(production_order_id,))
    else:cur.execute(query+' FOR UPDATE',(production_order_id,));rows=cur.fetchall()
    by_id={int(row['id']):row for row in rows}; node=int(operation_id) if operation_id is not None else None
    proposed=[int(x) for x in (predecessor_operation_id,input_source_operation_id) if x not in (None,'')]
    for dependency_id in proposed:
        if dependency_id not in by_id: raise ConflictError(f'Operation dependency #{dependency_id} không tồn tại trong cùng Production Order')
        if node is not None and dependency_id==node:
            code=str(by_id.get(node,{}).get('code') or node); raise ConflictError(f'Dependency cycle: {code} -> {code}')
    graph={item_id:[int(x) for x in (row.get('predecessor_operation_id'),row.get('input_source_operation_id')) if x] for item_id,row in by_id.items()}
    if node is not None: graph[node]=list(dict.fromkeys(proposed))
    state={}; stack=[]
    def visit(current):
        if state.get(current)==1:
            cycle=stack[stack.index(current):]+[current]
            raise ConflictError('Dependency cycle: '+' -> '.join(str(by_id.get(item,{}).get('code') or item) for item in cycle))
        if state.get(current)==2:return
        state[current]=1; stack.append(current)
        for dependency in graph.get(current,[]):
            if dependency not in by_id: raise NotFoundError(f'Operation dependency #{dependency} not found')
            visit(dependency)
        stack.pop(); state[current]=2
    for item_id in graph: visit(item_id)

def detect_operation_dependency_cycles(production_order_id:int)->None:
    validate_operation_dependencies(None,production_order_id)
