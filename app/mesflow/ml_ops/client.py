"""Fixed HP loopback ML contract: no proxies, redirects, external URLs or retries."""
import http.client
import json
import re
import time
from .domain import FEATURES, DataError


class EngineError(RuntimeError):
    pass


class Engine:
    def __init__(self, key):
        if not isinstance(key,str) or not 24 <= len(key) <= 512 or '\n' in key or '\r' in key:
            raise DataError('invalid_engine_key')
        self.key = key

    def request(self, method, route, body=None):
        raw = json.dumps(body, allow_nan=False).encode() if body is not None else None
        if raw and len(raw) > 256*1024:
            raise DataError('engine_payload_too_large')
        conn = http.client.HTTPConnection('127.0.0.1',18788,timeout=12)
        try:
            conn.request(method,'/v1/ml'+route,raw,{'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
            response = conn.getresponse()
            content = response.read(256*1024+1)
            if response.status not in (200,202) or len(content)>256*1024:
                raise EngineError('engine_request_rejected')
            result = json.loads(content)
            if not isinstance(result,dict):
                raise EngineError('engine_contract_mismatch')
            return result
        except (OSError, http.client.HTTPException, ValueError):
            raise EngineError('engine_unavailable_or_invalid_response') from None
        finally:
            conn.close()

    @staticmethod
    def model_id(value):
        if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):
            raise EngineError('invalid_model_id')
        return value

    def train(self, rows, source):
        job = self.request('POST','/train',dict(schema_version=1,algorithm='isolation_forest',
            source='synthetic' if source=='synthetic' else 'client-provided',features=FEATURES,
            rows=rows,parameters={'n_estimators':64,'contamination':.05}))
        mid = self.model_id(job.get('model_id'))
        deadline = time.monotonic()+75
        while job.get('status')=='training' and time.monotonic()<deadline:
            time.sleep(.25)
            job = self.request('GET','/jobs/'+mid)
        self.validate(job, mid, source)
        return mid

    def validate(self, manifest, mid, source):
        if (manifest.get('model_id')!=mid or manifest.get('status')!='ready' or
            any(type(manifest.get(k)) is not int or manifest[k]!=1 for k in
                ('schema_version','manifest_version','algorithm_version')) or
            manifest.get('algorithm')!='isolation_forest' or manifest.get('features')!=FEATURES or
            manifest.get('source')!=('synthetic' if source=='synthetic' else 'client-provided')):
            raise EngineError('model_contract_or_status_mismatch')

    def predict(self, mid, rows, source):
        mid = self.model_id(mid)
        self.validate(self.request('GET','/models/'+mid),mid,source)
        result=[]
        for start in range(0,len(rows),256):
            chunk=rows[start:start+256]
            value=self.request('POST','/models/'+mid+'/predict',dict(schema_version=1,features=FEATURES,rows=chunk))
            preds=value.get('predictions')
            if (value.get('model_id')!=mid or value.get('schema_version')!=1 or value.get('is_mock') is not False or
                not isinstance(preds,list) or len(preds)!=len(chunk) or any(type(p) is not int or p not in (-1,1) for p in preds)):
                raise EngineError('invalid_prediction_contract')
            result.extend(preds)
        return result
