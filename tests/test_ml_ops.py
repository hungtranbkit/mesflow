from datetime import datetime, timedelta, timezone
import pytest
from mesflow.ml_ops.domain import features, baseline, explain, split, DataError


def rows(n=120):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    return [dict(session_id=i+1,operation_id=1,ended_at=(start+timedelta(hours=i)).isoformat(),
                 duration_seconds=600+(i%9-4)*10,good_qty=20+i%3,defect_qty=i%2) for i in range(n)]


def test_temporal_holdout_and_physical_evidence():
    train,held=split(rows())
    assert len(train)==96 and len(held)==24
    assert train[-1]['ended_at']<held[0]['ended_at']
    b=baseline(train)
    evidence=explain(dict(rows(1)[0],duration_seconds=7200),b)
    assert evidence[0]['feature']=='elapsed_seconds'
    assert evidence[0]['observed']==7200 and evidence[0]['outside_baseline']
    assert 'sensor' not in str(evidence)


@pytest.mark.parametrize('value',[float('nan'),float('inf'),True,-1,'60',None])
def test_invalid_numeric_fails_closed(value):
    with pytest.raises(DataError):features(dict(rows(1)[0],duration_seconds=value))


def test_zero_quantity_is_defined_not_division_by_zero():
    assert features(dict(rows(1)[0],good_qty=0,defect_qty=0))[1:]==[0,0]


def test_no_data_gate_and_no_duplicate_leakage():
    with pytest.raises(DataError):split(rows(99))
    with pytest.raises(DataError):split(rows()+rows())


def test_constant_baseline_has_practical_floor():
    r=[dict(x,duration_seconds=600,good_qty=20,defect_qty=0) for x in rows()]
    b=baseline(r)
    assert not any(e['outside_baseline'] for e in explain(dict(r[0],duration_seconds=610),b))
    assert any(e['outside_baseline'] for e in explain(dict(r[0],duration_seconds=1200),b))

from pathlib import Path
from mesflow.ml_ops.config import Config, secret
from mesflow.ml_ops.client import Engine, EngineError


def test_config_scope_changes_and_secret_permissions(tmp_path):
    p=tmp_path/'key';p.write_text('x'*48);p.chmod(0o600)
    assert secret(p)=='x'*48
    p.chmod(0o644)
    with pytest.raises(DataError):secret(p)
    c=Config(True,(1,),'synthetic',tmp_path,p,p)
    assert c.scope!=Config(True,(2,),'synthetic',tmp_path,p,p).scope
    assert c.scope!=Config(True,(1,),'real',tmp_path,p,p).scope


def test_engine_rejects_mock_schema_and_feature_drift(monkeypatch):
    engine=Engine('k'*48);mid='a'*32
    manifest=dict(model_id=mid,status='ready',schema_version=1,manifest_version=1,algorithm_version=1,
                  algorithm='isolation_forest',features=['wrong'],source='synthetic')
    with pytest.raises(EngineError):engine.validate(manifest,mid,'synthetic')
    from mesflow.ml_ops.domain import FEATURES
    manifest['features']=FEATURES
    monkeypatch.setattr(engine,'request',lambda method,route,body=None:manifest if method=='GET' else
                        dict(model_id=mid,schema_version=1,is_mock=True,predictions=[1]))
    with pytest.raises(EngineError):engine.predict(mid,[[1,2,0]],'synthetic')
    with pytest.raises(EngineError):engine.model_id('../etc/passwd')


from mesflow.ml_ops.store import Store
from mesflow.ml_ops.worker import run_batch
from mesflow.ml_ops.api import create_app


class FakeEngine:
    def __init__(self):self.trains=0;self.predicts=0
    def train(self,matrix,source):self.trains+=1;return 'a'*32
    def predict(self,mid,matrix,source):self.predicts+=1;return [1]*len(matrix)


def config(tmp_path, source='synthetic'):
    key=tmp_path/'read.key';key.write_text('r'*48);key.chmod(0o600)
    engine=tmp_path/'engine.key';engine.write_text('e'*48);engine.chmod(0o600)
    return Config(True,(1,),source,tmp_path/'state',key,engine)


def test_worker_train_opt_in_and_no_data_gate(tmp_path):
    c=config(tmp_path);engine=FakeEngine()
    value=run_batch(c,rows(10),engine,train=True,now=10000)
    assert value['cohorts'][0]['status']=='insufficient_data' and engine.trains==0
    value=run_batch(c,rows(),engine,now=10301)
    assert value['cohorts'][0]['status']=='model_required' and engine.trains==0
    value=run_batch(c,rows(),engine,train=True,now=10602)
    assert value['cohorts'][0]['status']=='ready' and engine.trains==1
    run_batch(c,rows(),engine,now=10903)
    assert engine.trains==1
    with pytest.raises(DataError):run_batch(c,rows(),engine,now=10904)


def test_api_reads_only_rechecks_scope_key_and_ttl(tmp_path):
    c=config(tmp_path);engine=FakeEngine();run_batch(c,rows(),engine,train=True,now=10000)
    app=create_app(lambda:c,clock=lambda:10001);client=app.test_client();h={'Authorization':'Bearer '+'r'*48}
    assert client.get('/v1/ops-anomalies').status_code==401
    assert client.get('/v1/ops-anomalies',headers=h).status_code==200
    assert client.post('/v1/ops-anomalies',headers=h).status_code==405
    assert client.get('/v1/ops-anomalies?operation_id=2',headers=h).status_code==400
    c.read_key_file.write_text('s'*48)
    assert client.get('/v1/ops-anomalies',headers=h).status_code==401
    assert engine.trains==1
    changed=Config(True,(2,),'synthetic',c.state_dir,c.read_key_file,c.engine_key_file)
    assert create_app(lambda:changed,clock=lambda:10001).test_client().get('/v1/ops-anomalies',headers={'Authorization':'Bearer '+'s'*48}).status_code==503
    assert create_app(lambda:c,clock=lambda:11000).test_client().get('/v1/ops-anomalies',headers={'Authorization':'Bearer '+'s'*48}).status_code==503


def test_api_rate_limit_and_disabled(tmp_path):
    c=config(tmp_path);run_batch(c,rows(),FakeEngine(),train=True,now=10000)
    client=create_app(lambda:c,clock=lambda:10001).test_client();h={'Authorization':'Bearer '+'r'*48}
    for _ in range(30):assert client.get('/v1/ops-anomalies',headers=h).status_code==200
    assert client.get('/v1/ops-anomalies',headers=h).status_code==429
    off=Config(False,c.operations,c.source,c.state_dir,c.read_key_file,c.engine_key_file)
    assert create_app(lambda:off).test_client().get('/v1/ops-anomalies',headers=h).status_code==503


def test_source_error_overwrites_old_result_and_scope_rejects_rows(tmp_path):
    c=config(tmp_path);engine=FakeEngine()
    with pytest.raises(DataError):run_batch(c,[dict(x,operation_id=9) for x in rows()],engine,train=True,now=10000)
    assert engine.trains==0


def test_worker_failure_invalidates_previous_snapshot_and_cooldown(tmp_path):
    c=config(tmp_path);e=FakeEngine();run_batch(c,rows(),e,train=True,now=10000)
    def failure():raise RuntimeError('sensitive DB error must not reach API')
    with pytest.raises(RuntimeError):run_batch(c,failure,e,now=10301)
    assert Store(c.state_dir).read('snapshot.json')['status']=='unavailable'
    with pytest.raises(DataError,match='training_cooldown'):run_batch(c,rows(),e,train=True,now=10602)
    assert e.trains==1


def test_model_expiration_requires_explicit_training(tmp_path):
    c=config(tmp_path);e=FakeEngine();run_batch(c,rows(),e,train=True,now=10000)
    result=run_batch(c,rows(),e,now=10000+8*86400)
    assert result['cohorts'][0]['status']=='model_expired' and e.trains==1


def test_cold_corrupt_and_future_snapshots_are_unavailable(tmp_path):
    c=config(tmp_path);h={'Authorization':'Bearer '+'r'*48}
    client=create_app(lambda:c,clock=lambda:10000).test_client()
    assert client.get('/v1/ops-anomalies',headers=h).status_code==503
    run_batch(c,rows(),FakeEngine(),train=True,now=10100)
    assert client.get('/v1/ops-anomalies',headers=h).status_code==503
    (c.state_dir/'snapshot.json').write_text('{bad JSON')
    assert client.get('/v1/ops-anomalies',headers=h).status_code==503


def test_state_lock_prevents_concurrent_worker(tmp_path):
    s=Store(tmp_path/'state',create=True)
    with s.lock():
        with pytest.raises(DataError,match='worker_busy'):
            with s.lock():pass


@pytest.mark.parametrize('status,body',[(302,b'{}'),(401,b'{}'),(429,b'{}'),(503,b'{}'),(200,b'invalid'),(200,b'[]'),(200,b'x'*(256*1024+1))])
def test_engine_protocol_errors_are_sanitized(monkeypatch,status,body):
    class Response:
        def read(self,size):return body
    Response.status=status
    class Connection:
        def __init__(self,host,port,timeout):assert (host,port,timeout)==('127.0.0.1',18788,12)
        def request(self,*args):pass
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr('mesflow.ml_ops.client.http.client.HTTPConnection',Connection)
    with pytest.raises(EngineError):Engine('k'*48).request('GET','/algorithms')


def test_engine_timeout_does_not_echo_secret(monkeypatch):
    class Connection:
        def __init__(self,*a,**kw):pass
        def request(self,*a):raise TimeoutError('secret credential and raw data')
        def close(self):pass
    monkeypatch.setattr('mesflow.ml_ops.client.http.client.HTTPConnection',Connection)
    with pytest.raises(EngineError) as exc:Engine('k'*48).request('GET','/algorithms')
    assert 'secret' not in str(exc.value)


def test_constant_training_data_gated(tmp_path):
    c=config(tmp_path);e=FakeEngine()
    same=[dict(r,duration_seconds=600,good_qty=20,defect_qty=0) for r in rows()]
    result=run_batch(c,same,e,train=True,now=10000)
    assert result['cohorts'][0]['status']=='insufficient_variation' and e.trains==0


def test_engine_key_failure_invalidates_ready_snapshot(tmp_path):
    c=config(tmp_path);run_batch(c,rows(),FakeEngine(),train=True,now=10000)
    c.engine_key_file.unlink()
    with pytest.raises(OSError):run_batch(c,rows(),lambda:Engine(secret(c.engine_key_file)),now=10301)
    assert Store(c.state_dir).read('snapshot.json')['status']=='unavailable'

    client=create_app(lambda:c,clock=lambda:10302).test_client()
    assert client.get('/v1/ops-anomalies',headers={'Authorization':'Bearer '+'r'*48}).status_code==503


@pytest.mark.parametrize('field,value',[('algorithm_version',2),('schema_version',True),('manifest_version',2),('source','client-provided'),('status','retired')])
def test_manifest_version_and_source_drift_fail_closed(field,value):
    from mesflow.ml_ops.domain import FEATURES
    manifest=dict(model_id='a'*32,status='ready',schema_version=1,manifest_version=1,algorithm_version=1,
                  algorithm='isolation_forest',features=FEATURES,source='synthetic')
    manifest[field]=value
    with pytest.raises(EngineError):Engine('k'*48).validate(manifest,'a'*32,'synthetic')


def test_interrupted_staging_files_are_reaped_under_lock(tmp_path):
    store=Store(tmp_path/'state',create=True)
    orphan=store.root/'.snapshot.jsoninterrupted';orphan.write_text('partial')
    with store.lock():assert not orphan.exists()
