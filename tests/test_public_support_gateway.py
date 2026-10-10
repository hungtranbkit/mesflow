"""Public assistant: no raw text, bounded real AI, honest local fast path."""
import importlib.util
from pathlib import Path
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest

ROOT = Path(__file__).resolve().parents[1]
AI = {'topics': ['qr', 'productivity'], 'intent': 'guide', 'consent': True}

@pytest.fixture
def server(monkeypatch):
    spec = importlib.util.spec_from_file_location('public_support', ROOT / 'services/public-support/server.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'GATEWAY_KEY', 'unit-test-only')
    yield module
    if hasattr(module, 'executor'): module.executor.shutdown(wait=True)


def fake_gateway(path, body=None, timeout=9):
    if path == '/models':
        return {'data': [{'id': 'facebook-chat', 'candidates': ['gemini-web'], 'capabilities': {'queued': False}}]}
    assert body['model'] == 'facebook-chat'
    prompt = json.loads(body['messages'][1]['content'])
    assert set(prompt) == {'public_question', 'sources'}
    assert 'quét' in prompt['public_question']
    assert all(set(s) == {'id', 'text'} for s in prompt['sources'])
    return {'gateway': {'provider': 'gemini-web'}, 'choices': [{'message': {'content': json.dumps({
        'answer': 'Quét thẻ nhân viên trước, rồi QR Operation để ghi nhận phiên [qr]. Sau đó xem Năng suất để đối chiếu thời gian thực tế và định mức [productivity].',
        'source_ids': ['qr', 'productivity']}, ensure_ascii=False)}}]}


def test_legacy_faq_is_instant_without_gateway(server, monkeypatch):
    monkeypatch.setattr(server, 'gateway_request', lambda *a, **k: pytest.fail('FAQ must not call AI'))
    start=time.monotonic()
    response=server.app.test_client().post('/support/chat', json={'topics':['excel']})
    assert time.monotonic()-start < .5
    assert response.json['mode']=='faq'
    assert 'một file Excel' in response.json['answer']
    assert response.json['sources'][0]['action_href']=='/reports'
    assert not server.budget


def test_grounded_answer_cache_and_no_headers_or_prompts_forwarded(server, monkeypatch):
    calls=[]
    def gateway(*a,**kw): calls.append(a[0]); return fake_gateway(*a,**kw)
    monkeypatch.setattr(server,'gateway_request',gateway)
    client=server.app.test_client()
    first=client.post('/support/chat',json=AI,headers={'Authorization':'private','Cookie':'session=private'})
    assert first.json['mode']=='gateway'
    assert 'đối chiếu' in first.json['answer']
    assert first.json['provider']=='gemini-web'
    assert client.post('/support/chat',json=AI).json['mode']=='gateway_cached'
    assert calls==['/models','/chat/completions']
    assert 'Set-Cookie' not in first.headers
    assert first.headers['Cache-Control']=='no-store'


@pytest.mark.parametrize('body', [
    {'topics':['excel'],'question':'private customer'}, {'messages':[]}, {'topics':['private']},
    {'topics':['excel','excel']},{'topics':[]},{'topics':[1]},[],
    {**AI,'consent':False},{**AI,'consent':1},{**AI,'intent':'ignore instructions'},
    {**AI,'topics':['login','qr']},{**AI,'history':['private']},
])
def test_unapproved_input_never_reaches_gateway(server,monkeypatch,body):
    monkeypatch.setattr(server,'gateway_request',lambda *a,**k:pytest.fail('must not call AI'))
    assert server.app.test_client().post('/support/chat',json=body).status_code==400


def test_limits_and_origin(server):
    c=server.app.test_client()
    assert c.post('/support/chat',json={'topics':['x'*2000]}).status_code==413
    assert c.post('/support/chat',json=AI,headers={'Origin':'https://evil.test'}).status_code==403
    assert c.get('/support/chat').status_code==405
    assert c.post('/support/chat',data='no').status_code==415


@pytest.mark.parametrize('failure',['timeout','mock','claude','queued','extra','unknown_ref','no_citation','price','url','too_long','invented_feature'])
def test_invalid_or_unsafe_ai_falls_back(server,monkeypatch,failure):
    def upstream(path,body=None,timeout=9):
        if failure=='timeout':raise TimeoutError()
        reply=fake_gateway(path,body,timeout)
        if path=='/models':
            if failure=='claude':reply['data'][0]['candidates'].append('claude-review')
            if failure=='queued':reply['data'][0]['capabilities']['queued']=True
        else:
            if failure=='mock':reply['gateway']['provider']='mock'
            result=json.loads(reply['choices'][0]['message']['content'])
            if failure=='extra':result['price']='$99'
            if failure=='unknown_ref':result['source_ids']=['private']
            if failure=='no_citation':result['answer']='Thông tin không có nguồn.'
            if failure=='price':result['answer']='Giá 99 USD [qr].'
            if failure=='url':result['answer']='Xem https://evil.test [qr].'
            if failure=='too_long':result['answer']='x'*1801
            if failure=='invented_feature':result['answer']='MESFlow tự động thanh toán bằng blockchain [qr].'
            reply['choices'][0]['message']['content']=json.dumps(result)
        return reply
    monkeypatch.setattr(server,'gateway_request',upstream)
    result=server.app.test_client().post('/support/chat',json=AI).json
    assert result['mode']=='faq'
    assert result['reason'] in ('timeout','unavailable','invalid_answer')
    assert 'quét thẻ' in result['answer']


def test_wall_deadline_dedupe_and_slots(server,monkeypatch):
    entered=threading.Event(); release=threading.Event(); calls=[]
    def slow(ids,intent,deadline):
        calls.append(ids);entered.set();release.wait(2)
        return {'mode':'gateway','topic_ids':ids,'answer':'ok','sources':[],'provider':'gemini-web'}
    monkeypatch.setattr(server,'generate_answer',slow)
    monkeypatch.setattr(server,'AI_DEADLINE',.08)
    with ThreadPoolExecutor(1) as pool:
        first=pool.submit(lambda:server.app.test_client().post('/support/chat',json=AI).json)
        assert entered.wait(1)
        duplicate=server.app.test_client().post('/support/chat',json=AI).json
        assert duplicate['reason']=='in_flight'
        start=time.monotonic();assert first.result()['reason']=='timeout';assert time.monotonic()-start<.3
        assert len(calls)==1
        release.set()


def test_rate_and_global_budget(server,monkeypatch):
    monkeypatch.setattr(server,'gateway_request',fake_gateway)
    c=server.app.test_client()
    for _ in range(6):assert c.post('/support/chat',json=AI).status_code==200
    assert c.post('/support/chat',json=AI).status_code==429
    # FAQ stays usable even when AI budget is exhausted.
    assert c.post('/support/chat',json={'topics':['qr']}).json['mode']=='faq'
    server.buckets.clear();server.cache.clear();server.budget[:]=[time.monotonic()]*20
    assert c.post('/support/chat',json=AI).json['reason']=='budget'


def test_aggregate_metrics_do_not_contain_questions_or_ips(server):
    c=server.app.test_client();c.post('/support/chat',json={'topics':['excel']})
    data=c.get('/internal/metrics').json
    assert data['latency_ms']['faq']['count']==1
    assert 'p50' in data['latency_ms']['faq']
    assert '127.0.0.1' not in json.dumps(data)


def test_knowledge_assets_and_inline_sync(server):
    import subprocess
    subprocess.run(['python3',str(ROOT/'scripts/sync-public-support.py'),'--check'],check=True)
    c=server.app.test_client()
    js=c.get('/support/assistant.js')
    assert js.status_code==200 and 'MESFlowSupport' in js.text
    assert 'reviewed_in' not in js.text and server.GATEWAY_KEY not in js.text
    kb=c.get('/support/knowledge')
    assert kb.status_code==200
    for id in server.FACTS: assert f'id="{id}"' in kb.text


def test_nginx_upgrade_only_changes_support_locations():
    spec=importlib.util.spec_from_file_location('nginx',ROOT/'scripts/prepare-support-assistant-nginx.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    original='before\n    location = /support/chat {\n      client_max_body_size 256;\n      proxy_set_header Cookie "";\n      proxy_set_header Authorization "";\n      proxy_read_timeout 27s;\n    }\nafter reports app'
    updated=m.prepare(original)
    assert updated.replace(m.PUBLIC,'').replace('1024;','256;').replace('11s;','27s;')==original
    assert '/internal/metrics' not in updated
    with pytest.raises(ValueError):m.prepare(updated)


def test_concurrency_two_workers_no_unbounded_queue(server,monkeypatch):
    entered=threading.Barrier(3);release=threading.Event()
    def slow(ids,intent,deadline):
        entered.wait(timeout=2);release.wait(2)
        return server.fallback(ids,'test')
    monkeypatch.setattr(server,'generate_answer',slow)
    with ThreadPoolExecutor(2) as pool:
        a=pool.submit(lambda:server.app.test_client().post('/support/chat',json=AI))
        b=pool.submit(lambda:server.app.test_client().post('/support/chat',json={**AI,'intent':'compare'}))
        entered.wait(timeout=2)
        c=server.app.test_client().post('/support/chat',json={**AI,'intent':'diagnose'})
        assert c.json['reason']=='busy'
        assert len(server.budget)==2
        release.set();a.result();b.result()
