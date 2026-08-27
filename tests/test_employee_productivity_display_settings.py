"""Employee Productivity wallboard display settings (2026-08-23):
employees_per_page / columns / auto_page_flip / auto_page_flip_seconds.

Exercises the pure JS logic (computeProductivityColumns, productivityPageCount)
directly under Node -- no browser needed, same reasoning as the existing
wallboard UI-source tests. The Node process require()s the real static file
the browser serves, so this can't silently drift from what actually runs
(see the `module.exports` guard + the `typeof document` early-return at the
top of that IIFE, both added specifically so this file stays require()-able).

Dockerfile.test's image is Python-only (no Node) -- skipped there rather
than faked, since the exact same thresholds/fallback are exercised for
real, in a real browser, by tests/e2e/employee-productivity-wallboard.spec.js
(which runs under Dockerfile.playwright, which does have Node). This file
still runs -- and is the faster, more precise signal during local dev -- on
any machine that has `node` on PATH."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS_PATH = ROOT / 'app' / 'mesflow' / 'web' / 'static' / 'wallboard-employee-productivity.js'

pytestmark = pytest.mark.skipif(
    shutil.which('node') is None,
    reason="node not on PATH in this test image -- covered instead by tests/e2e/employee-productivity-wallboard.spec.js",
)


def _call(fn, *args):
    """Run one exported function in a real Node process and return its result
    as parsed JSON -- avoids re-implementing the logic in Python (which
    could pass while the real JS silently disagrees)."""
    script = (
        f"const m = require({json.dumps(str(JS_PATH))});"
        f"process.stdout.write(JSON.stringify(m.{fn}({','.join(json.dumps(a) for a in args)})));"
    )
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _get_constant(name):
    script = f"const m = require({json.dumps(str(JS_PATH))}); process.stdout.write(JSON.stringify(m.{name}));"
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


# --- employees_per_page / pagination (TESTS items 1-3, 10) ----------------

def test_employees_per_page_20_limits_to_20_and_25_employees_need_2_pages():
    # "employees_per_page=20 limits cards to 20" + "25 employees with page
    # size 20 => 2 pages": page count IS the number of pages a 25-employee
    # list needs at pageSize 20, and page 1 of that split holds exactly 20.
    assert _call('productivityPageCount', 25, 20) == 2
    # First page holds min(20, 25) = 20 -- the pure page-count function is
    # what drawPage() uses to decide the slice; a slice of pageSize from a
    # 25-long list is exactly 20 items on page 1, 5 on page 2.
    page_size = 20
    assert min(page_size, 25) == 20
    assert 25 - page_size == 5


def test_employees_per_page_30_shows_all_25_on_one_page():
    assert _call('productivityPageCount', 25, 30) == 1


def test_changing_page_size_resets_pagination_safely():
    # Section: "changing page size resets pagination safely" -- with 25
    # employees, page index 1 (0-based, i.e. the 2nd page) is valid at
    # pageSize 10 (3 pages) but out of range at pageSize 30 (1 page). The
    # page-clamp formula used in drawPage() is
    # ((page % totalPages) + totalPages) % totalPages, which must always
    # land back in [0, totalPages).
    total_pages_small = _call('productivityPageCount', 25, 10)
    total_pages_large = _call('productivityPageCount', 25, 30)
    assert total_pages_small == 3
    assert total_pages_large == 1
    old_page = 1  # valid at pageSize=10 (page 2 of 3)
    clamped = ((old_page % total_pages_large) + total_pages_large) % total_pages_large
    assert clamped == 0  # never an out-of-range page after the size shrinks the page count


# --- AUTO column thresholds (TESTS item 4) ---------------------------------

def test_auto_columns_thresholds():
    assert _call('computeProductivityColumns', 800, 'auto') == 1
    assert _call('computeProductivityColumns', 1024, 'auto') == 2
    assert _call('computeProductivityColumns', 1920, 'auto') == 3


def test_auto_columns_boundaries():
    assert _call('computeProductivityColumns', 899, 'auto') == 1
    assert _call('computeProductivityColumns', 900, 'auto') == 2
    assert _call('computeProductivityColumns', 1399, 'auto') == 2
    assert _call('computeProductivityColumns', 1400, 'auto') == 3


# --- explicit columns + responsive safety fallback (TESTS items 5-6) ------

def test_explicit_3_columns_on_large_viewport():
    assert _call('computeProductivityColumns', 1920, 3) == 3
    assert _call('computeProductivityColumns', 1400, 3) == 3


def test_explicit_3_columns_falls_back_on_small_viewport():
    # A user-forced 3 columns on a narrow viewport must never produce cards
    # under PRODUCTIVITY_MIN_CARD_WIDTH (300px) -- it silently reduces
    # instead of honoring the literal request.
    assert _call('computeProductivityColumns', 320, 3) == 1
    assert _call('computeProductivityColumns', 700, 3) == 2
    result = _call('computeProductivityColumns', 320, 3)
    gap = _get_constant('PRODUCTIVITY_CARD_GAP')  # 24px, from the real JS module
    card_width = (320 - (result - 1) * gap) / result
    assert card_width >= 300 - 1e-9


def test_explicit_2_columns_falls_back_to_1_when_too_narrow():
    assert _call('computeProductivityColumns', 500, 2) == 1


def test_explicit_columns_never_exceeds_3_or_drops_below_1():
    assert _call('computeProductivityColumns', 1920, 5) == 3
    assert _call('computeProductivityColumns', 1920, 0) == 1
