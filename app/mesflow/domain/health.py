from dataclasses import dataclass,field
from datetime import datetime
from enum import StrEnum
from typing import Any
class HealthStatus(StrEnum):HEALTHY='HEALTHY';DEGRADED='DEGRADED';DOWN='DOWN';UNKNOWN='UNKNOWN'
@dataclass(frozen=True)
class HealthCheckResult:
 component:str;status:HealthStatus;checked_at:datetime;latency_ms:int|None=None;message:str='';details:dict[str,Any]=field(default_factory=dict);critical:bool=False;configured:bool=True
def overall(results):
 active=[x for x in results if x.configured]
 if any(x.critical and x.status==HealthStatus.DOWN for x in active):return HealthStatus.DOWN
 if any(x.status in (HealthStatus.DOWN,HealthStatus.DEGRADED) for x in active):return HealthStatus.DEGRADED
 if active and all(x.status==HealthStatus.HEALTHY for x in active):return HealthStatus.HEALTHY
 return HealthStatus.UNKNOWN
