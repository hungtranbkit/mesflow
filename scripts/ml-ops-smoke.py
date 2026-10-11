#!/usr/bin/env python3
"""Real PR #68 HTTP smoke; synthetic only, no kiosk/service/DB changes."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from mesflow.ml_ops.api import create_app
from mesflow.ml_ops.client import Engine
from mesflow.ml_ops.config import Config, secret
from mesflow.ml_ops.synthetic import samples
from mesflow.ml_ops.worker import run_batch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine-key-file',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args();os.umask(0o077)
    out=Path(args.out).resolve();out.mkdir(mode=0o700,parents=True,exist_ok=False)
    read_key=out/'read.key';read_key.write_text(secrets.token_urlsafe(48))
    cfg=Config(True,(1,),'synthetic',out/'state',read_key,Path(args.engine_key_file).resolve())
    config_file=out/'config.json'
    config_file.write_text(json.dumps(dict(schema_version=1,enabled=True,operations=[1],source='synthetic',
        state_dir=str(cfg.state_dir),read_key_file=str(read_key),engine_key_file=str(cfg.engine_key_file))))
    engine=Engine(secret(cfg.engine_key_file));rows=samples()
    start=time.monotonic();snapshot=run_batch(cfg,rows,engine,train=True);elapsed=time.monotonic()-start
    cohort=snapshot['cohorts'][0];assert cohort['status']=='ready'
    held=[r for r in rows if r['ended_at']>cohort['training_cutoff']]
    flagged={r['session_id'] for r in cohort['findings']}
    normal=[r for r in held if not r['synthetic_label']]
    injected=[r for r in held if r['synthetic_label']]
    fp=sum(r['session_id'] in flagged for r in normal)
    tp=sum(r['session_id'] in flagged for r in injected)
    # Actual adapter HTTP is exercised in a separate private process by the runbook;
    # this in-process contract probe verifies no per-request gateway calls.
    client=create_app(lambda:Config.load(config_file)).test_client()
    assert client.get('/v1/ops-anomalies').status_code==401
    headers={'Authorization':'Bearer '+secret(read_key)}
    latencies=[]
    for _ in range(20):
        before=time.perf_counter();response=client.get('/v1/ops-anomalies',headers=headers)
        assert response.status_code==200
        latencies.append((time.perf_counter()-before)*1000)
    evidence=dict(status='PASS',source='synthetic',engine='real IsolationForest via 127.0.0.1:18788',
        train_predict_seconds=round(elapsed,3),training_rows=cohort['training_rows'],heldout_rows=len(held),
        heldout_normal=len(normal),heldout_injected=len(injected),false_positives=fp,
        synthetic_false_positive_rate=fp/len(normal),detected_injected=tp,
        distribution=cohort['distribution'],flagged_fraction=cohort['flagged_fraction'],
        api_in_process_p95_ms=round(sorted(latencies)[18],3),
        real_assessment='BLOCKED: no approved scoped readonly MESFlow credential or human-reviewed labels supplied',
        accuracy_claim=False,no_business_writes=True,no_production_restart=True,
        rollback='stop only adapter process; disable config; preserve or securely remove private pilot state')
    (out/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
