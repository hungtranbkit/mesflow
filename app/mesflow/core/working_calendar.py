from __future__ import annotations
from datetime import datetime, date, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from mesflow.core.config import settings
from mesflow.core.time_policy import business_date

DEFAULT_SHIFTS = [
    {"code":"DAY","name":"Ca ngày","timezone":"Asia/Ho_Chi_Minh","anchor_start":"08:00","anchor_end":"17:00","cross_midnight":False,"target_minutes":480,"working_weekdays":[0,1,2,3,4,5],"intervals":[
        {"interval_type":"WORK","start_minute":480,"end_minute":720,"label":"Ca sáng"},
        {"interval_type":"BREAK","start_minute":720,"end_minute":780,"label":"Nghỉ trưa"},
        {"interval_type":"WORK","start_minute":780,"end_minute":1020,"label":"Ca chiều"}]},
    {"code":"NIGHT","name":"Ca tối","timezone":"Asia/Ho_Chi_Minh","anchor_start":"18:00","anchor_end":"00:00","cross_midnight":False,"target_minutes":300,"working_weekdays":[0,1,2,3,4,5],"intervals":[
        {"interval_type":"WORK","start_minute":1080,"end_minute":1320,"label":"Đầu ca tối"},
        {"interval_type":"BREAK","start_minute":1320,"end_minute":1380,"label":"Nghỉ giữa ca"},
        {"interval_type":"WORK","start_minute":1380,"end_minute":1440,"label":"Cuối ca tối"}]},
]

def _clock(value: Any) -> str:
    if value is None: return "00:00"
    return value.strftime("%H:%M") if hasattr(value,"strftime") else str(value)[:5]

def get_work_shifts(active_only: bool=True) -> list[dict[str,Any]]:
    from mesflow.db.connection import fetch_all
    try:
        clause="WHERE s.active=true" if active_only else ""
        rows=fetch_all(f"""SELECT s.id,s.code,s.name,s.timezone,s.anchor_start,s.anchor_end,s.cross_midnight,
          s.target_minutes,s.working_weekdays,s.sort_order,s.active,
          COALESCE(json_agg(json_build_object('id',i.id,'interval_type',i.interval_type,'start_minute',i.start_minute,
          'end_minute',i.end_minute,'label',i.label,'sort_order',i.sort_order) ORDER BY i.sort_order)
          FILTER (WHERE i.id IS NOT NULL),'[]'::json) intervals
          FROM work_shifts s LEFT JOIN work_shift_intervals i ON i.shift_id=s.id {clause}
          GROUP BY s.id ORDER BY s.sort_order,s.id""")
        result=[]
        for r in rows:
            item=dict(r);item['anchor_start']=_clock(item['anchor_start']);item['anchor_end']=_clock(item['anchor_end'])
            item['working_weekdays']=[int(x) for x in (item.get('working_weekdays') or [])]
            item['intervals']=[dict(x) for x in (item.get('intervals') or [])]
            result.append(item)
        return result or [dict(x) for x in DEFAULT_SHIFTS]
    except Exception:
        return [dict(x) for x in DEFAULT_SHIFTS]

def get_work_shift(code: str|None=None, shift_id: int|None=None) -> dict[str,Any]:
    shifts=get_work_shifts()
    if shift_id is not None:
        for s in shifts:
            if int(s.get('id') or 0)==int(shift_id): return s
        raise ValueError(f'Không tìm thấy ca làm việc #{shift_id}')
    if code:
        for s in shifts:
            if str(s.get('code')).upper()==str(code).upper(): return s
        raise ValueError(f'Không tìm thấy ca làm việc {code}')
    return shifts[0]

def resolve_shift_context(shift_date_value: str|date|None, shift_id: int|None=None, shift_code: str|None=None) -> dict[str,Any]:
    zone_now=datetime.now(ZoneInfo(settings.timezone_name))
    if isinstance(shift_date_value,date): selected=shift_date_value
    elif str(shift_date_value or '').strip(): selected=date.fromisoformat(str(shift_date_value).strip())
    else: selected=business_date(timezone_name=settings.timezone_name)
    shift=get_work_shift(shift_code,shift_id)
    start,end=shift_bounds(selected,shift)
    base=datetime.combine(selected,time(0,0),tzinfo=start.tzinfo)
    intervals=[]
    for iv in shift.get('intervals',[]):
        item=dict(iv)
        item['start_at']=base+timedelta(minutes=int(iv['start_minute']))
        item['end_at']=base+timedelta(minutes=int(iv['end_minute']))
        intervals.append(item)
    return {'shift_date':selected,'shift':shift,'range_start':start,'range_end':end,'intervals':intervals}

def get_working_calendar() -> dict[str,Any]:
    """Compatibility view for older callers; backed by the DAY shift table."""
    s=get_work_shift('DAY'); work=[x for x in s['intervals'] if x['interval_type']=='WORK']
    br=[x for x in s['intervals'] if x['interval_type']=='BREAK']
    hm=lambda n:f"{(int(n)//60)%24:02d}:{int(n)%60:02d}"
    return {'timezone':s['timezone'],'work_start':hm(work[0]['start_minute']),'lunch_start':hm(br[0]['start_minute']) if br else hm(work[0]['end_minute']),
      'lunch_end':hm(br[0]['end_minute']) if br else hm(work[-1]['start_minute']),'work_end':hm(work[-1]['end_minute']),
      'working_weekdays':s['working_weekdays'],'shift_code':s['code'],'target_minutes':s['target_minutes']}

def _anchor_date_for(moment: datetime, shift: dict[str,Any]) -> date:
    zone=ZoneInfo(shift.get('timezone') or settings.timezone_name)
    if moment.tzinfo is None:raise ValueError('naive datetime is not allowed in shift logic')
    local=moment.astimezone(zone)
    minute=local.hour*60+local.minute
    if shift.get('cross_midnight') and minute < int(shift['intervals'][-1]['end_minute'])-1440:
        return local.date()-timedelta(days=1)
    return local.date()

def shift_bounds(shift_date: date, shift: dict[str,Any]) -> tuple[datetime,datetime]:
    zone=ZoneInfo(shift.get('timezone') or settings.timezone_name)
    start_h,start_m=map(int,shift['anchor_start'].split(':'));end_h,end_m=map(int,shift['anchor_end'].split(':'))
    start=datetime.combine(shift_date,time(start_h,start_m),tzinfo=zone)
    end_is_midnight=(end_h==0 and end_m==0 and (start_h!=0 or start_m!=0))
    end_day=shift_date+timedelta(days=1 if shift.get('cross_midnight') or end_is_midnight else 0)
    return start,datetime.combine(end_day,time(end_h,end_m),tzinfo=zone)

def resolve_shift_for_datetime(moment: datetime) -> dict[str,Any]:
    for shift in get_work_shifts():
        anchor=_anchor_date_for(moment,shift);start,end=shift_bounds(anchor,shift)
        if moment.tzinfo is None:raise ValueError('naive datetime is not allowed in shift logic')
        local=moment.astimezone(start.tzinfo)
        if start<=local<end:return shift
    return get_work_shift('DAY')

def working_seconds_between(start: datetime,end: datetime,cfg: dict[str,Any]|None=None,shift_code: str|None=None) -> int:
    if not start or not end or end<=start:return 0
    shift=get_work_shift(shift_code) if shift_code else (get_work_shift(cfg.get('shift_code')) if cfg and cfg.get('shift_code') else resolve_shift_for_datetime(start))
    zone=ZoneInfo(shift.get('timezone') or settings.timezone_name)
    if start.tzinfo is None or end.tzinfo is None:raise ValueError('naive datetime is not allowed in working-time logic')
    start=start.astimezone(zone);end=end.astimezone(zone)
    total=0.0;anchor=_anchor_date_for(start,shift)-timedelta(days=1)
    last=_anchor_date_for(end,shift)+timedelta(days=1)
    while anchor<=last:
        if anchor.weekday() in {int(x) for x in shift.get('working_weekdays',[])}:
            base=datetime.combine(anchor,time(0,0),tzinfo=zone)
            for interval in shift.get('intervals',[]):
                if interval.get('interval_type')!='WORK':continue
                left=base+timedelta(minutes=int(interval['start_minute']));right=base+timedelta(minutes=int(interval['end_minute']))
                a,b=max(start,left),min(end,right)
                if b>a:total+=(b-a).total_seconds()
        anchor+=timedelta(days=1)
    return max(0,int(total))

def all_shift_working_seconds_between(start:datetime,end:datetime)->int:
    """Allocate a long session across every configured shift without double counting overlaps."""
    if not start or not end or end<=start:return 0
    if start.tzinfo is None or end.tzinfo is None:raise ValueError('naive datetime is not allowed in working-time logic')
    spans=[]
    for shift in get_work_shifts():
        zone=ZoneInfo(shift.get('timezone') or settings.timezone_name);left=start.astimezone(zone);right=end.astimezone(zone)
        anchor=_anchor_date_for(left,shift)-timedelta(days=1);last=_anchor_date_for(right,shift)+timedelta(days=1)
        weekdays={int(x) for x in shift.get('working_weekdays',[])}
        while anchor<=last:
            if anchor.weekday() in weekdays:
                base=datetime.combine(anchor,time(0,0),tzinfo=zone)
                for interval in shift.get('intervals',[]):
                    if interval.get('interval_type')!='WORK':continue
                    a=max(left,base+timedelta(minutes=int(interval['start_minute'])));b=min(right,base+timedelta(minutes=int(interval['end_minute'])))
                    if b>a:spans.append((a.astimezone(ZoneInfo('UTC')),b.astimezone(ZoneInfo('UTC'))))
            anchor+=timedelta(days=1)
    spans.sort(key=lambda x:x[0]);merged=[]
    for left,right in spans:
        if merged and left<=merged[-1][1]:merged[-1]=(merged[-1][0],max(merged[-1][1],right))
        else:merged.append((left,right))
    return int(sum((right-left).total_seconds() for left,right in merged))
