"""Report assistant: verified session + RBAC, fixed GET APIs, bounded snapshots.

No database connection, business write methods, model SQL, raw prompts sent to AI,
or report data sent to AI. Deploy next to the existing MES app, not inside it.
"""
import csv
from datetime import datetime, timezone
import hashlib
from http.cookies import SimpleCookie
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from flask import Flask, g, jsonify, request, send_file, send_from_directory
from openpyxl import Workbook
from schema import ReportError, TYPES, extract, validate
from data import authorize, project, demo
from snapshot_store import SnapshotSource, load as load_snapshot

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 2048
BACKEND = os.environ.get('REPORT_BACKEND', 'http://mesflow-app:8080')
GATEWAY_KEY = os.environ.get('SUPPORT_GATEWAY_KEY', '')
AUDIT = Path(os.environ.get('REPORT_AUDIT_PATH', '/audit/reports.jsonl'))
ORIGIN = os.environ.get('REPORT_ORIGIN', 'https://mesflow.net')
SNAPSHOT_DIR = Path(os.environ.get('REPORT_SNAPSHOT_DIR', '/snapshots'))
pdf_slots = threading.BoundedSemaphore(1)
lock = threading.Lock()
slots = threading.BoundedSemaphore(2)
snapshots, rates, ai_cache = {}, {}, {}
ai_budget = []
ALLOWED = re.compile(r'^/api/auth/me$')


@app.errorhandler(ReportError)
def failure(error):
    return jsonify(error=error.message), error.status


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error='Yêu cầu quá dài.'), 413


@app.before_request
def boundary():
    if request.method == 'POST':
        if request.headers.get('Origin') not in (None, ORIGIN):
            raise ReportError('Origin không hợp lệ.', 403)
        if not request.is_json: raise ReportError('Yêu cầu phải là JSON.', 415)


@app.after_request
def headers(response):
    response.headers['Cache-Control'] = 'no-store, private'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    if getattr(g, 'session_refresh', None):
        response.headers.add('Set-Cookie', g.session_refresh)
    return response


def body(keys):
    value = request.get_json(silent=True)
    if not isinstance(value, dict) or set(value) - set(keys): raise ReportError('Cấu trúc yêu cầu không hợp lệ.')
    return value


def session_cookie():
    parsed = SimpleCookie()
    try: parsed.load(request.headers.get('Cookie', ''))
    except Exception: return ''
    return 'session='+parsed['session'].coded_value if 'session' in parsed else ''


def backend(path, params=None):
    if not ALLOWED.fullmatch(path): raise ReportError('Nguồn báo cáo không được phép.', 400)
    url = BACKEND + path + ('?'+urlencode(params) if params else '')
    headers = {'Cookie':session_cookie(), 'Host':'mesflow.net', 'X-Forwarded-Proto':'https', 'User-Agent':'MESFlow-report-assistant/1.0'}
    try:
        with urlopen(Request(url, headers=headers), timeout=4) as response:
            raw=response.read(8_000_001)
            if len(raw)>8_000_000: raise ReportError('Nguồn quá lớn. Thu hẹp bộ lọc.', 422)
            result=json.loads(raw)
            if not result.get('ok'): raise ReportError('Nguồn chưa sẵn sàng.', 502)
            # Preserve the existing app's idle-session renewal; never mint cookies.
            if path == '/api/auth/me':
                for cookie in response.headers.get_all('Set-Cookie', []):
                    if cookie.startswith('session='): g.session_refresh = cookie
            return result
    except HTTPError as error:
        if error.code in (401,403,404): raise ReportError({401:'Phiên hết hạn. Đăng nhập lại.',403:'Nguồn từ chối quyền truy cập.',404:'Không tìm thấy đối tượng trong hệ thống này.'}[error.code], error.code)
        raise ReportError('Nguồn báo cáo chưa sẵn sàng.', 502)
    except (TimeoutError, OSError, ValueError): raise ReportError('Không thể đọc nguồn. Hãy thử lại hoặc thu hẹp bộ lọc.', 503)


def current_user(required=True):
    if not session_cookie():
        if required: raise ReportError('Cần đăng nhập để xem dữ liệu MES.', 401)
        return None
    try: return backend('/api/auth/me')['user']
    except ReportError as error:
        if not required and error.status==401: return None
        raise


def rate(key, maximum=6):
    now=time.monotonic()
    with lock:
        for k in list(rates):
            if now-rates[k][-1]>=60: del rates[k]
        hits=[x for x in rates.get(key,[]) if now-x<60]
        if len(hits)>=maximum or (key not in rates and len(rates)>=2000): raise ReportError('Đã đạt giới hạn. Thử lại sau một phút.',429)
        rates[key]=hits+[now]


def peer():
    # nginx overwrites this header; the service has no published host port.
    return request.headers.get('X-Report-Client-IP', request.remote_addr)


def snapshot_freshness(record):
    metadata = record.get('snapshot')
    if not metadata: return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(metadata['generated_at'])).total_seconds()
    return {**metadata, 'age_seconds': round(age, 1), 'stale': age > metadata['ttl_seconds']}


def audit(action, owner, record, **extra):
    event={'at':datetime.now(timezone.utc).isoformat(),'action':action,'user_id':owner,'report_id':record['id'], 'mode':record['mode'],
           'filters':record['intent'],'row_count':len(record['rows']),'snapshot':snapshot_freshness(record),**extra}
    try:
        encoded=(json.dumps(event,ensure_ascii=False)+'\n').encode()
        # Append metadata only; report rows, cookie, raw prompt and AI key never logged.
        with lock:
            fd=os.open(AUDIT,os.O_WRONLY|os.O_APPEND|os.O_CREAT,0o600)
            try:
                if os.write(fd,encoded)!=len(encoded): raise OSError('short audit write')
                os.fsync(fd)
            finally: os.close(fd)
    except OSError: raise ReportError('Không ghi được nhật ký xuất báo cáo; yêu cầu đã bị chặn.',503)


def ai_select(candidates, period):
    """Only public enums and report definitions go upstream, never filters/data."""
    key=(tuple(candidates),period); now=time.monotonic()
    with lock:
        if key in ai_cache and now-ai_cache[key][0]<300: return ai_cache[key][1], 'gateway_cached'
        ai_budget[:]=[x for x in ai_budget if now-x<3600]
        if not GATEWAY_KEY or len(ai_budget)>=20: return None,'rules'
        ai_budget.append(now)
    def call(path,payload=None,timeout=20):
        req=Request('https://ai-gateway.mesflow.net/v1'+path,data=json.dumps(payload).encode() if payload else None,
                    headers={'Authorization':'Bearer '+GATEWAY_KEY,'Content-Type':'application/json','User-Agent':'MESFlow-report-assistant/1.0','X-AIGW-Source':'mesflow-report-intent'})
        with urlopen(req,timeout=timeout) as response:
            if response.status!=200: raise ValueError()
            raw=response.read(65537)
            if len(raw)>65536: raise ValueError()
            return json.loads(raw)
    try:
        allowed={'grok-web','gemini-web','deepseek-web'}
        route=next(x for x in call('/models',timeout=4)['data'] if x['id']=='facebook-chat')
        if not set(route.get('candidates',[])) or not set(route['candidates'])<=allowed or route.get('capabilities',{}).get('queued') is not False: raise ValueError()
        payload={'model':'facebook-chat','stream':False,'max_tokens':120,'temperature':0,'messages':[
            {'role':'system','content':'Interpret public MESFlow report intent only. Return JSON ONLY with exactly report_type and period. Select report_type from supplied candidates. period must equal supplied period (including null). Never output SQL, URLs, data, contact or pricing. Report meanings: '+json.dumps({k:v[0] for k,v in TYPES.items()})},
            {'role':'user','content':json.dumps({'candidates':candidates,'period':period})}]}
        response=call('/chat/completions',payload)
        if response.get('gateway',{}).get('provider') not in allowed: raise ValueError()
        value=json.loads(response['choices'][0]['message']['content'])
        if set(value)!={'report_type','period'} or value['report_type'] not in candidates or value['period']!=period: raise ValueError()
        with lock: ai_cache[key]=(time.monotonic(),value)
        return value,'gateway'
    except Exception: return None,'rules'


@app.get('/reports')
def page(): return send_from_directory(Path(__file__).parent, 'reports.html')


@app.get('/health')
def health(): return jsonify(ok=True)


@app.get('/reports-api/status')
def status():
    user=current_user(False)
    return jsonify(authenticated=bool(user),types={k:v[0] for k,v in TYPES.items()},mode='live' if user else 'demo')


@app.post('/reports-api/intent')
def intent():
    value=body({'request','mode'})
    if value.get('mode') not in ('demo','live'): raise ReportError('Chọn chế độ dữ liệu.')
    user=current_user() if value['mode']=='live' else None
    rate(('intent',user['id'] if user else peer()))
    filters,candidates,period=extract(value.get('request'))
    if user:
        for kind in candidates: authorize(user,kind)
    selected,source=ai_select(candidates,period) if candidates else (None,'rules')
    if selected: filters['report_type']=selected['report_type']
    missing=[field for field in ('report_type','from','to') if not filters[field]]
    if filters['report_type']=='po_progress' and not filters['po_id']: missing.append('po_id')
    return jsonify(intent=filters,missing=missing,source=source,notice='Kiểm tra loại báo cáo và tất cả bộ lọc trước khi xem trước. AI không nhận câu hỏi gốc, ID, dữ liệu MES hoặc lịch sử chat.')


@app.post('/reports-api/preview')
def preview():
    value=body({'intent','mode'})
    if value.get('mode') not in ('demo','live'): raise ReportError('Chọn chế độ dữ liệu.')
    filters=validate(value.get('intent'))
    user=current_user() if value['mode']=='live' else None
    owner=user['id'] if user else 'demo'
    if user:
        authorize(user,filters['report_type'])
        if (filters['po_id'] or filters['operation_id']) and user.get('role') not in ('admin','super_admin') and 'po.view' not in user.get('permissions',[]):
            raise ReportError('Bạn chưa có quyền xem PO/công đoạn.',403)
    rate(('preview',owner if user else peer()))
    if not slots.acquire(blocking=False): raise ReportError('Đang xử lý báo cáo khác. Thử lại sau.',429)
    try:
        source = SnapshotSource(SNAPSHOT_DIR, filters) if user else None
        data = project(filters, source.get) if source else demo(filters)
        if source: data['snapshot'] = source.metadata
    finally: slots.release()
    now=time.monotonic()
    record={**data,'id':secrets.token_urlsafe(24),'intent':filters,'mode':value['mode'],'owner':owner,'created':now,'downloads':0,'generated_at':data.get('snapshot', {}).get('generated_at', datetime.now(timezone.utc).isoformat())}
    audit('REPORT_PREVIEW',owner,record)
    with lock:
        for token in list(snapshots):
            if now-snapshots[token]['created']>300: del snapshots[token]
        owned=[r for r in snapshots.values() if r['owner']==owner]
        if len(owned)>=3: snapshots.pop(min(owned,key=lambda r:r['created'])['id'])
        if len(snapshots)>=30: raise ReportError('Bộ nhớ báo cáo đang đầy. Thử lại sau.',429)
        snapshots[record['id']]=record
    return jsonify({**{k:v for k,v in record.items() if k not in ('owner','created','downloads')},'expires_in':300})


@app.post('/reports-api/chat-data')
def chat_data():
    """Internal authenticated facts; never a public/external AI integration."""
    value = body({'intent'})
    filters = validate(value.get('intent'))
    user = current_user()
    authorize(user, filters['report_type'])
    if (filters['po_id'] or filters['operation_id']) and user.get('role') not in ('admin', 'super_admin') and 'po.view' not in user.get('permissions', []):
        raise ReportError('Bạn chưa có quyền xem PO/công đoạn.', 403)
    rate(('chat-data', user['id']), 30)
    if not slots.acquire(blocking=False): raise ReportError('Đang xử lý báo cáo khác. Thử lại sau.', 429)
    try:
        source = SnapshotSource(SNAPSHOT_DIR, filters)
        report = project(filters, source.get)
    finally:
        slots.release()
    # Counts only: no names, entity IDs, free text, or invalid sums of PO/OP KPI.
    # These facts stay in MESFlow; they are NOT an approved Gateway payload.
    facts = {'report_type': filters['report_type'], 'row_count': len(report['rows'])}
    if filters['report_type'] == 'productivity':
        for key in ('completed_sessions', 'good_qty', 'defect_qty', 'worked_seconds'):
            facts[key] = sum(row[key] or 0 for row in report['rows'])
        scores = [row['productivity_percent'] for row in report['rows'] if row['productivity_percent'] is not None]
        facts['avg_employee_productivity_percent'] = round(sum(scores) / len(scores), 2) if scores else None
    return jsonify(facts=facts,
                   snapshot=source.metadata, external_ai_allowed=False)


@app.get('/reports-api/active-sessions')
def active_sessions():
    user = current_user()
    authorize(user, 'operation_output')
    rate(('active-sessions', user['id']), 30)
    data, metadata = load_snapshot(SNAPSHOT_DIR, 'active.json', 60)
    return jsonify(facts={'active_sessions': len(data['sessions']),
                          'active_employees': len({row['employee_id'] for row in data['sessions']})},
                   snapshot=metadata, external_ai_allowed=False)


def safe_cell(value):
    if not isinstance(value,str): return value
    value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value


def export_bytes(record,format):
    # Grants preserve exact rows for five minutes; freshness is measured again
    # at export, so an older frozen preview never claims to be freshly computed.
    record = {**record, 'snapshot': snapshot_freshness(record)}
    if format == 'pdf':
        if len(record['rows']) > 200:
            raise ReportError('PDF giới hạn 200 dòng. Thu hẹp bộ lọc hoặc tải Excel/CSV.', 422)
        if not pdf_slots.acquire(blocking=False):
            raise ReportError('Đang tạo PDF khác. Thử lại sau.', 429)
        try:
            encoded = json.dumps(record, ensure_ascii=False).encode()
            if len(encoded) > 1_000_000: raise ReportError('Báo cáo quá lớn cho PDF.', 422)
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('snapshot_pdf.py'))],
                                    input=encoded, capture_output=True, timeout=12, check=True)
            if not result.stdout.startswith(b'%PDF-'): raise ValueError()
            return result.stdout
        except (subprocess.SubprocessError, ValueError, OSError):
            raise ReportError('Bộ tạo PDF chưa sẵn sàng. Dùng In / Lưu PDF hoặc Excel.', 503)
        finally:
            pdf_slots.release()
    meta={'report_mode': 'DEMO — DỮ LIỆU MẪU' if record['mode']=='demo' else 'MES — dữ liệu theo quyền',
          'report_id':record['id'],'generated_at':record['generated_at'],'snapshot':json.dumps(record.get('snapshot'),ensure_ascii=False),
          'applied_filters':json.dumps(record['intent'],ensure_ascii=False),'sources':json.dumps(record['sources'],ensure_ascii=False),'notes':'\n'.join(record['notes'])}
    if format=='csv':
        output=io.StringIO(newline=''); writer=csv.writer(output)
        writer.writerow(record['columns']+list(meta))
        for row in record['rows']: writer.writerow([safe_cell(row.get(k)) for k in record['columns']]+list(meta.values()))
        return ('\ufeff'+output.getvalue()).encode('utf-8')
    workbook=Workbook(); sheet=workbook.active; sheet.title='DEMO' if record['mode']=='demo' else 'Data'
    sheet.append(record['columns']); sheet.freeze_panes='A2'
    for row in record['rows']: sheet.append([safe_cell(row.get(k)) for k in record['columns']])
    metadata=workbook.create_sheet('Nguon va bo loc')
    for key,value in meta.items(): metadata.append([key,safe_cell(value)])
    output=io.BytesIO(); workbook.save(output); return output.getvalue()


@app.post('/reports-api/export')
def export():
    value=body({'report_id','format'})
    if value.get('format') not in ('xlsx','csv','pdf') or not isinstance(value.get('report_id'),str): raise ReportError('Chỉ hỗ trợ Excel, CSV và PDF.')
    with lock: record=snapshots.get(value['report_id'])
    if not record or time.monotonic()-record['created']>300: raise ReportError('Bản xem trước đã hết hạn. Tạo lại báo cáo.',404)
    user=current_user() if record['mode']=='live' else None
    owner=user['id'] if user else 'demo'
    if owner!=record['owner']: raise ReportError('Báo cáo không thuộc phiên người dùng này.',403)
    if user:
        authorize(user,record['intent']['report_type'])
        if (record['intent']['po_id'] or record['intent']['operation_id']) and user.get('role') not in ('admin','super_admin') and 'po.view' not in user.get('permissions',[]):
            raise ReportError('Quyền xem PO/công đoạn không còn hiệu lực.',403)
    rate(('download',owner if user else peer()),10)
    with lock:
        if record['downloads']>=3: raise ReportError('Đã đạt 3 lượt tải cho bản xem trước này. Tạo lại báo cáo.',429)
        record['downloads']+=1
    payload=export_bytes(record,value['format']); digest=hashlib.sha256(payload).hexdigest()
    audit('REPORT_DOWNLOAD_GRANTED',owner,record,format=value['format'],bytes=len(payload),sha256=digest)
    name=('DEMO_' if record['mode']=='demo' else 'MES_')+record['intent']['report_type']+'_'+record['intent']['from']+'_'+record['intent']['to']+'.'+value['format']
    response=send_file(io.BytesIO(payload),as_attachment=True,download_name=name,mimetype={'csv':'text/csv; charset=utf-8','pdf':'application/pdf','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}[value['format']])
    response.headers['X-Report-SHA256']=digest
    return response
