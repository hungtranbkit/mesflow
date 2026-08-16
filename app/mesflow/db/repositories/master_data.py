from __future__ import annotations
from typing import Any
from datetime import datetime
from mesflow.core.time_policy import parse_datetime_utc
from psycopg import sql
from mesflow.db.connection import transaction, fetch_all
from .base import BaseRepository, NotFoundError, ConflictError, RepositoryError
from .production_state import reconcile_operation_and_po
from .dependency_graph import validate_operation_dependencies
from mesflow.domain.trace import record_event

class EmployeeRepository(BaseRepository):
    table='employees'; id_column='id'
    selectable_columns=(
        'id','employee_no','name','department','team','position','employment_status','active','qr',
        'birth_date','hometown','phone','identity_number','identity_issue_date','current_address',
        'start_date','end_date','contract_1','contract_2','created_at','updated_at'
    )
    writable_columns=(
        'employee_no','name','department','team','position','employment_status','active','qr',
        'birth_date','hometown','phone','identity_number','identity_issue_date','current_address',
        'start_date','end_date','contract_1','contract_2'
    )

    @staticmethod
    def _normalize(data):
        clean=dict(data or {})
        for key in ('employee_no','name','department','team','position','employment_status','qr','hometown','phone','identity_number','current_address','contract_1','contract_2'):
            if key in clean:
                clean[key]=str(clean[key] or '').strip()
        if 'employee_no' in clean:
            clean['employee_no']=clean['employee_no'].upper()
        if 'employment_status' in clean:
            clean['employment_status']=clean['employment_status'] or 'Đang làm'
            clean['active']=clean['employment_status']!='Đã nghỉ'
        for key in ('birth_date','identity_issue_date','start_date','end_date'):
            if key in clean and clean[key] in ('',None):
                clean[key]=None
        return clean

    def create(self,data):
        data=self._normalize(data)
        no=str(data.get('employee_no','')).strip().upper()
        name=str(data.get('name','')).strip()
        if not no: raise ValueError('Mã nhân viên không được để trống')
        if not name: raise ValueError('Họ tên không được để trống')
        data['employee_no']=no
        data.setdefault('qr',f'WF|EMP|{no}')
        return super().create(data)

    def update(self,entity_id,data):
        clean=self._normalize(data)
        if 'employee_no' in clean and not clean['employee_no']:
            raise ValueError('Mã nhân viên không được để trống')
        if 'name' in clean and not clean['name']:
            raise ValueError('Họ tên không được để trống')
        if clean.get('employee_no') and not clean.get('qr'):
            clean['qr']=f"WF|EMP|{clean['employee_no']}"
        return super().update(entity_id,clean)

    def list_with_stats(self,limit=1000,offset=0):
        query=("SELECT e.*, COALESCE(s.session_count,0) AS session_count, "
               "COALESCE(s.total_good_qty,0) AS total_good_qty "
               "FROM employees e LEFT JOIN ("
               "SELECT employee_id, COUNT(*) AS session_count, "
               "COALESCE(SUM(good_qty),0) AS total_good_qty "
               "FROM work_sessions GROUP BY employee_id"
               ") s ON s.employee_id=e.id "
               "ORDER BY e.employee_no,e.id LIMIT %s OFFSET %s")
        return fetch_all(query,(limit,offset))

class StationRepository(BaseRepository):
    table='stations'; id_column='id'
    selectable_columns=('id','code','name','workshop','production_line','active','created_at','updated_at')
    writable_columns=('code','name','workshop','production_line','active')

class EquipmentRepository(BaseRepository):
    table='equipment'; id_column='id'
    selectable_columns=('id','code','name','equipment_type','status','active','notes','created_at','updated_at')
    writable_columns=('code','name','equipment_type','status','active','notes')

class SalesOrderRepository(BaseRepository):
    table='sales_orders'; id_column='id'
    selectable_columns=('id','code','customer_name','contract_no','status','priority','delivery_deadline','notes','created_at','updated_at')
    writable_columns=('code','customer_name','contract_no','status','priority','delivery_deadline','notes')

class ProductionOrderRepository(BaseRepository):
    table='production_orders'; id_column='id'
    selectable_columns=('id','code','sales_order_id','source_template_id','source_template_code','source_template_version','product','planned_quantity','status','priority','due_date','planned_start_at','planned_end_at','notes','created_at','updated_at')
    writable_columns=('code','sales_order_id','product','planned_quantity','status','priority','due_date','planned_start_at','planned_end_at','notes')
    allowed_statuses={'DRAFT','PLANNED','RELEASED','IN_PROGRESS','PAUSED','COMPLETED','CANCELLED'}
    allowed_priorities={'LOW','NORMAL','HIGH','URGENT'}

    @classmethod
    def _normalize(cls,data,*,creating=False):
        clean=dict(data or {})
        if 'code' in clean:
            clean['code']=str(clean.get('code') or '').strip().upper()
            if not clean['code']:
                raise ValueError('Mã PO không được để trống')
        elif creating:
            raise ValueError('Mã PO không được để trống')
        if 'product' in clean:
            clean['product']=str(clean.get('product') or '').strip()
            if not clean['product']:
                raise ValueError('Sản phẩm không được để trống')
        elif creating:
            raise ValueError('Sản phẩm không được để trống')
        if 'planned_quantity' in clean:
            try:
                clean['planned_quantity']=int(clean.get('planned_quantity'))
            except (TypeError,ValueError):
                raise ValueError('Số lượng kế hoạch không hợp lệ')
            if clean['planned_quantity']<=0:
                raise ValueError('Số lượng kế hoạch phải lớn hơn 0')
        elif creating:
            raise ValueError('Số lượng kế hoạch phải lớn hơn 0')
        if 'status' in clean:
            clean['status']=str(clean.get('status') or 'PLANNED').strip().upper()
            if clean['status'] not in cls.allowed_statuses:
                raise ValueError('Trạng thái PO không hợp lệ')
        if 'priority' in clean:
            clean['priority']=str(clean.get('priority') or 'NORMAL').strip().upper()
            if clean['priority'] not in cls.allowed_priorities:
                raise ValueError('Mức ưu tiên PO không hợp lệ')
        for key in ('sales_order_id','due_date','planned_start_at','planned_end_at'):
            if key in clean and clean[key] in ('',None):
                clean[key]=None
        if clean.get('planned_start_at') and clean.get('planned_end_at'):
            try:
                start=parse_datetime_utc(clean['planned_start_at'])
                end=parse_datetime_utc(clean['planned_end_at'])
            except ValueError:
                raise ValueError('Thời gian dự kiến không hợp lệ')
            if end<=start:
                raise ValueError('Thời gian kết thúc dự kiến phải sau thời gian bắt đầu')
            clean['planned_start_at']=start
            clean['planned_end_at']=end
        return clean

    def create(self,data):
        raise ValueError('Production Order phải được tạo từ Template để sao chép Part và Operation')

    def update(self,entity_id,data):
        return super().update(entity_id,self._normalize(data,creating=False))

    def delete(self,entity_id):
        rows=fetch_all('''SELECT
            EXISTS(SELECT 1 FROM work_sessions s JOIN operations o ON o.id=s.operation_id WHERE o.production_order_id=%s) has_sessions,
            EXISTS(SELECT 1 FROM operation_input_consumptions c JOIN operations o ON o.id=c.source_operation_id OR o.id=c.target_operation_id WHERE o.production_order_id=%s) has_ledgers,
            EXISTS(SELECT 1 FROM operations o WHERE o.production_order_id=%s AND (COALESCE(o.done_qty,0)>0 OR COALESCE(o.defect_qty,0)>0 OR COALESCE(o.rework_qty,0)>0)) has_output,
            EXISTS(SELECT 1 FROM kiosk_events e JOIN operations o ON o.id=e.operation_id WHERE o.production_order_id=%s) has_events,
            EXISTS(SELECT 1 FROM operation_adjustments a JOIN operations o ON o.id=a.operation_id WHERE o.production_order_id=%s) has_adjustments,
            EXISTS(SELECT 1 FROM qc_inspections q JOIN operations o ON o.id=q.operation_id WHERE o.production_order_id=%s) has_qc''',(entity_id,entity_id,entity_id,entity_id,entity_id,entity_id))
        info=rows[0] if rows else {}
        found=[label for key,label in {'has_sessions':'Session','has_ledgers':'ledger','has_output':'sản lượng','has_events':'event','has_adjustments':'điều chỉnh','has_qc':'QC'}.items() if info.get(key)]
        if found:
            raise ConflictError('Không thể xóa Production Order vì đã có production history: '+', '.join(found)+'.')
        return super().delete(entity_id)

class PartRepository(BaseRepository):
    table='parts'; id_column='id'
    selectable_columns=('id','production_order_id','code','name','drawing_path','sort_order','active','created_at','updated_at')
    writable_columns=('production_order_id','code','name','drawing_path','sort_order','active')

    def delete(self,entity_id):
        rows=fetch_all('''SELECT COUNT(*) operation_count,
            COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM work_sessions s WHERE s.operation_id=o.id)) session_ops,
            COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM operation_input_consumptions c WHERE c.source_operation_id=o.id OR c.target_operation_id=o.id)) ledger_ops,
            COUNT(*) FILTER (WHERE COALESCE(o.done_qty,0)>0 OR COALESCE(o.defect_qty,0)>0 OR COALESCE(o.rework_qty,0)>0) output_ops,
            COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM kiosk_events e WHERE e.operation_id=o.id)) event_ops,
            COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM operation_adjustments a WHERE a.operation_id=o.id)) adjustment_ops,
            COUNT(*) FILTER (WHERE EXISTS(SELECT 1 FROM qc_inspections q WHERE q.operation_id=o.id)) qc_ops
            FROM operations o WHERE o.part_id=%s''',(entity_id,))
        info=rows[0] if rows else {}
        found=[label for key,label in {'session_ops':'Session','ledger_ops':'ledger','output_ops':'sản lượng','event_ops':'event','adjustment_ops':'điều chỉnh','qc_ops':'QC'}.items() if int(info.get(key) or 0)>0]
        if found:
            raise ConflictError('Không thể xóa Part vì đã có production history: '+', '.join(found)+'.')
        return super().delete(entity_id)

class OperationRepository(BaseRepository):
    table='operations'; id_column='id'
    selectable_columns=('id','production_order_id','part_id','code','name','done_qty','defect_qty','rework_qty','status','sort_order','qr','equipment_id','standard_seconds_per_unit','repair_cycle_time_seconds_per_unit','predecessor_operation_id','dependency_type','lag_minutes','planned_start_at','planned_end_at','input_flow_enabled','input_source_operation_id','input_source_kind','defects_consume_input','created_at','updated_at')
    writable_columns=('production_order_id','part_id','code','name','done_qty','defect_qty','rework_qty','status','sort_order','qr','equipment_id','standard_seconds_per_unit','repair_cycle_time_seconds_per_unit','predecessor_operation_id','dependency_type','lag_minutes','planned_start_at','planned_end_at','input_flow_enabled','input_source_operation_id','input_source_kind','defects_consume_input')

    def list(self,*,limit=200,offset=0):
        return fetch_all("""SELECT o.*,COALESCE(po.planned_quantity,0) AS plan_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.target_operation_id=o.id),0) input_consumed_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id),0) input_allocated_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id AND c.source_qty_kind='GOOD'),0) good_allocated_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id AND c.source_qty_kind='REWORK'),0) rework_allocated_qty
            FROM operations o JOIN production_orders po ON po.id=o.production_order_id
            ORDER BY o.id DESC LIMIT %s OFFSET %s""",(limit,offset))

    def get(self,entity_id):
        row=fetch_all("""SELECT o.*,COALESCE(po.planned_quantity,0) AS plan_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.target_operation_id=o.id),0) input_consumed_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id),0) input_allocated_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id AND c.source_qty_kind='GOOD'),0) good_allocated_qty,
              COALESCE((SELECT SUM(c.good_qty_consumed+c.defect_qty_consumed) FROM operation_input_consumptions c WHERE c.source_operation_id=o.id AND c.source_qty_kind='REWORK'),0) rework_allocated_qty
            FROM operations o JOIN production_orders po ON po.id=o.production_order_id
            WHERE o.id=%s LIMIT 1""",(entity_id,))
        if not row: raise NotFoundError('operations not found')
        return row[0]

    @staticmethod
    def _validate_flow(data, *, existing_id=None):
        source_id=data.get('input_source_operation_id')
        enabled=bool(data.get('input_flow_enabled'))
        source_kind=str(data.get('input_source_kind') or 'GOOD').upper()
        if source_kind not in ('GOOD','REWORK'):
            raise ValueError('Loại nguồn đầu vào phải là GOOD hoặc REWORK')
        data['input_source_kind']=source_kind
        if not enabled or not source_id:
            data['input_source_operation_id']=None
            return data
        source_id=int(source_id)
        if existing_id and source_id==int(existing_id):
            raise ValueError('Operation không thể lấy đầu vào từ chính nó')
        po_id=data.get('production_order_id')
        if existing_id and not po_id:
            rows=fetch_all('SELECT production_order_id FROM operations WHERE id=%s',(existing_id,))
            po_id=rows[0]['production_order_id'] if rows else None
        rows=fetch_all('SELECT production_order_id FROM operations WHERE id=%s',(source_id,))
        if not rows or int(rows[0]['production_order_id'])!=int(po_id or 0):
            raise ValueError('OP nguồn phải thuộc cùng Production Order')
        data['input_source_operation_id']=source_id
        return data

    def create(self,data):
        data=dict(data)
        data.pop('plan_qty',None)
        for field in ('done_qty','defect_qty','rework_qty','status'):
            if field in data and data.get(field) not in (None,0,'0','PLANNED'):
                raise ConflictError('Aggregate và trạng thái Operation được tính từ production records, không thể nhập trực tiếp.')
        data['done_qty']=0; data['defect_qty']=0; data['rework_qty']=0; data['status']='PLANNED'
        data=self._validate_flow(data)
        validate_operation_dependencies(None,int(data.get('production_order_id') or 0),data.get('predecessor_operation_id'),data.get('input_source_operation_id') if data.get('input_flow_enabled') else None)
        code=str(data.get('code','')).strip().upper()
        if code: data.setdefault('qr',f'WF|OP|{code}')
        return super().create(data)

    def update(self,entity_id,data):
        clean=dict(data or {})
        clean.pop('plan_qty',None)
        current=self.get(entity_id)
        history_rows=fetch_all('SELECT COUNT(*) n FROM work_sessions WHERE operation_id=%s',(entity_id,))
        has_history=bool(history_rows and int(history_rows[0].get('n') or 0)>0)
        if any(key in clean for key in ('done_qty','defect_qty','rework_qty')):
            requested=(int(clean.get('done_qty',current.get('done_qty') or 0) or 0),
                       int(clean.get('defect_qty',current.get('defect_qty') or 0) or 0),
                       int(clean.get('rework_qty',current.get('rework_qty') or 0) or 0))
            actual=(int(current.get('done_qty') or 0),int(current.get('defect_qty') or 0),int(current.get('rework_qty') or 0))
            if requested!=actual:
                raise ConflictError('Không thể sửa trực tiếp aggregate của Operation đã có production history. Hãy điều chỉnh Session với lý do để giữ audit.')
        if 'status' in clean:
            requested_status=str(clean.get('status') or '').upper()
            if requested_status != str(current.get('status') or '').upper():
                raise ConflictError('Trạng thái Operation được tính từ production records; hãy dùng transition endpoint phù hợp.')
        merged=dict(current); merged.update(clean)
        merged=self._validate_flow(merged,existing_id=entity_id)
        validate_operation_dependencies(int(entity_id),int(merged.get('production_order_id') or 0),merged.get('predecessor_operation_id'),merged.get('input_source_operation_id') if merged.get('input_flow_enabled') else None)
        old_source=current.get('input_source_operation_id') if current.get('input_flow_enabled') else None
        new_source=merged.get('input_source_operation_id') if merged.get('input_flow_enabled') else None
        ledger_target=int(current.get('input_consumed_qty') or 0)
        allocated=int(current.get('input_allocated_qty') or 0)
        good_allocated=int(current.get('good_allocated_qty') or 0)
        rework_allocated=int(current.get('rework_allocated_qty') or 0)
        old_kind=str(current.get('input_source_kind') or 'GOOD')
        new_kind=str(merged.get('input_source_kind') or 'GOOD')
        if (old_source != new_source or old_kind != new_kind) and ledger_target>0:
            raise ConflictError(f'Không thể đổi OP nguồn vì Operation đã tiêu thụ {ledger_target} sản phẩm. Hãy hoàn tác/điều chỉnh các Session liên quan trước.')
        if 'done_qty' in clean and int(clean.get('done_qty') or 0)<good_allocated:
            raise ConflictError(f'Không thể giảm sản lượng đạt xuống dưới {good_allocated} vì số lượng này đã được phân bổ cho các OP đích.')
        if 'rework_qty' in clean:
            rework=int(clean.get('rework_qty') or 0); defect=int(merged.get('defect_qty') or 0)
            if rework<0 or rework>defect:
                raise ValueError('Lỗi sửa được phải từ 0 đến tổng số lỗi')
            if rework<rework_allocated:
                raise ConflictError(f'Không thể giảm lỗi sửa được xuống dưới {rework_allocated} vì số lượng này đã được phân bổ cho OP sửa chữa.')
        if 'defect_qty' in clean and int(clean.get('defect_qty') or 0)<int(merged.get('rework_qty') or 0):
            raise ValueError('Tổng số lỗi không thể nhỏ hơn số lỗi sửa được')
        # Preserve fields omitted by PATCH; only validate the merged flow state.
        clean['input_flow_enabled']=bool(merged.get('input_flow_enabled'))
        clean['input_source_operation_id']=merged.get('input_source_operation_id')
        clean['input_source_kind']=merged.get('input_source_kind') or 'GOOD'
        writable={k:v for k,v in clean.items() if k in self.writable_columns}
        if not writable:return self.get(entity_id)
        with transaction() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT pg_advisory_xact_lock(%s)',(int(merged.get('production_order_id') or 0),))
                validate_operation_dependencies(int(entity_id),int(merged.get('production_order_id') or 0),merged.get('predecessor_operation_id'),merged.get('input_source_operation_id') if merged.get('input_flow_enabled') else None,cur=cur)
                assignments=sql.SQL(',').join(sql.SQL('{}={}').format(sql.Identifier(k),sql.Placeholder()) for k in writable)
                query=sql.SQL('UPDATE operations SET {},updated_at=CURRENT_TIMESTAMP WHERE id=%s RETURNING {}').format(assignments,sql.SQL(',').join(map(sql.Identifier,self.selectable_columns)))
                cur.execute(query,tuple(writable.values())+(entity_id,));updated=cur.fetchone()
                if not updated:raise NotFoundError('operations not found')
                if has_history:reconcile_operation_and_po(cur,int(entity_id))
        return self.get(entity_id) if has_history else updated

    def delete(self,entity_id):
        current=self.get(entity_id)
        if any(int(current.get(key) or 0)>0 for key in ('done_qty','defect_qty','rework_qty')):
            raise ConflictError('Không thể xóa Operation vì đã có sản lượng production.')
        if int(current.get('input_consumed_qty') or 0)>0 or int(current.get('input_allocated_qty') or 0)>0:
            raise ConflictError('Không thể xóa Operation vì đã phát sinh Ledger dòng vật tư.')
        rows=fetch_all('SELECT COUNT(*) n FROM work_sessions WHERE operation_id=%s',(entity_id,))
        history=fetch_all('''SELECT
            EXISTS(SELECT 1 FROM kiosk_events WHERE operation_id=%s) has_events,
            EXISTS(SELECT 1 FROM operation_adjustments WHERE operation_id=%s) has_adjustments,
            EXISTS(SELECT 1 FROM qc_inspections WHERE operation_id=%s) has_qc''',(entity_id,entity_id,entity_id))
        if history and any(history[0].get(key) for key in ('has_events','has_adjustments','has_qc')):
            raise ConflictError('Không thể xóa Operation vì đã có event/audit thực thi.')
        if rows and int(rows[0].get('n') or 0)>0:
            raise ConflictError('Không thể xóa Operation vì đã phát sinh Session.')
        refs=fetch_all('SELECT code FROM operations WHERE input_source_operation_id=%s LIMIT 5',(entity_id,))
        if refs:
            raise ConflictError('Không thể xóa Operation vì đang là nguồn đầu vào của: '+', '.join(str(x.get('code')) for x in refs))
        return super().delete(entity_id)

class TemplateRepository(BaseRepository):
    table='templates'; id_column='id'
    selectable_columns=('id','code','name','product','version','active','source_workbook','created_at','updated_at')
    writable_columns=('code','name','product','version','active','source_workbook')

    @staticmethod
    def _normalize(data):
        clean=dict(data or {})
        if 'code' in clean:
            clean['code']=str(clean['code'] or '').strip().upper()
            if not clean['code']:
                raise ValueError('template code required')
        if 'name' in clean:
            clean['name']=str(clean['name'] or '').strip()
            if not clean['name']:
                raise ValueError('template name required')
        for key in ('product','version','source_workbook'):
            if key in clean:
                clean[key]=str(clean[key] or '').strip()
        if 'version' in clean and not clean['version']:
            clean['version']='1.0'
        return clean

    def create(self,data):
        clean=self._normalize(data)
        if not clean.get('code') or not clean.get('name'):
            raise ValueError('template code and name required')
        return super().create(clean)

    def update(self,entity_id,data):
        return super().update(entity_id,self._normalize(data))



class TemplateValidationError(RepositoryError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _normalize_part_code(value):
    return str(value or '').strip().upper()


def _validate_template_part_codes(parts, *, template=None):
    normalized=[]
    empty_indexes=[]
    for idx, part in enumerate(parts):
        code=_normalize_part_code(part.get('code'))
        if not code:
            empty_indexes.append(idx)
        normalized.append(code)
    if empty_indexes:
        details={'part_indexes':empty_indexes}
        if template:
            details.update({'template_id':template.get('id'),'template_code':template.get('code')})
        raise TemplateValidationError('EMPTY_PART_CODE','Template contains a part without a code.',details)
    counts={}
    for code in normalized:
        counts[code]=counts.get(code,0)+1
    duplicates=sorted(code for code,count in counts.items() if count>1)
    if duplicates:
        details={'duplicate_codes':duplicates}
        if template:
            details.update({'template_id':template.get('id'),'template_code':template.get('code')})
        raise TemplateValidationError('DUPLICATE_PART_CODE_IN_TEMPLATE','Template contains duplicate part codes.',details)
    return normalized


class TemplateTreeRepository:
    @staticmethod
    def _validate_dependency_graph(operations):
        by_code={str(op.get('code') or '').strip().upper():op for op in operations if str(op.get('code') or '').strip()}
        graph={code:[str(op.get('input_source_code') or '').strip().upper()] if op.get('input_flow_enabled') and str(op.get('input_source_code') or '').strip() else [] for code,op in by_code.items()}
        state={};stack=[]
        def visit(code):
            if state.get(code)==1:
                cycle=stack[stack.index(code):]+[code];raise ConflictError('Dependency cycle: '+' -> '.join(cycle))
            if state.get(code)==2:return
            state[code]=1;stack.append(code)
            for source in graph.get(code,[]):
                if source not in by_code:raise ConflictError(f'Không tìm thấy OP nguồn {source}')
                visit(source)
            stack.pop();state[code]=2
        for code in graph:visit(code)

    def get(self,template_id:int):
        with transaction() as conn:
            template=conn.execute('SELECT * FROM templates WHERE id=%s',(template_id,)).fetchone()
            if not template: raise NotFoundError('template not found')
            parts=conn.execute('SELECT * FROM template_parts WHERE template_id=%s ORDER BY sort_order,id',(template_id,)).fetchall()
            operations=conn.execute('SELECT * FROM template_operations WHERE template_id=%s ORDER BY part_id,sort_order,id',(template_id,)).fetchall()
            equipment=conn.execute('SELECT * FROM template_equipment WHERE template_id=%s ORDER BY id',(template_id,)).fetchall()
            return {'template':template,'parts':list(parts),'operations':list(operations),'equipment':list(equipment)}

    def replace_tree(self,template_id:int,payload:dict[str,Any]):
        parts=list(payload.get('parts') or [])
        operations=list(payload.get('operations') or [])
        equipment=list(payload.get('equipment') or [])
        part_keys=[str(p.get('key',idx)) for idx,p in enumerate(parts)]
        if len(set(part_keys)) != len(part_keys):
            raise ValueError('duplicate part key')
        _validate_template_part_codes(parts)
        if any(not str(p.get('name') or '').strip() for p in parts):
            raise ValueError('part name required')
        if any(str(op.get('part_key')) not in set(part_keys) for op in operations):
            raise ValueError('operation references invalid part')
        if any(not str(op.get('name') or '').strip() for op in operations):
            raise ValueError('operation name required')
        if any(float(op.get('standard_seconds_per_unit') or 0) < 0 for op in operations):
            raise ValueError('standard_seconds_per_unit must be >= 0')
        if any(float(op.get('repair_cycle_time_seconds_per_unit') or 0) < 0 for op in operations):
            raise ValueError('repair_cycle_time_seconds_per_unit must be >= 0')
        op_codes={str(op.get('code') or '').strip().upper() for op in operations if str(op.get('code') or '').strip()}
        for item in operations:
            source=str(item.get('input_source_code') or '').strip().upper()
            code=str(item.get('code') or '').strip().upper()
            if source and source==code: raise ValueError('Operation không thể lấy đầu vào từ chính nó')
            if source and source not in op_codes: raise ValueError(f'Không tìm thấy OP nguồn {source}')
        self._validate_dependency_graph(operations)
        equipment_ids=[int(item.get('equipment_id') or 0) for item in equipment]
        if any(x <= 0 for x in equipment_ids):
            raise ValueError('equipment_id required')
        if len(set(equipment_ids)) != len(equipment_ids):
            raise ValueError('duplicate template equipment')
        if any(int(item.get('quantity') or 0) < 1 for item in equipment):
            raise ValueError('equipment quantity must be >= 1')
        with transaction() as conn:
            if not conn.execute('SELECT 1 FROM templates WHERE id=%s',(template_id,)).fetchone():
                raise NotFoundError('template not found')
            conn.execute('DELETE FROM template_equipment WHERE template_id=%s',(template_id,))
            conn.execute('DELETE FROM template_operations WHERE template_id=%s',(template_id,))
            conn.execute('DELETE FROM template_parts WHERE template_id=%s',(template_id,))
            part_ids={}
            for idx,part in enumerate(parts):
                row=conn.execute('INSERT INTO template_parts(template_id,code,name,drawing_path,sort_order) VALUES(%s,%s,%s,%s,%s) RETURNING id',
                    (template_id,part.get('code',''),part.get('name',''),str(part.get('drawing_path') or ''),part.get('sort_order',idx))).fetchone()
                part_ids[str(part.get('key',idx))]=row['id']
            for idx,op in enumerate(operations):
                part_id=part_ids.get(str(op.get('part_key')))
                conn.execute('INSERT INTO template_operations(template_id,part_id,code,name,sort_order,equipment_code,standard_seconds_per_unit,repair_cycle_time_seconds_per_unit,input_flow_enabled,input_source_code,input_source_kind,defects_consume_input) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (template_id,part_id,op.get('code',''),op.get('name',''),op.get('sort_order',idx),op.get('equipment_code',''),float(op.get('standard_seconds_per_unit') or 0),float(op.get('repair_cycle_time_seconds_per_unit') or 0),bool(op.get('input_flow_enabled')),str(op.get('input_source_code') or '').strip().upper() or None,str(op.get('input_source_kind') or 'GOOD').upper(),bool(op.get('defects_consume_input',True))))
            for item in equipment:
                conn.execute('INSERT INTO template_equipment(template_id,equipment_id,quantity) VALUES(%s,%s,%s)',
                    (template_id,item.get('equipment_id'),int(item.get('quantity',1))))
        return self.get(template_id)


    def validate(self,template_id:int):
        with transaction() as conn:
            template=conn.execute('SELECT * FROM templates WHERE id=%s',(template_id,)).fetchone()
            if not template:
                raise NotFoundError('template not found')
            parts=list(conn.execute('SELECT * FROM template_parts WHERE template_id=%s ORDER BY sort_order,id',(template_id,)).fetchall())
            operations=list(conn.execute('SELECT * FROM template_operations WHERE template_id=%s ORDER BY part_id,sort_order,id',(template_id,)).fetchall())
        errors=[]
        try:
            _validate_template_part_codes(parts,template=template)
        except TemplateValidationError as exc:
            errors.append({'code':exc.code.replace('_IN_TEMPLATE',''),'field':'parts.code','values':exc.details.get('duplicate_codes',[]),'details':exc.details})
        if not parts:
            errors.append({'code':'NO_PARTS','field':'parts','values':[]})
        if not operations:
            errors.append({'code':'NO_OPERATIONS','field':'operations','values':[]})
        try:self._validate_dependency_graph(operations)
        except ConflictError as exc:errors.append({'code':'DEPENDENCY_CYCLE','field':'operations.input_source_code','values':[],'message':str(exc)})
        return {'valid':not errors,'template_id':template_id,'template_code':template.get('code'),'part_count':len(parts),'operation_count':len(operations),'errors':errors}


    def instantiate(self,template_id:int,*,code:str,planned_quantity:int=0,sales_order_id=None,due_date=None,planned_start_at=None,planned_end_at=None,priority='NORMAL',notes=''):
        code=str(code or '').strip().upper()
        if not code:
            raise ValueError('Mã Production Order không được để trống')
        if planned_quantity <= 0:
            raise ValueError('Số lượng kế hoạch phải lớn hơn 0')
        priority=str(priority or 'NORMAL').strip().upper()
        if priority not in ProductionOrderRepository.allowed_priorities:
            raise ValueError('Mức ưu tiên PO không hợp lệ')
        with transaction() as conn:
            template=conn.execute('SELECT * FROM templates WHERE id=%s AND active=true',(template_id,)).fetchone()
            if not template:
                raise NotFoundError('Template không tồn tại hoặc đã bị vô hiệu hóa')
            template_parts=conn.execute('SELECT * FROM template_parts WHERE template_id=%s ORDER BY sort_order,id',(template_id,)).fetchall()
            template_ops=conn.execute('SELECT * FROM template_operations WHERE template_id=%s ORDER BY part_id,sort_order,id',(template_id,)).fetchall()
            if not template_parts:
                raise ConflictError('Template chưa có Part. Hãy hoàn thiện Template trước khi tạo PO.')
            if not template_ops:
                raise ConflictError('Template chưa có Operation. Hãy hoàn thiện Template trước khi tạo PO.')
            self._validate_dependency_graph(template_ops)
            _validate_template_part_codes(list(template_parts), template=template)
            try:
                po=conn.execute(
                    "INSERT INTO production_orders(code,sales_order_id,source_template_id,source_template_code,source_template_version,product,planned_quantity,status,priority,due_date,planned_start_at,planned_end_at,notes) VALUES(%s,%s,%s,%s,%s,%s,%s,'PLANNED',%s,%s,%s,%s,%s) RETURNING id",
                    (code,sales_order_id,template['id'],template['code'],template['version'],template['product'] or template['name'],planned_quantity,priority,due_date,planned_start_at,planned_end_at,notes),
                ).fetchone()
            except Exception as exc:
                if 'unique' in str(exc).lower() or 'duplicate' in str(exc).lower():
                    raise ConflictError('Mã Production Order đã tồn tại') from exc
                raise
            part_map={}
            for part in template_parts:
                created=conn.execute(
                    'INSERT INTO parts(production_order_id,code,name,drawing_path,sort_order,active) VALUES(%s,%s,%s,%s,%s,true) RETURNING id',
                    (po['id'],part['code'],part['name'],part.get('drawing_path') or '',part['sort_order']),
                ).fetchone()
                part_map[part['id']]=created['id']
            operation_ids=[]
            template_to_actual={}
            pending_sources=[]
            for idx,op in enumerate(template_ops):
                part_id=part_map.get(op['part_id'])
                if not part_id: continue
                op_code=f"{code}-{op['code'] or str(idx+1).zfill(2)}"
                equipment_id=None
                if op['equipment_code']:
                    eq=conn.execute('SELECT id FROM equipment WHERE UPPER(code)=UPPER(%s)',(op['equipment_code'],)).fetchone()
                    equipment_id=eq['id'] if eq else None
                created=conn.execute(
                    "INSERT INTO operations(production_order_id,part_id,equipment_id,code,name,done_qty,defect_qty,status,sort_order,qr,standard_seconds_per_unit,repair_cycle_time_seconds_per_unit,predecessor_operation_id,dependency_type,lag_minutes) VALUES(%s,%s,%s,%s,%s,0,0,'PLANNED',%s,%s,%s,%s,%s,'FS',0) RETURNING id",
                    (po['id'],part_id,equipment_id,op_code,op['name'],op['sort_order'],f'WF|OP|{op_code}',float(op.get('standard_seconds_per_unit') or 0),float(op.get('repair_cycle_time_seconds_per_unit') or 0),None),
                ).fetchone()
                operation_ids.append(created['id'])
                template_to_actual[str(op.get('code') or '').strip().upper()]=created['id']
                pending_sources.append((created['id'], bool(op.get('input_flow_enabled')), str(op.get('input_source_code') or '').strip().upper(), str(op.get('input_source_kind') or 'GOOD').upper(), bool(op.get('defects_consume_input',True))))
            for actual_id,enabled,source_code,source_kind,consume_defects in pending_sources:
                source_id=template_to_actual.get(source_code) if source_code else None
                source_kind=source_kind if source_kind in ('GOOD','REWORK') else 'GOOD'
                conn.execute('UPDATE operations SET input_flow_enabled=%s,input_source_operation_id=%s,input_source_kind=%s,defects_consume_input=%s WHERE id=%s',(enabled and bool(source_id),source_id,source_kind,consume_defects,actual_id))
            with conn.cursor() as cur:record_event(cur,event_type='PO_CREATED',category='PO',title='Production Order được tạo',po_id=po['id'],source='NATIVE',metadata={'template_id':template['id'],'template_code':template['code'],'planned_quantity':planned_quantity})
            return {'production_order_id':po['id'],'production_order_code':code,'template_id':template['id'],'template_code':template['code'],'template_version':template['version'],'parts_created':len(part_map),'operations_created':len(operation_ids)}
