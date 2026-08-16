"""Phase 3 Predictive / AI: shared types + small, explainable statistics
helpers. No numpy/pandas/sklearn -- MESFlow does not depend on them, and
these calculations (linear trend, mean/stdev, MAD) are simple enough not
to need them (section 8: "start simple and explainable... before complex
ML")."""
from __future__ import annotations
from dataclasses import dataclass,field
from datetime import datetime
from enum import StrEnum
from typing import Any


class RiskLevel(StrEnum):
 INFO='INFO';LOW='LOW';MEDIUM='MEDIUM';HIGH='HIGH'


class Confidence(StrEnum):
 HIGH='HIGH';MEDIUM='MEDIUM';LOW='LOW';INSUFFICIENT_DATA='INSUFFICIENT_DATA'


@dataclass(frozen=True)
class ForecastResult:
 metric:str;component:str;available:bool;confidence:Confidence
 current_value:float|None=None
 growth_per_day:float|None=None
 days_to_warning:float|None=None
 days_to_critical:float|None=None
 r_squared:float|None=None
 sample_count:int=0
 span_hours:float=0.0
 reason:str=''


@dataclass(frozen=True)
class AnomalyResult:
 metric:str;component:str;detected:bool
 actual:float|None=None
 expected_low:float|None=None
 expected_high:float|None=None
 deviation:float|None=None  # multiples of baseline stdev/MAD
 confidence:Confidence=Confidence.INSUFFICIENT_DATA
 sample_count:int=0
 reason:str=''


def mean(xs:list[float])->float:return sum(xs)/len(xs) if xs else 0.0


def stdev(xs:list[float])->float:
 if len(xs)<2:return 0.0
 m=mean(xs)
 return (sum((x-m)**2 for x in xs)/(len(xs)-1))**0.5


def median(xs:list[float])->float:
 if not xs:return 0.0
 s=sorted(xs);n=len(s);mid=n//2
 return s[mid] if n%2 else (s[mid-1]+s[mid])/2


def mad(xs:list[float])->float:
 """Median Absolute Deviation -- robust to outliers, unlike stdev."""
 if not xs:return 0.0
 m=median(xs)
 return median([abs(x-m) for x in xs])*1.4826  # scaled to be comparable to stdev for normal data


def linear_regression(points:list[tuple[float,float]])->tuple[float,float,float]:
 """points: [(x,y), ...]. Returns (slope, intercept, r_squared) via
 ordinary least squares. Pure Python -- no numpy."""
 n=len(points)
 if n<2:return 0.0,0.0,0.0
 xs=[p[0] for p in points];ys=[p[1] for p in points]
 mx,my=mean(xs),mean(ys)
 sxx=sum((x-mx)**2 for x in xs)
 sxy=sum((x-mx)*(y-my) for x,y in points)
 if sxx==0:return 0.0,my,0.0
 slope=sxy/sxx;intercept=my-slope*mx
 ss_tot=sum((y-my)**2 for y in ys)
 ss_res=sum((y-(slope*x+intercept))**2 for x,y in points)
 r2=1-(ss_res/ss_tot) if ss_tot>0 else (1.0 if ss_res==0 else 0.0)
 return slope,intercept,max(0.0,min(1.0,r2))
