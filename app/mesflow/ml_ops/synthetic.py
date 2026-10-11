"""Labeled, deterministic non-sensitive operational fixtures, never IoT samples."""
from datetime import datetime, timedelta, timezone
import random


def samples():
    rng=random.Random(20261011)
    start=datetime(2026,10,1,tzinfo=timezone.utc)
    result=[]
    for i in range(240):
        duration=600+rng.uniform(-80,80);good=rng.randint(18,24);defect=rng.choice([0,0,0,1])
        abnormal=i>=228
        if abnormal:
            if i%3==0:duration=7200
            elif i%3==1:good=240
            else:defect=30
        result.append(dict(session_id=i+1,operation_id=1,ended_at=(start+timedelta(minutes=30*i)).isoformat(),
            duration_seconds=duration,good_qty=good,defect_qty=defect,synthetic_label=abnormal))
    return result
