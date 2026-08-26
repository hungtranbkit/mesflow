"""Reliability Validation Round 2, Gate 4 -- property-based testing of the
shift-window boundary math (resolve_shift_window_for_datetime /
shift_bounds), with special attention to the exact timestamps called out
in the request: 07:59:59, 08:00:00, 16:59:59, 17:00:00, 17:59:59, 18:00:00,
23:59:59, 00:00:00, 00:00:01, and a custom cross-midnight shift.

Pure function, no DB -- this runs hundreds of examples in well under a
second, unlike the real-DB session-lifecycle state machine in
tests/integration/test_session_lifecycle_state_machine_property.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given, example, settings, strategies as st

from mesflow.core.working_calendar import DEFAULT_SHIFTS, resolve_shift_window_for_datetime

TZ = ZoneInfo('Asia/Ho_Chi_Minh')

# A genuine cross-midnight shift (22:00 -> 06:00 next day), distinct from
# DEFAULT_SHIFTS' NIGHT (18:00 -> 00:00, cross_midnight=False -- it never
# actually crosses into the next calendar day's minute numbering). This is
# the shape resolve_shift_window_for_datetime's _anchor_date_for() docstring
# says needs anchor-day rollback: intervals ending past minute 1440.
CROSS_MIDNIGHT_SHIFT = {
    "code": "GRAVEYARD", "name": "Ca xuyên đêm", "timezone": "Asia/Ho_Chi_Minh",
    "anchor_start": "22:00", "anchor_end": "06:00", "cross_midnight": True, "target_minutes": 480,
    "working_weekdays": [0, 1, 2, 3, 4, 5],
    "intervals": [
        {"interval_type": "WORK", "start_minute": 1320, "end_minute": 1440 + 60, "label": "Đầu ca"},
        {"interval_type": "BREAK", "start_minute": 1440 + 60, "end_minute": 1440 + 90, "label": "Nghỉ giữa ca"},
        {"interval_type": "WORK", "start_minute": 1440 + 90, "end_minute": 1440 + 360, "label": "Cuối ca"},
    ],
}

DAY0 = datetime(2026, 8, 10, tzinfo=TZ)  # a Monday, well inside both shifts' working_weekdays


def at(hour, minute=0, second=0, day_offset=0):
    return DAY0.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=day_offset, hours=hour, minutes=minute, seconds=second)


# ---------------------------------------------------------------------------
# Exact boundary instants called out by name in the request.
# ---------------------------------------------------------------------------

def test_07_59_59_is_before_day_shift_starts():
    assert resolve_shift_window_for_datetime(at(7, 59, 59), DEFAULT_SHIFTS) is None


def test_08_00_00_enters_day_shift():
    resolved = resolve_shift_window_for_datetime(at(8, 0, 0), DEFAULT_SHIFTS)
    assert resolved is not None and resolved[0]['code'] == 'DAY'
    assert resolved[1] == at(8, 0, 0)


def test_16_59_59_is_still_day_shift():
    resolved = resolve_shift_window_for_datetime(at(16, 59, 59), DEFAULT_SHIFTS)
    assert resolved is not None and resolved[0]['code'] == 'DAY'


def test_17_00_00_is_day_shift_end_and_belongs_to_no_shift():
    # DAY's window is [08:00,17:00) -- the end instant itself is exclusive,
    # and DEFAULT_SHIFTS leaves a genuine 17:00-18:00 gap before NIGHT.
    assert resolve_shift_window_for_datetime(at(17, 0, 0), DEFAULT_SHIFTS) is None


def test_17_59_59_is_still_the_gap_before_night():
    assert resolve_shift_window_for_datetime(at(17, 59, 59), DEFAULT_SHIFTS) is None


def test_18_00_00_enters_night_shift():
    resolved = resolve_shift_window_for_datetime(at(18, 0, 0), DEFAULT_SHIFTS)
    assert resolved is not None and resolved[0]['code'] == 'NIGHT'
    assert resolved[1] == at(18, 0, 0)


def test_23_59_59_is_still_night_shift():
    resolved = resolve_shift_window_for_datetime(at(23, 59, 59), DEFAULT_SHIFTS)
    assert resolved is not None and resolved[0]['code'] == 'NIGHT'


def test_00_00_00_is_night_shift_end_and_belongs_to_no_shift():
    # NIGHT's window for "today" is [18:00 today, 00:00 tomorrow) -- the end
    # instant itself is exclusive. DEFAULT_SHIFTS' NIGHT has
    # cross_midnight=False (it ends exactly AT midnight, never crossing
    # into the next day's own minute numbering), so this is correctly a
    # NO_ACTIVE_SHIFT gap, not "still NIGHT" and not "already DAY".
    assert resolve_shift_window_for_datetime(at(0, 0, 0, day_offset=1), DEFAULT_SHIFTS) is None


def test_00_00_01_is_still_the_gap_before_day():
    assert resolve_shift_window_for_datetime(at(0, 0, 1, day_offset=1), DEFAULT_SHIFTS) is None


# ---------------------------------------------------------------------------
# The same boundary shape, but for a REAL cross-midnight shift (22:00 -> 06:00),
# where the anchor-day rollback logic actually has to fire.
# ---------------------------------------------------------------------------

def test_cross_midnight_shift_covers_its_own_late_evening():
    resolved = resolve_shift_window_for_datetime(at(23, 0, 0), [CROSS_MIDNIGHT_SHIFT])
    assert resolved is not None
    assert resolved[1] == at(22, 0, 0) and resolved[2] == at(6, 0, 0, day_offset=1)


def test_cross_midnight_shift_covers_the_following_early_morning_under_the_same_anchor():
    # 02:00 "the next calendar day" is still part of the shift instance that
    # STARTED the previous evening at 22:00 -- this is exactly what
    # cross_midnight=True's anchor-day rollback exists for.
    resolved = resolve_shift_window_for_datetime(at(2, 0, 0, day_offset=1), [CROSS_MIDNIGHT_SHIFT])
    assert resolved is not None
    assert resolved[1] == at(22, 0, 0) and resolved[2] == at(6, 0, 0, day_offset=1)


def test_cross_midnight_shift_05_59_59_still_inside_06_00_00_outside():
    assert resolve_shift_window_for_datetime(at(5, 59, 59, day_offset=1), [CROSS_MIDNIGHT_SHIFT]) is not None
    assert resolve_shift_window_for_datetime(at(6, 0, 0, day_offset=1), [CROSS_MIDNIGHT_SHIFT]) is None


def test_cross_midnight_shift_21_59_59_not_yet_started():
    assert resolve_shift_window_for_datetime(at(21, 59, 59), [CROSS_MIDNIGHT_SHIFT]) is None


# ---------------------------------------------------------------------------
# General properties across randomized instants (hundreds of examples).
# ---------------------------------------------------------------------------

_moment_strategy = st.builds(
    lambda day_offset, hour, minute, second: at(hour, minute, second, day_offset=day_offset),
    day_offset=st.integers(min_value=-3, max_value=3),
    hour=st.integers(min_value=0, max_value=23),
    minute=st.integers(min_value=0, max_value=59),
    second=st.integers(min_value=0, max_value=59),
)


@settings(max_examples=500, deadline=None)
@given(moment=_moment_strategy)
@example(moment=at(8, 0, 0))
@example(moment=at(17, 0, 0))
@example(moment=at(0, 0, 0, day_offset=1))
def test_resolved_window_always_contains_the_moment_half_open(moment):
    for shifts in (DEFAULT_SHIFTS, [CROSS_MIDNIGHT_SHIFT]):
        resolved = resolve_shift_window_for_datetime(moment, shifts)
        if resolved is None:
            continue
        shift, start, end = resolved
        # The defining half-open-interval property: start<=moment<end,
        # never moment==end (end is the FIRST instant NOT in the shift).
        assert start <= moment < end
        assert end > start


@settings(max_examples=500, deadline=None)
@given(moment=_moment_strategy)
def test_resolution_is_deterministic(moment):
    a = resolve_shift_window_for_datetime(moment, DEFAULT_SHIFTS)
    b = resolve_shift_window_for_datetime(moment, DEFAULT_SHIFTS)
    assert a == b


@settings(max_examples=500, deadline=None)
@given(moment=_moment_strategy)
def test_default_shifts_day_and_night_never_overlap(moment):
    # DAY and NIGHT are configured as non-overlapping in DEFAULT_SHIFTS;
    # this is a config-sanity property for that specific configuration, not
    # a claim that any arbitrary shift set can't be misconfigured to
    # overlap.
    resolved = resolve_shift_window_for_datetime(moment, DEFAULT_SHIFTS)
    if resolved is None:
        return
    shift, start, end = resolved
    other = [s for s in DEFAULT_SHIFTS if s['code'] != shift['code']]
    other_resolved = resolve_shift_window_for_datetime(moment, other)
    assert other_resolved is None, f'{moment} matched both {shift["code"]} and {other_resolved[0]["code"]}'
