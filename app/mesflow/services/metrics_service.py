"""Phase 3 Predictive / AI: bounded historical metric collection.

Deliberately narrow (section 3): only what Step 1/2/3 of this phase
actually need -- disk, DB size (+ a cheap top-tables snapshot), CPU, and
MESFlow's own latency. Reuses the exact same data Phase 1's health
providers already fetch (Deploy Agent's /api/ops/summary,
PostgreSQL SELECTs) rather than opening a second privileged probe.
"""
from __future__ import annotations
import time
from datetime import datetime,timedelta,timezone
from mesflow.core.config import settings
from mesflow.db.connection import fetch_all,fetch_one,transaction


def now():return datetime.now(timezone.utc)


class MetricsCollector:
 def collect(self):
  """One collection pass: disk, DB size (+ top tables), CPU, DB latency.
  Returns the list of (metric, component, value, unit, metadata) samples
  actually written -- callers/tests can inspect what happened without a
  second query."""
  written=[]
  written+=self._collect_infra()
  written+=self._collect_db()
  self._persist(written)
  return written

 def _collect_infra(self):
  from mesflow.services.system_health_service import DeployAgentFetch
  fetch=DeployAgentFetch().fetch()
  if fetch.health_error or not fetch.ops:return []
  ops=fetch.ops;out=[]
  disk=ops.get('disk') or {}
  if disk.get('percent') is not None:
   out.append(('DISK_USAGE_PERCENT',settings.predictive_disk_component,float(disk['percent']),'%',
               {'used_bytes':disk.get('used_bytes'),'total_bytes':disk.get('total_bytes'),'free_bytes':disk.get('free_bytes')}))
  if disk.get('used_bytes') is not None:
   out.append(('DISK_USED_BYTES',settings.predictive_disk_component,float(disk['used_bytes']),'bytes',{}))
  if ops.get('cpu_percent') is not None:
   out.append(('CPU_PERCENT','',float(ops['cpu_percent']),'%',{}))
  ram=ops.get('ram') or {}
  if ram.get('percent') is not None:
   out.append(('RAM_PERCENT','',float(ram['percent']),'%',{}))
  return out

 def _collect_db(self):
  out=[]
  t=time.perf_counter()
  try:
   size=fetch_one("SELECT pg_database_size(current_database()) bytes")['bytes']
   latency_ms=int((time.perf_counter()-t)*1000)
   out.append(('DB_SIZE_BYTES','primary',float(size),'bytes',{}))
   out.append(('DB_LATENCY_MS','primary',float(latency_ms),'ms',{}))
   # Top-5 growing tables: cheap catalog stats, not a live table scan
   # (section 11/41 -- do not run this on every page refresh; this only
   # runs from the periodic collector job).
   top=fetch_all("""SELECT relname,pg_total_relation_size(relid) bytes FROM pg_catalog.pg_statio_user_tables
     ORDER BY bytes DESC LIMIT 5""")
   out.append(('DB_TOP_TABLES','primary',float(size),'bytes',{'tables':[{'name':r['relname'],'bytes':r['bytes']} for r in top]}))
  except Exception:
   pass
  return out

 def _persist(self,samples):
  if not samples:return
  with transaction() as conn:
   with conn.cursor() as cur:
    for metric,component,value,unit,metadata in samples:
     import json
     cur.execute("INSERT INTO health_metric_samples(metric,component,value,unit,metadata_json) VALUES(%s,%s,%s,%s,%s)",
                 (metric,component,value,unit,json.dumps(metadata,default=str)))

 def cleanup(self,retention_days=None):
  """Bounded retention (section 5). No aggregation tiers implemented yet
  (section 47 is a documented follow-up) -- high-resolution samples are
  simply dropped past retention_days."""
  days=retention_days if retention_days is not None else settings.metric_sample_retention_days
  cutoff=now()-timedelta(days=days)
  with transaction() as conn:
   with conn.cursor() as cur:
    cur.execute("DELETE FROM health_metric_samples WHERE sampled_at<%s",(cutoff,))
    return cur.rowcount


def samples_for(metric,component='',days=30):
 cutoff=now()-timedelta(days=days)
 return fetch_all("SELECT value,sampled_at,metadata_json FROM health_metric_samples WHERE metric=%s AND component=%s AND sampled_at>=%s ORDER BY sampled_at",
                   (metric,component,cutoff))
