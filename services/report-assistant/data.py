"""Read-only projections of existing authorized reporting APIs, never AI SQL."""
from collections import defaultdict
import math
from schema import ReportError

MAX_ROWS = 500
PERMISSIONS = {
    'productivity': {'dashboard.view', 'employees.view'},
    'planned_actual': {'dashboard.view', 'employees.view'},
    'po_progress': {'po.view', 'session.view'},
    'operation_output': {'po.view', 'session.view'},
    'exceptions': {'exceptions.view', 'session.view'},
}
SESSION_TYPES = {'po_progress', 'operation_output', 'exceptions'}
NUMERIC = {'completed_sessions','good_qty','defect_qty','rework_qty','worked_seconds',
           'productivity_percent','session_id','actual_seconds','expected_seconds',
           'completion_percent','duration_seconds','planned_qty_now','done_qty_now',
           'good_qty_in_period','sessions_in_period'}


def number(value):
    # Flask serializes PostgreSQL Decimal values as JSON strings.
    try:
        if isinstance(value, bool): raise ValueError()
        result = float(value)
        if not math.isfinite(result): raise ValueError()
        return int(result) if result.is_integer() else result
    except (TypeError, ValueError, OverflowError): raise ReportError('Giá trị số từ nguồn không hợp lệ.',502)


def authorize(user, kind):
    if not user or user.get('must_change_password'): raise ReportError('Cần đăng nhập hợp lệ và hoàn tất đổi mật khẩu.', 401)
    # Match the existing session-management endpoints' role restriction.
    if kind in SESSION_TYPES and user.get('role') not in ('admin', 'manager', 'supervisor'):
        raise ReportError('Vai trò hiện tại không được xem báo cáo phiên này.', 403)
    if user.get('role') not in ('admin', 'super_admin') and not PERMISSIONS[kind] <= set(user.get('permissions', [])):
        raise ReportError('Bạn chưa có đủ quyền xem báo cáo này.', 403)


def bounded(rows, cap=MAX_ROWS):
    if len(rows) > cap: raise ReportError('Phạm vi quá rộng. Thu hẹp ngày, PO, công đoạn hoặc nhân viên; không xuất dữ liệu bị cắt.', 422)
    return rows


def project(intent, get):
    """get is an authenticated GET-only adapter pinned to this deployment."""
    kind = intent['report_type']; sources = []
    def read(path, params=None):
        sources.append(path)
        return get(path, params or {})
    dates = {'from': intent['from'], 'to': intent['to']}
    po_code = operation_code = None
    po_report = None
    if intent['po_id']:
        po_report = read('/api/reports/production-orders/'+str(intent['po_id']))['report']
        if po_report['production_order']['id'] != intent['po_id']: raise ReportError('Nguồn PO không khớp.',502)
        po_code = po_report['production_order']['code']
    if intent['operation_id']:
        operation = read('/api/operations/'+str(intent['operation_id']))['item']
        if operation['id'] != intent['operation_id']: raise ReportError('Nguồn Operation không khớp.',502)
        if intent['po_id'] and operation['production_order_id'] != intent['po_id']:
            raise ReportError('Operation không thuộc PO đã chọn.', 422)
        operation_code = operation['code']
        if not po_code:
            # Operation codes can repeat in different POs. Scope both fields.
            parent_id = operation['production_order_id']
            parent = read('/api/reports/production-orders/'+str(parent_id))['report']['production_order']
            if parent['id'] != parent_id: raise ReportError('Nguồn PO không khớp.',502)
            po_code = parent['code']
    notes = []
    if kind in ('productivity', 'planned_actual'):
        query = {**dates, 'limit': MAX_ROWS+1}
        if intent['employee_id']: query['employee_id'] = intent['employee_id']
        summary = read('/api/reports/employee-productivity', query)
        employees = bounded(summary['employees'])
        if intent['employee_id'] and any(row['employee_id'] != intent['employee_id'] for row in employees):
            raise ReportError('Nguồn trả nhân viên ngoài phạm vi yêu cầu.',502)
        if kind == 'productivity' and not (po_code or operation_code):
            columns = ['employee_code','employee_name','completed_sessions','good_qty','defect_qty','worked_seconds','productivity_percent']
            rows = [{key: row.get(key) for key in columns} for row in employees]
        else:
            bounded(employees, 20)
            sessions = []
            for employee in employees:
                detail = read('/api/reports/employee-productivity/'+str(employee['employee_id']), dates)
                if detail['employee']['employee_id'] != employee['employee_id']: raise ReportError('Nguồn nhân viên không khớp.',502)
                for row in detail['sessions']:
                    if row.get('excluded_from_reports'): continue
                    if po_code and row['po_code'] != po_code: continue
                    if operation_code and row['operation_code'] != operation_code: continue
                    sessions.append({**row,'employee_code':employee['employee_code'],'employee_name':employee['employee_name']})
                bounded(sessions)
            if kind == 'planned_actual':
                columns = ['employee_code','employee_name','po_code','operation_code','session_id','started_at','ended_at','good_qty','defect_qty','actual_seconds','expected_seconds','completion_percent']
                rows = [{key: row.get(key) for key in columns} for row in sessions]
            else:
                grouped = defaultdict(list)
                for row in sessions: grouped[row['employee_code']].append(row)
                rows = []
                for code, group in grouped.items():
                    scores = [number(row['completion_percent']) for row in group if row.get('completion_percent') is not None]
                    rows.append({'employee_code':code,'employee_name':group[0]['employee_name'], 'completed_sessions':len(group),
                                 'good_qty':sum(number(row.get('good_qty') or 0) for row in group), 'defect_qty':sum(number(row.get('defect_qty') or 0) for row in group),
                                 'worked_seconds':sum(number(row.get('actual_seconds') or 0) for row in group),
                                 'productivity_percent':round(sum(scores)/len(scores),2) if scores else None})
                columns = ['employee_code','employee_name','completed_sessions','good_qty','defect_qty','worked_seconds','productivity_percent']
            notes.append('Tổng hợp từ điểm phần trăm từng phiên do API hiện có trả về; loại phiên bị loại khỏi báo cáo. Ô trống là chưa có định mức/điểm hợp lệ.')
        notes.append('Ngày lọc theo thời điểm KẾT THÚC phiên CLOSED, múi giờ Asia/Ho_Chi_Minh; công thức năng suất từ báo cáo hiện có.')
    else:
        cap = 20 if kind == 'exceptions' else MAX_ROWS
        query = {**dates, 'limit':cap+1, **{k:intent[k] for k in ('po_id','operation_id','employee_id') if intent[k]}}
        sessions = bounded(read('/api/session-management', query)['items'], cap)
        # Defense in depth: never return a row outside the requested entity scope.
        for row in sessions:
            for key in ('po_id','operation_id','employee_id'):
                if intent[key] and row.get(key) != intent[key]: raise ReportError('Nguồn trả về dòng ngoài phạm vi yêu cầu.', 502)
        notes.append('Ngày lọc theo thời điểm BẮT ĐẦU phiên, múi giờ Asia/Ho_Chi_Minh.')
        if kind == 'exceptions':
            rows=[]
            for session in sessions:
                detail = read('/api/session-management/'+str(session['session_id']))
                if detail['session']['session_id'] != session['session_id']: raise ReportError('Nguồn phiên không khớp.', 502)
                for item in detail['exceptions']:
                    rows.append({'session_id':session['session_id'],'employee_code':session['employee_code'], 'po_code':session['po_code'], 'operation_code':session['operation_code'],
                                 'exception_code':item.get('exception_code'),'severity':item.get('severity'),'workflow_status':item.get('workflow_status'),'message':item.get('exception_message')})
            columns=['session_id','employee_code','po_code','operation_code','exception_code','severity','workflow_status','message']
            notes.append('Ngoại lệ hiện tại và lịch sử của tối đa 20 phiên trong phạm vi. Nguồn chi tiết chỉ đọc; không gọi API tự động xử lý/bỏ qua ngoại lệ.')
        elif kind == 'operation_output':
            columns=['session_id','employee_code','employee_name','po_code','operation_code','status','started_at','ended_at','good_qty','defect_qty','rework_qty','duration_seconds']
            rows=[{key:row.get(key) for key in columns} for row in sessions if not row.get('excluded_from_reports')]
            notes.append('Chi tiết sản lượng theo phiên; không cộng các công đoạn khác nhau thành sản lượng PO. Loại phiên excluded_from_reports.')
        else:
            rows=[]
            for operation in po_report['operations']:
                if intent['operation_id'] and operation['id'] != intent['operation_id']: continue
                scoped=[row for row in sessions if row['operation_id']==operation['id'] and not row.get('excluded_from_reports')]
                rows.append({'po_code':po_code,'operation_code':operation['code'],'status_now':operation.get('status'),'planned_qty_now':operation.get('planned_qty'),
                             'done_qty_now':operation.get('done_qty'),'good_qty_in_period':sum(number(row.get('good_qty') or 0) for row in scoped), 'sessions_in_period':len(scoped)})
            columns=['po_code','operation_code','status_now','planned_qty_now','done_qty_now','good_qty_in_period','sessions_in_period']
            notes.append('Kế hoạch/hoàn thành/trạng thái là ẢNH CHỤP HIỆN TẠI toàn PO, không phải lịch sử theo ngày/nhân viên. Chỉ các cột *_in_period áp dụng bộ lọc phiên/ngày/nhân viên.')
    for row in rows:
        for key in NUMERIC & row.keys():
            if row[key] is not None: row[key] = number(row[key])
    return {'columns':columns,'rows':bounded(rows),'sources':list(dict.fromkeys(sources)), 'notes':notes}


def demo(intent):
    """Fixed, invented sample records only. Never calls an MES API."""
    columns=['sample','report_type','po_code','operation_code','employee_code','good_qty','date_from','date_to']
    rows=[{'sample':'DEMO — DỮ LIỆU MẪU','report_type':intent['report_type'],'po_code':'DEMO-PO-01','operation_code':'DEMO-OP-01','employee_code':'DEMO-NV-01','good_qty':12,'date_from':intent['from'],'date_to':intent['to']}]
    return {'columns':columns,'rows':rows,'sources':['Dữ liệu mẫu cố định, không truy vấn MES'], 'notes':['DEMO: số liệu giả định chỉ minh họa xuất báo cáo; không phải dữ liệu sản xuất. ID nhập vào không dùng truy vấn dữ liệu thật.']}
