from __future__ import annotations
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo
from mesflow.core.config import settings

UTC=timezone.utc

def site_zone(name:str|None=None)->ZoneInfo:
    return ZoneInfo(name or settings.timezone_name)

def utc_now()->datetime:
    return datetime.now(UTC)

def site_now(now:datetime|None=None,timezone_name:str|None=None)->datetime:
    value=now or utc_now()
    if value.tzinfo is None:raise ValueError('naive datetime is not allowed in production time logic')
    return value.astimezone(site_zone(timezone_name))

def business_date(now:datetime|None=None,timezone_name:str|None=None)->date:
    return site_now(now,timezone_name).date()

def aware_utc(value:datetime|None,*,naive_timezone_name:str|None=None)->datetime|None:
    if value is None:return None
    if value.tzinfo is None:value=value.replace(tzinfo=site_zone(naive_timezone_name))
    return value.astimezone(UTC)

def business_datetime_utc(value:date,wall_time:time=time.min,timezone_name:str|None=None)->datetime:
    """Interpret a factory business date/wall-clock in the site zone, then convert to UTC."""
    if isinstance(value,datetime):
        raise TypeError('business_datetime_utc expects a date, not datetime')
    local=datetime.combine(value,wall_time,tzinfo=site_zone(timezone_name))
    return local.astimezone(UTC)

def business_date_start_utc(value:date,timezone_name:str|None=None)->datetime:
    return business_datetime_utc(value,time.min,timezone_name)

def business_date_end_utc(value:date,timezone_name:str|None=None)->datetime:
    return business_datetime_utc(value,time(23,59,59,999999),timezone_name)

def coerce_utc(value:date|datetime|None,*,date_time:time=time.min,naive_timezone_name:str|None=None)->datetime|None:
    if value is None:return None
    if isinstance(value,datetime):return aware_utc(value,naive_timezone_name=naive_timezone_name)
    if isinstance(value,date):return business_datetime_utc(value,date_time,naive_timezone_name)
    raise TypeError(f'unsupported temporal value: {type(value).__name__}')

def parse_datetime_utc(value:str|datetime,timezone_name:str|None=None)->datetime:
    if isinstance(value,datetime):return aware_utc(value,naive_timezone_name=timezone_name)
    parsed=datetime.fromisoformat(str(value).strip().replace('Z','+00:00'))
    return aware_utc(parsed,naive_timezone_name=timezone_name)
