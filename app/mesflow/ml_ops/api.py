"""Private machine-to-machine snapshot reader. No ML client or DB credential use."""
import argparse
from collections import deque
import hmac
import threading
import time
from flask import Flask, jsonify, request
from .config import Config, secret
from .domain import CONTRACT, TTL
from .store import Store


def create_app(load_config,clock=time.time):
    app=Flask(__name__)
    app.config['MAX_CONTENT_LENGTH']=1024
    accepted=deque();attempts=deque();lock=threading.Lock()

    @app.after_request
    def private(response):
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.get('/v1/ops-anomalies')
    def read():
        try:
            with lock:
                while attempts and clock()-attempts[0]>=60:attempts.popleft()
                if len(attempts)>=120:return jsonify(error='rate_limited'),429
                attempts.append(clock())
            config=load_config()
            if not config.enabled:return jsonify(error='adapter_disabled'),503
            key=secret(config.read_key_file)
            if len(key)<32:raise ValueError()
            if not hmac.compare_digest(request.headers.get('Authorization','').encode(),('Bearer '+key).encode()):
                return jsonify(error='unauthorized'),401
            if request.query_string or request.content_length or request.headers.get('Origin') or request.headers.get('Transfer-Encoding'):
                return jsonify(error='backend_only_no_overrides'),400
            now=clock()
            with lock:
                while accepted and now-accepted[0]>=60:accepted.popleft()
                if len(accepted)>=30:return jsonify(error='rate_limited'),429
                accepted.append(now)
            value=Store(config.state_dir).read('snapshot.json')
            if (value['scope']!=config.scope or value['source']!=config.source or
                value['feature_contract']!=CONTRACT or value['status']!='ready' or
                value['ttl_seconds']!=TTL or not 0<=now-value['generated_at']<=TTL or
                {c['operation_id'] for c in value['cohorts']}!=set(config.operations)):
                raise ValueError()
            value['age_seconds']=round(now-value['generated_at'],2)
            return jsonify(value)
        except Exception:
            return jsonify(error='snapshot_or_authorization_unavailable'),503
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',required=True)
    args=parser.parse_args()
    # No arbitrary bind override: never expose pilot to LAN or public nginx.
    from waitress import serve
    serve(create_app(lambda:Config.load(args.config)),host='127.0.0.1',port=18789,
          threads=2,connection_limit=16,channel_timeout=10,max_request_body_size=1024,
          clear_untrusted_proxy_headers=True)


if __name__=='__main__':main()
