from __future__ import annotations
from datetime import date, datetime, time, timedelta, timezone
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

# Offline session timestamp integrity: a single place
# deciding whether a device-reported event timestamp is safe to use as a
# work_sessions.started_at/ended_at value, instead of blindly trusting server
# CURRENT_TIMESTAMP even when the offline event carries a real device clock
# reading. "Trusted" here means BOTH: the device itself reported synced
# clock quality (kiosk_client_events.time_quality=='synced' -- 'estimated'/
# 'unknown' never qualify, per the plan's own "never blindly trust unknown/
# estimated/impossible timestamps"), AND the value is not so far from the
# server's own clock that it is almost certainly wrong (a stuck RTC, an
# unset clock defaulting to epoch, a corrupted payload) rather than a
# genuinely late offline sync.
#
# MAX_PAST is deliberately generous (default 30 days) -- a device can be
# legitimately offline for a long outage and still have a correct clock;
# rejecting that would defeat the whole point of this phase. MAX_FUTURE is
# deliberately tight (default 5 minutes) -- ordinary clock drift, not "the
# device thinks it's next week", which is `time_quality` being wrong even
# though the device claims 'synced'.
DEFAULT_MAX_FUTURE_SKEW=timedelta(minutes=5)
DEFAULT_MAX_PAST_SKEW=timedelta(days=30)

def trusted_event_time(occurred_at:datetime|None,quality:str,*,server_now:datetime|None=None,
                        max_future_skew:timedelta=DEFAULT_MAX_FUTURE_SKEW,
                        max_past_skew:timedelta=DEFAULT_MAX_PAST_SKEW)->datetime|None:
    """Returns `occurred_at` (normalized to UTC) if it is safe to trust as a
    real event time, else None (caller must fall back to server-received
    time). Never raises -- an untrustworthy timestamp is a "don't use it"
    signal, not an error; the event itself is still processed."""
    if str(quality or '').lower()!='synced':return None
    if occurred_at is None:return None
    try:
        value=aware_utc(occurred_at)
    except (ValueError,TypeError):
        return None
    now=server_now or utc_now()
    if value>now+max_future_skew:return None
    if value<now-max_past_skew:return None
    return value
