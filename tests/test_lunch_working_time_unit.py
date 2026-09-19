from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest

from mesflow.core.working_calendar import working_intervals_between, all_shift_working_seconds_between
from mesflow.db.repositories.analytics import DashboardRepository, ReportRepository

ZONE = ZoneInfo("Asia/Ho_Chi_Minh")
SHIFTS = [
    {"code":"DAY","timezone":"Asia/Ho_Chi_Minh","anchor_start":"07:30","anchor_end":"17:00",
     "working_weekdays":[0,1,2,3,4,5],"cross_midnight":False,"target_minutes":480,
     "intervals":[{"interval_type":"WORK","start_minute":450,"end_minute":690},
                  {"interval_type":"BREAK","start_minute":690,"end_minute":780},
                  {"interval_type":"WORK","start_minute":780,"end_minute":1020}]},
    {"code":"NIGHT","timezone":"Asia/Ho_Chi_Minh","anchor_start":"18:00","anchor_end":"00:00",
     "working_weekdays":[0,1,2,3,4,5],"cross_midnight":False,"target_minutes":300,
     "intervals":[{"interval_type":"WORK","start_minute":1080,"end_minute":1320},
                  {"interval_type":"BREAK","start_minute":1320,"end_minute":1380},
                  {"interval_type":"WORK","start_minute":1380,"end_minute":1440}]},
]
def moment(clock, day="2026-09-18"):
    return datetime.fromisoformat(day+"T"+clock).replace(tzinfo=ZONE)

@pytest.mark.parametrize("left,right,minutes", [
    ("07:30","17:00",480), ("11:00","14:00",90),
    ("11:15","12:15",15), ("12:00","12:45",0),
    ("11:30","13:00",0), ("13:00","14:00",60),
    ("06:00","07:30",0), ("17:00","18:00",0),
    ("18:00","23:30",270),
])
def test_working_duration_excludes_lunch_and_other_breaks(left,right,minutes):
    with patch("mesflow.core.working_calendar.get_work_shifts",return_value=SHIFTS):
        assert all_shift_working_seconds_between(moment(left),moment(right)) == minutes*60

def test_duplicate_shift_windows_are_not_counted_twice():
    spans=working_intervals_between(moment("07:30"),moment("17:00"),SHIFTS+[SHIFTS[0]])
    assert sum((b-a).total_seconds() for a,b in spans)==480*60

def test_sunday_has_no_work():
    assert working_intervals_between(moment("07:30","2026-09-20"),moment("17:00","2026-09-20"),SHIFTS)==[]

def test_day_keeps_previous_anchor_night_shift_and_clips_at_midnight():
    shift={**SHIFTS[1],"anchor_start":"22:00","anchor_end":"06:00","cross_midnight":True,
      "intervals":[{"interval_type":"WORK","start_minute":1320,"end_minute":1440},
                   {"interval_type":"BREAK","start_minute":1440,"end_minute":1500},
                   {"interval_type":"WORK","start_minute":1500,"end_minute":1800}]}
    spans=working_intervals_between(moment("00:00"),moment("07:00"),[shift])
    assert spans==[(moment("01:00"),moment("06:00"))]

def test_day_context_keeps_membership_full_day_but_work_excludes_breaks():
    with patch("mesflow.core.working_calendar.get_work_shifts",return_value=SHIFTS):
        ctx=DashboardRepository._calendar_day_context("2026-09-18")
    assert ctx["range_start"]==moment("00:00")
    assert ctx["range_end"]==moment("00:00","2026-09-19")
    work=[iv for iv in ctx["intervals"] if iv["interval_type"]=="WORK"]
    assert sum((iv["end_at"]-iv["start_at"]).total_seconds() for iv in work)==780*60
    assert not any(iv["start_minute"]<780 and iv["end_minute"]>690 for iv in work)

@pytest.mark.parametrize("now,minutes", [("11:30",30),("12:15",30),("13:00",30),("13:15",45)])
def test_open_session_stops_accruing_during_lunch(now,minutes):
    rows=[{"started_at":moment("11:00"),"ended_at":None,"duration_seconds":9999}]
    with patch("mesflow.db.repositories.analytics.get_work_shifts",return_value=SHIFTS), patch("mesflow.db.repositories.analytics.utc_now",return_value=moment(now)):
        ReportRepository._attach_work_durations(rows)
    assert rows[0]["work_duration_seconds"]==minutes*60
    assert rows[0]["duration_seconds"]==9999
