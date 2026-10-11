"""Single opt-in batch. Schedule inference only; training requires --train."""
import argparse
import time
from .config import Config, secret
from .client import Engine, EngineError
from .domain import CONTRACT, TTL, DataError, baseline, distribution, explain, features, split, timestamp
from .source import read_sessions
from .store import Store

MODEL_TTL=7*86400


def envelope(config,now,status):
    return dict(schema_version=1,feature_contract=CONTRACT,scope=config.scope,source=config.source,
                generated_at=now,ttl_seconds=TTL,status=status,external_ai_allowed=False,
                human_review_required=True,cohorts=[])


def run_batch(config, rows, engine, *, train=False, now=None):
    if not config.enabled:raise DataError('adapter_disabled')
    now=time.time() if now is None else now
    store=Store(config.state_dir,create=True)
    with store.lock():
        control=store.read('control.json',dict(schema_version=1,scope=config.scope,last_run=0,models={},attempts={}))
        if control['scope']!=config.scope:raise DataError('scope_changed_new_state_required')
        if now-control['last_run']<300:raise DataError('batch_rate_limited')
        control['last_run']=now
        store.write('control.json',control)
        try:
            # Load inside the single-writer boundary so failed reads invalidate results.
            records=rows() if callable(rows) else rows
            if len(records)>2000 or any(r.get('operation_id') not in config.operations for r in records):
                raise DataError('source_scope_or_size_mismatch')
            client=None
            def get_engine():
                nonlocal client
                if client is None:client=engine() if callable(engine) else engine
                return client
            result=envelope(config,now,'ready')
            for op in config.operations:
                sample=[r for r in records if r['operation_id']==op]
                cohort={'operation_id':op,'sample_count':len(sample)}
                result['cohorts'].append(cohort)
                if len(sample)<100:
                    cohort['status']='insufficient_data';continue
                reference,held=split(sample)
                if len({tuple(features(r)) for r in reference})<10:
                    cohort['status']='insufficient_variation';continue
                name=str(op);model=control['models'].get(name)
                if train:
                    last=control['attempts'].get(name)
                    if last is not None and now-last<86400:raise DataError('training_cooldown')
                    control['attempts'][name]=now
                    store.write('control.json',control)  # no retry after an ambiguous submit
                    mid=get_engine().train([features(r) for r in reference],config.source)
                    model=dict(model_id=mid,trained_at=now,cutoff=reference[-1]['ended_at'],
                               training_rows=len(reference),baseline=baseline(reference))
                    control['models'][name]=model
                    store.write('control.json',control)
                if not model:
                    cohort['status']='model_required';continue
                if not 0<=now-model['trained_at']<=MODEL_TTL:
                    cohort['status']='model_expired';continue
                held=[r for r in sample if timestamp(r['ended_at'])>timestamp(model['cutoff'])]
                if not held:
                    cohort['status']='no_unseen_data';continue
                labels=get_engine().predict(model['model_id'],[features(r) for r in held],config.source)
                findings=[];rule_count=ml_count=combined_count=0
                for row,label in zip(held,labels):
                    evidence=explain(row,model['baseline'])
                    rule=any(e['outside_baseline'] for e in evidence);ml=label==-1
                    rule_count+=rule;ml_count+=ml;combined_count+=rule or ml
                    if rule or ml:
                        findings.append(dict(session_id=row['session_id'],ended_at=row['ended_at'],
                            isolation_forest_flag=ml,baseline_flag=rule,evidence=evidence,
                            interpretation='Statistical outlier for human review; not a defect or failure probability.'))
                if len(findings)>256:raise DataError('findings_limit_exceeded')
                cohort.update(status='ready',model_id=model['model_id'],training_rows=model['training_rows'],
                    training_cutoff=model['cutoff'],evaluated_rows=len(held),distribution=distribution(held),
                    flagged_fraction=combined_count/len(held),isolation_fraction=ml_count/len(held),
                    baseline_fraction=rule_count/len(held),findings=findings,
                    false_positive_rate=None,false_positive_reason='Human-reviewed normal labels unavailable; flag rate is not false-positive rate.')
            store.write('snapshot.json',result)
            return result
        except Exception:
            store.write('snapshot.json',envelope(config,now,'unavailable'))
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--train',action='store_true',help='Explicit bounded retraining; at most once/24h per OP')
    args=parser.parse_args()
    try:
        config=Config.load(args.config)
        if not config.enabled:raise DataError('adapter_disabled')
        if config.source!='real' or not config.dsn_file:raise DataError('real_readonly_source_required')
        engine=lambda:Engine(secret(config.engine_key_file))
        result=run_batch(config,lambda:read_sessions(secret(config.dsn_file),config.operations),engine,train=args.train)
        print('ML_OPS_BATCH',result['status'])
    except (DataError,EngineError,OSError,ValueError,KeyError):
        raise SystemExit('ML_OPS_BATCH blocked; inspect scoped configuration/credentials/data; no sensitive exception logged') from None
    except Exception:
        raise SystemExit('ML_OPS_BATCH unavailable; no sensitive exception logged') from None


if __name__=='__main__':main()
